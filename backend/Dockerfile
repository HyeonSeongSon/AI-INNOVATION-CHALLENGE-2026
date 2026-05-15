FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY opensearch/requirements.txt /requirements.txt

RUN pip install uv && uv pip install -r /requirements.txt --system

WORKDIR /app
