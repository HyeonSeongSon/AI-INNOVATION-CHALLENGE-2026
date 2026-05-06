import json
import logging
from opensearch_hybrid import OpenSearchHybridClient
from path_utils import get_absolute_path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# 공통 structured 텍스트 필드
STRUCTURED_TEXT_FIELDS = [
    'summary', 'concern', 'ingredient', 'texture', 'value',
    'target_user', 'function', 'function_desc', 'attribute', 'attribute_desc',
    'combined', 'key_benefits', 'proof_points', 'usage_context',
    'product_story', 'highlight_keywords', 'search_phrases',
]
# 공통 keyword 필드 (스킨케어 인덱스에 이미 매핑된 것 포함)
STRUCTURED_KEYWORD_FIELDS = [
    'suitable_for', 'body_area',
    'absorption_speed',      # 스킨케어 인덱스에 이미 존재
    # 향수/바디 전용
    'care_product_type', 'fragrance_level', 'fragrance_family',
    'deodorant_type', 'longevity', 'bath_effect', 'bath_color',
    'hand_foot_concern',
    'function_tags', 'attribute_tags', 'target_tags', 'search_tags',
]
# 향수/바디 전용 boolean 필드
STRUCTURED_BOOL_FIELDS = [
    'aluminum_free',
]
# greasy_feel: 헤어에서 string keyword로 이미 매핑됨
# 향수/바디 데이터에선 bool 값이 올 수 있으므로 string으로 변환해서 저장
GREASY_FEEL_FIELD = 'greasy_feel'


def get_fragrance_body_new_field_mappings():
    """기존 인덱스에 없는 향수/바디 전용 필드 매핑.
    - absorption_speed: 스킨케어 인덱스에 이미 존재 → 제외
    - greasy_feel: 헤어 인덱스에 이미 keyword로 존재 → 제외
    """
    keyword_fields = [
        'care_product_type', 'fragrance_level', 'fragrance_family',
        'deodorant_type', 'longevity', 'bath_effect', 'bath_color',
        'hand_foot_concern',
    ]
    properties = {field: {"type": "keyword"} for field in keyword_fields}
    properties["aluminum_free"] = {"type": "boolean"}
    return properties


def update_index_mapping(client, index_name: str):
    """기존 인덱스에 향수/바디 전용 필드 매핑 추가 (이미 존재하는 필드는 건너뜀)"""
    new_properties = get_fragrance_body_new_field_mappings()

    try:
        existing = client.client.indices.get_mapping(index=index_name)
        existing_props = existing[index_name]["mappings"].get("properties", {})
        skipped = [k for k in new_properties if k in existing_props]
        new_properties = {k: v for k, v in new_properties.items() if k not in existing_props}
        if skipped:
            logging.info(f"이미 존재하는 필드 건너뜀: {skipped}")
    except Exception as e:
        logging.warning(f"기존 매핑 조회 실패, 전체 업데이트 시도: {e}")

    if not new_properties:
        logging.info("추가할 새 필드가 없습니다.")
        return True

    try:
        client.client.indices.put_mapping(
            index=index_name,
            body={"properties": new_properties}
        )
        logging.info(f"'{index_name}' 인덱스 매핑 업데이트 완료 ({len(new_properties)}개 필드)")
        return True
    except Exception as e:
        logging.error(f"매핑 업데이트 실패: {e}")
        return False


def _build_attribute_extended(structured: dict) -> str:
    """BM25용 확장 attribute 필드. attribute_desc + texture + value + usage_context"""
    parts = []
    if structured.get("attribute_desc"):
        parts.append(structured["attribute_desc"])
    for field in ("texture", "value", "usage_context"):
        val = structured.get(field)
        if val:
            parts.append(" ".join(val) if isinstance(val, list) else val)
    return " / ".join(filter(None, parts))


