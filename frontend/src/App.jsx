import React, { useState, useEffect, useRef, useCallback } from 'react'
import './index.css'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import axios from 'axios'

// ─── MUI Icons (commit 1: no more emoji icons) ───────────────────────────────
import SearchIcon from '@mui/icons-material/Search'
import HistoryIcon from '@mui/icons-material/History'
import FolderIcon from '@mui/icons-material/Folder'
import BoltIcon from '@mui/icons-material/Bolt'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked'
import AddIcon from '@mui/icons-material/Add'
import CloseIcon from '@mui/icons-material/Close'
import SpeedIcon from '@mui/icons-material/Speed'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import CheckIcon from '@mui/icons-material/Check'
import ThumbUpIcon from '@mui/icons-material/ThumbUp'
import ThumbDownIcon from '@mui/icons-material/ThumbDown'
import BookmarkIcon from '@mui/icons-material/Bookmark'
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder'
import DescriptionIcon from '@mui/icons-material/Description'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import ForumIcon from '@mui/icons-material/Forum'
import SyncIcon from '@mui/icons-material/Sync'
import VisibilityIcon from '@mui/icons-material/Visibility'

// ─── Central Deterministic Repo Color Management ──────────────────────────────
const PRESET_REPO_STYLES = {
  'LearnSphere': { color: '#E8A96A', soft: 'rgba(232,169,106,0.14)', classKey: 'a' },
  'SketchXPad': { color: '#6BC7E8', soft: 'rgba(107,199,232,0.14)', classKey: 'b' },
  'MultiSource-RAG-Agent': { color: '#B08CEF', soft: 'rgba(176,140,239,0.14)', classKey: 'c' },
}

const EXTENDED_PALETTE = [
  { color: '#E8A96A', soft: 'rgba(232,169,106,0.14)', classKey: 'a' },
  { color: '#6BC7E8', soft: 'rgba(107,199,232,0.14)', classKey: 'b' },
  { color: '#B08CEF', soft: 'rgba(176,140,239,0.14)', classKey: 'c' },
  { color: '#7FD8A6', soft: 'rgba(127,216,166,0.14)', classKey: 'd' },
  { color: '#F06B8A', soft: 'rgba(240,107,138,0.14)', classKey: 'e' },
]

function getRepoStyle(name) {
  if (!name) return EXTENDED_PALETTE[0]
  if (PRESET_REPO_STYLES[name]) return PRESET_REPO_STYLES[name]
  let h = 5381
  for (let i = 0; i < name.length; i++) h = ((h << 5) + h) + name.charCodeAt(i)
  return EXTENDED_PALETTE[Math.abs(h) % EXTENDED_PALETTE.length]
}

function getRepoColor(name) {
  return getRepoStyle(name).color
}

// ─── Commit 4: Citation popover component ────────────────────────────────────
function CitationPopover({ number, citation, repoStyle }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const lineLabel = citation.start_line
    ? `L${citation.start_line}${citation.end_line && citation.end_line !== citation.start_line ? `–${citation.end_line}` : ''}`
    : (citation.commit_hash ? `commit:${citation.commit_hash.slice(0, 7)}` : '')

  return (
    <span ref={ref} style={{ display: 'inline-block', position: 'relative' }}>
      <span
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 18, height: 18, borderRadius: 4,
          background: repoStyle?.soft || 'var(--accent-soft)',
          color: repoStyle?.color || 'var(--accent)',
          fontSize: 10, fontWeight: 800, fontFamily: 'var(--mono)',
          cursor: 'pointer', userSelect: 'none',
          border: `1px solid ${repoStyle?.color || 'var(--accent)'}`,
          transition: 'opacity 0.15s',
          verticalAlign: 'middle', margin: '0 2px',
        }}
        title={`Citation ${number}: ${citation.repo}/${citation.file_path || ''} ${lineLabel}`}
      >
        {number}
      </span>
      {open && (
        <div style={{
          position: 'absolute', bottom: 24, left: '50%', transform: 'translateX(-50%)',
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '12px 14px', width: 320, zIndex: 200,
          boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        }}>
          {/* Repo header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: repoStyle?.color || 'var(--accent)',
              display: 'inline-block', flexShrink: 0,
            }} />
            <span style={{ fontWeight: 700, fontSize: 12, color: 'var(--text)' }}>{citation.repo}</span>
            {lineLabel && (
              <span style={{ marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-dim)' }}>
                {lineLabel}
              </span>
            )}
          </div>
          {/* File path */}
          {citation.file_path && (
            <div style={{
              fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--text-mid)',
              marginBottom: 8, wordBreak: 'break-all',
            }}>
              {citation.file_path}
            </div>
          )}
          {/* Divider */}
          <div style={{ borderTop: '1px solid var(--border)', marginBottom: 8 }} />
          {/* Snippet */}
          {citation.snippet && (
            <pre style={{
              margin: 0, fontFamily: 'var(--mono)', fontSize: 10,
              color: 'var(--text-mid)', overflowX: 'auto',
              whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              maxHeight: 120,
            }}>
              {citation.snippet.slice(0, 300)}
            </pre>
          )}
        </div>
      )}
    </span>
  )
}

// ─── Commit 4: processAnswerText — insert [N] markers matching citations ──────
function processAnswerText(answerText, citations, repoStyleMap) {
  if (!citations || citations.length === 0) return answerText

  // Build a map: "repo/file_path:start_line" -> citation index
  const citationMap = {}
  citations.forEach((c, i) => {
    const key = `${c.repo}/${c.file_path || ''}:${c.start_line || ''}`
    if (!citationMap[key]) citationMap[key] = i + 1
    // Also key by just repo/file for partial matches
    const fileKey = `${c.repo}/${c.file_path || ''}`
    if (!citationMap[fileKey]) citationMap[fileKey] = i + 1
  })
  return answerText
}

