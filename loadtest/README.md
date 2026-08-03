# loadtest — `/chat/v2/stream` 동시성 게이팅 부하테스트

18~39차 부하테스트에 사용한 스크립트.
21차까지는 프론트엔드가 쓰지 않는 plain `/chat/v2`를 대상으로 비즈니스 지표만 수집했다.
이 디렉터리의 스크립트는 실제 프론트엔드 경로인 `/chat/v2/stream`(동시성 게이팅 적용 대상)을
대상으로 하고, 인프라 레벨 지표(ECS CPU/Memory, OpenSearch 노드 상태, DB 풀 고갈 로그)도 같이 모은다.

**최종 결과(39차)**: 동시 100 요청 완료율 **100%**, p50 202.5s / p99 323.3s, 실패·유실 0건.

## 사전 조건

- 부하생성은 **반드시 VPC 내부 loadtest EC2에서 실행**한다. 로컬 Windows 머신에서 직접
  실행하면 동시 220+ 연결에서 클라이언트 자체가 깨진다(22차 이전 확인).
- ALB idle_timeout(660s) > graph_execution_timeout(600s) > a2a_timeout(280s) 계층이 운영값/Terraform
  코드 양쪽에서 일치하는지 먼저 확인한다(`infra/ec2/alb.tf`).
- 테스트 계정(`loadtest001~100@example.com`)이 DB에 존재하는지 확인한다. 비밀번호를 모르면
  DB에서 임시 비밀번호로 재설정 후 테스트, 종료 후 다시 알 수 없는 값으로 바꾸거나 그대로 둘지 결정한다.

> **인스턴스 ID·ALB DNS·CloudFront 도메인은 재배포마다 바뀐다.** 매번 아래로 확인한다.
> `fetch_metrics.py`의 `DEFAULT_OPENSEARCH_INSTANCE_ID` /
> `DEFAULT_OPENSEARCH_API_INSTANCE_ID` 기본값도 같은 이유로 낡을 수 있으니, 맞지 않으면
> 인자로 넘긴다.
>
> ```bash
> aws ssm describe-instance-information \
>   --query 'InstanceInformationList[].{Id:InstanceId,Name:ComputerName}' --output table
> aws elbv2 describe-load-balancers --names ai-innovation-alb \
>   --query 'LoadBalancers[0].DNSName' --output text
> aws cloudfront list-distributions \
>   --query 'DistributionList.Items[0].DomainName' --output text
> ```

## 인프라 사전 스케일업

39차 검증 구성은 **ECS recommend 3 / generate 2 / crm 1, opensearch-api ASG 2대**다.
평시에는 비용 때문에 1/1/1로 내려두므로 테스트 전에 올리고 끝나면 되돌린다.

```bash
# 1) ECS — recommend 3 / generate 2
aws ecs update-service --cluster ai-innovation-cluster \
  --service ai-innovation-recommend --desired-count 3
aws ecs update-service --cluster ai-innovation-cluster \
  --service ai-innovation-generate  --desired-count 2

# 2) opensearch-api ASG — Terminate를 먼저 막지 않으면 TargetTracking 스케일인이
#    수 분 내로 증설을 되돌린다 (37차에서 확립).
#    'ScaleIn'은 유효한 프로세스명이 아니므로 반드시 'Terminate'를 중단시킨다.
aws autoscaling suspend-processes \
  --auto-scaling-group-name ai-innovation-asg-opensearch-api \
  --scaling-processes Terminate
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name ai-innovation-asg-opensearch-api \
  --desired-capacity 2
# 2대 모두 InService 확인 후 진행
```

## 실행 순서

```bash
# 1) loadtest EC2에 스크립트 배치 (scp 또는 SSM을 통한 S3 동기화)
# 2) loadtest EC2에서:
export CF_HOST="<CloudFront 도메인>"    # 로그인용 (HTTPS) — 필수
export ALB_HOST="<ALB DNS>"             # 부하용 (HTTP)   — 필수
export TEST_PASSWORD="<임시 비밀번호>"   # 필수
./run_chat_stream_test.sh
# → results/<RUN_ID>/ 에 raw 결과 저장, 마지막 줄에 result_dir 경로 출력

# 3) 결과 파싱 (로컬 또는 EC2 어디서나, Python만 있으면 됨)
python parse_results.py results/<RUN_ID>

# 4) (선택) OpenSearch 노드 상태 전/후 스냅샷 — 부하 시작 직전/직후에 각각 실행
./fetch_opensearch_node_stats.sh before results/<RUN_ID>
./fetch_opensearch_node_stats.sh after  results/<RUN_ID>

# 5) CloudWatch 인프라 지표 수집 (로컬에서, AWS CLI 자격증명 있는 환경)
python fetch_metrics.py --start <test_start ISO8601> --end <test_end ISO8601> \
    --opensearch-instance-id <opensearch EC2 ID> \
    --opensearch-api-instance-id <opensearch-api EC2 ID> \
    --output results/<RUN_ID>/metrics.json

# 6) 최종 리포트 생성
python analyze_results.py results/<RUN_ID> results/<RUN_ID>/metrics.json \
    > "<진행 md 디렉터리>/LOAD_TEST_<N>차_결과_<날짜>.md"
```

`test_start`/`test_end`는 `results/<RUN_ID>/meta.env`에 기록된다.

### 선택 환경변수

| 변수 | 기본값 | 의미 |
|---|:---:|---|
| `CONCURRENCY` | 100 | 동시 채팅 요청 수 |
| `LOGIN_BATCH_SIZE` | 8 | 로그인 배치 크기 (`rate_limit_login_max_requests=10/60s` 대비 여유) |
| `LOGIN_BATCH_SLEEP` | 65 | 배치 간 대기 초 (`rate_limit_login_window_seconds=60` 대비 여유) |
| `CURL_TIMEOUT` | 700 | graph_execution_timeout(600) + ALB idle_timeout(660) 대비 여유 |

### 로그인/부하 경로가 나뉘는 이유 (22차 확립)

스크립트가 자동으로 처리하지만, 직접 하네스를 만들 때 알아야 한다.

1. **로그인은 CloudFront(HTTPS)** — `access_token` 쿠키가 `Secure`라 HTTP 로그인은 curl이
   쿠키 저장을 거부한다
2. **채팅은 ALB(HTTP) 직접** — CloudFront `origin_read_timeout`(60s)에 기대지 않기 위해
   부하 경로에서는 엣지를 우회한다
3. 두 호스트의 쿠키 도메인이 달라 자동 매칭이 안 되므로, 로그인 후 `access_token` 값만
   추출해 `Cookie` 헤더로 직접 첨부한다
4. **로그인은 8명씩 65초 간격 배치** 후에야 `xargs -P 100`으로 동시 100개를 쏜다 —
   배치를 건너뛰면 로그인 단계에서 429가 나 테스트가 성립하지 않는다

## 정리

- ECS recommend/generate를 평시 값(1/1)으로 복원
- opensearch-api ASG `desired-capacity` 1로 복원 후 **`resume-processes`로 Terminate 재개**
  (중단된 채로 두면 이후 스케일인이 영영 동작하지 않는다)
- 테스트 계정 임시 비밀번호 사용 후 Secrets Manager에 저장했다면 시크릿 삭제
- `results/`는 git에 커밋하지 않음(`.gitignore` 처리)
