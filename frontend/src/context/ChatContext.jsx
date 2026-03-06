import React, { createContext, useState, useContext, useEffect, useCallback } from 'react';
import api from '../api';

const ChatContext = createContext();

const USER_ID = 'son';

export const ChatProvider = ({ children }) => {
  // 대화 목록 (사이드바용)
  const [conversations, setConversations] = useState([]);
  // 현재 활성 대화
  const [currentConvId, setCurrentConvId] = useState(() => localStorage.getItem('current_conv_id'));
  const [currentThreadId, setCurrentThreadId] = useState(null);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  // 현재 대화의 UI 메시지
  const [messages, setMessages] = useState([]);

  // currentConvId를 localStorage에 동기화
  useEffect(() => {
    if (currentConvId) {
      localStorage.setItem('current_conv_id', currentConvId);
    } else {
      localStorage.removeItem('current_conv_id');
    }
  }, [currentConvId]);

  // 대화 목록 로드
  const loadConversations = useCallback(async () => {
    try {
      const res = await api.get(`/conversations?user_id=${USER_ID}`);
      setConversations(res.data || []);
      return res.data || [];
    } catch (e) {
      console.error('대화 목록 로드 실패:', e);
      return [];
    }
  }, []);

  // 새로고침 시 currentConvId로 대화 복원
  useEffect(() => {
    const restore = async () => {
      const convs = await loadConversations();
      const savedConvId = localStorage.getItem('current_conv_id');
      if (savedConvId) {
        const target = convs.find(c => c.id === savedConvId);
        if (target) {
          try {
            const res = await api.get(`/conversations/${savedConvId}`);
            const conv = res.data;
            setMessages(conv.messages || []);
            setCurrentConvId(conv.id);
            setCurrentThreadId(conv.thread_id);
            setCurrentSessionId(conv.session_id);
          } catch (e) {
            console.error('대화 복원 실패:', e);
          }
        }
      }
    };
    restore();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 사이드바에서 기존 대화 선택
  const selectConversation = useCallback(async (conv) => {
    try {
      const res = await api.get(`/conversations/${conv.id}`);
      const detail = res.data;
      setMessages(detail.messages || []);
      setCurrentConvId(detail.id);
      setCurrentThreadId(detail.thread_id);
      setCurrentSessionId(detail.session_id);
    } catch (e) {
      console.error('대화 불러오기 실패:', e);
    }
  }, []);

  // /marketing/chat 응답 후 호출
  const setCurrentConversation = useCallback((convId, threadId, sessionId) => {
    setCurrentConvId(convId);
    setCurrentThreadId(threadId);
    setCurrentSessionId(sessionId);
  }, []);

  // 새 대화 시작 (상태 초기화)
  const startNewConversation = useCallback(() => {
    setCurrentConvId(null);
    setCurrentThreadId(null);
    setCurrentSessionId(null);
    setMessages([]);
    localStorage.removeItem('current_conv_id');
  }, []);

  // 메시지 추가
  const addMessage = useCallback((message) => {
    setMessages(prev => [...prev, message]);
  }, []);

  // DB에 메시지 + 제목 저장
  const saveMessages = useCallback(async (convId, msgs, title) => {
    if (!convId) return;
    try {
      await api.put(`/conversations/${convId}/messages`, {
        messages: msgs,
        title: title || undefined,
      });
      // 목록의 title/last_active_at 갱신
      setConversations(prev =>
        prev.map(c => c.id === convId ? { ...c, title: title || c.title } : c)
      );
    } catch (e) {
      console.error('메시지 저장 실패:', e);
    }
  }, []);

  // 대화 삭제
  const deleteConversation = useCallback(async (convId) => {
    try {
      await api.delete(`/conversations/${convId}`);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (currentConvId === convId) {
        startNewConversation();
      }
    } catch (e) {
      console.error('대화 삭제 실패:', e);
    }
  }, [currentConvId, startNewConversation]);

  // 대화 초기화 (기존 clearChat 호환)
  const clearChat = useCallback(() => {
    startNewConversation();
  }, [startNewConversation]);

  return (
    <ChatContext.Provider value={{
      // 상태
      conversations,
      currentConvId,
      currentThreadId,
      currentSessionId,
      messages,
      // 메서드
      loadConversations,
      selectConversation,
      setCurrentConversation,
      startNewConversation,
      addMessage,
      setMessages,
      saveMessages,
      deleteConversation,
      clearChat,
    }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
