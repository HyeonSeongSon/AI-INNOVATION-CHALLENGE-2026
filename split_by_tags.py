import json

# 지정된 태그 리스트
TARGET_TAGS = [
    "컨실러",
    "파운데이션",
    "BB&CC크림",
    "쿠션",
    "립스틱",
    "립글로스",
    "립케어&립밤",
    "립틴트",
    "아이브로우",
    "아이라이너",
    "아이섀도우",
    "브러셔",
    "브론져",
    "하이라이터",
    "네일컬러",
    "헤어컬러"
]

# 입력 파일 경로
input_file = r"C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\product_document\product_documents_tagged_v2_1_with_url_251218.jsonl"

# 출력 파일 경로
output_included = "./data/product_document/product_documents_v2_included_tags.jsonl"
output_excluded = "./data/product_document/product_documents_v2_excluded_tags.jsonl"

# 카운터
included_count = 0
excluded_count = 0

# 파일 읽고 분류하기
with open(input_file, 'r', encoding='utf-8') as infile, \
     open(output_included, 'w', encoding='utf-8') as included_file, \
     open(output_excluded, 'w', encoding='utf-8') as excluded_file:

    for line in infile:
        # 각 줄을 JSON으로 파싱
        data = json.loads(line.strip())

        # 태그 값 가져오기
        tag = data.get("태그", "")

        # 태그가 TARGET_TAGS에 포함되는지 확인
        if tag in TARGET_TAGS:
            included_file.write(line)
            included_count += 1
        else:
            excluded_file.write(line)
            excluded_count += 1

print(f"분리 완료!")
print(f"포함된 항목: {included_count}개 -> {output_included}")
print(f"제외된 항목: {excluded_count}개 -> {output_excluded}")
print(f"전체 항목: {included_count + excluded_count}개")
