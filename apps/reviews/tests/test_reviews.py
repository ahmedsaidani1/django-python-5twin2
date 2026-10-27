from django.test import TestCase
from django.urls import reverse

from apps.bookings.models import BookingRequest
from apps.core.ai.registry import AIInputError
from apps.core.testing.factories import BookingFactory, ReviewFactory
from apps.notifications.models import Notification
from apps.reviews import ai
from apps.reviews.models import Review
from apps.reviews.services import refresh_carrier_stats, reputation_score


class ReputationTests(TestCase):
    def test_reputation_score(self):
        self.assertIsNone(reputation_score(None, [], 0))
        perfect = reputation_score(5, ["positif"] * 10, 10)
        few = reputation_score(5, ["positif"], 1)
        self.assertGreater(perfect, few)  # smoothing: one review counts less
        self.assertLess(reputation_score(1, ["negatif"] * 5, 5), 30)
        self.assertEqual(reputation_score(3, [], 3), reputation_score(3, ["neutre"] * 3, 3))

    def test_refresh_carrier_stats(self):
        r = ReviewFactory(rating=4, sentiment="positif")
        ReviewFactory(
            carrier=r.carrier,
            booking=BookingFactory(trip__carrier=r.carrier, status="livree"),
            rating=2,
            sentiment="negatif",
        )
        p = refresh_carrier_stats(r.carrier)
        self.assertEqual((p.average_rating, p.reviews_count), (3.0, 2))
        self.assertIsNotNone(p.reputation_score)
        self.assertIsNone(refresh_carrier_stats(r.author))  # PME has no carrier profile
        self.assertIn("/5", str(r))


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.booking = BookingFactory(status=BookingRequest.Status.DELIVERED)
        self.pme, self.carrier = self.booking.freight.pme, self.booking.trip.carrier
        self.url = reverse("reviews:create", args=[self.booking.pk])

    def test_pme_reviews_delivered_booking(self):
        self.client.force_login(self.pme)
        self.assertContains(self.client.get(self.url), "Noter")
        r = self.client.post(self.url, {"rating": 5, "comment": "Livraison rapide, chauffeur très professionnel."})
        self.assertRedirects(r, self.booking.get_absolute_url(), fetch_redirect_response=False)
        review = Review.objects.get()
        self.assertEqual(review.sentiment, "positif")  # sentiment job ran (eager)
        self.carrier.carrier_profile.refresh_from_db()
        self.assertEqual(self.carrier.carrier_profile.average_rating, 5)
        self.assertIsNotNone(self.carrier.carrier_profile.reputation_score)
        self.assertTrue(Notification.objects.filter(user=self.carrier, kind="review").exists())
        # second review refused
        r = self.client.post(self.url, {"rating": 1, "comment": "encore"}, follow=True)
        self.assertContains(r, "déjà laissé")
        self.assertEqual(Review.objects.count(), 1)

    def test_not_delivered_redirects_with_message(self):
        b = BookingFactory(freight__pme=self.pme, status=BookingRequest.Status.IN_PROGRESS)
        self.client.force_login(self.pme)
        r = self.client.get(reverse("reviews:create", args=[b.pk]), follow=True)
        self.assertContains(r, "une fois la livraison effectuée")

    def test_validation(self):
        self.client.force_login(self.pme)
        r = self.client.post(self.url, {"rating": 9, "comment": "abc"})
        self.assertEqual(set(r.context["form"].errors), {"rating", "comment"})

    def test_my_reviews_lists(self):
        ReviewFactory(booking=self.booking, author=self.pme, carrier=self.carrier)
        self.client.force_login(self.carrier)
        self.assertEqual(len(self.client.get(reverse("reviews:mine")).context["reviews"]), 1)
        self.client.force_login(self.pme)
        self.assertEqual(len(self.client.get(reverse("reviews:mine")).context["reviews"]), 1)


class SentimentModelTests(TestCase):
    def test_predict_classes(self):
        self.assertEqual(ai.predict("Très mauvaise expérience, marchandise abîmée et retard.")[0], "negatif")
        self.assertEqual(ai.predict("Excellent transporteur, ponctuel et soigneux, je recommande !")[0], "positif")
        label, conf = ai.predict("Livraison effectuée, rien à signaler.")
        self.assertIn(label, ai.LABELS)
        self.assertTrue(0 < conf <= 1)

    def test_validate_and_handle_text(self):
        self.assertEqual(ai.validate({"review_id": "3"}, None), {"review_id": 3})
        with self.assertRaises(AIInputError):
            ai.validate({"review_id": "x"}, None)
        with self.assertRaises(AIInputError):
            ai.validate({"text": ""}, None)
        out = ai.handle(ai.validate({"text": "Service catastrophique"}, None), None)
        self.assertEqual(out["label"], "negatif")

    def test_training_set_generation(self):
        rows = ai.generate_training_set(n_per_class=10, seed=1)
        self.assertEqual({label for _, label in rows}, set(ai.LABELS))
        self.assertGreater(len(ai.load_test_set()), 50)
