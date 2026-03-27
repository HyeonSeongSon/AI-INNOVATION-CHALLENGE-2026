import json, sys
sys.stdout.reconfigure(encoding='utf-8')

filepath = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/data/product_data_251231_validated.jsonl"

from collections import defaultdict
summary = defaultdict(list)

with open(filepath, 'r', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line.strip())
        if d.get('태그') == "립메이크업":
            summary[d.get('서브태그', '')].append(d.get('상품명', ''))

out_path = "c:/Users/user/Documents/GitHub/AI-INNOVATION-CHALLENGE-2026/tmp_lip_verify_result.txt"
with open(out_path, 'w', encoding='utf-8') as out:
    for subtag in ['립스틱', '립글로스', '립틴트', '립케어&립밤']:
        items = summary.get(subtag, [])
        out.write(f"\n[서브태그={subtag}] ({len(items)}개)\n")
        for name in items:
            out.write(f"  - {name}\n")

print("done")
