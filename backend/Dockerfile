FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY opensearch/requirements.txt /requirements.txt

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system --no-cache -r /requirements.txt

WORKDIR /app
