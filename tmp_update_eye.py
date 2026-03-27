import json

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"

# 아이 메이크업 태그 전체
eye_tags = {"마스카라", "아이라이너", "아이브로우", "아이래쉬", "아이프라이머", "아이섀도우"}

# 브러쉬로 분류할 상품명 (→ 뷰티툴 / 브러쉬 / 아이브러쉬)
brush_names = {
    "[피카소꼴레지오니] 305 아이라이너",
    "[피카소꼴레지오니] 401 아이라이너",
    "01 아이브로우 브러쉬",
    "[피카소] 315 애교살 포인트 아이섀도우",
    "[피카소꼴레지오니] 207A 아이섀도우",
    "[피카소꼴레지오니] 19 아이섀도우",
    "[피카소꼴레지오니] 215 아이섀도우",
}

# 속눈썹으로 분류할 상품명 (→ 뷰티툴 / 소품&도구 / 속눈썹)
lash_names = {
    "컴팩트 아이래쉬 컬러",
    "[피카소] 속눈썹 접착제 튜브(클리어/다크)",
}

with open(filepath, 'r', encoding='utf-8') as f:
    lines_in = f.readlines()

lines_out = []
counts = {"아이메이크업": 0, "브러쉬": 0, "속눈썹": 0, "skip": 0}

for line in lines_in:
    stripped = line.strip()
    if not stripped:
        lines_out.append(line)
        continue

    d = json.loads(stripped)
    tag = d.get('태그', '')
    name = d.get('상품명', '')

    if tag not in eye_tags:
        lines_out.append(line)
        counts["skip"] += 1
        continue

    if name in brush_names:
        new_category = "뷰티툴"
        new_tag = "브러쉬"
        new_subtag = "아이브러쉬"
        counts["브러쉬"] += 1
    elif name in lash_names:
        new_category = "뷰티툴"
        new_tag = "소품&도구"
        new_subtag = "속눈썹"
        counts["속눈썹"] += 1
    else:
        new_category = "색조"
        new_tag = "아이메이크업"
        new_subtag = tag  # 현재 태그값 → 서브태그
        counts["아이메이크업"] += 1

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

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines_out)

print(f"아이메이크업 변경: {counts['아이메이크업']}개")
print(f"브러쉬(아이브러쉬) 변경: {counts['브러쉬']}개")
print(f"소품&도구(속눈썹) 변경: {counts['속눈썹']}개")

# 검증
print("\n=== 검증 ===")
from collections import defaultdict
summary = defaultdict(list)
with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        cat = d.get('카테고리', '')
        tag = d.get('태그', '')
        subtag = d.get('서브태그', '')
        if tag in ("아이메이크업", "브러쉬", "소품&도구") and cat in ("색조", "뷰티툴"):
            summary[f"{cat}|{tag}|{subtag}"].append(d.get('상품명', ''))

with open("tmp_eye_update_result.txt", 'w', encoding='utf-8') as out:
    for key in sorted(summary.keys()):
        items = summary[key]
        cat, tag, subtag = key.split("|")
        out.write(f"\n[{cat} > {tag} > {subtag}] ({len(items)}개)\n")
        for name in items:
            out.write(f"  - {name}\n")

print("결과 파일 저장 완료: tmp_eye_update_result.txt")
