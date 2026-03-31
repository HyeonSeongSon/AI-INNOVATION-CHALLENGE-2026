import json
from collections import Counter

def analyze_jsonl(file_path):
    # 각 필드의 빈도수를 저장할 Counter 객체 초기화
    categories = Counter()
    tags = Counter()
    sub_tags = Counter()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    data = json.loads(line)
                    
                    # 각 필드 존재 여부 확인 후 카운트 (get 사용으로 에러 방지)
                    if data.get("카테고리"):
                        categories[data["카테고리"]] += 1
                    
                    if data.get("태그"):
                        tags[data["태그"]] += 1
                        
                    if data.get("서브태그"):
                        sub_tags[data["서브태그"]] += 1
                        
                except json.JSONDecodeError:
                    print(f"Error: {line_num}행은 올바른 JSON 형식이 아닙니다.")

        # 결과 출력
        print("=== 필드별 데이터 집계 결과 ===")
        
        print(f"\n[카테고리 요약] (총 {len(categories)}종류)")
        for item, count in categories.most_common():
            print(f"- {item}: {count}개")

        print(f"\n[태그 요약] (총 {len(tags)}종류)")
        for item, count in tags.most_common():
            print(f"- {item}: {count}개")

        print(f"\n[서브태그 요약] (총 {len(sub_tags)}종류)")
        for item, count in sub_tags.most_common():
            print(f"- {item}: {count}개")

    except FileNotFoundError:
        print(f"Error: '{file_path}' 파일을 찾을 수 없습니다.")

if __name__=="__main__":
    file_name = r'C:\Users\user\Documents\GitHub\AI-INNOVATION-CHALLENGE-2026\data\product_data_filtered.jsonl' 
    analyze_jsonl(file_name)