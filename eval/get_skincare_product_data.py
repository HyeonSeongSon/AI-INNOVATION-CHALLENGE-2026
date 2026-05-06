import json

input_path = r"C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\eval\eval_results.jsonl"
output_path = r"C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\eval\eval_skincare_results.jsonl"

if __name__=="__main__":
    with open(input_path, "r", encoding="utf-8") as infile, \
        open(output_path, "w", encoding="utf-8") as outfile:
        
        for line in infile:
            if not line.strip():
                continue
            
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue  # 깨진 라인은 스킵
            
            # category 필터링
            if data.get("category") == "skincare":
                outfile.write(json.dumps(data, ensure_ascii=False) + "\n")

    print(f"완료: {output_path} 파일 생성")