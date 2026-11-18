"""Automatic sign-out a fixed time after signing in (SIGN_OUT_AFTER_DAYS, default 30).

Counted from the sign-in, not from the last visit, so a lost phone does not stay
signed in forever just because it keeps being opened.
"""
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.shortcuts import redirect

SESSION_KEY = "signed_in_at"


@receiver(user_logged_in)
def remember_sign_in_time(sender, request, user, **kwargs):
    if request is not None and hasattr(request, "session"):
        request.session[SESSION_KEY] = int(time.time())


class SignOutAfterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            signed_in_at = request.session.get(SESSION_KEY)
            if signed_in_at is None:  # session from before this feature: start counting now
                request.session[SESSION_KEY] = int(time.time())
            elif time.time() - signed_in_at > settings.SIGN_OUT_AFTER_DAYS * 86400:
                logout(request)
                messages.info(request, f"For safety you are signed out every {settings.SIGN_OUT_AFTER_DAYS} days. "
                                       "Please sign in again.")
                return redirect(f"{settings.LOGIN_URL_PATH}?next={request.get_full_path()}"
                                if request.method == "GET" else settings.LOGIN_URL_PATH)
        return self.get_response(request)


class FreshPagesMiddleware:
    """Signed-in pages are never kept by the browser, so Back always shows fresh data
    (a case paid a moment ago shows Paid) and patient details are not stored on the phone."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated and "Cache-Control" not in response
                and response.get("Content-Type", "").startswith("text/html")):
            response["Cache-Control"] = "no-store"
        return response
