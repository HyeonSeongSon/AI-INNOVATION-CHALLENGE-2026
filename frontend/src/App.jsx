import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import Home from './pages/Home';
import Persona from './pages/Persona';
import Message from './pages/Message';
import Settings from './pages/Settings';

// 글로벌 스타일 (CSS 리셋)
import { createGlobalStyle } from 'styled-components';

const GlobalStyle = createGlobalStyle`
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, sans-serif;
  }
  
  body {
    background-color: #f5f5f5;
  }
`;

function App() {
  return (
    <>
      <GlobalStyle />
      <BrowserRouter>
        <Routes>
          {/* 로그인 페이지 (사이드바 없음) */}
          <Route path="/login" element={<Login />} />

          {/* 메인 레이아웃 (사이드바 있음) */}
          <Route path="/" element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="persona" element={<Persona />} />
            <Route path="message" element={<Message />} />
            <Route path="settings" element={<Settings />} />
          </Route>

          {/* 없는 주소로 가면 홈으로 리다이렉트 */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </>
  );
}

export default App;