import axios from 'axios';

// 백엔드 주소 설정 (JSX 프로젝트용)
const api = axios.create({
  baseURL: 'http://localhost:8010/api', 
  headers: {
    'Content-Type': 'application/json',
  },
});

export default api;