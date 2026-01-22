FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libpq-dev gettext ffmpeg libsm6 libxext6 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install with --no-deps for conflicting packages to bypass dependency checks
RUN grep -v "dj-rest-auth" requirements.txt > requirements_temp.txt && \
    pip install --no-cache-dir -r requirements_temp.txt && \
    pip install --no-cache-dir --no-deps dj-rest-auth==7.0.2 && \
    rm requirements_temp.txt

COPY . .

# Collect static files for WhiteNoise
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p" , "8000", "facturation_backend.asgi:application"]