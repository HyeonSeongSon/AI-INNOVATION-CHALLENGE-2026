"""
금지 문장 임베딩 벡터DB(OpenSearch) 색인 스크립트

대상 데이터: forbidden_keyword.json의 sentences
용도: CRM 메시지 생성 시 유사도 기반 금지 표현 검출 (2단계 소프트 필터)
"""

import json
import logging
import sys
from pathlib import Path

# opensearch 모듈 경로 추가 (프로젝트 루트/opensearch/)
PROJECT_ROOT = Path(__file__).resolve().parents[5]  # crm_agent/scripts → backend/app/agents/crm_agent/scripts → ... → 프로젝트 루트
sys.path.insert(0, str(PROJECT_ROOT / "opensearch"))

from opensearch_hybrid import OpenSearchHybridClient  # type: ignore  # noqa: E402

# ── 로깅 설정 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "forbidden_keyword.json"

# ── 인덱스 설정 ────────────────────────────────────────────────────────────────
INDEX_NAME = "forbidden_sentences"
RECREATE_INDEX = True


def create_forbidden_sentences_mapping() -> dict:
    """금지 문장 색인용 OpenSearch 인덱스 매핑"""
    return {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "knn": True,
                "knn.algo_param.ef_search": 100,
            },
            "analysis": {
                "analyzer": {
                    "korean_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase"],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "sentence": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                },
                "category_key": {
                    "type": "keyword",
                },
                "label": {
                    "type": "keyword",
                },
                "severity": {
                    "type": "keyword",
                },
                "sentence_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,  # KURE-v1 모델의 벡터 차원
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
            }
        },
    }


def load_sentences(data_path: Path) -> list[dict]:
    """forbidden_keyword.json에서 sentences 추출"""
    try:
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logging.error(f"파일을 찾을 수 없습니다: {data_path}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"JSON 파싱 오류: {e}")
        return []

    docs = []
    for category_key, category in data["categories"].items():
        for sentence in category.get("sentences", []):
            docs.append(
                {
                    "sentence": sentence,
                    "category_key": category_key,
                    "label": category["label"],
                    "severity": category["severity"],
                }
            )

    logging.info(f"'{data_path.name}'에서 {len(docs)}개 문장을 로드했습니다.")
    return docs


def index_forbidden_sentences(
    index_name: str = INDEX_NAME,
    recreate_index: bool = RECREATE_INDEX,
) -> bool:
    """
    금지 문장을 OpenSearch에 색인합니다.

    Args:
        index_name: 생성할 인덱스 이름
        recreate_index: True이면 기존 인덱스 삭제 후 재생성
    """
    # OpenSearch 클라이언트 초기화
    client = OpenSearchHybridClient()

    if not client.client:
        logging.error("OpenSearch 클라이언트 초기화 실패")
        return False

    # 기존 인덱스 삭제 (옵션)
    if recreate_index:
        logging.info(f"기존 '{index_name}' 인덱스 삭제 중...")
        client.delete_index(index_name)

    # 인덱스 생성
    logging.info(f"'{index_name}' 인덱스 생성 중...")
    mapping = create_forbidden_sentences_mapping()
    if not client.create_index_with_mapping(index_name, mapping):
        logging.error("인덱스 생성 실패")
        return False

    # 문장 로드
    documents = load_sentences(DATA_PATH)
    if not documents:
        logging.error("로드할 문장이 없습니다.")
        return False

    logging.info(f"{len(documents)}개 문장에 대해 임베딩 생성 및 색인 시작...")

    # 임베딩 생성
    documents_with_embeddings = []
    for i, doc in enumerate(documents, 1):
        if client.model:
            doc["sentence_vector"] = client.model.encode(doc["sentence"]).tolist()
        documents_with_embeddings.append(doc)

        if i % 10 == 0:
            logging.info(f"임베딩 생성 진행 중: {i}/{len(documents)}")

    # Bulk 색인
    logging.info("Bulk 색인 시작...")
    success = client.bulk_index_documents(
        index_name=index_name,
        documents=documents_with_embeddings,
        refresh=True,
    )

    if success:
        logging.info(f"✅ 색인 완료! {len(documents_with_embeddings)}개 문장이 '{index_name}' 인덱스에 색인되었습니다.")

        try:
            count_response = client.client.count(index=index_name)
            logging.info(f"📊 인덱스 통계 - 총 문서 수: {count_response['count']}")
        except Exception as e:
            logging.warning(f"인덱스 통계 조회 실패: {e}")

        return True
    else:
        logging.error("❌ 색인 실패")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("금지 문장 OpenSearch 색인 시작")
    print("=" * 60)
    print(f"데이터 파일: {DATA_PATH}")
    print(f"인덱스 이름: {INDEX_NAME}")
    print(f"인덱스 재생성: {RECREATE_INDEX}")
    print("=" * 60)

    success = index_forbidden_sentences(
        index_name=INDEX_NAME,
        recreate_index=RECREATE_INDEX,
    )

    if success:
        print("\n✅ 모든 작업이 성공적으로 완료되었습니다!")
    else:
        print("\n❌ 작업 중 오류가 발생했습니다.")
