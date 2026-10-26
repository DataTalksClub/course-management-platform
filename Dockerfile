FROM python:3.13.5-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/code/.venv/bin:$PATH"

# Release identity baked at build time so /api/health/ reports the deployed
# image tag even if the runtime VERSION env is missing. GHA passes
# --build-arg VERSION=<YYYYMMDD-HHMMSS-<7>> (same value as the GHCR tag);
# deploy automation also pins the Coolify compose VERSION env to that tag.
ARG VERSION=local-development-build-version-not-configured
ENV VERSION=${VERSION}

WORKDIR /code

# Install dependencies
COPY "pyproject.toml" "uv.lock" ".python-version" ./
RUN uv sync --locked

# Copy project
COPY . .
RUN chmod +x entrypoint.sh docker-entrypoint.sh && \
    mkdir -p static && \
    python manage.py collectstatic --noinput

EXPOSE 80
ENTRYPOINT ["/code/entrypoint.sh"]
CMD ["gunicorn", "course_management.wsgi", "--bind", "0.0.0.0:80", "--timeout", "90"]
