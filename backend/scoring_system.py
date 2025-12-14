def calculate_ranking_weights(budget: str, has_preferred_brands: bool) -> dict:
    """
    [Ver 3.0] 예산과 브랜드 선호 여부를 기반으로 랭킹 가중치를 계산
    
    Args:
        budget (str): 사용자가 선택한 예산 (예: "가성비 중시")
        has_preferred_brands (bool): 사용자가 선호 브랜드를 입력했는지 여부 (True/False)
        
    Returns:
        dict: {'price': 0.0~1.0, 'popularity': 0.0~1.0, 'ingredient': 0.0~1.0}
    """
    
    # 1. 기본값 설정 (밸런스형)
    # 화장품은 보통 성분(효능)과 리뷰(인기)가 중요하므로 이를 기본으로 잡음
    weights = {
        "price": 0.3,       # 가격
        "popularity": 0.3,  # 인기/브랜드/리뷰
        "ingredient": 0.4   # 성분/효능
    }

    # 2. 예산(Budget)에 따른 대분류 조정
    if "가성비" in budget:
        # 돈이 중요함 -> 가격 비중 대폭 상향
        weights = {"price": 0.7, "popularity": 0.1, "ingredient": 0.2}
        
    elif "프리미엄" in budget or "고가" in budget:
        # 돈 상관없음 -> 가격 비중 0, 브랜드와 성분에 집중
        weights = {"price": 0.0, "popularity": 0.5, "ingredient": 0.5}
        
    elif "효능" in budget:
        # 효과만 좋으면 됨 -> 성분 비중 상향
        weights = {"price": 0.2, "popularity": 0.1, "ingredient": 0.7}

    # 3. [화이트보드 반영] 브랜드 선호 여부에 따른 미세 조정
    # 사용자가 "에스트라, 이니스프리" 처럼 브랜드를 콕 집어 입력했다면?
    # -> 그 사람은 "브랜드 이름값(인지도)"을 중요하게 생각하는 사람임.
    if has_preferred_brands:
        # 인기/브랜드 점수(popularity)를 높여줌
        weights["popularity"] += 0.3
        
        # 밸런스를 맞추기 위해 다른 점수를 조금 깎음 (음수가 안 되게 max 처리)
        weights["price"] = max(0.0, weights["price"] - 0.1)
        weights["ingredient"] = max(0.0, weights["ingredient"] - 0.2)
        
    # (참고) 여기서 합계가 꼭 1.0이 될 필요는 없지만, 상대적인 크기가 중요합니다.

    return weights