"""
forbidden_sentences 인덱스 생성 및 데이터 색인 스크립트

forbidden_keyword.json의 키워드(80개)와 문장(87개)을 KURE-v1으로 임베딩하여
OpenSearch forbidden_sentences 인덱스에 저장합니다.

3단계 스킵 로직:
  1. OpenSearch 인덱스에 문서가 이미 존재하면 → 즉시 종료 (KURE-v1 미로드)
  2. 캐시 파일(data/forbidden_sentences_cache.jsonl)이 있으면 → 임베딩 스킵, 캐시에서 로드
  3. 둘 다 없으면 → KURE-v1 로드, 임베딩, 캐시 저장, 색인

실행: python index_forbidden_sentences.py
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from opensearchpy import OpenSearch, exceptions, helpers
from sentence_transformers import SentenceTransformer

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

INDEX_NAME = "forbidden_sentences"
CACHE_FILE = Path("data/forbidden_sentences_cache.jsonl")
FORBIDDEN_KEYWORD_FILE = Path("data/forbidden_keyword.json")
BATCH_SIZE = 64
VECTOR_DIM = 1024

INDEX_MAPPING = {
    "settings": {
        "index": {
            "knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 1,
        }
    },
    "mappings": {
        "properties": {
            "sentence": {"type": "text"},
            "sentence_vector": {
                "type": "knn_vector",
                "dimension": VECTOR_DIM,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                    "parameters": {
                        "ef_construction": 128,
                        "m": 16,
                    },
                },
            },
            "source": {
                "properties": {
                    "category": {"type": "keyword"},
                    "label": {"type": "keyword"},
                    "severity": {"type": "keyword"},
                    "type": {"type": "keyword"},
                }
            },
        }
    },
}


def _connect() -> OpenSearch:
    """환경변수로 OpenSearch에 연결. 실패 시 SystemExit."""
    host = os.getenv("OPENSEARCH_HOST", "localhost")
    port = int(os.getenv("OPENSEARCH_PORT", "9200"))
    logger.info("connecting to opensearch host=%s port=%s", host, port)
    client = OpenSearch(hosts=[{"host": host, "port": port}], timeout=30)
    # 연결 확인: 최대 30초 대기
    for attempt in range(1, 7):
        if client.ping():
            logger.info("opensearch connected")
            return client
        logger.warning("ping failed (attempt %d/6), retrying in 5s...", attempt)
        time.sleep(5)
    logger.error("opensearch connection failed after retries")
    sys.exit(1)


def _index_has_docs(client: OpenSearch) -> bool:
    """forbidden_sentences 인덱스가 존재하고 문서가 1개 이상이면 True."""
    try:
        if not client.indices.exists(index=INDEX_NAME):
            return False
        count = client.count(index=INDEX_NAME)["count"]
        return count > 0
    except exceptions.OpenSearchException:
        return False


def _extract_items(keyword_file: Path) -> list[dict]:
    """
    forbidden_keyword.json에서 키워드와 문장을 추출하여
    {sentence, category, label, severity, type} dict 리스트 반환.
    """
    data = json.loads(keyword_file.read_text(encoding="utf-8"))
    items: list[dict] = []
    for cat_key, cat_data in data.get("categories", {}).items():
        label = cat_data.get("label", cat_key)
        severity = cat_data.get("severity", "")
        for kw in cat_data.get("keywords", []):
            items.append({"sentence": kw, "category": cat_key, "label": label, "severity": severity, "type": "keyword"})
        for sent in cat_data.get("sentences", []):
            items.append({"sentence": sent, "category": cat_key, "label": label, "severity": severity, "type": "sentence"})
    logger.info("extracted %d items from forbidden_keyword.json", len(items))
    return items


def _load_cache() -> list[dict] | None:
    """캐시 파일이 있으면 로드하여 반환. 없으면 None."""
    if not CACHE_FILE.exists():
        return None
    items = []
    with CACHE_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    logger.info("loaded %d items from cache %s", len(items), CACHE_FILE)
    return items


def _embed_and_cache(items: list[dict]) -> list[dict]:
    """KURE-v1 모델로 임베딩 후 캐시 파일에 저장. 임베딩된 items 반환."""
    logger.info("loading KURE-v1 model (this may take a few minutes)...")
    model = SentenceTransformer("nlpai-lab/KURE-v1")
    logger.info("model loaded, embedding %d items (batch_size=%d)...", len(items), BATCH_SIZE)

    texts = [item["sentence"] for item in items]
    vectors = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=True).tolist()

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        for item, vector in zip(items, vectors):
            record = {**item, "vector": vector}
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info("cache saved to %s", CACHE_FILE)
    return [{**item, "vector": vector} for item, vector in zip(items, vectors)]


def _create_index(client: OpenSearch) -> None:
    """forbidden_sentences 인덱스가 없으면 생성."""
    if client.indices.exists(index=INDEX_NAME):
        logger.info("index already exists: %s", INDEX_NAME)
        return
    client.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
    logger.info("index created: %s", INDEX_NAME)


def _bulk_index(client: OpenSearch, records: list[dict]) -> None:
    """records를 forbidden_sentences 인덱스에 bulk 색인."""
    actions = [
        {
            "_index": INDEX_NAME,
            "_source": {
                "sentence": r["sentence"],
                "sentence_vector": r["vector"],
                "source": {
                    "category": r["category"],
                    "label": r["label"],
                    "severity": r["severity"],
                    "type": r["type"],
                },
            },
        }
        for r in records
    ]
    success, failed = helpers.bulk(client, actions, refresh=True)
    if failed:
        logger.warning("bulk index: %d succeeded, %d failed", success, len(failed))
    else:
        logger.info("bulk index completed: %d documents indexed", success)


def main() -> None:
    client = _connect()

    # Step 1: 인덱스에 이미 데이터가 있으면 스킵
    if _index_has_docs(client):
        count = client.count(index=INDEX_NAME)["count"]
        logger.info("forbidden_sentences already indexed (%d docs), skipping", count)
        return

    # Step 2: forbidden_keyword.json 로드
    if not FORBIDDEN_KEYWORD_FILE.exists():
        logger.error("forbidden_keyword.json not found at %s", FORBIDDEN_KEYWORD_FILE)
        sys.exit(1)
    items = _extract_items(FORBIDDEN_KEYWORD_FILE)

    # Step 3: 캐시 확인 → 없으면 임베딩 후 캐시 저장
    cached = _load_cache()
    if cached is not None:
        records = cached
    else:
        records = _embed_and_cache(items)

    # Step 4: 인덱스 생성 + 색인
    _create_index(client)
    _bulk_index(client, records)

    final_count = client.count(index=INDEX_NAME)["count"]
    logger.info("forbidden_sentences_indexed total_docs=%d", final_count)


if __name__ == "__main__":
    main()
