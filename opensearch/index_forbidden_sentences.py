"""
forbidden_sentences 인덱스 색인 스크립트

forbidden_keyword.json 의 sentences 배열을 OpenSearch KNN 인덱스에 색인합니다.
setup_opensearch.py Step 4 에서 호출되거나 단독으로 실행할 수 있습니다.

단독 실행:
    python index_forbidden_sentences.py          # 인덱스가 없을 때만 생성
    python index_forbidden_sentences.py --force  # 기존 인덱스 삭제 후 재생성
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from path_utils import get_absolute_path

INDEX_NAME = "forbidden_sentences"
DEFAULT_JSON_PATH = get_absolute_path(
    "backend", "app", "agents", "generate_message_agent", "data", "forbidden_keyword.json"
)


def _build_mapping(vector_dim: int) -> dict:
    return {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100,
            }
        },
        "mappings": {
            "properties": {
                "sentence": {"type": "text"},
                "category": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "sentence_vector": {
                    "type": "knn_vector",
                    "dimension": vector_dim,
                },
            }
        },
    }


def _load_sentences(json_path: str) -> list[dict]:
    """forbidden_keyword.json 에서 (sentence, category, severity) 튜플 목록 반환."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    records = []
    for cat_key, cat_data in data.get("categories", {}).items():
        severity = cat_data.get("severity", "unknown")
        for sentence in cat_data.get("sentences", []):
            if sentence.strip():
                records.append({"sentence": sentence, "category": cat_key, "severity": severity})
    return records


def run_indexing(client=None, force: bool = False) -> bool:
    """
    forbidden_sentences 인덱스를 생성하고 문장을 색인합니다.

    Args:
        client: OpenSearchHybridClient 인스턴스. None 이면 내부에서 생성.
        force:  True 이면 기존 인덱스를 삭제하고 재생성.

    Returns:
        성공 여부
    """
    json_path = os.getenv("FORBIDDEN_KEYWORD_JSON_PATH", DEFAULT_JSON_PATH)

    if not Path(json_path).exists():
        logger.error("forbidden_keyword_json_not_found: %s", json_path)
        return False

    own_client = client is None
    if own_client:
        from opensearch_hybrid import OpenSearchHybridClient
        logger.info("OpenSearch 연결 중 (임베딩 모델 로드 포함)...")
        client = OpenSearchHybridClient()
        if not client.client:
            logger.error("OpenSearch 연결 실패")
            return False

    if force:
        client.delete_index(INDEX_NAME)

    vector_dim = len(client.model.encode("dummy"))
    mapping = _build_mapping(vector_dim)

    if not client.create_index_with_mapping(INDEX_NAME, mapping):
        logger.error("인덱스 생성 실패: %s", INDEX_NAME)
        return False

    # 이미 문서가 존재하면 (force 없이 재실행 시) 건너뜀
    try:
        count = client.client.count(index=INDEX_NAME)["count"]
        if count > 0 and not force:
            logger.info("인덱스에 이미 %d개 문서가 있습니다. 색인을 건너뜁니다. (--force 로 재색인)", count)
            return True
    except Exception:
        pass

    records = _load_sentences(json_path)
    if not records:
        logger.error("색인할 문장이 없습니다: %s", json_path)
        return False

    logger.info("%d개 문장 임베딩 및 색인 시작...", len(records))
    documents = []
    for rec in records:
        vector = client.model.encode(rec["sentence"]).tolist()
        documents.append({**rec, "sentence_vector": vector})

    ok = client.bulk_index_documents(INDEX_NAME, documents, refresh=True)
    if ok:
        count = client.client.count(index=INDEX_NAME)["count"]
        logger.info("forbidden_sentences 색인 완료: %d개 문서", count)
    else:
        logger.error("forbidden_sentences bulk 색인 실패")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="forbidden_sentences 인덱스 색인")
    parser.add_argument("--force", action="store_true", help="기존 인덱스 삭제 후 재생성")
    args = parser.parse_args()

    success = run_indexing(force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
