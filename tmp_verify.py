import json, sys
sys.stdout.reconfigure(encoding='utf-8')

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"

check_subtags = {'파운데이션','쿠션','컨실러','파우더','프라이머&베이스','BB&CC크림','파운데이션케이스','브러쉬세트'}

out_path = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/tmp_verify_result.txt"
with open(filepath, 'r', encoding='utf-8') as f, open(out_path, 'w', encoding='utf-8') as out:
    from collections import defaultdict
    summary = defaultdict(list)
    for line in f:
        d = json.loads(line.strip())
        subtag = d.get('서브태그', '')
        cat = d.get('카테고리', '')
        tag = d.get('태그', '')
        if subtag in check_subtags:
            key = f"카테고리={cat} | 태그={tag} | 서브태그={subtag}"
            summary[key].append(d.get('상품명', ''))

    for k in sorted(summary.keys()):
        names = summary[k]
        out.write(f"\n[{k}] ({len(names)}개)\n")
        for name in names:
            out.write(f"  - {name}\n")

print("done")
