import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import styled from 'styled-components';
import { FileText, Search, RotateCcw, ChevronLeft, ChevronRight, X, Trash2, Copy, Check } from 'lucide-react';
import { dbApi } from '../api';

const USER_ID = 'son';
const LIMIT = 20;

// ============================================================
// Styled Components
// ============================================================

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
  gap: 10px;
  margin-bottom: 20px;

  h1 {
    font-size: 22px;
    font-weight: 800;
    color: #1A1A1A;
    margin: 0;
  }

  svg {
    color: #6B4DFF;
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

const FilterCard = styled.div`
  background: #fff;
  border: 1px solid #E0E0E0;
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
`;

const FilterGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;

  label {
    font-size: 11px;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }
`;

const FilterInput = styled.input`
  height: 34px;
  padding: 0 10px;
  border: 1px solid #D8D8D8;
  border-radius: 8px;
  font-size: 13px;
  color: #333;
  background: #FAFAFA;
  outline: none;
  cursor: pointer;

  &:focus {
    border-color: #6B4DFF;
    background: #fff;
  }
`;

const FilterSelect = styled.select`
  height: 34px;
  padding: 0 10px;
  border: 1px solid #D8D8D8;
  border-radius: 8px;
  font-size: 13px;
  color: #333;
  background: #FAFAFA;
  outline: none;
  cursor: pointer;
  min-width: 130px;

  &:focus {
    border-color: #6B4DFF;
    background: #fff;
  }
`;

const DateRangeGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;

  label {
    font-size: 11px;
    font-weight: 700;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.4px;
  }

  .date-inputs {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #aaa;
  }
`;

const ButtonGroup = styled.div`
  display: flex;
  gap: 8px;
  margin-left: auto;
  align-self: flex-end;
`;

const SearchButton = styled.button`
  height: 34px;
  padding: 0 16px;
  background: #6B4DFF;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.15s;

  &:hover { background: #5a3ee0; }
  svg { width: 14px; height: 14px; }
`;

const ResetButton = styled.button`
  height: 34px;
  padding: 0 14px;
  background: #fff;
  color: #666;
  border: 1px solid #D0D0D0;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s;

  &:hover { background: #F5F5F5; color: #333; }
  svg { width: 14px; height: 14px; }
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
  min-width: 900px;
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

const Tr = styled.tr`
  border-bottom: 1px solid #F0F0F0;
  cursor: pointer;
  transition: background 0.1s;

  &:last-child { border-bottom: none; }
  &:hover { background: #F7F7FA; }
`;

const Td = styled.td`
  padding: 11px 14px;
  font-size: 13px;
  color: #333;
  vertical-align: middle;
`;

const TruncatedTd = styled(Td)`
  max-width: 200px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px;
`;

const QualityBadge = styled.span`
  display: inline-block;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
  background: ${props =>
    props.$score >= 4 ? '#E6F9F0' :
    props.$score >= 3 ? '#FFF3E0' : '#FFEBEB'};
  color: ${props =>
    props.$score >= 4 ? '#1A9E5A' :
    props.$score >= 3 ? '#E07A00' : '#D93025'};
`;

const EmptyRow = styled.tr`
  td {
    padding: 48px;
    text-align: center;
    color: #BBB;
    font-size: 14px;
  }
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

const CheckTh = styled(Th)`
  width: 40px;
  padding: 10px 0 10px 14px;
`;

const CheckTd = styled(Td)`
  width: 40px;
  padding: 11px 0 11px 14px;
`;

const Checkbox = styled.input.attrs({ type: 'checkbox' })`
  width: 15px;
  height: 15px;
  cursor: pointer;
  accent-color: #6B4DFF;
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
  width: 32px;
  height: 32px;
  border: 1px solid #D8D8D8;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  transition: all 0.15s;

  &:hover:not(:disabled) { background: #F0EDFF; border-color: #6B4DFF; color: #6B4DFF; }
  &:disabled { opacity: 0.35; cursor: not-allowed; }
  svg { width: 15px; height: 15px; }
`;

const CurrentPage = styled.span`
  font-weight: 700;
  color: #6B4DFF;
  min-width: 20px;
  text-align: center;
`;

// ============================================================
// 모달
// ============================================================

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
  max-width: 680px;
  max-height: 85vh;
  overflow-y: auto;
  padding: 28px 32px;
  position: relative;

  &::-webkit-scrollbar { width: 5px; }
  &::-webkit-scrollbar-thumb { background: #D0D0D0; border-radius: 3px; }
`;

const ModalClose = styled.button`
  position: absolute;
  top: 18px;
  right: 20px;
  background: none;
  border: none;
  cursor: pointer;
  color: #AAA;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;

  &:hover { color: #333; background: #F0F0F0; }
  svg { width: 18px; height: 18px; }
`;

const ModalMeta = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
`;

const MetaChip = styled.span`
  background: #F5F5F5;
  color: #555;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 6px;
`;

const ModalTitle = styled.h2`
  font-size: 18px;
  font-weight: 800;
  color: #1A1A1A;
  margin: 0 0 12px;
  line-height: 1.4;
`;

const ModalContent = styled.p`
  font-size: 14px;
  color: #444;
  line-height: 1.8;
  white-space: pre-wrap;
  margin: 0;
`;

const ModalDivider = styled.hr`
  border: none;
  border-top: 1px solid #F0F0F0;
  margin: 16px 0;
`;

const FeedbackSection = styled.div`
  background: #F7F7FA;
  border: 1px solid #EBEBF0;
  border-radius: 10px;
  padding: 14px 16px;
  margin-top: 20px;
`;

const FeedbackLabel = styled.div`
  font-size: 11px;
  font-weight: 700;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
`;

const FeedbackText = styled.p`
  font-size: 13px;
  color: #666;
  line-height: 1.7;
  white-space: pre-wrap;
  margin: 0;
`;

const CopyButton = styled.button`
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1px solid ${props => props.$copied ? '#1A9E5A' : '#D0D0D0'};
  background: ${props => props.$copied ? '#E6F9F0' : '#fff'};
  color: ${props => props.$copied ? '#1A9E5A' : '#555'};
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;

  &:hover { background: ${props => props.$copied ? '#E6F9F0' : '#F5F5F5'}; }
  svg { width: 13px; height: 13px; }
`;

// ============================================================
// Helper
// ============================================================

function formatDateTime(dt) {
  if (!dt) return '-';
  const d = new Date(dt);
  return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' })
    + ' ' + d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
}

// ============================================================
// Component
// ============================================================

export default function GeneratedMessages() {
  const location = useLocation();

  const [filterOptions, setFilterOptions] = useState({ brands: [], product_tags: [], purposes: [] });
  const [filters, setFilters] = useState({ brand: '', product_tag: '', purpose: '', start_date: '', end_date: '' });
  const [messages, setMessages] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedMsg, setSelectedMsg] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [copied, setCopied] = useState(false);

  // 조회 버튼 클릭 시 확정된 필터 — ref로 관리해 closure 문제 방지
  const committedRef = useRef({});

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));

  // 실제 fetch 함수 — 직접 파라미터를 받아 호출
  const doFetch = useCallback(async (filterParams, targetPage) => {
    setLoading(true);
    try {
      const cleanParams = Object.fromEntries(
        Object.entries(filterParams).filter(([, v]) => v)
      );
      const params = {
        user_id: USER_ID,
        limit: LIMIT,
        offset: (targetPage - 1) * LIMIT,
        ...cleanParams,
      };
      const res = await dbApi.get('/generated-messages', { params });
      setMessages(res.data.items || []);
      setTotal(res.data.total || 0);
    } catch (err) {
      console.error('메시지 조회 실패:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // 페이지 진입 시 필터 옵션 + 전체 데이터 초기 로드
  useEffect(() => {
    dbApi.get('/generated-messages/filter-options', { params: { user_id: USER_ID } })
      .then(res => setFilterOptions(res.data))
      .catch(err => console.error('필터 옵션 로드 실패:', err));

    doFetch({}, 1);
  }, [doFetch]);

  // Home에서 넘어온 메시지가 있으면 모달 자동 오픈
  useEffect(() => {
    if (location.state?.openMessage) {
      setSelectedMsg(location.state.openMessage);
    }
  }, [location.state]);

  const handleSearch = () => {
    committedRef.current = { ...filters };
    setPage(1);
    setSelectedIds(new Set());
    doFetch(committedRef.current, 1);
  };

  const handleReset = () => {
    const empty = { brand: '', product_tag: '', purpose: '', start_date: '', end_date: '' };
    setFilters(empty);
    committedRef.current = {};
    setPage(1);
    setSelectedIds(new Set());
    doFetch({}, 1);
  };

  const handlePageChange = (newPage) => {
    setPage(newPage);
    setSelectedIds(new Set());
    doFetch(committedRef.current, newPage);
  };

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  // 체크박스 핸들러
  const allChecked = messages.length > 0 && messages.every(m => selectedIds.has(m.id));
  const someChecked = messages.some(m => selectedIds.has(m.id));

  const handleSelectAll = (e) => {
    if (e.target.checked) {
      setSelectedIds(new Set(messages.map(m => m.id)));
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

  const handleDeleteSelected = async () => {
    if (selectedIds.size === 0) return;
    if (!window.confirm(`선택한 ${selectedIds.size}개의 메시지를 삭제하시겠습니까?`)) return;
    try {
      await dbApi.delete('/generated-messages', { data: { ids: [...selectedIds] } });
      setSelectedIds(new Set());
      doFetch(committedRef.current, page);
    } catch (err) {
      console.error('삭제 실패:', err);
    }
  };

  const handleCopy = () => {
    if (!selectedMsg) return;
    const text = [selectedMsg.title, selectedMsg.content].filter(Boolean).join('\n\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <Container>
      <PageHeader>
        <FileText size={22} />
        <h1>생성 메시지 조회</h1>
        <TotalBadge>총 {total.toLocaleString()}건</TotalBadge>
      </PageHeader>

      {/* 필터 바 */}
      <FilterCard>
        <DateRangeGroup>
          <label>기간</label>
          <div className="date-inputs">
            <FilterInput
              type="date"
              value={filters.start_date}
              onChange={e => handleFilterChange('start_date', e.target.value)}
            />
            ~
            <FilterInput
              type="date"
              value={filters.end_date}
              onChange={e => handleFilterChange('end_date', e.target.value)}
            />
          </div>
        </DateRangeGroup>

        <FilterGroup>
          <label>브랜드</label>
          <FilterSelect value={filters.brand} onChange={e => handleFilterChange('brand', e.target.value)}>
            <option value="">전체</option>
            {filterOptions.brands.map(b => <option key={b} value={b}>{b}</option>)}
          </FilterSelect>
        </FilterGroup>

        <FilterGroup>
          <label>상품 태그</label>
          <FilterSelect value={filters.product_tag} onChange={e => handleFilterChange('product_tag', e.target.value)}>
            <option value="">전체</option>
            {filterOptions.product_tags.map(t => <option key={t} value={t}>{t}</option>)}
          </FilterSelect>
        </FilterGroup>

        <FilterGroup>
          <label>메시지 목적</label>
          <FilterSelect value={filters.purpose} onChange={e => handleFilterChange('purpose', e.target.value)}>
            <option value="">전체</option>
            {filterOptions.purposes.map(p => <option key={p} value={p}>{p}</option>)}
          </FilterSelect>
        </FilterGroup>

        <ButtonGroup>
          <ResetButton onClick={handleReset}>
            <RotateCcw /> 초기화
          </ResetButton>
          <SearchButton onClick={handleSearch}>
            <Search /> 조회
          </SearchButton>
        </ButtonGroup>
      </FilterCard>

      {/* 테이블 */}
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
                <Th>생성일시</Th>
                <Th>상품명</Th>
                <Th>브랜드</Th>
                <Th>카테고리</Th>
                <Th>목적</Th>
                <Th>제목</Th>
                <Th>내용</Th>
                <Th>품질점수</Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <EmptyRow><td colSpan={9}>조회 중...</td></EmptyRow>
              ) : messages.length === 0 ? (
                <EmptyRow><td colSpan={9}>조건에 맞는 메시지가 없습니다.</td></EmptyRow>
              ) : (
                messages.map(msg => (
                  <Tr
                    key={msg.id}
                    onClick={() => setSelectedMsg(msg)}
                    style={selectedIds.has(msg.id) ? { background: '#F5F2FF' } : {}}
                  >
                    <CheckTd>
                      <Checkbox
                        checked={selectedIds.has(msg.id)}
                        onChange={e => handleToggleSelect(e, msg.id)}
                        onClick={e => e.stopPropagation()}
                      />
                    </CheckTd>
                    <Td style={{ whiteSpace: 'nowrap', color: '#888', fontSize: 12 }}>
                      {formatDateTime(msg.created_at)}
                    </Td>
                    <TruncatedTd style={{ maxWidth: 160 }}>{msg.product_name || '-'}</TruncatedTd>
                    <Td>{msg.brand ? <TagBadge>{msg.brand}</TagBadge> : '-'}</Td>
                    <Td>
                      {msg.product_tag
                        ? <TagBadge style={{ background: '#F0F7FF', color: '#2B6CB0' }}>{msg.product_tag}</TagBadge>
                        : '-'}
                    </Td>
                    <Td style={{ fontSize: 12, color: '#666' }}>{msg.purpose || '-'}</Td>
                    <TruncatedTd style={{ maxWidth: 180, fontWeight: 600 }}>{msg.title || '-'}</TruncatedTd>
                    <TruncatedTd style={{ maxWidth: 220, color: '#666' }}>{msg.content}</TruncatedTd>
                    <Td>
                      {msg.llm_score_overall != null
                        ? <QualityBadge $score={msg.llm_score_overall}>{msg.llm_score_overall.toFixed(1)}</QualityBadge>
                        : '-'}
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
            {total > 0 ? `${(page - 1) * LIMIT + 1}–${Math.min(page * LIMIT, total)} / ${total}` : ''}
          </span>
          <PageBtn onClick={() => handlePageChange(page - 1)} disabled={page <= 1}>
            <ChevronLeft />
          </PageBtn>
          <CurrentPage>{page}</CurrentPage>
          <span style={{ color: '#AAA' }}>/ {totalPages}</span>
          <PageBtn onClick={() => handlePageChange(page + 1)} disabled={page >= totalPages}>
            <ChevronRight />
          </PageBtn>
        </Pagination>
      </TableCard>

      {/* 상세 모달 */}
      {selectedMsg && (
        <ModalOverlay onClick={() => { setSelectedMsg(null); setCopied(false); }}>
          <ModalBox onClick={e => e.stopPropagation()}>
            <ModalClose onClick={() => { setSelectedMsg(null); setCopied(false); }}><X /></ModalClose>
            <ModalMeta>
              {selectedMsg.brand && <MetaChip>{selectedMsg.brand}</MetaChip>}
              {selectedMsg.product_tag && <MetaChip>{selectedMsg.product_tag}</MetaChip>}
              {selectedMsg.purpose && <MetaChip>{selectedMsg.purpose}</MetaChip>}
              {selectedMsg.llm_score_overall != null && (
                <QualityBadge $score={selectedMsg.llm_score_overall}>
                  품질 {selectedMsg.llm_score_overall.toFixed(1)}점
                </QualityBadge>
              )}
            </ModalMeta>
            <ModalTitle>{selectedMsg.title || '(제목 없음)'}</ModalTitle>
            <ModalDivider />
            <ModalContent>{selectedMsg.content}</ModalContent>

            {selectedMsg.llm_feedback && (
              <FeedbackSection>
                <FeedbackLabel>AI 평가 코멘트</FeedbackLabel>
                <FeedbackText>{selectedMsg.llm_feedback}</FeedbackText>
              </FeedbackSection>
            )}

            <ModalDivider />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ fontSize: 11, color: '#AAA' }}>
                {selectedMsg.product_name && <span>{selectedMsg.product_name} · </span>}
                {formatDateTime(selectedMsg.created_at)}
              </div>
              <CopyButton $copied={copied} onClick={handleCopy}>
                {copied ? <><Check /> 복사됨</> : <><Copy /> 복사</>}
              </CopyButton>
            </div>
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}
