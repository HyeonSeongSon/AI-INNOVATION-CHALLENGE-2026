import { ShoppingBag, Wand2, Sparkles, Tag, Bot } from 'lucide-react';

const SLASH_COMMANDS = [
  {
    name: 'recommend',
    label: '/recommend',
    description: '페르소나 기반 상품 추천',
    icon: ShoppingBag,
    tools: ['페르소나 기반 상품 추천'],
    tasks: ['특정 카테고리 한정 추천', '특정 브랜드 한정 추천'],
    examples: [
      '김덕구 페르소나에 맞는 상품 추천해줘',
      '김덕구 페르소나가 사용할만한 스킨 제품 추천해줘',
      '김덕구 페르소나에게 맞는 이니스프리 스킨 추천해줘',
    ],
  },
  {
    name: 'generate',
    label: '/generate',
    description: 'CRM 마케팅 메시지 생성',
    icon: Wand2,
    tools: ['CRM 광고 메시지 생성', '메시지 내용 수정'],
    tasks: ['브랜드/제품 첫소개 메시지 생성', '베스트셀러 제품 소개 메시지 생성', '프로모션/이벤트 소개', '성분/효능 강조 소개'],
    examples: [
      '김덕구 페르소나에게 보낼 시카페인 트러블리셋 클렌징폼(A20251200315) 제품으로 제품 첫소개 메시지 생성해줘',
      'A20251200315 제품으로 베스트셀러 소개 광고 메시지 생성해줘',
      'A20251200315 으로 성분 강조 메시지 만들어줘',
    ],
  },
  {
    name: 'search',
    label: '/search',
    description: '고객 · 상품 데이터 조회',
    icon: Sparkles,
    tools: ['페르소나 목록 조회', '인기 상품 카테고리 조회', '브랜드 인기 상품 조회', '특정 페르소나 상세 정보 조회', '등록된 브랜드 목록 조회', '등록된 카테고리 목록 조회'],
    tasks: ['조건별 페르소나 목록 조회', '카테고리 · 브랜드별 상품 조회'],
    examples: [
      '20대 지성 피부 페르소나 목록 보여줘',
      '이니스프리 브랜드 상품 조회해줘',
      '인기 토너 제품을 추천해줘',
    ],
  },
  {
    name: 'register',
    label: '/register',
    description: '상품 · 고객 데이터 등록',
    icon: Tag,
    tools: ['자연어 페르소나 등록', '파일 업로드 페르소나 등록', '파일 업로드 상품 등록'],
    tasks: ['신규 상품 정보 등록', '신규 페르소나 등록'],
    examples: [
      '업로드한 xlsx로 상품 등록해줘',
      '업로드한 CSV 파일로 페르소나 일괄 등록해줘',
      '다음 내용으로 페르소나 생성해줘. 20대 지성 피부 김덕구는 가볍게 발리는 제품을 선호하며...',
    ],
  },
  {
    name: 'help',
    label: '/help',
    description: '사용 가능한 모든 기능 안내',
    icon: Bot,
    tools: [],
    tasks: [],
    examples: [],
  },
];

export default SLASH_COMMANDS;
