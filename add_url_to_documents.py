import json

def add_urls_to_documents():
    """
    product_crawling_251217.jsonl의 상품명과 URL을 읽어
    product_documents_tagged_251218.jsonl의 동일한 상품명에 URL을 추가
    """

    # 크롤링 데이터에서 상품명:URL 매핑 생성
    product_url_map = {}
    with open('./data/crawling_result/product_crawling_251217.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line.strip())
            product_name = data.get('상품명')
            url = data.get('url')
            if product_name and url:
                product_url_map[product_name] = url

    print(f"크롤링 데이터에서 {len(product_url_map)}개의 상품명-URL 매핑을 로드했습니다.")

    # 문서 데이터에 URL 추가
    updated_documents = []
    matched_count = 0
    unmatched_count = 0

    with open('./data/product_document/product_documents_tagged_251218.jsonl', 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line.strip())
            product_name = data.get('상품명')

            if product_name and product_name in product_url_map:
                data['url'] = product_url_map[product_name]
                matched_count += 1
            else:
                unmatched_count += 1
                if product_name:
                    print(f"매칭 실패: {product_name}")

            updated_documents.append(data)

    # 결과 저장
    output_path = './data/product_document/product_documents_with_url_251218.jsonl'
    with open(output_path, 'w', encoding='utf-8') as f:
        for doc in updated_documents:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')

    print(f"\n처리 완료:")
    print(f"- 총 문서 수: {len(updated_documents)}")
    print(f"- URL 매칭 성공: {matched_count}")
    print(f"- URL 매칭 실패: {unmatched_count}")
    print(f"- 결과 파일: {output_path}")

if __name__ == "__main__":
    add_urls_to_documents()
