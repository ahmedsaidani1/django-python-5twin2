"""Permission matrix over EVERY view: anonymous, wrong role, not owner, owner.

A direct URL access (bypassing the UI) must give a login redirect (anonymous) or a 403
(authenticated without the right). Rows are (url_name, method, allowed roles, object kind, owner kind).
"""

from django.test import TestCase
from django.urls import reverse

from apps.bookings.models import BookingRequest
from apps.core.testing.factories import (
    AdminFactory,
    BookingFactory,
    CarrierFactory,
    FreightFactory,
    NotificationFactory,
    PMEFactory,
    ReportFactory,
    TripFactory,
    VehicleFactory,
)

PME, CARRIER, ADMIN = "pme", "transporteur", "admin"
ALL = (PME, CARRIER, ADMIN)


class PermissionMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pme = PMEFactory()
        cls.carrier = CarrierFactory()
        cls.admin = AdminFactory()
        cls.other_pme = PMEFactory()
        cls.other_carrier = CarrierFactory()
        cls.freight = FreightFactory(pme=cls.pme)
        cls.trip = TripFactory(carrier=cls.carrier)
        cls.vehicle = VehicleFactory(carrier=cls.carrier)
        cls.booking = BookingFactory(freight=cls.freight, trip=cls.trip)
        cls.delivered = BookingFactory(
            freight=FreightFactory(pme=cls.pme),
            trip=TripFactory(carrier=cls.carrier),
            status=BookingRequest.Status.DELIVERED,
        )
        cls.notif = NotificationFactory(user=cls.pme)
        cls.report = ReportFactory(reporter=cls.other_pme, target=cls.freight)
        cls.users = {PME: cls.pme, CARRIER: cls.carrier, ADMIN: cls.admin}

    def as_user(self, user):
        self.client.force_login(user)

    # (name, kwargs, method, allowed_roles, owner_role, non_owner)
    def rows(self):
        f, t, v, b = self.freight.pk, self.trip.pk, self.vehicle.pk, self.booking.pk
        return [
            # public pages
            ("core:home", {}, "get", None, None, None),
            ("accounts:login", {}, "get", None, None, None),
            ("accounts:signup", {}, "get", None, None, None),
            # any authenticated user
            ("shipments:list", {}, "get", ALL, None, None),
            ("shipments:detail", {"pk": f}, "get", ALL, None, None),
            ("trips:list", {}, "get", ALL, None, None),
            ("trips:detail", {"pk": t}, "get", ALL, None, None),
            ("accounts:carrier", {"pk": self.carrier.pk}, "get", ALL, None, None),
            ("notifications:list", {}, "get", ALL, None, None),
            ("dashboard:home", {}, "get", ALL, None, None),
            # PME only
            ("shipments:mine", {}, "get", (PME,), None, None),
            ("shipments:create", {}, "get", (PME,), None, None),
            ("shipments:update", {"pk": f}, "get", (PME,), PME, self.other_pme),
            ("shipments:delete", {"pk": f}, "get", (PME,), PME, self.other_pme),
            ("bookings:create_from_trip", {"trip_pk": t}, "get", (PME,), None, None),
            ("reviews:create", {"booking_pk": self.delivered.pk}, "get", (PME,), PME, self.other_pme),
            ("dashboard:pme", {}, "get", (PME,), None, None),
            # Transporteur only
            ("trips:mine", {}, "get", (CARRIER,), None, None),
            ("trips:create", {}, "get", (CARRIER,), None, None),
            ("trips:update", {"pk": t}, "get", (CARRIER,), CARRIER, self.other_carrier),
            ("trips:delete", {"pk": t}, "get", (CARRIER,), CARRIER, self.other_carrier),
            ("trips:vehicles", {}, "get", (CARRIER,), None, None),
            ("trips:vehicle_create", {}, "get", (CARRIER,), None, None),
            ("trips:vehicle_update", {"pk": v}, "get", (CARRIER,), CARRIER, self.other_carrier),
            ("trips:vehicle_delete", {"pk": v}, "get", (CARRIER,), CARRIER, self.other_carrier),
            ("bookings:create_from_freight", {"freight_pk": f}, "get", (CARRIER,), None, None),
            ("dashboard:carrier", {}, "get", (CARRIER,), None, None),
            # Both parties (PME + carrier), object-level for the booking
            ("accounts:profile", {}, "get", (PME, CARRIER), None, None),
            ("bookings:list", {}, "get", (PME, CARRIER), None, None),
            ("bookings:detail", {"pk": b}, "get", (PME, CARRIER), PME, self.other_pme),
            ("messaging:inbox", {}, "get", (PME, CARRIER), None, None),
            ("reviews:mine", {}, "get", (PME, CARRIER), None, None),
            # Admin only
            ("dashboard:admin", {}, "get", (ADMIN,), None, None),
            ("accounts:moderation", {}, "get", (ADMIN,), None, None),
        ]

    def test_matrix(self):
        login = reverse("accounts:login")
        for name, kwargs, method, roles, _owner_role, non_owner in self.rows():
            url = reverse(name, kwargs=kwargs)
            with self.subTest(view=name, who="anonymous"):
                self.client.logout()
                r = getattr(self.client, method)(url)
                if roles is None:
                    self.assertEqual(r.status_code, 200)
                else:
                    self.assertEqual(r.status_code, 302)
                    self.assertTrue(r["Location"].startswith(login))
            if roles is None:
                continue
            for role, user in self.users.items():
                with self.subTest(view=name, who=role):
                    self.as_user(user)
                    r = getattr(self.client, method)(url)
                    if role in roles:
                        self.assertIn(r.status_code, (200, 302), f"{name} as {role}")
                    else:
                        self.assertEqual(r.status_code, 403, f"{name} as wrong role {role}")
            if non_owner is not None:
                with self.subTest(view=name, who="not owner"):
                    self.as_user(non_owner)
                    r = getattr(self.client, method)(url)
                    self.assertEqual(r.status_code, 403, f"{name} as non-owner")

    def test_post_only_views_permissions(self):
        """POST endpoints: anonymous → login, wrong role / non participant → 403."""
        b = self.booking
        cases = [
            (reverse("bookings:transition", args=[b.pk, "accepter"]), (PME, CARRIER), self.other_pme),
            (reverse("messaging:send", args=[b.pk]), (PME, CARRIER), self.other_carrier),
            (reverse("notifications:open", args=[self.notif.pk]), ALL, self.carrier),
            (reverse("accounts:moderation_action", args=["signalement", self.report.pk, "traiter"]), (ADMIN,), None),
        ]
        for url, roles, outsider in cases:
            self.client.logout()
            r = self.client.post(url, {"body": "x"})
            self.assertEqual(r.status_code, 302)
            self.assertIn(reverse("accounts:login"), r["Location"])
            for role, user in self.users.items():
                if role not in roles:
                    self.as_user(user)
                    self.assertEqual(self.client.post(url, {"body": "x"}).status_code, 403, url)
            if outsider is not None:
                self.as_user(outsider)
                self.assertEqual(self.client.post(url, {"body": "x"}).status_code, 403, url)

    def test_get_on_post_only_view_not_allowed(self):
        self.as_user(self.pme)
        r = self.client.get(reverse("bookings:transition", args=[self.booking.pk, "annuler"]))
        self.assertEqual(r.status_code, 405)

    def test_hidden_annonce_is_404_for_others_but_visible_to_owner(self):
        hidden = FreightFactory(pme=self.pme, is_active=False)
        self.as_user(self.carrier)
        self.assertEqual(self.client.get(reverse("shipments:detail", args=[hidden.pk])).status_code, 404)
        self.as_user(self.pme)
        self.assertEqual(self.client.get(reverse("shipments:detail", args=[hidden.pk])).status_code, 200)
        self.as_user(self.admin)
        self.assertEqual(self.client.get(reverse("shipments:detail", args=[hidden.pk])).status_code, 200)

    def test_django_admin_requires_staff(self):
        self.as_user(self.pme)
        r = self.client.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.as_user(self.admin)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
