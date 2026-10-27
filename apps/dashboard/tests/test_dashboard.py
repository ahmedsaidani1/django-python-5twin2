from django.test import TestCase
from django.urls import reverse

from apps.core.models import AIJob
from apps.core.testing.factories import (
    AdminFactory,
    BookingFactory,
    CarrierFactory,
    FreightFactory,
    PMEFactory,
    ReportFactory,
    TripFactory,
)


class DashboardTests(TestCase):
    def test_home_redirects_per_role(self):
        for factory, target in (
            (PMEFactory, "dashboard:pme"),
            (CarrierFactory, "dashboard:carrier"),
            (AdminFactory, "dashboard:admin"),
        ):
            self.client.force_login(factory())
            self.assertRedirects(self.client.get(reverse("dashboard:home")), reverse(target))

    def test_pme_dashboard_context(self):
        pme = PMEFactory()
        f = FreightFactory(pme=pme)
        BookingFactory(freight=f, status="livree", proposed_price=300)
        BookingFactory(freight=FreightFactory(pme=pme))
        self.client.force_login(pme)
        r = self.client.get(reverse("dashboard:pme"))
        self.assertEqual(r.context["stats"]["annonces"], 2)
        self.assertEqual(r.context["stats"]["livrees"], 1)
        self.assertEqual(r.context["stats"]["depense"], 300)
        self.assertEqual(len(r.context["to_review"]), 1)
        self.assertEqual(len(r.context["sent"]), 2)
        counts = {v: n for v, _, n in r.context["status_counts"]}
        self.assertEqual(counts["livree"], 1)
        self.assertEqual(counts["en_attente"], 1)

    def test_carrier_dashboard_context(self):
        carrier = CarrierFactory()
        t = TripFactory(carrier=carrier)
        BookingFactory(trip=t)
        self.client.force_login(carrier)
        r = self.client.get(reverse("dashboard:carrier"))
        self.assertEqual(r.context["stats"]["trajets"], 1)
        self.assertEqual(len(r.context["received"]), 1)
        self.assertEqual(r.context["profile"], carrier.carrier_profile)

    def test_admin_dashboard_stats(self):
        BookingFactory()
        ReportFactory()
        FreightFactory(is_flagged=True)
        AIJob.objects.create(kind="price", status="success", latency_ms=12)
        self.client.force_login(AdminFactory())
        r = self.client.get(reverse("dashboard:admin"))
        s = r.context["stats"]
        self.assertGreaterEqual(s["pme"], 1)
        self.assertEqual(s["signalements"], 1)
        self.assertEqual(s["drapeaux"], 1)
        self.assertEqual(list(r.context["ai_stats"])[0]["kind"], "price")
