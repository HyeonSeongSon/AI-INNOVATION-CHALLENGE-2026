from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import persona_routes
# from routes import product_routes  # 있으면 주석 해제

app = FastAPI()

# --- [수정된 부분] ---
origins = [
    "http://localhost:5173",  # 👈 여기가 범인! (Vite 기본 포트)
    "http://127.0.0.1:5173",
    "http://localhost:3000",  # 혹시 몰라 기존 것도 유지
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # 허용 리스트 적용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --------------------

app.include_router(persona_routes.router, prefix="/api/persona")

@app.get("/")
def read_root():
    return {"message": "Backend is running!"}