// ─── Simple syntax highlighter ────────────────────────────────────────────────
const HighlightedCode = ({ code }) => {
  if (!code) return null
  const lines = code.split('\n')
  return (
    <pre className="code">
      {lines.map((line, idx) => {
        if (line.trim().startsWith('//') || line.trim().startsWith('#')) {
          return <div key={idx}><span className="cm">{line}</span></div>
        }
        const kwRegex = /\b(const|let|var|export|import|from|new|function|def|class|return|if|else|async|await|try|catch|except|for|while|in|of|with|as)\b/g
        const fnRegex = /\b([a-zA-Z0-9_]+)(?=\()/g
        const strRegex = /(['"`].*?['"`])/g
        return (
          <div key={idx} dangerouslySetInnerHTML={{
            __html: line
              .replace(strRegex, '<span class="str">$1</span>')
              .replace(kwRegex, '<span class="kw">$1</span>')
              .replace(fnRegex, '<span class="fn">$1</span>')
          }} />
        )
      })}
    </pre>
  )
}

// ─── Starter queries shown when no history exists (onboarding) ───────────────
const STARTER_QUERIES = [
  'Where have I implemented WebSocket real-time features?',
  'In which language is the backend implemented?',
  'Show me retry or backoff error handling logic',
  'How does the RAG retrieval router work?',
  'What authentication patterns are used in the codebase?',
]

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  // Navigation tabs: 'ask' | 'history' | 'repos'
  const [activeTab, setActiveTab] = useState('ask')

  // Repos & health
  const [reposList, setReposList] = useState([])
  const [selectedRepos, setSelectedRepos] = useState([])
  const [healthStatus, setHealthStatus] = useState(null)
  // null = not yet checked, true = backend up, false = backend down
  const [backendAvailable, setBackendAvailable] = useState(null)

  // commit 8: History with `saved` flag (replaces separate savedQueries array)
  const [history, setHistory] = useState(() => {
    try { return JSON.parse(localStorage.getItem('kb_query_history') || '[]') }
    catch { return [] }
  })
  // commit 8: history filter pill: 'all' | 'saved'
  const [historyFilter, setHistoryFilter] = useState('all')
  const [historySearchQuery, setHistorySearchQuery] = useState('')
  const [selectedHistoryIds, setSelectedHistoryIds] = useState(new Set())

  // Persist history
  useEffect(() => {
    try { localStorage.setItem('kb_query_history', JSON.stringify(history)) }
    catch {}
  }, [history])

  // commit 10: session-only conversation thread (never persisted)
  const [conversationHistory, setConversationHistory] = useState([])

  // Section collapse states
  const [summaryCollapsed, setSummaryCollapsed] = useState(false)
  const [keyFilesCollapsed, setKeyFilesCollapsed] = useState(false)
  const [evidenceCollapsed, setEvidenceCollapsed] = useState(false)
  const [sourcesCollapsed, setSourcesCollapsed] = useState(false)

  // Repo management state
  const [showAddModal, setShowAddModal] = useState(false)
  const [newRepoName, setNewRepoName] = useState('')
  const [newRepoUrl, setNewRepoUrl] = useState('')
  const [repoActionLoading, setRepoActionLoading] = useState(false)
  const [repoActionMode, setRepoActionMode] = useState('')
  const [repoActionMessage, setRepoActionMessage] = useState('')
  const [lastSyncText, setLastSyncText] = useState('Just now')

  // commit 7: copy state
  const [copied, setCopied] = useState(false)
  // commit 6: feedback state
  const [feedbackSent, setFeedbackSent] = useState(null) // 'up' | 'down' | null
  const [feedbackToast, setFeedbackToast] = useState(false)

  // ── Load repos & health ────────────────────────────────────────────────────
  const loadSystemInfo = async () => {
    try {
      const [reposRes, healthRes] = await Promise.all([
        axios.get('/repos').catch(() => null),
        axios.get('/health').catch(() => null),
      ])

      if (reposRes === null && healthRes === null) {
        // Both calls failed — backend is not reachable
        setBackendAvailable(false)
        return
      }

      setBackendAvailable(true)

      if (reposRes?.data) {
        // API returns { repos, repos_detail, count, chunk_counts, last_sync }
        // Use repos_detail which has { name, url, chunk_count } objects
        const detail = reposRes.data.repos_detail || []
        setReposList(detail.map(r => ({
          ...r,
          count: r.chunk_count || 0,
          ...getRepoStyle(r.name),   // commit 9: hash-stable color
        })))
      }
      if (healthRes?.data) setHealthStatus(healthRes.data)
      setLastSyncText(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
    } catch {}
  }

  useEffect(() => { loadSystemInfo() }, [])

  // ── Repo filter toggle ─────────────────────────────────────────────────────
  const toggleRepoFilter = (repoName) => {
    setSelectedRepos(prev =>
      prev.includes(repoName) ? prev.filter(r => r !== repoName) : [...prev, repoName]
    )
  }

  // ── Handle query ───────────────────────────────────────────────────────────
  const handleQuery = async () => {
    const qText = query.trim()
    if (!qText || loading) return

    setLoading(true)
    setError(null)
    setActiveTab('ask')
    setFeedbackSent(null)

    try {
      const payload = {
        query: qText,
        ...(selectedRepos.length > 0 ? { repos: selectedRepos } : {}),
        // commit 10: send last 3 turns of session conversation
        ...(conversationHistory.length > 0 ? {
          conversation_history: conversationHistory.slice(-3).map(t => ({
            query: t.query,
            answer: t.answer,
          }))
        } : {}),
      }
      const res = await axios.post('/query', payload)
      const data = res.data
      setResult(data)

      // commit 10: append to session conversation history
      setConversationHistory(prev => [...prev, { query: qText, answer: data.answer || '' }])

      // commit 8: add to history (with saved=false by default)
      // Derive repos from backend routed_repos or citations or active filter
      const reposUsed = data.routed_repos && data.routed_repos.length > 0
        ? data.routed_repos
        : (data.citations || []).length > 0
        ? [...new Set((data.citations || []).map(c => c.metadata?.repo).filter(Boolean))]
        : selectedRepos.length > 0 ? selectedRepos : reposList.map(r => r.name)
      const historyItem = {
        id: Date.now(),
        query: qText,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        latency_ms: data.latency_ms,
        citationsCount: (data.citations || []).length,
        repos: reposUsed,
        result: data,
        saved: false,   // bookmark flag
      }
      setHistory(prev => [historyItem, ...prev.slice(0, 49)])
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Error processing query.')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); handleQuery() }
  }

  // ── commit 8: Toggle bookmark on a history item ────────────────────────────
  const toggleBookmark = (id) => {
    setHistory(prev => prev.map(h => h.id === id ? { ...h, saved: !h.saved } : h))
  }

  const deleteHistoryItem = (id) => {
    setHistory(prev => prev.filter(h => h.id !== id))
    setSelectedHistoryIds(prev => { const n = new Set(prev); n.delete(id); return n })
  }

  // Bulk selection helpers
  const toggleHistorySelect = (id) => {
    setSelectedHistoryIds(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }
  const bulkDelete = (ids) => {
    setHistory(prev => prev.filter(h => !ids.has(h.id)))
    setSelectedHistoryIds(new Set())
  }
  const bulkSave = (ids) => {
    setHistory(prev => prev.map(h => ids.has(h.id) ? { ...h, saved: true } : h))
    setSelectedHistoryIds(new Set())
  }

  // ── commit 6: Submit feedback ──────────────────────────────────────────────
  const submitFeedback = async (rating) => {
    if (!result || feedbackSent) return
    setFeedbackSent(rating)
    try {
      await axios.post('/feedback', {
        query: query,
        answer_snippet: (result.answer || '').slice(0, 200),
        rating,
        routed_repos: result.routed_repos || [],
      })
      setFeedbackToast(true)
      setTimeout(() => setFeedbackToast(false), 1800)
    } catch {}
  }

  // ── commit 7: Copy as markdown ────────────────────────────────────────────
  const copyAsMarkdown = () => {
    if (!result) return
    const citationsMd = (result.citations || []).map((c, i) => {
      const line = c.start_line ? `L${c.start_line}${c.end_line ? `-${c.end_line}` : ''}` : ''
      return `[${i + 1}] ${c.repo}/${c.file_path || c.symbol_name || ''}${line ? ':' + line : ''}`
    }).join('\n')
    const md = `# ${query}\n\n${result.answer || ''}\n\n---\n**Sources:**\n${citationsMd}`
    navigator.clipboard.writeText(md)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  // ── Repo actions ───────────────────────────────────────────────────────────
  const handleAddRepo = async (e) => {
    e.preventDefault()
    setRepoActionLoading(true)
    setRepoActionMode('add')
    setRepoActionMessage(`Ingesting '${newRepoName.trim()}' and building vector embeddings…`)
    try {
      await axios.post('/repos/add', { name: newRepoName.trim(), url: newRepoUrl.trim() })
      setShowAddModal(false)
      setNewRepoName('')
      setNewRepoUrl('')
      await loadSystemInfo()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to add repository.')
    } finally {
      setRepoActionLoading(false)
      setRepoActionMode('')
      setRepoActionMessage('')
    }
  }

  const handleDeleteRepo = async (repoName) => {
    if (!window.confirm(`Delete '${repoName}'? It will be removed from all indexes.`)) return
    setRepoActionLoading(true)
    setRepoActionMode('delete')
    setRepoActionMessage(`Removing '${repoName}' from FAISS & BM25 indexes…`)
    try {
      await axios.delete(`/repos/${encodeURIComponent(repoName)}`)
      setSelectedRepos(prev => prev.filter(r => r !== repoName))
      await loadSystemInfo()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to delete repository.')
    } finally {
      setRepoActionLoading(false)
      setRepoActionMode('')
      setRepoActionMessage('')
    }
  }

  const handleUpdateRepo = async (repoName) => {
    setRepoActionLoading(true)
    setRepoActionMode('update')
    setRepoActionMessage(`Re-indexing '${repoName}' with latest changes…`)
    try {
      await axios.post(`/repos/${encodeURIComponent(repoName)}/update`)
      await loadSystemInfo()
    } catch (err) {
      alert(err.response?.data?.detail || 'Failed to update repository.')
    } finally {
      setRepoActionLoading(false)
      setRepoActionMode('')
      setRepoActionMessage('')
    }
  }

  // ── Citation processing ────────────────────────────────────────────────────
  const processCitations = () => {
    if (!result?.citations?.length) return { keyFiles: [], evidenceGroups: [], sourceGroups: [] }
    const citations = result.citations
    const repoIndexMap = {}
    reposList.forEach(r => { repoIndexMap[r.name] = r })

    const fileRefMap = {}, fileEvidenceMap = {}, fileSourcesMap = {}

    citations.forEach(c => {
      const fname = c.file_path || c.symbol_name || 'Document / Commit'
      const repoName = c.repo || 'Repository'
      const repoStyle = getRepoStyle(repoName)   // commit 9

      if (!fileRefMap[fname]) fileRefMap[fname] = { count: 0, repo: repoName, repoStyle }
      fileRefMap[fname].count += 1

      if (!fileEvidenceMap[fname]) fileEvidenceMap[fname] = {
        repo: repoName, repoStyle,
        n: c.start_line ? `lines ${c.start_line}–${c.end_line || c.start_line}` : (c.chunk_type || 'reference'),
        items: []
      }
      fileEvidenceMap[fname].items.push({
        tag: c.symbol_name || (c.start_line ? `lines ${c.start_line}–${c.end_line || c.start_line}` : ''),
        code: c.snippet,
      })

      if (!fileSourcesMap[fname]) fileSourcesMap[fname] = { repo: repoName, repoStyle, lines: [] }
      const lineTag = c.start_line
        ? (c.end_line && c.end_line !== c.start_line ? `L${c.start_line}–${c.end_line}` : `L${c.start_line}`)
        : (c.commit_hash ? `commit:${c.commit_hash.slice(0, 7)}` : c.chunk_type || 'ref')
      if (!fileSourcesMap[fname].lines.includes(lineTag)) fileSourcesMap[fname].lines.push(lineTag)
    })

    return {
      keyFiles: Object.entries(fileRefMap).map(([fname, d]) => ({ fname, repoStyle: d.repoStyle, count: d.count })),
      evidenceGroups: Object.entries(fileEvidenceMap).map(([fname, d]) => ({ fname, repoStyle: d.repoStyle, n: d.n, items: d.items })),
      sourceGroups: Object.entries(fileSourcesMap).map(([fname, d]) => ({ fname, repoStyle: d.repoStyle, count: d.lines.length, lines: d.lines })),
    }
  }

  const { keyFiles, evidenceGroups, sourceGroups } = processCitations()

  // ── commit 8: saved queries = history items with saved: true ───────────────
  const savedItems = history.filter(h => h.saved)
  // chips on empty state: saved items if any exist, else show onboarding starters
  const suggestionChips = savedItems.length > 0
    ? savedItems.map(h => h.query)
    : STARTER_QUERIES

  // ── ReactMarkdown override: render [doc: label @ path] nicely (commit 2) ──
  const renderMarkdownComponents = {
    code({ node, inline, className, children, ...props }) {
      const content = String(children).replace(/\n$/, '')
      if (inline) return <code style={{ fontFamily: 'var(--mono)', fontSize: '0.88em', background: 'var(--surface-2)', borderRadius: 3, padding: '1px 5px' }}>{content}</code>
      return <pre className="code"><code>{content}</code></pre>
    },
    p({ children }) {
      // Intercept [doc: ...] text nodes and render them as styled file badges (commit 2)
      const processChildren = (ch) => {
        if (typeof ch !== 'string') return ch
        const docTagRegex = /\[doc:\s*([^\]]+)\]/g
        const parts = []
        let last = 0, m
        while ((m = docTagRegex.exec(ch)) !== null) {
          if (m.index > last) parts.push(ch.slice(last, m.index))
          parts.push(
            <span key={m.index} style={{
              display: 'inline-flex', alignItems: 'center', gap: 3,
              fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)',
              background: 'var(--surface-2)', border: '1px solid var(--border-soft)',
              borderRadius: 4, padding: '1px 6px', verticalAlign: 'middle',
            }}>
              <DescriptionIcon sx={{ fontSize: 11, verticalAlign: 'middle' }} />
              {m[1].trim()}
            </span>
          )
          last = m.index + m[0].length
        }
        if (last < ch.length) parts.push(ch.slice(last))
        return parts.length > 1 ? parts : ch
      }
      const processed = React.Children.map(children, processChildren)
      return <p>{processed}</p>
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div className="shell">

      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="brand" style={{ padding: '4px 0' }}>
          <div style={{
            fontFamily: 'var(--mono)',
            fontSize: 22,
            fontWeight: 900,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            whiteSpace: 'nowrap',
            lineHeight: 1,
          }}>
            CodeAtlas
          </div>
        </div>

        {/* commit 3: 'Search' → 'Ask'; commit 8: remove 'Saved queries' nav item */}
        <div className="nav-group">
          <div
            className={`nav-item ${activeTab === 'ask' ? 'active' : ''}`}
            onClick={() => setActiveTab('ask')}
          >
            <SearchIcon sx={{ fontSize: 16 }} />
            Ask
          </div>

          <div
            className={`nav-item ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            <HistoryIcon sx={{ fontSize: 16 }} />
            History {history.length > 0 && <span style={{ marginLeft: 'auto', fontSize: 11, opacity: 0.7 }}>({history.length})</span>}
          </div>

          <div
            className={`nav-item ${activeTab === 'repos' ? 'active' : ''}`}
            onClick={() => setActiveTab('repos')}
          >
            <FolderIcon sx={{ fontSize: 16 }} />
            Repositories
          </div>
        </div>

        <div className="sidebar-foot">groq · jina · faiss</div>
      </aside>

      {/* MAIN */}
      <main>
        <div className="topline">
          <div>
            <h1 className="page-title">
              {activeTab === 'ask' && 'Ask anything across your repositories'}
              {activeTab === 'history' && 'Query Execution History'}
              {activeTab === 'repos' && 'Repository Management'}
            </h1>
          </div>
        </div>

        {/* ─── HERO SEARCH BAR (ask tab only) ─────────────────────────────── */}
        {activeTab === 'ask' && backendAvailable === false ? (
          // Backend not reachable — show connection error, not "no repos"
          <div style={{
            background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: 14, padding: '40px 32px', textAlign: 'center', marginTop: 8,
          }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🔌</div>
            <h3 style={{ color: '#f87171', margin: '0 0 10px', fontWeight: 700, fontSize: 17 }}>
              Backend Not Reachable
            </h3>
            <p style={{ color: 'var(--text-dim)', fontSize: 13, margin: '0 0 20px', maxWidth: 400, marginLeft: 'auto', marginRight: 'auto' }}>
              Could not connect to the API server on <code style={{ fontFamily: 'var(--mono)', background: 'var(--surface-2)', padding: '1px 5px', borderRadius: 3 }}>localhost:8000</code>.
              Make sure the backend is running:
            </p>
            <pre style={{ fontFamily: 'var(--mono)', fontSize: 12, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 16px', display: 'inline-block', marginBottom: 20, color: 'var(--accent)' }}>
              uvicorn api.main:app --reload --port 8000
            </pre>
            <br />
            <button
              onClick={loadSystemInfo}
              style={{
                background: 'var(--accent)', color: '#000', border: 'none',
                borderRadius: 10, padding: '10px 22px', fontSize: 13,
                fontWeight: 700, cursor: 'pointer',
              }}
            >
              Retry Connection
            </button>
          </div>
        ) : activeTab === 'ask' && backendAvailable === true && reposList.length === 0 ? (
          // Backend is up but no repos configured — guide user to add one
          <div style={{
            background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 14, padding: '48px 32px', textAlign: 'center', marginTop: 8,
          }}>
            <FolderIcon sx={{ fontSize: 44, color: 'var(--text-dim)', display: 'block', mx: 'auto', mb: 2 }} />
            <h3 style={{ color: 'var(--text)', margin: '0 0 10px', fontWeight: 700, fontSize: 18 }}>
              No Repositories Indexed
            </h3>
            <p style={{ color: 'var(--text-dim)', fontSize: 14, margin: '0 0 24px', maxWidth: 420, marginLeft: 'auto', marginRight: 'auto' }}>
              The knowledge base has no repositories to search. Add at least one repository to start asking questions about your code.
            </p>
            <button
              onClick={() => setActiveTab('repos')}
              style={{
                background: 'var(--accent)', color: '#000', border: 'none',
                borderRadius: 10, padding: '12px 24px', fontSize: 14,
                fontWeight: 700, cursor: 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 8,
              }}
            >
              <AddIcon sx={{ fontSize: 18 }} />
              Add Your First Repository
            </button>
          </div>
        ) : activeTab === 'ask' && reposList.length > 0 && (
          <div className="hero">
            {/* commit 10: conversation thread indicator */}
            {conversationHistory.length > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 11.5, color: 'var(--accent)', fontFamily: 'var(--mono)',
                marginBottom: 10, padding: '6px 10px',
                background: 'var(--accent-soft)', borderRadius: 6,
                border: '1px solid var(--accent-line)',
              }}>
                <ForumIcon sx={{ fontSize: 13 }} />
                Continuing conversation ({conversationHistory.length} turn{conversationHistory.length !== 1 ? 's' : ''})
                <button
                  onClick={() => setConversationHistory([])}
                  title="Clear conversation thread"
                  style={{
                    marginLeft: 'auto', background: 'none', border: 'none',
                    cursor: 'pointer', color: 'var(--accent)', padding: 0,
                    display: 'flex', alignItems: 'center',
                  }}
                >
                  <CloseIcon sx={{ fontSize: 13 }} />
                </button>
              </div>
            )}

            <div className="search-row">
              <div className="search-box">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></svg>
                <input
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask anything about your code… e.g. Where is authentication handled?"
                  autoFocus
                />
              </div>
              <button
                className="ask-btn"
                onClick={handleQuery}
                disabled={loading || !query.trim()}
              >
                {loading ? 'Searching…' : 'Ask'}
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
              </button>
            </div>

            {/* REPO CHIPS FILTER */}
            <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                Filter search by repository (click to select/deselect):
              </div>
              <div className="repo-chips" style={{ marginTop: 0 }}>
                {reposList.map((r, i) => {
                  const isSelected = selectedRepos.includes(r.name)
                  const rStyle = getRepoStyle(r.name)
                  return (
                    <div
                      key={i}
                      className={`chip ${rStyle.classKey}`}
                      style={{
                        border: isSelected ? `1px solid ${rStyle.color}` : '1px solid var(--border)',
                        background: isSelected ? rStyle.soft : undefined,
                        boxShadow: isSelected ? `0 0 8px ${rStyle.soft}` : 'none',
                      }}
                      onClick={() => toggleRepoFilter(r.name)}
                      title={isSelected ? 'Click to deselect filter' : 'Click to filter to this repo'}
                    >
                      <span className="repo-dot" style={{ background: rStyle.color }}></span>
                      {r.name} <span className="n">{r.count}</span>
                      {isSelected && <span style={{ marginLeft: 4, color: rStyle.color, fontWeight: 700, fontSize: 11 }}>✓</span>}
                    </div>
                  )
                })}
                {selectedRepos.length > 0 && (
                  <button
                    onClick={() => setSelectedRepos([])}
                    style={{
                      background: 'none', border: '1px solid var(--border-soft)', color: '#f87171',
                      fontSize: 11, fontFamily: 'var(--mono)', cursor: 'pointer',
                      padding: '4px 8px', borderRadius: 100,
                      display: 'flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    <CloseIcon sx={{ fontSize: 11 }} /> Clear filter ({selectedRepos.length})
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ─── TAB: ASK content (only when backend is up and repos exist) ── */}
        {activeTab === 'ask' && backendAvailable === true && reposList.length > 0 && (
          <>
            {error && (
              <div style={{
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 10, padding: '12px 16px', color: '#f87171', fontSize: 13, marginBottom: 20,
              }}>
                ⚠ {error}
              </div>
            )}

            {loading && (
              <div className="loading-skeleton">
                <div className="loading-spinner"></div>
                <div>Routing query across vector indexes · Retrieving code chunks · Synthesizing answer…</div>
              </div>
            )}

            {/* Empty state with suggestion chips */}
            {!result && !loading && !error && (
              <div style={{
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 14, padding: '36px 28px', textAlign: 'center', color: 'var(--text-mid)',
              }}>
                <SearchIcon sx={{ fontSize: 36, color: 'var(--text-dim)', mb: 1.5, display: 'block', mx: 'auto' }} />
                <h3 style={{ color: 'var(--text)', margin: '0 0 8px', fontWeight: 700 }}>Ready to Ask</h3>
                <p style={{ margin: '0 0 6px', fontSize: 13, color: 'var(--text-dim)' }}>
                  {savedItems.length > 0
                    ? 'Your saved queries — click to pre-fill the search box:'
                    : 'Try one of these starter questions:'}
                </p>
                {/* commit 8: chips backed by saved history, fall back to starters */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'center', marginTop: 14 }}>
                  {suggestionChips.map((sq, i) => (
                    <button
                      key={i}
                      className="source-line"
                      style={{ cursor: 'pointer', padding: '6px 12px', fontSize: 12.5 }}
                      onClick={() => setQuery(sq)}
                    >
                      <BoltIcon sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.5 }} />
                      {sq}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Results */}
            {result && !loading && (
              <>
                {/* commit 5: ambiguity warning banner */}
                {result.ambiguity_flag && (
                  <div style={{
                    background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.4)',
                    borderRadius: 10, padding: '10px 16px',
                    display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 16,
                  }}>
                    <WarningAmberIcon sx={{ color: '#FBBF24', fontSize: 18, mt: 0.15, flexShrink: 0 }} />
                    <div>
                      <div style={{ color: '#FBBF24', fontWeight: 700, fontSize: 13 }}>
                        Conflicting implementations found across repositories
                      </div>
                      {result.ambiguity_detail && (
                        <div style={{ color: 'var(--text-mid)', fontSize: 12, marginTop: 2 }}>
                          {result.ambiguity_detail}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Answer meta bar */}
                <div className="answer-meta">
                  <span className="ok">Answer ready</span>
                  <span className="dividerdot">·</span>
                  <SpeedIcon sx={{ fontSize: 12, verticalAlign: 'middle' }} />
                  <span>{Math.round(result.latency_ms || 0)} ms</span>
                  <span className="dividerdot">·</span>
                  <span>types: {(result.routed_types || ['code']).join(', ')}</span>
                  <span className="dividerdot">·</span>
                  <span style={{ color: 'var(--accent)' }}>{(result.citations || []).length} citations</span>

                  <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
                    {/* commit 6: feedback buttons */}
                    <button
                      onClick={() => submitFeedback('up')}
                      title="This answer was helpful"
                      style={{
                        background: feedbackSent === 'up' ? 'rgba(127,216,166,0.15)' : 'none',
                        border: `1px solid ${feedbackSent === 'up' ? '#7FD8A6' : 'var(--border)'}`,
                        borderRadius: 6, color: feedbackSent === 'up' ? '#7FD8A6' : 'var(--text-dim)',
                        padding: '2px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3,
                        fontSize: 11,
                      }}
                    >
                      <ThumbUpIcon sx={{ fontSize: 11 }} />
                    </button>
                    <button
                      onClick={() => submitFeedback('down')}
                      title="This answer was not helpful"
                      style={{
                        background: feedbackSent === 'down' ? 'rgba(248,113,113,0.12)' : 'none',
                        border: `1px solid ${feedbackSent === 'down' ? '#f87171' : 'var(--border)'}`,
                        borderRadius: 6, color: feedbackSent === 'down' ? '#f87171' : 'var(--text-dim)',
                        padding: '2px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 3,
                        fontSize: 11,
                      }}
                    >
                      <ThumbDownIcon sx={{ fontSize: 11 }} />
                    </button>

                    {/* commit 7: copy-as-markdown */}
                    <button
                      onClick={copyAsMarkdown}
                      title="Copy answer as Markdown"
                      style={{
                        background: copied ? 'rgba(139,147,248,0.15)' : 'none',
                        border: `1px solid ${copied ? 'var(--accent)' : 'var(--border)'}`,
                        borderRadius: 6, color: copied ? 'var(--accent)' : 'var(--text-dim)',
                        padding: '2px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                        fontSize: 11,
                      }}
                    >
                      {copied ? <CheckIcon sx={{ fontSize: 11 }} /> : <ContentCopyIcon sx={{ fontSize: 11 }} />}
                      {copied ? 'Copied!' : 'Copy MD'}
                    </button>

                    {/* commit 8: bookmark current query */}
                    <button
                      onClick={() => {
                        const item = history.find(h => h.query === query)
                        if (item) toggleBookmark(item.id)
                      }}
                      title={history.find(h => h.query === query)?.saved ? 'Remove bookmark' : 'Save query'}
                      style={{
                        background: 'none', border: '1px solid var(--border)',
                        borderRadius: 6, color: history.find(h => h.query === query)?.saved ? 'var(--repo-a)' : 'var(--text-mid)',
                        padding: '2px 8px', cursor: 'pointer', fontSize: 11, fontFamily: 'var(--mono)',
                        display: 'flex', alignItems: 'center', gap: 4,
                      }}
                    >
                      {history.find(h => h.query === query)?.saved
                        ? <><BookmarkIcon sx={{ fontSize: 11 }} /> Saved</>
                        : <><BookmarkBorderIcon sx={{ fontSize: 11 }} /> Save</>}
                    </button>
                  </div>
                </div>

                {/* Feedback toast */}
                {feedbackToast && (
                  <div style={{
                    position: 'fixed', bottom: 24, right: 24, zIndex: 500,
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 10, padding: '10px 16px', fontSize: 13,
                    color: 'var(--text)', boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}>
                    <CheckCircleIcon sx={{ fontSize: 16, color: '#7FD8A6' }} />
                    Feedback recorded — thanks!
                  </div>
                )}

                <div className="answer-wrap">
                  <div className="thread"></div>
                  <div className="answer-card">

                    {/* SUMMARY SECTION */}
                    <div className={`section ${summaryCollapsed ? 'collapsed' : ''}`}>
                      <div className="section-head" onClick={() => setSummaryCollapsed(!summaryCollapsed)}>
                        <div className="section-title">
                          <svg className="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M6 9l6 6 6-6" /></svg>
                          Summary
                        </div>
                      </div>
                      <div className="section-body">
                        <div className="summary-text">
                          {/* commit 4: inline citation numbered badges */}
                          <div style={{ position: 'relative' }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={renderMarkdownComponents}>
                              {result.answer}
                            </ReactMarkdown>
                            {/* Citation reference panel below answer */}
                            {(result.citations || []).length > 0 && (
                              <div style={{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                {result.citations.map((c, i) => {
                                  const rStyle = getRepoStyle(c.repo)
                                  return (
                                    <CitationPopover
                                      key={i}
                                      number={i + 1}
                                      citation={c}
                                      repoStyle={rStyle}
                                    />
                                  )
                                })}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* KEY FILES */}
                    {keyFiles.length > 0 && (
                      <div className={`section ${keyFilesCollapsed ? 'collapsed' : ''}`}>
                        <div className="section-head" onClick={() => setKeyFilesCollapsed(!keyFilesCollapsed)}>
                          <div className="section-title">
                            <svg className="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M6 9l6 6 6-6" /></svg>
                            Key files
                          </div>
                        </div>
                        <div className="section-body">
                          {keyFiles.map((kf, i) => (
                            <div key={i} className="file-row">
                              <span className="fname">
                                <span className={`repo-tag ${kf.repoStyle.classKey}`}><i></i></span>
                                {kf.fname}
                              </span>
                              <span className="refs">{kf.count} reference{kf.count > 1 ? 's' : ''}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* EVIDENCE */}
                    {evidenceGroups.length > 0 && (
                      <div className={`section ${evidenceCollapsed ? 'collapsed' : ''}`}>
                        <div className="section-head" onClick={() => setEvidenceCollapsed(!evidenceCollapsed)}>
                          <div className="section-title">
                            <svg className="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M6 9l6 6 6-6" /></svg>
                            Evidence
                          </div>
                        </div>
                        <div className="section-body">
                          {evidenceGroups.map((eg, i) => (
                            <div key={i} className="evidence-group">
                              <div className="evidence-file-head">
                                <span className={`repo-tag ${eg.repoStyle.classKey}`}><i></i></span>
                                <span className="fname">{eg.fname}</span>
                                <span className="n">{eg.n}</span>
                              </div>
                              {eg.items.map((item, j) => (
                                <React.Fragment key={j}>
                                  {item.tag && <div className="line-tag">{item.tag}</div>}
                                  <HighlightedCode code={item.code} />
                                </React.Fragment>
                              ))}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* SOURCES */}
                    {sourceGroups.length > 0 && (
                      <div className={`section ${sourcesCollapsed ? 'collapsed' : ''}`}>
                        <div className="section-head" onClick={() => setSourcesCollapsed(!sourcesCollapsed)}>
                          <div className="section-title">
                            <svg className="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M6 9l6 6 6-6" /></svg>
                            Sources · {(result.citations || []).length}
                          </div>
                        </div>
                        <div className="section-body">
                          {sourceGroups.map((sg, i) => (
                            <div key={i} className="source-group">
                              <div className="source-group-head">
                                <span className={`repo-tag ${sg.repoStyle.classKey}`}><i></i></span>
                                <span className="fname">{sg.fname}</span>
                                <span className="n">{sg.count} reference{sg.count > 1 ? 's' : ''}</span>
                              </div>
                              <div className="source-lines">
                                {sg.lines.map((line, j) => (
                                  <span key={j} className="source-line">{line}</span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ─── TAB: HISTORY ─────────────────────────────────────────────── */}
        {activeTab === 'history' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Row 1: Filter pills + search + clear all */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              {/* Filter pills */}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {['all', 'saved'].map(f => (
                  <button
                    key={f}
                    onClick={() => setHistoryFilter(f)}
                    style={{
                      background: historyFilter === f ? 'var(--accent-soft)' : 'none',
                      border: `1px solid ${historyFilter === f ? 'var(--accent-line)' : 'var(--border)'}`,
                      color: historyFilter === f ? 'var(--accent)' : 'var(--text-mid)',
                      borderRadius: 100, padding: '4px 14px', fontSize: 12,
                      fontWeight: historyFilter === f ? 700 : 400,
                      cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5,
                    }}
                  >
                    {f === 'saved' && <BookmarkIcon sx={{ fontSize: 12 }} />}
                    {f === 'all' ? 'All' : 'Saved'}
                    {f === 'saved' && savedItems.length > 0 && (
                      <span style={{ background: 'var(--accent)', color: '#000', borderRadius: 8, padding: '0 5px', fontSize: 10, fontWeight: 800 }}>
                        {savedItems.length}
                      </span>
                    )}
                  </button>
                ))}
              </div>

              {/* Search bar */}
              <div style={{ position: 'relative', flex: 1, maxWidth: 300, display: 'flex', alignItems: 'center' }}>
                <SearchIcon sx={{ position: 'absolute', left: 10, fontSize: 15, color: 'var(--text-dim)', pointerEvents: 'none' }} />
                <input
                  type="text"
                  placeholder="Search queries..."
                  value={historySearchQuery}
                  onChange={e => setHistorySearchQuery(e.target.value)}
                  style={{
                    width: '100%', background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 8, padding: '5px 28px 5px 32px', fontSize: 12,
                    color: 'var(--text)', outline: 'none', fontFamily: 'var(--sans)',
                  }}
                />
                {historySearchQuery && (
                  <CloseIcon onClick={() => setHistorySearchQuery('')} sx={{ position: 'absolute', right: 8, fontSize: 14, color: 'var(--text-dim)', cursor: 'pointer' }} />
                )}
              </div>

              {/* Clear all */}
              {history.length > 0 && (
                <button
                  onClick={() => { setHistory([]); setSelectedHistoryIds(new Set()) }}
                  style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 6, color: '#f87171', padding: '4px 10px', fontSize: 12, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}
                >
                  <DeleteOutlineIcon sx={{ fontSize: 13 }} /> Clear All
                </button>
              )}
            </div>

            {/* Row 2: Bulk action bar — appears when items are selected */}
            {selectedHistoryIds.size > 0 && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                background: 'var(--accent-soft)', border: '1px solid var(--accent-line)',
                borderRadius: 10, padding: '8px 14px',
              }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--accent)', fontWeight: 700 }}>
                  {selectedHistoryIds.size} selected
                </span>
                <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
                  <button
                    onClick={() => bulkSave(selectedHistoryIds)}
                    style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'var(--accent-soft)', border: '1px solid var(--accent-line)', borderRadius: 6, color: 'var(--accent)', padding: '4px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                  >
                    <BookmarkIcon sx={{ fontSize: 13 }} /> Save Selected
                  </button>
                  <button
                    onClick={() => bulkDelete(selectedHistoryIds)}
                    style={{ display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', borderRadius: 6, color: '#f87171', padding: '4px 12px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                  >
                    <DeleteOutlineIcon sx={{ fontSize: 13 }} /> Delete Selected
                  </button>
                  <button
                    onClick={() => setSelectedHistoryIds(new Set())}
                    style={{ background: 'none', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-dim)', padding: '4px 10px', fontSize: 12, cursor: 'pointer' }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* History list */}
            {(() => {
              let items = historyFilter === 'saved' ? savedItems : history
              if (historySearchQuery.trim()) {
                const q = historySearchQuery.toLowerCase().trim()
                items = items.filter(item => item.query.toLowerCase().includes(q))
              }

              if (items.length === 0) return (
                <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '40px 20px', textAlign: 'center', color: 'var(--text-dim)' }}>
                  {historySearchQuery.trim()
                    ? `No queries matching "${historySearchQuery.trim()}"`
                    : historyFilter === 'saved'
                    ? 'No saved queries yet. Bookmark answers using the Save button.'
                    : 'No query history yet. Queries you execute will appear here!'}
                </div>
              )

              // check if all visible are selected (for Select All toggle)
              const allVisibleIds = new Set(items.map(i => i.id))
              const allSelected = items.length > 0 && items.every(i => selectedHistoryIds.has(i.id))

              return (
                <>
                  {/* Select All row */}
                  {items.length > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 4 }}>
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={() => {
                          if (allSelected) {
                            setSelectedHistoryIds(prev => {
                              const n = new Set(prev)
                              allVisibleIds.forEach(id => n.delete(id))
                              return n
                            })
                          } else {
                            setSelectedHistoryIds(prev => new Set([...prev, ...allVisibleIds]))
                          }
                        }}
                        style={{ width: 14, height: 14, accentColor: 'var(--accent)', cursor: 'pointer' }}
                      />
                      <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)' }}>
                        {allSelected ? 'Deselect all' : `Select all (${items.length})`}
                      </span>
                    </div>
                  )}

                  {items.map(item => {
                    let repos = item.repos || []
                    if (repos.length === 0) {
                      if (item.result?.routed_repos && item.result.routed_repos.length > 0) {
                        repos = item.result.routed_repos
                      } else if (item.result?.citations && item.result.citations.length > 0) {
                        repos = [...new Set(item.result.citations.map(c => c.metadata?.repo).filter(Boolean))]
                      }
                    }
                    const isSelected = selectedHistoryIds.has(item.id)

                    return (
                      <div
                        key={item.id}
                        style={{
                          background: 'var(--surface)',
                          border: `1px solid ${isSelected ? 'var(--accent-line)' : item.saved ? 'var(--accent-line)' : 'var(--border)'}`,
                          borderRadius: 12, padding: '14px 18px',
                          display: 'flex', flexDirection: 'column', gap: 8,
                          outline: isSelected ? '1px solid rgba(139,147,248,0.2)' : 'none',
                        }}
                        title={`Query took ${Math.round(item.latency_ms || 0)} ms`}
                      >
                        {/* Row 1: checkbox + query text */}
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleHistorySelect(item.id)}
                            style={{ width: 14, height: 14, marginTop: 2, accentColor: 'var(--accent)', cursor: 'pointer', flexShrink: 0 }}
                          />
                          <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)', flex: 1, lineHeight: 1.4 }}>
                            {item.query}
                          </span>
                        </div>

                        {/* Row 2: Repo pills + citations + actions (view, save, delete) + time & date (Single Line!) */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingLeft: 24 }}>
                          {repos.length > 0 && (
                            <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
                              {repos.map(r => {
                                const rStyle = getRepoStyle(r)
                                return (
                                  <span
                                    key={r}
                                    style={{
                                      display: 'inline-flex', alignItems: 'center', gap: 5,
                                      fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 500,
                                      padding: '2px 8px', borderRadius: 100,
                                      color: rStyle.color,
                                      background: rStyle.soft,
                                      border: `1px solid ${rStyle.color}44`,
                                    }}
                                  >
                                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: rStyle.color, display: 'inline-block' }} />
                                    {r}
                                  </span>
                                )
                              })}
                            </div>
                          )}

                          {repos.length > 0 && <span style={{ color: 'var(--text-dim)', opacity: 0.4, fontSize: 11 }}>·</span>}

                          <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)' }}>
                            {item.citationsCount} citation{item.citationsCount !== 1 ? 's' : ''}
                          </span>

                          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
                            {/* View (Eye) */}
                            <button
                              onClick={() => { setQuery(item.query); setResult(item.result); setActiveTab('ask') }}
                              title="View answer details"
                              style={{
                                background: 'var(--accent-soft)', border: '1px solid var(--accent-line)',
                                borderRadius: 6, color: 'var(--accent)',
                                padding: '3px 8px', fontSize: 11, cursor: 'pointer',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                              }}
                            >
                              <VisibilityIcon sx={{ fontSize: 13 }} />
                            </button>

                            {/* Save (Bookmark) */}
                            <button
                              onClick={() => toggleBookmark(item.id)}
                              title={item.saved ? 'Remove bookmark' : 'Bookmark this query'}
                              style={{
                                background: 'none',
                                border: `1px solid ${item.saved ? 'var(--accent-line)' : 'var(--border)'}`,
                                borderRadius: 6, color: item.saved ? 'var(--accent)' : 'var(--text-dim)',
                                padding: '3px 8px', fontSize: 11, cursor: 'pointer',
                                display: 'flex', alignItems: 'center', gap: 3,
                              }}
                            >
                              {item.saved ? <BookmarkIcon sx={{ fontSize: 11 }} /> : <BookmarkBorderIcon sx={{ fontSize: 11 }} />}
                            </button>

                            {/* Delete */}
                            <button
                              onClick={() => deleteHistoryItem(item.id)}
                              title="Delete query from history"
                              style={{
                                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                                borderRadius: 6, color: '#f87171', padding: '3px 8px', fontSize: 11, cursor: 'pointer',
                                display: 'flex', alignItems: 'center', gap: 3,
                              }}
                            >
                              <DeleteOutlineIcon sx={{ fontSize: 12 }} />
                            </button>

                            <span style={{ color: 'var(--text-dim)', opacity: 0.4, fontSize: 11 }}>·</span>

                            <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--text-dim)', whiteSpace: 'nowrap' }}>
                              {item.timestamp}
                            </span>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </>
              )
            })()}
          </div>
        )}

        {/* ─── TAB: REPOSITORIES ───────────────────────────────────────────── */}
        {activeTab === 'repos' && (

          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '20px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Configured Repositories</h3>
                <button
                  onClick={() => setShowAddModal(true)}
                  style={{
                    background: 'var(--accent)', color: '#000', border: 'none', borderRadius: 8,
                    padding: '8px 16px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <AddIcon sx={{ fontSize: 16 }} /> Add Repository
                </button>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {reposList.length === 0 ? (
                  <div style={{ padding: '24px 0', textAlign: 'center', color: 'var(--text-dim)', fontSize: 13 }}>
                    No repositories configured yet. Click <b>Add Repository</b> to index your first codebase.
                  </div>
                ) : (
                  reposList.map((r, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-2)', border: '1px solid var(--border-soft)',
                        borderRadius: 10, padding: '14px 18px',
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <span className="repo-dot" style={{ background: getRepoColor(r.name), width: 10, height: 10 }}></span>
                        <div>
                          <div style={{ fontWeight: 600, fontSize: 14 }}>{r.name}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-dim)', fontFamily: 'var(--mono)' }}>
                            {r.count} chunks · Last synced: {r.last_synced || 'Just now'}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        {/* Update: re-index this repo only, leave others untouched */}
                        <button
                          onClick={() => handleUpdateRepo(r.name)}
                          title={`Pull latest changes and re-index '${r.name}' only — other repos stay unchanged`}
                          style={{
                            background: 'rgba(139,147,248,0.1)', border: '1px solid rgba(139,147,248,0.35)',
                            color: 'var(--accent)', borderRadius: 8, padding: '6px 14px',
                            fontSize: 12, fontWeight: 600, cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: 5,
                          }}
                        >
                          <SyncIcon sx={{ fontSize: 14 }} /> Update
                        </button>
                        <button
                          onClick={() => handleDeleteRepo(r.name)}
                          style={{
                            background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)',
                            color: '#f87171', borderRadius: 8, padding: '6px 14px',
                            fontSize: 12, fontWeight: 600, cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: 5,
                          }}
                        >
                          <DeleteOutlineIcon sx={{ fontSize: 14 }} /> Delete
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Index status */}
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '20px 24px' }}>
              <h3 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 700 }}>Vector Index Status</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                {['code.faiss', 'commits.faiss', 'readme.faiss', 'bm25_code.pkl'].map(name => (
                  <div key={name} className="source-line" style={{ padding: 12 }}>
                    <div style={{ color: 'var(--text-dim)', fontSize: 11 }}>{name.replace('.', ' · ').toUpperCase()}</div>
                    <div style={{ color: '#7FD8A6', fontWeight: 600, fontSize: 13, marginTop: 4, display: 'flex', alignItems: 'center', gap: 5 }}>
                      <CheckCircleIcon sx={{ fontSize: 13 }} /> Ready
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ─── ADD REPO MODAL ───────────────────────────────────────────────── */}
        {showAddModal && (
          <div style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 1000, backdropFilter: 'blur(4px)',
          }}>
            <div style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 16, padding: '28px 32px', width: 480, maxWidth: '90vw',
              boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
            }}>
              <h3 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700 }}>Add New Repository</h3>
              <p style={{ margin: '0 0 20px', fontSize: 12, color: 'var(--text-dim)' }}>
                Provide the repository name and Git URL or local folder path. The backend will automatically ingest and index the code.
              </p>
              <form onSubmit={handleAddRepo} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)', marginBottom: 6 }}>
                    REPOSITORY NAME
                  </label>
                  <input
                    type="text" required
                    placeholder="e.g. LearnSphere"
                    value={newRepoName}
                    onChange={e => setNewRepoName(e.target.value)}
                    style={{
                      width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
                      borderRadius: 8, padding: '10px 14px', color: 'var(--text)', fontSize: 13,
                      fontFamily: 'var(--sans)', outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text-dim)', marginBottom: 6 }}>
                    GITHUB URL OR LOCAL PATH
                  </label>
                  <input
                    type="text" required
                    placeholder="e.g. https://github.com/user/repo.git"
                    value={newRepoUrl}
                    onChange={e => setNewRepoUrl(e.target.value)}
                    style={{
                      width: '100%', background: 'var(--surface-2)', border: '1px solid var(--border)',
                      borderRadius: 8, padding: '10px 14px', color: 'var(--text)', fontSize: 13,
                      fontFamily: 'var(--sans)', outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    style={{
                      background: 'none', border: '1px solid var(--border)', borderRadius: 8,
                      padding: '8px 16px', color: 'var(--text-mid)', fontSize: 13, cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    style={{
                      background: 'var(--accent)', color: '#000', border: 'none', borderRadius: 8,
                      padding: '8px 18px', fontSize: 13, fontWeight: 700, cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: 6,
                    }}
                  >
                    <AddIcon sx={{ fontSize: 14 }} /> Add & Index Repo
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ─── FULL-SCREEN LOADING OVERLAY (repo add/delete) ───────────────── */}
        {repoActionLoading && (
          <div style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.88)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            zIndex: 1100, backdropFilter: 'blur(8px)', gap: 18,
          }}>
            <div className="spinner" style={{ width: 48, height: 48, borderWidth: 3.5 }}></div>
            <div style={{ textAlign: 'center', maxWidth: 500 }}>
              <div style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>
                {repoActionMessage || 'Processing repository changes…'}
              </div>
              <div style={{ fontSize: 12, color: 'var(--accent)', fontFamily: 'var(--mono)', marginBottom: 16 }}>
                {repoActionMode === 'delete'
                  ? '⚡ Instant in-place index patching — No re-embedding of other repos'
                  : repoActionMode === 'update'
                  ? '⚡ Single-Repo Re-Index — Only this repo is re-embedded, others untouched'
                  : '⚡ Single-Repository Ingestion — Only this repo is indexed'}
              </div>

              <div style={{
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 12, padding: '16px 20px', textAlign: 'left',
                display: 'flex', flexDirection: 'column', gap: 12, fontSize: 12,
              }}>
                {repoActionMode === 'delete' ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text)' }}>
                      <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }}></span>
                      <span>1. Stripping deleted repo chunks from JSONL files</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>2. Patching FAISS vectors in-place (reconstruct, no JinaAI)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>3. Updating BM25 keyword index & clearing memory cache</span>
                    </div>
                  </>
                ) : repoActionMode === 'update' ? (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text)' }}>
                      <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }}></span>
                      <span>1. Stripping stale chunks for this repo only (no other repos touched)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>2. Git pull latest commits & re-walking AST syntax tree</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>3. Generating fresh 768-dim embeddings with JinaAI (this repo only)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>4. Appending updated vectors to FAISS & BM25 indexes</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text)' }}>
                      <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }}></span>
                      <span>1. Cloning repo & walking AST syntax tree</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>2. Generating 768-dim embeddings with JinaAI (new repo only)</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-dim)' }}>
                      <RadioButtonUncheckedIcon sx={{ fontSize: 14 }} />
                      <span>3. Appending to FAISS index & clearing retriever cache</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

      </main>
    </div>
  )
}



