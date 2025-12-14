import React, { useState, useEffect } from 'react';
import styled, { css } from 'styled-components';
import { 
  Plus, X, User, Trash2, Check, 
  Droplets, Sun, Zap, Frown, Smile, Moon, Utensils, 
  Dumbbell, Wallet, ShoppingBag, Sparkles, AlertCircle,
  Thermometer, MapPin, Wind, Monitor, Clock, Heart, 
  ChevronRight, ChevronLeft
} from 'lucide-react';

/* --- [1] 데이터 및 옵션 설정 (Persona.jsx의 로직 기반 + 아이콘 매핑) --- */
const OPTIONS = {
  gender: [
    { label: '여성', icon: <User size={20}/> },
    { label: '남성', icon: <User size={20}/> },
    { label: '기타', icon: <Smile size={20}/> }
  ],
  skinType: [
    { label: '건성', icon: <Droplets size={20}/> },
    { label: '지성', icon: <Sun size={20}/> },
    { label: '복합성', icon: <Sparkles size={20}/> },
    { label: '중성', icon: <Smile size={20}/> },
    { label: '민감성', icon: <Zap size={20}/> },
  ],
  skinConcerns: [
    { label: '트러블/여드름', icon: <AlertCircle size={20}/> },
    { label: '속건조', icon: <Droplets size={20}/> },
    { label: '주름/노화', icon: <Frown size={20}/> },
    { label: '칙칙함/미백', icon: <Sun size={20}/> },
    { label: '넓은모공', icon: <div style={{width:20, height:20, border:'2px dotted currentColor', borderRadius:'50%'}}/> },
    { label: '민감성/홍조', icon: <Zap size={20}/> },
  ],
  ingredients: ['히알루론산', '나이아신아마이드', '레티놀', '비타민C', '펩타이드', 'AHA', 'BHA', '세라마이드', '콜라겐', '알부틴'],
  avoidedIngredients: ['파라벤', '알코올', '인공향료', '인공색소', '미네랄오일', '실리콘', 'SLS/SLES', '합성방부제'],
  scents: ['무향', '플로럴', '시트러스', '허브', '우디', '머스크'],
  priceRange: ['1만원이하', '1-3만원', '3-5만원', '5-10만원', '10만원이상'],
  lifestyle: {
    sleep: ['6시간 미만', '6~7시간', '8시간 이상'], 
    stress: ['낮음', '보통', '높음'],
    diet: ['클린식단', '보통', '배달/자극적'],
    exercise: ['주0회', '주1-2회', '주3-4회', '주5회이상']
  }
};

