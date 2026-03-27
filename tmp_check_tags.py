import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"
target_tags = {"파운데이션", "BB&CC크림", "쿠션", "컨실러", "파우더", "프라이머&베이스"}

results = {}
for tag in target_tags:
    results[tag] = []

with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        tag = d.get('태그', '')
        if tag in target_tags:
            results[tag].append({
                '상품명': d.get('상품명', ''),
                '한줄소개': d.get('한줄소개', '')
            })

out_path = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/tmp_tag_result.txt"
with open(out_path, 'w', encoding='utf-8') as out:
    for tag in ["파운데이션", "BB&CC크림", "쿠션", "컨실러", "파우더", "프라이머&베이스"]:
        items = results[tag]
        out.write(f"\n=== {tag} ({len(items)}개) ===\n")
        for i, item in enumerate(items, 1):
            out.write(f"  [{i}] {item['상품명']}\n")
            out.write(f"       {item['한줄소개']}\n")

print("Done")
