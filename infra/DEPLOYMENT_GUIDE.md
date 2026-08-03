# AWS 배포 가이드 — AWS 서비스 생성부터 GitHub Actions 자동 배포까지

> 대상 아키텍처: ECS Fargate(5 FastAPI 서비스) + EC2(PostgreSQL / OpenSearch) + ALB + S3/CloudFront
> 리전: `ap-northeast-2` (서울) · 프로젝트 접두사: `ai-innovation`
> IaC 위치: [infra/bootstrap/](bootstrap/) (state·OIDC·**ECR**), [infra/ec2/](ec2/) (운영 인프라)

이 문서는 **0에서 운영 배포까지** 순서대로 따라갈 수 있는 런북이다. 각 단계는 "왜"와
"정확한 명령어"를 함께 적었다. 명령어는 Windows PowerShell / Git Bash / Linux 셸 모두에서
동작하도록 표기했고, 차이가 있으면 별도로 명시한다.

---

## 1. 사전 준비물

| 항목 | 설명 |
|------|------|
| AWS 계정 | 결제 활성화. IAM 관리자 권한 사용자 또는 SSO |
| AWS CLI v2 | `aws --version` ≥ 2.x. `aws configure`로 자격증명 등록 |
| Terraform | `terraform version` ~1.9 (워크플로가 `~1.9` 사용) |
| Docker | 로컬 이미지 빌드 테스트용 (선택) |
| GitHub 저장소 | 이 리포가 GitHub에 push되어 있어야 함 |
| 도메인 (선택) | HTTPS·CloudFront용. 없으면 ALB DNS로 HTTP 접속 |

설치 확인:

```bash
aws sts get-caller-identity   # 계정 ID·ARN 확인 → 이후 <ACCOUNT_ID>로 사용
terraform version
```

---

## 2. 배포 전체 흐름 한눈에

```
[1회성 부트스트랩]
  Phase 3  bootstrap apply  → S3(state) + DynamoDB(lock) + OIDC Provider + IAM Role + ECR 레포(5개)
  Phase 4  GitHub Secrets/Variables 등록

[최초 인프라 + 앱 배포]
  Phase 5  ec2 인프라 apply  → VPC·NAT·ALB·EC2·ECS·Secrets (이미지 push 후)
  Phase 6  데이터 EC2 코드 배포 (SSM) → DB API / OpenSearch API 기동   ※ CI 자동
  Phase 7  데이터 파이프라인 (인덱스·스키마 셋업)
  Phase 8  ECS 서비스 기동 확인 + admin 시드 검증

[정상 운영]
  Phase 9  프론트엔드(S3+CloudFront)                                  ※ CI 자동
  Phase 10 도메인 + HTTPS(ACM)
  Phase 11 이후 배포는 main push → GitHub Actions 전자동
```

### 알아둘 배포 구조 3가지

Phase 5 이후를 이해하려면 아래 3가지를 먼저 알아두면 좋다.

| 구조 | 설명 |
|------|------|
| **단일 이미지 + 서비스별 `command`** | 5개 FastAPI 서비스가 같은 이미지를 쓰고, 실행할 서버는 ECS task definition의 `command`로 분기한다([ecs.tf](ec2/ecs.tf) `command = ["uvicorn", "servers.*:app", ...]`). 앱 코드는 이미지에 포함된다([backend/Dockerfile](../backend/Dockerfile) `COPY backend/ /app/`) — ECS에는 볼륨 마운트가 없기 때문이다. |
| **데이터 EC2는 SSM으로 자동 배포** | `database/`·`opensearch/` 코드는 CI가 tar.gz로 묶어 S3 deploy 버킷에 올리고(`package-data-services` 잡), SSM `send-command`로 EC2에 내려받아 기동한다(`deploy-data-services` 잡). 수동 접속은 장애 대응 시에만 필요하다. |
| **프론트엔드도 CI가 배포** | S3+CloudFront는 [cloudfront.tf](ec2/cloudfront.tf)에 정의돼 있고, 빌드·업로드·캐시 무효화는 `deploy-frontend` 잡이 수행한다. |

