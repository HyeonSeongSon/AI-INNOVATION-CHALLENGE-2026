import json
import sys
from pathlib import Path


def remove_ingredient_quality(input_path: str, output_path: str = None):
    input_file = Path(input_path)
    output_file = Path(output_path) if output_path else input_file

    lines = input_file.read_text(encoding="utf-8").splitlines()
    removed_count = 0
    result_lines = []

    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        # 최상위 레벨
        if "ingredient_quality" in record:
            del record["ingredient_quality"]
            removed_count += 1
        # structured 중첩 객체
        if isinstance(record.get("structured"), dict) and "ingredient_quality" in record["structured"]:
            del record["structured"]["ingredient_quality"]
            removed_count += 1
        result_lines.append(json.dumps(record, ensure_ascii=False))

    output_file.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    print(f"완료: {removed_count}개 레코드에서 ingredient_quality 제거 → {output_file}")


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "product_data_structured_skincare.jsonl",
    ]
    for path in targets:
        remove_ingredient_quality(path)
