import json
import os
from datetime import datetime
from models.persona import PersonaInput, CategoryResult
from services.category_matcher import CategoryMatcher

# 전역 메모리 캐시
CACHE = {}

class PersonaService:
    def __init__(self):
        self.matcher = CategoryMatcher()

    async def create_persona_category(self, persona: PersonaInput) -> CategoryResult:
        # 1. 캐싱 확인
        input_key = str(sorted(persona.dict().items()))
        if input_key in CACHE:
            print(f"🚀 [Cache Hit] {persona.name}님의 분석 결과를 캐시에서 반환합니다.")
            return CACHE[input_key]

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
        # 저장할 데이터 구조화 (DB 스키마와 비슷하게 구성)
        log_entry = {
            "timestamp": datetime.now().isoformat(),  # 생성 시간
            "user_name": persona.name,                # 사용자 이름
            "age": persona.age,                       # 나이
            "gender": persona.gender,                 # 성별
            "skin_type": persona.skinType,            # 피부 타입
            "concerns": persona.skinConcerns,         # 피부 고민 (리스트)
            "category_result": result.primary_category, # 결과 카테고리
            "reasoning": result.reasoning,            # 추천 사유
            "confidence": result.confidence_score     # 신뢰도
        }
        
        # logs 폴더가 없으면 생성
        os.makedirs("logs", exist_ok=True)
        
        # 파일명을 .jsonl로 변경
        file_path = "logs/persona_history.jsonl"
        
        try:
            # mode='a' (append)로 열어서 끝에 추가
            with open(file_path, "a", encoding="utf-8") as f:
                # ensure_ascii=False: 한글 깨짐 방지
                # + "\n": 다음 데이터는 줄바꿈 후 저장 (이게 JSONL의 핵심!)
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                
            print(f"💾 [JSONL Saved] {file_path}에 데이터가 추가되었습니다.")
            
        except Exception as e:
            print(f"❌ Log Save Error: {e}")