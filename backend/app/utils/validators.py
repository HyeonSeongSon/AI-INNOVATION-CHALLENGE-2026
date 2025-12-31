from fastapi import HTTPException
from models.persona import PersonaInput

def validate_persona_logic(data: PersonaInput):
    """
    페르소나 데이터의 논리적 오류를 검증합니다.
    문제가 있을 경우 즉시 400 에러를 발생시켜 불필요한 LLM 호출을 막습니다.
    """
    

    # 2. 필수 입력값 체크
    if not data.name:
        raise HTTPException(status_code=400, detail="페르소나 이름은 필수입니다.")
    
    if not data.skinType:
        raise HTTPException(status_code=400, detail="피부 타입은 필수 입력값입니다.")

    # 3. 피부 타입 유효성 검사 (프론트엔드 옵션과 일치)
    valid_skin_types = [
        '건성', '중성', '복합성', '지성', 
        '민감성', '악건성', '트러블성', '수분 부족 지성'
    ]
    if data.skinType and data.skinType not in valid_skin_types:
        raise HTTPException(status_code=400, detail=f"잘못된 피부 타입입니다: {data.skinType}")

    # 4. 퍼스널 컬러 유효성 검사 (값이 있는 경우에만)
    valid_personal_colors = [
        '웜톤', '봄웜톤', '가을웜톤', 
        '쿨톤', '여름쿨톤', '겨울쿨톤', 
        '뉴트럴톤'
    ]
    if data.personalColor and data.personalColor not in valid_personal_colors:
        raise HTTPException(status_code=400, detail=f"잘못된 퍼스널 컬러입니다: {data.personalColor}")

    # 5. 나이 검증 (기존 로직 유지)
    if data.age:
        try:
            # "20대", "28세" 등에서 숫자만 추출 시도
            age_str = ''.join(filter(str.isdigit, str(data.age)))
            if age_str:
                age_num = int(age_str)
                if age_num < 10 or age_num > 100:
                    raise HTTPException(status_code=400, detail="유효하지 않은 나이입니다 (10~100세).")
        except ValueError:
            pass # 숫자가 없는 문자열(예: "모름")인 경우 패스

    return True