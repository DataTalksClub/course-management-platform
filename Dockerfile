FROM python:3.12.3-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

# Install dependencies
COPY Pipfile Pipfile.lock ./
RUN pip install pipenv && pipenv install --system

# Copy project
COPY . .
RUN chmod +x entrypoint.sh && \
    mkdir -p static && \
    python manage.py collectstatic --noinput

EXPOSE 80
ENTRYPOINT ["/code/entrypoint.sh"]
CMD gunicorn course_management.wsgi --bind 0.0.0.0:80