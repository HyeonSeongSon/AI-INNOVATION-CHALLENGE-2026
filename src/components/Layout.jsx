import React from 'react';
import { Outlet } from 'react-router-dom';
import styled from 'styled-components';
import Sidebar from './Sidebar';

const Container = styled.div`
  display: flex;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
`;

const Content = styled.div`
  flex: 1;
  padding: 40px;
  background-color: #FFFFFF;
  overflow-y: auto; /* 내용이 길어지면 스크롤 */
`;

export default function Layout() {
  return (
    <Container>
      <Sidebar />
      <Content>
        {/* URL에 따라 바뀌는 페이지 내용이 여기 들어갑니다 */}
        <Outlet /> 
      </Content>
    </Container>
  );
}