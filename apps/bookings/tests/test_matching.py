import random
from datetime import date

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.bookings import ai, matching
from apps.bookings.management.commands.evaluate_matching import annotate, build_dataset, to_features
from apps.core.ai.registry import AIInputError
from apps.core.testing.factories import CarrierFactory, FreightFactory, PMEFactory, TripFactory, VehicleFactory

F = matching.FreightFeatures(
    origin="Sfax",
    destination="Tunis",
    pickup_date=date(2026, 3, 3),
    delivery_deadline=date(2026, 3, 5),
    weight_kg=1000,
    volume_m3=4,
    budget=300,
)


def trip(**kw):
    base = dict(
        origin="Sfax",
        destination="Tunis",
        departure_date=date(2026, 3, 4),
        remaining_weight_kg=2000,
        remaining_volume_m3=10,
        price_per_kg=0.2,
        rating=4.5,
    )
    base.update(kw)
    return matching.TripFeatures(**base)


class ScoreTests(TestCase):
    def test_perfect_match_scores_high(self):
        s = matching.score(F, trip())
        self.assertTrue(s["compatible"])
        self.assertGreater(s["score"], 0.85)
        self.assertEqual(s["parts"]["route"], 1.0)

    def test_route_date_price_capacity_components(self):
        self.assertLess(matching.route_score(F, trip(origin="Gabès", destination="Bizerte")), 0.3)
        self.assertGreater(matching.route_score(F, trip(origin="Sfax", destination="Ariana")), 0.8)
        self.assertEqual(matching.date_score(F, trip(departure_date=date(2026, 3, 20))), 0)
        self.assertAlmostEqual(matching.date_score(F, trip(departure_date=date(2026, 3, 1))), 0.5)
        self.assertEqual(matching.price_score(F, trip(price_per_kg=0.6), None), 0)
        self.assertEqual(matching.price_score(F, trip(price_per_kg=None, fixed_price=None), None), 0.5)
        self.assertEqual(matching.price_score(F, trip(fixed_price=200, price_per_kg=None), None), 1.0)
        self.assertEqual(matching.capacity_score(F, trip(remaining_weight_kg=500)), 0)
        self.assertEqual(matching.rating_score(trip(rating=None)), 0.5)
        self.assertEqual(matching.rating_score(trip(reputation=80)), 0.8)

    def test_hard_constraints(self):
        cold = matching.FreightFeatures(**{**F.__dict__, "merchandise_type": "frais"})
        self.assertFalse(matching.score(cold, trip(refrigerated=False))["compatible"])
        self.assertTrue(matching.score(cold, trip(refrigerated=True))["compatible"])
        self.assertFalse(matching.score(F, trip(remaining_weight_kg=10))["compatible"])

    def test_ranking_order(self):
        good, near, bad = (
            trip(id=1),
            trip(id=2, destination="Ariana"),
            trip(id=3, origin="Gabès", remaining_weight_kg=1),
        )
        ranked = matching.rank(F, [bad, near, good])
        self.assertEqual([t.id for t, _ in ranked], [1, 2, 3])
        ranked_f = matching.rank_freights(good, [F])
        self.assertEqual(len(ranked_f), 1)

    def test_metrics(self):
        self.assertEqual(matching.precision_at_k([3, 2, 0, 0, 1], 5), 0.4)
        self.assertEqual(matching.ndcg_at_k([3, 2, 1]), 1.0)
        self.assertLess(matching.ndcg_at_k([0, 1, 3]), 1.0)
        self.assertEqual(matching.ndcg_at_k([0, 0]), 0.0)

    def test_annotation_rubric_and_dataset(self):
        rng = random.Random(0)
        rng.random = lambda: 0.99  # disable simulated noise
        f = {
            "origin": "Sfax",
            "destination": "Tunis",
            "pickup_date": "2026-03-03",
            "delivery_deadline": "2026-03-05",
            "weight_kg": 1000,
            "volume_m3": 4,
            "merchandise_type": "alimentaire",
            "budget": 300,
        }
        t = {
            "origin": "Sfax",
            "destination": "Tunis",
            "departure_date": "2026-03-04",
            "remaining_weight_kg": 2000,
            "remaining_volume_m3": 10,
            "refrigerated": False,
            "fixed_price": 250,
            "price_per_kg": None,
            "rating": 4,
        }
        self.assertEqual(annotate(f, t, rng), 3)
        self.assertEqual(annotate(f, {**t, "remaining_weight_kg": 10}, rng), 0)
        data = build_dataset(n_queries=2, n_candidates=3)
        self.assertEqual(len(data["queries"]), 2)
        ff, tf = to_features(data["queries"][0]["freight"], data["queries"][0]["candidates"][0])
        self.assertIn("relevance", tf.extra)


class MatchingJobTests(TestCase):
    def test_freight_to_trips(self):
        pme = PMEFactory()
        f = FreightFactory(pme=pme)
        good = TripFactory(origin=f.origin, destination=f.destination, departure_date=f.pickup_date)
        TripFactory(origin="Gabès", destination="Bizerte", departure_date=f.pickup_date)
        self.assertEqual(ai.validate({"freight_id": f.pk}, pme), {"freight_id": f.pk})
        out = ai.handle({"freight_id": f.pk}, pme)
        self.assertEqual(out["results"][0]["id"], good.pk)
        self.assertIn("action_url", out["results"][0])

    def test_trip_to_freights(self):
        carrier = CarrierFactory()
        t = TripFactory(carrier=carrier, vehicle=VehicleFactory(carrier=carrier))
        f = FreightFactory(origin=t.origin, destination=t.destination, pickup_date=t.departure_date)
        self.assertEqual(ai.validate({"trip_id": t.pk}, carrier), {"trip_id": t.pk})
        out = ai.handle({"trip_id": t.pk}, carrier)
        self.assertEqual(out["results"][0]["id"], f.pk)

    def test_validate_errors(self):
        pme = PMEFactory()
        with self.assertRaises(AIInputError):
            ai.validate({}, pme)
        with self.assertRaises(AIInputError):
            ai.validate({"freight_id": 999999}, pme)
        with self.assertRaises(PermissionDenied):
            ai.validate({"freight_id": FreightFactory().pk}, pme)
        with self.assertRaises(PermissionDenied):
            ai.validate({"trip_id": TripFactory().pk}, pme)

    def test_reference_price_when_no_budget(self):
        f = FreightFactory(budget=None)
        self.assertGreater(ai._reference_price(f), 0)
        self.assertIsNone(ai._reference_price(FreightFactory()))
