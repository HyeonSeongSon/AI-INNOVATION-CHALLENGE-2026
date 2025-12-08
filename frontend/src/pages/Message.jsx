import React, { useState } from 'react';
import styled from 'styled-components';
import { Send, Settings, Sparkles, Copy, RefreshCw, Wand2, ThumbsUp, ThumbsDown, MessageCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

/* --- 스타일 컴포넌트 --- */
const Container = styled.div`
  display: flex;
  height: calc(100vh - 100px);
  gap: 24px;
  max-width: 1400px;
  margin: 0 auto;
`;

const Sidebar = styled.div`
  width: 340px;
  background: white;
  border-radius: 16px;
  border: 1px solid #eee;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  overflow-y: auto;
`;

const SidebarHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 15px;
  border-bottom: 1px solid #eee;
  h3 { font-size: 18px; font-weight: 800; color: #333; }
`;

const SectionLabel = styled.label`
  font-size: 12px;
  font-weight: 700;
  color: #888;
  margin-bottom: 8px;
  display: block;
  text-transform: uppercase;
`;

const FormGroup = styled.div`
  display: flex;
  flex-direction: column;
`;

const Input = styled.input`
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  &:focus { border-color: #6B4DFF; }
`;

const Select = styled.select`
  padding: 12px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
  background: white;
  cursor: pointer;
  &:focus { border-color: #6B4DFF; }
`;

const GenerateButton = styled.button`
  margin-top: auto;
  background: linear-gradient(135deg, #6B4DFF 0%, #9F85FF 100%);
  color: white;
  padding: 16px;
  border-radius: 12px;
  border: none;
  font-weight: 700;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
  transition: transform 0.2s;
  
  &:hover { transform: translateY(-2px); box-shadow: 0 4px 15px rgba(107, 77, 255, 0.3); }
  &:disabled { background: #ccc; cursor: not-allowed; transform: none; box-shadow: none; }
`;

const ResultArea = styled.div`
  flex: 1;
  background: white;
  border-radius: 16px;
  border: 1px solid #eee;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
`;

const ResultHeader = styled.div`
  padding: 20px 30px;
  border-bottom: 1px solid #f0f0f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  h2 { font-size: 18px; font-weight: 700; color: #333; }
`;

const ResultContent = styled.div`
  flex: 1;
  padding: 40px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
`;

const EmptyState = styled.div`
  text-align: center;
  color: #aaa;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  svg { width: 48px; height: 48px; color: #ddd; }
`;

const MessageCard = styled.div`
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 16px;
  padding: 30px;
  box-shadow: 0 4px 30px rgba(0,0,0,0.04);
  max-width: 600px;
  margin: 0 auto;
  width: 100%;
`;

const CardToolbar = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid #f5f5f5;
`;

const ToolBtn = styled.button`
  background: none; border: none; cursor: pointer; color: #999;
  display: flex; align-items: center; gap: 4px; font-size: 12px;
  &:hover { color: #6B4DFF; }
`;

const TestButton = styled.button`
  background: #E8EAF6; color: #6B4DFF; border: none; cursor: pointer;
  display: flex; align-items: center; gap: 4px; font-size: 12px;
  padding: 6px 12px; border-radius: 20px; font-weight: 700;
  &:hover { background: #D1C4E9; }
`;

const MessageText = styled.textarea`
  width: 100%;
  min-height: 200px;
  border: none;
  font-size: 16px;
  line-height: 1.8;
  color: #333;
  resize: none;
  outline: none;
  font-family: inherit;
`;

const RefineBar = styled.div`
  padding: 20px 30px;
  background: #F8F9FA;
  border-top: 1px solid #eee;
  display: flex;
  gap: 12px;
  align-items: center;
`;

const RefineInput = styled.input`
  flex: 1;
  padding: 14px 20px;
  border: 1px solid #ddd;
  border-radius: 30px;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); }
`;

const SendBtn = styled.button`
  width: 44px; height: 44px;
  border-radius: 50%;
  background: #333;
  color: white;
  border: none;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  &:hover { background: black; }
`;

export default function Message() {
  const navigate = useNavigate();
  const [isGenerating, setIsGenerating] = useState(false);
  const [result, setResult] = useState('');
  const [refineQuery, setRefineQuery] = useState('');

  const [config, setConfig] = useState({
    persona: '김민지/20대/수부지',
    product: '',
    goal: '할인·프로모션 안내',
    tone: '친근하고 감성적인'
  });

  const handleGenerate = () => {
    if (!config.product) return alert('상품명을 입력해주세요!');
    setIsGenerating(true);
    setTimeout(() => {
      setIsGenerating(false);
      setResult(
        `[${config.goal}] ${config.product} X 아모레몰 🎁\n\n` +
        `안녕하세요, ${config.persona.split('/')[0]}님!\n` +
        `환절기라 피부가 많이 건조하시죠? 💧\n\n` +
        `${config.product} 특가 이벤트를 준비했어요.\n` +
        `오직 회원님만을 위한 시크릿 쿠폰,\n` +
        `지금 바로 확인해보세요! 👇\n` +
        `amoremall.com/event/secret`
      );
    }, 1500);
  };

  const handleRefine = () => {
    if (!refineQuery.trim()) return;
    setIsGenerating(true);
    setTimeout(() => {
      setIsGenerating(false);
      setResult(prev => prev + `\n\n(AI 수정됨: "${refineQuery}" 반영 완료)`);
      setRefineQuery('');
    }, 1000);
  };

  // 시뮬레이션 탭으로 데이터 넘겨주기
  const handleTestSimulation = () => {
    // 실제로는 전역 상태(Context)를 써야 하지만, 여기선 간단히 navigate만 함
    if(window.confirm('이 메시지로 고객 반응 테스트(시뮬레이션)를 하시겠습니까?')) {
      navigate('/simulation', { state: { message: result, persona: config.persona } });
    }
  };

  return (
    <Container>
      <Sidebar>
        <SidebarHeader>
          <Settings size={20} />
          <h3>Generation Config</h3>
        </SidebarHeader>

        <FormGroup>
          <SectionLabel>Target Persona</SectionLabel>
          <Select value={config.persona} onChange={(e) => setConfig({...config, persona: e.target.value})}>
            <option>김민지/20대/수부지/가성비</option>
            <option>박서준/30대/건성/기능성</option>
            <option>미란다/45세/주름/친환경</option>
          </Select>
        </FormGroup>

        <FormGroup>
          <SectionLabel>Product Name</SectionLabel>
          <Input 
            placeholder="예: 라네즈 워터뱅크" 
            value={config.product} 
            onChange={(e) => setConfig({...config, product: e.target.value})} 
          />
        </FormGroup>

        <FormGroup>
          <SectionLabel>Goal</SectionLabel>
          <Select value={config.goal} onChange={(e) => setConfig({...config, goal: e.target.value})}>
            <option>장바구니/위시리스트 리마인드</option>
            <option>할인·프로모션 안내</option>
            <option>브랜드 캠페인 참여 유도</option>
          </Select>
        </FormGroup>

        <FormGroup>
          <SectionLabel>Tone & Manner</SectionLabel>
          <Select value={config.tone} onChange={(e) => setConfig({...config, tone: e.target.value})}>
            <option>친근하고 감성적인</option>
            <option>전문적이고 신뢰감 있는</option>
            <option>위트 있는</option>
          </Select>
        </FormGroup>

        <GenerateButton onClick={handleGenerate} disabled={isGenerating}>
          {isGenerating ? 'AI가 작성 중...' : '메시지 생성하기'}
          <Sparkles size={18} className={isGenerating ? 'spin' : ''} />
        </GenerateButton>
      </Sidebar>

      <ResultArea>
        <ResultHeader>
          <h2>Generated Message</h2>
        </ResultHeader>
        <ResultContent>
          {!result ? (
            <EmptyState>
              <Wand2 />
              <p>왼쪽에서 설정을 완료하고<br/>[메시지 생성하기] 버튼을 눌러주세요.</p>
            </EmptyState>
          ) : (
            <MessageCard>
              <CardToolbar>
                <TestButton onClick={handleTestSimulation}>
                  <MessageCircle size={14}/> 시뮬레이션 테스트
                </TestButton>
                <ToolBtn><Copy size={14}/> 복사</ToolBtn>
                <ToolBtn><ThumbsUp size={14}/> 좋아요</ToolBtn>
              </CardToolbar>
              <MessageText value={result} readOnly />
            </MessageCard>
          )}
        </ResultContent>
        {result && (
          <RefineBar>
            <Sparkles size={18} color="#6B4DFF" />
            <RefineInput 
              placeholder="수정 요청 (예: 좀 더 짧게 줄여줘)" 
              value={refineQuery}
              onChange={(e) => setRefineQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRefine()}
            />
            <SendBtn onClick={handleRefine}><Send size={18} /></SendBtn>
          </RefineBar>
        )}
      </ResultArea>
    </Container>
  );
}