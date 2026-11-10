FROM python:3.13.18-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

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

# Keep the configured port 80 for the existing Coolify application while
# granting only the low-port bind capability to Python.
RUN apt-get update && \
    apt-get install -y --no-install-recommends libcap2-bin && \
    setcap 'cap_net_bind_service=+ep' /usr/local/bin/python3.13 && \
    apt-get purge -y --auto-remove libcap2-bin && \
    rm -rf /var/lib/apt/lists/*

RUN useradd --system --uid 10001 --create-home --home-dir /home/cmp cmp

# Install dependencies
COPY "pyproject.toml" "uv.lock" ".python-version" ./
RUN uv sync --locked --no-dev

# Copy project
COPY . .
RUN chmod +x entrypoint.sh docker-entrypoint.sh && \
    mkdir -p static && \
    SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \
      python manage.py collectstatic --noinput && \
    chown -R cmp:cmp /code

EXPOSE 80
USER cmp:cmp
ENTRYPOINT ["/code/entrypoint.sh"]
CMD ["gunicorn", "course_management.wsgi", "--bind", "0.0.0.0:80", "--timeout", "90"]
