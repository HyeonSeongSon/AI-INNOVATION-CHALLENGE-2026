import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import styled from 'styled-components';
import { Package, Search, RotateCcw, ChevronLeft, ChevronRight, X, ExternalLink, Star, Upload, Sparkles } from 'lucide-react';
import { dbApi } from '../api';
import { useToast } from '../components/Toast';
import brandsData from '../../data/brands.json';
import categoryData from '../../data/category.json';

const PAGE_SIZE = 20;

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
  justify-content: space-between;
  margin-bottom: 20px;

  .left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  h1 {
    font-size: 22px;
    font-weight: 800;
    color: #1A1A1A;
    margin: 0;
  }

  svg { color: #6B4DFF; }
`;

const RegisterButton = styled.button`
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
  min-width: 120px;

  &:focus {
    border-color: #6B4DFF;
    background: #fff;
  }
`;

const PriceRangeGroup = styled.div`
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

  .range-inputs {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #aaa;
  }

  input { width: 90px; }
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
  min-width: 860px;
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

const DiscountBadge = styled.span`
  display: inline-block;
  background: #FFF0F0;
  color: #D93025;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
`;

const RatingBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 600;
  color: #E07A00;

  svg { width: 12px; height: 12px; fill: #E07A00; color: #E07A00; }
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
  height: 32px;
  padding: 0 12px;
  gap: 4px;
  border: 1px solid #D8D8D8;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
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
  max-width: 720px;
  max-height: 88vh;
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

const ModalTopRow = styled.div`
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
`;

const ProductImage = styled.img`
  width: 110px;
  height: 110px;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid #EBEBF0;
  flex-shrink: 0;
  background: #F5F5F5;
`;

const ProductImagePlaceholder = styled.div`
  width: 110px;
  height: 110px;
  border-radius: 10px;
  border: 1px solid #EBEBF0;
  background: #F5F5F5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #CCC;
  flex-shrink: 0;
  svg { width: 32px; height: 32px; }
`;

const ModalInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

const ModalProductName = styled.h2`
  font-size: 18px;
  font-weight: 800;
  color: #1A1A1A;
  margin: 0 36px 8px 0;
  line-height: 1.4;
`;

const ModalMetaRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
`;

const MetaChip = styled.span`
  background: #F5F5F5;
  color: #555;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 6px;
`;

const ModalPriceRow = styled.div`
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 6px;
`;

const SalePrice = styled.span`
  font-size: 20px;
  font-weight: 800;
  color: #1A1A1A;
`;

const OriginalPrice = styled.span`
  font-size: 13px;
  color: #BBB;
  text-decoration: line-through;
`;

const ModalDivider = styled.hr`
  border: none;
  border-top: 1px solid #F0F0F0;
  margin: 16px 0;
`;

const SectionLabel = styled.div`
  font-size: 11px;
  font-weight: 700;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
`;

const TagList = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
`;

const AttrTag = styled.span`
  background: ${props => props.$color || '#F0EDFF'};
  color: ${props => props.$textColor || '#6B4DFF'};
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 20px;
`;

const CommentBox = styled.div`
  background: #F7F7FA;
  border: 1px solid #EBEBF0;
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 13px;
  color: #555;
  line-height: 1.7;
  font-style: italic;
`;

const DetailGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 16px;
`;

const DetailItem = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;

  .key {
    font-size: 11px;
    color: #999;
    font-weight: 600;
    text-transform: capitalize;
  }
  .value {
    font-size: 13px;
    color: #333;
    word-break: break-all;
  }
`;

const ExternalLinkBtn = styled.a`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: #6B4DFF;
  color: #fff;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: background 0.15s;

  &:hover { background: #5a3ee0; }
  svg { width: 14px; height: 14px; }
`;

const IdText = styled.span`
  font-size: 11px;
  color: #AAA;
  font-family: monospace;
`;

// ============================================================
// Helper
// ============================================================

function formatPrice(v) {
  if (v == null) return '-';
  return v.toLocaleString('ko-KR') + '원';
}

function renderTagList(arr, color, textColor) {
  if (!arr || arr.length === 0) return <span style={{ color: '#CCC', fontSize: 12 }}>-</span>;
  return (
    <TagList>
      {arr.map((item, i) => (
        <AttrTag key={i} $color={color} $textColor={textColor}>{item}</AttrTag>
      ))}
    </TagList>
  );
}

// ============================================================
// 상품 상세 모달
// ============================================================

function ProductModal({ product, onClose }) {
  const imgUrl = product.product_image_url?.[0];

  return (
    <ModalOverlay onClick={onClose}>
      <ModalBox onClick={e => e.stopPropagation()}>
        <ModalClose onClick={onClose}><X /></ModalClose>

        <ModalTopRow>
          {imgUrl
            ? <ProductImage src={imgUrl} alt={product.product_name} />
            : <ProductImagePlaceholder><Package /></ProductImagePlaceholder>
          }
          <ModalInfo>
            <ModalProductName>{product.product_name}</ModalProductName>
            <ModalMetaRow>
              {product.brand && <MetaChip>{product.brand}</MetaChip>}
              {product.category && <MetaChip>{product.category}</MetaChip>}
              {product.tag && <MetaChip>{product.tag}</MetaChip>}
              {product.sub_tag && (
                <MetaChip style={{ background: '#F0EDFF', color: '#6B4DFF' }}>{product.sub_tag}</MetaChip>
              )}
              {product.exclusive_product && (
                <MetaChip style={{ background: '#FFF3E0', color: '#E07A00' }}>{product.exclusive_product} 전용</MetaChip>
              )}
            </ModalMetaRow>
            {(product.rating != null || product.review_count != null) && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                {product.rating != null && (
                  <RatingBadge>
                    <Star /> {Number(product.rating).toFixed(1)}
                  </RatingBadge>
                )}
                {product.review_count != null && (
                  <span style={{ fontSize: 12, color: '#AAA' }}>({product.review_count.toLocaleString()}개 리뷰)</span>
                )}
              </div>
            )}
            <ModalPriceRow>
              {product.sale_price != null && <SalePrice>{formatPrice(product.sale_price)}</SalePrice>}
              {product.original_price != null && product.original_price !== product.sale_price && (
                <OriginalPrice>{formatPrice(product.original_price)}</OriginalPrice>
              )}
              {product.discount_rate != null && product.discount_rate > 0 && (
                <DiscountBadge>{product.discount_rate}% 할인</DiscountBadge>
              )}
            </ModalPriceRow>
            <IdText style={{ display: 'block', marginTop: 8 }}>ID: {product.product_id}</IdText>
          </ModalInfo>
        </ModalTopRow>

        {product.product_comment && (
          <>
            <SectionLabel>한줄평</SectionLabel>
            <CommentBox>"{product.product_comment}"</CommentBox>
            <ModalDivider />
          </>
        )}

        {/* 타겟 속성 */}
        {[
          { label: '피부 타입', arr: product.skin_type, color: '#E8F4FD', textColor: '#2B6CB0' },
          { label: '피부 고민', arr: product.concerns, color: '#FFF0F6', textColor: '#C2185B' },
          { label: '퍼스널 컬러', arr: product.personal_color, color: '#F3E5F5', textColor: '#7B1FA2' },
          { label: '선호 성분', arr: product.preferred_ingredients, color: '#E8F5E9', textColor: '#2E7D32' },
          { label: '기피 성분', arr: product.avoided_ingredients, color: '#FFEBEE', textColor: '#C62828' },
          { label: '선호 색상', arr: product.preferred_colors, color: '#FFF8E1', textColor: '#F57F17' },
          { label: '선호 향', arr: product.preferred_scents, color: '#F3E5F5', textColor: '#6A1B9A' },
          { label: '라이프스타일', arr: product.lifestyle_values, color: '#E0F2F1', textColor: '#00695C' },
        ].filter(({ arr }) => arr && arr.length > 0).map(({ label, arr, color, textColor }) => (
          <div key={label} style={{ marginBottom: 14 }}>
            <SectionLabel>{label}</SectionLabel>
            {renderTagList(arr, color, textColor)}
          </div>
        ))}

        {product.skin_shades && product.skin_shades.length > 0 && (
          <div style={{ marginBottom: 14 }}>
            <SectionLabel>피부톤 번호</SectionLabel>
            <TagList>
              {product.skin_shades.map((n, i) => (
                <AttrTag key={i} $color="#F5F5F5" $textColor="#555">{n}호</AttrTag>
              ))}
            </TagList>
          </div>
        )}

        {/* product_details JSONB */}
        {product.product_details && Object.keys(product.product_details).length > 0 && (
          <>
            <ModalDivider />
            <SectionLabel>상품 상세 정보</SectionLabel>
            <DetailGrid>
              {Object.entries(product.product_details).map(([k, v]) => (
                <DetailItem key={k}>
                  <span className="key">{k}</span>
                  <span className="value">{Array.isArray(v) ? v.join(', ') : String(v)}</span>
                </DetailItem>
              ))}
            </DetailGrid>
          </>
        )}

        {product.product_page_url && (
          <>
            <ModalDivider />
            <ExternalLinkBtn href={product.product_page_url} target="_blank" rel="noopener noreferrer">
              <ExternalLink /> 상품 페이지 바로가기
            </ExternalLinkBtn>
          </>
        )}
      </ModalBox>
    </ModalOverlay>
  );
}

// ============================================================
// 메인 컴포넌트
// ============================================================

const ALL_BRANDS = brandsData.brands;
const ALL_CATEGORIES = Object.keys(categoryData.categories);
const ALL_SUB_TAGS = categoryData.sub_tags;

function getSubTagsForCategory(category) {
  if (!category) return ALL_SUB_TAGS;
  const subs = categoryData.categories[category];
  if (!subs) return ALL_SUB_TAGS;
  return Object.values(subs).flat();
}

const EMPTY_FILTERS = { search: '', brand: '', category: '', sub_tag: '', min_price: '', max_price: '', min_discount: '' };

export default function Products() {
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);

  // 상품 등록 모달 상태
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [isRegistering, setIsRegistering] = useState(false);
  // registerProgress: null | { total, current, done, succeeded, failed, results: [{name, success, product_id?, error?}] }
  const [registerProgress, setRegisterProgress] = useState(null);

  const { addToast } = useToast();

  const committedRef = useRef({});

  const availableSubTags = useMemo(() => getSubTagsForCategory(filters.category), [filters.category]);

  const doFetch = useCallback(async (filterParams, targetPage) => {
    setLoading(true);
    try {
      const cleanParams = Object.fromEntries(
        Object.entries(filterParams).filter(([, v]) => v !== '' && v != null)
      );
      const res = await dbApi.get('/products', {
        params: { ...cleanParams, page: targetPage, page_size: PAGE_SIZE },
      });
      setProducts(res.data.items || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 1);
    } catch (err) {
      console.error('상품 조회 실패:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    doFetch({}, 1);
  }, [doFetch]);

  const handleSearch = () => {
    committedRef.current = { ...filters };
    setPage(1);
    doFetch(committedRef.current, 1);
  };

  const handleReset = () => {
    setFilters(EMPTY_FILTERS);
    committedRef.current = {};
    setPage(1);
    doFetch({}, 1);
  };

  const handlePageChange = (newPage) => {
    setPage(newPage);
    doFetch(committedRef.current, newPage);
  };

  const handleFilterChange = (key, value) => {
    if (key === 'category') {
      setFilters(prev => ({ ...prev, category: value, sub_tag: '' }));
    } else {
      setFilters(prev => ({ ...prev, [key]: value }));
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch();
  };

  const handleRegisterFromFile = async () => {
    if (!uploadFile) return addToast('파일을 선택해주세요.', 'error');
    setIsRegistering(true);
    setRegisterProgress(null);

    const formData = new FormData();
    formData.append('file', uploadFile);

    try {
      const response = await fetch('http://localhost:8005/api/pipeline/products/register', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        addToast(`등록 실패: ${err.detail || response.statusText}`, 'error');
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
            addToast(`등록 실패: ${event.detail}`, 'error');
            return;
          }

          if (event.type === 'progress') {
            setRegisterProgress(prev => ({
              total: event.total,
              current: event.current,
              done: false,
              succeeded: (prev?.succeeded ?? 0) + (event.success ? 1 : 0),
              failed: (prev?.failed ?? 0) + (event.success ? 0 : 1),
              results: [...(prev?.results ?? []), {
                name: event.name,
                success: event.success,
                product_id: event.product_id,
                error: event.error,
              }],
            }));
          }

          if (event.type === 'done') {
            setRegisterProgress(prev => ({ ...prev, done: true, succeeded: event.succeeded, failed: event.failed }));
            doFetch(committedRef.current, page);
          }
        }
      }
    } catch (error) {
      addToast(`등록 실패: ${error.message}`, 'error');
    } finally {
      setIsRegistering(false);
    }
  };

  return (
    <Container>
      <PageHeader>
        <div className="left">
          <Package size={22} />
          <h1>상품 목록</h1>
          <TotalBadge>총 {total.toLocaleString()}개</TotalBadge>
        </div>
        <RegisterButton onClick={() => { setShowRegisterModal(true); setUploadFile(null); setRegisterProgress(null); }}>
          <Upload size={15} /> 상품 등록
        </RegisterButton>
      </PageHeader>

      {/* 필터 바 */}
      <FilterCard>
        <FilterGroup style={{ minWidth: 200 }}>
          <label>검색 (상품명 / ID)</label>
          <FilterInput
            placeholder="상품명 또는 ID 입력"
            value={filters.search}
            onChange={e => handleFilterChange('search', e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </FilterGroup>

        <FilterGroup>
          <label>브랜드</label>
          <FilterSelect
            value={filters.brand}
            onChange={e => handleFilterChange('brand', e.target.value)}
          >
            <option value="">전체</option>
            {ALL_BRANDS.map(b => <option key={b} value={b}>{b}</option>)}
          </FilterSelect>
        </FilterGroup>

        <FilterGroup>
          <label>카테고리</label>
          <FilterSelect
            value={filters.category}
            onChange={e => handleFilterChange('category', e.target.value)}
          >
            <option value="">전체</option>
            {ALL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </FilterSelect>
        </FilterGroup>

        <FilterGroup style={{ width: 160, minWidth: 160, maxWidth: 160 }}>
          <label>서브태그</label>
          <FilterSelect
            value={filters.sub_tag}
            onChange={e => handleFilterChange('sub_tag', e.target.value)}
            style={{ width: '100%' }}
          >
            <option value="">전체</option>
            {availableSubTags.map(t => <option key={t} value={t}>{t}</option>)}
          </FilterSelect>
        </FilterGroup>

        <PriceRangeGroup>
          <label>판매가 (원)</label>
          <div className="range-inputs">
            <FilterInput
              placeholder="최소"
              type="number"
              value={filters.min_price}
              onChange={e => handleFilterChange('min_price', e.target.value)}
              onKeyDown={handleKeyDown}
            />
            ~
            <FilterInput
              placeholder="최대"
              type="number"
              value={filters.max_price}
              onChange={e => handleFilterChange('max_price', e.target.value)}
              onKeyDown={handleKeyDown}
            />
          </div>
        </PriceRangeGroup>

        <FilterGroup style={{ minWidth: 90 }}>
          <label>최소 할인율 (%)</label>
          <FilterInput
            placeholder="예: 10"
            type="number"
            min="0"
            max="100"
            value={filters.min_discount}
            onChange={e => {
              const v = e.target.value;
              if (v === '' || (Number(v) >= 0 && Number(v) <= 100)) {
                handleFilterChange('min_discount', v);
              }
            }}
            onKeyDown={handleKeyDown}
          />
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
        <TableWrapper>
          <Table>
            <thead>
              <tr>
                <Th>상품 ID</Th>
                <Th>상품명</Th>
                <Th>브랜드</Th>
                <Th>서브태그</Th>
                <Th>판매가</Th>
                <Th>할인율</Th>
                <Th>평점</Th>
                <Th>리뷰 수</Th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <EmptyRow><td colSpan={8}>조회 중...</td></EmptyRow>
              ) : products.length === 0 ? (
                <EmptyRow><td colSpan={8}>조건에 맞는 상품이 없습니다.</td></EmptyRow>
              ) : (
                products.map(p => (
                  <Tr key={p.product_id} onDoubleClick={() => setSelectedProduct(p)}>
                    <Td><IdText>{p.product_id}</IdText></Td>
                    <TruncatedTd style={{ maxWidth: 220, fontWeight: 600 }}>{p.product_name}</TruncatedTd>
                    <Td>{p.brand ? <TagBadge>{p.brand}</TagBadge> : '-'}</Td>
                    <Td>
                      {p.sub_tag
                        ? <TagBadge style={{ background: '#F0F7FF', color: '#2B6CB0' }}>{p.sub_tag}</TagBadge>
                        : '-'}
                    </Td>
                    <Td style={{ fontWeight: 600 }}>
                      {p.sale_price != null ? (
                        <span>
                          {p.sale_price.toLocaleString()}원
                          {p.original_price != null && p.original_price !== p.sale_price && (
                            <span style={{ fontSize: 11, color: '#BBB', textDecoration: 'line-through', marginLeft: 5 }}>
                              {p.original_price.toLocaleString()}
                            </span>
                          )}
                        </span>
                      ) : '-'}
                    </Td>
                    <Td>
                      {p.discount_rate != null && p.discount_rate > 0
                        ? <DiscountBadge>{p.discount_rate}%</DiscountBadge>
                        : '-'}
                    </Td>
                    <Td>
                      {p.rating != null
                        ? <RatingBadge><Star />{Number(p.rating).toFixed(1)}</RatingBadge>
                        : '-'}
                    </Td>
                    <Td style={{ color: '#666' }}>
                      {p.review_count != null ? p.review_count.toLocaleString() : '-'}
                    </Td>
                  </Tr>
                ))
              )}
            </tbody>
          </Table>
        </TableWrapper>

        <Pagination>
          <span style={{ color: '#AAA', fontSize: 12 }}>
            {total > 0
              ? `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} / ${total}`
              : ''}
          </span>
          <PageBtn onClick={() => handlePageChange(page - 1)} disabled={page <= 1}>
            <ChevronLeft /> 이전
          </PageBtn>
          <CurrentPage>{page}</CurrentPage>
          <span style={{ color: '#AAA' }}>/ {totalPages}</span>
          <PageBtn onClick={() => handlePageChange(page + 1)} disabled={page >= totalPages}>
            다음 <ChevronRight />
          </PageBtn>
        </Pagination>
      </TableCard>

      {selectedProduct && (
        <ProductModal product={selectedProduct} onClose={() => setSelectedProduct(null)} />
      )}

      {/* 상품 등록 모달 */}
      {showRegisterModal && (
        <ModalOverlay onClick={() => { if (!isRegistering) { setShowRegisterModal(false); setUploadFile(null); setRegisterProgress(null); } }}>
          <ModalBox onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h2 style={{ fontSize: 20, fontWeight: 'bold', color: '#333', margin: 0 }}>상품 등록</h2>
              <button
                onClick={() => { if (!isRegistering) { setShowRegisterModal(false); setUploadFile(null); setRegisterProgress(null); } }}
                style={{ background: 'none', border: 'none', cursor: isRegistering ? 'not-allowed' : 'pointer', color: '#aaa', padding: 4, display: 'flex', alignItems: 'center' }}
              >
                <X size={22} />
              </button>
            </div>

            {/* 파일 선택 화면 */}
            {!registerProgress && !isRegistering && (
              <>
                <p style={{ fontSize: 14, color: '#666', marginBottom: 16, lineHeight: 1.6 }}>
                  JSONL, CSV, XLSX 파일을 업로드하면 Vision AI가 이미지를 분석하여 상품을 자동 등록합니다.
                </p>
                <p style={{ fontSize: 12, color: '#999', marginBottom: 16, lineHeight: 1.7 }}>
                  필수 컬럼: <code style={{ background: '#F5F5F5', padding: '1px 6px', borderRadius: 4 }}>상품명</code>,{' '}
                  <code style={{ background: '#F5F5F5', padding: '1px 6px', borderRadius: 4 }}>상품상세_이미지</code>,{' '}
                  <code style={{ background: '#F5F5F5', padding: '1px 6px', borderRadius: 4 }}>브랜드</code>
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
                  <span style={{ fontSize: 12, color: '#bbb' }}>지원 형식: .jsonl, .csv, .xlsx</span>
                  <input
                    type="file"
                    accept=".jsonl,.csv,.xlsx"
                    style={{ display: 'none' }}
                    onChange={e => setUploadFile(e.target.files[0] || null)}
                  />
                </label>
                <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
                  <button
                    onClick={() => { setShowRegisterModal(false); setUploadFile(null); }}
                    style={{ flex: 1, padding: 14, borderRadius: 12, border: 'none', background: '#f0f0f0', color: '#555', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}
                  >
                    취소
                  </button>
                  <button
                    onClick={handleRegisterFromFile}
                    disabled={!uploadFile}
                    style={{ flex: 1, padding: 14, borderRadius: 12, border: 'none', background: '#6B4DFF', color: 'white', fontWeight: 700, fontSize: 15, cursor: uploadFile ? 'pointer' : 'not-allowed', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, opacity: uploadFile ? 1 : 0.5 }}
                  >
                    <Upload size={16} /> 등록 시작
                  </button>
                </div>
              </>
            )}

            {/* 초기 로딩 (첫 progress 이벤트 오기 전) */}
            {isRegistering && !registerProgress && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '24px 0' }}>
                <PulseRing><Sparkles size={28} color="#6B4DFF" fill="#6B4DFF" /></PulseRing>
                <span style={{ fontSize: 14, color: '#888' }}>파일을 분석하는 중...</span>
              </div>
            )}

            {/* 진행 중 화면 */}
            {isRegistering && registerProgress && !registerProgress.done && (
              <>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#666', marginBottom: 8 }}>
                    <span style={{ fontWeight: 700, color: '#333' }}>{registerProgress.current} / {registerProgress.total} 등록 중...</span>
                    <span>{Math.round((registerProgress.current / registerProgress.total) * 100)}%</span>
                  </div>
                  <div style={{ height: 8, background: '#eee', borderRadius: 99, overflow: 'hidden' }}>
                    <div style={{ height: '100%', background: '#6B4DFF', borderRadius: 99, width: `${(registerProgress.current / registerProgress.total) * 100}%`, transition: 'width 0.3s' }} />
                  </div>
                </div>
                <div style={{ maxHeight: 240, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {registerProgress.results.map((r, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '6px 10px', borderRadius: 8, background: r.success ? '#F0FFF4' : '#FFF1F2' }}>
                      <span>{r.success ? '✅' : '❌'}</span>
                      <span style={{ fontWeight: 600, color: '#333' }}>{r.name || '(이름 없음)'}</span>
                      {r.success && r.product_id && (
                        <span style={{ fontSize: 11, color: '#888', marginLeft: 'auto', fontFamily: 'monospace' }}>{r.product_id}</span>
                      )}
                      {!r.success && <span style={{ color: '#EF4444', fontSize: 11, marginLeft: 'auto' }}>{r.error}</span>}
                    </div>
                  ))}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '6px 10px', borderRadius: 8, background: '#F5F0FF', color: '#6B4DFF' }}>
                    <Sparkles size={14} />
                    <span>Vision AI 분석 중...</span>
                  </div>
                </div>
              </>
            )}

            {/* 완료 화면 */}
            {registerProgress?.done && (
              <>
                <div style={{ textAlign: 'center', marginBottom: 20 }}>
                  <div style={{ fontSize: 36, marginBottom: 8 }}>{registerProgress.failed === 0 ? '🎉' : '⚠️'}</div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: '#333' }}>등록 완료</div>
                </div>
                <div style={{ display: 'flex', gap: 12, marginBottom: registerProgress.failed > 0 ? 16 : 24 }}>
                  <div style={{ flex: 1, padding: '14px', borderRadius: 12, background: '#F0FFF4', textAlign: 'center' }}>
                    <div style={{ fontSize: 26, fontWeight: 800, color: '#22C55E' }}>{registerProgress.succeeded}</div>
                    <div style={{ fontSize: 12, color: '#16A34A', marginTop: 2 }}>성공</div>
                  </div>
                  <div style={{ flex: 1, padding: '14px', borderRadius: 12, background: registerProgress.failed > 0 ? '#FFF1F2' : '#f5f5f5', textAlign: 'center' }}>
                    <div style={{ fontSize: 26, fontWeight: 800, color: registerProgress.failed > 0 ? '#EF4444' : '#bbb' }}>{registerProgress.failed}</div>
                    <div style={{ fontSize: 12, color: registerProgress.failed > 0 ? '#DC2626' : '#bbb', marginTop: 2 }}>실패</div>
                  </div>
                </div>
                {registerProgress.failed > 0 && (
                  <div style={{ background: '#FFF1F2', borderRadius: 10, padding: '10px 14px', marginBottom: 16, maxHeight: 100, overflowY: 'auto' }}>
                    {registerProgress.results.filter(r => !r.success).map((r, i) => (
                      <div key={i} style={{ fontSize: 12, color: '#666', marginBottom: 2 }}>· {r.name || `${i + 1}번`}: {r.error}</div>
                    ))}
                  </div>
                )}
                <button
                  onClick={() => { setShowRegisterModal(false); setUploadFile(null); setRegisterProgress(null); }}
                  style={{ width: '100%', padding: 14, borderRadius: 12, border: 'none', background: '#6B4DFF', color: 'white', fontWeight: 700, fontSize: 15, cursor: 'pointer' }}
                >
                  닫기
                </button>
              </>
            )}
          </ModalBox>
        </ModalOverlay>
      )}
    </Container>
  );
}
