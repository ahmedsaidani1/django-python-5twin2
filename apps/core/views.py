import json
import logging

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from .ai.registry import ALLOWED_ROLES, AIInputError, get_module
from .mixins import RoleRequiredMixin
from .models import AIJob
from .tasks import submit_job

logger = logging.getLogger("apps.ai")

FRENCH_ERRORS = {
    "invalid": "Les données envoyées à l'assistant IA sont invalides.",
    "forbidden": "Vous n'avez pas accès à cette fonctionnalité IA.",
    "failed": "L'assistant IA n'a pas pu traiter votre demande. Réessayez ou remplissez le formulaire manuellement.",
}


class HomeView(TemplateView):
    template_name = "core/home.html"


class AIJobCreateView(RoleRequiredMixin, View):
    """POST /ai/<kind>/ → 202 {job_id, poll_url}. The work runs in Celery."""

    http_method_names = ["post"]

    def post(self, request, kind):
        if kind not in ALLOWED_ROLES:
            return JsonResponse({"error": FRENCH_ERRORS["invalid"]}, status=404)
        if request.user.effective_role not in ALLOWED_ROLES[kind]:
            return JsonResponse({"error": FRENCH_ERRORS["forbidden"]}, status=403)
        try:
            if request.content_type == "application/json":
                payload = json.loads(request.body or b"{}")
            else:
                payload = request.POST.dict()
            payload.pop("csrfmiddlewaretoken", None)
            cleaned = get_module(kind).validate(payload, request.user)
        except (json.JSONDecodeError, AIInputError) as exc:
            return JsonResponse({"error": f"{FRENCH_ERRORS['invalid']} {exc}".strip()}, status=400)
        except PermissionDenied:
            return JsonResponse({"error": FRENCH_ERRORS["forbidden"]}, status=403)
        job = AIJob.objects.create(user=request.user, kind=kind, input=cleaned)
        submit_job(job)
        return JsonResponse(
            {"job_id": job.pk, "status": job.status, "poll_url": reverse("core:ai_job", args=[job.pk])},
            status=202,
        )


class AIJobDetailView(RoleRequiredMixin, View):
    """GET /ai/jobs/<id>/ → JSON status, polled by static/js/ai-poll.js."""

    def get(self, request, pk):
        job = get_object_or_404(AIJob, pk=pk)
        if job.user_id != request.user.pk:
            return JsonResponse({"error": FRENCH_ERRORS["forbidden"]}, status=403)
        job.refresh_from_db()
        data = {"job_id": job.pk, "kind": job.kind, "status": job.status, "latency_ms": job.latency_ms}
        if job.status == AIJob.Status.SUCCESS:
            data["output"] = job.output
        elif job.status == AIJob.Status.ERROR:
            data["error"] = FRENCH_ERRORS["failed"]
        return JsonResponse(data)


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    # Rendered without the request context: context processors may hit the failing component.
    return HttpResponseServerError(loader.render_to_string("errors/500.html"))
