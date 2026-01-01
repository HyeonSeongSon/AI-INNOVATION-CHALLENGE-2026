import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import Home from './pages/Home';
import Persona from './pages/Persona';
import Message from './pages/Message';
import Settings from './pages/Settings';

// ✅ ToastProvider 불러오기
import { ToastProvider } from './components/Toast'; 

// ✅ [추가됨] ChatProvider 불러오기 (이게 없어서 에러가 났던 것입니다!)
import { ChatProvider } from './context/ChatContext';

// ✅ api.jsx 불러오기
import api from './api';

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

// 화면에 에러를 띄우지 않는 조용한 버전
const ServerStatusCheck = () => {
  useEffect(() => {
    const checkServer = async () => {
      try {
        await api.get('/'); 
        console.log("✅ 백엔드 서버 연결 성공!");
      } catch (error) {
        console.warn("⚠️ 백엔드 연결 실패 (Docker 실행 여부를 확인하세요)");
      }
    };
    
    checkServer();
  }, []); 

  return null;
};

function App() {
  return (
    <>
      <GlobalStyle />
      
      <ToastProvider>
        {/* 서버 상태 체크 */}
        <ServerStatusCheck />

        {/* ✅ [추가됨] 여기서 ChatProvider로 감싸줍니다! */}
        <ChatProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />

              <Route path="/" element={<Layout />}>
                <Route index element={<Home />} />
                <Route path="persona" element={<Persona />} />
                <Route path="message" element={<Message />} />
                <Route path="settings" element={<Settings />} />
              </Route>

              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </ChatProvider>
        
      </ToastProvider>
    </>
  );
}

export default App;