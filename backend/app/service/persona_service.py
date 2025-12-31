import json
import os
from datetime import datetime
from models.persona import PersonaInput, CategoryResult
from services.ai_service import PersonaAIService

# 전역 메모리 캐시
CACHE = {}

class PersonaService:
    def __init__(self):
        self.matcher = CategoryMatcher()

    async def create_persona_category(self, persona: PersonaInput) -> CategoryResult:
        # 1. 캐싱 확인
        input_key = str(sorted(persona.dict().items()))
        # [수정] LLM 프롬프트 테스트 중에는 캐시가 이전(잘못된) 결과를 계속 반환할 수 있으므로 비활성화합니다.
        # if input_key in CACHE:
        #     print(f"🚀 [Cache Hit] {persona.name}님의 분석 결과를 캐시에서 반환합니다.")
        #     return CACHE[input_key]

        # 2. 분석 실행
        result = await self.matcher.analyze(persona)
        
        # 3. [수정됨] JSONL 형식으로 저장
        await self.save_history(persona, result)
        
        # 4. 캐시 저장 및 반환
        CACHE[input_key] = result
        return result

    async def save_history(self, persona: PersonaInput, result: CategoryResult):
        """
        분석 기록을 JSONL(Newline Delimited JSON) 형식으로 저장합니다.
        DB 적재(Bulk Insert)나 로그 분석에 최적화된 포맷입니다.
        """
        # 1. 페르소나 입력 데이터 전체를 딕셔너리로 변환 (모든 필드 자동 포함)
        log_entry = persona.dict()

        # 2. 분석 결과 및 메타데이터 병합
        # DB 업데이트 시 편의를 위해 분석 결과를 명확한 키로 추가합니다.
        log_entry.update({
            "created_at": datetime.now().isoformat(),
            "ai_primary_category": result.primary_category,
            "ai_reasoning": result.reasoning,
            "ai_confidence": result.confidence_score,
            "ai_keywords": result.keywords
        })

        # [수정] 실행 위치에 상관없이 항상 backend/logs 폴더에 저장되도록 절대 경로 사용
        # 현재 파일(persona_service.py)의 위치를 기준으로 경로를 설정합니다.
        # __file__ -> .../backend/services/persona_service.py -> os.path.dirname -> .../backend/services -> os.path.dirname -> .../backend
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_path = os.path.join(log_dir, "persona_history.jsonl")
        
        try:
            # mode='a' (append)로 열어서 끝에 추가
            with open(file_path, "a", encoding="utf-8") as f:
                # ensure_ascii=False: 한글 깨짐 방지
                # + "\n": 다음 데이터는 줄바꿈 후 저장 (이게 JSONL의 핵심!)
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
            print(f"💾 [JSONL Saved] {file_path}에 데이터가 추가되었습니다.")
            
        except Exception as e:
            print(f"❌ Log Save Error: {e}")