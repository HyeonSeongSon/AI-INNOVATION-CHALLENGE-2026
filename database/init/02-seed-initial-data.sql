-- AI Innovation Challenge 2026 Initial Data Seed
-- 초기 데이터: 브랜드만 삽입 (페르소나는 프론트엔드에서 추가)

-- ============================================================
-- 브랜드 초기 데이터 삽입 (brand_ton.yaml 기반)
-- ============================================================

-- 글랜팜
INSERT INTO brands (
    name,
    brand_url,
    tone_description,
    target_audience,
    brand_positioning,
    brand_personality,
    tone_style,
    core_keywords,
    prohibited_expressions
) VALUES (
    '글랜팜',
    'https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=glampam',
    '신뢰할 수 있는 전문가 친구. 노련하지만 친근하고, 검증된 실력으로 자신감 있게 조언하는 동반자.',
    '{
        "age_range": "25-45세",
        "target": "헤어 스타일링 중시하는 전문가 및 일반 소비자",
        "values": ["품질", "내구성", "실용주의"]
    }'::jsonb,
    '프리미엄 전문가용 헤어 디바이스. 미용실에서 쓰는 그 고데기라는 전문가 신뢰 기반의 검증된 명품.',
    '신뢰할 수 있는 전문가 친구',
    '확신에 찬, 전문적인, 검증된, 신뢰할 수 있는. 과장 없이 팩트로 말하는 톤.',
    ARRAY['전문가 선택', '미용실 점유율 90퍼센트', '특허 22종', '열손상 최소화', '윤기', '내구성', '셀프 스타일링', '글로벌 기술력'],
    ARRAY['과도한 수식어', '가격 할인 강조', '즉각 효과 과장', '경쟁사 비교', '이모티콘이나 유행어 남발']
);

-- 놋담
INSERT INTO brands (
    name,
    brand_url,
    tone_description,
    target_audience,
    brand_positioning,
    brand_personality,
    tone_style,
    core_keywords,
    prohibited_expressions
) VALUES (
    '놋담',
    'https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=notdam',
    '세심하게 케어하는 웰니스 파트너. 전통의 지혜를 현대적으로 재해석하고, 매일 꾸준히 내 몸을 돌보도록 이끌어주는 건강한 조언자.',
    '{
        "age_range": "25-45세",
        "target": "셀프케어와 뷰티 관리에 관심 많은 여성",
        "values": ["전통", "건강", "꾸준한 자기관리"]
    }'::jsonb,
    '프리미엄 방짜유기 괄사 마사지기 브랜드. 전통 유기의 건강함에 인체공학적 디자인을 더한 모던 셀프케어 도구.',
    '세심하게 케어하는 웰니스 파트너',
    '세심한, 건강을 생각하는, 꾸준함을 강조하는, 은은하게 품격 있는. 과장 없이 케어의 본질로 말하는 톤.',
    ARRAY['방짜유기 괄사', '인체공학적 디자인', '혈액순환 촉진', '림프 순환', '부종 완화', '피부 탄력', '구리 78퍼센트 주석 22퍼센트', '항균효과', '홈 에스테틱', '매일 10분 셀프케어'],
    ARRAY['즉각적인 효과 과장', '의료 효능 주장', '다이어트나 체형 변화 보장', '자극적인 비포 애프터', '화려한 과장']
);

-- 라네즈
INSERT INTO brands (
    name,
    brand_url,
    tone_description,
    target_audience,
    brand_positioning,
    brand_personality,
    tone_style,
    core_keywords,
    prohibited_expressions
) VALUES (
    '라네즈',
    'https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=22',
    '함께 성장하는 뷰티 파트너. 최신 트렌드와 기술을 빠르게 적용하며, 고객과 함께 진화하는 혁신적인 동반자.',
    '{
        "age_range": "20-30대 초반",
        "target": "도시에서 활동하는 커리어 우먼",
        "values": ["효율성", "혁신", "글로벌 트렌드"]
    }'::jsonb,
    '수분 기능성 뷰티 브랜드. 수분으로 꽉 차 맑고 건강하게 빛나는 루미너스 뷰티 추구.',
    '함께 성장하는 뷰티 파트너',
    '밝고 긍정적인, 혁신적인, 트렌디한. 미래지향적이면서도 친근한 톤.',
    ARRAY['수분 기능성', '루미너스 뷰티', '글로벌 K뷰티', '혁신 기술', '워터 사이언스', '클린 뷰티'],
    ARRAY['과도한 의료 효능 주장', '즉각적 효과 과장', '경쟁사 비교']
);

-- 설화수
INSERT INTO brands (
    name,
    brand_url,
    tone_description,
    target_audience,
    brand_positioning,
    brand_personality,
    tone_style,
    core_keywords,
    prohibited_expressions
) VALUES (
    '설화수',
    'https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=sulwhasoo',
    '한방의 지혜를 전하는 스승. 세대를 넘어 전해지는 아름다움의 비법을 현대적으로 계승하는 명품.',
    '{
        "age_range": "40-60대",
        "target": "한방 프리미엄 뷰티 추구자",
        "values": ["전통", "품격", "명품"]
    }'::jsonb,
    '한방 프리미엄 뷰티 브랜드. 5000년 한방의 지혜와 현대 과학의 조화.',
    '한방의 지혜를 전하는 스승',
    '우아하고 고급스러운, 전통과 현대의 조화, 품격 있는 톤.',
    ARRAY['한방', '자음단', '윤조에센스', '궁중 비법', '5000년 지혜', '프리미엄', '명품'],
    ARRAY['캐주얼한 표현', '유행어', '과도한 할인 강조']
);

-- 에스쁘아
INSERT INTO brands (
    name,
    brand_url,
    tone_description,
    target_audience,
    brand_positioning,
    brand_personality,
    tone_style,
    core_keywords,
    prohibited_expressions
) VALUES (
    '에스쁘아',
    'https://www.amoremall.com/kr/ko/display/brand/detail?brandSn=231',
    '트렌디하고 당당한 언니. 최신 트렌드를 빠르게 캐치하고, 자신만의 스타일로 소화하는 패셔너블한 친구.',
    '{
        "age_range": "20-30대",
        "target": "컬러 메이크업 트렌드 추구자",
        "values": ["트렌드", "컬러", "개성"]
    }'::jsonb,
    '컬러 메이크업 전문 브랜드. 당당하고 세련된 컬러 플레이.',
    '트렌디하고 당당한 언니',
    '발랄하고 트렌디한, 컬러풀한, 자신감 넘치는 톤.',
    ARRAY['컬러 플레이', '트렌디', '당당한 메이크업', 'MZ세대', '컬러 전문'],
    ARRAY['올드한 표현', '과도한 안티에이징 강조']
);

-- ============================================================
-- 데이터 검증 쿼리
-- ============================================================

-- 삽입된 브랜드 수 확인
DO $$
DECLARE
    brand_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO brand_count FROM brands;

    RAISE NOTICE '============================================================';
    RAISE NOTICE 'Initial Data Inserted';
    RAISE NOTICE 'Brands: %', brand_count;
    RAISE NOTICE 'Personas: Ready to receive from frontend';
    RAISE NOTICE '============================================================';
END $$;
