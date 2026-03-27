import json

# 세트 상품 판별 기준: 샴푸 태그이면서 이름에 아래 키워드 포함
SET_KEYWORDS = ["컨디셔너", "트리트먼트", "키트"]

input_path = "data/product_data_251231_validated.jsonl"
output_path = "data/product_data_251231_validated.jsonl"

TARGET_TAGS = {"샴푸", "린스&컨디셔너"}

results = []
changed = 0

with open(input_path, encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        tag = d.get("태그", "")

        if tag in TARGET_TAGS:
            name = d.get("상품명", "")

            # 서브태그 결정
            if tag == "샴푸" and any(kw in name for kw in SET_KEYWORDS):
                sub_tag = "샴푸세트"
            else:
                sub_tag = tag  # 원래 태그 값 유지

            # 필드 순서 재구성: 상품명 다음에 카테고리, 태그, 서브태그 삽입
            new_d = {}
            for k, v in d.items():
                if k == "태그":
                    new_d["카테고리"] = "헤어"
                    new_d["태그"] = "세정"
                    new_d["서브태그"] = sub_tag
                else:
                    new_d[k] = v

            results.append(new_d)
            changed += 1
        else:
            results.append(d)

with open(output_path, "w", encoding="utf-8") as f:
    for d in results:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print(f"완료: {changed}개 상품 수정")

# 검증: 수정된 샘플 출력
with open(output_path, encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        if d.get("태그") == "세정":
            fields = list(d.keys())
            print(f"필드순서: {fields[:6]}")
            print(f"카테고리={d.get('카테고리')}, 태그={d.get('태그')}, 서브태그={d.get('서브태그')}")
            print(f"상품명: {d.get('상품명')}")
            print()
            break
