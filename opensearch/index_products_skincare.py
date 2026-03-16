import json
import logging
from opensearch_hybrid import OpenSearchHybridClient
from path_utils import get_absolute_path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# structured 필드 중 색인할 항목 (category 제외)
STRUCTURED_TEXT_FIELDS = [
    'summary', 'concern', 'ingredient', 'texture', 'value',
    'target_user', 'function', 'function_desc', 'attribute', 'attribute_desc',
    'combined', 'key_benefits', 'proof_points', 'usage_context',
    'product_story', 'highlight_keywords',
]
STRUCTURED_KEYWORD_FIELDS = [
    'suitable_for', 'body_area', 'absorption_speed', 'finish_type',
    'concentration_level', 'layering_compatible_types', 'ingredient_quality',
]
STRUCTURED_INT_FIELDS = [
    'layering_order',
]


def create_product_index_mapping():
    """
    상품 데이터를 위한 OpenSearch 인덱스 매핑 생성
    """
    mapping = {
        "settings": {
            "index": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
                "knn": True,
                "knn.algo_param.ef_search": 100
            },
            "analysis": {
                "analyzer": {
                    "korean_analyzer": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "product_id": {
                    "type": "keyword"
                },
                "카테고리": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "태그": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "브랜드": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "상품명": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "피부타입": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "고민키워드": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "선호포인트색상": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "선호성분": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "기피성분": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "선호향": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "가치관": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "전용제품": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "퍼스널컬러": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                "피부호수": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {"keyword": {"type": "keyword"}}
                },
                # structured 필드 (category 제외)
                "summary": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "concern": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "ingredient": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "texture": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "value": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "target_user": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "suitable_for": {
                    "type": "keyword"
                },
                "body_area": {
                    "type": "keyword"
                },
                "function": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "function_desc": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "attribute": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "attribute_desc": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "combined": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "key_benefits": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "proof_points": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "usage_context": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "product_story": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "highlight_keywords": {
                    "type": "keyword"
                },
                "layering_order": {
                    "type": "integer"
                },
                "absorption_speed": {
                    "type": "keyword"
                },
                "finish_type": {
                    "type": "keyword"
                },
                "concentration_level": {
                    "type": "keyword"
                },
                "layering_compatible_types": {
                    "type": "keyword"
                },
                "function_desc_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": 128, "m": 16}
                    }
                },
                "attribute_desc_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": 128, "m": 16}
                    }
                },
                "combined_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": 128, "m": 16}
                    }
                },
                "target_user_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {"ef_construction": 128, "m": 16}
                    }
                }
            }
        }
    }
    return mapping


def load_and_prepare_documents(jsonl_file_path):
    """
    JSONL 파일에서 문서를 로드하고 색인할 필드만 추출합니다.
    structured 필드를 최상위로 펼쳐서 저장하고, category는 제외합니다.
    """
    documents = []

    # 기존 최상위 필드 (문서 제외)
    base_fields = [
        'product_id', '카테고리', '태그', '브랜드', '상품명', '피부타입',
        '고민키워드', '선호포인트색상', '선호성분', '기피성분',
        '선호향', '가치관', '전용제품', '퍼스널컬러', '피부호수',
    ]

    try:
        with open(jsonl_file_path, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)

                    # 기존 필드 추출
                    filtered_doc = {}
                    for field in base_fields:
                        if field in data:
                            filtered_doc[field] = data[field]

                    # 페르소나태그에서 필드 추출
                    persona = data.get('페르소나태그', {})
                    for field in ['피부타입', '고민키워드', '선호포인트색상', '선호성분',
                                  '기피성분', '선호향', '가치관', '전용제품']:
                        if field not in filtered_doc and field in persona:
                            filtered_doc[field] = persona[field]

                    # structured 필드 추출 (category 제외, 최상위로 펼침)
                    structured = data.get('structured', {})
                    for field in STRUCTURED_TEXT_FIELDS:
                        val = structured.get(field)
                        if val is not None:
                            # list는 그대로 저장 (OpenSearch text 필드는 list 지원)
                            filtered_doc[field] = val if val != [] else None

                    for field in STRUCTURED_KEYWORD_FIELDS:
                        val = structured.get(field)
                        if val is not None:
                            filtered_doc[field] = val

                    for field in STRUCTURED_INT_FIELDS:
                        val = structured.get(field)
                        if val is not None:
                            filtered_doc[field] = val

                    if 'product_id' not in filtered_doc:
                        logging.warning(f"라인 {line_num}: product_id가 없어 건너뜁니다.")
                        continue

                    documents.append(filtered_doc)

                except json.JSONDecodeError as e:
                    logging.error(f"라인 {line_num} JSON 파싱 오류: {e}")
                    continue

        logging.info(f"'{jsonl_file_path}'에서 {len(documents)}개 문서를 로드했습니다.")
        return documents

    except FileNotFoundError:
        logging.error(f"파일을 찾을 수 없습니다: {jsonl_file_path}")
        return []
    except Exception as e:
        logging.error(f"파일 로드 중 오류 발생: {e}")
        return []


