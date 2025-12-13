import React, { useState, useEffect } from 'react';
import styled, { css } from 'styled-components';
import { 
  Plus, X, User, Trash2, Check, 
  Droplets, Sun, Zap, Frown, Smile, Moon, Utensils, 
  Dumbbell, Wallet, ShoppingBag, Sparkles, AlertCircle,
  ChevronDown, ChevronUp // 화살표 아이콘 추가
} from 'lucide-react';

/* --- [1] 데이터 및 옵션 설정 --- */
const OPTIONS = {
  skinType: [
    { label: '건성', icon: <Droplets size={20}/> },
    { label: '지성', icon: <Sun size={20}/> },
    { label: '수부지', icon: <Sparkles size={20}/> },
    { label: '민감성', icon: <Zap size={20}/> },
  ],
  concerns: [
    { label: '트러블/여드름', icon: <AlertCircle size={20}/> },
    { label: '속건조', icon: <Droplets size={20}/> },
    { label: '주름/탄력', icon: <Frown size={20}/> },
    { label: '칙칙함/미백', icon: <Sun size={20}/> },
    { label: '모공', icon: <div style={{width:20, height:20, border:'2px dotted currentColor', borderRadius:'50%'}}/> },
  ],
  lifestyle: {
    sleep: ['6시간 미만', '6~7시간', '8시간 이상'], 
    stress: ['낮음', '보통', '높음'],
    diet: ['배달/자극적', '불규칙', '클린식단'],
  },
  shopping: {
    budget: [
      { label: '가성비 중시', desc: '세일/1+1 선호', icon: <Wallet size={20}/> },
      { label: '효능 중시', desc: '가격보다 효과', icon: <Sparkles size={20}/> },
      { label: '프리미엄', desc: '백화점/럭셔리', icon: <ShoppingBag size={20}/> },
    ]
  }
};

/* --- [2] 스타일 컴포넌트 --- */
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  font-family: 'Pretendard', sans-serif;
  color: #333;
`;

const Header = styled.div`
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;
`;

const Title = styled.h1`
  font-size: 24px; font-weight: 800; color: #111;
`;

const AddButton = styled.button`
  display: flex; align-items: center; gap: 8px;
  background-color: #6B4DFF; color: white;
  padding: 12px 20px; border-radius: 8px; border: none;
  font-weight: 700; cursor: pointer;
  &:hover { background-color: #5a3de0; }
`;

const Grid = styled.div`
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 24px;
`;

const PersonaCard = styled.div`
  background: white; border-radius: 16px; padding: 24px;
  border: 1px solid #eee; box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  position: relative;
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
  z-index: 1000; backdrop-filter: blur(4px);
`;

const ModalBox = styled.div`
  background: white; width: 600px; max-height: 90vh; overflow-y: auto;
  border-radius: 20px; padding: 40px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);

  &::-webkit-scrollbar { width: 8px; }
  &::-webkit-scrollbar-thumb { background-color: #ddd; border-radius: 4px; }
`;

const SectionTitle = styled.h3`
  font-size: 16px; font-weight: 700; color: #6B4DFF;
  margin: 24px 0 12px 0; display: flex; align-items: center; gap: 6px;
  &:first-child { margin-top: 0; }
`;

const IconGrid = styled.div`
  display: grid; 
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr)); 
  gap: 10px;
`;

const SelectionCard = styled.div`
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 16px 10px; gap: 8px;
  border: 2px solid #f0f0f0; border-radius: 12px;
  cursor: pointer; transition: all 0.2s;
  background: #fafafa; color: #888;
  svg { transition: transform 0.2s; }
  &:hover {
    border-color: #d0c4ff;
    background: #f8f6ff;
    color: #6B4DFF;
    transform: translateY(-2px);
  }
  ${props => props.$selected && css`
    border-color: #6B4DFF;
    background-color: #6B4DFF;
    color: white;
    box-shadow: 0 4px 12px rgba(107, 77, 255, 0.3);
    &:hover { background-color: #5a3de0; color: white; }
  `}
  span { font-size: 13px; font-weight: 600; text-align: center; }
  small { font-size: 11px; font-weight: 400; opacity: 0.8; }
`;

const InputRow = styled.div`
  display: flex; gap: 12px; margin-bottom: 10px;
`;

const Input = styled.input`
  flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 8px;
  font-size: 14px; outline: none;
  &:focus { border-color: #6B4DFF; }
`;

/* --- [New] 상세 설정 토글 버튼 스타일 --- */
const AdvancedToggleBtn = styled.button`
  width: 100%;
  padding: 12px;
  margin-top: 20px;
  margin-bottom: 10px;
  border: 1px dashed #ccc;
  border-radius: 10px;
  background: #fdfdfd;
  color: #666;
  font-weight: 600;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: #f5f5f5;
    color: #6B4DFF;
    border-color: #6B4DFF;
  }
