import React, { useState } from 'react';
import styled from 'styled-components';
import { User, Sparkles, X, ChevronDown, CheckCircle, Copy, RefreshCw } from 'lucide-react';

/* --- 스타일 컴포넌트 --- */
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
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

/* 카드 그리드 (페르소나 목록) */
const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 24px;
`;

const PersonaCard = styled.div`
  background: white;
  border-radius: 16px;
  padding: 24px;
  border: 1px solid #eee;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  overflow: hidden;

  &:hover {
    transform: translateY(-4px);
    border-color: #6B4DFF;
    box-shadow: 0 8px 20px rgba(107, 77, 255, 0.15);
  }
`;

const CardHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f0f0f0;
  padding-bottom: 16px;
`;

const Avatar = styled.div`
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background-color: #F0EBFF;
  color: #6B4DFF;
  display: flex;
  align-items: center;
  justify-content: center;
`;

const NameInfo = styled.div`
  display: flex;
  flex-direction: column;
`;

const Name = styled.span`
  font-size: 18px;
  font-weight: 700;
  color: #333;
`;

const Job = styled.span`
  font-size: 14px;
  color: #888;
`;

const TagContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
`;

const Tag = styled.span`
  font-size: 12px;
  color: #555;
  background-color: #F5F6FA;
  padding: 4px 8px;
  border-radius: 4px;
`;

/* --- 모달(설정 팝업) 스타일 --- */
const Overlay = styled.div`
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
`;

const ModalBox = styled.div`
  background: #F8F9FE; /* 이미지 배경색 참고 */
  width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
  display: flex;
  flex-direction: column;
