#!/bin/sh
set -e

# Ensure media directories exist with correct permissions
mkdir -p /app/media/user_avatars /app/media/article_images /app/media/company_images
chown -R appuser:appuser /app/media

# Celery Beat stores its schedule in a dedicated persistent volume.
if [ -d /schedule ]; then
    chown appuser:appuser /schedule
fi

# Drop to appuser and exec the CMD
exec gosu appuser "$@"
