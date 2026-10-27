from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.ai.registry import AIInputError
from apps.core.testing.factories import BookingFactory, CarrierFactory, PMEFactory, TripFactory, VehicleFactory, today
from apps.trips import ai, pricing
from apps.trips.forms import TripForm
from apps.trips.models import Trip, Vehicle


def trip_data(vehicle, **over):
    return {
        "vehicle": vehicle.pk,
        "origin": "Sfax",
        "destination": "Tunis",
        "departure_date": today(3).isoformat(),
        "available_weight_kg": 3000,
        "available_volume_m3": 10,
        "pricing_mode": "per_kg",
        "price_per_kg": "0.05",
        "fixed_price": "",
        "notes": "",
        **over,
    }


class TripModelTests(TestCase):
    def test_capacity_and_quote(self):
        t = TripFactory(available_weight_kg=1000, available_volume_m3=5, reserved_weight_kg=400, reserved_volume_m3=2)
        self.assertEqual(t.remaining_weight_kg, 600)
        self.assertEqual(t.remaining_volume_m3, 3)
        self.assertTrue(t.can_carry(600, 3))
        self.assertFalse(t.can_carry(601, 1))
        self.assertEqual(t.quote(100), Decimal("5.00"))
        t.pricing_mode, t.fixed_price = Trip.Pricing.FIXED, Decimal("300")
        self.assertEqual(t.quote(100), Decimal("300"))
        t.pricing_mode, t.price_per_kg = Trip.Pricing.PER_KG, None
        self.assertIsNone(t.quote(10))
        self.assertIn("→", str(t))
        self.assertIn("TU", str(t.vehicle))

    def test_clean_rules(self):
        v = VehicleFactory(capacity_kg=1000, capacity_m3=5)
        t = Trip(
            carrier=v.carrier,
            vehicle=v,
            origin="Sfax",
            destination="Sfax",
            departure_date=today(1),
            available_weight_kg=2000,
            available_volume_m3=9,
            pricing_mode="per_kg",
        )
        with self.assertRaises(ValidationError) as ctx:
            t.clean()
        self.assertEqual(
            {"destination", "price_per_kg", "available_weight_kg", "available_volume_m3"},
            set(ctx.exception.message_dict),
        )
        t.pricing_mode = "fixed"
        with self.assertRaises(ValidationError) as ctx:
            t.clean()
        self.assertIn("fixed_price", ctx.exception.message_dict)


class TripFormTests(TestCase):
    def test_vehicle_queryset_limited_to_carrier(self):
        carrier = CarrierFactory()
        mine = VehicleFactory(carrier=carrier)
        other = VehicleFactory()
        form = TripForm(trip_data(other), carrier=carrier)
        self.assertFalse(form.is_valid())
        self.assertIn("vehicle", form.errors)
        self.assertTrue(TripForm(trip_data(mine), carrier=carrier).is_valid())

    def test_past_date_and_reserved_weight(self):
        v = VehicleFactory()
        form = TripForm(trip_data(v, departure_date=today(-2).isoformat()), carrier=v.carrier)
        self.assertIn("departure_date", form.errors)
        t = TripFactory(carrier=v.carrier, vehicle=v, reserved_weight_kg=2000)
        form = TripForm(trip_data(v, available_weight_kg=1000), instance=t, carrier=v.carrier)
        self.assertIn("available_weight_kg", form.errors)


