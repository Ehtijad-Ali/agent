FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Unprivileged user; /app/data holds the optional Telegram account session.
RUN useradd --create-home signal && mkdir -p /app/data && chown -R signal /app
USER signal

EXPOSE 8000

# One worker: the scheduled scanner runs inside the API process. The Redis
# scan lock keeps it safe if this is ever raised.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
