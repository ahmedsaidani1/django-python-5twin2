from datetime import date
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.core.ai.llm_client import LLMClient, LLMError
from apps.core.ai.registry import AIInputError
from apps.core.models import AIJob
from apps.core.testing.factories import BookingFactory, CarrierFactory, FreightFactory, PMEFactory, TripFactory, today
from apps.shipments import ai
from apps.shipments.forms import FreightRequestForm
from apps.shipments.models import FreightRequest

VALID = {
    "title": "Palettes de dattes",
    "merchandise_type": "agricole",
    "description": "",
    "weight_kg": 2000,
    "volume_m3": 5,
    "origin": "Tozeur",
    "destination": "Tunis",
    "constraints": "",
    "budget": 600,
}


def form_data(**over):
    return {**VALID, "pickup_date": today(2).isoformat(), "delivery_deadline": today(4).isoformat(), **over}


class FreightModelAndFormTests(TestCase):
    def test_clean_rules(self):
        f = FreightFactory.build(pickup_date=today(5), delivery_deadline=today(2), destination="Sfax")
        with self.assertRaises(ValidationError) as ctx:
            f.clean()
        self.assertIn("delivery_deadline", ctx.exception.message_dict)
        self.assertIn("destination", ctx.exception.message_dict)
        self.assertIn("→", str(FreightFactory()))

    def test_form_valid_and_invalid(self):
        self.assertTrue(FreightRequestForm(form_data()).is_valid())
        form = FreightRequestForm(form_data(weight_kg=0, volume_m3=-1, pickup_date=today(-1).isoformat()))
        self.assertFalse(form.is_valid())
        self.assertEqual({"weight_kg", "volume_m3", "pickup_date"} - set(form.errors), set())

    def test_html5_attributes(self):
        html = str(FreightRequestForm())
        self.assertIn('type="date"', html)
        self.assertIn('min="1"', html)
        self.assertIn("required", html)

    def test_queryset_helpers(self):
        FreightFactory(is_active=False)
        FreightFactory(status=FreightRequest.Status.CLOSED)
        open_one = FreightFactory()
        self.assertEqual(list(FreightRequest.objects.open()), [open_one])


class FreightViewTests(TestCase):
    def setUp(self):
        self.pme = PMEFactory()
        self.client.force_login(self.pme)

    def test_create_triggers_fraud_screening(self):
        r = self.client.post(reverse("shipments:create"), form_data())
        f = FreightRequest.objects.get(title="Palettes de dattes")
        self.assertRedirects(r, f.get_absolute_url())
        self.assertEqual(f.pme, self.pme)
        self.assertTrue(AIJob.objects.filter(kind="fraud", input__id=f.pk).exists())
        f.refresh_from_db()
        self.assertIsNotNone(f.fraud_score)

    def test_create_prefill_from_query(self):
        r = self.client.get(reverse("shipments:create") + "?origin=Sfax&weight_kg=300&evil=1")
        self.assertEqual(r.context["form"].initial, {"origin": "Sfax", "weight_kg": "300"})

    def test_create_invalid_rerenders_with_errors(self):
        r = self.client.post(reverse("shipments:create"), form_data(delivery_deadline=today(1).isoformat()))
        self.assertEqual(r.status_code, 200)
        self.assertIn("delivery_deadline", r.context["form"].errors)

    def test_update_and_lock_when_assigned(self):
        f = FreightFactory(pme=self.pme)
        r = self.client.post(reverse("shipments:update", args=[f.pk]), form_data(title="Modifiée"))
        self.assertEqual(r.status_code, 302)
        f.refresh_from_db()
        self.assertEqual(f.title, "Modifiée")
        f.status = FreightRequest.Status.ASSIGNED
        f.save()
        r = self.client.post(reverse("shipments:update", args=[f.pk]), form_data(title="Interdit"))
        self.assertEqual(r.status_code, 200)

    def test_delete(self):
        f = FreightFactory(pme=self.pme)
        BookingFactory(freight=f, status="acceptee")
        self.client.post(reverse("shipments:delete", args=[f.pk]))
        self.assertTrue(FreightRequest.objects.filter(pk=f.pk).exists())
        f2 = FreightFactory(pme=self.pme)
        self.assertRedirects(self.client.post(reverse("shipments:delete", args=[f2.pk])), reverse("shipments:mine"))
        self.assertFalse(FreightRequest.objects.filter(pk=f2.pk).exists())

    def test_search_filters_and_pagination(self):
        FreightFactory(origin="Sfax", destination="Tunis", title="Tomates", merchandise_type="agricole", volume_m3=10)
        FreightFactory(origin="Gabès", destination="Sousse", title="Ciment", merchandise_type="materiaux", volume_m3=2)
        url = reverse("shipments:list")
        self.assertEqual(self.client.get(url, {"origin": "Sfax"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"destination": "Sousse"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"q": "toma"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"min_volume": 5}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"merchandise_type": "materiaux"}).context["paginator"].count, 1)
        self.assertEqual(self.client.get(url, {"date": today(30).isoformat()}).context["paginator"].count, 0)
        for _ in range(10):
            FreightFactory()
        r = self.client.get(url, {"page": 2})
        self.assertEqual(r.context["page_obj"].number, 2)
        self.assertEqual(r.context["querystring"], "")

    def test_detail_context_for_carrier(self):
        f = FreightFactory()
        carrier = CarrierFactory()
        TripFactory(carrier=carrier)
        self.client.force_login(carrier)
        r = self.client.get(f.get_absolute_url())
        self.assertFalse(r.context["is_owner"])
        self.assertEqual(len(r.context["my_trips"]), 1)
        self.assertContains(r, "Envoyer une offre")

    def test_detail_for_owner_shows_matching_panel(self):
        f = FreightFactory(pme=self.pme)
        r = self.client.get(f.get_absolute_url())
        self.assertTrue(r.context["is_owner"])
        self.assertContains(r, "data-ai-matching")

    def test_mine(self):
        FreightFactory(pme=self.pme)
        FreightFactory()
        self.assertEqual(len(self.client.get(reverse("shipments:mine")).context["freights"]), 1)

    def test_xss_is_escaped(self):
        f = FreightFactory(title="<script>alert(1)</script>")
        r = self.client.get(f.get_absolute_url())
        self.assertNotContains(r, "<script>alert(1)</script>")
        self.assertContains(r, "&lt;script&gt;")


