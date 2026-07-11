# CogPrint backend — production container.
# Build:  docker build -t cogprint-api .
# Run:    docker run -p 8000:8000 --env-file .env cogprint-api
FROM python:3.13-slim

# Faster, quieter Python in containers.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first for better layer caching.
COPY requirements.txt .
# psycopg (binary) is added here — it's not in requirements.txt because local dev
# uses SQLite. Prod points DATABASE_URL at Postgres (postgresql+psycopg://...).
RUN pip install -r requirements.txt "psycopg[binary]>=3.1"

COPY . .

# Most PaaS platforms inject $PORT; default to 8000 for plain `docker run`.
ENV PORT=8000
EXPOSE 8000

# Shell form so $PORT expands at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
