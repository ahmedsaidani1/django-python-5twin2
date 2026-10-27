import numpy as np
from django.core.management.base import BaseCommand
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split

from apps.core.ai.evaluation import LatencyTimer, md_table, write_report
from apps.trips import pricing


class Command(BaseCommand):
    help = "Entraîne et évalue le modèle de suggestion de prix (MAE, RMSE, R²)."

    def add_arguments(self, parser):
        parser.add_argument("--rebuild", action="store_true", help="Régénère le jeu de données synthétique.")

    def handle(self, *args, **options):
        df = pricing.load_dataset(rebuild=options["rebuild"])
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=7)
        model = pricing.train(train_df, save=False)
        y_true = test_df["price_tnd"].to_numpy()
        y_pred = model.predict(test_df[pricing.FEATURES])
        mae = mean_absolute_error(y_true, y_pred)
        rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        r2 = r2_score(y_true, y_pred)
        mape = float(np.mean(np.abs(y_pred - y_true) / y_true))

        # Baseline: a single average price per km·tonne, to show what the model adds.
        rate = (train_df["price_tnd"] / (train_df["distance_km"] * train_df["weight_kg"] / 1000 + 1)).median()
        base_pred = rate * (test_df["distance_km"] * test_df["weight_kg"] / 1000 + 1)
        base_mae = mean_absolute_error(y_true, base_pred)
        base_r2 = r2_score(y_true, base_pred)

        timer = LatencyTimer()
        for row in test_df.head(200).itertuples():
            timer.time(model.predict, test_df.loc[[row.Index], pricing.FEATURES])

        pricing.train(df)  # production model: refit on the full dataset and save it
        sections = [
            (
                "Protocole",
                f"""
- Données : `data/ai/price_synth.csv`, **{len(df)} trajets synthétiques** entre {df["origin"].nunique()} villes
  tunisiennes (distance routière estimée = haversine × 1,25), poids 50 kg – 24 t, 9 types de marchandise,
  urgence 0–10 jours. Le prix « marché » suit une formule cachée (coût fixe + distance × charge taxable,
  multiplicateur par type, prime d'urgence) avec un bruit log-normal de 8 %.
- Variables du modèle : distance, poids, volume, type de marchandise, urgence.
- Modèle : `GradientBoostingRegressor` (400 arbres, profondeur 4) dans un pipeline scikit-learn
  (one-hot du type, log du poids/volume), cible apprise en log(prix).
- Découpage : 80 % entraînement / 20 % test ({len(test_df)} trajets), `random_state` fixé.
""",
            ),
            (
                "Résultats (jeu de test)",
                md_table(
                    ["modèle", "MAE (TND)", "RMSE (TND)", "R²", "MAPE"],
                    [
                        ["Gradient Boosting", round(mae, 2), round(rmse, 2), round(r2, 4), f"{mape:.1%}"],
                        ["Référence : tarif médian / t·km", round(base_mae, 2), "—", round(base_r2, 4), "—"],
                    ],
                ),
            ),
            (
                "Interprétation",
                f"""
Le prix moyen du jeu de test est de {y_true.mean():.0f} TND : une MAE de {mae:.0f} TND correspond à une erreur
relative moyenne de {mape:.1%}, proche du bruit irréductible de 8 % injecté dans les données. L'intervalle affiché à
l'utilisateur (±12 %) couvre donc la majorité des cas. Le modèle est sauvegardé dans
`data/ai/models/price.joblib` et ré-entraîné automatiquement s'il est absent.
""",
            ),
        ]
        out = write_report("price", "IA 2 — Suggestion de prix (régression)", sections, timer.summary())
        self.stdout.write(self.style.SUCCESS(f"MAE={mae:.2f} RMSE={rmse:.2f} R2={r2:.4f} — rapport : {out}"))
