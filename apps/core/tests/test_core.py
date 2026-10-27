from pathlib import Path
from unittest import mock

import numpy as np
from django.core.exceptions import PermissionDenied
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core import geo
from apps.core.ai import evaluation
from apps.core.mixins import OwnerRequiredMixin, resolve_attr
from apps.core.testing.factories import FreightFactory, PMEFactory
from apps.core.views import error_403, error_404, error_500


class GeoTests(TestCase):
    def test_canonical_and_aliases(self):
        self.assertEqual(geo.canonical_city("gabes"), "Gabès")
        self.assertEqual(geo.canonical_city("  KEF "), "Le Kef")
        self.assertIsNone(geo.canonical_city("Paris"))
        self.assertEqual(geo.governorate("Hammamet"), "Nabeul")
        self.assertIsNone(geo.governorate("Paris"))

    def test_distance(self):
        d = geo.distance_km("Sfax", "Tunis")
        self.assertTrue(250 < d < 340, d)
        self.assertEqual(geo.distance_km("Sfax", "Sfax"), 0)
        self.assertEqual(geo.distance_km("Sfax", "Lyon"), 0)


class HomeAndErrorsTests(TestCase):
    def test_landing_page_content(self):
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, "Connecter • Optimiser • Avancer ensemble")
        self.assertContains(r, "Des trajets à vide")
        self.assertContains(r, 'class="skip-link"')
        self.assertContains(r, "<main", count=1)
        self.assertContains(r, 'lang="fr"')

    def test_error_handlers(self):
        rf = RequestFactory()
        req = rf.get("/")
        req.user = PMEFactory()
        self.assertEqual(error_403(req).status_code, 403)
        self.assertEqual(error_404(req).status_code, 404)
        r = error_500(req)
        self.assertEqual(r.status_code, 500)
        self.assertIn("Erreur serveur", r.content.decode())

    def test_404_template(self):
        r = self.client.get("/page-qui-n-existe-pas/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Page introuvable", status_code=404)

    def test_security_headers_and_csrf(self):
        r = self.client.get(reverse("accounts:login"))
        self.assertContains(r, "csrfmiddlewaretoken")
        self.assertEqual(r["X-Frame-Options"], "DENY")


class MixinTests(TestCase):
    def test_resolve_attr(self):
        f = FreightFactory()
        self.assertEqual(resolve_attr(f, "pme.username"), f.pme.username)

    def test_owner_mixin_custom_fields(self):
        f = FreightFactory()

        class Base:
            def get_object(self, queryset=None):
                return f

        class View(OwnerRequiredMixin, Base):
            owner_fields = ("pme",)

        v = View()
        v.request = mock.Mock(user=f.pme)
        self.assertEqual(v.get_object(), f)
        v.request = mock.Mock(user=PMEFactory())
        with self.assertRaises(PermissionDenied):
            v.get_object()


class TemplateTagTests(TestCase):
    def render(self, tpl, **ctx):
        return Template("{% load cargolink %}" + tpl).render(Context(ctx))

    def test_tnd_filter(self):
        self.assertEqual(self.render("{{ v|tnd }}", v=1234.5), "1 234,50 TND")
        self.assertEqual(self.render("{{ v|tnd }}", v=None), "—")

    def test_stars(self):
        out = self.render("{% stars 4 %}")
        self.assertEqual(out.count("bi-star-fill"), 4)
        self.assertIn('aria-label="Note : 4,0 sur 5"', out)

    def test_nav_current(self):
        req = RequestFactory().get("/annonces/12/")
        self.assertIn("aria-current", self.render("{% nav_current '/annonces/' %}", request=req))
        self.assertEqual(self.render("{% nav_current '/trajets/' '/' %}", request=req), "")


class EvaluationHelpersTests(TestCase):
    def test_latency_and_reports(self):
        timer = evaluation.LatencyTimer()
        self.assertEqual(timer.summary()["n"], 0)
        self.assertEqual(timer.time(lambda x: x + 1, 1), 2)
        self.assertEqual(timer.summary()["n"], 1)
        self.assertIn("| a | b |", evaluation.md_table(["a", "b"], [[1, 2.0]]))
        cm = np.array([[3, 1], [0, 4]])
        self.assertIn("réel", evaluation.cm_markdown(cm, ["x", "y"]))

    def test_write_report_and_png(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(evaluation, "DOCS_AI_DIR", Path(tmp)):
                png = evaluation.confusion_matrix_png(np.array([[1, 0], [0, 1]]), ["a", "b"], "cm.png", "t")
                md = evaluation.write_report(
                    "demo", "Titre", [("Section", "corps")], {"n": 1, "mean_ms": 1.0, "p95_ms": 2.0}
                )
                self.assertTrue(png.exists())
                self.assertIn("# Titre", md.read_text(encoding="utf-8"))


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class SeedDemoTests(TestCase):
    def test_seed_demo_creates_every_status(self):
        from django.core.management import call_command

        from apps.accounts.models import User
        from apps.bookings.models import BookingRequest

        call_command("seed_demo", stdout=mock.MagicMock())
        self.assertEqual(User.objects.filter(role="pme", username__startswith="pme_").count(), 3)
        self.assertEqual(User.objects.filter(role="transporteur").count(), 3)
        self.assertTrue(User.objects.get(username="admin").is_superuser)
        statuses = set(BookingRequest.objects.values_list("status", flat=True))
        self.assertEqual(statuses, set(BookingRequest.Status.values))
        call_command("seed_demo", stdout=mock.MagicMock())  # idempotent
        self.assertEqual(User.objects.filter(username="admin").count(), 1)
