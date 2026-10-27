"""Demo data for the soutenance: 1 admin, 3 PME, 3 transporteurs, annonces, trips,
bookings in every status, messages, reviews, a report and a fraud-flagged annonce.

Idempotent: demo accounts are deleted and recreated on each run.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.fraud import screen_object
from apps.accounts.models import CarrierProfile, CompanyProfile, Report, User
from apps.bookings import services
from apps.bookings.models import BookingRequest
from apps.messaging.models import Message
from apps.reviews.ai import handle as sentiment_handle
from apps.reviews.models import Review
from apps.reviews.services import refresh_carrier_stats
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip, Vehicle
from apps.trips.pricing import suggest_price

ADMIN_PASSWORD = "Admin2026!"
DEMO_PASSWORD = "Demo2026!"

PMES = [
    ("pme_sfax", "Agro Sfax SARL", "Sfax", "Agroalimentaire", "Leila", "Ben Salah"),
    ("pme_monastir", "Textiles Monastir", "Monastir", "Textile", "Karim", "Trabelsi"),
    ("pme_bizerte", "Matériaux du Nord", "Bizerte", "BTP", "Sonia", "Gharbi"),
]
CARRIERS = [
    ("trans_sahel", "Trans Sahel", "Sousse", "Mehdi", "Jlassi"),
    ("frigo_sud", "Frigo Sud Express", "Gabès", "Amine", "Haddad"),
    ("capbon_log", "Cap Bon Logistique", "Nabeul", "Rim", "Mansouri"),
]


class Command(BaseCommand):
    help = "Crée les comptes et données de démonstration CargoLink."

    def make_user(self, username, password, role, first, last, **extra):
        user = User.objects.create_user(
            username=username,
            password=password,
            role=role,
            first_name=first,
            last_name=last,
            email=f"{username}@demo.cargolink.tn",
            **extra,
        )
        return user

    def add_arguments(self, parser):
        parser.add_argument(
            "--if-empty",
            action="store_true",
            help="Ne rien faire si les comptes de démo existent déjà (utilisé au démarrage sur Render).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["if_empty"] and User.objects.filter(username="admin").exists():
            self.stdout.write("Données de démonstration déjà présentes : rien à faire.")
            return
        usernames = ["admin", "promo_fret"] + [p[0] for p in PMES] + [c[0] for c in CARRIERS]
        Trip.objects.filter(carrier__username__in=usernames).delete()  # vehicles are PROTECTed by trips
        User.objects.filter(username__in=usernames).delete()
        today = timezone.localdate()
        d = lambda n: today + timedelta(days=n)  # noqa: E731

        self.make_user("admin", ADMIN_PASSWORD, User.Role.ADMIN, "Admin", "CargoLink", is_staff=True, is_superuser=True)

        pmes = []
        for username, company, city, sector, first, last in PMES:
            u = self.make_user(username, DEMO_PASSWORD, User.Role.PME, first, last, phone="+216 74 000 000")
            CompanyProfile.objects.create(
                user=u, company_name=company, city=city, sector=sector, description=f"{company}, PME basée à {city}."
            )
            pmes.append(u)
        carriers = []
        for username, company, city, first, last in CARRIERS:
            u = self.make_user(username, DEMO_PASSWORD, User.Role.TRANSPORTEUR, first, last)
            CarrierProfile.objects.create(
                user=u,
                company_name=company,
                city=city,
                license_number=f"TR-{city[:3].upper()}-2024",
                description=f"Transporteur indépendant basé à {city}.",
            )
            carriers.append(u)
        sfax, monastir, bizerte = pmes
        sahel, frigo, capbon = carriers

        v = {
            "sahel_semi": Vehicle.objects.create(
                carrier=sahel, vehicle_type="semi", plate_number="210 TU 4521", capacity_kg=24000, capacity_m3=80
            ),
            "sahel_van": Vehicle.objects.create(
                carrier=sahel, vehicle_type="camionnette", plate_number="198 TU 1102", capacity_kg=1500, capacity_m3=12
            ),
            "frigo": Vehicle.objects.create(
                carrier=frigo,
                vehicle_type="frigo",
                plate_number="225 TU 7788",
                capacity_kg=12000,
                capacity_m3=45,
                refrigerated=True,
            ),
            "capbon": Vehicle.objects.create(
                carrier=capbon, vehicle_type="camion", plate_number="203 TU 3344", capacity_kg=8000, capacity_m3=35
            ),
        }

        def trip(carrier, vehicle, o, dest, day, kg, m3, per_kg=None, fixed=None, notes=""):
            return Trip.objects.create(
                carrier=carrier,
                vehicle=vehicle,
                origin=o,
                destination=dest,
                departure_date=d(day),
                available_weight_kg=kg,
                available_volume_m3=m3,
                pricing_mode="fixed" if fixed else "per_kg",
                price_per_kg=Decimal(str(per_kg)) if per_kg else None,
                fixed_price=Decimal(str(fixed)) if fixed else None,
                notes=notes,
            )

        def freight(pme, title, mtype, kg, m3, o, dest, pick, deadline, budget_factor=1.05, constraints="", desc=""):
            # budgets close to the price model's market estimate, as a real PME would post
            market = suggest_price(o, dest, kg, m3, mtype, deadline - pick)["price"]
            return FreightRequest.objects.create(
                pme=pme,
                title=title,
                merchandise_type=mtype,
                weight_kg=kg,
                volume_m3=m3,
                origin=o,
                destination=dest,
                pickup_date=d(pick),
                delivery_deadline=d(deadline),
                budget=Decimal(round(market * budget_factor)) if budget_factor else None,
                constraints=constraints,
                description=desc
                or "Marchandise conditionnée sur palettes, chargement à quai, bon de livraison fourni.",
            )

        # Trips (future)
        t_sfax_tunis = trip(
            sahel,
            v["sahel_semi"],
            "Sfax",
            "Tunis",
            2,
            14000,
            50,
            per_kg=0.045,
            notes="Retour à vide habituel le mardi, chargement possible dès 7h.",
        )
        t_sousse_tunis = trip(sahel, v["sahel_van"], "Sousse", "Tunis", 3, 1200, 10, fixed=180)
        t_gabes_tunis = trip(
            frigo, v["frigo"], "Gabès", "Tunis", 2, 10000, 40, per_kg=0.06, notes="Camion frigorifique 2–8 °C."
        )
        trip(frigo, v["frigo"], "Béja", "Sfax", 6, 9000, 35, per_kg=0.055)
        t_nabeul_bizerte = trip(capbon, v["capbon"], "Nabeul", "Bizerte", 4, 7000, 30, fixed=650)
        t_monastir_tunis = trip(capbon, v["capbon"], "Monastir", "Tunis", 5, 6000, 28, per_kg=0.04)
        trip(capbon, v["capbon"], "Bizerte", "Sousse", 8, 7500, 30, per_kg=0.05)
        trip(sahel, v["sahel_semi"], "Tunis", "Gabès", 9, 20000, 70, per_kg=0.05)

        # Annonces (future)
        f_tomates = freight(
            sfax,
            "20 palettes de tomates",
            "agricole",
            10000,
            30,
            "Sfax",
            "Tunis",
            1,
            4,
            desc="Tomates en cagettes sur palettes, marché de gros de Bir El Kassaa.",
        )
        f_huile = freight(
            sfax, "Huile d'olive en bidons", "alimentaire", 800, 1.2, "Sfax", "Tunis", 2, 5, constraints="fragile"
        )
        f_yaourt = freight(
            sfax, "Produits laitiers réfrigérés", "frais", 3000, 12, "Gabès", "Tunis", 1, 3, constraints="réfrigéré"
        )
        f_textile = freight(monastir, "120 cartons de vêtements", "textile", 1800, 7.2, "Monastir", "Tunis", 4, 7)
        f_tissu = freight(monastir, "Rouleaux de tissu", "textile", 900, 4, "Sousse", "Tunis", 3, 6)
        f_ciment = freight(bizerte, "4 tonnes de ciment", "materiaux", 4000, 3.5, "Nabeul", "Bizerte", 3, 6)
        freight(bizerte, "Carrelage pour chantier", "materiaux", 5000, 4.5, "Bizerte", "Sousse", 7, 10)
        freight(monastir, "Machines à coudre", "industriel", 600, 3, "Monastir", "Sfax", 5, 9, budget_factor=None)

        # Bookings in every status
        b_pending = services.create_booking(
            freight=f_huile,
            trip=t_sfax_tunis,
            sender=sfax,
            proposed_price=((f_huile.budget or 0) * Decimal("0.95")).quantize(Decimal("1")),
            message="Bonjour, est-ce possible de charger 2 palettes mardi matin ?",
        )
        services.create_booking(
            freight=f_textile,
            trip=t_monastir_tunis,
            sender=capbon,
            proposed_price=((f_textile.budget or 0) * Decimal("1.0")).quantize(Decimal("1")),
            message="Je passe par Monastir jeudi, place dispo.",
        )
        b_accepted = services.create_booking(
            freight=f_tomates,
            trip=t_sfax_tunis,
            sender=sfax,
            proposed_price=((f_tomates.budget or 0) * Decimal("0.95")).quantize(Decimal("1")),
            message="20 palettes, quai disponible.",
        )
        services.transition(b_accepted, BookingRequest.Status.ACCEPTED, sahel)
        b_progress = services.create_booking(
            freight=f_yaourt,
            trip=t_gabes_tunis,
            sender=frigo,
            proposed_price=((f_yaourt.budget or 0) * Decimal("1.0")).quantize(Decimal("1")),
            message="Frigo 4 °C, départ à 6h.",
        )
        services.transition(b_progress, BookingRequest.Status.ACCEPTED, sfax)
        services.transition(b_progress, BookingRequest.Status.IN_PROGRESS, frigo)
        b_refused = services.create_booking(
            freight=f_tissu,
            trip=t_sousse_tunis,
            sender=monastir,
            proposed_price=((f_tissu.budget or 0) * Decimal("0.6")).quantize(Decimal("1")),
            message="Prix serré, possible ?",
        )
        services.transition(b_refused, BookingRequest.Status.REFUSED, sahel, "Prix trop bas pour ce trajet")
        b_cancel = services.create_booking(
            freight=f_ciment,
            trip=t_nabeul_bizerte,
            sender=bizerte,
            proposed_price=((f_ciment.budget or 0) * Decimal("1.0")).quantize(Decimal("1")),
            message="Chargement samedi ?",
        )
        services.transition(b_cancel, BookingRequest.Status.CANCELLED, bizerte, "Chantier reporté")

        # Delivered bookings (past dates) with reviews
        delivered = []
        past = [
            (
                sfax,
                sahel,
                v["sahel_semi"],
                "Sfax",
                "Tunis",
                "Dattes deglet nour",
                "agricole",
                2500,
                450,
                5,
                "Livraison rapide et soignée, chauffeur ponctuel. Je recommande Trans Sahel.",
            ),
            (
                monastir,
                capbon,
                v["capbon"],
                "Monastir",
                "Tunis",
                "Cartons de jeans",
                "textile",
                1200,
                160,
                4,
                "Service correct, livré dans les délais, un peu de retard au chargement.",
            ),
            (
                bizerte,
                capbon,
                v["capbon"],
                "Bizerte",
                "Nabeul",
                "Fer à béton",
                "materiaux",
                5000,
                520,
                2,
                "Livraison en retard de deux jours et aucune communication, très déçu.",
            ),
            (
                sfax,
                frigo,
                v["frigo"],
                "Gabès",
                "Sfax",
                "Poisson frais",
                "frais",
                2000,
                300,
                5,
                "Chaîne du froid parfaitement respectée, transporteur très professionnel.",
            ),
        ]
        for i, (pme, carrier, vehicle, o, dest, title, mtype, kg, price, rating, comment) in enumerate(past):
            t = Trip.objects.create(
                carrier=carrier,
                vehicle=vehicle,
                origin=o,
                destination=dest,
                departure_date=d(-20 + i * 3),
                available_weight_kg=min(kg * 2, vehicle.capacity_kg),
                available_volume_m3=vehicle.capacity_m3 / 2,
                pricing_mode="fixed",
                fixed_price=Decimal(price),
            )
            f = FreightRequest.objects.create(
                pme=pme,
                title=title,
                merchandise_type=mtype,
                weight_kg=kg,
                volume_m3=round(kg / 400, 2),
                origin=o,
                destination=dest,
                pickup_date=d(-21 + i * 3),
                delivery_deadline=d(-18 + i * 3),
                budget=Decimal(price + 50),
            )
            b = services.create_booking(
                freight=f, trip=t, sender=pme, proposed_price=Decimal(price), message="Demande pour notre envoi."
            )
            services.transition(b, BookingRequest.Status.ACCEPTED, carrier)
            services.transition(b, BookingRequest.Status.IN_PROGRESS, carrier)
            services.transition(b, BookingRequest.Status.DELIVERED, carrier)
            t.status = Trip.Status.DONE
            t.save(update_fields=["status"])
            delivered.append((b, rating, comment))
        for b, rating, comment in delivered[:3]:
            r = Review.objects.create(
                booking=b, author=b.freight.pme, carrier=b.trip.carrier, rating=rating, comment=comment
            )
            sentiment_handle({"review_id": r.pk}, None)
        # the 4th delivered booking is left un-reviewed so the PME can rate it live during the demo
        for carrier in carriers:
            refresh_carrier_stats(carrier)

        # Messages
        for b, lines in [
            (
                b_accepted,
                [
                    (sahel, "Bonjour, je confirme le chargement mardi à 7h, quai n°2 ?"),
                    (sfax, "Oui, quai 2. Les palettes seront filmées."),
                    (sahel, "Parfait, à mardi."),
                ],
            ),
            (b_progress, [(frigo, "Chargement effectué, départ de Gabès."), (sfax, "Merci, tenez-nous informés.")]),
            (b_pending, [(sfax, "Les bidons sont sur une palette, 800 kg au total.")]),
        ]:
            for sender, body in lines:
                Message.objects.create(booking=b, sender=sender, body=body)

        # Make the demo history realistic: accounts created months ago, posts spread over the last days
        now = timezone.now()
        for i, u in enumerate(pmes + carriers):
            User.objects.filter(pk=u.pk).update(date_joined=now - timedelta(days=120 + 30 * i))
        for i, obj in enumerate(FreightRequest.objects.filter(pme__in=pmes).order_by("pk")):
            FreightRequest.objects.filter(pk=obj.pk).update(created_at=now - timedelta(days=2 + i))
        for i, obj in enumerate(Trip.objects.filter(carrier__in=carriers).order_by("pk")):
            Trip.objects.filter(pk=obj.pk).update(created_at=now - timedelta(days=2 + i))

        # Moderation: a suspicious annonce screened by the fraud model + a user report
        spammer = self.make_user("promo_fret", DEMO_PASSWORD, User.Role.PME, "Promo", "Fret")
        CompanyProfile.objects.create(user=spammer, company_name="Promo Fret", city="Tunis")
        spam = FreightRequest.objects.create(
            pme=spammer,
            title="OFFRE EXCEPTIONNELLE !!!",
            merchandise_type="autre",
            weight_kg=100,
            volume_m3=0.5,
            origin="Tunis",
            destination="Sfax",
            pickup_date=d(2),
            delivery_deadline=d(4),
            budget=Decimal("5000"),
            description="Gagnez de l'argent facile !!! Paiement d'avance par Western Union, contactez WhatsApp 98 123 456",
        )
        screen_object(spam)
        for obj in FreightRequest.objects.exclude(pk=spam.pk).filter(pickup_date__gte=today):
            screen_object(obj)
        for obj in Trip.objects.filter(departure_date__gte=today):
            screen_object(obj)
        Report.objects.create(
            reporter=monastir,
            content_type=ContentType.objects.get_for_model(spam),
            object_id=spam.pk,
            reason=Report.Reason.SPAM,
            details="Annonce publicitaire, pas du fret.",
        )

        self.stdout.write(self.style.SUCCESS("Données de démonstration créées."))
        self.stdout.write(f"  admin / {ADMIN_PASSWORD}")
        for username in [p[0] for p in PMES] + [c[0] for c in CARRIERS]:
            self.stdout.write(f"  {username} / {DEMO_PASSWORD}")
