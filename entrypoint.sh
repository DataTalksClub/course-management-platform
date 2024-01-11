#!/bin/sh

echo "Apply database migrations"
python manage.py migrate

echo "Starting server"
exec "$@"