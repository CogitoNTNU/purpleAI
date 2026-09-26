#!/bin/sh

# Apply database migrations
python manage.py migrate

# Check if any users exist in the database
USER_EXISTS=$(python manage.py shell -c "from django.contrib.auth import get_user_model; print(get_user_model().objects.exists())")

if [ "$USER_EXISTS" = "False" ]
then
    echo "Database is empty. Seeding data..."
    python manage.py populate_db
else
    echo "Database already contains data. Skipping seed."
fi

# Start the server
python manage.py runserver 0.0.0.0:8000