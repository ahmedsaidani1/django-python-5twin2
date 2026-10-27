/* CargoLink front-end helpers (vanilla JS): toasts, AI job polling, form pre-fill. */
(function () {
  "use strict";

  // ---- Toasts: show Django messages rendered in the aria-live region ----
  document.querySelectorAll(".toast").forEach(function (el) {
    if (window.bootstrap) new bootstrap.Toast(el, { delay: 6000 }).show();
  });

  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    var input = document.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  var GENERIC_ERROR = "L'assistant IA est indisponible pour le moment. Réessayez ou remplissez le formulaire manuellement.";

  /**
   * Start an AI job and poll /ai/jobs/<id>/ until it finishes.
   * panel: element with [data-ai-status] (aria-live) and receives aria-busy.
   */
  function runAIJob(kind, payload, panel, onSuccess) {
    var status = panel.querySelector("[data-ai-status]");
    var button = panel.querySelector("[data-ai-trigger]");
    panel.setAttribute("aria-busy", "true");
    if (button) button.disabled = true;
    status.classList.remove("ai-result-error");
    status.textContent = "Analyse en cours…";

    function finish(message, isError) {
      panel.setAttribute("aria-busy", "false");
      if (button) button.disabled = false;
      status.textContent = message;
      status.classList.toggle("ai-result-error", !!isError);
    }

    fetch("/ai/" + kind + "/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      credentials: "same-origin",
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.data.error || GENERIC_ERROR);
        var started = Date.now();
        (function poll() {
          fetch(res.data.poll_url, { credentials: "same-origin" })
            .then(function (r) { return r.json(); })
            .then(function (job) {
              if (job.status === "success") {
                finish("Terminé en " + (job.latency_ms || 0) + " ms.", false);
                onSuccess(job.output);
              } else if (job.status === "error") {
                finish(job.error || GENERIC_ERROR, true);
              } else if (Date.now() - started > 30000) {
                finish("L'analyse prend trop de temps. Réessayez dans un instant.", true);
              } else {
                setTimeout(poll, 800);
              }
            })
            .catch(function () { finish(GENERIC_ERROR, true); });
        })();
      })
      .catch(function (err) { finish(err.message || GENERIC_ERROR, true); });
  }
  window.CargoLinkAI = { run: runAIJob };

  function formValues(form, names) {
    var out = {};
    names.forEach(function (n) {
      var el = form.querySelector("[name=" + n + "]");
      if (el) out[n] = el.value;
    });
    return out;
  }

  // ---- Smart annonce: fill the FreightRequest form ----
  var smart = document.getElementById("ai-smart-annonce");
  if (smart) {
    smart.querySelector("[data-ai-trigger]").addEventListener("click", function () {
      var text = smart.querySelector("textarea").value;
      runAIJob("smart_annonce", { text: text }, smart, function (out) {
        var filled = 0;
        Object.keys(out.fields || {}).forEach(function (name) {
          var value = out.fields[name];
          var el = document.getElementById("id_" + name);
          if (el && value !== null && value !== "") { el.value = value; filled++; }
        });
        smart.querySelector("[data-ai-status]").textContent =
          filled + " champ(s) pré-rempli(s) (" + out.provider + "). Vérifiez avant de publier.";
        var first = document.getElementById("id_title");
        if (first) first.focus();
      });
    });
  }

  // ---- Price suggestion (freight budget or trip price) ----
  document.querySelectorAll("[data-ai-price]").forEach(function (panel) {
    panel.querySelector("[data-ai-trigger]").addEventListener("click", function () {
      var form = panel.closest("form") || document.querySelector("form.needs-price");
      var payload = formValues(form, ["origin", "destination", "weight_kg", "volume_m3", "merchandise_type",
        "pickup_date", "delivery_deadline", "available_weight_kg", "available_volume_m3"]);
      if (!payload.weight_kg) payload.weight_kg = payload.available_weight_kg;
      if (!payload.volume_m3) payload.volume_m3 = payload.available_volume_m3;
      runAIJob("price", payload, panel, function (out) {
        panel.querySelector("[data-ai-status]").textContent =
          "Prix conseillé : " + out.price + " TND (fourchette " + out.low + " – " + out.high + " TND, " +
          out.distance_km + " km).";
        var target = document.getElementById(panel.getAttribute("data-ai-price"));
        if (target && !target.value) target.value = target.id === "id_price_per_kg" ? out.per_kg : out.price;
      });
    });
  });

  // ---- Smart matching ----
  document.querySelectorAll("[data-ai-matching]").forEach(function (panel) {
    panel.querySelector("[data-ai-trigger]").addEventListener("click", function () {
      var payload = JSON.parse(panel.getAttribute("data-ai-matching"));
      var list = panel.querySelector("[data-ai-results]");
      list.innerHTML = "";
      runAIJob("matching", payload, panel, function (out) {
        if (!out.results.length) {
          panel.querySelector("[data-ai-status]").textContent = "Aucun résultat compatible pour le moment.";
          return;
        }
        panel.querySelector("[data-ai-status]").textContent = out.results.length + " résultat(s) classé(s) par compatibilité.";
        out.results.forEach(function (r) {
          var li = document.createElement("li");
          li.className = "list-group-item";
          var pct = Math.round(r.score * 100);
          var top = document.createElement("div");
          top.className = "d-flex justify-content-between align-items-center gap-2 flex-wrap";
          var a = document.createElement("a");
          a.href = r.url; a.textContent = r.label; a.className = "fw-semibold";
          var badge = document.createElement("span");
          badge.className = "badge " + (r.compatible ? "bg-primary" : "bg-secondary");
          badge.textContent = pct + " % compatible";
          top.appendChild(a); top.appendChild(badge);
          var sub = document.createElement("div");
          sub.className = "small text-muted"; sub.textContent = r.subtitle;
          var bar = document.createElement("div");
          bar.className = "score-bar mt-1"; bar.setAttribute("role", "img");
          bar.setAttribute("aria-label", "Score de compatibilité " + pct + " %");
          var fill = document.createElement("span"); fill.style.width = pct + "%"; bar.appendChild(fill);
          var parts = document.createElement("div");
          parts.className = "small text-muted mt-1";
          parts.textContent = "Trajet " + Math.round(r.parts.route * 100) + " % · Date " + Math.round(r.parts.date * 100) +
            " % · Capacité " + Math.round(r.parts.capacity * 100) + " % · Prix " + Math.round(r.parts.price * 100) +
            " % · Note " + Math.round(r.parts.rating * 100) + " %";
          li.appendChild(top); li.appendChild(sub); li.appendChild(bar); li.appendChild(parts);
          if (r.compatible) {
            var act = document.createElement("a");
            act.href = r.action_url; act.className = "btn btn-sm btn-outline-primary mt-2";
            act.textContent = "Envoyer une demande";
            li.appendChild(act);
          }
          list.appendChild(li);
        });
      });
    });
  });

  // ---- Rating radios: keyboard-friendly star labels are native radios; nothing to do. ----
})();
