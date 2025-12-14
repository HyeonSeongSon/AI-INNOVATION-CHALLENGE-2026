# backend/persona_categorizer.py
from scoring_system import calculate_ranking_weights

def split_str(text):
    """콤마로 구분된 문자열을 리스트로 변환"""
    if not text: return []
    return [t.strip() for t in text.split(',')]

def analyze_persona_logic(data: dict) -> dict:
    # --- 1. 데이터 추출 ---
    skin_types = data.get("skinType", [])
    concerns = data.get("concerns", [])
    sensitivity_level = data.get("sensitivity", "중") # 상/중/하
    
    # 텍스트 입력 필드 리스트로 변환
    pref_ingredients = split_str(data.get("preferredIngredients", ""))
    avoid_ingredients = split_str(data.get("avoidedIngredients", ""))
    allergies = split_str(data.get("allergies", ""))
    brands = split_str(data.get("preferredBrands", ""))
    
    lifestyle = {
        "sleep": data.get("sleep", ""),
        "stress": data.get("stress", 3),
        "diet": data.get("diet", ""),
        "exercise": data.get("exercise", "")
    }
    
    # --- 2. 결과 구조 초기화 ---
    search_profile = {
        "main_category": "스킨케어",
        "sub_intent": [],
        "include_tags": [],
        "exclude_tags": [], # 기피 성분 담을 곳
        "texture_pref": data.get("preferredTexture", ""),
        "ranking_weights": {}
    }
    
    message_guide = {
        "summary": "",
        "tone": "",
        "pain_point": "",
        "solution": ""
    }

    # --- 3. [Logic] 피부 타입 & 민감도 ---
    # 민감도 '상'이면 강력한 필터링 적용
    if sensitivity_level == "상" or "민감성" in skin_types:
        search_profile["include_tags"].extend(["시카", "판테놀", "마데카소사이드", "무향", "EWG그린"])
        search_profile["exclude_tags"].extend(["인공향료", "알코올", "파라벤", "AHA", "BHA"]) # 자극 성분 제외
        search_profile["sub_intent"].append("저자극진정")
    
    # 건성/지성 매핑
    if "건성" in skin_types:
        search_profile["include_tags"].extend(["세라마이드", "히알루론산", "고보습"])
    if "지성" in skin_types:
        search_profile["include_tags"].extend(["산뜻한", "오일프리", "피지조절"])

    # --- 4. [Logic] 사용자 지정 선호/기피 성분 반영 ---
    # 사용자가 직접 입력한 '좋아하는 성분'은 무조건 검색어에 포함
    search_profile["include_tags"].extend(pref_ingredients)
    
    # 사용자가 입력한 '알러지/기피 성분'은 제외 태그에 추가
    search_profile["exclude_tags"].extend(avoid_ingredients)
    search_profile["exclude_tags"].extend(allergies)

    # --- 5. [Logic] 라이프스타일 분석 (화이트보드) ---
    # 운동량 분석 (땀 많이 흘리면 쿨링/모공)
    if "주 3회 이상" in lifestyle["exercise"] or "매일" in lifestyle["exercise"]:
        search_profile["include_tags"].extend(["쿨링", "모공케어", "산뜻한마무리"])
        search_profile["sub_intent"].append("운동후케어")

    # 스트레스 레벨 (0~5)
    stress_level = int(lifestyle["stress"])
    if stress_level >= 4:
        search_profile["include_tags"].extend(["아로마", "릴렉싱", "리프레쉬"])
        message_guide["pain_point"] = "높은 스트레스로 지친 피부 컨디션"
        message_guide["solution"] = "마음까지 편안해지는 힐링 리추얼"

    # 수면 시간
    if "6시간 미만" in lifestyle["sleep"]:
        search_profile["include_tags"].append("비타민C") # 브라이트닝
        message_guide["pain_point"] = "수면 부족으로 칙칙해진 안색"

    # --- 6. [Logic] 가중치 계산 ---
    # 브랜드 선호가 명확하면 인기/브랜드 점수를 높임
    has_preferred_brands = len(brands) > 0
    search_profile["ranking_weights"] = calculate_ranking_weights(
        data.get("budget", ""), has_preferred_brands
    )

    # --- 7. 정리 ---
    search_profile["include_tags"] = list(set(search_profile["include_tags"]))
    search_profile["exclude_tags"] = list(set(search_profile["exclude_tags"]))
    
    # 메시지 생성
    skin_desc = f"{' '.join(skin_types)} 피부"
    if sensitivity_level == "상": skin_desc += "(초민감)"
    message_guide["summary"] = f"{data.get('age')} {skin_desc} 고객님"

    return {
        "search_profile": search_profile,
        "message_guide": message_guide
    }