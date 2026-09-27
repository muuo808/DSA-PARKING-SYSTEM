"""
SmartPark Kenya – Django settings.

Configuration is environment-driven so the database can move from the local
development placeholder to Supabase PostgreSQL by changing DATABASE_URL only.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env (never committed - see .env.example)
load_dotenv(BASE_DIR / ".env")

# Security
# https://docs.djangoproject.com/en/6.1/ref/settings/#secret-key
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-key-change-me-before-production",
)

# https://docs.djangoproject.com/en/6.1/ref/settings/#debug
DEBUG = os.environ.get("DJANGO_DEBUG", "true").strip().lower() in {"1", "true", "yes"}

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # SmartPark Kenya applications
    "django_app.accounts",
    "django_app.parking",
    "django_app.payments",
    "django_app.reports",
    "django_app.dashboard",
    "django_app.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "django_app.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "django_app.wsgi.application"

# Database
# Single source of truth is Supabase PostgreSQL (spec: Database section).
# DATABASE_URL examples:
#   Supabase : postgresql://postgres.xxxx:password@aws-0.xx.pooler.supabase.com:5432/postgres?sslmode=require
#   Local    : postgresql://user:password@127.0.0.1:5432/smartpark
# Falls back to SQLite only for first-run bootstrap before credentials exist.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require="supabase" in DATABASE_URL,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Testing
# -------
# `manage.py test` is deliberately zero-config and offline: unless the
# operator explicitly opts in, the run swaps in a local SQLite test database
# (Django keeps it in memory) so that:
#   * a fresh clone can run the suite with no database account and no network,
#   * a test run can never write to the live Supabase database even when
#     DATABASE_URL is configured, and
#   * a stale `test_postgres` left behind by an interrupted run cannot stall
#     the suite while it tries to drop it over the connection pooler.
#
# Opt in to the PostgreSQL path (exercises tests/runner.py's pooler-safe
# teardown) with:
#     TEST_USE_POSTGRES=1 python manage.py test tests
if "test" in sys.argv:
    use_postgres = os.environ.get("TEST_USE_POSTGRES", "").strip().lower()
    if use_postgres not in {"1", "true", "yes"}:
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",  # never opened: tests run in memory
            "TEST": {"NAME": ":memory:"},
        }

    # Also disable the keep-alive so Supabase's pooler (Supavisor) releases its
    # server-side session the moment Django disconnects. With conn_max_age
    # still active, that lingering session blocks the `DROP DATABASE
    # test_postgres` at the end of `manage.py test`
    # ("database is being accessed by other users").
    DATABASES["default"]["CONN_MAX_AGE"] = 0

# Custom runner: if the pooler still holds the test database open at teardown,
# retry the DROP DATABASE WITH (FORCE) instead of failing the whole run
# (see tests/runner.py).
TEST_RUNNER = "tests.runner.PoolerSafeTestRunner"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-ke"

# Kenya local time for entry/exit records and fee calculation
TIME_ZONE = "Africa/Nairobi"

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Custom user model (roles: ADMIN / ATTENDANT)
AUTH_USER_MODEL = "accounts.User"

# Authentication URLs
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# Email backend for password reset during development (prints to console)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "noreply@smartpark.co.ke"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Flask microservice endpoints (Modules 5 and 7)
FEE_SERVICE_URL = os.environ.get("FEE_SERVICE_URL", "http://127.0.0.1:5000").rstrip("/")
BARRIER_SERVICE_URL = os.environ.get(
    "BARRIER_SERVICE_URL", "http://127.0.0.1:5001"
).rstrip("/")
SERVICE_TIMEOUT_SECONDS = float(os.environ.get("SERVICE_TIMEOUT_SECONDS", "5"))
