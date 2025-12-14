from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import persona_routes

app = FastAPI()

# CORS 설정 (React 프론트엔드 연동용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"], # React 주소
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(persona_routes.router, prefix="/api/persona", tags=["Persona"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)