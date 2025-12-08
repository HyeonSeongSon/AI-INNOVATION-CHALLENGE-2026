import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import styled from 'styled-components';
import { Home, User, MessageSquare, Settings, MessageCircle } from 'lucide-react';

/* --- 스타일 컴포넌트 --- */
const SidebarContainer = styled.div`
  width: 260px;
  height: 100vh;
  background-color: #F7F7FA;
  padding: 24px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #E0E0E0;
  flex-shrink: 0; /* 화면이 줄어들어도 사이드바 크기 유지 */
`;

const Logo = styled.div`
  font-size: 20px;
  font-weight: 800;
  color: #333;
  margin-bottom: 40px;
  padding-left: 8px;
`;

const MenuList = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const MenuItem = styled(Link)`
  display: flex;
  align-items: center;
  padding: 12px 16px;
  text-decoration: none;
  border-radius: 12px;
  font-size: 15px;
  font-weight: ${props => props.$active ? '600' : '500'};
  color: ${props => props.$active ? '#1A1A1A' : '#666'};
  background-color: ${props => props.$active ? '#EBEBF0' : 'transparent'};
  transition: all 0.2s ease;

  &:hover {
    background-color: #EBEBF0;
    color: #1A1A1A;
  }

  svg {
    margin-right: 12px;
    width: 20px;
    height: 20px;
    color: ${props => props.$active ? '#5F4B8B' : '#888'}; /* 아이콘 색상 포인트 */
  }
`;

const BottomMenu = styled.div`
  margin-top: auto;
  border-top: 1px solid #E0E0E0;
  padding-top: 16px;
`;

export default function Sidebar() {
  const location = useLocation();

  return (
    <SidebarContainer>
      <Logo>Gimozzi</Logo>
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

        {/* 새로 추가된 시뮬레이션 메뉴 */}
        <MenuItem to="/simulation" $active={location.pathname.startsWith('/simulation')}>
          <MessageCircle /> 가상 고객 시뮬레이션
        </MenuItem>
      </MenuList>
      
      <BottomMenu>
        <MenuItem to="/settings" $active={location.pathname === '/settings'}>
          <Settings /> 설정
        </MenuItem>
      </BottomMenu>
    </SidebarContainer>
  );
}