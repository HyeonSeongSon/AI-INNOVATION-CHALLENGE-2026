"""이미지 URL 확인 스크립트"""
import json

with open('./data/crawling_result/product_crawling_251225_no_doc.jsonl', 'r', encoding='utf-8') as f:
    records = [json.loads(line) for line in f if line.strip()]

print('실패한 3개 상품의 이미지 URL 분석:\n')
for i, r in enumerate(records[:3]):
    print(f'{i+1}. 상품명: {r.get("상품명", "N/A")[:50]}')
    imgs = r.get('상품상세_이미지', [])
    print(f'   이미지 개수: {len(imgs)}')
    if imgs:
        print(f'   첫 URL: {imgs[0]}')
        # URL 특이사항 체크
        if '%' in imgs[0]:
            print('   - URL에 % 기호 포함 (URL 인코딩)')
        if '(' in imgs[0] or ')' in imgs[0]:
            print('   - URL에 괄호 포함')
        if 'cafe24' in imgs[0]:
            print('   - Cafe24 호스팅')
    print()
