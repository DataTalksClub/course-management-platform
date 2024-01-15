FROM python:3.9.13-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /code

# Install dependencies
COPY Pipfile Pipfile.lock /code/
RUN pip install pipenv && pipenv install --system

# Copy project
COPY . /code/

# Collect static files
RUN mkdir -p /code/static && python manage.py collectstatic --noinput

COPY entrypoint.sh /code/
RUN chmod +x /code/entrypoint.sh
ENTRYPOINT ["/code/entrypoint.sh"]

EXPOSE 8000

CMD uvicorn course_management.asgi:application --host 0.0.0.0 --port 8000
