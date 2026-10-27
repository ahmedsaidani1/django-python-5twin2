from django.db.models import Avg, Count

from apps.accounts.models import CarrierProfile

from .models import Review

SENTIMENT_VALUE = {Review.Sentiment.POSITIVE: 1.0, Review.Sentiment.NEUTRAL: 0.5, Review.Sentiment.NEGATIVE: 0.0}


def reputation_score(average_rating: float | None, sentiments: list[str], count: int) -> float | None:
    """0–100 reputation: 60% star average + 40% AI sentiment of the comments,
    shrunk towards a neutral 50 when there are few reviews (Bayesian smoothing, k=3)."""
    if not count or average_rating is None:
        return None
    stars = (average_rating - 1) / 4
    scored = [SENTIMENT_VALUE[s] for s in sentiments if s in SENTIMENT_VALUE]
    sentiment = sum(scored) / len(scored) if scored else stars
    raw = 100 * (0.6 * stars + 0.4 * sentiment)
    k = 3
    return round((count * raw + k * 50) / (count + k), 1)


def refresh_carrier_stats(carrier) -> CarrierProfile | None:
    profile = CarrierProfile.objects.filter(user=carrier).first()
    if profile is None:
        return None
    reviews = Review.objects.filter(carrier=carrier)
    agg = reviews.aggregate(avg=Avg("rating"), n=Count("id"))
    profile.average_rating = round(agg["avg"], 2) if agg["avg"] is not None else None
    profile.reviews_count = agg["n"]
    profile.reputation_score = reputation_score(
        agg["avg"], list(reviews.exclude(sentiment="").values_list("sentiment", flat=True)), agg["n"]
    )
    profile.save(update_fields=["average_rating", "reviews_count", "reputation_score"])
    return profile
