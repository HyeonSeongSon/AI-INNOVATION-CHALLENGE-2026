import json
import logging
from opensearch_hybrid import OpenSearchHybridClient
from path_utils import get_absolute_path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def export_product_id_mapping(index_name="product_index", output_file="product_id_mapping.jsonl"):
    """
    OpenSearch 인덱스에서 product_id와 벡터DB ID(_id) 매핑을 추출하여 JSONL로 저장합니다.

    Args:
        index_name: OpenSearch 인덱스 이름
        output_file: 출력할 JSONL 파일 경로

    Returns:
        bool: 성공 여부
    """
    # OpenSearch 클라이언트 초기화
    client = OpenSearchHybridClient()

    if not client.client:
        logging.error("OpenSearch 클라이언트 초기화 실패")
        return False

    try:
        # 인덱스 존재 여부 확인
        if not client.client.indices.exists(index=index_name):
            logging.error(f"인덱스 '{index_name}'가 존재하지 않습니다.")
            return False

        # 전체 문서 수 확인
        count_response = client.client.count(index=index_name)
        total_docs = count_response['count']
        logging.info(f"총 {total_docs}개의 문서를 처리합니다.")

        # Scroll API를 사용하여 모든 문서 가져오기
        scroll_size = 1000
        scroll_time = '2m'

        # 초기 검색 (product_id와 _id만 가져오기)
        search_body = {
            "query": {
                "match_all": {}
            },
            "_source": ["product_id"],  # product_id 필드만 가져오기
            "size": scroll_size
        }

        response = client.client.search(
            index=index_name,
            body=search_body,
            scroll=scroll_time
        )

        scroll_id = response['_scroll_id']
        hits = response['hits']['hits']

        # 결과를 저장할 리스트
        mappings = []
        processed = 0

        # 모든 문서 순회
        while hits:
            for hit in hits:
                doc_id = hit['_id']  # OpenSearch 내부 문서 ID
                product_id = hit['_source'].get('product_id')

                if product_id:
                    mappings.append({
                        "product_id": product_id,
                        "vector_db_id": doc_id
                    })
                    processed += 1
                else:
                    logging.warning(f"문서 ID '{doc_id}'에 product_id가 없습니다.")

            # 진행 상황 로깅
            if processed % 1000 == 0:
                logging.info(f"진행 중: {processed}/{total_docs} 문서 처리됨")

            # 다음 배치 가져오기
            response = client.client.scroll(
                scroll_id=scroll_id,
                scroll=scroll_time
            )
            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']

        # Scroll 정리
        try:
            client.client.clear_scroll(scroll_id=scroll_id)
        except Exception as e:
            logging.warning(f"Scroll 정리 실패: {e}")

        # JSONL 파일로 저장
        logging.info(f"'{output_file}'에 매핑 데이터 저장 중...")
        with open(output_file, 'w', encoding='utf-8') as f:
            for mapping in mappings:
                json_line = json.dumps(mapping, ensure_ascii=False)
                f.write(json_line + '\n')

        logging.info(f"✅ 완료! {len(mappings)}개의 product_id 매핑이 '{output_file}'에 저장되었습니다.")

        # 샘플 데이터 출력
        if mappings:
            logging.info("샘플 데이터 (처음 3개):")
            for i, mapping in enumerate(mappings[:3], 1):
                logging.info(f"  {i}. product_id: {mapping['product_id']}, vector_db_id: {mapping['vector_db_id']}")

        return True

    except Exception as e:
        logging.error(f"매핑 데이터 추출 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 설정 - 프로젝트 루트 기준 절대 경로 자동 생성
    INDEX_NAME = "product_index"
    OUTPUT_FILE = get_absolute_path("data", "product_id_mapping.jsonl")

    print("=" * 60)
    print("OpenSearch Product ID 매핑 추출")
    print("=" * 60)
    print(f"인덱스 이름: {INDEX_NAME}")
    print(f"출력 파일: {OUTPUT_FILE}")
    print("=" * 60)

    # 매핑 추출 실행
    success = export_product_id_mapping(
        index_name=INDEX_NAME,
        output_file=OUTPUT_FILE
    )

    if success:
        print("\n✅ 매핑 추출이 성공적으로 완료되었습니다!")
    else:
        print("\n❌ 매핑 추출 중 오류가 발생했습니다.")
