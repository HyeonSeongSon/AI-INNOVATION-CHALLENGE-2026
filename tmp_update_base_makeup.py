import json

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"

target_tags = {"파운데이션", "BB&CC크림", "쿠션", "컨실러", "파우더", "프라이머&베이스"}

# 특수 케이스: 상품명 기준
special_cases = {
    "프라임 리저브 리트리니 메쉬 파운데이션 케이스": {
        "카테고리": "뷰티툴",
        "태그": "소품&도구",
        "서브태그": "파운데이션케이스"
    },
    "[피카소] FB11 밀착 베이스 메이크업 세트": {
        "카테고리": "뷰티툴",
        "태그": "브러쉬",
        "서브태그": "브러쉬세트"
    }
}

with open(filepath, 'r', encoding='utf-8') as f:
    lines_in = f.readlines()

lines_out = []
changed = 0

for line in lines_in:
    stripped = line.strip()
    if not stripped:
        lines_out.append(line)
        continue

    d = json.loads(stripped)
    tag = d.get('태그', '')
    product_name = d.get('상품명', '')

    if tag in target_tags:
        # 신규 값 결정
        if product_name in special_cases:
            sc = special_cases[product_name]
            new_category = sc["카테고리"]
            new_tag = sc["태그"]
            new_subtag = sc["서브태그"]
        else:
            new_category = "색조"
            new_tag = "베이스메이크업"
            new_subtag = tag  # 현재 태그값 → 서브태그

        # 카테고리/서브태그는 제거하고, 태그 위치에 카테고리→태그→서브태그 삽입
        new_d = {}
        for k, v in d.items():
            if k in ('카테고리', '서브태그'):
                continue
            if k == '태그':
                new_d['카테고리'] = new_category
                new_d['태그'] = new_tag
                new_d['서브태그'] = new_subtag
            else:
                new_d[k] = v

        lines_out.append(json.dumps(new_d, ensure_ascii=False) + '\n')
        changed += 1
    else:
        lines_out.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines_out)

print(f"변경된 레코드: {changed}개")

# 결과 검증
print("\n=== 검증 ===")
tag_summary = {}
with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        tag = d.get('태그', '')
        cat = d.get('카테고리', '')
        subtag = d.get('서브태그', '')
        if cat in ('색조', '뷰티툴') and subtag in ('파운데이션','쿠션','컨실러','파우더','프라이머&베이스','BB&CC크림','파운데이션케이스','브러쉬세트'):
            key = f"카테고리={cat} | 태그={tag} | 서브태그={subtag}"
            tag_summary[key] = tag_summary.get(key, 0) + 1

for k, v in sorted(tag_summary.items()):
    print(f"  {k}: {v}개")
