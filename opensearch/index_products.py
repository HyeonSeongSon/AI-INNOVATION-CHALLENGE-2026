import json
import logging
from opensearch_hybrid import OpenSearchHybridClient

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def create_product_index_mapping():
    """
    상품 데이터를 위한 OpenSearch 인덱스 매핑 생성
    """
    mapping = {
        "settings": {
            "index": {
                "number_of_shards": 3,
                "number_of_replicas": 1,
                "knn": True,  # KNN 검색 활성화
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
                    "type": "keyword"  # 정확한 매칭을 위해 keyword 타입
                },
                "태그": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
                },
                "브랜드": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
                },
                "상품명": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
                },
                "피부타입": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
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
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
                },
                "퍼스널컬러": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
                },
                "피부호수": {
                    "type": "text",
                    "analyzer": "korean_analyzer",
                    "fields": {
                        "keyword": {
                            "type": "keyword"
                        }
                    }
                },
                "문서": {
                    "type": "text",
                    "analyzer": "korean_analyzer"
                },
                "content_vector": {
                    "type": "knn_vector",
                    "dimension": 1024,  # KURE-v1 모델의 벡터 차원
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "lucene",
                        "parameters": {
                            "ef_construction": 128,
                            "m": 16
                        }
                    }
                }
            }
        }
    }
    return mapping


def load_and_prepare_documents(jsonl_file_path):
    """
    JSONL 파일에서 문서를 로드하고 색인할 필드만 추출합니다.
    """
    documents = []

    # 색인할 필드 목록
    fields_to_index = [
        'product_id', '태그', '브랜드', '상품명', '피부타입',
        '고민키워드', '선호포인트색상', '선호성분', '기피성분',
        '선호향', '가치관', '전용제품', '퍼스널컬러', '피부호수', '문서'
    ]

    try:
        with open(jsonl_file_path, 'r', encoding='utf-8') as file:
            for line_num, line in enumerate(file, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    # JSON 파싱
                    data = json.loads(line)

                    # 필요한 필드만 추출
                    filtered_doc = {}
                    for field in fields_to_index:
                        if field in data:
                            filtered_doc[field] = data[field]

                    # product_id가 있는 경우만 추가
                    if 'product_id' in filtered_doc:
                        documents.append(filtered_doc)
                    else:
                        logging.warning(f"라인 {line_num}: product_id가 없어 건너뜁니다.")

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
    index_name="product_index",
    recreate_index=False
):
    """
    상품 데이터를 OpenSearch에 색인합니다.

    Args:
        jsonl_file_path: JSONL 파일 경로
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
    mapping = create_product_index_mapping()
    if not client.create_index_with_mapping(index_name, mapping):
        logging.error("인덱스 생성 실패")
        return False

    # 문서 로드
    logging.info("JSONL 파일에서 문서 로드 중...")
    documents = load_and_prepare_documents(jsonl_file_path)

    if not documents:
        logging.error("로드할 문서가 없습니다.")
        return False

    logging.info(f"{len(documents)}개 문서에 대해 임베딩 생성 및 색인 시작...")

    # 임베딩 생성 및 문서 준비
    documents_with_embeddings = []
    for i, doc in enumerate(documents, 1):
        # 문서 필드로 임베딩 생성
        content = doc.get('문서', '')

        # 임베딩 벡터 생성
        if content and hasattr(client, 'model') and client.model:
            doc['content_vector'] = client.model.encode(content).tolist()

        documents_with_embeddings.append(doc)

        if i % 100 == 0:
            logging.info(f"임베딩 생성 진행 중: {i}/{len(documents)}")

    # Bulk 색인
    logging.info("Bulk 색인 시작...")
    success = client.bulk_index_documents(
        index_name=index_name,
        documents=documents_with_embeddings,
        refresh=True
    )

    if success:
        logging.info(f"✅ 색인 완료! {len(documents_with_embeddings)}개 문서가 '{index_name}' 인덱스에 색인되었습니다.")

        # 인덱스 통계 확인
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
    # 설정
    JSONL_FILE = "product_data_251227.jsonl"
    INDEX_NAME = "product_index"
    RECREATE_INDEX = True  # 기존 인덱스 삭제 후 재생성

    print("=" * 60)
    print("상품 데이터 OpenSearch 색인 시작")
    print("=" * 60)
    print(f"JSONL 파일: {JSONL_FILE}")
    print(f"인덱스 이름: {INDEX_NAME}")
    print(f"인덱스 재생성: {RECREATE_INDEX}")
    print("=" * 60)

    # 색인 실행
    success = index_products_to_opensearch(
        jsonl_file_path=JSONL_FILE,
        index_name=INDEX_NAME,
        recreate_index=RECREATE_INDEX
    )

    if success:
        print("\n✅ 모든 작업이 성공적으로 완료되었습니다!")
    else:
        print("\n❌ 작업 중 오류가 발생했습니다.")
