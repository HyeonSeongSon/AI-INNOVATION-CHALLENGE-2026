FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/
RUN uv pip install --system --no-cache -r requirements.txt

COPY . .

# --timeout-keep-alive 75: 클라이언트(product_client.py, keepalive_expiry=30s)보다
# 충분히 길게 잡아 keep-alive 커넥션 재사용 레이스를 줄인다. 운영 EC2의
# infra/ec2/user_data/db_server.sh ExecStart에도 동일 값을 맞춰야 한다.
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8020", "--timeout-keep-alive", "75"]
