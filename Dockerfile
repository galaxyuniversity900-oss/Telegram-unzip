FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends p7zip-full unrar-free \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin botuser

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
RUN mkdir -p /tmp/tuzsbot && chown -R botuser:botuser /app /tmp/tuzsbot

USER botuser
ENV WORK_DIR=/tmp/tuzsbot

CMD ["python", "-m", "app"]
