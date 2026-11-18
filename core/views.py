import logging

from django.contrib import messages
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control, never_cache

from .assets import OWN_ASSETS, asset_version
from .forms import AppSettingsForm
from .models import AppSettings
from .permissions import admin_required

logger = logging.getLogger(__name__)

# Bump when static assets change so installed PWAs refresh their cache.
SW_CACHE_VERSION = "v11"


@cache_control(max_age=3600)
def manifest(request):
    data = {
        "name": "Team Anesthesia",
        "short_name": "Team Anesthesia",
        "description": "Track completed anaesthesia cases, payments and follow-ups.",
        "id": "/",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#f8f8fb",
        "theme_color": "#ffffff",
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("icons/icon-maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
        "shortcuts": [
            {"name": "Add Case", "url": "/cases/add/", "icons": [{"src": static("icons/icon-192.png"), "sizes": "192x192"}]},
            {"name": "Record Payment", "url": "/payments/record/", "icons": [{"src": static("icons/icon-192.png"), "sizes": "192x192"}]},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")


@never_cache
def service_worker(request):
    precache = [
        "/offline/",
        static("vendor/bootstrap/bootstrap.min.css"),
        static("vendor/bootstrap/bootstrap.bundle.min.js"),
        static("vendor/bootstrap-icons/bootstrap-icons.min.css"),
        static("vendor/bootstrap-icons/fonts/bootstrap-icons.woff2"),
        static("icons/icon-192.png"),
        static("icons/badge-96.png"),
    ] + [f"{static(path)}?v={asset_version()}" for path in OWN_ASSETS]
    response = render(
        request, "pwa/sw.js", {"version": f"{SW_CACHE_VERSION}-{asset_version()}", "precache": precache, "icon": static("icons/icon-192.png"),
                  "badge": static("icons/badge-96.png")},
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    return response


def offline(request):
    return render(request, "pwa/offline.html")


@never_cache
def health(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    # The Windows launcher looks for this exact text to confirm it reached *this* app.
    return HttpResponse("payments-tracker ok", content_type="text/plain")


@admin_required
def settings_view(request):
    obj = AppSettings.load()
    form = AppSettingsForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("app_settings")
    return render(request, "core/settings.html", {"form": form})


def csrf_failure(request, reason=""):
    """Friendly replacement for Django's bare "403 CSRF verification failed" page.

    On phones this mostly happens when a sign-in page was left open for a long
    time, or when the link was opened inside WhatsApp/Gmail's built-in browser.
    """
    logger.warning("CSRF failure on %s: %s (UA: %s)", request.path, reason, request.META.get("HTTP_USER_AGENT", "")[:120])
    if request.path == reverse("login"):
        messages.warning(
            request,
            "Your sign-in page had expired - please sign in again. If this keeps happening, open the "
            "link in Chrome or Safari (not inside WhatsApp/Gmail) and make sure cookies are allowed.",
        )
        return redirect("login")
    return render(request, "403_csrf.html", {"retry_url": request.path}, status=403)

