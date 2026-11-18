"""
Django settings for the Team Anesthesia.

All environment-specific values are read from environment variables so the
same code runs locally (Docker Compose) and in production (behind HTTPS).
"""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def load_env_file(path):
    """Read KEY=VALUE lines from a .env file (for hosts without Docker, e.g.
    PythonAnywhere). Real environment variables always win."""
    if not path.is_file():
        return
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")  # last one wins
    for key, value in values.items():
        os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-secret-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8010,http://127.0.0.1:8010"
)
# Also trust localhost on whichever port Docker publishes the app (APP_PORT),
# so logins keep working if the launcher moves the app to a free port.
if os.environ.get("APP_PORT"):
    for host in ("localhost", "127.0.0.1"):
        origin = f"http://{host}:{os.environ['APP_PORT']}"
        if origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Project apps
    "core",
    "accounts",
    "hospitals",
    "contacts",
    "cases",
    "payments",
    "dashboard",
    "reports",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "core.middleware.SignOutAfterMiddleware",
    "core.middleware.FreshPagesMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
            "builtins": ["core.templatetags.money"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
# - Default: SQLite file in DATA_DIR (client testing / small single-server use).
# - Production (e.g. DigitalOcean): set DATABASE_URL=postgres://user:pass@host:5432/dbname
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL and not DATABASE_URL.startswith("sqlite"):
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=60)}
else:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": DATA_DIR / "db.sqlite3",
            "OPTIONS": {
                # WAL + immediate transactions avoid "database is locked" errors
                # when several people use the app at the same time.
                "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
                "transaction_mode": "IMMEDIATE",
                "timeout": 20,
            },
        }
    }

AUTH_USER_MODEL = "accounts.User"

# Web Push (VAPID). Optional: if not set, a key pair is generated once and kept in DATA_DIR/vapid_keys.json.
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

CSRF_FAILURE_VIEW = "core.views.csrf_failure"

# --- Email (used for "Forgot password") ----------------------------------------
# Set EMAIL_HOST etc. to send real emails (e.g. Gmail with an App Password, Brevo, SES).
# Without it, emails are written to the server log instead of being sent.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST
    else "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER or "Team Anesthesia <noreply@localhost>"
PASSWORD_RESET_TIMEOUT = 60 * 60 * 3  # reset links work for 3 hours

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

LOGIN_URL_PATH = "/login/"

# Automatic sign-out: every user must sign in again this many days after signing in
# (protects other people's data if a phone is lost). 14 = two weeks, 30 = one month.
SIGN_OUT_AFTER_DAYS = int(os.environ.get("SIGN_OUT_AFTER_DAYS", "30"))
SESSION_COOKIE_AGE = 60 * 60 * 24 * SIGN_OUT_AFTER_DAYS

LANGUAGE_CODE = "en-in"
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "Asia/Kolkata")

# Optional secret for /notifications/cron/<token>/ - lets an external scheduler (e.g. cron-job.org)
# trigger the reminder sender every hour on hosts without background jobs. Empty = URL disabled.
NOTIFICATIONS_CRON_TOKEN = os.environ.get("NOTIFICATIONS_CRON_TOKEN", "")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- HTTPS / production hardening -------------------------------------------
# Turn on when the app is served over HTTPS (e.g. behind the Caddy proxy in
# docker-compose.prod.yml). Leave off for plain http://localhost testing.
if env_bool("DJANGO_SECURE", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^health/$"]
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO")},
}
