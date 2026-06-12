"""
JWT_SECRET 및 INTERNAL_TOKEN 생성 및 .env 자동 업데이트 스크립트.
사용법: python generate_jwt_secret.py
"""

import re
import secrets
from pathlib import Path

ENV_PATH = Path(__file__).parent / "backend" / "app" / ".env"

jwt_secret = secrets.token_hex(32)  # 64자리 hex
internal_token = secrets.token_hex(32)
while internal_token == jwt_secret:
    internal_token = secrets.token_hex(32)


def update_env(env_path: Path, key: str, value: str) -> None:
    if not env_path.exists():
        print(f"[ERROR] .env 파일을 찾을 수 없습니다: {env_path}")
        return

    content = env_path.read_text(encoding="utf-8")

    if re.search(rf"^{key}\s*=", content, re.MULTILINE):
        content = re.sub(
            rf"^({key}\s*=).*$",
            rf"\g<1>{value}",
            content,
            flags=re.MULTILINE,
        )
        action = "업데이트"
    else:
        content = content.rstrip() + f"\n{key}={value}\n"
        action = "추가"

    env_path.write_text(content, encoding="utf-8")
    print(f"[OK] {key} {action} 완료: {env_path}")


print(f"생성된 JWT_SECRET:\n{jwt_secret}\n")
print(f"생성된 INTERNAL_TOKEN:\n{internal_token}\n")
update_env(ENV_PATH, "JWT_SECRET", jwt_secret)
update_env(ENV_PATH, "INTERNAL_TOKEN", internal_token)
