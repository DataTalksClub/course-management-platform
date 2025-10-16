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
    echo "First-time setup: running add_data.py"
    uv run python add_data.py
    
    if [ $? -ne 0 ]; then
        echo "Failed to run add_data.py"
        exit 1
    fi
    
    echo "First-time setup: running add_more_test_data.py"
    uv run python add_more_test_data.py
    
    if [ $? -ne 0 ]; then
        echo "Failed to run add_more_test_data.py"
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
