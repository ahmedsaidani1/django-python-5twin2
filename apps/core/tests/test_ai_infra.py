import json
from unittest import mock

import httpx
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core import tasks
from apps.core.ai.llm_client import LLMClient, LLMError, parse_json_object
from apps.core.models import AIJob
from apps.core.testing.factories import AdminFactory, CarrierFactory, FreightFactory, PMEFactory


def fake_response(status=200, payload=None):
    return httpx.Response(status, json=payload or {}, request=httpx.Request("POST", "https://x/v1/chat/completions"))


class LLMClientTests(TestCase):
    def client_(self, **kw):
        return LLMClient(
            provider=kw.get("provider", "openai"),
            api_key="k",
            base_url="https://x/v1",
            model="m",
            timeout=1,
            max_retries=kw.get("retries", 2),
        )

    def test_local_when_no_key(self):
        c = LLMClient(provider="openai", api_key="")
        self.assertFalse(c.is_remote)
        self.assertEqual(c.name, "local")
        with self.assertRaises(LLMError):
            c.complete_json("s", "u")

    def test_from_settings(self):
        with override_settings(AI_PROVIDER="anthropic", AI_API_KEY="abc", AI_BASE_URL="https://api/v1/"):
            c = LLMClient.from_settings()
        self.assertTrue(c.is_remote)
        self.assertEqual(c.base_url, "https://api/v1")

    @mock.patch("apps.core.ai.llm_client.httpx.post")
    def test_openai_success(self, post):
        post.return_value = fake_response(payload={"choices": [{"message": {"content": '{"a": 1}'}}]})
        self.assertEqual(self.client_().complete_json("s", "u"), {"a": 1})
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["response_format"], {"type": "json_object"})

    @mock.patch("apps.core.ai.llm_client.httpx.post")
    def test_anthropic_success(self, post):
        post.return_value = fake_response(payload={"content": [{"type": "text", "text": 'Voici {"b": 2}'}]})
        self.assertEqual(self.client_(provider="anthropic").complete_json("s", "u"), {"b": 2})
        self.assertIn("x-api-key", post.call_args.kwargs["headers"])

    @mock.patch("apps.core.ai.llm_client.time.sleep")
    @mock.patch("apps.core.ai.llm_client.httpx.post")
    def test_retries_then_fails(self, post, sleep):
        post.side_effect = httpx.ConnectError("boom")
        with self.assertRaises(LLMError):
            self.client_(retries=2).complete_json("s", "u")
        self.assertEqual(post.call_count, 3)

    @mock.patch("apps.core.ai.llm_client.time.sleep")
    @mock.patch("apps.core.ai.llm_client.httpx.post")
    def test_retry_on_503_then_success(self, post, sleep):
        post.side_effect = [fake_response(503), fake_response(payload={"choices": [{"message": {"content": "{}"}}]})]
        self.assertEqual(self.client_().complete_json("s", "u"), {})

    @mock.patch("apps.core.ai.llm_client.httpx.post")
    def test_no_retry_on_401(self, post):
        post.return_value = fake_response(401)
        with self.assertRaises(LLMError):
            self.client_().complete_json("s", "u")
        self.assertEqual(post.call_count, 1)

    @mock.patch("apps.core.ai.llm_client.httpx.post")
    def test_unexpected_shape(self, post):
        post.return_value = fake_response(payload={"weird": True})
        with self.assertRaises(LLMError):
            self.client_(retries=0).complete_json("s", "u")

    def test_parse_json_object(self):
        self.assertEqual(parse_json_object('blah {"x": [1]} fin'), {"x": [1]})
        with self.assertRaises(LLMError):
            parse_json_object("pas de json")
        with self.assertRaises(LLMError):
            parse_json_object("{invalide}")


