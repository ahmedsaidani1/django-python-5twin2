from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.bookings import services
from apps.bookings.models import BookingRequest, BookingStatusHistory
from apps.core.testing.factories import CarrierFactory, FreightFactory, PMEFactory, TripFactory, today
from apps.notifications.models import Notification
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

S = BookingRequest.Status


class StatusMachineTests(TestCase):
    def setUp(self):
        self.pme = PMEFactory()
        self.carrier = CarrierFactory()
        self.freight = FreightFactory(pme=self.pme, weight_kg=1000, volume_m3=4)
        self.trip = TripFactory(carrier=self.carrier, available_weight_kg=5000, available_volume_m3=20)

    def new(self, sender=None):
        return services.create_booking(
            freight=self.freight, trip=self.trip, sender=sender or self.pme, message="m", proposed_price=Decimal("100")
        )

    def test_create_records_history_and_notifies_receiver(self):
        b = self.new()
        self.assertEqual(b.receiver, self.carrier)
        self.assertEqual(b.status, S.PENDING)
        self.assertEqual(b.history.count(), 1)
        self.assertTrue(Notification.objects.filter(user=self.carrier, kind="new_request").exists())
        offer = services.create_booking(
            freight=FreightFactory(pme=self.pme),
            trip=self.trip,
            sender=self.carrier,
            message="",
            proposed_price=Decimal("50"),
        )
        self.assertEqual(offer.receiver, self.pme)
        self.assertEqual(offer.pme, self.pme)
        self.assertEqual(offer.carrier, self.carrier)

    def test_full_happy_path(self):
        b = self.new()
        services.transition(b, S.ACCEPTED, self.carrier)
        self.trip.refresh_from_db()
        self.freight.refresh_from_db()
        self.assertEqual(self.trip.reserved_weight_kg, 1000)
        self.assertEqual(self.freight.status, FreightRequest.Status.ASSIGNED)
        services.transition(b, S.IN_PROGRESS, self.carrier)
        services.transition(b, S.DELIVERED, self.carrier)
        b.refresh_from_db()
        self.freight.refresh_from_db()
        self.assertEqual(b.status, S.DELIVERED)
        self.assertEqual(self.freight.status, FreightRequest.Status.CLOSED)
        self.assertEqual(
            list(b.history.values_list("to_status", flat=True)), [S.PENDING, S.ACCEPTED, S.IN_PROGRESS, S.DELIVERED]
        )
        self.assertEqual(Notification.objects.filter(user=self.pme, kind="status").count(), 3)

    def test_every_invalid_transition_is_rejected(self):
        allowed = set(services.TRANSITIONS)
        for from_status in S.values:
            for to_status in S.values:
                if (from_status, to_status) in allowed:
                    continue
                b = BookingRequest.objects.create(
                    freight=FreightFactory(pme=self.pme),
                    trip=self.trip,
                    sender=self.pme,
                    receiver=self.carrier,
                    status=from_status,
                    proposed_price=10,
                )
                for user in (self.pme, self.carrier):
                    with self.subTest(frm=from_status, to=to_status, user=user.role):
                        self.assertFalse(services.can_transition(b, to_status, user))
                        with self.assertRaises(services.InvalidTransition):
                            services.transition(b, to_status, user)

    def test_only_right_party(self):
        b = self.new()
        outsider = PMEFactory()
        self.assertFalse(services.can_transition(b, S.ACCEPTED, self.pme))  # sender cannot accept
        self.assertTrue(services.can_transition(b, S.ACCEPTED, self.carrier))
        self.assertFalse(services.can_transition(b, S.CANCELLED, self.carrier))  # receiver cannot cancel pending
        self.assertTrue(services.can_transition(b, S.CANCELLED, self.pme))
        self.assertFalse(services.can_transition(b, S.REFUSED, outsider))
        services.transition(b, S.ACCEPTED, self.carrier)
        b.refresh_from_db()
        self.assertFalse(services.can_transition(b, S.IN_PROGRESS, self.pme))  # only carrier starts
        self.assertTrue(services.can_transition(b, S.CANCELLED, self.carrier))  # either party cancels accepted
        self.assertEqual([a for a, _ in services.available_actions(b, self.carrier)], ["annuler", "demarrer"])

    def test_refuse_and_cancel(self):
        b = self.new()
        services.transition(b, S.REFUSED, self.carrier, "trop loin")
        self.assertEqual(BookingStatusHistory.objects.filter(booking=b).last().note, "trop loin")
        b2 = services.create_booking(
            freight=FreightFactory(pme=self.pme), trip=self.trip, sender=self.pme, message="", proposed_price=1
        )
        services.transition(b2, S.CANCELLED, self.pme)
        b2.refresh_from_db()
        self.assertEqual(b2.status, S.CANCELLED)

    def test_cancel_after_accept_releases_capacity(self):
        b = self.new()
        services.transition(b, S.ACCEPTED, self.carrier)
        services.transition(b, S.CANCELLED, self.pme)
        self.trip.refresh_from_db()
        self.freight.refresh_from_db()
        self.assertEqual(self.trip.reserved_weight_kg, 0)
        self.assertEqual(self.freight.status, FreightRequest.Status.OPEN)

    def test_capacity_exceeded_blocks_accept(self):
        self.trip.reserved_weight_kg = 4500
        self.trip.save()
        b = self.new()
        with self.assertRaises(services.InvalidTransition):
            services.transition(b, S.ACCEPTED, self.carrier)

    def test_trip_becomes_full(self):
        trip = TripFactory(carrier=self.carrier, available_weight_kg=1000, available_volume_m3=4)
        b = services.create_booking(freight=self.freight, trip=trip, sender=self.pme, message="", proposed_price=1)
        services.transition(b, S.ACCEPTED, self.carrier)
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.Status.FULL)
        services.transition(b, S.CANCELLED, self.carrier)
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.Status.OPEN)

    def test_accept_auto_refuses_other_pending_offers(self):
        other_carrier = CarrierFactory()
        other = services.create_booking(
            freight=self.freight,
            trip=TripFactory(carrier=other_carrier),
            sender=other_carrier,
            message="",
            proposed_price=1,
        )
        b = self.new()
        services.transition(b, S.ACCEPTED, self.carrier)
        other.refresh_from_db()
        self.assertEqual(other.status, S.REFUSED)
        self.assertTrue(Notification.objects.filter(user=other_carrier, message__contains="autre offre").exists())

    def test_cannot_accept_already_assigned_freight(self):
        b = self.new()
        self.freight.status = FreightRequest.Status.ASSIGNED
        self.freight.save()
        with self.assertRaises(services.InvalidTransition):
            services.transition(b, S.ACCEPTED, self.carrier)


