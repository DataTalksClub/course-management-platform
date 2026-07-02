#!/bin/sh

echo "Apply database migrations"
uv run python manage.py migrate

if [ $? -ne 0 ]; then
    echo "Failed to apply database migrations."
    exit 1
else
    echo "Database migrations applied successfully."
fi

if [ ! -f /code/.docker/initialized ]; then
    echo "First-time setup: running scripts.add_data"
    uv run python -m scripts.add_data
    
    if [ $? -ne 0 ]; then
        echo "Failed to run scripts.add_data"
        exit 1
    fi
    
    echo "First-time setup: running scripts.add_more_test_data"
    uv run python -m scripts.add_more_test_data
    
    if [ $? -ne 0 ]; then
        echo "Failed to run scripts.add_more_test_data"
        exit 1
    fi
    
    mkdir -p /code/.docker
    touch /code/.docker/initialized
    echo "First-time setup completed successfully"
else
    echo "Database already initialized, skipping data setup"
fi

echo "Starting server"
exec "$@"
