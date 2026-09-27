import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 120000,  // 2 min — LLM inference can be slow on free tier
})

export default api