> ECR 레포 5개는 `infra/bootstrap/ecr.tf`에 있다. bootstrap은 CI/CD 파이프라인 자체의 전제
> 리소스(S3 state, DynamoDB lock, OIDC, IAM Role)를 담는 계층이며 ECR도 같은 범주다 —
> Phase 3의 `terraform apply` 한 번으로 ECR까지 생성되므로 이미지 push 순서 문제가 없다.

---

## 3. Phase 3 — 부트스트랩 (state 백엔드 + GitHub OIDC)

**최초 1회만, 로컬에서 수동 실행한다.** state를 저장할 S3 버킷 자체는 Terraform state로
관리할 수 없으므로(닭-달걀) 부트스트랩은 로컬 state로 만든다.

### 3-1. 변수 입력

[infra/bootstrap/terraform.tfvars](bootstrap/terraform.tfvars)의 GitHub 정보를 실제 값으로 수정:

```hcl
aws_region   = "ap-northeast-2"
project_name = "ai-innovation"
github_org  = "son"                          # ← 본인 GitHub 사용자/조직명
github_repo = "AI-INNOVATION-CHALLENGE-2026"
```

> **주의**: OIDC 신뢰 조건이 `repo:<org>/<repo>:ref:refs/heads/main`이므로 org/repo가 정확해야
> GitHub Actions가 AWS 역할을 assume할 수 있다.

### 3-2. apply

```bash
cd infra/bootstrap
terraform init
terraform apply        # 리소스 검토 후 yes
terraform output       # 아래 3개 값 확인 → GitHub에 등록
```

출력값:

| output | 용도 |
|--------|------|
| `github_actions_role_arn` | GitHub Secret `AWS_ROLE_ARN` |
| `terraform_state_bucket` | `ai-innovation-terraform-state` (ec2/backend.tf와 일치 확인) |
| `terraform_lock_table` | `ai-innovation-terraform-lock` |
| `ecr_registry` | ECR 레지스트리 URI (참고용 — deploy.yml이 account ID로 자동 구성) |
| `ecr_repository_urls` | 서비스별 ECR 레포 URI (참고용) |

> **OIDC Provider 이미 존재 시**: 계정에 GitHub OIDC Provider가 이미 있으면 apply가 "이미 존재"
> 오류를 낸다. [main.tf](bootstrap/main.tf)의 `data "aws_iam_openid_connect_provider" "github"`
> `count`를 `1`로 바꾸고 `resource` 블록을 제거한 뒤, IAM Role의 `Federated` 참조를
> `data....arn`으로 바꾼다.

---

## 4. Phase 4 — GitHub Secrets / Variables 등록

리포 → Settings → Secrets and variables → Actions.

### 4-1. 시크릿 값 먼저 생성

```bash
openssl rand -hex 32   # internal_token 용
openssl rand -hex 32   # jwt_secret 용 (위와 다른 값)
```

PowerShell만 있는 경우:

```powershell
-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })
```

### 4-2. Secrets (암호화 — 민감 정보)

| Secret 이름 | 값 |
|-------------|-----|
| `AWS_ROLE_ARN` | Phase 3 `github_actions_role_arn` |
| `POSTGRES_PASSWORD` | 강력한 DB 비밀번호 |
| `INTERNAL_TOKEN` | `openssl rand -hex 32` 결과 |
| `JWT_SECRET` | `openssl rand -hex 32` 결과(다른 값) |
| `OPENAI_API_KEY` | `sk-...` |
| `ANTHROPIC_API_KEY` | Claude 사용 시. 안 쓰면 빈 값 |
| `ALLOWED_ORIGINS` | 프론트 도메인 (예: `https://app.example.com`). 미정이면 임시로 ALB DNS |
| `ADMIN_SEED_EMAIL` | **최초 1회만**. 시드 후 삭제 |
| `ADMIN_SEED_PASSWORD` | **최초 1회만**. 8자+ 대/소문자+숫자 |

### 4-3. Variables (비민감 — 모델명 등)