`;

const ModalHeader = styled.div`
  padding: 24px 30px;
  background: white;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #eee;

  h2 { font-size: 20px; font-weight: bold; color: #333; }
  svg { cursor: pointer; color: #999; &:hover { color: #333; } }
`;

const ModalContent = styled.div`
  padding: 30px;
  display: flex;
  flex-direction: column;
  gap: 24px;
`;

const InfoSection = styled.div`
  background: #EBEBF0;
  padding: 20px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  
  strong { font-size: 15px; color: #333; }
  span { font-size: 14px; color: #666; }
`;

const SectionLabel = styled.label`
  font-size: 14px;
  font-weight: 700;
  color: #444;
  margin-bottom: 8px;
  display: block;
`;

const SelectBox = styled.div`
  position: relative;
  
  select {
    width: 100%;
    padding: 14px;
    padding-right: 40px;
    border: 1px solid #ddd;
    border-radius: 8px;
    font-size: 14px;
    appearance: none;
    background: white;
    cursor: pointer;
    outline: none;
    &:focus { border-color: #6B4DFF; }
  }

  svg {
    position: absolute;
    right: 14px;
    top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
    color: #888;
  }
`;

const GenerateBtn = styled.button`
  width: 100%;
  padding: 16px;
  background: #6B4DFF;
  color: white;
  font-weight: bold;
  font-size: 16px;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  margin-top: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;

  &:hover { background: #5a3de0; }
  &:disabled { background: #ccc; cursor: not-allowed; }
`;

/* 결과 모달 스타일 (재사용) */
const ResultBox = styled.div`
  background: white;
  padding: 24px;
  border-radius: 12px;
  border: 1px solid #eee;
  white-space: pre-line;
  line-height: 1.6;
  color: #333;
  margin-bottom: 20px;
  max-height: 300px;
  overflow-y: auto;
`;

const ActionBtn = styled.button`
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid #ddd;
  background: white;
  color: #555;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  &:hover { background: #f5f5f5; }
`;


export default function Message() {
  /* 주의: 실제로는 페르소나 탭의 데이터(Context/Store)를 가져와야 하지만,
     프론트엔드 프로토타입이므로 여기서도 임시 데이터(Mock)를 사용합니다.
  */
  const personas = [
    { id: 1, name: '미란다 프리슬리', age: '45세', job: '도심의 직장인', detail: '친환경 제품 선호, 꼼꼼한 성분 분석' },
    { id: 2, name: '앤드리아 삭스', age: '28세', job: '사회초년생', detail: '가성비 중시, 트렌드 민감' },
    { id: 3, name: '에밀리', age: '32세', job: '패션업계 종사자', detail: '럭셔리 뷰티, 비주얼 중시' },
  ];

  const [selectedPersona, setSelectedPersona] = useState(null); // 선택된 페르소나 (모달 열림 여부)
  const [isGenerating, setIsGenerating] = useState(false); // 생성 중 로딩 상태
  const [generatedResult, setGeneratedResult] = useState(null); // 결과 값

  // 입력값 관리
  const [goal, setGoal] = useState('장바구니/위시리스트 리마인드');
  const [model, setModel] = useState('Claude sonnet-4.5');

  // 카드 클릭 시 모달 열기
  const handleCardClick = (persona) => {
    setSelectedPersona(persona);
    setGeneratedResult(null); // 이전 결과 초기화
  };

  // 모달 닫기
  const closeModal = () => {
    setSelectedPersona(null);
    setIsGenerating(false);
  };

  // 메시지 생성 로직 (가짜)
  const handleGenerate = () => {
    setIsGenerating(true);
    
    // 2초 뒤 결과 생성
    setTimeout(() => {
      setIsGenerating(false);
      setGeneratedResult(
        `[${goal}] 메시지 생성 완료 ✨\n\n` +
        `안녕하세요, ${selectedPersona.name}님!\n` +
        `${selectedPersona.detail} 성향을 고려하여 제안드립니다.\n\n` +
        `바쁜 도심 생활 속, 피부 휴식이 필요하지 않으신가요?\n` +
        `지금 아모레몰에서 회원님만을 위한 시크릿 혜택을 확인해보세요.\n\n` +
        `👉 링크: amoremall.com/secret`
      );
    }, 2000);
  };

  return (
    <Container>
      <Header>
        <Title>메시지 생성</Title>
        <SubDesc>메시지를 발송할 타겟 페르소나를 선택해주세요.</SubDesc>
      </Header>

      {/* 1. 페르소나 목록 (카드) */}
      <Grid>
        {personas.map(persona => (
          <PersonaCard key={persona.id} onClick={() => handleCardClick(persona)}>
            <CardHeader>
              <Avatar><User size={24}/></Avatar>
              <NameInfo>
                <Name>{persona.name}</Name>
                <Job>{persona.job}</Job>
              </NameInfo>
            </CardHeader>
            <TagContainer>
              <Tag>{persona.age}</Tag>
              <Tag>{persona.detail.split(',')[0]}</Tag>
            </TagContainer>
          </PersonaCard>
        ))}
      </Grid>

      {/* 2. 설정 및 생성 팝업 (모달) */}
      {selectedPersona && (
        <Overlay onClick={closeModal}>
          <ModalBox onClick={e => e.stopPropagation()}>
            <ModalHeader>
              <h2>{generatedResult ? '메시지 생성 결과' : '메시지 생성 설정'}</h2>
              <X onClick={closeModal} size={24}/>
            </ModalHeader>

            <ModalContent>
              {/* 생성 전: 설정 화면 */}
              {!generatedResult ? (
                <>
                  {/* 선택된 페르소나 정보 (이미지 참고) */}
                  <div style={{marginBottom: '10px'}}>
                    <SectionLabel>페르소나</SectionLabel>
                    <InfoSection>
                      <strong>{selectedPersona.name}</strong>
                      <span>{selectedPersona.job} / {selectedPersona.age}</span>
                      <span>{selectedPersona.detail}</span>
                    </InfoSection>
                  </div>

                  {/* 광고 목적 선택 */}
                  <div>
                    <SectionLabel>광고 목적</SectionLabel>
                    <SelectBox>
                      <select value={goal} onChange={(e) => setGoal(e.target.value)}>
                        <option>장바구니/위시리스트 리마인드</option>
                        <option>할인·프로모션 안내</option>
                        <option>브랜드 캠페인 참여 유도</option>
                        <option>시즌·날씨 기반 추천</option>
                        <option>개인 피부·고민 맞춤 솔루션</option>
                      </select>
                      <ChevronDown size={16}/>
                    </SelectBox>
                  </div>

                  {/* 모델 선택 */}
                  <div>
                    <SectionLabel>모델 선택</SectionLabel>
                    <SelectBox>
                      <select value={model} onChange={(e) => setModel(e.target.value)}>
                        <option>Claude sonnet-4.5</option>
                        <option>Chat GPT-5</option>
                        <option>Gemini-3</option>
                        <option>Chat GPT-4.1o</option>
                        <option>Custom-model</option>
                      </select>
                      <ChevronDown size={16}/>
                    </SelectBox>
                  </div>

                  <GenerateBtn onClick={handleGenerate} disabled={isGenerating}>
                    {isGenerating ? (
                      <>생성 중입니다... <Sparkles size={18} className="spin"/></>
                    ) : (
                      <>메시지 생성하기 <Sparkles size={18}/></>
                    )}
                  </GenerateBtn>
                </>
              ) : (
                /* 생성 후: 결과 화면 (모달 내부에서 보여줌) */
                <>
                  <div style={{textAlign: 'center', marginBottom: '10px'}}>
                     <CheckCircle size={48} color="#6B4DFF" style={{marginBottom: '10px'}}/>
                     <h3>생성이 완료되었습니다!</h3>
                  </div>

                  <ResultBox>
                    {generatedResult}
                  </ResultBox>

                  <div style={{display:'flex', gap:'10px', justifyContent:'center'}}>
                    <ActionBtn onClick={() => alert('클립보드에 복사됨')}>
                      <Copy size={14}/> 복사
                    </ActionBtn>
                    <ActionBtn onClick={() => setGeneratedResult(null)}>
                      <RefreshCw size={14}/> 다시 생성
                    </ActionBtn>
                  </div>
                </>
              )}
            </ModalContent>
          </ModalBox>
        </Overlay>
      )}
    </Container>
  );
}