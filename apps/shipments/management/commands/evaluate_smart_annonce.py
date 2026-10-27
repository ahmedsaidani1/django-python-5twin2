import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.ai.evaluation import LatencyTimer, md_table, write_report
from apps.shipments.ai import EVALUATED_FIELDS, normalize_fields, parse_freight_text

NUMERIC_TOLERANCE = 0.05  # ±5 % on weight, volume and budget


def field_correct(field: str, expected, predicted) -> bool:
    if expected is None:
        return predicted is None
    if predicted is None:
        return False
    if field in ("weight_kg", "volume_m3", "budget"):
        return abs(float(predicted) - float(expected)) <= NUMERIC_TOLERANCE * abs(float(expected))
    return str(predicted) == str(expected)


def evaluate(path: Path):
    timer = LatencyTimer()
    per_field = defaultdict(lambda: [0, 0])
    errors = []
    examples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    exact = 0
    for ex in examples:
        today = date.fromisoformat(ex["today"])
        pred = timer.time(lambda t=ex["text"], d=today: normalize_fields(parse_freight_text(t, d), t, d))
        all_ok = True
        for field, expected in ex["expected"].items():
            ok = field_correct(field, expected, pred.get(field))
            per_field[field][0] += ok
            per_field[field][1] += 1
            if not ok:
                all_ok = False
                errors.append((ex["id"], field, expected, pred.get(field)))
        exact += all_ok
    return examples, per_field, errors, exact, timer.summary()


class Command(BaseCommand):
    help = "Évalue l'extraction « annonce intelligente » (précision par champ) sur data/ai/smart_annonce_50.jsonl."

    def handle(self, *args, **options):
        path = Path(settings.AI_DATA_DIR) / "smart_annonce_50.jsonl"
        examples, per_field, errors, exact, latency = evaluate(path)
        total_ok = sum(v[0] for v in per_field.values())
        total = sum(v[1] for v in per_field.values())
        rows = [
            [f, per_field[f][0], per_field[f][1], per_field[f][0] / per_field[f][1]]
            for f in EVALUATED_FIELDS
            if per_field[f][1]
        ]
        rows.append(["**micro-moyenne**", total_ok, total, total_ok / total])
        error_rows = [[i, f, e, p] for i, f, e, p in errors[:40]]
        sections = [
            (
                "Protocole",
                f"""
- Jeu de test : `data/ai/smart_annonce_50.jsonl`, **{len(examples)} textes libres annotés à la main**
  (une date de référence par exemple pour résoudre « mardi », « demain »…).
- Modèle évalué : l'extracteur local (règles françaises + référentiel des villes), utilisé en démo
  et en secours quand le LLM n'est pas configuré ou échoue. Avec `AI_API_KEY`, le même post-traitement
  (`normalize_fields`) s'applique à la sortie du LLM.
- Métrique : **précision par champ** = champs corrects / champs annotés. Nombres justes à ±{NUMERIC_TOLERANCE:.0%},
  dates et villes exactes, `null` attendu ⇒ la prédiction doit être vide.
- Convention d'annotation : 1 palette ≈ 500 kg / 1,5 m³, 1 carton ≈ 15 kg / 0,06 m³, 1 sac ≈ 50 kg,
  sans date limite ⇒ enlèvement + 2 jours, sans date d'enlèvement ⇒ lendemain.
""",
            ),
            (
                "Résultats",
                md_table(["champ", "corrects", "annotés", "précision"], rows)
                + f"\n\nExemples entièrement corrects : **{exact}/{len(examples)}** ({exact / len(examples):.0%}).",
            ),
            (
                "Erreurs observées",
                md_table(["exemple", "champ", "attendu", "prédit"], error_rows) if error_rows else "Aucune erreur.",
            ),
            (
                "Analyse",
                """
Les erreurs restantes viennent de cas que des règles traitent mal : nombres avec séparateur de milliers
(« 2 000 kg »), villes hors référentiel (« La Marsa »), produits ambigus (« huile d'olive » classée agricole,
« lait UHT » classé frais). Ce sont précisément les cas où un LLM apporte un gain ; c'est pourquoi le client
IA essaie d'abord le fournisseur configuré, puis bascule sur ces règles.
""",
            ),
        ]
        out = write_report("smart_annonce", "IA 1 — Annonce intelligente (extraction de champs)", sections, latency)
        self.stdout.write(
            self.style.SUCCESS(f"Précision par champ : {total_ok}/{total} = {total_ok / total:.1%} — rapport : {out}")
        )
