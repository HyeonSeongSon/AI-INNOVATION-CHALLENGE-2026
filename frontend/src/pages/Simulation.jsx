import React, { useState, useEffect, useRef } from 'react';
import styled from 'styled-components';
import { useLocation } from 'react-router-dom';
import { MessageCircle, User, Bot, Send, AlertCircle } from 'lucide-react';

const Container = styled.div`
  max-width: 1000px;
  margin: 0 auto;
  height: calc(100vh - 100px);
  display: flex;
  flex-direction: column;
`;

const Header = styled.div`
  margin-bottom: 20px;
`;

const Title = styled.h1`
  font-size: 24px;
  font-weight: 800;
  color: #333;
  display: flex;
  align-items: center;
  gap: 10px;
`;

const SubDesc = styled.p`
  color: #666;
  margin-top: 5px;
  font-size: 14px;
`;

const ChatBox = styled.div`
  flex: 1;
  background: white;
  border-radius: 16px;
  border: 1px solid #eee;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0,0,0,0.02);
`;

const ChatHeader = styled.div`
  padding: 20px;
  background: #F8F9FA;
  border-bottom: 1px solid #eee;
  display: flex;
  align-items: center;
  gap: 15px;
`;

const PersonaAvatar = styled.div`
  width: 50px; height: 50px;
  border-radius: 50%;
  background: #FFD166; /* 고객은 노란색 느낌 */
  color: white;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px;
`;

const PersonaInfo = styled.div`
  display: flex; flex-direction: column;
  strong { font-size: 16px; color: #333; }
  span { font-size: 13px; color: #777; }
`;

const MessageList = styled.div`
  flex: 1;
  padding: 30px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
  background-color: white;
`;

const BubbleWrapper = styled.div`
  display: flex;
  gap: 12px;
  align-self: ${props => props.$isUser ? 'flex-end' : 'flex-start'};
  flex-direction: ${props => props.$isUser ? 'row-reverse' : 'row'};
  max-width: 80%;
`;

const Bubble = styled.div`
  background: ${props => props.$isUser ? '#6B4DFF' : '#F0F2F5'};
  color: ${props => props.$isUser ? 'white' : '#333'};
  padding: 14px 20px;
  border-radius: 20px;
  border-top-left-radius: ${props => !props.$isUser ? '4px' : '20px'};
  border-top-right-radius: ${props => props.$isUser ? '4px' : '20px'};
  font-size: 15px;
  line-height: 1.6;
  white-space: pre-line;
  box-shadow: 0 2px 5px rgba(0,0,0,0.05);
`;

const InputArea = styled.div`
  padding: 20px;
  border-top: 1px solid #eee;
  display: flex;
  gap: 10px;
`;

const Input = styled.input`
  flex: 1;
  padding: 14px 20px;
  border: 1px solid #ddd;
  border-radius: 30px;
  outline: none;
  font-size: 15px;
  &:focus { border-color: #6B4DFF; }
`;

const SendBtn = styled.button`
  width: 50px; height: 50px;
  border-radius: 50%;
  background: #333;
  color: white;
  border: none;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  &:hover { background: black; }
`;

export default function Simulation() {
  const location = useLocation();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef(null);

  // 메시지 생성 탭에서 넘어온 데이터가 있으면 그걸로 초기화
  const initialMessage = location.state?.message;
  const personaName = location.state?.persona || '김민지/20대/수부지';

  useEffect(() => {
    if (initialMessage) {
      setMessages([
        { id: 1, type: 'user', text: initialMessage }, // 내가 보낸 메시지
        { id: 2, type: 'bot', text: '잠시만요, 메시지 확인 중입니다...' } // 봇의 반응 대기
      ]);
      
      // 1초 뒤 봇(고객)의 반응 시뮬레이션
      setTimeout(() => {
        setMessages(prev => [
          prev[0], // 내 메시지 유지
          { id: 2, type: 'bot', text: '음.. 할인은 좋은데, 제가 피부가 좀 예민해서요. 성분은 괜찮은가요? 혹시 트러블 날까봐 걱정돼서...' }
        ]);
      }, 1500);
    } else {
      // 그냥 들어왔을 때
      setMessages([{ id: 1, type: 'bot', text: '안녕하세요! 저는 가상 고객입니다. 테스트할 마케팅 메시지를 보내주세요.' }]);
    }
  }, [initialMessage]);

  const handleSend = () => {
    if (!input.trim()) return;

    setMessages(prev => [...prev, { id: Date.now(), type: 'user', text: input }]);
    setInput('');
    setIsTyping(true);

    setTimeout(() => {
      setIsTyping(false);
      setMessages(prev => [...prev, { 
        id: Date.now() + 1, 
        type: 'bot', 
        text: '아 그렇군요! 시카 성분이 들어있다니 안심이 되네요. 링크 보내주시면 한번 구경해볼게요! 😊' 
      }]);
    }, 1200);
  };

  return (
    <Container>
      <Header>
        <Title><MessageCircle /> 가상 고객 시뮬레이션</Title>
        <SubDesc>생성된 메시지에 대해 AI 페르소나({personaName.split('/')[0]})가 어떻게 반응하는지 테스트합니다.</SubDesc>
      </Header>

      <ChatBox>
        <ChatHeader>
          <PersonaAvatar>👩</PersonaAvatar>
          <PersonaInfo>
            <strong>{personaName.split('/')[0]} (가상 고객)</strong>
            <span>{personaName.split('/')[1]} • {personaName.split('/')[2]}</span>
          </PersonaInfo>
          <div style={{marginLeft:'auto', fontSize:'12px', color:'#FF8C00', background:'#FFF3E0', padding:'6px 12px', borderRadius:'20px'}}>
             ⚠️ 까칠함 모드 ON
          </div>
        </ChatHeader>

        <MessageList>
          {messages.map(msg => (
            <BubbleWrapper key={msg.id} $isUser={msg.type === 'user'}>
              <Bubble $isUser={msg.type === 'user'}>
                {msg.text}
              </Bubble>
            </BubbleWrapper>
          ))}
          {isTyping && <div style={{color:'#999', paddingLeft:'20px'}}>고객이 답변을 입력하고 있습니다...</div>}
        </MessageList>

        <InputArea>
          <Input 
            placeholder="고객에게 답변하기 (설득해 보세요)" 
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          />
          <SendBtn onClick={handleSend}><Send size={20}/></SendBtn>
        </InputArea>
      </ChatBox>
    </Container>
  );
}