FROM python:3.13.5-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

# Install dependencies
COPY "pyproject.toml" "uv.lock" ".python-version" ./
RUN uv sync --locked
ENV PATH="/code/.venv/bin:$PATH"

# Copy project
COPY . .
RUN chmod +x entrypoint.sh && \
    mkdir -p static && \
    python manage.py collectstatic --noinput

EXPOSE 80
ENTRYPOINT ["/code/entrypoint.sh"]
CMD gunicorn course_management.wsgi --bind 0.0.0.0:80