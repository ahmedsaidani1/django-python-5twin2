from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts import fraud
from apps.core.ai.registry import AIInputError
from apps.core.testing.factories import FreightFactory, PMEFactory, TripFactory


class FraudFeatureTests(TestCase):
    def test_text_features(self):
        f = fraud.text_features("GAGNEZ vite !!! WhatsApp 98 123 456 www.promo.com contact@x.tn")
        self.assertEqual((f["has_phone"], f["has_url"], f["has_email"]), (1, 1, 1))
        self.assertGreaterEqual(f["spam_terms"], 2)
        self.assertEqual(f["exclamations"], 3)
        clean = fraud.text_features("Palettes filmées, chargement à quai.")
        self.assertEqual(clean["spam_terms"], 0)
        self.assertEqual(fraud.text_features("")["upper_ratio"], 0.0)

    def test_features_price_and_quantity(self):
        f = fraud.features("ok", 100, 1000, 50000, 0, 10)
        self.assertLess(f["price_log_ratio"], -2)
        self.assertEqual(f["absurd_quantity"], 1)
        self.assertEqual(fraud.features("ok", None, None, 1000, 0, 10)["price_log_ratio"], 0.0)
        self.assertEqual(len(fraud.vector(f)), len(fraud.FEATURES))

    def test_model_separates_obvious_cases(self):
        spam = fraud.features(
            "GAGNEZ DE L'ARGENT FACILE !!! WhatsApp 98 123 456, paiement d'avance Western Union",
            5000,
            300,
            100,
            15,
            0,
            2,
        )
        legit = fraud.features("Palettes filmées, chargement par chariot élévateur sur place.", 310, 300, 2000, 1, 400)
        self.assertGreater(fraud.fraud_probability(spam), 0.5)
        self.assertLess(fraud.fraud_probability(legit), 0.5)

    def test_dataset_has_disjoint_splits(self):
        rows = fraud.generate_dataset(n=100, seed=1)
        self.assertEqual({r["split"] for r in rows}, {"train", "test"})
        self.assertTrue(any(r["label"] for r in rows))


class FraudScreeningTests(TestCase):
    def test_screen_spam_annonce_flags_it(self):
        pme = PMEFactory()
        spam = FreightFactory(
            pme=pme,
            title="OFFRE !!!",
            budget=5000,
            weight_kg=100,
            volume_m3=0.5,
            description="Gagnez de l'argent facile !!! Paiement d'avance Western Union, WhatsApp 98 123 456",
        )
        result = fraud.screen_object(spam)
        spam.refresh_from_db()
        self.assertTrue(result["flagged"])
        self.assertTrue(spam.is_flagged)
        self.assertIn("has_phone", result["reasons"])
        self.assertIn("spam_terms", result["reasons"])

    def test_screen_normal_annonce_and_trip_and_user(self):
        pme = PMEFactory()
        pme.date_joined = timezone.now() - timedelta(days=300)
        pme.save()
        f = FreightFactory(
            pme=pme, description="Marchandise conditionnée sur palettes, chargement à quai.", budget=None
        )
        self.assertFalse(fraud.screen_object(f)["flagged"])
        t = TripFactory()
        self.assertIn("score", fraud.screen_object(t))
        self.assertIn("score", fraud.screen_object(pme))
        with self.assertRaises(TypeError):
            fraud.object_features(object())

    def test_validate_and_handle(self):
        f = FreightFactory()
        self.assertEqual(fraud.validate({"target": "annonce", "id": f.pk}, None), {"target": "annonce", "id": f.pk})
        with self.assertRaises(AIInputError):
            fraud.validate({"target": "x", "id": 1}, None)
        with self.assertRaises(AIInputError):
            fraud.validate({"target": "annonce", "id": 999999}, None)
        with self.assertRaises(AIInputError):
            fraud.validate({"target": "annonce", "id": "abc"}, None)
        out = fraud.handle({"target": "annonce", "id": f.pk}, None)
        self.assertEqual(out["provider"], "local:random-forest")

    def test_owner_flagged_after_two_flagged_posts(self):
        pme = PMEFactory()
        text = "GAGNEZ DE L'ARGENT FACILE !!! Western Union, paiement d'avance, WhatsApp 98 123 456"
        for _ in range(2):
            f = FreightFactory(pme=pme, budget=9000, weight_kg=50, volume_m3=0.2, description=text)
            fraud.handle({"target": "annonce", "id": f.pk}, None)
        pme.refresh_from_db()
        self.assertTrue(pme.is_flagged)
