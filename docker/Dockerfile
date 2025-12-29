FROM python:3.12.12-slim-bookworm
LABEL maintainer="zenpaiang <zenpai@2020220.xyz>"
LABEL org.opencontainers.image.source=https://github.com/whiteout-project/bot

WORKDIR /app

RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN chmod +x /app/docker/bootstrap.sh

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/bin/sh", "/app/docker/bootstrap.sh"]
