FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files (WhiteNoise) and local AI models are built into the image.
RUN SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.db python manage.py collectstatic --noinput \
 && SECRET_KEY=build-only DATABASE_URL=sqlite:////tmp/build.db python manage.py train_ai_models \
 && chmod +x docker/entrypoint.sh \
 && useradd --create-home --uid 1000 app && chown -R app:app /app

USER app
EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]