| Variable 이름 | 값 |
|---------------|-----|
| `CHATGPT_MODEL_NAME` | `gpt-5-mini` |
| `PARSER_MODEL_NAME` | `gpt-5-nano` |

> `deploy.yml`은 `env.AWS_REGION=ap-northeast-2`, `env.PROJECT_NAME=ai-innovation`을 하드코딩으로
> 갖고 있어 추가 등록 불필요. `TF_VAR_ecr_registry`는 워크플로가 계정 ID를 조회해 자동 구성한다.

### 4-4. Admin 시드는 첫 배포 후 즉시 회수

`ADMIN_SEED_EMAIL/PASSWORD`는 첫 배포로 admin 계정을 만든 직후
**GitHub Secret에서 삭제**하고, 다음 배포에서 Secrets Manager 시크릿이 사라지도록 한다
([secrets.tf](ec2/secrets.tf): 빈 값이면 `count=0`으로 즉시 삭제).

---

## 5. Phase 5 — 최초 인프라 + 이미지 배포

여기서부터 **GitHub Actions로 전자동**이 가능하다.

### 5-A. (권장) GitHub Actions로 배포

```bash
git add backend/Dockerfile infra/ec2/ecs.tf infra/DEPLOYMENT_GUIDE.md
git commit -m "fix: ECS 이미지 코드 포함 및 서비스별 command 지정"
git checkout main && git merge son_branch   # main에 반영
git push origin main
```

`deploy.yml`이 트리거되어:
1. `build-and-push` — `backend/Dockerfile`로 단일 이미지 빌드 → 5개 ECR 레포에 태그/푸시
   (태그: `github.sha`, `latest`)
2. `terraform` — `infra/ec2` apply. VPC·NAT·VPC Endpoints·ALB·EC2(DB/OpenSearch)·ECS·
   Secrets Manager 전부 생성. 이미지가 이미 ECR에 있으므로 ECS 태스크가 정상 기동.

진행 상황: 리포 → Actions 탭. terraform job 로그 끝에 outputs(ALB DNS 등) 출력.

> EC2 user_data(PostgreSQL/OpenSearch 설치)는 부팅 후 5~10분 소요. terraform apply 자체는
> EC2 "실행 중"까지만 기다리고 끝나므로, 데이터 서버 완전 준비는 비동기로 진행된다.

### 5-B. (대안) 로컬에서 수동 배포

GitHub Actions 없이 검증하려면:

```bash
# 1) 이미지 빌드 & 푸시
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com"
aws ecr get-login-password --region ap-northeast-2 \
  | docker login --username AWS --password-stdin "$REGISTRY"

docker build -f backend/Dockerfile -t "$REGISTRY/ai-innovation-backend:latest" .
for SVC in backend crm recommend generate data-registration; do
  docker tag "$REGISTRY/ai-innovation-backend:latest" "$REGISTRY/ai-innovation-$SVC:latest"
  docker push "$REGISTRY/ai-innovation-$SVC:latest"
done

# 2) 인프라 apply (시크릿은 tfvars 또는 TF_VAR_*로)
cd infra/ec2
cp terraform.tfvars.example terraform.tfvars   # 값 채우기 (시크릿 포함, .gitignore 확인)
terraform apply \
  -var="ecr_registry=$REGISTRY" \
  -var="ecr_image_tag=latest"
```

> `terraform.tfvars`에는 실제 시크릿이 들어가므로 **반드시 `.gitignore`에 포함**되어 있어야 한다
> (루트 `.gitignore` 확인). CI 경로(5-A)는 tfvars 없이 `TF_VAR_*` 환경변수만 쓰므로 더 안전하다.

---

## 6. Phase 6 — 데이터 EC2에 앱 코드 배포 (SSM)

Database API(8020)·OpenSearch API(8010) 앱 코드 배포는 **CI가 자동으로 수행한다.**
직접 할 일은 없고, 아래는 무슨 일이 일어나는지와 실패했을 때 어떻게 보는지다.

### 6-0. CI가 자동으로 하는 일

`deploy.yml`의 두 잡이 순서대로 처리한다.

