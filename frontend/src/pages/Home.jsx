import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { MessageSquare, Users, Zap, Sparkles, ArrowRight, History, TrendingUp } from 'lucide-react';
import api, { pipelineApi } from '../api';
import { useChat } from '../context/ChatContext';

/* --- 스타일 컴포넌트 (기존 유지) --- */
const PageContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
`;

const Header = styled.div`
  margin-bottom: 10px;
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

/* 상단 통계 카드 */
const StatsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
`;

const StatCard = styled.div`
  background: white;
  padding: 24px;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.03);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 140px;
  border: 1px solid #f0f0f0;
  transition: transform 0.2s;

  &:hover {
    transform: translateY(-2px);
  }
`;

const StatHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const StatIcon = styled.div`
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background-color: ${props => props.$bg || '#F5F6FA'};
  color: ${props => props.$color || '#555'};
  display: flex;
  align-items: center;
  justify-content: center;
`;

const StatLabel = styled.span`
  font-size: 14px;
  color: #888;
  font-weight: 600;
`;

const StatValue = styled.div`
  font-size: 32px;
  font-weight: 800;
  color: #333;
  
  span {
    font-size: 16px;
    font-weight: 500;
    margin-left: 4px;
    color: #888;
  }
`;

/* 배너 영역 */
const Banner = styled.div`
  width: 100%;
  padding: 30px;
  background: linear-gradient(135deg, #6B4DFF 0%, #9F85FF 100%);
  border-radius: 16px;
  color: white;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 8px 30px rgba(107, 77, 255, 0.2);
`;

const BannerContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 10px;
`;

const BannerTitle = styled.h2`
  font-size: 22px;
  font-weight: 800;
  display: flex;
  align-items: center;
  gap: 10px;
`;

const BannerText = styled.p`
  font-size: 15px;
  opacity: 0.9;
  line-height: 1.5;
`;

const ActionButton = styled.button`
  background-color: white;
  color: #6B4DFF;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 700;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s;

  &:hover {
    background-color: #f0f0f0;
    transform: scale(1.02);
  }
`;

/* 하단 2단 레이아웃 */
const BottomSection = styled.div`
  display: grid;
  grid-template-columns: 1.4fr 0.6fr; /* 7:3 비율로 조정 */
  gap: 24px;
`;

const SectionBox = styled.div`
  background: white;
  padding: 24px;
  border-radius: 16px;
  border: 1px solid #eee;
`;

const SectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
`;

const SectionTitle = styled.h3`
  font-size: 18px;
  font-weight: bold;
  color: #333;
  display: flex;
  align-items: center;
  gap: 8px;
`;

/* 최근 생성 리스트 스타일 */
const MessageItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background-color: #FAFAFA;
  border-radius: 12px;
  margin-bottom: 12px;
  border: 1px solid #f5f5f5;
  transition: background 0.2s;

  &:hover {
    background-color: #F0F0FF;
    border-color: #DEDEFE;
  }
`;

const MessageInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const MessageTag = styled.span`
  font-size: 11px;
  font-weight: 700;
  color: #6B4DFF;
  background-color: #F0EBFF;
  padding: 4px 8px;
  border-radius: 4px;
  width: fit-content;
`;

const MessageTitle = styled.span`
  font-size: 15px;
  font-weight: 600;
  color: #333;
`;

const PersonaInfo = styled.span`
  font-size: 13px;
  color: #888;
`;

/* 인기 페르소나 랭킹 스타일 */
const RankItem = styled.div`
  display: flex;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid #f5f5f5;

  &:last-child {
    border-bottom: none;
  }
`;

const RankNumber = styled.span`
  font-size: 16px;
  font-weight: 800;
  color: ${props => props.$top ? '#6B4DFF' : '#bbb'};
  width: 30px;
`;

const RankName = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #444;
  flex: 1;
`;

const RankCount = styled.span`
  font-size: 12px;
  color: #999;
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 10px;
`;


/* --- 메인 컴포넌트 --- */
export default function Home() {
  const navigate = useNavigate();
  const { selectConversation } = useChat();

  const [personaStats, setPersonaStats] = useState({ count: 0, list: [] });
  const [recentMessages, setRecentMessages] = useState([]);

  useEffect(() => {
    api.get('/generated-messages?user_id=son&limit=5')
      .then(res => setRecentMessages(res.data || []))
      .catch(() => {});
  }, []);

  const handleMessageClick = async (item) => {
    await selectConversation({ id: item.conversation_id });
    navigate('/message');
  };

  const parseTag = (item) => {
    const purpose = item.conversation_title?.match(/\[(.+?)\]/)?.[1] || '';
    const product = item.product_name ? item.product_name.slice(0, 20) : '';
    if (purpose && product) return `${purpose} / ${product}`;
    return purpose || product || '마케팅 메시지';
  };

  // ✅ 페르소나 데이터 불러오기 (실제 DB 연동)
  useEffect(() => {
    const fetchPersonas = async () => {
      try {
        const response = await pipelineApi.post('/personas/list');

        // 백엔드 응답 구조에 따라 데이터 추출 (배열인지, 객체 안의 배열인지 확인)
        const data = Array.isArray(response.data) ? response.data : (response.data.personas || []);
        
        // 최신순으로 정렬 (ID 기준 역순 가정)
        const sorted = [...data].reverse();

        setPersonaStats({
          count: data.length, // 실제 개수
          list: sorted.slice(0, 5) // 실제 목록 (최대 5개)
        });
      } catch (error) {
        console.error("페르소나 데이터 로드 실패:", error);
        // 에러 시 기존 상태 유지 (0개)
      }
    };
    fetchPersonas();
  }, []);

  return (
    <PageContainer>
      <Header>
        <Title>Dashboard</Title>
        <SubDesc>아모레몰 AI 마케팅 에이전트에 오신 것을 환영합니다.</SubDesc>
      </Header>

      {/* 상단 통계 카드 */}
      <StatsGrid>
        <StatCard>
          <StatHeader>
            <StatLabel>오늘 생성된 메시지</StatLabel>
            <StatIcon $bg="#E0F2F1" $color="#00695C"><MessageSquare size={20} /></StatIcon>
          </StatHeader>
          <StatValue>24 <span>건</span></StatValue> {/* 하드코딩 (메시지 이력 DB 없음) */}
        </StatCard>
        
        <StatCard onClick={() => navigate('/persona')} style={{cursor: 'pointer'}}>
          <StatHeader>
            <StatLabel>등록된 페르소나</StatLabel>
            <StatIcon $bg="#F3E5F5" $color="#7B1FA2"><Users size={20} /></StatIcon>
          </StatHeader>
          {/* ✅ 실제 DB 데이터 반영 */}
          <StatValue>{personaStats.count} <span>개</span></StatValue>
        </StatCard>
        
        <StatCard>
          <StatHeader>
            <StatLabel>AI 최적화 상태</StatLabel>
            <StatIcon $bg="#FFF3E0" $color="#E65100"><Zap size={20} /></StatIcon>
          </StatHeader>
          <StatValue style={{fontSize: '24px', color: '#E65100'}}>Optimal</StatValue>
        </StatCard>
      </StatsGrid>

      {/* 메인 배너 */}
      <Banner>
        <BannerContent>
          <BannerTitle>
            <Sparkles fill="white" size={20} />
            새로운 캠페인 메시지가 필요하신가요?
          </BannerTitle>
          <BannerText>
            브랜드 톤앤매너와 고객 페르소나를 기반으로<br/>
            가장 자연스럽고 구매 전환율이 높은 메시지를 생성해 드립니다.
          </BannerText>
        </BannerContent>
        <ActionButton onClick={() => navigate('/message')}>
          메시지 생성하기 <ArrowRight size={18} />
        </ActionButton>
      </Banner>

      {/* 하단 영역 */}
      <BottomSection>
        {/* 왼쪽: 최근 생성 이력 (하드코딩 유지 - DB에 메시지 저장 기능 없음) */}
        <SectionBox>
          <SectionHeader>
            <SectionTitle><History size={18}/> 최근 생성 내역</SectionTitle>
          </SectionHeader>
          
          {recentMessages.length === 0 ? (
            <div style={{color:'#bbb', fontSize:14, textAlign:'center', padding:'32px 0'}}>아직 생성된 메시지가 없습니다</div>
          ) : recentMessages.map(item => (
            <MessageItem key={item.id} onClick={() => handleMessageClick(item)} style={{cursor:'pointer'}}>
              <MessageInfo>
                <MessageTag>{parseTag(item)}</MessageTag>
                <MessageTitle>"{item.title || '(제목 없음)'}"</MessageTitle>
                <PersonaInfo>페르소나: {item.persona_id || '-'}</PersonaInfo>
              </MessageInfo>
            </MessageItem>
          ))}
        </SectionBox>

        {/* 오른쪽: 등록된 페르소나 목록 (실제 데이터 연동) */}
        <SectionBox>
          <SectionHeader>
            <SectionTitle><TrendingUp size={18}/> 최근 등록된 페르소나</SectionTitle>
          </SectionHeader>
          
          {/* DB에 데이터가 있으면 실제 목록 표시, 없으면 하드코딩된 예시 표시 */}
          {personaStats.list.length > 0 ? (
            personaStats.list.map((persona, index) => (
              <RankItem key={persona.id || index}>
                <RankNumber $top={index < 3}>{index + 1}</RankNumber>
                <RankName>{persona.name} ({persona.age}세)</RankName>
                <RankCount>New</RankCount>
              </RankItem>
            ))
          ) : (
            // 데이터가 없을 때 보여줄 기본(하드코딩) 예시
            <>
              <RankItem>
                <RankNumber $top>1</RankNumber>
                <RankName>20대 수부지 대학생</RankName>
                <RankCount>Example</RankCount>
              </RankItem>
              <RankItem>
                <RankNumber $top>2</RankNumber>
                <RankName>30대 뷰티 고관여</RankName>
                <RankCount>Example</RankCount>
              </RankItem>
            </>
          )}
        </SectionBox>
      </BottomSection>
    </PageContainer>
  );
}