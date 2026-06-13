FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8020"]