| 잡 | 하는 일 |
|---|---|
| `package-data-services` | `database/`·`opensearch/`·`data/`를 tar.gz로 묶어 S3 deploy 버킷(`ai-innovation-deploy`)에 업로드 |
| `deploy-data-services` | 각 EC2의 user_data 완료를 폴링해 기다린 뒤, SSM `send-command`로 tar.gz를 내려받아 전개 → `pip install` → `.env` 생성 → `init/*.sql` 적용 → `systemctl restart db-api` → `seed_products.py` 시드 |

EC2는 프라이빗 서브넷·키페어 없음이라 CI도 SSH가 아닌 **SSM `send-command`**를 쓴다.
S3 Gateway Endpoint가 있어 tar.gz 전송에 NAT 비용이 들지 않는다.

> `deploy-data-services`는 `/var/log/user-data-complete` 파일을 폴링해 EC2 초기화 완료를
> 기다린다(DB 최대 20분, OpenSearch 최대 40분). 최초 배포에서 이 단계가 오래 걸리는 건 정상이다.

### 6-1. 실패 시 — 인스턴스 ID 확인 & 수동 접속

```bash
aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=ai-innovation-ec2-db,ai-innovation-ec2-opensearch" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value, InstanceId]' \
  --output table

aws ssm start-session --target <INSTANCE_ID>   # 세션 매니저 플러그인 필요
```

> SSM이 안 되면: ① EC2에 `AmazonSSMManagedInstanceCore` 롤이 붙어 있는지([ec2.tf](ec2/ec2.tf)에
> 이미 구성됨), ② SSM용 VPC Endpoint(`ssm`, `ssmmessages`, `ec2messages`)가 필요할 수 있다.
> 현재 vpc_endpoints.tf에는 SSM 엔드포인트가 없으므로, NAT를 통해 SSM에 연결된다(프라이빗+NAT면 동작).
> NAT만으로 SSM이 안 붙으면 SSM 3종 Interface Endpoint를 추가한다.

### 6-2. DB EC2 상태 확인 (db EC2 세션 안에서)

```bash
sudo -i
tail -n 30 /var/log/user-data.log          # 초기화 로그
systemctl status postgresql --no-pager
systemctl status db-api --no-pager
journalctl -u db-api -n 50 --no-pager      # 앱이 죽는 경우 원인
curl -sf http://localhost:8020/health && echo " DB API OK"
```

### 6-3. OpenSearch EC2 상태 확인 (opensearch EC2 세션 안에서)

```bash
sudo -i
systemctl status opensearch --no-pager
curl -sf http://localhost:9200/_cluster/health && echo " OpenSearch OK"
systemctl status opensearch-api --no-pager
journalctl -u opensearch-api -n 50 --no-pager
curl -sf http://localhost:8010/health && echo " OpenSearch API OK"
```

> **코드를 다시 내려받아야 한다면** CI와 동일하게 S3 deploy 버킷에서 받는다 — git clone이
> 아니다. 예: `aws s3 cp s3://ai-innovation-deploy/database.tar.gz /tmp/ && tar -xzf
> /tmp/database.tar.gz -C /opt/db-api && systemctl restart db-api`.
> 정상 경로는 워크플로를 재실행하는 것이고, 아래는 CI가 막혔을 때의 우회 수단이다.

---

## 7. Phase 7 — 데이터 파이프라인 (인덱스 / 스키마 셋업)

대부분 CI가 이미 처리한다. 남는 건 **최초 구축 때의 상품 색인**뿐이다.

| 항목 | 누가 | 비고 |
|---|---|---|
| DB 스키마 (`init/*.sql`) | CI (`deploy-data-services`) | 매 배포마다 멱등 적용 |
| 상품 시드 (`seed_products.py`) | CI (`deploy-data-services`) | 〃 |
| 금칙 문장 색인 (`index_forbidden.sh`) | CI (`deploy-data-services`) | 〃 |
| 스냅샷 복원 (`restore_or_skip.sh`) | CI | 1차 인덱스가 비었을 때만 복원, 평시 스킵 |
| **상품 인덱스 최초 구축** | **수동 (아래)** | OpenSearch는 보존 EBS(`/data/opensearch`)의 라이브 데이터를 그대로 쓰므로 최초 1회만 |