class BookingViewTests(TestCase):
    def setUp(self):
        self.pme = PMEFactory()
        self.carrier = CarrierFactory()
        self.freight = FreightFactory(pme=self.pme)
        self.trip = TripFactory(carrier=self.carrier)

    def test_pme_sends_request_from_trip(self):
        self.client.force_login(self.pme)
        url = reverse("bookings:create_from_trip", args=[self.trip.pk])
        r = self.client.get(url + f"?freight={self.freight.pk}")
        self.assertEqual(r.context["form"].initial["freight"], str(self.freight.pk))
        r = self.client.post(url, {"freight": self.freight.pk, "proposed_price": "250", "message": "Bonjour"})
        b = BookingRequest.objects.get()
        self.assertRedirects(r, b.get_absolute_url())
        self.assertEqual((b.sender, b.receiver), (self.pme, self.carrier))

    def test_carrier_sends_offer_from_freight(self):
        self.client.force_login(self.carrier)
        url = reverse("bookings:create_from_freight", args=[self.freight.pk])
        self.assertEqual(self.client.get(url + f"?trip={self.trip.pk}").status_code, 200)
        r = self.client.post(url, {"trip": self.trip.pk, "proposed_price": "250", "message": ""})
        b = BookingRequest.objects.get()
        self.assertRedirects(r, b.get_absolute_url())
        self.assertEqual(b.receiver, self.pme)

    def test_cannot_use_someone_elses_freight(self):
        self.client.force_login(PMEFactory())
        r = self.client.post(
            reverse("bookings:create_from_trip", args=[self.trip.pk]),
            {"freight": self.freight.pk, "proposed_price": "250"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("freight", r.context["form"].errors)

    def test_business_rules_in_form(self):
        self.client.force_login(self.pme)
        url = reverse("bookings:create_from_trip", args=[self.trip.pk])
        big = FreightFactory(pme=self.pme, weight_kg=99999)
        r = self.client.post(url, {"freight": big.pk, "proposed_price": "250"})
        self.assertIn("Capacité insuffisante", str(r.context["form"].non_field_errors()))
        # dates are not a blocking rule: a trip leaving after the deadline can still be requested
        late = FreightFactory(pme=self.pme, pickup_date=today(0), delivery_deadline=today(1))  # trip leaves at today+3
        r = self.client.post(url, {"freight": late.pk, "proposed_price": "250"})
        self.assertEqual(r.status_code, 302)
        self.client.post(url, {"freight": self.freight.pk, "proposed_price": "250"})
        r = self.client.post(url, {"freight": self.freight.pk, "proposed_price": "250"})
        self.assertIn("déjà en cours", str(r.context["form"].non_field_errors()))
        self.trip.status = Trip.Status.FULL
        self.trip.save()
        r = self.client.post(url, {"freight": FreightFactory(pme=self.pme).pk, "proposed_price": "0"})
        self.assertIn("proposed_price", r.context["form"].errors)
        self.assertIn("plus ouvert", str(r.context["form"].non_field_errors()))

    def test_transition_view_and_detail(self):
        b = services.create_booking(freight=self.freight, trip=self.trip, sender=self.pme, message="", proposed_price=1)
        self.client.force_login(self.carrier)
        r = self.client.get(b.get_absolute_url())
        self.assertEqual([a for a, _ in r.context["actions"]], ["accepter", "refuser"])
        self.assertContains(r, 'class="modal fade"')
        self.assertEqual(r.context["other_party"], self.pme)
        r = self.client.post(reverse("bookings:transition", args=[b.pk, "accepter"]))
        self.assertRedirects(r, b.get_absolute_url())
        b.refresh_from_db()
        self.assertEqual(b.status, S.ACCEPTED)
        # invalid transition via direct URL → error message, status unchanged
        r = self.client.post(reverse("bookings:transition", args=[b.pk, "livrer"]), follow=True)
        self.assertContains(r, "non autorisée")
        b.refresh_from_db()
        self.assertEqual(b.status, S.ACCEPTED)
        self.assertEqual(self.client.post(reverse("bookings:transition", args=[b.pk, "voler"])).status_code, 404)

    def test_list_filters(self):
        b = services.create_booking(freight=self.freight, trip=self.trip, sender=self.pme, message="", proposed_price=1)
        self.client.force_login(self.pme)
        url = reverse("bookings:list")
        self.assertEqual(list(self.client.get(url, {"box": "sent"}).context["bookings"]), [b])
        self.assertEqual(list(self.client.get(url, {"box": "received"}).context["bookings"]), [])
        self.assertEqual(list(self.client.get(url, {"status": "livree"}).context["bookings"]), [])
        self.assertEqual(list(self.client.get(url).context["bookings"]), [b])
        self.assertIn("#", str(b))
