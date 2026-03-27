import json

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"

target_tags = {"립스틱", "립글로스", "립틴트", "립케어&립밤"}

# 특수 케이스
special_cases = {
    "[NEW 컬러 출시]센슈얼 틴티드 샤인스틱 3.5g": {
        "카테고리": "색조",
        "태그": "립메이크업",
        "서브태그": "립틴트"
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
        if product_name in special_cases:
            sc = special_cases[product_name]
            new_category = sc["카테고리"]
            new_tag = sc["태그"]
            new_subtag = sc["서브태그"]
        else:
            new_category = "색조"
            new_tag = "립메이크업"
            new_subtag = tag  # 현재 태그값 → 서브태그

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

# 검증
print("\n=== 검증 ===")
from collections import defaultdict
summary = defaultdict(int)
with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        tag = d.get('태그', '')
        subtag = d.get('서브태그', '')
        if tag == "립메이크업":
            summary[subtag] += 1

for k in sorted(summary.keys()):
    print(f"  서브태그={k}: {summary[k]}개")