def load_and_prepare_documents(jsonl_file_path):
    """
    fragrance_body JSONL에서 문서를 로드하고 색인할 필드만 추출합니다.
    structured 필드를 최상위로 펼쳐서 저장합니다.
    """
    documents = []

    base_fields = [
        'product_id', '태그', '브랜드', '상품명',
        '상품이미지', 'product_url',
    ]

    try:
        with open(jsonl_file_path, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    filtered_doc = {}

                    for field in base_fields:
                        if field in data:
                            filtered_doc[field] = data[field]

                    # 페르소나태그에서 필드 추출
                    persona = data.get('페르소나태그', {})
                    for field in ['피부타입', '고민키워드', '선호포인트색상', '선호성분',
                                  '기피성분', '선호향', '가치관', '전용제품']:
                        if field in persona:
                            filtered_doc[field] = persona[field]

                    structured = data.get('structured', {})

                    # 카테고리 (structured 내부)
                    category = structured.get('category')
                    if category:
                        filtered_doc['카테고리'] = category

                    for field in STRUCTURED_TEXT_FIELDS:
                        val = structured.get(field)
                        if val is not None:
                            filtered_doc[field] = val if val != [] else None

                    for field in STRUCTURED_KEYWORD_FIELDS:
                        val = structured.get(field)
                        if val is not None:
                            filtered_doc[field] = val

                    for field in STRUCTURED_BOOL_FIELDS:
                        val = structured.get(field)
                        if val is not None:
                            filtered_doc[field] = val

                    # greasy_feel: 헤어 인덱스에서 keyword로 매핑됨
                    # bool 값이 들어올 수 있으므로 string으로 변환
                    greasy = structured.get(GREASY_FEEL_FIELD)
                    if greasy is not None:
                        filtered_doc[GREASY_FEEL_FIELD] = str(greasy) if isinstance(greasy, bool) else greasy

                    if 'product_id' not in filtered_doc:
                        logging.warning(f"라인 {line_num}: product_id가 없어 건너뜁니다.")
                        continue

                    filtered_doc['attribute_extended'] = _build_attribute_extended(structured)
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


def index_fragrance_body_to_opensearch(
    jsonl_file_path,
    index_name="product_index_v3",
    recreate_index=False
):
    client = OpenSearchHybridClient()

    if not client.client:
        logging.error("OpenSearch 클라이언트 초기화 실패")
        return False

    if recreate_index:
        logging.info(f"기존 '{index_name}' 인덱스 삭제 중...")
        client.delete_index(index_name)

    # 인덱스가 없으면 에러
    index_exists = client.client.indices.exists(index=index_name)
    if not index_exists:
        logging.error(f"'{index_name}' 인덱스가 존재하지 않습니다. 먼저 스킨케어 색인을 실행하세요.")
        return False

    logging.info(f"'{index_name}' 인덱스에 향수/바디 전용 필드 매핑 추가 중...")
    if not update_index_mapping(client, index_name):
        return False

    logging.info("JSONL 파일에서 문서 로드 중...")
    documents = load_and_prepare_documents(jsonl_file_path)

    if not documents:
        logging.error("로드할 문서가 없습니다.")
        return False

    logging.info(f"{len(documents)}개 문서에 대해 임베딩 생성 및 색인 시작...")

    EMBED_FIELDS = [
        ('function_desc',  'function_desc_vector'),
        ('combined',       'combined_vector'),
        ('target_user',    'target_user_vector'),
    ]

    if hasattr(client, 'model') and client.model:
        for src_field, vec_field in EMBED_FIELDS:
            texts = []
            for doc in documents:
                val = doc.get(src_field) or ''
                texts.append(' '.join(val) if isinstance(val, list) else val)

            logging.info(f"'{src_field}' 배치 임베딩 중... ({len(texts)}건)")
            vectors = client.model.encode(texts, batch_size=64, show_progress_bar=False)

            for doc, vec, text in zip(documents, vectors, texts):
                if text:
                    doc[vec_field] = vec.tolist()

    logging.info("Bulk 색인 시작...")
    success = client.bulk_index_documents(
        index_name=index_name,
        documents=documents,
        refresh=True
    )

    if success:
        logging.info(f"색인 완료! {len(documents)}개 문서가 '{index_name}' 인덱스에 추가되었습니다.")
        try:
            count_response = client.client.count(index=index_name)
            logging.info(f"인덱스 통계 - 총 문서 수: {count_response['count']}")
        except Exception as e:
            logging.warning(f"인덱스 통계 조회 실패: {e}")
        return True
    else:
        logging.error("색인 실패")
        return False


if __name__ == "__main__":
    JSONL_FILE = get_absolute_path("data", "v3_product_data_rewritten_fragrance_body.jsonl")
    INDEX_NAME = "product_index_v3"
    RECREATE_INDEX = False  # 기존 인덱스에 추가

    print("=" * 60)
    print("향수/바디 상품 데이터 OpenSearch 색인 시작")
    print("=" * 60)
    print(f"JSONL 파일: {JSONL_FILE}")
    print(f"인덱스 이름: {INDEX_NAME}")
    print(f"인덱스 재생성: {RECREATE_INDEX}")
    print("=" * 60)

    success = index_fragrance_body_to_opensearch(
        jsonl_file_path=JSONL_FILE,
        index_name=INDEX_NAME,
        recreate_index=RECREATE_INDEX
    )

    if success:
        print("\n모든 작업이 성공적으로 완료되었습니다!")
    else:
        print("\n작업 중 오류가 발생했습니다.")
