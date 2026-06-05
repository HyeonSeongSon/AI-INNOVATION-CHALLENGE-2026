"""
JWT_SECRET 생성 및 .env 자동 업데이트 스크립트.
사용법: python generate_jwt_secret.py
"""

import re
import secrets
from pathlib import Path

ENV_PATH = Path(__file__).parent / "backend" / "app" / ".env"
SECRET = secrets.token_hex(32)  # 64자리 hex


def update_env(env_path: Path, secret: str) -> None:
    if not env_path.exists():
        print(f"[ERROR] .env 파일을 찾을 수 없습니다: {env_path}")
        return

    content = env_path.read_text(encoding="utf-8")

    if re.search(r"^JWT_SECRET\s*=", content, re.MULTILINE):
        # 기존 값 교체
        content = re.sub(
            r"^(JWT_SECRET\s*=).*$",
            rf"\g<1>{secret}",
            content,
            flags=re.MULTILINE,
        )
        action = "업데이트"
    else:
        # 없으면 끝에 추가
        content = content.rstrip() + f"\nJWT_SECRET={secret}\n"
        action = "추가"

    env_path.write_text(content, encoding="utf-8")
    print(f"[OK] JWT_SECRET {action} 완료: {env_path}")


print(f"생성된 JWT_SECRET:\n{SECRET}\n")
update_env(ENV_PATH, SECRET)
