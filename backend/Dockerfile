FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 의존성 — 레이어 캐시를 위해 코드보다 먼저
COPY opensearch/requirements.txt /requirements.txt
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /uvx /bin/
RUN uv pip install --system --no-cache -r /requirements.txt

WORKDIR /app
# 앱 코드 — ECS는 볼륨 마운트가 없으므로 이미지에 포함되어야 함 (.dockerignore가 .env/캐시 제외)
COPY backend/ /app/
COPY data/category.json /data/category.json
COPY data/brands.json /data/brands.json
COPY data/purposes.json /data/purposes.json

# 비루트 유저로 실행 (보안)
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8005
# 기본 명령 = API 게이트웨이. 나머지 4개 서비스는 ECS task_definition의 command로 오버라이드.
CMD ["python", "main.py"]
