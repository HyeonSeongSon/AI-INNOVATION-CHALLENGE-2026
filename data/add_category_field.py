import json
import sys
from pathlib import Path


def add_category_field(input_path: str, category_value: str):
    input_file = Path(input_path)
    lines = input_file.read_text(encoding="utf-8").splitlines()
    result_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)

        # 태그 앞에 카테고리 삽입 (dict 순서 유지)
        new_record = {}
        for key, value in record.items():
            if key == "태그":
                new_record["카테고리"] = category_value
            new_record[key] = value

        # 태그 키가 없을 경우 맨 앞에 추가
        if "카테고리" not in new_record:
            new_record = {"카테고리": category_value, **record}

        result_lines.append(json.dumps(new_record, ensure_ascii=False))

    input_file.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    print(f"done: {input_file.name} - category={category_value}, {len(result_lines)} records")


if __name__ == "__main__":
    targets = [
        ("product_data_structured_color_tone.jsonl", "색조"),
        ("product_data_structured_skincare.jsonl", "스킨케어"),
    ]
    for path, category in targets:
        add_category_field(path, category)
