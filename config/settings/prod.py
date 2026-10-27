from .base import *  # noqa: F401,F403
from .base import ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, env

DEBUG = False
SECRET_KEY = env("SECRET_KEY")  # required: no default in production

# Render (and similar PaaS) expose the public hostname in an env var.
if host := env("RENDER_EXTERNAL_HOSTNAME", default=""):
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, host]
    CSRF_TRUSTED_ORIGINS = [*CSRF_TRUSTED_ORIGINS, f"https://{host}"]

# HTTPS hardening. Behind a TLS-terminating proxy (Render, nginx) the scheme comes from X-Forwarded-Proto.
# For a purely local `docker compose up` over http://localhost, set SECURE_SSL_REDIRECT=False,
# SECURE_COOKIES=False and SECURE_HSTS_SECONDS=0 (see docker-compose.yml).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