/* --- [2] 스타일 컴포넌트 (백업 파일 디자인 유지) --- */
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
  background: white; border-radius: 20px; padding: 24px;
  border: 1px solid #eee; box-shadow: 0 4px 20px rgba(0,0,0,0.05);
  position: relative; transition: 0.2s;
  &:hover { transform: translateY(-5px); box-shadow: 0 8px 25px rgba(107, 77, 255, 0.15); border-color: #d0c4ff; }
`;
const DeleteBtn = styled.button`
  position: absolute; top: 20px; right: 20px;
  background: none; border: none; color: #ddd; cursor: pointer;
  &:hover { color: #ff4d4d; }
`;
const ModalOverlay = styled.div`
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background-color: rgba(0, 0, 0, 0.6);
  display: flex; justify-content: center; align-items: center;
  z-index: 1000; backdrop-filter: blur(5px);
`;
const ModalBox = styled.div`
  background: white; width: 700px; max-height: 90vh; overflow-y: auto;
  border-radius: 24px; padding: 40px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  display: flex; flex-direction: column;

  &::-webkit-scrollbar { width: 8px; }
  &::-webkit-scrollbar-thumb { background-color: #ddd; border-radius: 4px; }
`;
const SectionTitle = styled.h3`
  font-size: 18px; font-weight: 700; color: #6B4DFF;
  margin: 0 0 16px 0; display: flex; align-items: center; gap: 8px;
`;
const SubLabel = styled.div`
  font-size: 14px; font-weight: 600; color: #555; margin-bottom: 8px; margin-top: 20px;
`;
const IconGrid = styled.div`
  display: grid; 
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); 
  gap: 10px;
`;
const SelectionCard = styled.div`
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 12px 8px; gap: 6px;
  border: 2px solid #f4f4f4; border-radius: 12px;
  cursor: pointer; transition: all 0.2s;
  background: #fafafa; color: #888;
  
  &:hover { border-color: #d0c4ff; background: #f8f6ff; color: #6B4DFF; }
  
  ${props => props.$selected && css`
    border-color: #6B4DFF; background-color: #6B4DFF; color: white;
    box-shadow: 0 4px 12px rgba(107, 77, 255, 0.3);
    &:hover { background-color: #5a3de0; color: white; border-color: #5a3de0; }
  `}
  
  /* 작은 칩 스타일 (텍스트 위주) */
  ${props => props.$chip && css`
    flex-direction: row; padding: 10px 14px; font-size: 13px;
    background: white;
  `}

  span { font-size: 13px; font-weight: 600; text-align: center; }
`;

const InputRow = styled.div`
  display: flex; gap: 12px; margin-bottom: 10px;
`;
const Input = styled.input`
  flex: 1; padding: 14px; border: 1px solid #ddd; border-radius: 10px;
  font-size: 14px; outline: none; transition: 0.2s;
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); }
`;
const StyledRange = styled.input`
  width: 100%; cursor: pointer; accent-color: #6B4DFF; margin-top: 10px;
`;
const CheckboxRow = styled.label`
  display: flex; align-items: center; gap: 8px; cursor: pointer; 
  padding: 12px; border-radius: 8px; background: #f9f9f9;
  &:hover { background: #f0ebff; }
  input { accent-color: #6B4DFF; transform: scale(1.2); }
`;
const ButtonGroup = styled.div`
  display: flex; gap: 12px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;
`;
const NavButton = styled.button`
  flex: 1; padding: 16px; border-radius: 12px; border: none; font-weight: 700; font-size: 16px; cursor: pointer;
  ${props => props.$primary ? css`
    background-color: #6B4DFF; color: white;
    &:hover { background-color: #5a3de0; }
  ` : css`
    background-color: #f0f0f0; color: #555;
    &:hover { background-color: #e0e0e0; }
  `}
`;
const ProgressBar = styled.div`
  height: 6px; background: #f0f0f0; border-radius: 3px; margin-bottom: 30px; overflow: hidden;
  div { height: 100%; background: linear-gradient(90deg, #6B4DFF, #9D8CFF); transition: width 0.3s ease; }
`;

/* --- [3] 메인 컴포넌트 --- */
export default function PersonaManager() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [personas, setPersonas] = useState(() => {
    const saved = localStorage.getItem('personas');
    return saved ? JSON.parse(saved) : [];
  });

  // Persona.jsx의 모든 데이터 필드 포함 + name 추가
  const initialData = {
    name: '', // 백업 파일의 카드 표시용
    age: '', gender: '', skinType: '', skinTone: '', skinConcerns: [],
    sensitivityLevel: '중', moistureLevel: 50, oilLevel: 50,
    preferredIngredients: [], avoidedIngredients: [],
    texturePreference: [], preferredScent: [], priceRange: '',
    sleepHours: '', stressLevel: '', dietQuality: '', exerciseFrequency: '',
    occupation: '', location: '', climate: '',
    screenTime: '', makeupFrequency: '',
    naturalOrganic: false, veganCrueltyFree: false, ecoPackaging: false,
    multiFunctionPreference: false, pregnancyLactation: false
  };

  const [data, setData] = useState(initialData);

  useEffect(() => {
    localStorage.setItem('personas', JSON.stringify(personas));
  }, [personas]);

  // 핸들러들
  const handleChange = (field, value) => setData(prev => ({ ...prev, [field]: value }));
  
  const toggleArray = (field, value) => {
    setData(prev => ({
      ...prev,
      [field]: prev[field].includes(value) 
        ? prev[field].filter(i => i !== value)
        : [...prev[field], value]
    }));
  };

  const handleSave = () => {
    if (!data.name) return alert('페르소나 이름을 입력해주세요.');
    const newPersona = { id: Date.now(), ...data };
    setPersonas([...personas, newPersona]);
    closeModal();
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setStep(1);
    setData(initialData);
  };

  const handleDelete = (id) => {
    if(window.confirm('정말 삭제하시겠습니까?')) setPersonas(personas.filter(p => p.id !== id));
  };

  // 단계별 렌더링 컨텐츠
  const renderStepContent = () => {
    switch(step) {
      case 1: // 기본 정보
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
                <Input value={data.occupation} onChange={e => handleChange('occupation', e.target.value)} placeholder="예: 직장인" />
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
      case 2: // 피부 정보
        return (
          <>
            <SectionTitle><Sparkles size={20}/>피부 프로필</SectionTitle>
            
            <SubLabel>피부 타입</SubLabel>
            <IconGrid>
              {OPTIONS.skinType.map(opt => (
                <SelectionCard key={opt.label} $selected={data.skinType === opt.label} onClick={() => handleChange('skinType', opt.label)}>
                  {opt.icon}<span>{opt.label}</span>
                </SelectionCard>
              ))}
            </IconGrid>

            <SubLabel>주요 피부 고민 (중복 선택)</SubLabel>
            <IconGrid>
              {OPTIONS.skinConcerns.map(opt => (
                <SelectionCard key={opt.label} $selected={data.skinConcerns.includes(opt.label)} onClick={() => toggleArray('skinConcerns', opt.label)}>
                  {opt.icon}<span>{opt.label}</span>
                </SelectionCard>
              ))}
            </IconGrid>

            <div style={{display:'flex', gap:20, marginTop:20}}>
              <div style={{flex:1}}>
                <SubLabel>수분도 {data.moistureLevel}%</SubLabel>
                <StyledRange type="range" min="0" max="100" value={data.moistureLevel} onChange={e => handleChange('moistureLevel', e.target.value)}/>
              </div>
              <div style={{flex:1}}>
                <SubLabel>유분도 {data.oilLevel}%</SubLabel>
                <StyledRange type="range" min="0" max="100" value={data.oilLevel} onChange={e => handleChange('oilLevel', e.target.value)}/>
              </div>
            </div>
          </>
        );
      case 3: // 성분 및 선호
        return (
          <>
            <SectionTitle><Utensils size={20}/>성분 및 텍스처</SectionTitle>
            
            <SubLabel>선호 성분</SubLabel>
            <IconGrid>
              {OPTIONS.ingredients.map(item => (
                <SelectionCard $chip key={item} $selected={data.preferredIngredients.includes(item)} onClick={() => toggleArray('preferredIngredients', item)}>
                  <span>{item}</span>
                </SelectionCard>
              ))}
            </IconGrid>

            <SubLabel>기피 성분</SubLabel>
            <IconGrid>
              {OPTIONS.avoidedIngredients.map(item => (
                <SelectionCard $chip key={item} $selected={data.avoidedIngredients.includes(item)} onClick={() => toggleArray('avoidedIngredients', item)} style={{color: data.avoidedIngredients.includes(item) ? 'white' : '#ff6b6b', borderColor: data.avoidedIngredients.includes(item) ? '#ff6b6b' : '#ffeaea', backgroundColor: data.avoidedIngredients.includes(item) ? '#ff6b6b' : '#fff'}}>
                  <span>{item}</span>
                </SelectionCard>
              ))}
            </IconGrid>

            <SubLabel>선호 향</SubLabel>
            <div style={{display:'flex', gap:10, flexWrap:'wrap'}}>
              {OPTIONS.scents.map(s => (
                <button 
                  key={s}
                  onClick={() => toggleArray('preferredScent', s)}
                  style={{
                    padding: '8px 16px', borderRadius: '20px', border: '1px solid',
                    backgroundColor: data.preferredScent.includes(s) ? '#6B4DFF' : 'white',
                    color: data.preferredScent.includes(s) ? 'white' : '#888',
                    borderColor: data.preferredScent.includes(s) ? '#6B4DFF' : '#ddd',
                    cursor: 'pointer'
                  }}
                >{s}</button>
              ))}
            </div>
          </>
        );
      case 4: // 라이프스타일
        return (
          <>
            <SectionTitle><Moon size={20}/>라이프스타일</SectionTitle>
            
            <SubLabel>수면 시간</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.sleep.map(val => (
                <SelectionCard key={val} style={{flex:1}} $selected={data.sleepHours === val} onClick={() => handleChange('sleepHours', val)}><span>{val}</span></SelectionCard>
              ))}
            </div>

            <SubLabel>스트레스 수준</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.stress.map(val => (
                <SelectionCard key={val} style={{flex:1}} $selected={data.stressLevel === val} onClick={() => handleChange('stressLevel', val)}><span>{val}</span></SelectionCard>
              ))}
            </div>

            <SubLabel>운동 빈도</SubLabel>
            <div style={{display:'flex', gap:10}}>
              {OPTIONS.lifestyle.exercise.map(val => (
                <SelectionCard key={val} style={{flex:1}} $selected={data.exerciseFrequency === val} onClick={() => handleChange('exerciseFrequency', val)}><span>{val}</span></SelectionCard>
              ))}
            </div>
          </>
        );
      case 5: // 환경 및 습관
        return (
          <>
            <SectionTitle><MapPin size={20}/>환경 및 습관</SectionTitle>
            <InputRow>
              <div style={{flex:1}}>
                 <SubLabel>거주 지역</SubLabel>
                 <Input value={data.location} onChange={e => handleChange('location', e.target.value)} placeholder="예: 서울" />
              </div>
              <div style={{flex:1}}>
                 <SubLabel>디지털 기기 사용</SubLabel>
                 <Input value={data.screenTime} onChange={e => handleChange('screenTime', e.target.value)} placeholder="예: 8시간 이상" />
              </div>
            </InputRow>
            <SubLabel>쇼핑 예산 (개당)</SubLabel>
            <IconGrid>
                {OPTIONS.priceRange.map(p => (
                   <SelectionCard $chip key={p} $selected={data.priceRange === p} onClick={() => handleChange('priceRange', p)}><span>{p}</span></SelectionCard>
                ))}
            </IconGrid>
          </>
        );
      case 6: // 가치관
        return (
          <>
            <SectionTitle><Heart size={20}/>가치관 및 특수사항</SectionTitle>
            <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:'15px'}}>
              <CheckboxRow>
                <input type="checkbox" checked={data.naturalOrganic} onChange={e => handleChange('naturalOrganic', e.target.checked)} />
                <span>🌱 천연/유기농 선호</span>
              </CheckboxRow>
              <CheckboxRow>
                <input type="checkbox" checked={data.veganCrueltyFree} onChange={e => handleChange('veganCrueltyFree', e.target.checked)} />
                <span>🐰 비건/크루얼티프리</span>
              </CheckboxRow>
              <CheckboxRow>
                <input type="checkbox" checked={data.ecoPackaging} onChange={e => handleChange('ecoPackaging', e.target.checked)} />
                <span>♻️ 친환경 패키징</span>
              </CheckboxRow>
              <CheckboxRow>
                <input type="checkbox" checked={data.pregnancyLactation} onChange={e => handleChange('pregnancyLactation', e.target.checked)} />
                <span>🤰 임신/수유 중</span>
              </CheckboxRow>
            </div>
            
            <div style={{marginTop: 30, padding: 20, background: '#f8f9fa', borderRadius: 12, fontSize: 13, color: '#666'}}>
              <strong>💡 입력 확인:</strong><br/>
              {data.name}님은 {data.skinType} 피부이며, {data.skinConcerns.join(', ')} 고민을 가지고 있습니다.
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
          <p style={{color:'#666', marginTop:'8px'}}>AI 마케팅을 위한 상세 고객 페르소나를 정의합니다.</p>
        </div>
        <AddButton onClick={() => setIsModalOpen(true)}><Plus size={18}/> 새 페르소나 만들기</AddButton>
      </Header>

      <Grid>
        {personas.map(p => (
          <PersonaCard key={p.id}>
            <DeleteBtn onClick={() => handleDelete(p.id)}><Trash2 size={16}/></DeleteBtn>
            <div style={{display:'flex', alignItems:'center', gap:'16px', marginBottom:'20px', borderBottom:'1px solid #f0f0f0', paddingBottom:'20px'}}>
              <div style={{width:48, height:48, borderRadius:'50%', background:'#F0EBFF', display:'flex', alignItems:'center', justifyContent:'center', color:'#6B4DFF'}}>
                <User size={24}/>
              </div>
              <div>
                <div style={{fontWeight:'800', fontSize:'18px', color:'#333'}}>{p.name}</div>
                <div style={{fontSize:'13px', color:'#888', marginTop:'4px'}}>{p.age}세 · {p.occupation || '직업 미입력'} ({p.gender})</div>
              </div>
            </div>
            <div style={{fontSize:'13px', color:'#555', display:'flex', flexDirection:'column', gap:'10px'}}>
              <div><strong>🧴 피부:</strong> {p.skinType} <span style={{color:'#ddd'}}>|</span> {p.skinConcerns.slice(0,2).join(', ')}{p.skinConcerns.length > 2 && '...'}</div>
              <div><strong>🌡 상태:</strong> 수분 {p.moistureLevel}% / 유분 {p.oilLevel}%</div>
              <div><strong>🛍 예산:</strong> {p.priceRange || '미정'}</div>
              <div style={{marginTop:'5px', display:'flex', gap:'5px', flexWrap:'wrap'}}>
                {p.naturalOrganic && <span style={{background:'#e6fcf5', color:'#0ca678', padding:'2px 6px', borderRadius:'4px', fontSize:'11px'}}>유기농</span>}
                {p.veganCrueltyFree && <span style={{background:'#fff3bf', color:'#f08c00', padding:'2px 6px', borderRadius:'4px', fontSize:'11px'}}>비건</span>}
              </div>
            </div>
          </PersonaCard>
        ))}
      </Grid>

      {isModalOpen && (
        <ModalOverlay onClick={closeModal}>
          <ModalBox onClick={e => e.stopPropagation()}>
            <div style={{display:'flex', justifyContent:'space-between', marginBottom:'10px'}}>
              <h2 style={{fontSize:'20px', fontWeight:'bold', color:'#333'}}>페르소나 생성 (Step {step}/6)</h2>
              <X style={{cursor:'pointer', color:'#999'}} onClick={closeModal}/>
            </div>

            <ProgressBar><div style={{width: `${(step/6)*100}%`}}/></ProgressBar>

            <div style={{flex: 1, overflowY:'auto', paddingRight:'5px'}}>
              {renderStepContent()}
            </div>

            <ButtonGroup>
              {step > 1 && (
                <NavButton onClick={() => setStep(step - 1)}>
                   <ChevronLeft size={16} style={{marginBottom:-2, marginRight:5}}/>이전
                </NavButton>
              )}
              {step < 6 ? (
                <NavButton $primary onClick={() => setStep(step + 1)}>
                  다음<ChevronRight size={16} style={{marginBottom:-2, marginLeft:5}}/>
                </NavButton>
              ) : (
                <NavButton $primary onClick={handleSave}>
                  <Check size={16} style={{marginBottom:-2, marginLeft:5}}/> 완료 및 저장
                </NavButton>
              )}
            </ButtonGroup>
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}