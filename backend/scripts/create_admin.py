"""
첫 번째 admin 계정을 생성하는 CLI 스크립트.
비밀번호는 getpass로 입력 받아 셸 히스토리에 남지 않는다.

사용법:
  # 로컬 (backend/ 디렉터리에서)
  python -m scripts.create_admin --email admin@example.com

  # Docker
  docker compose exec fastapi-backend python -m scripts.create_admin --email admin@example.com
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 경로에 추가

from app.core.database import SessionLocal
from app.core.models import User
from app.core.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="admin 계정 생성")
    parser.add_argument("--email", required=True, help="admin 이메일")
    args = parser.parse_args()

    password = getpass.getpass("비밀번호 입력: ")
    confirm  = getpass.getpass("비밀번호 확인: ")

    if password != confirm:
        print("비밀번호가 일치하지 않습니다.", file=sys.stderr)
        sys.exit(1)

    if len(password) < 8:
        print("비밀번호는 최소 8자 이상이어야 합니다.", file=sys.stderr)
        sys.exit(1)

    with SessionLocal() as db:
        if db.query(User).filter(User.email == args.email).first():
            print(f"이미 존재하는 이메일입니다: {args.email}")
            sys.exit(0)

        user = User(
            email=args.email,
            password_hash=hash_password(password),
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    print(f"admin 계정 생성 완료: {args.email} (id={user.id})")


if __name__ == "__main__":
    main()
