import axios from 'axios'

// In dev: empty string → Vite proxy → localhost:8000
// In production: point directly at the Render backend
const API_BASE_URL = import.meta.env.DEV
  ? ''
  : (import.meta.env.VITE_API_BASE_URL || 'https://codeatlas-zyys.onrender.com')

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,  // 2 min — LLM inference can be slow on free tier
})

export default api