최초 구축이라 상품 인덱스가 비어 있다면 opensearch EC2에서 실행한다:

```bash
cd /opt/opensearch-api
venv/bin/python setup_opensearch.py               # 인덱스/검색 파이프라인 셋업
venv/bin/python run_indexing_pipeline.py          # v3 카테고리 색인 (skincare가 인덱스 생성 → 선행 필수)
venv/bin/python index_products_v4_multivector.py  # v4 멀티벡터 색인 — 앱의 1차 인덱스
```

> 앱이 실제 검색에 쓰는 1차 인덱스는 `product_v4_combined`(v4 멀티벡터)다. 임베딩 모델
> (`KURE-v1`) 다운로드가 필요하면 OpenSearch EC2의 아웃바운드(NAT)로 받는다.
>
> **주의**: 이미 운영 중인 클러스터에 재색인을 돌리면 **라이브 등록분이 덮여 소실될 수 있다.**
> 재해 복구 시에는 재색인이 아니라 `restore_or_skip.sh`(S3 최신 스냅샷)를 쓴다.

---

## 8. Phase 8 — 기동 확인 + admin 시드 검증

### 8-1. ECS 서비스 상태

```bash
aws ecs list-services --cluster ai-innovation-cluster
for SVC in backend crm recommend generate data-registration; do
  aws ecs describe-services --cluster ai-innovation-cluster \
    --services ai-innovation-$SVC \
    --query 'services[0].{name:serviceName,running:runningCount,desired:desiredCount}' \
    --output table
done
```

`running == desired == 1`이면 정상. 0이면 태스크가 죽는 중 → CloudWatch 로그 확인:

```bash
aws logs tail /ecs/ai-innovation --follow --format short
```

### 8-2. ALB 헬스 & 외부 접속

```bash
ALB=$(cd infra/ec2 && terraform output -raw alb_dns_name)
curl -i "http://$ALB/health"      # 200 기대 (Target Group health_check path=/health)
```

### 8-3. admin 시드 확인 후 회수

CloudWatch에서 `admin_seeded` 로그 확인 → admin 로그인 테스트 → 그다음:

1. GitHub Secret `ADMIN_SEED_EMAIL`, `ADMIN_SEED_PASSWORD` **삭제**
2. main에 빈 커밋이나 다음 배포 → `terraform`이 빈 값을 받아 Secrets Manager 시크릿
   `ai-innovation/admin-seed-*`를 `count=0`으로 즉시 삭제

> 시드 시크릿은 `recovery_window_in_days=0`이라 복구 없이 바로 사라진다([secrets.tf](ec2/secrets.tf)).

---

## 9. Phase 9 — 프론트엔드 (S3 + CloudFront)

**Terraform과 CI에 모두 구현돼 있다.** 직접 할 일은 없다.

### 9-1. 인프라 ([cloudfront.tf](ec2/cloudfront.tf))

| 리소스 | 역할 |
|---|---|
| `aws_s3_bucket.frontend` + `public_access_block` | 정적 파일 저장, 퍼블릭 접근 완전 차단 |
| `aws_cloudfront_origin_access_control.frontend` | CloudFront만 S3를 읽도록 OAC로 제한 |
| `aws_cloudfront_distribution.frontend` | 진입점. S3(기본) + ALB(`/api/*`, `/auth/*`) 두 오리진 |
| `aws_s3_bucket_policy.frontend` | OAC 전용 읽기 정책 |

동작 특성 두 가지를 알아두면 좋다.

- **SPA 라우팅**: S3 404/403 → `/index.html` 200으로 매핑(React Router 지원)
- **SSE 스트리밍**: `/api/*` behavior는 `compress = false`, `origin_read_timeout = 60`.
  채팅 스트림은 25초 간격 keepalive를 보내므로 이 60초(바이트 간 간격 기준)에 걸리지 않는다

### 9-2. 배포 (`deploy.yml`의 `deploy-frontend` 잡)

