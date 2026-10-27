from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Entraîne et sauvegarde les modèles IA locaux (prix, sentiment, fraude) dans data/ai/models/."

    def handle(self, *args, **options):
        from apps.accounts import fraud
        from apps.reviews import ai as sentiment
        from apps.trips import pricing

        pricing.train()
        self.stdout.write("✓ modèle de prix")
        sentiment.train()
        self.stdout.write("✓ modèle de sentiment")
        fraud.train()
        self.stdout.write("✓ modèle de fraude")
        self.stdout.write(self.style.SUCCESS("Modèles entraînés."))
