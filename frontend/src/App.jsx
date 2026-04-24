import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import Layout from './components/Layout';
import Login from './pages/Login';
import Home from './pages/Home';
import Persona from './pages/Persona';
import Message from './pages/Message';
import Settings from './pages/Settings';
import GeneratedMessages from './pages/GeneratedMessages';
import Products from './pages/Products';

// ToastProvider 불러오기
import { ToastProvider } from './components/Toast'; 

//  ChatProvider 불러오기
import { ChatProvider } from './context/ChatContext';

// api.jsx 불러오기
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
        await api.get('/marketing/health');
        console.log("✅ 백엔드 서버 연결 성공!");
      } catch (error) {
        console.warn("⚠️ 백엔드 연결 실패 (Docker 실행 여부를 확인하세요)");
      }
    };
    
    checkServer();
  }, []); 

  return null;
};

// convId가 바뀔 때마다 Message를 완전히 재마운트시키는 래퍼
function MessageWithKey() {
  const { convId } = useParams();
  return <Message key={convId} />;
}

function App() {
  return (
    <>
      <GlobalStyle />
      
      <ToastProvider>
        {/* 서버 상태 체크 */}
        <ServerStatusCheck />

        <ChatProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />

              <Route path="/" element={<Layout />}>
                <Route index element={<Home />} />
                <Route path="persona" element={<Persona />} />
                <Route path="message" element={<Message key="new" />} />
                <Route path="message/:convId" element={<MessageWithKey />} />
                <Route path="generated-messages" element={<GeneratedMessages />} />
                <Route path="products" element={<Products />} />
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