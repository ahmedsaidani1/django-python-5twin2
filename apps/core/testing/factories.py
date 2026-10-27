"""factory_boy factories shared by every app's tests."""

from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from apps.accounts.models import CarrierProfile, CompanyProfile, Report, User
from apps.bookings.models import BookingRequest
from apps.messaging.models import Message
from apps.notifications.models import Notification
from apps.reviews.models import Review
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip, Vehicle


def today(days=0):
    return timezone.localdate() + timedelta(days=days)


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@test.tn")
    role = User.Role.PME
    password = factory.PostGenerationMethodCall("set_password", "Passw0rd!x")

    @factory.post_generation
    def _save(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class PMEFactory(UserFactory):
    role = User.Role.PME
    company_profile = factory.RelatedFactory(
        "apps.core.testing.factories.CompanyProfileFactory", factory_related_name="user"
    )


class CarrierFactory(UserFactory):
    role = User.Role.TRANSPORTEUR
    carrier_profile = factory.RelatedFactory(
        "apps.core.testing.factories.CarrierProfileFactory", factory_related_name="user"
    )


class AdminFactory(UserFactory):
    role = User.Role.ADMIN
    is_staff = True


class CompanyProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CompanyProfile

    user = factory.SubFactory(UserFactory)
    company_name = factory.Sequence(lambda n: f"PME {n}")
    city = "Sfax"


class CarrierProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CarrierProfile

    user = factory.SubFactory(UserFactory, role=User.Role.TRANSPORTEUR)
    company_name = factory.Sequence(lambda n: f"Transport {n}")
    city = "Sousse"


class VehicleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Vehicle

    carrier = factory.SubFactory(CarrierFactory)
    vehicle_type = Vehicle.Type.TRUCK
    plate_number = factory.Sequence(lambda n: f"{100 + n} TU {1000 + n}")
    capacity_kg = 10000
    capacity_m3 = 40
    refrigerated = False


class TripFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Trip

    carrier = factory.SubFactory(CarrierFactory)
    vehicle = factory.LazyAttribute(lambda o: VehicleFactory(carrier=o.carrier))
    origin = "Sfax"
    destination = "Tunis"
    departure_date = factory.LazyFunction(lambda: today(3))
    available_weight_kg = 5000
    available_volume_m3 = 20
    pricing_mode = Trip.Pricing.PER_KG
    price_per_kg = Decimal("0.050")


class FreightFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FreightRequest

    pme = factory.SubFactory(PMEFactory)
    title = factory.Sequence(lambda n: f"Annonce {n}")
    merchandise_type = "alimentaire"
    weight_kg = 1000
    volume_m3 = 4
    origin = "Sfax"
    destination = "Tunis"
    pickup_date = factory.LazyFunction(lambda: today(2))
    delivery_deadline = factory.LazyFunction(lambda: today(5))
    budget = Decimal("300")


class BookingFactory(factory.django.DjangoModelFactory):
    """PME → carrier request by default (sender = PME of the freight)."""

    class Meta:
        model = BookingRequest

    freight = factory.SubFactory(FreightFactory)
    trip = factory.SubFactory(TripFactory)
    sender = factory.LazyAttribute(lambda o: o.freight.pme)
    receiver = factory.LazyAttribute(lambda o: o.trip.carrier)
    proposed_price = Decimal("250")
    message = "Bonjour"


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    booking = factory.SubFactory(BookingFactory)
    sender = factory.LazyAttribute(lambda o: o.booking.sender)
    body = "Message de test"


class ReviewFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Review

    booking = factory.SubFactory(BookingFactory, status=BookingRequest.Status.DELIVERED)
    author = factory.LazyAttribute(lambda o: o.booking.freight.pme)
    carrier = factory.LazyAttribute(lambda o: o.booking.trip.carrier)
    rating = 5
    comment = "Livraison rapide et soignée, je recommande."


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(PMEFactory)
    kind = Notification.Kind.STATUS
    message = "Notification de test"
    url = "/tableau-de-bord/"


class ReportFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Report

    reporter = factory.SubFactory(PMEFactory)
    target = factory.SubFactory(FreightFactory)
    reason = Report.Reason.SPAM
