import json

input_path = r"C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\test_products_selected.jsonl"  # 파일 경로 수정

product_ids = []

with open(input_path, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        
        data = json.loads(line)
        
        if data.get("카테고리") == "향수/바디":
            pid = data.get("product_id")
            if pid:
                product_ids.append(pid)


if __name__=="__main__":
    # 출력
    for pid in product_ids:
        print(pid)

    print(f"\n총 {len(product_ids)}개")