class AIEndpointTests(TestCase):
    def setUp(self):
        self.pme = PMEFactory()
        self.client.force_login(self.pme)

    def post(self, kind, payload, user=None):
        if user:
            self.client.force_login(user)
        return self.client.post(
            reverse("core:ai_create", args=[kind]), json.dumps(payload), content_type="application/json"
        )

    def test_smart_annonce_job_lifecycle(self):
        r = self.post("smart_annonce", {"text": "20 palettes de tomates de Sfax à Tunis mardi"})
        self.assertEqual(r.status_code, 202)
        data = r.json()
        job = AIJob.objects.get(pk=data["job_id"])
        self.assertEqual(job.user, self.pme)
        self.assertEqual(job.status, AIJob.Status.SUCCESS)  # eager in tests
        self.assertIsNotNone(job.latency_ms)
        poll = self.client.get(data["poll_url"]).json()
        self.assertEqual(poll["status"], "success")
        self.assertEqual(poll["output"]["fields"]["origin"], "Sfax")
        self.assertEqual(poll["output"]["fields"]["destination"], "Tunis")

    def test_form_encoded_payload(self):
        r = self.client.post(
            reverse("core:ai_create", args=["smart_annonce"]), {"text": "3 tonnes de ciment de Gabès vers Sousse"}
        )
        self.assertEqual(r.status_code, 202)

    def test_invalid_input_is_400_in_french(self):
        r = self.post("smart_annonce", {"text": "court"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalides", r.json()["error"])
        r = self.client.post(reverse("core:ai_create", args=["smart_annonce"]), "{bad", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_unknown_kind_404(self):
        self.assertEqual(self.post("inconnu", {}).status_code, 404)

    def test_wrong_role_403(self):
        self.assertEqual(self.post("smart_annonce", {"text": "x" * 20}, user=CarrierFactory()).status_code, 403)
        self.assertEqual(self.post("fraud", {"target": "annonce", "id": 1}).status_code, 403)

    def test_matching_not_owner_403(self):
        other = FreightFactory()
        self.assertEqual(self.post("matching", {"freight_id": other.pk}).status_code, 403)

    def test_poll_other_users_job_403(self):
        job = AIJob.objects.create(user=PMEFactory(), kind="price")
        r = self.client.get(reverse("core:ai_job", args=[job.pk]))
        self.assertEqual(r.status_code, 403)

    def test_poll_anonymous_redirects(self):
        job = AIJob.objects.create(user=self.pme, kind="price")
        self.client.logout()
        self.assertEqual(self.client.get(reverse("core:ai_job", args=[job.pk])).status_code, 302)

    def test_failed_job_shows_french_error(self):
        with mock.patch("apps.shipments.ai.extract", side_effect=RuntimeError("panne")):
            r = self.post("smart_annonce", {"text": "20 palettes de tomates de Sfax à Tunis"})
        job = AIJob.objects.get(pk=r.json()["job_id"])
        self.assertEqual(job.status, AIJob.Status.ERROR)
        self.assertIn("panne", job.error)
        poll = self.client.get(r.json()["poll_url"]).json()
        self.assertEqual(poll["status"], "error")
        self.assertIn("n'a pas pu traiter", poll["error"])
        self.assertNotIn("panne", poll["error"])  # internal details are not leaked

    def test_pending_job_poll(self):
        job = AIJob.objects.create(user=self.pme, kind="price")
        poll = self.client.get(reverse("core:ai_job", args=[job.pk])).json()
        self.assertEqual(poll["status"], "pending")
        self.assertNotIn("output", poll)

    def test_admin_fraud_endpoint(self):
        f = FreightFactory()
        r = self.post("fraud", {"target": "annonce", "id": f.pk}, user=AdminFactory())
        self.assertEqual(r.status_code, 202)
        f.refresh_from_db()
        self.assertIsNotNone(f.fraud_score)


class SubmitJobTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_BROKER_URL="redis://127.0.0.1:1/0")
    def test_falls_back_to_thread_when_broker_down(self):
        tasks._broker_state.update(ok=None, checked=0)
        job = AIJob.objects.create(user=PMEFactory(), kind="smart_annonce", input={"text": "x"})
        with mock.patch("apps.core.tasks.threading.Thread") as thread:
            tasks.submit_job(job)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False, CELERY_BROKER_URL="memory://")
    def test_uses_celery_when_broker_ok(self):
        tasks._broker_state.update(ok=None, checked=0)
        job = AIJob.objects.create(user=PMEFactory(), kind="smart_annonce", input={"text": "x"})
        with mock.patch.object(tasks.run_ai_job, "apply_async") as apply_async:
            tasks.submit_job(job)
        apply_async.assert_called_once_with(args=[job.pk], retry=False)

    def test_run_in_thread_executes(self):
        job = AIJob.objects.create(
            user=PMEFactory(), kind="smart_annonce", input={"text": "2 tonnes de blé de Béja à Bizerte"}
        )
        # Called on the test thread: don't let the cleanup close the test transaction's connection.
        with mock.patch("apps.core.tasks.close_old_connections") as close:
            tasks._run_in_thread(job.pk)
        close.assert_called_once()
        job.refresh_from_db()
        self.assertEqual(job.status, AIJob.Status.SUCCESS)
        self.assertEqual(str(job), f"Annonce intelligente #{job.pk} (success)")
        self.assertTrue(job.is_finished)
