import React, { useState, useRef, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import styled, { css } from 'styled-components';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Papa from 'papaparse';
import * as XLSX from 'xlsx';
import {
  Send, Settings, Sparkles, Wand2, ShoppingBag,
  Tag, Bot, Trash2, X, RefreshCw, Copy, Check, Image as ImageIcon, ExternalLink, ChevronDown,
  Paperclip, Plus
} from 'lucide-react';

// API 및 Context
import api, { pipelineApi, dbApi } from '../api';
import { useChat } from '../context/ChatContext';

// 브랜드 / 카테고리 데이터
import brandsData from '../data/brands.json';
import categoriesData from '../data/categories.json';

const USER_ID = 'son';

/* --- [1] 스타일 컴포넌트 --- */
const Container = styled.div` display: flex; height: calc(100vh - 100px); gap: 24px; max-width: 1400px; margin: 0 auto; `;
const Sidebar = styled.div` width: 340px; background: white; border-radius: 24px; border: 1px solid #eee; padding: 24px; display: flex; flex-direction: column; gap: 24px; box-shadow: 0 4px 20px rgba(0,0,0,0.02); `;
const SidebarHeader = styled.div` display: flex; align-items: center; gap: 10px; padding-bottom: 20px; border-bottom: 1px solid #f0f0f0; h3 { font-size: 18px; font-weight: 800; color: #111; } `;
const SectionLabel = styled.label` font-size: 12px; font-weight: 700; color: #888; margin-bottom: 8px; display: block; text-transform: uppercase; letter-spacing: 0.5px; `;
const FormGroup = styled.div` display: flex; flex-direction: column; `;
const Input = styled.input` padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; transition: 0.2s; &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); } `;
const Select = styled.select` padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; background: white; cursor: pointer; transition: 0.2s; &:focus { border-color: #6B4DFF; } `;
const ComboWrapper = styled.div` position: relative; `;
const ComboInput = styled.input` width: 100%; padding: 14px 40px 14px 14px; border: 1px solid #e0e0e0; border-radius: 12px; font-size: 14px; outline: none; transition: 0.2s; box-sizing: border-box; &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.1); } `;
const ComboCaret = styled.button` position: absolute; right: 12px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; color: #888; padding: 2px; display: flex; align-items: center; &:hover { color: #6B4DFF; } `;
const ComboDropdown = styled.ul` position: absolute; top: calc(100% + 4px); left: 0; right: 0; background: white; border: 1px solid #e0e0e0; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.1); max-height: 220px; overflow-y: auto; z-index: 100; margin: 0; padding: 6px 0; list-style: none; &::-webkit-scrollbar { width: 4px; } &::-webkit-scrollbar-thumb { background: #ddd; border-radius: 2px; } `;
const ComboOption = styled.li` padding: 10px 14px; font-size: 14px; cursor: pointer; color: ${p => p.$active ? '#6B4DFF' : '#333'}; font-weight: ${p => p.$active ? '700' : '400'}; background: ${p => p.$active ? 'rgba(107,77,255,0.06)' : 'transparent'}; &:hover { background: rgba(107,77,255,0.08); color: #6B4DFF; } `;
const GenerateButton = styled.button` margin-top: auto; background: linear-gradient(135deg, #111 0%, #333 100%); color: white; padding: 18px; border-radius: 16px; border: none; font-weight: 700; font-size: 16px; cursor: pointer; display: flex; justify-content: center; align-items: center; gap: 10px; transition: all 0.2s; &:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,0.2); } &:disabled { background: #eee; color: #aaa; cursor: not-allowed; transform: none; box-shadow: none; } `;
const ChatArea = styled.div` flex: 1; background: #F8F9FA; border-radius: 24px; border: 1px solid #eee; display: flex; flex-direction: column; overflow: hidden; position: relative; `;
const ChatHeader = styled.div` padding: 20px 30px; background: white; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; z-index: 10; h2 { font-size: 16px; font-weight: 700; color: #333; display: flex; align-items: center; gap: 8px; } `;
const ChatScroll = styled.div` flex: 1; padding: 30px; overflow-y: auto; display: flex; flex-direction: column; gap: 24px; &::-webkit-scrollbar { width: 6px; } &::-webkit-scrollbar-thumb { background-color: #ddd; border-radius: 3px; } `;

const MessageBubble = styled.div`
  display: flex;
  flex-direction: column;
  max-width: ${props => props.$wide ? '100%' : '800px'};
  align-self: ${props => props.$isUser ? 'flex-end' : 'flex-start'};
  ${props => props.$isUser ? css`
    align-items: flex-end;
    .bubble { background: #333; color: white; border-radius: 20px 20px 4px 20px; padding: 12px 20px; white-space: pre-line; }
  ` : css`
    align-items: flex-start;
    .bubble { background: white; color: #333; border: 1px solid #eee; border-radius: 20px 20px 20px 4px; padding: 16px 24px; box-shadow: 0 2px 10px rgba(0,0,0,0.03); line-height: 1.6; }
  `}
  .sender { font-size: 12px; color: #888; margin-bottom: 6px; margin-left: 4px; display: flex; align-items: center; gap: 4px; }
`;

const ProductGrid = styled.div` display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; width: 100%; `;
const ProductCard = styled.div`
  background: white; border: 1px solid #eee; border-radius: 16px; overflow: hidden; transition: all 0.2s; cursor: pointer; position: relative; display: flex; flex-direction: column; height: 480px;
  &:hover { transform: translateY(-4px); box-shadow: 0 10px 20px rgba(0,0,0,0.05); border-color: #6B4DFF; }
  ${props => props.$selected && css` border: 2px solid #6B4DFF; box-shadow: 0 0 0 4px rgba(107, 77, 255, 0.1); `}
  ${props => props.$disabled && css` opacity: 0.4; cursor: default; `}
  ${props => props.$locked && css`
    cursor: default;
    &:hover { transform: none; box-shadow: none; border-color: #eee; }
  `}
  ${props => props.$locked && props.$selected && css`
    &:hover { border-color: #6B4DFF; box-shadow: 0 0 0 4px rgba(107, 77, 255, 0.1); }
  `}
`;
const CardImage = styled.div`
  height: 180px; width: 100%; background: #f9f9f9; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; border-bottom: 1px solid #f0f0f0;
  img { width: 100%; height: 100%; object-fit: contain; padding: 10px; transition: 0.3s; }
  &:hover img { transform: scale(1.05); }
  .placeholder { color: #ccc; display: flex; flex-direction: column; align-items: center; gap: 8px; font-size: 12px; }
  .brand-badge { position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.7); color: white; font-size: 10px; font-weight: 700; padding: 4px 8px; border-radius: 4px; z-index: 2; }
`;
const CardContent = styled.div` padding: 16px; flex: 1; display: flex; flex-direction: column; justify-content: space-between; `;
const ProductName = styled.div` font-weight: 700; font-size: 15px; color: #222; margin-bottom: 8px; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; `;
const OneLineReview = styled.div` font-size: 14px; color: #444; background: #f0f4ff; padding: 12px; border-radius: 8px; margin-bottom: 12px; line-height: 1.6; border-left: 4px solid #6B4DFF; font-weight: 500; display: -webkit-box; -webkit-line-clamp: 5; -webkit-box-orient: vertical; overflow: hidden; flex: 1; `;
const TagContainer = styled.div` display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; `;
const TagChip = styled.span` font-size: 10px; color: #555; background: #f0f0f0; padding: 4px 8px; border-radius: 4px; font-weight: 600; `;
const ProductLinkBtn = styled.a` display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 13px; font-weight: 700; color: #6B4DFF; background: #fff; border: 1px solid #6B4DFF; padding: 10px; border-radius: 8px; text-decoration: none; transition: 0.2s; margin-top: auto; &:hover { background: #6B4DFF; color: white; } `;
const InputArea = styled.div` padding: 20px; background: white; border-top: 1px solid #eee; display: flex; flex-direction: column; gap: 8px; `;
const InputRow = styled.div` display: flex; gap: 8px; align-items: center; `;
const ChatInput = styled.textarea`
  flex: 1;
  padding: 10px 18px;
  border: 1px solid #ddd;
  border-radius: 22px;
  font-size: 14px;
  outline: none;
  resize: none;
  overflow-y: auto;
  min-height: 36px;
  max-height: 200px;
  line-height: 1.6;
  font-family: inherit;
  transition: border-color 0.2s;
  &:focus { border-color: #6B4DFF; box-shadow: 0 0 0 3px rgba(107, 77, 255, 0.08); }
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: #ddd; border-radius: 2px; }
`;
const SendBtn = styled.button` width: 36px; height: 36px; border-radius: 50%; background: #6B4DFF; color: white; border: none; cursor: pointer; flex-shrink: 0; display: flex; align-items: center; justify-content: center; &:hover { background: #5a3de0; } &:disabled { background: #ccc; cursor: not-allowed; } `;
const SelectedProductChip = styled.div`
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 10px 6px 12px; background: rgba(107, 77, 255, 0.08);
  border: 1px solid rgba(107, 77, 255, 0.3); border-radius: 20px;
  font-size: 13px; color: #6B4DFF; font-weight: 600; align-self: flex-start;
  span { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  button { background: none; border: none; cursor: pointer; color: #6B4DFF; display: flex; align-items: center; padding: 0; opacity: 0.6; &:hover { opacity: 1; } }
`;

const AttachBtn = styled.button`
  width: 36px; height: 36px; min-width: 36px; min-height: 36px;
  border-radius: 50%; background: #f4f4f4;
  border: 1.5px solid #ddd; color: #444; cursor: pointer; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; transition: all 0.15s;
  font-size: 20px; font-weight: 400; line-height: 36px; padding: 0; box-sizing: border-box;
  &:hover { background: #ebebeb; border-color: #bbb; color: #111; }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
`;

const FileChip = styled.div`
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 10px 6px 12px; background: rgba(107,77,255,0.08);
  border: 1px solid rgba(107,77,255,0.3); border-radius: 20px;
  font-size: 13px; color: #6B4DFF; font-weight: 600; align-self: flex-start;
  span { max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  button { background: none; border: none; cursor: pointer; color: #6B4DFF;
           display: flex; align-items: center; padding: 0; opacity: 0.6;
           &:hover { opacity: 1; } }
`;

const CopyBtn = styled.button`
  display: inline-flex; align-items: center; gap: 5px;
  margin-top: 8px; padding: 5px 12px;
  background: none; border: 1px solid #e0e0e0; border-radius: 8px;
  font-size: 12px; color: #888; cursor: pointer; transition: all 0.15s;
  &:hover { border-color: #6B4DFF; color: #6B4DFF; background: rgba(107,77,255,0.05); }
  &.copied { border-color: #22c55e; color: #22c55e; background: rgba(34,197,94,0.05); }
`;

const MarkdownBody = styled.div`
  line-height: 1.7;
  p { margin: 0 0 10px; }
  p:last-child { margin-bottom: 0; }
  strong { font-weight: 700; }
  em { font-style: italic; }
  h1, h2, h3, h4 { font-weight: 700; margin: 14px 0 6px; line-height: 1.4; }
  h1 { font-size: 18px; } h2 { font-size: 16px; } h3 { font-size: 15px; }
  ul, ol { margin: 6px 0 10px 20px; padding: 0; }
  li { margin-bottom: 4px; }
  a { color: #6B4DFF; text-decoration: underline; word-break: break-all; }
  a:hover { opacity: 0.75; }
  code { background: rgba(107,77,255,0.08); color: #5a3de0; padding: 2px 6px; border-radius: 4px; font-size: 13px; font-family: monospace; }
  pre { background: #f4f4f8; padding: 14px; border-radius: 10px; overflow-x: auto; margin: 10px 0; }
  pre code { background: none; padding: 0; color: #333; }
  blockquote { border-left: 3px solid #6B4DFF; margin: 10px 0; padding: 6px 14px; color: #666; background: #f8f7ff; border-radius: 0 8px 8px 0; }
  hr { border: none; border-top: 1px solid #eee; margin: 12px 0; }
  table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13px; }
  th, td { border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; }
  th { background: #f5f5f5; font-weight: 700; }
`;


/* --- [2] ComboSelect 컴포넌트 (키보드 입력 + 스크롤 선택) --- */
function ComboSelect({ value, onChange, options, placeholder }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');
  const wrapperRef = useRef(null);

  useEffect(() => {
    const handler = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setOpen(false);
        setSearch('');
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const filtered = options.filter(o => o.toLowerCase().includes(search.toLowerCase()));

  const handleInput = (e) => {
    setSearch(e.target.value);
    onChange(e.target.value);
    setOpen(true);
  };

  const handleSelect = (opt) => {
    onChange(opt);
    setSearch('');
    setOpen(false);
  };

  const handleFocus = () => {
    setSearch('');
    setOpen(true);
  };

  const handleCaretClick = () => {
    setOpen(o => !o);
    setSearch('');
  };

  return (
    <ComboWrapper ref={wrapperRef}>
      <ComboInput
        value={open ? search : value}
        onChange={handleInput}
        onFocus={handleFocus}
        placeholder={placeholder}
      />
      <ComboCaret type="button" onClick={handleCaretClick}>
        <ChevronDown size={14} />
      </ComboCaret>
      {open && filtered.length > 0 && (
        <ComboDropdown>
          {filtered.map(opt => (
            <ComboOption key={opt} onMouseDown={() => handleSelect(opt)} $active={opt === value}>
              {opt}
            </ComboOption>
          ))}
        </ComboDropdown>
      )}
    </ComboWrapper>
  );
}

/* --- [3] 메인 컴포넌트 --- */
export default function Message() {
  // URL에서 convId 읽기 (없으면 새 대화)
  const { convId } = useParams();
  const navigate = useNavigate();

  // ChatContext — 대화 목록 + in-flight 상태 관리
  const { saveMessages, loadConversations, activeConvs, setPendingConv, clearPendingConv } = useChat();

  const scrollRef = useRef(null);
  const chatInputRef = useRef(null);

  // activeState에서 로드했으면 DB 재로드 스킵 (convId 변경 시 리셋)
  const loadedFromActive = useRef(false);

  const autoResize = (el) => {
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  const parseFile = (file) => new Promise((resolve, reject) => {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext === 'csv') {
      Papa.parse(file, {
        header: true,
        skipEmptyLines: true,
        complete: (r) => resolve(r.data),
        error: (e) => reject(new Error(`CSV 파싱 실패: ${e.message}`)),
      });
    } else if (ext === 'xlsx' || ext === 'xls') {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const wb = XLSX.read(e.target.result, { type: 'array' });
          resolve(XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]], { defval: '' }));
        } catch (err) { reject(new Error(`Excel 파싱 실패: ${err.message}`)); }
      };
      reader.onerror = () => reject(new Error('파일을 읽을 수 없습니다.'));
      reader.readAsArrayBuffer(file);
    } else if (ext === 'jsonl') {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const data = e.target.result
            .split('\n').map((l) => l.trim()).filter(Boolean)
            .map((line, i) => {
              try { return JSON.parse(line); }
              catch { throw new Error(`${i + 1}번째 줄 파싱 실패`); }
            });
          resolve(data);
        } catch (err) { reject(err); }
      };
      reader.onerror = () => reject(new Error('파일을 읽을 수 없습니다.'));
      reader.readAsText(file, 'UTF-8');
    } else {
      reject(new Error('CSV, XLSX, JSONL 파일만 지원합니다.'));
    }
  });

  const handleFileSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = ''; // 동일 파일 재선택 허용
    try {
      const records = await parseFile(file);
      if (records.length === 0) { alert('파일에 데이터가 없습니다.'); return; }
      if (records.length > 50) { alert(`최대 50개까지 업로드 가능합니다. 현재: ${records.length}개`); return; }
      setUploadedFile({ name: file.name, records });
    } catch (err) { alert(err.message); }
  };

  const [personas, setPersonas] = useState([]);
  const [config, setConfig] = useState({
    personaId: '', purpose: '신제품 홍보', category: '립스틱', brand: '이니스프리'
  });

  const [messages, setMessages] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [sessionId, setSessionId] = useState(null);
  const [isConvLoading, setIsConvLoading] = useState(false);

  // messages를 항상 최신 값으로 참조 (클로저 stale 방지)
  const messagesRef = useRef([]);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  const [chatInput, setChatInput] = useState('');
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState(null);

  // 파일 업로드 상태
  const [uploadedFile, setUploadedFile] = useState(null); // { name: string, records: [] }
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  // convId 변경 시 loadedFromActive 리셋
  useEffect(() => { loadedFromActive.current = false; }, [convId]);

  // 핵심 로딩 로직: Context(in-flight) 우선 → DB 폴백
  const activeState = convId ? activeConvs.get(convId) : null;

  useEffect(() => {
    if (!convId) return;

    if (activeState) {
      // Context에 in-flight 상태 있음 → 즉시 복원 (API 진행 중이어도 메시지 보임)
      setMessages(activeState.messages);
      setIsChatLoading(activeState.isLoading);
      setIsConvLoading(false);
      if (!activeState.isLoading) {
        // API 완료 신호 → Context 정리, DB 재로드 스킵 플래그 설정
        loadedFromActive.current = true;
        clearPendingConv(convId);
      }
      return;
    }

    // activeState 없고 이미 Context에서 로드한 적 있으면 DB 재로드 스킵
    // (clearPendingConv 후 effect 재실행 시 중복 로드 방지)
    if (loadedFromActive.current) return;

    // DB에서 로드
    setIsConvLoading(true);
    dbApi.get(`/conversations/${convId}`)
      .then(res => {
        setMessages(res.data.messages || []);
        setThreadId(res.data.thread_id || null);
        setSessionId(res.data.session_id || null);
      })
      .catch(e => console.error('대화 로드 실패:', e))
      .finally(() => setIsConvLoading(false));

  }, [convId, activeState]); // eslint-disable-line react-hooks/exhaustive-deps

  // 초기 데이터 로드 (페르소나 목록 + 사이드바)
  useEffect(() => {
    loadConversations();
    const fetchPersonas = async () => {
      try {
        const response = await pipelineApi.post('/personas/list');
        const rawData = Array.isArray(response.data) ? response.data : response.data.personas || [];
        const pData = rawData.map(p => ({
          ...p,
          persona_id: p.persona_id || p.id,
          displayLabel: `${p.name} / ${p.age}세 / ${Array.isArray(p.skin_type) ? p.skin_type[0] : (p.skin_type || '정보없음')}`
        }));
        setPersonas(pData);
        if (pData.length > 0) setConfig(prev => ({ ...prev, personaId: pData[0].persona_id }));
        if (!convId) {
          setMessages([{ id: Date.now(), role: 'ai', text: '안녕하세요! 페르소나를 선택하고 맞춤 상품을 추천받아보세요.' }]);
        }
      } catch (err) {
        console.error("데이터 로드 실패:", err);
      }
    };
    fetchPersonas();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSendChat = async () => {
    if (uploadedFile) return handleSendBulkUpload();
    const text = chatInput.trim();
    if (!text || isChatLoading || isConvLoading) return;

    setChatInput('');
    if (chatInputRef.current) chatInputRef.current.style.height = '36px';

    const userMsg    = { id: Date.now(),     role: 'user', text };
    const loadingMsg = { id: Date.now() + 1, role: 'ai',  text: '처리 중...', isLoading: true };
    setMessages(prev => [...prev, userMsg, loadingMsg]);
    setIsChatLoading(true);

    const messagesWithUser  = [...messagesRef.current, userMsg];              // DB 저장용 (로딩 없음)
    const messagesWithLoading = [...messagesWithUser, loadingMsg];            // Context용 (로딩 포함)
    const currentSessionId = sessionId || `sess_${crypto.randomUUID()}`;
    let targetConvId = convId;

    try {
      if (!targetConvId) {
        // 새 대화: DB에 레코드 미리 생성 → convId 확보
        const created = await dbApi.post('/conversations', {
          user_id: USER_ID,
          session_id: currentSessionId,
          title: text.slice(0, 40),
        });
        targetConvId = created.data.id;
        await loadConversations();

        // navigate 전에 Context 등록 → 새 컴포넌트가 마운트 즉시 상태를 찾을 수 있음
        setPendingConv(targetConvId, messagesWithLoading, true);
        await saveMessages(targetConvId, messagesWithUser);
        navigate(`/message/${targetConvId}`, { replace: true });
        // 이후 코드는 구 컴포넌트 인스턴스에서 계속 실행 (targetConvId 클로저로 유지됨)
      } else {
        setPendingConv(targetConvId, messagesWithLoading, true);
        await saveMessages(targetConvId, messagesWithUser);
      }

      const response = await api.post('/marketing/chat/v2', {
        user_input: text,
        session_id: currentSessionId,
        conversation_id: targetConvId,
      }, { headers: { 'X-User-Id': USER_ID } });

      const result = response.data;

      const mappedProducts = (result.recommended_products || []).map(p => ({
        id: p.product_id,
        name: p.product_name || "상품명 없음",
        brand: p.brand || "AMORE",
        image: (p.product_image_url?.length > 0) ? p.product_image_url[0] : null,
        tags: (p.product_details?.concern?.length > 0) ? p.product_details.concern.slice(0, 5) : ["AI추천"],
        price: p.sale_price,
        productUrl: p.product_page_url || "#",
        oneLineReview: p.product_comment || "맞춤 솔루션 아이템입니다."
      }));

      let aiText = '';
      let isGenerated = false;

      if (result.status === 'failed') {
        aiText = result.error || "메시지 품질 검사를 통과하지 못했습니다. 내용을 조정하여 다시 시도해주세요.";
      } else if (result.messages?.length > 0) {
        const msg = result.messages[0];
        const title = msg.title || "";
        const content = msg.content || "";
        if (title && content) { aiText = `## ${title}\n\n${content}`; isGenerated = true; }
        else { aiText = content || title || "응답을 처리했습니다."; }
      } else if (mappedProducts.length > 0) {
        aiText = `이러한 분석을 바탕으로 **${mappedProducts.length}개의 맞춤 솔루션 상품**을 추천해 드립니다.`;
      } else {
        aiText = "응답을 처리했습니다.";
      }

      const aiMsg = {
        id: Date.now() + 2, role: 'ai', text: aiText, isGenerated,
        products: mappedProducts.length > 0 ? mappedProducts : undefined
      };
      const finalMessages = [...messagesWithUser, aiMsg];

      await saveMessages(targetConvId, finalMessages);
      setThreadId(result.thread_id || null);
      setSessionId(result.session_id || null);

      setPendingConv(targetConvId, finalMessages, false);

    } catch (error) {
      console.error("채팅 전송 실패:", error);
      const errMsg = error.response?.data?.detail || error.message;
      const errAiMsg = { id: Date.now() + 2, role: 'ai', text: `오류가 발생했습니다: ${errMsg}` };
      if (targetConvId) {
        const errMessages = [...messagesWithUser, errAiMsg];
        await saveMessages(targetConvId, errMessages).catch(() => {});
        setPendingConv(targetConvId, errMessages, false);
      } else {
        // 대화 생성 전 실패 — 로딩 메시지 제거 후 에러 표시 (DB 저장 없음)
        setMessages(prev => [...prev.filter(m => !m.isLoading), errAiMsg]);
        setIsChatLoading(false);
      }
    }
  };


  const handleSendBulkUpload = async () => {
    if (!uploadedFile || isChatLoading || isConvLoading) return;
    const { name: filename, records } = uploadedFile;
    const typedText = chatInput.trim();
    const fileLabel = `📎 ${filename} (${records.length}명)`;
    const userMsgText = typedText ? `${typedText}\n\n${fileLabel}` : fileLabel;

    setUploadedFile(null);
    setChatInput('');
    if (chatInputRef.current) chatInputRef.current.style.height = '36px';

    const userMsg    = { id: Date.now(),     role: 'user', text: userMsgText };
    const loadingMsg = { id: Date.now() + 1, role: 'ai',  text: '처리 중...', isLoading: true };

    setMessages(prev => [...prev, userMsg, loadingMsg]);
    setIsChatLoading(true);

    const messagesWithUser = [...messagesRef.current, userMsg, loadingMsg];
    const currentSessionId = sessionId || `sess_${crypto.randomUUID()}`;
    let targetConvId = convId;

    try {
      if (!targetConvId) {
        const created = await dbApi.post('/conversations', {
          user_id: USER_ID, session_id: currentSessionId, title: userMsgText.slice(0, 40),
        });
        targetConvId = created.data.id;
        await loadConversations();
        setPendingConv(targetConvId, messagesWithUser, true);
        await saveMessages(targetConvId, messagesWithUser);
        navigate(`/message/${targetConvId}`, { replace: true });
      } else {
        setPendingConv(targetConvId, messagesWithUser, true);
        await saveMessages(targetConvId, messagesWithUser);
      }

      const response = await api.post('/marketing/chat/v2', {
        user_input: typedText || fileLabel,
        session_id: currentSessionId,
        conversation_id: targetConvId,
        file_records: records,
      }, { headers: { 'X-User-Id': USER_ID } });

      const result = response.data;
      const aiText = result.messages?.[0]?.content || result.messages?.[0]?.text || '처리가 완료되었습니다.';

      const aiMsg = { id: Date.now() + 2, role: 'ai', text: aiText };
      const finalMessages = [...messagesWithUser.filter(m => !m.isLoading), aiMsg];
      await saveMessages(targetConvId, finalMessages);
      setPendingConv(targetConvId, finalMessages, false);

    } catch (error) {
      const errMsg = error.response?.data?.detail || error.message;
      const errAiMsg = { id: Date.now() + 2, role: 'ai', text: `파일 처리 오류: ${errMsg}` };
      const errMessages = [...messagesWithUser.filter(m => !m.isLoading), errAiMsg];
      if (targetConvId) {
        await saveMessages(targetConvId, errMessages).catch(() => {});
        setPendingConv(targetConvId, errMessages, false);
      } else {
        setMessages(errMessages);
        setIsChatLoading(false);
      }
    }
  };

  return (
    <Container>
      <ChatArea>
        <ChatHeader>
          <div><h2 style={{margin:0}}><Bot size={20} color="#6B4DFF"/> AI Merchandiser Agent</h2><div style={{fontSize:'12px', color:'#888', marginTop: 4}}>Powered by Amore GPT</div></div>
        </ChatHeader>
        <ChatScroll ref={scrollRef}>
          {(messages || []).map((msg, idx) => (
            <MessageBubble key={msg.id || idx} $isUser={msg.role === 'user'} $wide={msg.products && msg.products.length > 0}>
              <div className="sender">{msg.role === 'ai' ? <><Sparkles size={12}/> AI Agent</> : 'Me'}</div>
              {msg.isLoading ? (
                <div className="bubble" style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#888' }}>
                  <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} />
                  처리 중...
                </div>
              ) : msg.text && (
                <div className="bubble">
                  {msg.role === 'ai' ? (
                    <MarkdownBody>
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ href, children }) => (
                            <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
                          )
                        }}
                      >
                        {msg.text}
                      </ReactMarkdown>
                    </MarkdownBody>
                  ) : (
                    msg.text
                  )}
                </div>
              )}
              {msg.isGenerated && (
                <CopyBtn
                  className={copiedMsgId === msg.id ? 'copied' : ''}
                  onClick={() => {
                    navigator.clipboard.writeText(msg.text.replace(/^##\s+.+\n\n/, '').replace(/\*\*/g, ''));
                    setCopiedMsgId(msg.id);
                    setTimeout(() => setCopiedMsgId(null), 2000);
                  }}
                >
                  {copiedMsgId === msg.id ? <><Check size={12}/> 복사됨</> : <><Copy size={12}/> 텍스트 복사</>}
                </CopyBtn>
              )}
              {msg.products && msg.products.length > 0 && (
                <ProductGrid>
                  {msg.products.map(product => (
                    <ProductCard key={product.id} onDoubleClick={() => {
                      setChatInput(prev => (prev ? prev + ' ' : '') + product.id);
                      chatInputRef.current?.focus();
                    }}>
                      <CardImage>
                        <span className="brand-badge">{product.brand}</span>
                        {product.image ? (
                           <img src={product.image} alt={product.name} onError={(e) => { e.target.style.display='none'; e.target.nextSibling.style.display='flex'; }} />
                        ) : null}
                        <div className="placeholder" style={{display: product.image ? 'none' : 'flex'}}>
                           <ImageIcon size={24} color="#ddd"/>
                           <span>No Image</span>
                        </div>
                      </CardImage>
                      <CardContent>
                        <ProductName>{product.name}</ProductName>
                        <div style={{fontSize:'11px', color:'#bbb', marginBottom:'8px', fontFamily:'monospace'}}>{product.id}</div>
                        <OneLineReview>{product.oneLineReview}</OneLineReview>
                        <TagContainer>{product.tags?.slice(0, 3).map((t,i)=><TagChip key={i}>{t}</TagChip>)}</TagContainer>
                        <ProductLinkBtn href={product.productUrl} target="_blank">
                          <ExternalLink size={14}/> 추천 상품 확인하기
                        </ProductLinkBtn>
                      </CardContent>
                    </ProductCard>
                  ))}
                </ProductGrid>
              )}
            </MessageBubble>
          ))}
        </ChatScroll>
        <InputArea>
          {uploadedFile && (
            <FileChip>
              <Paperclip size={13} />
              <span>{uploadedFile.name} ({uploadedFile.records.length}명)</span>
              <button onClick={() => setUploadedFile(null)}><X size={14} /></button>
            </FileChip>
          )}
          <InputRow>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls,.jsonl"
              style={{ display: 'none' }}
              onChange={handleFileSelect}
            />
            <AttachBtn
              onClick={() => fileInputRef.current?.click()}
              disabled={isChatLoading || isConvLoading}
              title="CSV / XLSX / JSONL 업로드"
            >
              +
            </AttachBtn>
            <ChatInput
              ref={chatInputRef}
              placeholder={uploadedFile ? `메시지를 입력하거나 그냥 Enter로 파일만 업로드` : '메시지를 입력하세요'}
              value={chatInput}
              onChange={(e) => { setChatInput(e.target.value); autoResize(e.target); }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  uploadedFile ? handleSendBulkUpload() : handleSendChat();
                }
              }}
              disabled={isChatLoading || isConvLoading}
              rows={1}
            />
            <SendBtn
              onClick={uploadedFile ? handleSendBulkUpload : handleSendChat}
              disabled={isChatLoading || isConvLoading || (!chatInput.trim() && !uploadedFile)}
            >
              {isChatLoading ? <RefreshCw size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <Send size={18} />}
            </SendBtn>
          </InputRow>
        </InputArea>
      </ChatArea>

    </Container>
  );
}
