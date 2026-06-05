import urllib.request, json, os
from jose import jwt as jose_jwt

token = os.getenv("INTERNAL_TOKEN", "")
ADMIN_ID = "a50a8933-3d17-4375-8f12-4c209694054f"
USER_ID  = "aeea6be7-aadd-4906-92bb-6c2e0da0b1ee"

def make_assertion(user_id: str, role: str = "user") -> str:
    return jose_jwt.encode(
        {"user_id": user_id, "role": role, "iss": "api-gateway", "aud": "internal"},
        token,
        algorithm="HS256",
    )

def call_list(label: str, user_id: str, role: str):
    assertion = make_assertion(user_id, role)
    req = urllib.request.Request(
        "http://localhost:8020/api/personas/list",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            "X-Internal-Token": token,
            "X-User-Assertion": assertion,
        }
    )
    try:
        res = urllib.request.urlopen(req)
        data = json.loads(res.read())
        print(f"[{label}] total={data.get('total')}, items={len(data.get('items', []))}")
        for item in data.get("items", [])[:3]:
            print(f"  - {item.get('persona_id')} {item.get('name')} (user_id={item.get('persona_id')})")
    except urllib.error.HTTPError as e:
        print(f"[{label}] HTTP {e.code}: {e.read()[:200]}")

call_list("admin@test.com (admin role)", ADMIN_ID, "admin")
call_list("admin@test.com (user role)", ADMIN_ID, "user")
call_list("user@test.com  (user role)", USER_ID,  "user")