`terraform` 잡의 output(`frontend_s3_bucket`, `cloudfront_distribution_id`)을 받아
빌드 → 업로드 → 캐시 무효화를 자동 수행한다. `main` push마다 실행된다.

> 프론트 빌드 시 API base URL 주입이 필요하다(`VITE_API_URL` 등) — 값은 GitHub
> Variables에서 관리한다(Phase 4-3).
> 그리고 그 도메인을 백엔드 `ALLOWED_ORIGINS`(CORS)에 반드시 포함시킨다.

---

## 10. Phase 10 — 도메인 + HTTPS (ACM)

1. **ACM 인증서 발급** (리전 = `ap-northeast-2`, ALB용):
   ```bash
   aws acm request-certificate --domain-name app.example.com \
     --validation-method DNS --region ap-northeast-2
   ```
   반환된 CNAME을 도메인 DNS에 등록 → 검증 완료 대기.
   (CloudFront용 인증서는 별도로 **us-east-1**에 발급해야 한다.)

2. **ALB에 적용**: `terraform.tfvars`(또는 TF_VAR) `alb_ssl_certificate_arn`에 ARN 입력 → apply.
   [alb.tf](ec2/alb.tf)가 HTTPS(443) 리스너를 자동 생성한다.

3. **HTTP→HTTPS 리다이렉트**: alb.tf 주석 안내대로 `aws_lb_listener.http`의 `default_action`을
   `redirect`(443)로 바꾼다.

4. **Route 53**: ALB DNS로 A(Alias) 레코드, CloudFront로 프론트 도메인 Alias 연결.

---

## 11. Phase 11 — 이후 배포 (정상 운영 루프)

코드 수정 후 **main 브랜치에 push만 하면** 전자동:

```
git push origin main
  → build-and-push: 새 SHA 태그로 이미지 빌드 → 5개 ECR push
  → terraform apply: task_definition이 새 ecr_image_tag(github.sha)로 갱신
                     → ECS가 롤링 배포 (rolling update)
```

- **무중단**: ECS는 새 태스크가 ALB 헬스체크를 통과한 뒤 옛 태스크를 내린다.
  `deregistration_delay=30`으로 SSE 스트림이 graceful close될 시간을 준다([alb.tf](ec2/alb.tf)).
- **데이터 EC2 코드 변경 시**: EC2는 이 파이프라인 밖이다. Phase 6 절차를 재실행하거나
  S3 deploy 방식 자동화를 구성한다.

### 롤백

```bash
# 직전 정상 SHA로 되돌리기
cd infra/ec2
terraform apply -var="ecr_image_tag=<직전_정상_SHA>" \
  -var="ecr_registry=<ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com"
```

이미지는 ECR lifecycle로 최근 10개 보관되므로([ecr.tf](bootstrap/ecr.tf)) 최근 배포로 롤백 가능.

---

## 12. 검증 체크리스트

- [ ] `aws ecr describe-repositories` — 5개 레포 존재, 이미지 push됨
- [ ] ECS 5개 서비스 `running == desired`
- [ ] `curl http://<ALB>/health` → 200
- [ ] CloudWatch `/ecs/ai-innovation`에 structlog JSON 로그 수신
- [ ] DB EC2: `systemctl is-active postgresql db-api` → active
- [ ] OpenSearch EC2: `systemctl is-active opensearch opensearch-api` → active
- [ ] OpenSearch 인덱스/DB 스키마 셋업 완료 (`product_v4_combined` 문서 수 > 0)
- [ ] 프론트엔드: CloudFront 도메인 접속 → SPA 라우팅 동작, `/api/*`가 ALB로 전달됨
- [ ] admin 로그인 성공 → 시드 Secret 회수 완료
- [ ] (HTTPS 도입 시) `https://도메인/health` 200, HTTP→HTTPS 리다이렉트
- [ ] CORS: 프론트 도메인이 `ALLOWED_ORIGINS`에 포함
- [ ] CloudWatch 경보 `ai-innovation-alb-5xx` 활성([alb.tf](ec2/alb.tf))

---

