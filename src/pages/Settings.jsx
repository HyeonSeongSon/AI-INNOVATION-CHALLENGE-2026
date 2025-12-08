import React, { useState } from 'react';
import styled from 'styled-components';
import { Key, Save, Eye, EyeOff, Sliders, Bell, Globe, ShieldCheck } from 'lucide-react';

/* --- 스타일 컴포넌트 --- */
const Container = styled.div`
  max-width: 800px; /* 설정창은 너무 넓지 않게 */
  margin: 0 auto;
  padding-bottom: 60px;
`;

const Header = styled.div`
  margin-bottom: 30px;
`;

const Title = styled.h1`
  font-size: 24px;
  font-weight: 800;
  color: #333;
`;

const SubDesc = styled.p`
  color: #666;
  margin-top: 8px;
  font-size: 14px;
`;

/* 섹션 카드 공통 스타일 */
const SectionCard = styled.div`
  background: white;
  border-radius: 16px;
  border: 1px solid #eee;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  padding: 30px;
  margin-bottom: 24px;
`;

const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 24px;
  padding-bottom: 15px;
  border-bottom: 1px solid #f0f0f0;

  h3 { font-size: 18px; font-weight: 700; color: #333; }
  svg { color: #6B4DFF; }
`;

const FormGroup = styled.div`
  margin-bottom: 20px;
  &:last-child { margin-bottom: 0; }
`;

const Label = styled.label`
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #444;
  margin-bottom: 8px;
`;

/* API Key 입력 전용 스타일 */
const ApiKeyWrapper = styled.div`
  position: relative;
  display: flex;
  align-items: center;
`;

const Input = styled.input`
  width: 100%;
  padding: 12px;
  padding-right: 40px; /* 눈 아이콘 공간 */
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  transition: border 0.2s;
  background-color: ${props => props.disabled ? '#f9f9f9' : 'white'};

  &:focus { border-color: #6B4DFF; }
`;

const IconBtn = styled.button`
  position: absolute;
  right: 10px;
  background: none;
  border: none;
  cursor: pointer;
  color: #999;
  display: flex;
  align-items: center;
  &:hover { color: #555; }
`;

/* 슬라이더 및 기타 컨트롤 */
const RangeWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 15px;
`;

const RangeInput = styled.input`
  flex: 1;
  cursor: pointer;
  accent-color: #6B4DFF;
`;

const RangeValue = styled.span`
  font-weight: bold;
  color: #6B4DFF;
  width: 40px;
  text-align: right;
`;

const Select = styled.select`
  width: 100%;
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  &:focus { border-color: #6B4DFF; }
`;

/* 토글 스위치 */
const ToggleWrapper = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
`;

const ToggleLabel = styled.span`
  font-size: 14px;
  color: #555;
`;

const ToggleSwitch = styled.label`
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;

  input { opacity: 0; width: 0; height: 0; }

  span {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #ccc;
    transition: .4s;
    border-radius: 24px;
  }

  span:before {
    position: absolute;
    content: "";
    height: 18px;
    width: 18px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: .4s;
    border-radius: 50%;
  }

  input:checked + span { background-color: #6B4DFF; }
  input:checked + span:before { transform: translateX(20px); }
`;

const SaveButton = styled.button`
  position: fixed;
  bottom: 30px;
  right: 40px;
  background: #333;
  color: white;
  padding: 14px 28px;
  border-radius: 50px;
  border: none;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 100;
  transition: transform 0.2s;

  &:hover {
    background: #000;
    transform: translateY(-2px);
  }
`;

export default function Settings() {
  // 상태 관리
  const [keys, setKeys] = useState({
    openai: 'sk-proj-xxxxxxxxxxxxxxxxxxxx',
    claude: '',
  });
  
  const [showKey, setShowKey] = useState({ openai: false, claude: false });
  const [creativity, setCreativity] = useState(0.7);
  
  // 입력 핸들러
  const handleKeyChange = (e) => {
    setKeys({...keys, [e.target.name]: e.target.value});
  };

  const toggleVisibility = (field) => {
    setShowKey({...showKey, [field]: !showKey[field]});
  };

  const handleSave = () => {
    alert('설정이 저장되었습니다!');
  };

  return (
    <Container>
      <Header>
        <Title>환경 설정</Title>
        <SubDesc>AI 모델 연결 및 에이전트의 기본 동작 방식을 설정합니다.</SubDesc>
      </Header>

      {/* 1. API KEY 설정 (필수) */}
      <SectionCard>
        <SectionHeader>
          <Key size={20} />
          <h3>API Key 관리</h3>
        </SectionHeader>

        <FormGroup>
          <Label>OpenAI API Key (GPT-4o)</Label>
          <ApiKeyWrapper>
            <Input 
              type={showKey.openai ? "text" : "password"} 
              name="openai"
              value={keys.openai}
              onChange={handleKeyChange}
              placeholder="sk-..."
            />
            <IconBtn onClick={() => toggleVisibility('openai')}>
              {showKey.openai ? <EyeOff size={18}/> : <Eye size={18}/>}
            </IconBtn>
          </ApiKeyWrapper>
        </FormGroup>

        <FormGroup>
          <Label>Anthropic API Key (Claude 3.5 Sonnet)</Label>
          <ApiKeyWrapper>
            <Input 
              type={showKey.claude ? "text" : "password"} 
              name="claude"
              value={keys.claude}
              onChange={handleKeyChange}
              placeholder="sk-ant-..."
            />
            <IconBtn onClick={() => toggleVisibility('claude')}>
              {showKey.claude ? <EyeOff size={18}/> : <Eye size={18}/>}
            </IconBtn>
          </ApiKeyWrapper>
        </FormGroup>
      </SectionCard>

      {/* 2. 에이전트 기본값 설정 (추천) */}
      <SectionCard>
        <SectionHeader>
          <Sliders size={20} />
          <h3>기본 생성 옵션</h3>
        </SectionHeader>

        <FormGroup>
          <Label>기본 브랜드 톤앤매너</Label>
          <Select>
            <option>선택 안함 (매번 직접 설정)</option>
            <option>감성적이고 따뜻한 (Emotional)</option>
            <option>논리적이고 신뢰감 있는 (Professional)</option>
            <option>재치있고 트렌디한 (Witty)</option>
          </Select>
        </FormGroup>

        <FormGroup>
          <Label>
            AI 창의성 (Temperature)
            <span style={{fontSize:'12px', color:'#888', marginLeft:'8px', fontWeight:'normal'}}>
              높을수록 더 창의적이고 다양한 문장을 만듭니다.
            </span>
          </Label>
          <RangeWrapper>
            <span style={{fontSize:'12px'}}>정확함</span>
            <RangeInput 
              type="range" 
              min="0" max="1" step="0.1" 
              value={creativity} 
              onChange={(e) => setCreativity(e.target.value)}
            />
            <span style={{fontSize:'12px'}}>창의적</span>
            <RangeValue>{creativity}</RangeValue>
          </RangeWrapper>
        </FormGroup>
      </SectionCard>

      {/* 3. 알림 및 기타 설정 */}
      <SectionCard>
        <SectionHeader>
          <Bell size={20} />
          <h3>알림 및 시스템</h3>
        </SectionHeader>

        <ToggleWrapper>
          <ToggleLabel>메시지 생성 완료 시 브라우저 알림 받기</ToggleLabel>
          <ToggleSwitch>
            <input type="checkbox" defaultChecked />
            <span></span>
          </ToggleSwitch>
        </ToggleWrapper>

        <ToggleWrapper>
          <ToggleLabel>마케팅 규정 준수 필터(Safe-Guard) 켜기</ToggleLabel>
          <ToggleSwitch>
            <input type="checkbox" defaultChecked />
            <span></span>
          </ToggleSwitch>
        </ToggleWrapper>
      </SectionCard>

      <SaveButton onClick={handleSave}>
        <Save size={18} /> 설정 저장하기
      </SaveButton>
    </Container>
  );
}