class TripViewTests(TestCase):
    def setUp(self):
        self.carrier = CarrierFactory()
        self.client.force_login(self.carrier)

    def test_create_requires_vehicle_first(self):
        r = self.client.get(reverse("trips:create"))
        self.assertRedirects(r, reverse("trips:vehicle_create"))

    def test_vehicle_crud(self):
        r = self.client.post(
            reverse("trips:vehicle_create"),
            {"vehicle_type": "camion", "plate_number": "200 TU 1", "capacity_kg": 8000, "capacity_m3": 30},
        )
        self.assertRedirects(r, reverse("trips:vehicles"))
        v = Vehicle.objects.get(plate_number="200 TU 1")
        self.client.post(
            reverse("trips:vehicle_update", args=[v.pk]),
            {
                "vehicle_type": "frigo",
                "plate_number": "200 TU 1",
                "capacity_kg": 8000,
                "capacity_m3": 30,
                "refrigerated": "on",
            },
        )
        v.refresh_from_db()
        self.assertTrue(v.refrigerated)
        TripFactory(carrier=self.carrier, vehicle=v)
        self.client.post(reverse("trips:vehicle_delete", args=[v.pk]))
        self.assertTrue(Vehicle.objects.filter(pk=v.pk).exists())  # protected by its trip
        v2 = VehicleFactory(carrier=self.carrier)
        self.client.post(reverse("trips:vehicle_delete", args=[v2.pk]))
        self.assertFalse(Vehicle.objects.filter(pk=v2.pk).exists())
        r = self.client.post(
            reverse("trips:vehicle_create"),
            {"vehicle_type": "camion", "plate_number": "!!", "capacity_kg": 10, "capacity_m3": 0},
        )
        self.assertEqual(set(r.context["form"].errors), {"plate_number", "capacity_kg", "capacity_m3"})

    def test_trip_create_update_delete(self):
        v = VehicleFactory(carrier=self.carrier)
        r = self.client.post(reverse("trips:create"), trip_data(v))
        t = Trip.objects.get(carrier=self.carrier)
        self.assertRedirects(r, t.get_absolute_url())
        t.refresh_from_db()
        self.assertIsNotNone(t.fraud_score)
        self.client.post(reverse("trips:update", args=[t.pk]), trip_data(v, notes="Mise à jour"))
        t.refresh_from_db()
        self.assertEqual(t.notes, "Mise à jour")
        BookingFactory(trip=t)
        self.client.post(reverse("trips:delete", args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.status, Trip.Status.CANCELLED)
        t2 = TripFactory(carrier=self.carrier)
        self.client.post(reverse("trips:delete", args=[t2.pk]))
        self.assertFalse(Trip.objects.filter(pk=t2.pk).exists())

    def test_search(self):
        TripFactory(origin="Sfax", destination="Tunis", available_volume_m3=30, notes="retour à vide")
        TripFactory(
            origin="Gabès", destination="Sousse", available_volume_m3=2, vehicle=VehicleFactory(refrigerated=True)
        )
        url = reverse("trips:list")
        self.assertEqual(self.client.get(url, {"origin": "Gabès"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"destination": "Tunis"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"min_volume": 10}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"q": "vide"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"merchandise_type": "frais"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"date": today(20).isoformat()}).context["paginator"].count, 0)

    def test_detail_for_pme_and_owner(self):
        t = TripFactory(carrier=self.carrier)
        r = self.client.get(t.get_absolute_url())
        self.assertTrue(r.context["is_owner"])
        self.assertContains(r, "data-ai-matching")
        self.client.force_login(PMEFactory())
        r = self.client.get(t.get_absolute_url())
        self.assertContains(r, "Publier une annonce")
        self.assertEqual(len(self.client.get(reverse("trips:list")).context["trips"]), 1)

    def test_mine_lists_own_trips(self):
        TripFactory(carrier=self.carrier)
        TripFactory()
        self.assertEqual(len(self.client.get(reverse("trips:mine")).context["trips"]), 1)
        self.assertEqual(self.client.get(reverse("trips:vehicles")).status_code, 200)


class PricingTests(TestCase):
    def test_market_price_monotonic(self):
        base = pricing.market_price(300, 1000, 3, "alimentaire", 5)
        self.assertGreater(pricing.market_price(600, 1000, 3, "alimentaire", 5), base)
        self.assertGreater(pricing.market_price(300, 5000, 3, "alimentaire", 5), base)
        self.assertGreater(pricing.market_price(300, 1000, 3, "frais", 5), base)
        self.assertGreater(pricing.market_price(300, 1000, 3, "alimentaire", 0), base)

    def test_dataset_and_suggestion(self):
        df = pricing.generate_dataset(n=50, seed=1)
        self.assertEqual(len(df), 50)
        self.assertEqual(set(pricing.FEATURES) - set(df.columns), set())
        s = pricing.suggest_price("Sfax", "Tunis", 2000, 5, "alimentaire", 3)
        self.assertGreater(s["price"], 0)
        self.assertLess(s["low"], s["price"])
        self.assertGreater(s["high"], s["price"])
        far = pricing.suggest_price("Bizerte", "Tataouine", 2000, 5, "alimentaire", 3)
        self.assertGreater(far["price"], s["price"])

    def test_ai_validate_and_handle(self):
        p = ai.validate(
            {
                "origin": "sfax",
                "destination": "Tunis",
                "weight_kg": "1000",
                "merchandise_type": "x",
                "pickup_date": "2026-03-01",
                "delivery_deadline": "2026-03-20",
            },
            None,
        )
        self.assertEqual(p["merchandise_type"], "autre")
        self.assertEqual(p["urgency_days"], 10)
        self.assertEqual(p["volume_m3"], 2.5)
        self.assertEqual(ai.handle(p, None)["provider"], "local:sklearn-gbr")
        for bad in (
            {"origin": "Sfax", "destination": "Sfax", "weight_kg": 1},
            {"origin": "Sfax", "destination": "Tunis", "weight_kg": 0},
            {"origin": "Sfax", "destination": "Tunis", "weight_kg": "abc"},
        ):
            with self.assertRaises(AIInputError):
                ai.validate(bad, None)
        p = ai.validate(
            {
                "origin": "Sfax",
                "destination": "Tunis",
                "weight_kg": 5,
                "pickup_date": "bad",
                "delivery_deadline": "bad",
            },
            None,
        )
        self.assertEqual(p["urgency_days"], 3)

    def test_model_reload_from_disk(self):
        pricing._model = None
        self.assertIsNotNone(pricing.get_model())
