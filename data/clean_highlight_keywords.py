import json
import sys
from pathlib import Path


def clean_highlight_keywords(input_path: str):
    input_file = Path(input_path)
    lines = input_file.read_text(encoding="utf-8").splitlines()
    changed_count = 0
    result_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        structured = record.get("structured")
        if isinstance(structured, dict) and isinstance(structured.get("highlight_keywords"), list):
            cleaned = [kw.lstrip("#") if isinstance(kw, str) else kw for kw in structured["highlight_keywords"]]
            if cleaned != structured["highlight_keywords"]:
                changed_count += 1
            structured["highlight_keywords"] = cleaned
        result_lines.append(json.dumps(record, ensure_ascii=False))

    input_file.write_text("\n".join(result_lines) + "\n", encoding="utf-8")
    print(f"done: {input_file.name} - {changed_count} records updated")


if __name__ == "__main__":
    targets = sys.argv[1:] or [
        "product_data_structured_skincare.jsonl",
        "product_data_structured_color_tone.jsonl",
    ]
    for path in targets:
        clean_highlight_keywords(path)
