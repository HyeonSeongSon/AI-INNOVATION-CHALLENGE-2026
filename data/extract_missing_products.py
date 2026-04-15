import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = Path(__file__).parent

V3_FILES = [
    "v3_product_data_rewritten_skincare.jsonl",
    "v3_product_data_rewritten_living_supplies.jsonl",
    "v3_product_data_rewritten_inner_beauty.jsonl",
    "v3_product_data_rewritten_fragrance_body.jsonl",
    "v3_product_data_rewritten_hair.jsonl",
    "v3_product_data_rewritten_color_tone.jsonl",
    "v3_product_data_rewritten_beauty_tool.jsonl",
]

SOURCE_FILE = "product_data.jsonl"
OUTPUT_FILE = "product_data_missing_from_v3.jsonl"


def load_product_ids(filepath: Path) -> set[str]:
    ids = set()
    with open(filepath, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                pid = obj.get("product_id")
                if pid:
                    ids.add(pid)
            except json.JSONDecodeError as e:
                print(f"  [경고] {filepath.name} 줄 {lineno} JSON 파싱 오류: {e}", file=sys.stderr)
    return ids


def main():
    # 1. v3 파일들의 product_id 수집
    v3_ids: set[str] = set()
    for fname in V3_FILES:
        fpath = DATA_DIR / fname
        if not fpath.exists():
            print(f"[경고] 파일 없음: {fname}", file=sys.stderr)
            continue
        ids = load_product_ids(fpath)
        print(f"  {fname}: {len(ids)}개 ID 로드")
        v3_ids |= ids

    print(f"\nv3 파일 전체 고유 product_id 수: {len(v3_ids)}")

    # 2. source 파일에서 v3에 없는 항목 추출
    source_path = DATA_DIR / SOURCE_FILE
    output_path = DATA_DIR / OUTPUT_FILE

    missing = []
    total = 0
    with open(source_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [경고] {SOURCE_FILE} 줄 {lineno} JSON 파싱 오류: {e}", file=sys.stderr)
                continue
            total += 1
            pid = obj.get("product_id")
            if pid not in v3_ids:
                missing.append(obj)

    # 3. 결과 저장
    with open(output_path, "w", encoding="utf-8") as f:
        for obj in missing:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"\n[결과]")
    print(f"  원본 총 레코드 수:   {total}")
    print(f"  v3에 포함된 레코드:  {total - len(missing)}")
    print(f"  v3에 없는 레코드:    {len(missing)}")
    print(f"  출력 파일: {output_path}")


if __name__ == "__main__":
    main()
