# loadtest — `/chat/v2/stream` 동시성 게이팅 부하테스트

18~21차 부하테스트(`c:\Users\user\Desktop\2026ai프로젝트 진행 md파일\LOAD_TEST_*.md`)의 후속.
21차까지는 프론트엔드가 쓰지 않는 plain `/chat/v2`를 대상으로 했고, 비즈니스 지표만 수집했다.
이 디렉터리의 스크립트는 실제 프론트엔드 경로인 `/chat/v2/stream`(동시성 게이팅 적용 대상)을
대상으로 하고, 인프라 레벨 지표(ECS CPU/Memory, OpenSearch 노드 상태, DB 풀 고갈 로그)도 같이 모은다.

## 사전 조건

- 부하생성은 **반드시 VPC 내부 EC2(`loadtest-chat3-ec2`, `i-0937fb4243df8baeb`)에서 실행**한다.
  로컬 Windows 머신에서 직접 실행하면 동시 220+ 연결에서 클라이언트 자체가 깨진다.
- ALB idle_timeout(660s) > graph_execution_timeout(600s) > a2a_timeout(280s) 계층이 운영값/Terraform
  코드 양쪽에서 일치하는지 먼저 확인한다(`infra/ec2/alb.tf`).
- recommend/generate ECS가 테스트하려는 인스턴스 수(예: 21차 기준 3/2)로 스케일되어 있는지 확인한다.
- 테스트 계정(`loadtest001~100@example.com`)이 DB에 존재하는지 확인한다. 비밀번호를 모르면
  DB에서 임시 비밀번호로 재설정 후 테스트, 종료 후 다시 알 수 없는 값으로 바꾸거나 그대로 둘지 결정한다.

## 실행 순서

```bash
# 1) loadtest EC2에 스크립트 배치 (scp 또는 SSM을 통한 S3 동기화)
# 2) loadtest EC2에서:
export ALB_HOST="ai-innovation-alb-105766867.ap-northeast-2.elb.amazonaws.com"
export TEST_PASSWORD="<임시 비밀번호>"
./run_chat_stream_test.sh
# → results/<RUN_ID>/ 에 raw 결과 저장, 마지막 줄에 result_dir 경로 출력

# 3) 결과 파싱 (로컬 또는 EC2 어디서나, Python만 있으면 됨)
python parse_results.py results/<RUN_ID>

# 4) (선택) OpenSearch 노드 상태 전/후 스냅샷 — 부하 시작 직전/직후에 각각 실행
./fetch_opensearch_node_stats.sh before results/<RUN_ID>
./fetch_opensearch_node_stats.sh after  results/<RUN_ID>

# 5) CloudWatch 인프라 지표 수집 (로컬에서, AWS CLI 자격증명 있는 환경)
python fetch_metrics.py --start <test_start ISO8601> --end <test_end ISO8601> \
    --output results/<RUN_ID>/metrics.json

# 6) 최종 리포트 생성
python analyze_results.py results/<RUN_ID> results/<RUN_ID>/metrics.json \
    > "c:\Users\user\Desktop\2026ai프로젝트 진행 md파일\LOAD_TEST_22차_결과_<날짜>.md"
```

`test_start`/`test_end`는 `results/<RUN_ID>/meta.env`에 기록된다.

## 정리

- 테스트 후 recommend/generate ECS를 평시 값(1/1)으로 복원
- 테스트 계정 임시 비밀번호 사용 후 Secrets Manager에 저장했다면 시크릿 삭제
- `results/`는 git에 커밋하지 않음(`.gitignore` 처리)
