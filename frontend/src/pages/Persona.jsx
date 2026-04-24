import React, { useState, useEffect } from 'react';
import styled from 'styled-components';
import {
  Plus, X, User, Sparkles, AlertCircle, ChevronLeft, ChevronRight, Trash2, Upload
} from 'lucide-react';

import { useToast } from '../components/Toast';
import { pipelineApi } from '../api';

const PAGE_SIZE = 20;

/* ============================================================
   Styled Components
   ============================================================ */

const Container = styled.div`
  flex: 1;
  padding: 32px;
  overflow-y: auto;
  background: #f5f5f5;
  min-height: 0;
`;

const PageHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;

  h1 {
    font-size: 22px;
    font-weight: 800;
    color: #1A1A1A;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 8px;
  }
`;

const TotalBadge = styled.span`
  background: #EEE9FF;
  color: #6B4DFF;
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 20px;
  margin-left: 4px;
`;

const AddButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  background: #6B4DFF;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;

  &:hover { background: #5a3de0; }
`;

const FileButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  background: white;
  color: #6B4DFF;
  border: 1.5px solid #6B4DFF;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s;

  &:hover { background: #F5F0FF; }
`;

const TableCard = styled.div`
  background: #fff;
  border: 1px solid #E0E0E0;
  border-radius: 12px;
  overflow: hidden;
`;

const TableWrapper = styled.div`
  overflow-x: auto;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  min-width: 780px;
`;

const Th = styled.th`
  padding: 10px 14px;
  text-align: left;
  font-size: 11px;
  font-weight: 700;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  background: #F7F7FA;
  border-bottom: 1px solid #EBEBF0;
  white-space: nowrap;
`;

const CheckTh = styled(Th)`
  width: 40px;
  padding: 10px 0 10px 14px;
`;

const Tr = styled.tr`
  border-bottom: 1px solid #F0F0F0;
  cursor: pointer;
  transition: background 0.1s;

  &:last-child { border-bottom: none; }
  &:hover { background: #F7F7FA; }
  ${props => props.$selected && 'background: #F5F2FF !important;'}
`;

const Td = styled.td`
  padding: 11px 14px;
  font-size: 13px;
  color: #333;
  vertical-align: middle;
`;

const CheckTd = styled(Td)`
  width: 40px;
  padding: 11px 0 11px 14px;
`;

const TruncatedTd = styled(Td)`
  max-width: 360px;
`;

const ClampedText = styled.div`
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  white-space: normal;
  line-height: 1.5;
  font-size: 12px;
  color: #666;
`;

const Checkbox = styled.input.attrs({ type: 'checkbox' })`
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: #6B4DFF;
`;

const TagBadge = styled.span`
  display: inline-block;
  background: #F0EDFF;
  color: #6B4DFF;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 6px;
  white-space: nowrap;
  margin-right: 3px;
`;

const ConcernBadge = styled(TagBadge)`
  background: #FFF0F0;
  color: #D93025;
`;

const SelectionBar = styled.div`
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: #F0EDFF;
  border-bottom: 1px solid #DDD8FF;
  font-size: 13px;
  font-weight: 600;
  color: #5a3ee0;
`;

const DeleteButton = styled.button`
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  background: #fff;
  color: #D93025;
  border: 1px solid #FFCDD2;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  margin-left: auto;
  transition: all 0.15s;

  &:hover { background: #FFF0F0; border-color: #D93025; }
  svg { width: 13px; height: 13px; }
`;

const EmptyRow = styled.tr`
  td {
    padding: 48px;
    text-align: center;
    color: #BBB;
    font-size: 14px;
  }
`;

const Pagination = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid #F0F0F0;
  font-size: 13px;
  color: #555;
`;

const PageBtn = styled.button`
  display: flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 12px;
  border: 1.5px solid #D8D8D8;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  color: #555;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.18s;
  white-space: nowrap;

  &:hover:not(:disabled) {
    background: #F0EDFF;
    border-color: #6B4DFF;
    color: #6B4DFF;
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(107, 77, 255, 0.15);
  }
  &:disabled { opacity: 0.35; cursor: not-allowed; transform: none; box-shadow: none; }
  svg { width: 14px; height: 14px; flex-shrink: 0; }
`;

const CurrentPage = styled.span`
  font-weight: 700;
  color: #6B4DFF;
  min-width: 20px;
  text-align: center;
`;

/* 모달 */
const ModalOverlay = styled.div`
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(2px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
`;

const ModalBox = styled.div`
  background: #fff;
  border-radius: 16px;
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 28px 32px;
  position: relative;

  &::-webkit-scrollbar { width: 5px; }
  &::-webkit-scrollbar-thumb { background: #D0D0D0; border-radius: 3px; }
`;

const AnalyzingOverlay = styled.div`
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(255, 255, 255, 0.98);
  z-index: 50;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border-radius: 16px;
`;

const PulseRing = styled.div`
  width: 80px;
  height: 80px;
  background: rgba(107, 77, 255, 0.1);
  border-radius: 50%;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;

  &::before, &::after {
    content: '';
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    border: 2px solid #6B4DFF;
    animation: pulse 2s linear infinite;
    opacity: 0;
  }
  &::after { animation-delay: 1s; }
  @keyframes pulse {
    0% { transform: scale(1); opacity: 0.8; }
    100% { transform: scale(2.5); opacity: 0; }
  }
`;

/* ============================================================
   Helper
   ============================================================ */

function formatDate(dt) {
  if (!dt) return '-';
  const d = new Date(dt);
  return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

/* ============================================================
   Main Component
   ============================================================ */

export default function PersonaManager() {
  const [personas, setPersonas] = useState([]);
  const [loading, setLoading] = useState(false);

  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState(new Set());

  // 검색 쿼리 모달
  const [queryModal, setQueryModal] = useState({ open: false, persona: null, data: null, loading: false, error: null });

  // 페르소나 생성 모달 (텍스트)
  const [showTextModal, setShowTextModal] = useState(false);
  const [personaText, setPersonaText] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // 페르소나 생성 모달 (파일)
  const [showFileModal, setShowFileModal] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [isFileCreating, setIsFileCreating] = useState(false);
  // fileProgress: null | { total, current, done, succeeded, failed, results: [{name, success, error?}] }
  const [fileProgress, setFileProgress] = useState(null);

  const { addToast } = useToast();

  /* 목록 로드 */
  const fetchPersonas = async () => {
    setLoading(true);
    try {
      const response = await pipelineApi.post('/personas/list');
      const rawData = Array.isArray(response.data) ? response.data : response.data.personas || [];
      const formatted = rawData.map(p => ({
        ...p,
        id: p.persona_id || p.id,
        skinType: p.skin_type || [],
        skinConcerns: p.concerns || p.skin_concerns || [],
        aiAnalysis: {
          reasoning: p.ai_analysis?.ai_analysis_text || p.persona_summary || '',
        },
      }));
      setPersonas(formatted);
    } catch (err) {
      console.warn('페르소나 목록 로드 실패:', err);
      setPersonas([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPersonas(); }, []);

  /* 페이지네이션 */
  const totalPages = Math.max(1, Math.ceil(personas.length / PAGE_SIZE));
  const pagedPersonas = personas.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  /* 체크박스 */
  const allChecked = pagedPersonas.length > 0 && pagedPersonas.every(p => selectedIds.has(p.id));
  const someChecked = pagedPersonas.some(p => selectedIds.has(p.id));

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedIds(new Set(pagedPersonas.map(p => p.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleToggleSelect = (e, id) => {
    e.stopPropagation();
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  /* 일괄 삭제 */
  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`선택한 ${selectedIds.size}개의 페르소나를 삭제하시겠습니까?`)) return;
    try {
      await pipelineApi.delete('/personas', { data: { ids: [...selectedIds] } });
      setSelectedIds(new Set());
      await fetchPersonas();
      addToast(`${selectedIds.size}개 삭제되었습니다.`, 'info');
    } catch (err) {
      console.error('삭제 실패:', err);
      addToast('삭제 실패: 서버 오류', 'error');
    }
  };

  /* 행 클릭 → 검색 쿼리 모달 */
  const handleRowClick = async (persona) => {
    setQueryModal({ open: true, persona, data: null, loading: true, error: null });
    try {
      const res = await pipelineApi.post('/product-search-queries/get', { persona_id: persona.id });
      setQueryModal(prev => ({ ...prev, loading: false, data: res.data }));
    } catch {
      setQueryModal(prev => ({ ...prev, loading: false, error: '검색 쿼리가 아직 생성되지 않았습니다.' }));
    }
  };

  /* 페르소나 생성 */
  const handleCreateFromText = async () => {
    if (!personaText.trim()) return addToast('페르소나 설명을 입력해주세요.', 'error');
    setIsCreating(true);
    try {
      await pipelineApi.post('/pipeline/personas/create-from-text', { text: personaText });
      await fetchPersonas();
      addToast('페르소나 생성 완료!', 'success');
      setShowTextModal(false);
      setPersonaText('');
    } catch (error) {
      const errMsg = error.response?.data?.detail
        ? (typeof error.response.data.detail === 'string' ? error.response.data.detail : JSON.stringify(error.response.data.detail))
        : error.message;
      addToast(`생성 실패: ${errMsg}`, 'error');
    } finally {
      setIsCreating(false);
    }
  };

  /* 파일로 페르소나 생성 (SSE 스트리밍) */
  const handleCreateFromFile = async () => {
    if (!uploadFile) return addToast('파일을 선택해주세요.', 'error');
    setIsFileCreating(true);
    setFileProgress(null);

    const formData = new FormData();
    formData.append('file', uploadFile);

    try {
      const response = await fetch('http://localhost:8020/api/pipeline/personas/create-from-file', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        addToast(`생성 실패: ${err.detail || response.statusText}`, 'error');
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const chunks = buffer.split('\n\n');
        buffer = chunks.pop();

        for (const chunk of chunks) {
          const dataLine = chunk.split('\n').find(l => l.startsWith('data: '));
          if (!dataLine) continue;
          const event = JSON.parse(dataLine.slice(6));

          if (event.type === 'error') {
            addToast(`생성 실패: ${event.detail}`, 'error');
            return;
          }

          if (event.type === 'progress') {
            setFileProgress(prev => ({
              total: event.total,
              current: event.current,
              done: false,
              succeeded: (prev?.succeeded ?? 0) + (event.success ? 1 : 0),
              failed: (prev?.failed ?? 0) + (event.success ? 0 : 1),
              results: [...(prev?.results ?? []), {
                name: event.name,
                success: event.success,
                error: event.error,
              }],
            }));
          }

          if (event.type === 'done') {
            setFileProgress(prev => ({ ...prev, done: true, succeeded: event.succeeded, failed: event.failed }));
            await fetchPersonas();
          }
        }
      }
    } catch (error) {
      addToast(`생성 실패: ${error.message}`, 'error');
    } finally {
      setIsFileCreating(false);
    }
  };

  return (
    <Container>
      <PageHeader>
        <h1>
          <User size={22} color="#6B4DFF" />
          페르소나 관리
          <TotalBadge>총 {personas.length}개</TotalBadge>
        </h1>
        <div style={{ display: 'flex', gap: 8 }}>
          <FileButton onClick={() => { setShowFileModal(true); setFileResult(null); setUploadFile(null); }}>
            <Upload size={15} /> 파일로 페르소나 만들기
          </FileButton>
          <AddButton onClick={() => setShowTextModal(true)}>
            <Plus size={15} /> 새 페르소나 만들기
          </AddButton>
        </div>
      </PageHeader>

      <TableCard>
        {/* 선택 삭제 바 */}
        {someChecked && (
          <SelectionBar>
            <span>{selectedIds.size}개 선택됨</span>
            <DeleteButton onClick={handleDeleteSelected}>
              <Trash2 /> 삭제
            </DeleteButton>
          </SelectionBar>
        )}

        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <CheckTh>
                  <Checkbox
                    checked={allChecked}
                    ref={el => { if (el) el.indeterminate = someChecked && !allChecked; }}
                    onChange={handleSelectAll}
                    onClick={e => e.stopPropagation()}
                  />
                </CheckTh>
                <Th>이름</Th>
                <Th>나이 / 성별 / 직업</Th>
                <Th>페르소나 ID</Th>
                <Th>고민</Th>
                <Th>요약</Th>
                <Th>등록일</Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <EmptyRow><td colSpan={7}>불러오는 중...</td></EmptyRow>
              ) : pagedPersonas.length === 0 ? (
                <EmptyRow><td colSpan={7}>등록된 페르소나가 없습니다. 새 페르소나를 추가해보세요!</td></EmptyRow>
              ) : (
                pagedPersonas.map(p => (
                  <Tr
                    key={p.id}
                    $selected={selectedIds.has(p.id)}
                    onDoubleClick={() => handleRowClick(p)}
                  >
                    <CheckTd>
                      <Checkbox
                        checked={selectedIds.has(p.id)}
                        onChange={e => handleToggleSelect(e, p.id)}
                        onClick={e => e.stopPropagation()}
                      />
                    </CheckTd>
                    <Td style={{ fontWeight: 700 }}>{p.name}</Td>
                    <Td style={{ color: '#666' }}>
                      {[p.age ? `${p.age}세` : null, p.gender, p.occupation].filter(Boolean).join(' / ') || '-'}
                    </Td>
                    <Td style={{ fontFamily: 'monospace', fontSize: 11, color: '#999', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.id || <span style={{ color: '#ccc' }}>-</span>}
                    </Td>
                    <Td>
                      {p.skinConcerns?.length > 0
                        ? p.skinConcerns.slice(0, 2).map(c => <ConcernBadge key={c}>{c}</ConcernBadge>)
                        : <span style={{ color: '#ccc' }}>-</span>}
                    </Td>
                    <TruncatedTd>
                      <ClampedText>{p.aiAnalysis?.reasoning || '-'}</ClampedText>
                    </TruncatedTd>
                    <Td style={{ whiteSpace: 'nowrap', color: '#888', fontSize: 12 }}>
                      {formatDate(p.persona_created_at)}
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </Table>
        </TableWrapper>

        {/* 페이지네이션 */}
        <Pagination>
          <span style={{ color: '#AAA', fontSize: 12 }}>
            {personas.length > 0
              ? `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, personas.length)} / ${personas.length}`
              : ''}
          </span>
          <PageBtn onClick={() => { setPage(p => p - 1); setSelectedIds(new Set()); }} disabled={page <= 1}>
            <ChevronLeft /> 이전
          </PageBtn>
          <CurrentPage>{page}</CurrentPage>
          <span style={{ color: '#AAA' }}>/ {totalPages}</span>
          <PageBtn onClick={() => { setPage(p => p + 1); setSelectedIds(new Set()); }} disabled={page >= totalPages}>
            다음 <ChevronRight />
          </PageBtn>
        </Pagination>
      </TableCard>

      {/* 검색 쿼리 모달 */}
      {queryModal.open && (
        <ModalOverlay onClick={() => setQueryModal(prev => ({ ...prev, open: false }))}>
          <ModalBox onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <div>
                <div style={{ fontSize: 20, fontWeight: 800, color: '#111' }}>{queryModal.persona?.name}</div>
                <div style={{ fontSize: 13, color: '#888', marginTop: 4 }}>검색 쿼리</div>
              </div>
              <button
                onClick={() => setQueryModal(prev => ({ ...prev, open: false }))}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#aaa', padding: 4, display: 'flex', alignItems: 'center' }}
              >
                <X size={22} />
              </button>
            </div>

            {queryModal.loading && (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#888' }}>
                <div style={{ fontSize: 14 }}>쿼리를 불러오는 중...</div>
              </div>
            )}

            {queryModal.error && (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#aaa' }}>
                <AlertCircle size={32} style={{ marginBottom: 12, display: 'block', margin: '0 auto 12px' }} />
                <div style={{ fontSize: 14 }}>{queryModal.error}</div>
              </div>
            )}

            {queryModal.data && (() => {
              const labels = { need: '니즈 쿼리', preference: '선호 쿼리', retrieval: '검색 쿼리', persona: '페르소나 쿼리' };
              const colors = {
                need: { bg: '#F0EBFF', color: '#6B4DFF' },
                preference: { bg: '#fff0f6', color: '#c41d7f' },
                retrieval: { bg: '#e6f7ff', color: '#1890ff' },
                persona: { bg: '#f6ffed', color: '#389e0d' },
              };
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {Object.entries(labels).map(([key, label]) => (
                    <div key={key} style={{ padding: '16px 20px', borderRadius: 14, border: '1px solid #eee', background: '#fafafa' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: colors[key].color, background: colors[key].bg, display: 'inline-block', padding: '3px 10px', borderRadius: 20, marginBottom: 8 }}>
                        {label}
                      </div>
                      <div style={{ fontSize: 14, color: '#333', lineHeight: 1.6 }}>
                        {queryModal.data[key]?.text || '-'}
                      </div>
                    </div>
                  ))}
                </div>
              );
            })()}
          </ModalBox>
        </ModalOverlay>
      )}

      {/* 페르소나 생성 모달 */}
      {showTextModal && (
        <ModalOverlay onClick={() => { if (!isCreating) { setShowTextModal(false); setPersonaText(''); } }}>
          <ModalBox onClick={e => e.stopPropagation()}>
            {isCreating && (
              <AnalyzingOverlay>
                <PulseRing>
                  <Sparkles size={32} color="#6B4DFF" fill="#6B4DFF" />
                </PulseRing>
                <div style={{ fontSize: 18, fontWeight: 700, color: '#333', textAlign: 'center' }}>
                  페르소나를 생성 중입니다...
                  <span style={{ display: 'block', marginTop: 8, fontSize: 14, fontWeight: 400, color: '#888' }}>
                    입력 내용을 분석하고 검색 쿼리를 생성하는 중
                  </span>
                </div>
              </AnalyzingOverlay>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 20, fontWeight: 'bold', color: '#333', margin: 0 }}>새 페르소나 만들기</h2>
              <X style={{ cursor: 'pointer', color: '#999' }} onClick={() => { if (!isCreating) { setShowTextModal(false); setPersonaText(''); } }} />
            </div>

            <p style={{ fontSize: 14, color: '#666', marginBottom: 16, lineHeight: 1.6 }}>
              고객의 특성을 자유롭게 입력해주세요. AI가 자동으로 구조화하고 검색 쿼리를 생성합니다.
            </p>

            <textarea
              value={personaText}
              onChange={e => setPersonaText(e.target.value)}
              placeholder="예) 28살 직장인 여성, 지성·복합성 피부, 여드름과 모공 고민, 히알루론산 선호, 알코올 기피, 가성비 쇼핑 선호..."
              disabled={isCreating}
              style={{
                width: '100%', minHeight: '160px', padding: '14px', fontSize: '14px',
                border: '1px solid #ddd', borderRadius: '12px', resize: 'vertical',
                outline: 'none', fontFamily: 'inherit', lineHeight: '1.6',
                boxSizing: 'border-box', transition: '0.2s',
              }}
              onFocus={e => e.target.style.borderColor = '#6B4DFF'}
              onBlur={e => e.target.style.borderColor = '#ddd'}
              autoFocus
            />

            <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
              <button
                onClick={() => { setShowTextModal(false); setPersonaText(''); }}
                disabled={isCreating}
                style={{ flex: 1, padding: 14, borderRadius: 12, border: 'none', background: '#f0f0f0', color: '#555', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}
              >
                취소
              </button>
              <button
                onClick={handleCreateFromText}
                disabled={isCreating || !personaText.trim()}
                style={{ flex: 1, padding: 14, borderRadius: 12, border: 'none', background: '#6B4DFF', color: 'white', fontWeight: 700, fontSize: 15, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}
              >
                <Sparkles size={16} style={{ marginBottom: -2 }} />
                {isCreating ? '생성 중...' : '페르소나 생성'}
              </button>
            </div>
          </ModalBox>
        </ModalOverlay>
      )}
      {/* 파일로 페르소나 생성 모달 */}
      {showFileModal && (
        <ModalOverlay onClick={() => { if (!isFileCreating) { setShowFileModal(false); setUploadFile(null); setFileProgress(null); } }}>
          <ModalBox onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 20, fontWeight: 'bold', color: '#333', margin: 0 }}>파일로 페르소나 만들기</h2>
              <X style={{ cursor: isFileCreating ? 'not-allowed' : 'pointer', color: '#999' }} onClick={() => { if (!isFileCreating) { setShowFileModal(false); setUploadFile(null); setFileProgress(null); } }} />
            </div>

            {/* 파일 선택 화면 */}
            {!fileProgress && !isFileCreating && (
              <>
                <p style={{ fontSize: 14, color: '#666', marginBottom: 16, lineHeight: 1.6 }}>
                  CSV, JSON, JSONL 파일을 업로드하면 각 행/항목을 페르소나로 일괄 생성합니다.
                </p>
                <label style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                  gap: 10, padding: '32px 20px', border: '2px dashed', borderRadius: 12,
                  cursor: 'pointer', background: uploadFile ? '#F5F0FF' : '#fafafa',
                  borderColor: uploadFile ? '#6B4DFF' : '#ddd', transition: '0.2s',
                }}>
                  <Upload size={28} color={uploadFile ? '#6B4DFF' : '#aaa'} />
                  <span style={{ fontSize: 14, color: uploadFile ? '#6B4DFF' : '#999', fontWeight: uploadFile ? 700 : 400 }}>
                    {uploadFile ? uploadFile.name : '파일을 클릭하거나 드래그하세요'}
                  </span>
                  <span style={{ fontSize: 12, color: '#bbb' }}>지원 형식: .csv, .json, .jsonl</span>
                  <input type="file" accept=".csv,.json,.jsonl" style={{ display: 'none' }} onChange={e => setUploadFile(e.target.files[0] || null)} />
                </label>
                <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
                  <button onClick={() => { setShowFileModal(false); setUploadFile(null); }} style={{ flex: 1, padding: 14, borderRadius: 12, border: 'none', background: '#f0f0f0', color: '#555', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}>취소</button>
                  <button onClick={handleCreateFromFile} disabled={!uploadFile} style={{ flex: 1, padding: 14, borderRadius: 12, border: 'none', background: '#6B4DFF', color: 'white', fontWeight: 700, fontSize: 15, cursor: uploadFile ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, opacity: uploadFile ? 1 : 0.5 }}>
                    <Upload size={16} /> 페르소나 생성
                  </button>
                </div>
              </>
            )}

            {/* 진행 중 화면 */}
            {isFileCreating && fileProgress && !fileProgress.done && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#666', marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, color: '#333' }}>{fileProgress.current} / {fileProgress.total} 생성 중...</span>
                    <span>{Math.round((fileProgress.current / fileProgress.total) * 100)}%</span>
                  </div>
                  <div style={{ height: 8, background: '#eee', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{ height: '100%', background: '#6B4DFF', borderRadius: 99, width: `${(fileProgress.current / fileProgress.total) * 100}%`, transition: 'width 0.3s' }} />
                  </div>
                </div>
                <div style={{ maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {fileProgress.results.map((r, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '6px 10px', borderRadius: 8, background: r.success ? '#F0FFF4' : '#FFF1F2' }}>
                      <span>{r.success ? '✅' : '❌'}</span>
                      <span style={{ fontWeight: 600, color: '#333' }}>{r.name || '(이름 없음)'}</span>
                      {!r.success && <span style={{ color: '#EF4444', fontSize: 11, marginLeft: 'auto' }}>{r.error}</span>}
                    </div>
                  ))}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '6px 10px', borderRadius: 8, background: '#F5F0FF', color: '#6B4DFF' }}>
                    <Sparkles size={14} />
                    <span>생성 중...</span>
                  </div>
                </div>
              </>
            )}

            {/* 초기 로딩 (progress 이벤트 오기 전) */}
            {isFileCreating && !fileProgress && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '24px 0' }}>
                <PulseRing><Sparkles size={28} color="#6B4DFF" fill="#6B4DFF" /></PulseRing>
                <span style={{ fontSize: 14, color: '#888' }}>파일을 분석하는 중...</span>
              </div>
            )}

            {/* 완료 화면 */}
            {fileProgress?.done && (
              <>
                <div style={{ textAlign: 'center', marginBottom: 20 }}>
                  <div style={{ fontSize: 36, marginBottom: 8 }}>{fileProgress.failed === 0 ? '🎉' : '⚠️'}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#333' }}>생성 완료</div>
                </div>
                <div style={{ display: 'flex', gap: 12, marginBottom: fileProgress.failed > 0 ? 16 : 24 }}>
                  <div style={{ flex: 1, padding: '14px', borderRadius: 12, background: '#F0FFF4', textAlign: 'center' }}>
                    <div style={{ fontSize: 26, fontWeight: 800, color: '#22C55E' }}>{fileProgress.succeeded}</div>
                    <div style={{ fontSize: 12, color: '#16A34A', marginTop: 2 }}>성공</div>
                  </div>
                  <div style={{ flex: 1, padding: '14px', borderRadius: 12, background: fileProgress.failed > 0 ? '#FFF1F2' : '#f5f5f5', textAlign: 'center' }}>
                    <div style={{ fontSize: 26, fontWeight: 800, color: fileProgress.failed > 0 ? '#EF4444' : '#bbb' }}>{fileProgress.failed}</div>
                    <div style={{ fontSize: 12, color: fileProgress.failed > 0 ? '#DC2626' : '#bbb', marginTop: 2 }}>실패</div>
                  </div>
                </div>
                {fileProgress.failed > 0 && (
                  <div style={{ background: '#FFF1F2', borderRadius: 10, padding: '10px 14px', marginBottom: 16, maxHeight: 100, overflowY: 'auto' }}>
                    {fileProgress.results.filter(r => !r.success).map((r, i) => (
                      <div key={i} style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>· {r.name || `${i + 1}번`}: {r.error}</div>
                    ))}
                  </div>
                )}
                <button onClick={() => { setShowFileModal(false); setUploadFile(null); setFileProgress(null); }} style={{ width: '100%', padding: 14, borderRadius: 12, border: 'none', background: '#6B4DFF', color: 'white', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}>닫기</button>
              </>
            )}
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}
