"""
v4 멀티벡터 색인 스크립트

구조:
- 5개 필드별 별도 인덱스 (product_v4_combined, product_v4_function_desc, ...)
- 각 문장을 독립 문서로 색인 (문장별 임베딩)
- 7개 JSONL 파일 일괄 처리

인덱스당 문서 구조:
  product_id, group, sentence_idx, text, vector, is_active, embedding_model
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import logging

from opensearch_hybrid import OpenSearchHybridClient
from path_utils import get_absolute_path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 임베딩 모델 버전
EMBEDDING_MODEL_VERSION = "KURE-v1"

# 색인할 5개 필드
FIELD_NAMES = ["combined", "function_desc", "attribute_desc", "target_user", "spec_feature"]

# 인덱스 이름 prefix
INDEX_PREFIX = "product_v4"

# 색인할 7개 파일
DATA_FILES = [
    ("data", "v4_product_data_beauty_tool.jsonl"),
    ("data", "v4_product_data_color_tone.jsonl"),
    ("data", "v4_product_data_fragrance_body.jsonl"),
    ("data", "v4_product_data_hair.jsonl"),
    ("data", "v4_product_data_inner_beauty.jsonl"),
    ("data", "v4_product_data_living_supplies.jsonl"),
    ("data", "v4_product_data_skincare.jsonl"),
]


def create_field_index_mapping() -> dict:
    """
    5개 필드 인덱스 공통 매핑.
    BM25 b=0.4: 필드별 문장 수 편차에 의한 길이 패널티 완화
    """
    return {
        "settings": {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100,
                "similarity": {
                    "custom_bm25": {
                        "type": "BM25",
                        "k1": 1.2,
                        "b": 0.4,
                    }
                },
            },
            "analysis": {
                "analyzer": {
                    "korean_analyzer": {
                        "type": "custom",
                        "tokenizer": "nori_tokenizer",
                        "filter": [
                            "nori_readingform",
                            "lowercase",
                        ],
                    }
                }
            },
        },
        "mappings": {
            "properties": {
                "product_id":      {"type": "keyword"},
                "group":           {"type": "keyword"},
                "sentence_idx":    {"type": "integer"},
                "text": {
                    "type":       "text",
                    "analyzer":   "korean_analyzer",
                    "similarity": "custom_bm25",
                },
                "vector": {
                    "type":      "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name":       "hnsw",
                        "space_type": "cosinesimil",
                        "engine":     "lucene",
                        "parameters": {"ef_construction": 128, "m": 16},
                    },
                },
                "is_active":       {"type": "boolean"},
                "embedding_model": {"type": "keyword"},
            }
        },
    }


def load_all_sentences(data_files: list[tuple]) -> dict[str, list[dict]]:
    """
    7개 파일을 읽어 필드별로 문장 문서 리스트를 반환합니다.

    Returns:
        {
          "combined": [{"product_id": ..., "group": ..., "sentence_idx": ..., "text": ..., ...}, ...],
          "function_desc": [...],
          ...
        }
    """
    field_docs: dict[str, list[dict]] = {field: [] for field in FIELD_NAMES}

    for path_parts in data_files:
        file_path = get_absolute_path(*path_parts)
        logging.info(f"로드 중: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        product = json.loads(line)
                    except json.JSONDecodeError as e:
                        logging.error(f"  {file_path}:{line_num} JSON 파싱 오류: {e}")
                        continue

                    product_id = product.get("product_id")
                    if not product_id:
                        logging.warning(f"  {file_path}:{line_num} product_id 없음, 건너뜀")
                        continue

                    group = product.get("group", "")

                    for field in FIELD_NAMES:
                        sentences = product.get(field, [])
                        if isinstance(sentences, str):
                            sentences = [sentences]
                        for idx, sentence in enumerate(sentences):
                            if not sentence or not sentence.strip():
                                continue
                            field_docs[field].append({
                                "product_id":      product_id,
                                "group":           group,
                                "sentence_idx":    idx,
                                "text":            sentence.strip(),
                                "is_active":       True,
                                "embedding_model": EMBEDDING_MODEL_VERSION,
                            })

        except FileNotFoundError:
            logging.error(f"파일 없음: {file_path}")

    logging.info("필드별 로드 결과:")
    for field, docs in field_docs.items():
        logging.info(f"  {field}: {len(docs)}개 문장")

    return field_docs


def index_one_field(
    client: OpenSearchHybridClient,
    field_name: str,
    documents: list[dict],
    recreate_index: bool,
) -> bool:
    """단일 필드 인덱스 생성 → 임베딩 → bulk 색인"""
    index_name = f"{INDEX_PREFIX}_{field_name}"

    if recreate_index:
        logging.info(f"[{index_name}] 기존 인덱스 삭제...")
        client.delete_index(index_name)

    mapping = create_field_index_mapping()
    if not client.create_index_with_mapping(index_name, mapping):
        logging.error(f"[{index_name}] 인덱스 생성 실패")
        return False

    texts = [doc["text"] for doc in documents]
    logging.info(f"[{index_name}] {len(texts)}개 문장 임베딩 중...")
    vectors = client.model.encode(texts, batch_size=64, show_progress_bar=True)

    for doc, vec in zip(documents, vectors):
        doc["vector"] = vec.tolist()

    logging.info(f"[{index_name}] Bulk 색인 시작...")
    success = client.bulk_index_documents(
        index_name=index_name,
        documents=documents,
        refresh=True,
    )

    if success:
        count = client.client.count(index=index_name)["count"]
        logging.info(f"[{index_name}] ✅ 색인 완료 — {count}개 문서")
    else:
        logging.error(f"[{index_name}] ❌ 색인 실패")

    return success


def run_indexing(recreate_index: bool = True):
    client = OpenSearchHybridClient()
    if not client.client:
        logging.error("OpenSearch 클라이언트 초기화 실패")
        return

    logging.info("7개 파일에서 문장 로드 중...")
    field_docs = load_all_sentences(DATA_FILES)

    results = {}
    for field_name in FIELD_NAMES:
        documents = field_docs[field_name]
        if not documents:
            logging.warning(f"[{field_name}] 색인할 문장 없음, 건너뜀")
            results[field_name] = False
            continue
        results[field_name] = index_one_field(
            client, field_name, documents, recreate_index
        )

    print("\n" + "=" * 60)
    print("색인 결과 요약")
    print("=" * 60)
    for field_name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} product_v4_{field_name}")


if __name__ == "__main__":
    RECREATE_INDEX = True

    print("=" * 60)
    print("v4 멀티벡터 색인 시작")
    print(f"생성 인덱스: {[f'{INDEX_PREFIX}_{f}' for f in FIELD_NAMES]}")
    print(f"인덱스 재생성: {RECREATE_INDEX}")
    print("=" * 60)

    run_indexing(recreate_index=RECREATE_INDEX)
