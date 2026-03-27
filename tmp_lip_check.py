import json, sys
sys.stdout.reconfigure(encoding='utf-8')

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"
out_path = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/tmp_lip_result.txt"

target_tags = {'립스틱', '립글로스', '립틴트', '립케어&립밤'}

from collections import defaultdict
summary = defaultdict(list)

with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        tag = d.get('태그', '')
        if tag in target_tags:
            cat = d.get('카테고리', '')
            subtag = d.get('서브태그', '')
            name = d.get('상품명', '')
            desc = d.get('한줄소개', '')
            key = f"{tag}"
            summary[key].append((name, desc, cat, subtag))

with open(out_path, 'w', encoding='utf-8') as out:
    for tag in ['립스틱', '립글로스', '립틴트', '립케어&립밤']:
        items = summary.get(tag, [])
        out.write(f"\n=== {tag} ({len(items)}개) ===\n")
        for i, (name, desc, cat, subtag) in enumerate(items, 1):
            out.write(f"  [{i}] {name}\n")
            out.write(f"       카테고리={cat} | 서브태그={subtag}\n")
            out.write(f"       {desc}\n")

print("done")
