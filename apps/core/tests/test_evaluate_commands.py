"""Run every evaluate_<feature> command end to end (reports written to a temporary folder)."""

import io
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.core.ai import evaluation


class EvaluateCommandsTests(SimpleTestCase):
    def test_all_evaluate_commands_write_reports(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(evaluation, "DOCS_AI_DIR", Path(tmp)):
            for feature in ("smart_annonce", "price", "matching", "sentiment", "fraud"):
                out = io.StringIO()
                call_command(f"evaluate_{feature}", stdout=out)
                report = Path(tmp) / f"{feature}.md"
                self.assertTrue(report.exists(), feature)
                text = report.read_text(encoding="utf-8")
                self.assertIn("## Latence", text)
                self.assertIn("p95", text)
            self.assertTrue((Path(tmp) / "sentiment_confusion.png").exists())
            self.assertTrue((Path(tmp) / "fraud_confusion.png").exists())

    def test_train_ai_models(self):
        out = io.StringIO()
        call_command("train_ai_models", stdout=out)
        self.assertIn("Modèles entraînés", out.getvalue())
