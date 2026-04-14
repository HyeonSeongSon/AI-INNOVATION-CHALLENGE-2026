import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { Home, User, MessageSquare, FileText, Settings, Plus, Trash2 } from 'lucide-react';
import { useChat } from '../context/ChatContext';

/* --- 스타일 컴포넌트 --- */
const SidebarContainer = styled.div`
  width: 260px;
  height: 100vh;
  background-color: #F7F7FA;
  padding: 24px 16px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #E0E0E0;
  flex-shrink: 0;
  overflow: hidden;
`;

const Logo = styled.div`
  font-size: 20px;
  font-weight: 800;
  color: #333;
  margin-bottom: 24px;
  padding-left: 8px;
`;

const MenuList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const MenuItem = styled(Link)`
  display: flex;
  align-items: center;
  padding: 10px 12px;
  text-decoration: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: ${props => props.$active ? '600' : '500'};
  color: ${props => props.$active ? '#1A1A1A' : '#666'};
  background-color: ${props => props.$active ? '#EBEBF0' : 'transparent'};
  transition: all 0.15s ease;

  &:hover {
    background-color: #EBEBF0;
    color: #1A1A1A;
  }

  svg {
    margin-right: 10px;
    width: 18px;
    height: 18px;
    flex-shrink: 0;
    color: ${props => props.$active ? '#5F4B8B' : '#888'};
  }
`;

const Divider = styled.div`
  height: 1px;
  background: #E0E0E0;
  margin: 16px 0 12px;
`;

const ConvSectionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 4px;
  margin-bottom: 8px;
`;

const ConvSectionTitle = styled.span`
  font-size: 11px;
  font-weight: 700;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
`;

const NewChatBtn = styled.button`
  display: flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: 1px solid #D0D0D0;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #555;
  cursor: pointer;
  transition: 0.15s;

  &:hover {
    background: #EBEBF0;
    border-color: #B0B0B0;
    color: #333;
  }

  svg { width: 12px; height: 12px; }
`;

const ConvList = styled.div`
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;

  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: #D0D0D0; border-radius: 2px; }
`;

const ConvItem = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  background: ${props => props.$active ? '#EBEBF0' : 'transparent'};
  border: 1px solid ${props => props.$active ? '#D8D0F0' : 'transparent'};
  transition: 0.15s;

  &:hover {
    background: #EBEBF0;
    .del-btn { opacity: 1; }
  }
`;

const ConvTitle = styled.div`
  flex: 1;
  font-size: 13px;
  color: ${props => props.$active ? '#1A1A1A' : '#555'};
  font-weight: ${props => props.$active ? '600' : '400'};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const ConvDate = styled.div`
  font-size: 10px;
  color: #AAA;
  flex-shrink: 0;
`;

const DelBtn = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  opacity: 0;
  flex-shrink: 0;
  transition: 0.15s;
  color: #AAA;

  &:hover {
    color: #ff4d4d;
    background: #fee;
  }

  svg { width: 13px; height: 13px; display: block; }
`;

const BottomMenu = styled.div`
  margin-top: auto;
  border-top: 1px solid #E0E0E0;
  padding-top: 12px;
`;

const EmptyConv = styled.div`
  font-size: 12px;
  color: #BBB;
  text-align: center;
  padding: 16px 0;
`;

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const now = new Date();
  const diff = now - d;
  if (diff < 86400000) {
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
  }
  if (diff < 604800000) {
    return d.toLocaleDateString('ko-KR', { weekday: 'short' });
  }
  return d.toLocaleDateString('ko-KR', { month: 'numeric', day: 'numeric' });
}

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { conversations, currentConvId, selectConversation, startNewConversation, deleteConversation } = useChat();

  const isMessagePage = location.pathname.startsWith('/message');

  const handleNewChat = () => {
    startNewConversation();
    navigate('/message');
  };

  const handleSelectConv = async (conv) => {
    await selectConversation(conv);
    navigate('/message');
  };

  const handleDelete = (e, convId) => {
    e.stopPropagation();
    deleteConversation(convId);
  };

  return (
    <SidebarContainer>
      <Logo>EASY MARKING</Logo>

      <MenuList>
        <MenuItem to="/" $active={location.pathname === '/'}>
          <Home /> 홈
        </MenuItem>
        <MenuItem to="/persona" $active={location.pathname.startsWith('/persona')}>
          <User /> 페르소나 생성
        </MenuItem>
        <MenuItem to="/message" $active={location.pathname.startsWith('/message')}>
          <MessageSquare /> 메시지 생성
        </MenuItem>
        <MenuItem to="/generated-messages" $active={location.pathname.startsWith('/generated-messages')}>
          <FileText /> 메시지 조회
        </MenuItem>
      </MenuList>

      {isMessagePage && (
        <>
          <Divider />
          <ConvSectionHeader>
            <ConvSectionTitle>대화 목록</ConvSectionTitle>
            <NewChatBtn onClick={handleNewChat}>
              <Plus /> 새 대화
            </NewChatBtn>
          </ConvSectionHeader>

          <ConvList>
            {conversations.length === 0 ? (
              <EmptyConv>대화 내역이 없습니다</EmptyConv>
            ) : (
              conversations.map(conv => (
                <ConvItem
                  key={conv.id}
                  $active={conv.id === currentConvId}
                  onClick={() => handleSelectConv(conv)}
                >
                  <ConvTitle $active={conv.id === currentConvId}>
                    {conv.title || '새 대화'}
                  </ConvTitle>
                  <ConvDate>{formatDate(conv.last_active_at)}</ConvDate>
                  <DelBtn
                    className="del-btn"
                    onClick={(e) => handleDelete(e, conv.id)}
                    title="대화 삭제"
                  >
                    <Trash2 />
                  </DelBtn>
                </ConvItem>
              ))
            )}
          </ConvList>
        </>
      )}

      <BottomMenu>
        <MenuItem to="/settings" $active={location.pathname === '/settings'}>
          <Settings /> 설정
        </MenuItem>
      </BottomMenu>
    </SidebarContainer>
  );
}