class SmartAnnonceTests(TestCase):
    REF = date(2026, 3, 2)  # a Monday

    def test_parser_example_from_spec(self):
        out = ai.parse_freight_text("20 palettes de tomates de Sfax à Tunis mardi", self.REF)
        self.assertEqual((out["origin"], out["destination"]), ("Sfax", "Tunis"))
        self.assertEqual(out["merchandise_type"], "agricole")
        self.assertEqual(out["weight_kg"], 10000)
        self.assertEqual(out["volume_m3"], 30)
        self.assertEqual(out["pickup_date"], "2026-03-03")
        self.assertEqual(out["delivery_deadline"], "2026-03-05")

    def test_parser_variants(self):
        out = ai.parse_freight_text(
            "Je dois livrer 3 tonnes de ciment à Mahdia depuis Sousse le 10/03, livraison avant le 12/03, budget 900 DT",
            self.REF,
        )
        self.assertEqual((out["origin"], out["destination"]), ("Sousse", "Mahdia"))
        self.assertEqual((out["pickup_date"], out["delivery_deadline"]), ("2026-03-10", "2026-03-12"))
        self.assertEqual(out["budget"], 900)
        self.assertEqual(out["volume_m3"], 2.5)  # estimated from density
        out = ai.parse_freight_text("Yaourts frigo Béja → Sfax demain, 500 kg, sous 3 jours", self.REF)
        self.assertEqual(out["merchandise_type"], "frais")
        self.assertIn("réfrigéré", out["constraints"])
        self.assertEqual(out["delivery_deadline"], "2026-03-06")
        out = ai.parse_freight_text("colis Tunis Sfax aujourd'hui 12 mars 1er avril", self.REF)
        self.assertEqual(out["pickup_date"], "2026-03-02")
        self.assertEqual(ai.parse_freight_text("envoi après-demain", self.REF)["pickup_date"], "2026-03-04")
        self.assertEqual(ai.parse_freight_text("envoi le 5 mars", self.REF)["pickup_date"], "2026-03-05")
        self.assertEqual(ai.parse_freight_text("envoi le 1/1", self.REF)["pickup_date"], "2027-01-01")
        self.assertEqual(ai.parse_freight_text("envoi la semaine prochaine", self.REF)["pickup_date"], "2026-03-09")
        self.assertIsNone(ai.parse_freight_text("rien ici", self.REF)["origin"])

    def test_normalize_fields(self):
        raw = {
            "origin": "sfax",
            "destination": "Paris",
            "merchandise_type": "x",
            "weight_kg": "-3",
            "volume_m3": "abc",
            "pickup_date": "2020-01-01",
            "delivery_deadline": "pas une date",
            "budget": "250",
        }
        out = ai.normalize_fields(raw, "texte", self.REF)
        self.assertEqual(out["origin"], "Sfax")
        self.assertIsNone(out["destination"])
        self.assertEqual(out["merchandise_type"], "autre")
        self.assertIsNone(out["weight_kg"])
        self.assertIsNone(out["volume_m3"])
        self.assertEqual(out["pickup_date"], "2026-03-02")
        self.assertIsNone(out["delivery_deadline"])
        self.assertEqual(out["budget"], 250)

    def test_validate(self):
        with self.assertRaises(AIInputError):
            ai.validate({"text": "court"}, None)
        with self.assertRaises(AIInputError):
            ai.validate({"text": "x" * 1001}, None)

    def test_llm_path_mocked(self):
        client = LLMClient(provider="openai", api_key="k")
        with mock.patch.object(
            LLMClient, "complete_json", return_value={"origin": "Tunis", "destination": "Sousse", "weight_kg": 100}
        ):
            fields, provider = ai.extract("texte quelconque", self.REF, client)
        self.assertEqual(provider, "openai:")
        self.assertEqual(fields["origin"], "Tunis")

    def test_llm_failure_falls_back_to_rules(self):
        client = LLMClient(provider="openai", api_key="k")
        with mock.patch.object(LLMClient, "complete_json", side_effect=LLMError("down")):
            fields, provider = ai.extract("2 tonnes de blé de Béja à Bizerte", self.REF, client)
        self.assertEqual(provider, "local-fallback")
        self.assertEqual(fields["origin"], "Béja")

    def test_evaluate_command_accuracy(self):
        from pathlib import Path

        from django.conf import settings

        from apps.shipments.management.commands.evaluate_smart_annonce import evaluate, field_correct

        examples, per_field, errors, exact, latency = evaluate(Path(settings.AI_DATA_DIR) / "smart_annonce_50.jsonl")
        self.assertEqual(len(examples), 50)
        ok = sum(v[0] for v in per_field.values())
        total = sum(v[1] for v in per_field.values())
        self.assertGreater(ok / total, 0.9)
        self.assertTrue(field_correct("weight_kg", 1000, 1040))
        self.assertFalse(field_correct("weight_kg", 1000, None))
        self.assertTrue(field_correct("budget", None, None))
