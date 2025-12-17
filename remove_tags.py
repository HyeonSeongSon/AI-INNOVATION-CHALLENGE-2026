import json
import re
import time
from datetime import datetime

# 입력 및 출력 파일 경로
input_file = "./data/crawling_result/product_crawling_tagged.jsonl"
output_file = "./data/crawling_result/product_crawling_251217.jsonl"

def fix_json_string(json_str):
    """JSON 문자열의 trailing comma 및 기타 문제를 수정"""
    # 배열이나 객체 끝의 쉼표 제거: ,] 또는 ,} 패턴을 ] 또는 }로 변경
    json_str = re.sub(r',\s*]', ']', json_str)
    json_str = re.sub(r',\s*}', '}', json_str)

    # 배열 시작 부분의 불필요한 공백 제거: [ " 패턴을 [" 로 변경
    json_str = re.sub(r'\[\s+\"', '[\"', json_str)

    # URL 파라미터 내에 다른 URL이 섞인 경우 제거
    # 예: ?param=value&resize=1100:https://other.com/file.jpg1100&...
    # -> ?param=value&resize=1100:1100&...
    json_str = re.sub(r':https://[^"&]*?\.jpg(\d+)', r':\1', json_str)

    return json_str

# 시작 시간 기록
start_time = time.time()
start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print(f"{'='*60}")
print(f"작업 시작 시간: {start_datetime}")
print(f"{'='*60}\n")

# 전체 라인 수 먼저 계산
print("전체 파일 크기 확인 중...")
with open(input_file, 'r', encoding='utf-8') as f:
    total_lines = sum(1 for line in f if line.strip())
print(f"총 {total_lines}개 항목 발견\n")

# 파일 읽기 및 tags 제거
processed_count = 0
error_count = 0
fixed_count = 0

print("처리 시작...\n")

with open(input_file, 'r', encoding='utf-8') as infile, \
     open(output_file, 'w', encoding='utf-8') as outfile:

    for line_num, line in enumerate(infile, 1):
        line = line.strip()
        if not line:  # 빈 줄 건너뛰기
            continue

        # 진행률 표시 (10개마다)
        if line_num % 10 == 0:
            progress = (line_num / total_lines) * 100
            elapsed = time.time() - start_time
            print(f"진행: {line_num}/{total_lines} ({progress:.1f}%) | "
                  f"성공: {processed_count} | 수정: {fixed_count} | 실패: {error_count} | "
                  f"경과 시간: {elapsed:.1f}초")

        try:
            # 각 줄을 JSON으로 파싱
            data = json.loads(line)

        except json.JSONDecodeError as e:
            # 파싱 실패시 trailing comma 수정 후 재시도
            try:
                fixed_line = fix_json_string(line)
                data = json.loads(fixed_line)
                fixed_count += 1
            except json.JSONDecodeError as e2:
                error_count += 1
                print(f"\n[오류] 라인 {line_num}: {str(e2)[:50]}...")
                continue

        # tags 키가 있으면 제거
        if 'tags' in data:
            del data['tags']

        # 수정된 데이터를 JSONL 형식으로 저장
        outfile.write(json.dumps(data, ensure_ascii=False) + '\n')
        processed_count += 1

# 종료 시간 계산
end_time = time.time()
end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
total_time = end_time - start_time

print(f"\n{'='*60}")
print(f"작업 완료!")
print(f"{'='*60}")
print(f"종료 시간: {end_datetime}")
print(f"총 소요 시간: {total_time:.2f}초 ({total_time/60:.2f}분)")
print(f"\n[결과 요약]")
print(f"  - 전체 항목: {total_lines}개")
print(f"  - 성공 처리: {processed_count}개 ({(processed_count/total_lines*100):.1f}%)")
print(f"  - 자동 수정: {fixed_count}개")
print(f"  - 실패 항목: {error_count}개")
print(f"\n생성된 파일: {output_file}")
print(f"{'='*60}")
