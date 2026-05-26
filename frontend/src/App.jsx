import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams } from 'react-router-dom';
import { createGlobalStyle } from 'styled-components';

import Layout from './components/Layout';
import Login from './pages/Login';
import Home from './pages/Home';
import Persona from './pages/Persona';
import Message from './pages/Message';
import Settings from './pages/Settings';
import GeneratedMessages from './pages/GeneratedMessages';
import Products from './pages/Products';

import { ToastProvider } from './components/Toast';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ChatProvider } from './context/ChatContext';
import api from './api';

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

const ServerStatusCheck = () => {
  useEffect(() => {
    api.get('/marketing/health')
      .then(() => console.log('✅ 백엔드 서버 연결 성공!'))
      .catch(() => console.warn('⚠️ 백엔드 연결 실패 (Docker 실행 여부를 확인하세요)'));
  }, []);
  return null;
};

function MessageWithKey() {
  const { convId } = useParams();
  return <Message key={convId} />;
}

function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}


function App() {
  return (
    <>
      <GlobalStyle />
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <ChatProvider>
              <Routes>
                <Route path="/login" element={<Login />} />

                <Route
                  path="/"
                  element={
                    <ProtectedRoute>
                      <ServerStatusCheck />
                      <Layout />
                    </ProtectedRoute>
                  }
                >
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
            </ChatProvider>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </>
  );
}

export default App;
