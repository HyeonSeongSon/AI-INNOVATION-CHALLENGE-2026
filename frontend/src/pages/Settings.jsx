import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import { Save, Sliders, Bell, ChevronDown } from 'lucide-react';

// Toast 훅 불러오기
import { useToast } from '../components/Toast';

/* --- 스타일 컴포넌트 --- */
const Container = styled.div`
  max-width: 800px;
  margin: 0 auto;
  padding-bottom: 100px;
  padding-top: 40px;
`;

const Header = styled.div`
  margin-bottom: 30px;
`;

const Title = styled.h1`
  font-size: 28px;
  font-weight: 800;
  color: #333;
  margin: 0;
`;

const SubDesc = styled.p`
  color: #666;
  margin-top: 8px;
  font-size: 14px;
`;

/* 섹션 카드 공통 스타일 */
const SectionCard = styled.div`
  background: white;
  border-radius: 20px;
  border: 1px solid #eee;
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
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

  h3 { font-size: 18px; font-weight: 700; color: #333; margin: 0; }
  svg { color: #6B4DFF; }
`;

const FormGroup = styled.div`
  margin-bottom: 24px;
  &:last-child { margin-bottom: 0; }
`;

const Label = styled.label`
  display: block;
  font-size: 14px;
  font-weight: 600;
  color: #444;
  margin-bottom: 10px;
`;

/* 드롭다운 스타일 */
const SelectWrapper = styled.div`
  position: relative;
  svg {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: #888;
    pointer-events: none;
  }
`;

const Select = styled.select`
  width: 100%;
  padding: 14px;
  padding-right: 40px;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  font-size: 14px;
  outline: none;
  appearance: none;
  background: white;
  cursor: pointer;
  transition: 0.2s;
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); }
`;

/* 슬라이더 */
const RangeWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 0 5px;
`;

const RangeInput = styled.input`
  flex: 1;
  cursor: pointer;
  accent-color: #6B4DFF;
  height: 6px;
`;

const RangeValue = styled.span`
  font-weight: 700;
  color: #6B4DFF;
  width: 40px;
  text-align: right;
  font-size: 14px;
`;

/* 토글 스위치 */
const ToggleWrapper = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 12px;
  border-radius: 12px;
  background: #fcfcfc;
  border: 1px solid #f5f5f5;
  
  &:last-child { margin-bottom: 0; }
`;

const ToggleLabel = styled.span`
  font-size: 14px;
  font-weight: 500;
  color: #333;
`;

const ToggleSwitch = styled.label`
  position: relative;
  display: inline-block;
  width: 48px;
  height: 26px;

  input { opacity: 0; width: 0; height: 0; }

  span {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background-color: #e0e0e0;
    transition: .3s;
    border-radius: 30px;
  }

  span:before {
    position: absolute;
    content: "";
    height: 20px;
    width: 20px;
    left: 3px;
    bottom: 3px;
    background-color: white;
    transition: .3s;
    border-radius: 50%;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  }

  input:checked + span { background-color: #6B4DFF; }
  input:checked + span:before { transform: translateX(22px); }
`;

const SaveButton = styled.button`
  position: fixed;
  bottom: 30px;
  right: 40px;
  background: #111;
  color: white;
  padding: 16px 32px;
  border-radius: 50px;
  border: none;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 8px 20px rgba(0,0,0,0.2);
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 100;
  transition: all 0.2s;

  &:hover {
    background: #6B4DFF;
    transform: translateY(-4px);
    box-shadow: 0 12px 25px rgba(107, 77, 255, 0.3);
  }
  
  &:active { transform: scale(0.95); }
`;

export default function Settings() {
  const { addToast } = useToast();

  // --- 상태 관리 (API Key, Model 삭제됨) ---
  const [creativity, setCreativity] = useState(0.7);
  const [tone, setTone] = useState('');
  const [toggles, setToggles] = useState({ notification: true, safeGuard: true });

  // --- [useEffect] 로컬 스토리지에서 설정 불러오기 ---
  useEffect(() => {
    const savedSettings = localStorage.getItem('app_settings');
    if (savedSettings) {
      try {
        const parsed = JSON.parse(savedSettings);
        if (parsed.creativity) setCreativity(parsed.creativity);
        if (parsed.tone) setTone(parsed.tone);
        if (parsed.toggles) setToggles(parsed.toggles);
      } catch (e) {
        console.error("설정 로드 실패", e);
      }
    }
  }, []);

  // 입력 핸들러
  const handleToggleChange = (field) => setToggles({...toggles, [field]: !toggles[field]});

  // --- [저장] 로컬 스토리지에 저장 ---
  const handleSave = () => {
    const settings = {
      creativity,
      tone,
      toggles
    };
    
    localStorage.setItem('app_settings', JSON.stringify(settings));
    addToast("설정이 저장되었습니다.", "success");
  };

  return (
    <Container>
      <Header>
        <Title>환경 설정</Title>
        <SubDesc>AI 에이전트의 생성 스타일과 알림 방식을 설정합니다.</SubDesc>
      </Header>

      {/* 1. 생성 옵션 설정 */}
      <SectionCard>
        <SectionHeader>
          <Sliders size={20} />
          <h3>생성 옵션 설정</h3>
        </SectionHeader>

        <FormGroup>
          <Label>기본 브랜드 톤앤매너</Label>
          <SelectWrapper>
            <Select value={tone} onChange={(e) => setTone(e.target.value)}>
              <option value="">선택 안함 (매번 직접 설정)</option>
              <option value="emotional">감성적이고 따뜻한 (Emotional)</option>
              <option value="professional">논리적이고 신뢰감 있는 (Professional)</option>
              <option value="witty">재치있고 트렌디한 (Witty)</option>
            </Select>
            <ChevronDown size={16} />
          </SelectWrapper>
        </FormGroup>

        <FormGroup>
          <Label>
            AI 창의성 (Temperature)
            <span style={{fontSize:'12px', color:'#888', marginLeft:'8px', fontWeight:'normal'}}>
              높을수록 더 창의적이고 다양한 문장을 만듭니다.
            </span>
          </Label>
          <RangeWrapper>
            <span style={{fontSize:'12px', color:'#888'}}>정확함</span>
            <RangeInput 
              type="range" 
              min="0" max="1" step="0.1" 
              value={creativity} 
              onChange={(e) => setCreativity(e.target.value)}
            />
            <span style={{fontSize:'12px', color:'#888'}}>창의적</span>
            <RangeValue>{creativity}</RangeValue>
          </RangeWrapper>
        </FormGroup>
      </SectionCard>

      {/* 2. 시스템 설정 */}
      <SectionCard>
        <SectionHeader>
          <Bell size={20} />
          <h3>시스템 설정</h3>
        </SectionHeader>

        <ToggleWrapper>
          <ToggleLabel>완료 시 브라우저 알림 받기</ToggleLabel>
          <ToggleSwitch>
            <input type="checkbox" checked={toggles.notification} onChange={() => handleToggleChange('notification')} />
            <span></span>
          </ToggleSwitch>
        </ToggleWrapper>

        <ToggleWrapper>
          <ToggleLabel>마케팅 규정 준수 필터(Safe-Guard) 켜기</ToggleLabel>
          <ToggleSwitch>
            <input type="checkbox" checked={toggles.safeGuard} onChange={() => handleToggleChange('safeGuard')} />
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