def index_products_to_opensearch(
    jsonl_file_path,
    index_name="product_index_v2",
    recreate_index=False
):
    """
    상품 데이터를 OpenSearch에 색인합니다.

    Args:
        jsonl_file_path: JSONL 파일 경로
        index_name: 생성할 인덱스 이름
        recreate_index: True이면 기존 인덱스 삭제 후 재생성
    """
    client = OpenSearchHybridClient()

    if not client.client:
        logging.error("OpenSearch 클라이언트 초기화 실패")
        return False

    if recreate_index:
        logging.info(f"기존 '{index_name}' 인덱스 삭제 중...")
        client.delete_index(index_name)

    logging.info(f"'{index_name}' 인덱스 생성 중...")
    mapping = create_product_index_mapping()
    if not client.create_index_with_mapping(index_name, mapping):
        logging.error("인덱스 생성 실패")
        return False

    logging.info("JSONL 파일에서 문서 로드 중...")
    documents = load_and_prepare_documents(jsonl_file_path)

    if not documents:
        logging.error("로드할 문서가 없습니다.")
        return False

    logging.info(f"{len(documents)}개 문서에 대해 임베딩 생성 및 색인 시작...")

    # 임베딩할 필드와 저장할 벡터 필드명 매핑
    EMBED_FIELDS = [
        ('function_desc',  'function_desc_vector'),
        ('attribute_desc', 'attribute_desc_vector'),
        ('combined',       'combined_vector'),
        ('target_user',    'target_user_vector'),
    ]

    if hasattr(client, 'model') and client.model:
        for src_field, vec_field in EMBED_FIELDS:
            # 각 문서에서 텍스트 추출 (list면 join)
            texts = []
            for doc in documents:
                val = doc.get(src_field) or ''
                texts.append(' '.join(val) if isinstance(val, list) else val)

            logging.info(f"'{src_field}' 배치 임베딩 중... ({len(texts)}건)")
            vectors = client.model.encode(texts, batch_size=64, show_progress_bar=False)

            for doc, vec, text in zip(documents, vectors, texts):
                if text:  # 텍스트가 없는 문서는 벡터 저장 안 함
                    doc[vec_field] = vec.tolist()

    logging.info("Bulk 색인 시작...")
    success = client.bulk_index_documents(
        index_name=index_name,
        documents=documents,
        refresh=True
    )

    if success:
        logging.info(f"✅ 색인 완료! {len(documents)}개 문서가 '{index_name}' 인덱스에 색인되었습니다.")
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
    JSONL_FILE = get_absolute_path("data", "product_data_structured_skincare.jsonl")
    INDEX_NAME = "product_index_v2"
    RECREATE_INDEX = True

    print("=" * 60)
    print("상품 데이터 OpenSearch 색인 시작 (v2 - structured 필드 포함)")
    print("=" * 60)
    print(f"JSONL 파일: {JSONL_FILE}")
    print(f"인덱스 이름: {INDEX_NAME}")
    print(f"인덱스 재생성: {RECREATE_INDEX}")
    print("=" * 60)

    success = index_products_to_opensearch(
        jsonl_file_path=JSONL_FILE,
        index_name=INDEX_NAME,
        recreate_index=RECREATE_INDEX
    )

    if success:
        print("\n✅ 모든 작업이 성공적으로 완료되었습니다!")
    else:
        print("\n❌ 작업 중 오류가 발생했습니다.")