## 13. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| ECS 태스크가 `STOPPED` 반복 | ① 이미지에 앱 코드 미포함 ② task definition `command` 누락 ③ Secrets Manager 권한 — CloudWatch 로그의 `stoppedReason` 확인 |
| `CannotPullContainerError` | ECR 레포 없음(bootstrap apply 미실행) 또는 ECR VPC Endpoint/NAT 경로 문제 |
| crm-service만 안 뜸 | 5432 인바운드 규칙 확인 — LangGraph checkpointer가 PostgreSQL에 직접 연결([security_groups.tf](ec2/security_groups.tf) `ecs_to_postgres`) |
| ALB 502/503 | Target group unhealthy. `/health` 200 여부, 태스크 기동 여부 확인 |
| SSE 20초+에서 끊김 | ALB `idle_timeout=300` 적용됐는지([alb.tf](ec2/alb.tf)). CloudFront 경유면 CF 타임아웃도 확인 |
| OpenSearch OOM | JVM heap 4000m 설정 확인(opensearch_setup.sh). c5.xlarge(8GB) 기준 |
| DB/OpenSearch API 연결 거부 | Phase 6 미수행 — 앱 코드 배포 + `systemctl start` 필요 |
| terraform `Error acquiring state lock` | DynamoDB 잠금 잔류. `terraform force-unlock <ID>` (신중히) |
| GitHub Actions OIDC 거부 | Secret `AWS_ROLE_ARN` 오타 또는 부트스트랩 org/repo 불일치 |

---

## 14. 비용 관리 메모

- 운영 안 할 때 비용 절감: ECS `desired_count=0`으로 낮추고, EC2는 `aws ec2 stop-instances`.
  단 NAT Gateway 고정비(~$43/월)와 ALB 고정비는 리소스가 살아있는 한 계속 과금된다.
- 완전 정리: `cd infra/ec2 && terraform destroy` (EBS 데이터 볼륨도 삭제됨 — 백업 먼저).
  부트스트랩 S3 버킷은 `prevent_destroy=true`라 별도 처리 필요.
- 상시 가동 기준 총 비용은 약 **$203/월**.

---

## 부록 A. 핵심 리소스 ↔ 파일 매핑

| 리소스 | 파일 |
|--------|------|
| state 백엔드·OIDC·배포 IAM Role | [bootstrap/main.tf](bootstrap/main.tf) |
| VPC·서브넷·라우팅 | [ec2/vpc.tf](ec2/vpc.tf) |
| NAT Gateway | [ec2/nat_gateway.tf](ec2/nat_gateway.tf) |
| VPC Endpoints (ECR/S3/Secrets/Logs) | [ec2/vpc_endpoints.tf](ec2/vpc_endpoints.tf) |
| Security Groups | [ec2/security_groups.tf](ec2/security_groups.tf) |
| EC2(DB/OpenSearch)·EBS | [ec2/ec2.tf](ec2/ec2.tf) + [user_data/](ec2/user_data/) |
| OpenSearch API ASG(골든 AMI·CPU 타깃 트래킹) | [ec2/opensearch_api_asg.tf](ec2/opensearch_api_asg.tf) |
| OpenSearch API용 내부 NLB | [ec2/opensearch_api_nlb.tf](ec2/opensearch_api_nlb.tf) |
| ECR 레포·lifecycle | [bootstrap/ecr.tf](bootstrap/ecr.tf) |
| ECS 클러스터·task·service·Cloud Map | [ec2/ecs.tf](ec2/ecs.tf) |
| ALB·Target Group·5xx 경보 | [ec2/alb.tf](ec2/alb.tf) |
| S3(프론트)·CloudFront·OAC | [ec2/cloudfront.tf](ec2/cloudfront.tf) |
| 백업(스냅샷·EBS) | [ec2/backup.tf](ec2/backup.tf) |
| Secrets Manager(admin 시드) | [ec2/secrets.tf](ec2/secrets.tf) |
| 변수·출력 | [ec2/variables.tf](ec2/variables.tf) · [ec2/outputs.tf](ec2/outputs.tf) |
| CI/CD | [.github/workflows/deploy.yml](../.github/workflows/deploy.yml) |
