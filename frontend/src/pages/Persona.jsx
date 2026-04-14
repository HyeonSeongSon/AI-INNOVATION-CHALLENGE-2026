import React, { useState, useEffect } from 'react';
import styled, { css, keyframes } from 'styled-components';
import { 
  Plus, X, User, Trash2, Check, 
  Droplets, Sun, Zap, Frown, Smile, Moon, Utensils, 
  MapPin, Heart, Sparkles, AlertCircle, Palette, Wallet,
  ChevronRight, ChevronLeft, 
  Layers, Wind, Home, Feather, Shield, Clock, ShoppingBag, Star, Gift,
  Cat 
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

// ✅ Toast 및 API 모듈 불러오기
import { useToast } from '../components/Toast';
import api, { pipelineApi } from '../api';

/* --- [1] 데이터 및 옵션 설정 --- */
const OPTIONS = {
  occupations: ['학생', '직장인', '취준생', '주부', '프리랜서', '사업가', '전문직', '공무원', '예술가', '은퇴', '기타'],
  gender: [
    { label: '여성', icon: <User size={20}/> },
    { label: '남성', icon: <User size={20}/> },
    { label: '기타', icon: <Smile size={20}/> }
  ],
  skinTypes: ['건성', '중성', '복합성', '지성', '민감성', '악건성', '트러블성', '수분 부족 지성'],
  personalColors: ['웜톤', '봄웜톤', '가을웜톤', '쿨톤', '여름쿨톤', '겨울쿨톤', '뉴트럴톤'],
  baseColors: ['13', '17', '19', '21', '22', '23', '25', '27', '29', '31'], // 숫자 문자열로 통일
  sleepTimeOptions: ['4', '5', '6', '7', '8', '9', '10', '11', '12'],
  skinConcerns: [
    '잡티', '미백', '주름', '각질', '여드름', '블랙헤드', '피지과다', '아토피', '민감성', 
    '다크서클', '기미', '홍조', '유수분밸런스', '탄력', '트러블자국', '비듬', '탈모'
  ],
  ingredients: ['히알루론산', '나이아신아마이드', '레티놀', '비타민C', '펩타이드', '시카', '티트리', '세라마이드', '콜라겐', '알부틴'],
  avoidedIngredients: ['파라벤', '알코올', '인공향료', '인공색소', '미네랄오일', '실리콘', 'SLS/SLES', '합성방부제'],
  makeupColors: [
    { label: '레드', code: '#FF4D4D' }, { label: '핑크', code: '#FFADD2' }, { label: '코랄', code: '#FF7F50' },
    { label: '오렌지', code: '#FFA500' }, { label: '베이지', code: '#E8DCCA' }, { label: '브라운', code: '#8B4513' },
  ],
  scents: ['무향', '플로럴', '시트러스', '허브', '우디', '머스크'],
  spendingStyles: [
    { label: '실속/가성비파', desc: '세일·대용량·최저가 중시', icon: <Wallet size={20}/> },
    { label: '합리적 밸런스', desc: '가격 대비 효능/품질 비교', icon: <Check size={20}/> },
    { label: '고급/프리미엄', desc: '백화점·럭셔리 브랜드 선호', icon: <Sparkles size={20}/> }
  ],
  buyingFactors: [
    { label: '효능/효과', desc: '비포애프터 확실해야 함', icon: <Zap size={20}/> },
    { label: '후기/랭킹', desc: '남들이 많이 쓰는 템', icon: <Star size={20}/> },
    { label: '성분/안전', desc: '유해성분 없는 클린뷰티', icon: <Droplets size={20}/> },
    { label: '신상/트렌드', desc: '요즘 핫한 신제품', icon: <Gift size={20}/> }
  ],
  lifestyle: {
    skincareRoutine: [
      { label: '미니멀/올인원', desc: '하나만 바름', icon: <Zap size={20}/> },
      { label: '기본 케어', desc: '스킨+로션', icon: <Check size={20}/> },
      { label: '스페셜 집중', desc: '앰플+팩 필수', icon: <Sparkles size={20}/> },
      { label: '7스킨/레이어링', desc: '여러번 덧바름', icon: <Layers size={20}/> }
    ],
    dailyEnvironment: [
      { label: '사무실/실내', desc: '히터/에어컨 건조', icon: <Wind size={20}/> },
      { label: '야외/이동', desc: '자외선/미세먼지', icon: <Sun size={20}/> },
      { label: '홈/재택', desc: '불규칙한 생활', icon: <Home size={20}/> },
      { label: '작업실/밀폐', desc: '먼지/환기부족', icon: <AlertCircle size={20}/> }
    ],
    texturePreference: [
      { label: '물토너/산뜻', desc: '흡수 빠른 물 제형', icon: <Droplets size={20}/> },
      { label: '촉촉/에센스', desc: '부드러운 수분감', icon: <Feather size={20}/> },
      { label: '꾸덕/영양', desc: '묵직한 보습막', icon: <Shield size={20}/> },
      { label: '패드/티슈', desc: '간편한 닦토/팩', icon: <Layers size={20}/> }
    ],
    petLife: [
      { label: '없음', desc: '', icon: <X size={20}/> },
      { label: '강아지', desc: '강아지 키워요', icon: <Smile size={20}/> },
      { label: '고양이', desc: '고양이 키워요', icon: <Cat size={20}/> },
      { label: '강아지/고양이', desc: '둘 다 키워요', icon: <Heart size={20}/> }
    ],
    stress: ['낮음', '보통', '높음'],
  }
};

/* --- [2] 스타일 컴포넌트 --- */
const Container = styled.div`
  max-width: 1200px; margin: 0 auto; font-family: 'Pretendard', sans-serif; color: #333; padding: 40px 20px;
`;
const Header = styled.div`
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;
`;
const Title = styled.h1`
  font-size: 28px; font-weight: 800; color: #111; margin: 0;
`;
const AddButton = styled.button`
  display: flex; align-items: center; gap: 8px;
  background-color: #6B4DFF; color: white;
  padding: 12px 24px; border-radius: 12px; border: none;
  font-weight: 700; cursor: pointer; transition: 0.2s;
  &:hover { background-color: #5a3de0; transform: translateY(-2px); }
`;
const Grid = styled.div`
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px;
`;
const PersonaCard = styled.div`
  background: white; border-radius: 24px; padding: 28px; border: 1px solid #f0f0f0;
  box-shadow: 0 10px 40px rgba(0,0,0,0.03); position: relative; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  overflow: hidden; cursor: pointer;
  &::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 6px; background: linear-gradient(90deg, #6B4DFF, #9D8CFF); opacity: 0; transition: 0.3s; }
  &:hover { transform: translateY(-8px); box-shadow: 0 20px 50px rgba(107, 77, 255, 0.15); &::before { opacity: 1; } }
`;
const TagChip = styled.span`
  font-size: 11px; font-weight: 600; padding: 6px 12px; border-radius: 20px;
  background-color: ${props => props.$bg || '#f7f7f7'}; color: ${props => props.$color || '#666'};
  display: inline-flex; align-items: center; gap: 6px;
`;
const DeleteBtn = styled.button`
  background: none; border: none; color: #ccc; cursor: pointer; padding: 8px; border-radius: 50%; display: flex; align-items: center; justify-content: center; transition: all 0.2s; z-index: 10;
  &:hover { color: #ff4d4d; background-color: #fff5f5; }
`;
const ModalOverlay = styled.div`
  position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0, 0, 0, 0.6); display: flex; justify-content: center; align-items: center; z-index: 1000; backdrop-filter: blur(5px);
`;
const ModalBox = styled.div`
  background: white; width: 700px; max-height: 90vh; overflow-y: auto; border-radius: 24px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); display: flex; flex-direction: column; position: relative;
  &::-webkit-scrollbar { width: 8px; } &::-webkit-scrollbar-thumb { background-color: #ddd; border-radius: 4px; }
`;
const AnalyzingOverlay = styled.div`
  position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255, 255, 255, 0.98); z-index: 50; display: flex; flex-direction: column; justify-content: center; align-items: center; border-radius: 24px;
`;
const PulseRing = styled.div`
  width: 80px; height: 80px; background: rgba(107, 77, 255, 0.1); border-radius: 50%; position: relative; display: flex; align-items: center; justify-content: center; margin-bottom: 24px;
  &::before, &::after { content: ''; position: absolute; width: 100%; height: 100%; border-radius: 50%; border: 2px solid #6B4DFF; animation: pulse 2s linear infinite; opacity: 0; }
  &::after { animation-delay: 1s; }
  @keyframes pulse { 0% { transform: scale(1); opacity: 0.8; } 100% { transform: scale(2.5); opacity: 0; } }
`;
const LoadingText = styled.div`
  font-size: 18px; font-weight: 700; color: #333; text-align: center;
  span { display: block; margin-top: 8px; font-size: 14px; font-weight: 400; color: #888; }
`;
const SectionTitle = styled.h3`
  font-size: 18px; font-weight: 700; color: #6B4DFF; margin: 0 0 16px 0; display: flex; align-items: center; gap: 8px;
`;
const SubLabel = styled.div`
  font-size: 14px; font-weight: 600; color: #555; margin-bottom: 8px; margin-top: 20px;
`;
const IconGrid = styled.div`
  display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); gap: 10px;
`;
const SelectionCard = styled.div`
  display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 12px 8px; gap: 6px; border: 2px solid #f4f4f4; border-radius: 12px; cursor: pointer; transition: all 0.2s; background: #fafafa; color: #888;
  ${props => props.$chip && css`flex-direction: row; padding: 10px 14px; font-size: 13px; background: white;`}
  &:hover { border-color: #d0c4ff; background: #f8f6ff; color: #6B4DFF; }
  ${props => props.$selected && css`border-color: #6B4DFF; background-color: #F0EBFF; color: #333; font-weight: 700; box-shadow: 0 0 0 1px #6B4DFF inset; &:hover { background-color: #e0d9ff; color: #000; border-color: #6B4DFF; }`}
  span { font-size: 13px; font-weight: 600; text-align: center; }
`;
const InputRow = styled.div`display: flex; gap: 12px; margin-bottom: 10px;`;
const Input = styled.input`
  flex: 1; padding: 14px; border: 1px solid #ddd; border-radius: 10px; font-size: 14px; outline: none; transition: 0.2s;
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); }
`;
const Select = styled.select`
  flex: 1; width: 100%; padding: 14px; border: 1px solid #ddd; border-radius: 10px; font-size: 14px; outline: none; transition: 0.2s; background-color: white; cursor: pointer; color: ${props => props.value ? '#333' : '#aaa'};
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); }
`;
const CheckboxRow = styled.label`
  display: flex; align-items: center; gap: 8px; cursor: pointer; padding: 12px; border-radius: 8px; background: #f9f9f9;
  &:hover { background: #f0ebff; }
  input { accent-color: #6B4DFF; transform: scale(1.2); }
`;
const ButtonGroup = styled.div`
  display: flex; gap: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;
`;
const NavButton = styled.button`
  flex: 1; padding: 16px; border-radius: 12px; border: none; font-weight: 700; font-size: 16px; cursor: pointer;
  ${props => props.$primary ? css`background-color: #6B4DFF; color: white; &:hover { background-color: #5a3de0; }` : css`background-color: #f0f0f0; color: #555; &:hover { background-color: #e0e0e0; }`}
`;
const ProgressBar = styled.div`
  height: 6px; background: #f0f0f0; border-radius: 3px; margin-bottom: 30px; overflow: hidden;
  div { height: 100%; background: linear-gradient(90deg, #6B4DFF, #9D8CFF); transition: width 0.3s ease; }
`;
const RangeContainer = styled.div`display: flex; flex-direction: column; gap: 10px; padding: 10px 0;`;
const RangeHeader = styled.div`display: flex; justify-content: space-between; align-items: center; font-size: 14px; font-weight: 600; color: #6B4DFF;`;
const RangeSlider = styled.input.attrs({ type: 'range' })`
  -webkit-appearance: none; width: 100%; height: 6px; background: #e0e0e0; border-radius: 5px; outline: none; cursor: pointer; margin: 10px 0;
  &::-webkit-slider-runnable-track { width: 100%; height: 6px; cursor: pointer; background: linear-gradient(to right, #6B4DFF 0%, #6B4DFF var(--value, 0%), #e0e0e0 var(--value, 0%), #e0e0e0 100%); border-radius: 5px; }
  &::-webkit-slider-thumb { -webkit-appearance: none; height: 20px; width: 20px; border-radius: 50%; background: #6B4DFF; border: 2px solid white; box-shadow: 0 2px 6px rgba(0,0,0,0.2); margin-top: -7px; transition: transform 0.1s; }
  &:active::-webkit-slider-thumb { transform: scale(1.2); }
`;
const RangeLabels = styled.div`display: flex; justify-content: space-between; font-size: 11px; color: #999;`;

/* --- [3] 메인 컴포넌트 --- */
export default function PersonaManager() {
  const navigate = useNavigate();
  const [showTextModal, setShowTextModal] = useState(false);
  const [personaText, setPersonaText] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [personas, setPersonas] = useState([]);

  const { addToast } = useToast();

  useEffect(() => {
    const fetchPersonas = async () => {
      try {
        const response = await pipelineApi.post('/personas/list');
        const rawData = Array.isArray(response.data) ? response.data : response.data.personas || [];
        
        // 백엔드 응답(snake_case) -> 프론트엔드 상태(camelCase) 매핑
        const formatted = rawData.map(p => ({
            ...p,
            id: p.persona_id || p.id,
            name: p.name,
            age: p.age,
            gender: p.gender,
            occupation: p.occupation,
            skinType: p.skin_type || [], 
            personalColor: p.personal_color,
            baseColor: p.shade_number,
            priceRange: p.shopping_style,
            petInfo: p.pets || '없음', 
            screenTime: p.digital_device_usage_time || 0,
            preferredColors: p.preferred_colors || [],
            texturePreference: p.preferred_texture || [],
            buyingFactor: p.purchase_decision_factors || [], 
            skinConcerns: p.skin_concerns || [],
            // values 배열 처리
            naturalOrganic: p.values && p.values.includes('천연/유기농'),
            veganCrueltyFree: p.values && p.values.includes('비건'),
            
            // ✅ [수정] 백엔드에서 ai_analysis(json)으로 옴 -> 프론트엔드 aiAnalysis 객체로 매핑
            aiAnalysis: {
                primary_category: p.ai_analysis?.primary_category || '분석 중',
                reasoning: p.ai_analysis?.ai_analysis_text || '상세 리포트 준비 중'
            }
        }));
        setPersonas(formatted);
      } catch (err) {
        console.warn("페르소나 목록 로드 실패 (API 서버 확인 필요):", err);
        setPersonas([]);
      }
    };
    fetchPersonas();
  }, []);

  const handleCreateFromText = async () => {
    if (!personaText.trim()) return addToast('페르소나 설명을 입력해주세요.', 'error');
    setIsCreating(true);
    try {
      const res = await pipelineApi.post('/pipeline/personas/create-from-text', {
        text: personaText,
      });
      const { persona_id, structured_persona, persona_summary } = res.data;

      const newPersona = {
        id: persona_id,
        personaId: persona_id,
        name: structured_persona.name,
        age: structured_persona.age,
        gender: structured_persona.gender,
        occupation: structured_persona.occupation,
        skinType: structured_persona.skin_type || [],
        personalColor: structured_persona.personal_color,
        baseColor: structured_persona.shade_number,
        priceRange: structured_persona.shopping_style,
        petInfo: structured_persona.pets || '없음',
        screenTime: structured_persona.digital_device_usage_time || 0,
        preferredColors: structured_persona.preferred_colors || [],
        texturePreference: structured_persona.preferred_texture || [],
        buyingFactor: structured_persona.purchase_decision_factors || [],
        skinConcerns: structured_persona.skin_concerns || [],
        naturalOrganic: (structured_persona.values || []).includes('천연/유기농'),
        veganCrueltyFree: (structured_persona.values || []).includes('비건'),
        aiAnalysis: {
          primary_category: '맞춤형 뷰티',
          reasoning: persona_summary,
        },
      };

      setPersonas(prev => [newPersona, ...prev]);
      addToast('페르소나 생성 완료!', 'success');
      setShowTextModal(false);
      setPersonaText('');
    } catch (error) {
      console.error('페르소나 생성 에러:', error);
      const errMsg = error.response?.data?.detail
        ? (typeof error.response.data.detail === 'string' ? error.response.data.detail : JSON.stringify(error.response.data.detail))
        : error.message;
      addToast(`생성 실패: ${errMsg}`, 'error');
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async (e, id) => {
    e.stopPropagation(); 
    if(window.confirm('정말 삭제하시겠습니까? (DB에서도 완전히 삭제됩니다)')) {
      try {
        await pipelineApi.delete(`/personas/${id}`);
        setPersonas(personas.filter(p => p.id !== id));
        addToast('삭제되었습니다.', 'info');
      } catch (error) {
        console.error("삭제 에러:", error);
        addToast('삭제 실패: 서버 오류', 'error');
      }
    }
  };

  const handleCardClick = (persona) => {
    navigate('/message', { state: { persona } });
  };

  // renderStepContent 제거됨 — 텍스트 입력 방식으로 전환
  const _unused_renderStepContent = () => {
    switch(0) {
      case 1:
        return (
          <>
            <SectionTitle><User size={20}/>기본 정보 설정</SectionTitle>
            <SubLabel>이름 (식별용)</SubLabel>
            <Input value={data.name} onChange={e => handleChange('name', e.target.value)} placeholder="예: 건성 김민수" autoFocus />
            <InputRow style={{marginTop: 15}}>
              <div>
                <SubLabel>나이</SubLabel>
                <Input type="number" value={data.age} onChange={e => handleChange('age', e.target.value)} placeholder="예: 28" />
              </div>
              <div style={{flex:1}}>
                <SubLabel>직업</SubLabel>
                <Select value={data.occupation} onChange={e => handleChange('occupation', e.target.value)}>
                  <option value="" disabled>선택해주세요</option>
                  {OPTIONS.occupations.map(job => (<option key={job} value={job}>{job}</option>))}
                </Select>
              </div>
            </InputRow>
            <SubLabel>성별</SubLabel>
            <IconGrid>
              {OPTIONS.gender.map(opt => (
                <SelectionCard key={opt.label} $selected={data.gender === opt.label} onClick={() => handleChange('gender', opt.label)}>
                  {opt.icon}<span>{opt.label}</span>
                </SelectionCard>
              ))}
            </IconGrid>
          </>
        );
      case 2: 
        return (
          <>
            <SectionTitle><Sparkles size={20}/>피부 상세 프로필</SectionTitle>
            <SubLabel>피부 타입 (복수 선택 가능)</SubLabel>
            <div style={{display:'flex', flexWrap:'wrap', gap:'8px'}}>
              {OPTIONS.skinTypes.map(type => (
                <SelectionCard $chip key={type} $selected={data.skinType.includes(type)} onClick={() => toggleArray('skinType', type)}>
                  <span>{type}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>피부 고민 (복수 선택)</SubLabel>
            <div style={{display:'flex', flexWrap:'wrap', gap:'8px'}}>
              {OPTIONS.skinConcerns.map(concern => (
                <SelectionCard $chip key={concern} $selected={data.skinConcerns.includes(concern)} onClick={() => toggleArray('skinConcerns', concern)}>
                  <span>{concern}</span>
                </SelectionCard>
              ))}
            </div>
          </>
        );
      case 3: 
        return (
          <>
            <SectionTitle><Palette size={20}/>컬러 & 메이크업 프로필</SectionTitle>
            <SubLabel>퍼스널 컬러</SubLabel>
            <div style={{display:'flex', flexWrap:'wrap', gap:'8px'}}>
              {OPTIONS.personalColors.map(color => (
                <SelectionCard $chip key={color} $selected={data.personalColor === color} onClick={() => handleChange('personalColor', color)}>
                  <span>{color}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>선호 호수 (베이스 컬러)</SubLabel>
            <Select value={data.baseColor} onChange={(e) => handleChange('baseColor', e.target.value)}>
               <option value="" disabled>호수 선택 (숫자)</option>
               {OPTIONS.baseColors.map(c => <option key={c} value={c}>{c}호</option>)}
            </Select>
            
            <SubLabel>선호 메이크업 컬러 (복수 선택)</SubLabel>
            <div style={{display:'flex', gap:12, flexWrap:'wrap'}}>
              {OPTIONS.makeupColors.map(color => (
                <div key={color.label} onClick={() => toggleArray('preferredColors', color.label)}
                  style={{display:'flex', flexDirection:'column', alignItems:'center', cursor:'pointer', gap:6,
                    opacity: data.preferredColors.includes(color.label) ? 1 : 0.6,
                    transform: data.preferredColors.includes(color.label) ? 'scale(1.1)' : 'scale(1)', transition: 'all 0.2s'
                  }}>
                  <div style={{width:36, height:36, borderRadius:'50%', background:color.code, 
                    border: data.preferredColors.includes(color.label) ? '3px solid #6B4DFF' : '1px solid #ddd',
                    boxShadow: '0 2px 5px rgba(0,0,0,0.1)'}}/>
                  <span style={{fontSize:12, fontWeight: data.preferredColors.includes(color.label) ? 700 : 400}}>{color.label}</span>
                </div>
              ))}
            </div>
          </>
        );
      case 4: return (
          <>
            <SectionTitle><Droplets size={20}/>성분 & 향 취향</SectionTitle>
            <SubLabel>선호 성분</SubLabel>
            <div style={{display:'flex', flexWrap:'wrap', gap:'8px'}}>
              {OPTIONS.ingredients.map(item => (
                <SelectionCard $chip key={item} $selected={data.preferredIngredients.includes(item)} onClick={() => toggleArray('preferredIngredients', item)}>
                  <span>{item}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>기피 성분</SubLabel>
            <div style={{display:'flex', flexWrap:'wrap', gap:'8px'}}>
              {OPTIONS.avoidedIngredients.map(item => (
                <SelectionCard $chip key={item} $selected={data.avoidedIngredients.includes(item)} onClick={() => toggleArray('avoidedIngredients', item)}
                  style={ data.avoidedIngredients.includes(item) ? { borderColor: '#ff6b6b', backgroundColor: '#ffeaea', color: '#ff4d4d', boxShadow:'none' } : {} }>
                  <span>{item}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>선호 향</SubLabel>
            <div style={{display:'flex', gap:10, flexWrap:'wrap'}}>
              {OPTIONS.scents.map(s => (
                <button key={s} onClick={() => toggleArray('preferredScent', s)}
                  style={{padding: '8px 16px', borderRadius: '20px', border: '1px solid',
                    backgroundColor: data.preferredScent.includes(s) ? '#6B4DFF' : 'white',
                    color: data.preferredScent.includes(s) ? 'white' : '#888',
                    borderColor: data.preferredScent.includes(s) ? '#6B4DFF' : '#ddd', cursor: 'pointer'
                  }}>{s}</button>
              ))}
            </div>
          </>
        );
      case 5: return (
          <>
            <SectionTitle><Heart size={20}/>가치관 및 특수사항</SectionTitle>
            <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:'15px'}}>
              <CheckboxRow><input type="checkbox" checked={data.naturalOrganic} onChange={e => handleChange('naturalOrganic', e.target.checked)} /><span>🌱 천연/유기농 선호</span></CheckboxRow>
              <CheckboxRow><input type="checkbox" checked={data.veganCrueltyFree} onChange={e => handleChange('veganCrueltyFree', e.target.checked)} /><span>🐰 비건/크루얼티프리</span></CheckboxRow>
              <CheckboxRow><input type="checkbox" checked={data.ecoPackaging} onChange={e => handleChange('ecoPackaging', e.target.checked)} /><span>♻️ 친환경 패키징</span></CheckboxRow>
              <CheckboxRow><input type="checkbox" checked={data.pregnancyLactation} onChange={e => handleChange('pregnancyLactation', e.target.checked)} /><span>🤰 임신/수유 중</span></CheckboxRow>
            </div>
            <div style={{marginTop: 30, padding: 20, background: '#f8f9fa', borderRadius: 12, fontSize: 13, color: '#666'}}>
              <strong>💡 중간 확인:</strong><br/>{data.name}님
            </div>
          </>
        );
      case 6: return (
          <>
            <SectionTitle><Moon size={20}/>라이프스타일</SectionTitle>
            <SubLabel>스킨케어 루틴</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.skincareRoutine.map(opt => (
                <SelectionCard key={opt.label} style={{flex:1}} $selected={data.skincareRoutine === opt.label} onClick={() => handleChange('skincareRoutine', opt.label)}>
                  <div style={{marginBottom:4, color: data.skincareRoutine === opt.label ? '#333' : '#aaa'}}>{opt.icon}</div>
                  <span>{opt.label}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>주 활동 환경</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.dailyEnvironment.map(opt => (
                <SelectionCard key={opt.label} style={{flex:1}} $selected={data.dailyEnvironment === opt.label} onClick={() => handleChange('dailyEnvironment', opt.label)}>
                  <div style={{marginBottom:4, color: data.dailyEnvironment === opt.label ? '#333' : '#aaa'}}>{opt.icon}</div>
                  <span>{opt.label}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>선호 제형 (복수 선택 가능)</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.texturePreference.map(opt => (
                <SelectionCard key={opt.label} style={{flex:1}} $selected={data.texturePreference.includes(opt.label)} onClick={() => toggleArray('texturePreference', opt.label)}>
                  <div style={{marginBottom:4, color: data.texturePreference.includes(opt.label) ? '#333' : '#aaa'}}>{opt.icon}</div>
                  <span>{opt.label}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>반려동물 (하나만 선택)</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.petLife.map(opt => (
                <SelectionCard key={opt.label} style={{flex:1}} $selected={data.petInfo === opt.label} onClick={() => handleChange('petInfo', opt.label)}>
                  <div style={{marginBottom:4, color: data.petInfo === opt.label ? '#333' : '#aaa'}}>{opt.icon}</div>
                  <span style={{fontSize: 12}}>{opt.label}</span>
                </SelectionCard>
              ))}
            </div>
            <div style={{display:'flex', gap:12, marginTop:25, borderTop:'1px dashed #eee', paddingTop:25}}>
               <div style={{flex:1}}>
                 <SubLabel>수면 시간 (시간)</SubLabel>
                 <Select value={data.sleepHours} onChange={(e) => handleChange('sleepHours', e.target.value)}>
                   <option value="" disabled>선택</option>
                   {OPTIONS.sleepTimeOptions.map(t => <option key={t} value={t}>{t}시간</option>)}
                 </Select>
               </div>
               <div style={{flex:1}}>
                 <SubLabel>스트레스</SubLabel>
                 <div style={{display:'flex', gap:6}}>
                   {OPTIONS.lifestyle.stress.map(val => (
                     <SelectionCard key={val} style={{flex:1, fontSize:11}} $selected={data.stressLevel === val} onClick={() => handleChange('stressLevel', val)}><span>{val}</span></SelectionCard>
                   ))}
                 </div>
               </div>
            </div>
          </>
        );
      case 7: return (
          <>
            <SectionTitle><MapPin size={20}/>소비 습관</SectionTitle>
            
            <div style={{marginBottom: 30}}>
              <SubLabel>디지털 기기 사용 (일평균)</SubLabel>
              <RangeContainer>
                <RangeHeader><span>사용 시간</span><span style={{fontSize: 16, fontWeight: 'bold'}}>{data.screenTime === 0 ? '사용 안 함' : data.screenTime >= 12 ? '12시간 이상 🔥' : `${data.screenTime}시간`}</span></RangeHeader>
                <RangeSlider min="0" max="12" step="1" value={data.screenTime || 0} style={{ '--value': `${(data.screenTime / 12) * 100}%` }} onChange={(e) => handleChange('screenTime', Number(e.target.value))}/>
                <RangeLabels><span>0시간</span><span>6시간</span><span>12시간+</span></RangeLabels>
              </RangeContainer>
            </div>
            <SubLabel>쇼핑 스타일</SubLabel>
            <div style={{display:'flex', gap:12}}>
              {OPTIONS.spendingStyles.map(opt => (
                <SelectionCard key={opt.label} style={{flex:1, padding:'20px 10px', alignItems:'center', textAlign:'center', gap:'8px'}} $selected={data.priceRange === opt.label} onClick={() => handleChange('priceRange', opt.label)}>
                  <div style={{marginBottom:'4px', color:'#6B4DFF'}}>{opt.icon}</div>
                  <span style={{fontSize:'14px', fontWeight:'bold'}}>{opt.label}</span>
                </SelectionCard>
              ))}
            </div>
            <SubLabel>구매 결정 요인 (복수 선택 가능)</SubLabel>
            <div style={{display:'flex', gap:12}}>
              {OPTIONS.buyingFactors.map(opt => (
                <SelectionCard key={opt.label} style={{flex:1, padding:'20px 10px', alignItems:'center', textAlign:'center', gap:'8px'}} $selected={data.buyingFactor.includes(opt.label)} onClick={() => toggleArray('buyingFactor', opt.label)}>
                  <div style={{marginBottom:'4px', color:'#6B4DFF'}}>{opt.icon}</div>
                  <span style={{fontSize:'14px', fontWeight:'bold'}}>{opt.label}</span>
                </SelectionCard>
              ))}
            </div>
          </>
        );
      default: return null;
    }
  };

  return (
    <Container>
      <Header>
        <div>
          <Title>페르소나 관리</Title>
          <p style={{color:'#666', marginTop:'8px'}}>스킨케어부터 메이크업까지, AI가 맞춤 분석합니다.</p>
        </div>
        <AddButton onClick={() => setShowTextModal(true)}><Plus size={18}/> 새 페르소나 만들기</AddButton>
      </Header>

      {personas.length === 0 && (
        <div style={{textAlign:'center', padding:'60px 0', color:'#888'}}>
          <p>등록된 페르소나가 없습니다. 새로운 페르소나를 추가해보세요!</p>
        </div>
      )}

      <Grid>
        {personas.map(p => (
          <PersonaCard key={p.id} onClick={() => handleCardClick(p)}>
            <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:'15px', borderBottom:'1px solid #f0f0f0', paddingBottom:'15px'}}>
              <div style={{display:'flex', alignItems:'center', gap:'16px'}}>
                <div style={{width:48, height:48, borderRadius:'50%', background:'#F0EBFF', display:'flex', alignItems:'center', justifyContent:'center', color:'#6B4DFF'}}>
                  <User size={24}/>
                </div>
                <div>
                  <div style={{fontWeight:'800', fontSize:'18px', color:'#333'}}>{p.name}</div>
                  <div style={{fontSize:'13px', color:'#888', marginTop:'4px'}}>{p.age}세 · {p.occupation || '직업 미입력'} ({p.gender})</div>
                </div>
              </div>
              <div style={{display:'flex', alignItems:'center', gap:'8px'}}>
                {p.aiAnalysis && <div style={{background:'#6B4DFF', color:'white', padding:'6px 12px', borderRadius:'20px', fontSize:'12px', fontWeight:'bold', boxShadow:'0 4px 10px rgba(107, 77, 255, 0.3)'}}>{p.aiAnalysis.primary_category}</div>}
                <DeleteBtn onClick={(e) => handleDelete(e, p.id)}><Trash2 size={16}/></DeleteBtn>
              </div>
            </div>

            <div style={{fontSize:'13px', color:'#555', display:'flex', flexDirection:'column', gap:'12px'}}>
              <div style={{display:'flex', gap:'6px', flexWrap:'wrap'}}>
                 {p.skinType && p.skinType.map(type => <TagChip key={type} $bg="#F0EBFF" $color="#6B4DFF">{type}</TagChip>)}
                 {p.personalColor && <TagChip>{p.personalColor}</TagChip>}
                 {p.baseColor && <TagChip>{p.baseColor}호</TagChip>}
              </div>

              <div style={{display:'flex', gap:'6px', flexWrap:'wrap', alignItems:'center'}}>
                 <span style={{fontWeight:'bold', width:'50px'}}>취향</span>
                 {p.preferredColors?.length > 0 ? p.preferredColors.slice(0,2).map(c=><TagChip key={c} $bg="#fff0f6" $color="#c41d7f">{c}</TagChip>) : <span style={{color:'#ccc'}}>색상 미선택</span>}
                 {p.texturePreference && p.texturePreference.length > 0 && <TagChip $bg="#e6f7ff" $color="#1890ff">{p.texturePreference[0]}</TagChip>}
              </div>

              <div style={{display:'flex', gap:'6px', flexWrap:'wrap', alignItems:'center'}}>
                 <span style={{fontWeight:'bold', width:'50px'}}>라이프</span>
                 {p.petInfo && p.petInfo !== '없음' && <TagChip $bg="#fff7e6" $color="#d46b08">🐾 {p.petInfo}</TagChip>}
                 {p.screenTime >= 10 && <TagChip $bg="#f6ffed" $color="#389e0d">📱 {p.screenTime}h+</TagChip>}
                 {p.veganCrueltyFree && <TagChip $bg="#f9f0ff" $color="#531dab">비건</TagChip>}
              </div>

              {p.aiAnalysis && (
                <div style={{marginTop:'10px', padding:'12px', background:'#f8f9fa', borderRadius:'12px', fontSize:'12px', color:'#555', lineHeight:'1.5', border: '1px solid #eee'}}>
                  <strong>페르소나 요약:</strong> {p.aiAnalysis.reasoning}
                </div>
              )}
            </div>
          </PersonaCard>
        ))}
      </Grid>

      {showTextModal && (
        <ModalOverlay onClick={() => { if (!isCreating) { setShowTextModal(false); setPersonaText(''); } }}>
          <ModalBox onClick={e => e.stopPropagation()} style={{maxWidth: 560}}>

            {isCreating && (
              <AnalyzingOverlay>
                <PulseRing>
                  <Sparkles size={32} color="#6B4DFF" fill="#6B4DFF" />
                </PulseRing>
                <LoadingText>
                  페르소나를 생성 중입니다...
                  <span>입력 내용을 분석하고 검색 쿼리를 생성하는 중</span>
                </LoadingText>
              </AnalyzingOverlay>
            )}

            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'20px'}}>
              <h2 style={{fontSize:'20px', fontWeight:'bold', color:'#333', margin:0}}>새 페르소나 만들기</h2>
              <X style={{cursor:'pointer', color:'#999'}} onClick={() => { if (!isCreating) { setShowTextModal(false); setPersonaText(''); } }}/>
            </div>

            <p style={{fontSize:'14px', color:'#666', marginBottom:'16px', lineHeight:'1.6'}}>
              고객의 특성을 자유롭게 입력해주세요. AI가 자동으로 구조화하고 검색 쿼리를 생성합니다.
            </p>

            <textarea
              value={personaText}
              onChange={e => setPersonaText(e.target.value)}
              placeholder="예) 28살 직장인 여성, 지성·복합성 피부, 여드름과 모공 고민, 히알루론산 선호, 알코올 기피, 가성비 쇼핑 선호..."
              disabled={isCreating}
              style={{
                width: '100%', minHeight: '160px', padding: '14px', fontSize: '14px',
                border: '1px solid #ddd', borderRadius: '12px', resize: 'vertical',
                outline: 'none', fontFamily: 'inherit', lineHeight: '1.6',
                boxSizing: 'border-box',
                transition: '0.2s',
              }}
              onFocus={e => e.target.style.borderColor = '#6B4DFF'}
              onBlur={e => e.target.style.borderColor = '#ddd'}
              autoFocus
            />

            <ButtonGroup>
              <NavButton onClick={() => { setShowTextModal(false); setPersonaText(''); }} disabled={isCreating}>
                취소
              </NavButton>
              <NavButton $primary onClick={handleCreateFromText} disabled={isCreating || !personaText.trim()}>
                <Sparkles size={16} style={{marginBottom:-2, marginRight:6}}/>
                {isCreating ? '생성 중...' : '페르소나 생성'}
              </NavButton>
            </ButtonGroup>
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}