`;

const SaveButton = styled.button`
  width: 100%; padding: 16px; margin-top: 20px;
  background-color: #222; color: white;
  font-size: 16px; font-weight: bold; border-radius: 12px; border: none;
  cursor: pointer; transition: background 0.2s;
  &:hover { background-color: #000; }
`;

/* --- [3] 메인 컴포넌트 --- */
export default function PersonaManager() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  
  // 상세 설정(피부, 라이프스타일 등)이 열려있는지 여부
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [personas, setPersonas] = useState(() => {
    const saved = localStorage.getItem('personas');
    return saved ? JSON.parse(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem('personas', JSON.stringify(personas));
  }, [personas]);

  const [form, setForm] = useState({
    name: '', age: '', job: '',
    skinType: [], concerns: [], sleep: '', stress: '', diet: '', budget: ''
  });

  const toggleMulti = (field, value) => {
    setForm(prev => {
      const list = prev[field];
      return list.includes(value) 
        ? { ...prev, [field]: list.filter(item => item !== value) }
        : { ...prev, [field]: [...list, value] };
    });
  };

  const setSingle = (field, value) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  const handleText = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSave = () => {
    if (!form.name) return alert('이름을 입력해주세요.');
    
    // 필수 입력 체크: 피부 타입을 선택 안했으면 상세 설정을 열어줌
    if (form.skinType.length === 0) {
      if (!showAdvanced) {
        setShowAdvanced(true); // 닫혀있으면 열어줌
      }
      return alert('피부 타입을 최소 1개 선택해주세요.');
    }

    const newPersona = { id: Date.now(), ...form };
    setPersonas([...personas, newPersona]);
    setForm({ name: '', age: '', job: '', skinType: [], concerns: [], sleep: '', stress: '', diet: '', budget: '' });
    setShowAdvanced(false); // 저장 후엔 다시 닫음
    setIsModalOpen(false);
  };

  const handleDelete = (id) => {
    if(window.confirm('삭제하시겠습니까?')) setPersonas(personas.filter(p => p.id !== id));
  };

  return (
    <Container>
      <Header>
        <div>
          <Title>페르소나 관리</Title>
          <p style={{color:'#666', fontSize:'14px', marginTop:'5px'}}>마케팅 타겟(고객)을 정의하고 AI 분석을 준비합니다.</p>
        </div>
        <AddButton onClick={() => setIsModalOpen(true)}><Plus size={18}/> 페르소나 추가</AddButton>
      </Header>

      <Grid>
        {personas.map(p => (
          <PersonaCard key={p.id}>
            <DeleteBtn onClick={() => handleDelete(p.id)}><Trash2 size={16}/></DeleteBtn>
            <div style={{display:'flex', alignItems:'center', gap:'12px', marginBottom:'15px', borderBottom:'1px solid #f0f0f0', paddingBottom:'15px'}}>
              <div style={{width:40, height:40, borderRadius:'50%', background:'#F0EBFF', display:'flex', alignItems:'center', justifyContent:'center', color:'#6B4DFF'}}>
                <User size={20}/>
              </div>
              <div>
                <div style={{fontWeight:'bold', fontSize:'18px'}}>{p.name}</div>
                <div style={{fontSize:'13px', color:'#888'}}>{p.age} · {p.job}</div>
              </div>
            </div>
            <div style={{fontSize:'13px', color:'#555', display:'flex', flexDirection:'column', gap:'8px'}}>
              <div><strong>🧴 피부:</strong> {p.skinType.join(', ')} ({p.concerns.join(', ')})</div>
              <div><strong>🌙 라이프:</strong> {p.sleep} / 스트레스 {p.stress}</div>
              <div><strong>💰 쇼핑성향:</strong> {p.budget}</div>
            </div>
          </PersonaCard>
        ))}
      </Grid>

      {/* --- 페르소나 생성 모달 --- */
      isModalOpen && (
        <ModalOverlay onClick={() => setIsModalOpen(false)}>
          <ModalBox onClick={e => e.stopPropagation()}>
            <div style={{display:'flex', justifyContent:'space-between', marginBottom:'20px'}}>
              <h2 style={{fontSize:'22px', fontWeight:'bold'}}>새 페르소나 정의</h2>
              <X style={{cursor:'pointer'}} onClick={() => setIsModalOpen(false)}/>
            </div>

            {/* 기본 정보 (항상 보임) */}
            <SectionTitle><User size={18}/>기본 정보</SectionTitle>
            <InputRow>
              <Input name="name" placeholder="이름 (예: 김아모)" value={form.name} onChange={handleText} />
              <Input name="age" placeholder="나이 (예: 20대 후반)" value={form.age} onChange={handleText} />
              <Input name="job" placeholder="직업 (예: 직장인)" value={form.job} onChange={handleText} />
            </InputRow>

            {/* --- [New] 상세 설정 토글 버튼 --- */}
            <AdvancedToggleBtn onClick={() => setShowAdvanced(!showAdvanced)}>
              {showAdvanced ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
              {showAdvanced ? '상세 정보 접기' : '피부 및 라이프스타일 설정 (클릭)'}
            </AdvancedToggleBtn>

            {/* 상세 정보 영역 (토글됨) */}
            {showAdvanced && (
              <div style={{animation: 'fadeIn 0.3s ease-in-out'}}>
                {/* STEP 2: 피부 프로필 */}
                <SectionTitle><Sparkles size={18}/>피부 타입 & 고민</SectionTitle>
                <div style={{marginBottom:'10px', fontSize:'13px', fontWeight:'bold', color:'#555'}}>피부 타입</div>
                <IconGrid style={{marginBottom:'15px'}}>
                  {OPTIONS.skinType.map(opt => (
                    <SelectionCard 
                      key={opt.label} 
                      $selected={form.skinType.includes(opt.label)}
                      onClick={() => toggleMulti('skinType', opt.label)}
                    >
                      {opt.icon}
                      <span>{opt.label}</span>
                    </SelectionCard>
                  ))}
                </IconGrid>
                
                <div style={{marginBottom:'10px', fontSize:'13px', fontWeight:'bold', color:'#555'}}>주요 고민</div>
                <IconGrid>
                  {OPTIONS.concerns.map(opt => (
                    <SelectionCard 
                      key={opt.label} 
                      $selected={form.concerns.includes(opt.label)}
                      onClick={() => toggleMulti('concerns', opt.label)}
                    >
                      {opt.icon}
                      <span>{opt.label}</span>
                    </SelectionCard>
                  ))}
                </IconGrid>

                {/* STEP 3: 라이프스타일 */}
                <SectionTitle style={{marginTop:'30px'}}><Moon size={18}/>라이프스타일</SectionTitle>
                <div style={{display:'flex', flexDirection:'column', gap:'12px'}}>
                  <div style={{display:'flex', gap:'10px', alignItems:'center'}}>
                    <span style={{fontSize:'13px', width:'60px', fontWeight:'bold'}}>수면시간</span>
                    <div style={{display:'flex', gap:'5px', flex:1}}>
                      {OPTIONS.lifestyle.sleep.map(val => (
                        <SelectionCard key={val} style={{flex:1, padding:'10px'}} $selected={form.sleep === val} onClick={() => setSingle('sleep', val)}>
                          <span style={{fontSize:'12px'}}>{val}</span>
                        </SelectionCard>
                      ))}
                    </div>
                  </div>
                  <div style={{display:'flex', gap:'10px', alignItems:'center'}}>
                    <span style={{fontSize:'13px', width:'60px', fontWeight:'bold'}}>스트레스</span>
                    <div style={{display:'flex', gap:'5px', flex:1}}>
                      {OPTIONS.lifestyle.stress.map(val => (
                        <SelectionCard key={val} style={{flex:1, padding:'10px'}} $selected={form.stress === val} onClick={() => setSingle('stress', val)}>
                          <span style={{fontSize:'12px'}}>{val}</span>
                        </SelectionCard>
                      ))}
                    </div>
                  </div>
                  <div style={{display:'flex', gap:'10px', alignItems:'center'}}>
                    <span style={{fontSize:'13px', width:'60px', fontWeight:'bold'}}>식습관</span>
                    <div style={{display:'flex', gap:'5px', flex:1}}>
                      {OPTIONS.lifestyle.diet.map(val => (
                        <SelectionCard key={val} style={{flex:1, padding:'10px'}} $selected={form.diet === val} onClick={() => setSingle('diet', val)}>
                          <span style={{fontSize:'12px'}}>{val}</span>
                        </SelectionCard>
                      ))}
                    </div>
                  </div>
                </div>

                {/* STEP 4: 쇼핑 성향 */}
                <SectionTitle style={{marginTop:'30px'}}><ShoppingBag size={18}/>쇼핑 성향</SectionTitle>
                <IconGrid>
                  {OPTIONS.shopping.budget.map(opt => (
                    <SelectionCard 
                      key={opt.label} 
                      $selected={form.budget === opt.label}
                      onClick={() => setSingle('budget', opt.label)}
                    >
                      {opt.icon}
                      <span>{opt.label}</span>
                      <small>{opt.desc}</small>
                    </SelectionCard>
                  ))}
                </IconGrid>
              </div>
            )}

            <SaveButton onClick={handleSave}>페르소나 저장하기</SaveButton>
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}