import React, { useState, useEffect, useRef } from 'react'

const PALETTES = [
  { id: 'palette-kyoto', name: 'Kyoto Hinoki', desc: 'Botanical Moss & Indigo', light: ['#F4F4EC', '#1F573E', '#2C4A78'], dark: ['#080A09', '#57C492', '#7BA8E8'] },
  { id: 'palette-bordeaux', name: 'Bordeaux Petrol', desc: 'Oxblood Wine & Fjord Teal', light: ['#F7F3F0', '#822036', '#1F5B66'], dark: ['#0A0809', '#E86B84', '#5EC2D4'] },
  { id: 'palette-cobalt', name: 'Marrakesh Cobalt', desc: 'Sunlit Sand & Ultramarine', light: ['#F6F1E7', '#2146A6', '#B86B11'], dark: ['#09090B', '#7097F8', '#F0B24C'] },
  { id: 'palette-plum', name: 'Persimmon & Plum', desc: 'Vermilion & Mulberry', light: ['#F8F4EE', '#C43B28', '#6B3263'], dark: ['#0A090A', '#F26A52', '#CC85C2'] },
  { id: 'palette-ft-salmon', name: 'FT Salmon', desc: 'Bisque Newsprint & Oxford', light: ['#FFF1E5', '#990F3D', '#0F5499'], dark: ['#0B0908', '#FF7597', '#66A8FF'] },
  { id: 'palette-bauhaus', name: 'Weimar Bauhaus', desc: 'Archival Vellum & Brick', light: ['#F3EFE6', '#BE3124', '#1D4E89'], dark: ['#090909', '#F25C4E', '#68A2E8'] },
  { id: 'palette-espresso', name: 'Milanese Espresso', desc: 'Roasted Coffee & Olive', light: ['#F6F2EC', '#6F381C', '#4A6128'], dark: ['#0A0806', '#DDA15E', '#99B865'] },
  { id: 'palette-swiss', name: 'Swiss Archival', desc: 'Signal Orange & Slate', light: ['#F7F6F2', '#D9381E', '#1F4E5B'], dark: ['#080808', '#FF5538', '#75B8C8'] },
]

const VOICE_OPTIONS = [
  { id: 'af_sarah', label: 'Sarah (US Female)' },
  { id: 'af_heart', label: 'Heart (US Female)' },
  { id: 'af_bella', label: 'Bella (US Female)' },
  { id: 'am_adam', label: 'Adam (US Male)' },
  { id: 'am_michael', label: 'Michael (US Male)' },
  { id: 'bf_emma', label: 'Emma (UK Female)' },
  { id: 'bm_george', label: 'George (UK Male)' },
]

const DEFAULT_AI_SETTINGS = {
  llm_temperature: 0.35,
  summary_target_words: 250,
  context_min_score: 0.42,
  context_max_precedents: 4,
  articles_per_feed: 5,
  bandit_alpha: 0.4,
  tts_voice: 'af_sarah',
}

const AI_SLIDERS = [
  {
    key: 'llm_temperature',
    label: 'LLM Temperature',
    hint: 'Lower stays strict and factual; higher allows freer phrasing.',
    min: 0.0,
    max: 1.0,
    step: 0.05,
    format: (v) => Number(v).toFixed(2),
  },
  {
    key: 'summary_target_words',
    label: 'Target Summary Length',
    hint: 'Target word budget for each analytical briefing.',
    min: 100,
    max: 400,
    step: 25,
    format: (v) => `${v} words`,
  },
  {
    key: 'context_min_score',
    label: 'Context Cosine min_score',
    hint: 'Minimum semantic similarity (0.20–0.75) to link archive articles.',
    min: 0.2,
    max: 0.75,
    step: 0.01,
    format: (v) => Number(v).toFixed(2),
  },
  {
    key: 'context_max_precedents',
    label: 'Max Timeline Precedents',
    hint: 'Max historical archive stories stitched into a timeline.',
    min: 1,
    max: 6,
    step: 1,
    format: (v) => `${v} stories`,
  },
  {
    key: 'articles_per_feed',
    label: 'Articles Per RSS Feed',
    hint: 'How many recent entries each feed scans per sync.',
    min: 1,
    max: 10,
    step: 1,
    format: (v) => `${v} / feed`,
  },
  {
    key: 'bandit_alpha',
    label: 'LinUCB Exploration (α)',
    hint: '0.0 exploits known likes strictly; higher explores novel topics.',
    min: 0.0,
    max: 1.5,
    step: 0.05,
    format: (v) => `α = ${Number(v).toFixed(2)}`,
  },
]

function getVoiceShortName(voiceId) {
  const match = VOICE_OPTIONS.find((v) => v.id === voiceId)
  return match ? match.label.split(' ')[0] : 'Sarah'
}

/**
 * Safely parse the JSON string takeaways stored in SQLite.
 * If null, invalid, or empty, falls back to the article headline.
 */
function parseTakeaways(takeawaysRaw, fallbackTitle) {
  if (!takeawaysRaw) return [fallbackTitle]
  try {
    const parsed = JSON.parse(takeawaysRaw)
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : [fallbackTitle]
  } catch {
    return [takeawaysRaw]
  }
}

/**
 * Extract an editorial-style publication label from an article URL.
 */
function getSourceName(url) {
  try {
    const host = new URL(url).hostname.replace('www.', '')
    if (host.includes('arstechnica')) return 'Ars Technica'
    if (host.includes('techcrunch')) return 'TechCrunch'
    if (host.includes('ycombinator')) return 'Hacker News'
    return host.split('.')[0].toUpperCase()
  } catch {
    return 'DISPATCH'
  }
}

/**
 * Humanize published dates into relative time ("18m ago", "1h ago", or date string).
 */
function formatTimeAgo(dateStr) {
  if (!dateStr) return 'Recent'
  try {
    const date = new Date(dateStr)
    if (isNaN(date.getTime())) return dateStr.split(' ')[0] || 'Recent'
    const diffMin = Math.round((Date.now() - date.getTime()) / (1000 * 60))
    if (diffMin < 1) return 'Just now'
    if (diffMin < 60) return `${diffMin}m ago`
    const diffHours = Math.round(diffMin / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    return `${Math.round(diffHours / 24)}d ago`
  } catch {
    return 'Recent'
  }
}

export default function App() {
  const [articles, setArticles] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSyncing, setIsSyncing] = useState(false)
  const [isDark, setIsDark] = useState(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem('news_agent_is_dark') === 'true'
  })
  const [dayPalette, setDayPalette] = useState(() => {
    if (typeof window === 'undefined') return 'palette-kyoto'
    return localStorage.getItem('news_agent_day_palette') || 'palette-kyoto'
  })
  const [nightPalette, setNightPalette] = useState(() => {
    if (typeof window === 'undefined') return 'palette-bordeaux'
    return localStorage.getItem('news_agent_night_palette') || 'palette-bordeaux'
  })
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [paletteEditMode, setPaletteEditMode] = useState('light')
  const [aiSettings, setAiSettings] = useState(DEFAULT_AI_SETTINGS)
  const [isSavingSettings, setIsSavingSettings] = useState(false)
  const [settingsStatus, setSettingsStatus] = useState('')
  const [expandedTimelines, setExpandedTimelines] = useState({})
  const [expandedSummaries, setExpandedSummaries] = useState({})
  const [cardHeights, setCardHeights] = useState({})
  const [contextById, setContextById] = useState({})
  const [contextLoading, setContextLoading] = useState({})
  const [contextErrors, setContextErrors] = useState({})
  const [feedback, setFeedback] = useState({})
  const [sortMode, setSortMode] = useState('personalized')
  const [radarStats, setRadarStats] = useState(null)
  const [feeds, setFeeds] = useState([])
  const [newFeedUrl, setNewFeedUrl] = useState('')
  const [newFeedName, setNewFeedName] = useState('')
  const [feedError, setFeedError] = useState('')
  const [isAddingFeed, setIsAddingFeed] = useState(false)

  // Audio Playback State
  const [currentTrack, setCurrentTrack] = useState(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const [audioDuration, setAudioDuration] = useState(0)
  const [audioCurrentTime, setAudioCurrentTime] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1.05)

  const audioRef = useRef(null)

  // Dynamic API Base URL: checks URL query (?api=https://...), localStorage, VITE_API_URL, or relative proxy
  const queryApi = typeof window !== 'undefined' ? new URLSearchParams(window.location.search).get('api') : null
  if (queryApi && typeof window !== 'undefined') {
    localStorage.setItem('news_agent_api_base', queryApi.replace(/\/+$/, ''))
  }
  const API_BASE = (
    queryApi ||
    (typeof window !== 'undefined' ? localStorage.getItem('news_agent_api_base') : '') ||
    import.meta.env.VITE_API_URL ||
    ''
  ).replace(/\/+$/, '')

  // 1. Fetch articles from FastAPI backend
  const fetchArticles = async (mode = sortMode) => {
    try {
      const res = await fetch(`${API_BASE}/api/articles?limit=30&sort=${encodeURIComponent(mode)}`)
      if (res.ok) {
        const data = await res.json()
        setArticles(data)
        const hydratedVotes = {}
        data.forEach((a) => {
          if (a.user_vote === 'up' || a.user_vote === 'down') {
            hydratedVotes[a.id] = a.user_vote
          }
        })
        setFeedback((prev) => ({ ...hydratedVotes, ...prev }))
      }
    } catch (err) {
      console.error('Failed to fetch articles:', err)
    } finally {
      setIsLoading(false)
    }
  }

  const fetchRadarStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/articles/bandit/stats`)
      if (res.ok) {
        const data = await res.json()
        setRadarStats(data)
      }
    } catch (err) {
      console.error('Failed to fetch LinUCB radar stats:', err)
    }
  }

  const fetchSettings = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings`)
      if (res.ok) {
        const data = await res.json()
        setAiSettings((prev) => ({
          ...prev,
          llm_temperature: data.llm_temperature ?? prev.llm_temperature,
          summary_target_words: data.summary_target_words ?? prev.summary_target_words,
          context_min_score: data.context_min_score ?? prev.context_min_score,
          context_max_precedents: data.context_max_precedents ?? prev.context_max_precedents,
          articles_per_feed: data.articles_per_feed ?? prev.articles_per_feed,
          bandit_alpha: data.bandit_alpha ?? prev.bandit_alpha,
          tts_voice: data.tts_voice || prev.tts_voice,
        }))
      }
    } catch (err) {
      console.error('Failed to fetch AI settings:', err)
    }
  }

  const saveAiSettings = async (overrideSettings = null) => {
    const payload = overrideSettings || aiSettings
    setIsSavingSettings(true)
    setSettingsStatus('')
    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const saved = await res.json()
      setAiSettings((prev) => ({ ...prev, ...saved }))
      setSettingsStatus('✓ Saved')
      setTimeout(() => setSettingsStatus(''), 2500)
      fetchArticles(sortMode)
      fetchRadarStats()
    } catch (err) {
      console.error('Failed to save AI settings:', err)
      setSettingsStatus('Failed to save')
    } finally {
      setIsSavingSettings(false)
    }
  }

  const resetAiSettings = () => {
    setAiSettings(DEFAULT_AI_SETTINGS)
    saveAiSettings(DEFAULT_AI_SETTINGS)
  }

  const handleThemeToggle = () => {
    const next = !isDark
    setIsDark(next)
    setPaletteEditMode(next ? 'dark' : 'light')
    if (typeof window !== 'undefined') {
      localStorage.setItem('news_agent_is_dark', String(next))
    }
  }

  const selectPalette = (paletteId) => {
    if (paletteEditMode === 'dark') {
      setNightPalette(paletteId)
      if (!isDark) {
        setIsDark(true)
        if (typeof window !== 'undefined') localStorage.setItem('news_agent_is_dark', 'true')
      }
      if (typeof window !== 'undefined') localStorage.setItem('news_agent_night_palette', paletteId)
    } else {
      setDayPalette(paletteId)
      if (isDark) {
        setIsDark(false)
        if (typeof window !== 'undefined') localStorage.setItem('news_agent_is_dark', 'false')
      }
      if (typeof window !== 'undefined') localStorage.setItem('news_agent_day_palette', paletteId)
    }
  }

  const fetchFeeds = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/feeds`)
      if (res.ok) {
        const data = await res.json()
        setFeeds(Array.isArray(data) ? data : [])
      }
    } catch (err) {
      console.error('Failed to fetch RSS feeds:', err)
    }
  }

  const handleAddFeed = async (e) => {
    e.preventDefault()
    const trimmedUrl = newFeedUrl.trim()
    if (!trimmedUrl) {
      setFeedError('Please enter an RSS or Atom feed URL.')
      return
    }
    setFeedError('')
    setIsAddingFeed(true)
    try {
      const res = await fetch(`${API_BASE}/api/feeds`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: trimmedUrl, name: newFeedName.trim() }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`)
      }
      setFeeds((prev) => [...prev, data])
      setNewFeedUrl('')
      setNewFeedName('')
    } catch (err) {
      setFeedError(err.message || 'Could not add RSS feed.')
    } finally {
      setIsAddingFeed(false)
    }
  }

  const handleToggleFeed = async (feedId, nextEnabled) => {
    setFeedError('')
    try {
      const res = await fetch(`${API_BASE}/api/feeds/${feedId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: nextEnabled }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const updated = await res.json()
      setFeeds((prev) => prev.map((f) => (f.id === feedId ? updated : f)))
    } catch (err) {
      console.error('Failed to toggle RSS feed:', err)
      setFeedError('Could not update feed status.')
    }
  }

  const handleDeleteFeed = async (feedId) => {
    setFeedError('')
    try {
      const res = await fetch(`${API_BASE}/api/feeds/${feedId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setFeeds((prev) => prev.filter((f) => f.id !== feedId))
    } catch (err) {
      console.error('Failed to delete RSS feed:', err)
      setFeedError('Could not remove feed.')
    }
  }

  useEffect(() => {
    fetchArticles('personalized')
    fetchRadarStats()
    fetchSettings()
    fetchFeeds()
  }, [])

  // Measure rendered collapsed card heights after feed load/refresh to balance 2-column masonry
  useEffect(() => {
    if (articles.length <= 1) return
    const raf = requestAnimationFrame(() => {
      const els = document.querySelectorAll('[data-dispatch-card-id]')
      setCardHeights((prev) => {
        let changed = false
        const next = { ...prev }
        els.forEach((el) => {
          if (el.offsetParent === null) return
          const id = Number(el.getAttribute('data-dispatch-card-id'))
          if (expandedSummaries[id] || expandedTimelines[id]) return
          const h = el.offsetHeight
          if (h > 0 && (!prev[id] || Math.abs(prev[id] - h) > 8)) {
            next[id] = h
            changed = true
          }
        })
        return changed ? next : prev
      })
    })
    return () => cancelAnimationFrame(raf)
  }, [articles])

  // 2. Refresh / Sync: instant DB cache check + real-time SSE stream
  const handleSync = async () => {
    if (isSyncing) return
    setIsSyncing(true)

    // Action 1: Instantly fetch any articles already cached by the 30-min cron
    try {
      const maxId = articles.length > 0 ? Math.max(...articles.map((a) => a.id)) : 0
      if (maxId > 0) {
        const res = await fetch(`${API_BASE}/api/articles?since_id=${maxId}`)
        if (res.ok) {
          const cachedNew = await res.json()
          if (cachedNew.length > 0) {
            setArticles((prev) => {
              const existingIds = new Set(prev.map((a) => a.id))
              const uniqueNew = cachedNew.filter((a) => !existingIds.has(a.id))
              return [...uniqueNew, ...prev]
            })
          }
        }
      } else {
        await fetchArticles()
      }
    } catch (err) {
      console.error('Failed to check cached articles:', err)
    }

    // Action 2: Open live SSE stream for freshly scraped & synthesized articles
    const eventSource = new EventSource(`${API_BASE}/api/articles/sync/stream`)

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'article_ready' && payload.article) {
          setArticles((prev) =>
            prev.some((a) => a.id === payload.article.id)
              ? prev
              : [payload.article, ...prev]
          )
        } else if (payload.type === 'sync_complete' || payload.type === 'sync_error') {
          eventSource.close()
          setIsSyncing(false)
        }
      } catch (err) {
        console.error('Failed to parse SSE payload:', err)
      }
    }

    eventSource.onerror = (err) => {
      console.error('SSE stream error:', err)
      eventSource.close()
      setIsSyncing(false)
    }
  }

  // 3. Play or pause a specific article's audio stream
  const playArticleAudio = (article) => {
    if (currentTrack?.id === article.id) {
      if (isPlaying) {
        audioRef.current?.pause()
        setIsPlaying(false)
      } else {
        audioRef.current?.play()
        setIsPlaying(true)
      }
      return
    }

    // Set new track and auto-play
    setCurrentTrack(article)
    setIsPlaying(true)
    setAudioCurrentTime(0)
    setAudioDuration(0)
    setAudioProgress(0)
    if (audioRef.current) {
      const voiceParam = encodeURIComponent(aiSettings.tts_voice || 'af_sarah')
      audioRef.current.src = `${API_BASE}/api/articles/${article.id}/audio?voice=${voiceParam}`
      audioRef.current.playbackRate = playbackRate
      audioRef.current.play().catch((err) => console.log('Audio autoplay prevented:', err))
    }
  }

  // 4. Global Play Briefing (plays the lead article or top queue)
  const handleToggleHeroBriefing = () => {
    if (articles.length === 0) return
    const target = currentTrack || articles[0]
    playArticleAudio(target)
  }

  // 5. Audio time update handler
  const handleTimeUpdate = () => {
    if (!audioRef.current) return
    const cur = audioRef.current.currentTime || 0
    const rawDur = audioRef.current.duration
    const dur = Number.isFinite(rawDur) ? rawDur : 0
    setAudioCurrentTime(cur)
    setAudioDuration(dur)
    setAudioProgress(dur > 0 ? (cur / dur) * 100 : 0)
  }

  // 6. Audio scrub bar seek
  const handleSeek = (e) => {
    if (!audioRef.current || !audioDuration || !Number.isFinite(audioDuration)) return
    const rect = e.currentTarget.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const newFraction = Math.max(0, Math.min(1, clickX / rect.width))
    audioRef.current.currentTime = newFraction * audioDuration
  }

  // 7. Toggle playback speed (1.0x -> 1.05x -> 1.25x -> 1.5x)
  const cyclePlaybackRate = () => {
    const rates = [1.0, 1.05, 1.25, 1.5]
    const nextRate = rates[(rates.indexOf(playbackRate) + 1) % rates.length]
    setPlaybackRate(nextRate)
    if (audioRef.current) {
      audioRef.current.playbackRate = nextRate
    }
  }

  // 8. Fetch and toggle collapsible LangGraph historical context timeline
  const fetchArticleContext = async (articleId, refresh = false) => {
    if (contextLoading[articleId]) return
    setContextLoading((prev) => ({ ...prev, [articleId]: true }))
    setContextErrors((prev) => ({ ...prev, [articleId]: null }))
    try {
      const url = `${API_BASE}/api/articles/${articleId}/context${refresh ? '?refresh=true' : ''}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setContextById((prev) => ({ ...prev, [articleId]: data }))
    } catch (err) {
      console.error('Failed to fetch historical context:', err)
      setContextErrors((prev) => ({ ...prev, [articleId]: 'Could not trace story arc right now.' }))
    } finally {
      setContextLoading((prev) => ({ ...prev, [articleId]: false }))
    }
  }

  const toggleTimeline = (articleId) => {
    const willExpand = !expandedTimelines[articleId]
    setExpandedTimelines((prev) => ({
      ...prev,
      [articleId]: willExpand,
    }))

    if (willExpand && !contextById[articleId]) {
      const target = articles.find((a) => a.id === articleId)
      if (target?.historical_context) {
        try {
          const parsed = JSON.parse(target.historical_context)
          if (parsed && typeof parsed === 'object') {
            setContextById((prev) => ({ ...prev, [articleId]: parsed }))
            return
          }
        } catch {
          // Fall through to backend context generation
        }
      }
      fetchArticleContext(articleId)
    }
  }

  // 8b. Toggle analytical summary expansion
  const toggleSummary = (articleId) => {
    setExpandedSummaries((prev) => ({
      ...prev,
      [articleId]: !prev[articleId],
    }))
  }

  // Shared renderer for both Lead Story and Further Dispatches context drawers
  const renderContextPanel = (article) => {
    const ctx = contextById[article.id]
    const isCtxLoading = !!contextLoading[article.id]
    const ctxError = contextErrors[article.id]

    return (
      <div
        className="pt-5 border-t space-y-4 text-xs"
        style={{ borderColor: 'var(--border-hairline)' }}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div
            className="font-semibold uppercase tracking-widest"
            style={{ color: 'var(--accent-secondary)' }}
          >
            Story Arc &amp; Prior Precedents
          </div>
          <div className="flex items-center gap-2">
            {ctx && ctx.related_count > 0 && (
              <span
                className="px-2 py-0.5 rounded-full text-[11px] font-medium"
                style={{
                  backgroundColor: 'var(--tag-bg)',
                  color: 'var(--text-body)',
                }}
              >
                {ctx.related_count} linked {ctx.related_count === 1 ? 'story' : 'stories'}
              </span>
            )}
            <button
              onClick={() => fetchArticleContext(article.id, true)}
              disabled={isCtxLoading}
              className="px-2 py-0.5 rounded border text-[11px] cursor-pointer hover:opacity-80 disabled:opacity-50"
              style={{
                borderColor: 'var(--border-strong)',
                color: 'var(--text-muted)',
              }}
              title="Re-run LangGraph historical context agent"
            >
              {isCtxLoading ? 'Tracing...' : '↻ Refresh'}
            </button>
          </div>
        </div>

        {isCtxLoading && !ctx && (
          <div
            className="py-2 font-editorial text-sm italic animate-pulse"
            style={{ color: 'var(--text-muted)' }}
          >
            Tracing entities, archive precedents, and timeline with LangGraph...
          </div>
        )}

        {ctxError && !ctx && (
          <div className="flex items-center gap-3 text-xs" style={{ color: 'var(--text-muted)' }}>
            <span>{ctxError}</span>
            <button
              onClick={() => fetchArticleContext(article.id, true)}
              className="underline cursor-pointer font-semibold"
              style={{ color: 'var(--accent-primary)' }}
            >
              Retry
            </button>
          </div>
        )}

        {ctx && (
          <div className="space-y-4">
            {ctx.story_arc && (
              <p
                className="font-editorial text-sm leading-relaxed"
                style={{ color: 'var(--text-body)' }}
              >
                {ctx.story_arc}
              </p>
            )}

            {Array.isArray(ctx.entities) && ctx.entities.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {ctx.entities.map((ent, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-0.5 rounded-full text-[11px] font-medium"
                    style={{
                      backgroundColor: 'var(--tag-bg)',
                      color: 'var(--text-body)',
                    }}
                  >
                    {ent}
                  </span>
                ))}
              </div>
            )}

            {Array.isArray(ctx.milestones) && ctx.milestones.length > 0 && (
              <div
                className="border-l-2 pl-4 space-y-3.5"
                style={{ borderColor: 'var(--accent-secondary)' }}
              >
                {ctx.milestones.map((m, idx) => (
                  <div key={idx} className="space-y-1">
                    <div
                      className="text-[11px] font-bold uppercase tracking-wider"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {m.date || 'Milestone'}
                    </div>
                    <div className="text-sm font-semibold leading-snug" style={{ color: 'var(--text-main)' }}>
                      {m.source_url ? (
                        <a
                          href={m.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:underline"
                          style={{ color: 'var(--accent-primary)' }}
                        >
                          {m.headline} ↗
                        </a>
                      ) : (
                        m.headline
                      )}
                    </div>
                    <p
                      className="font-editorial text-xs md:text-sm leading-relaxed"
                      style={{ color: 'var(--text-body)' }}
                    >
                      {m.summary}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div
          className="pt-3 border-t space-y-1"
          style={{ borderColor: 'var(--border-hairline)' }}
        >
          <div
            className="text-[11px] font-bold uppercase tracking-wider"
            style={{ color: 'var(--text-muted)' }}
          >
            AI Broadcast Script
          </div>
          <p
            className="font-editorial text-xs md:text-sm italic leading-relaxed"
            style={{ color: 'var(--text-body)' }}
          >
            &ldquo;{article.audio_script || article.title}&rdquo;
          </p>
        </div>
      </div>
    )
  }

  // 9. Personalization feedback (persisted LinUCB thumbs up / down)
  const handleFeedback = async (articleId, vote) => {
    const nextVote = feedback[articleId] === vote ? null : vote
    setFeedback((prev) => ({
      ...prev,
      [articleId]: nextVote,
    }))
    try {
      const res = await fetch(`${API_BASE}/api/articles/${articleId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vote: nextVote }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.radar) {
          setRadarStats(data.radar)
        }
      }
    } catch (err) {
      console.error('Failed to persist LinUCB feedback:', err)
    }
  }

  const handleSortChange = (nextMode) => {
    if (nextMode === sortMode) return
    setSortMode(nextMode)
    fetchArticles(nextMode)
  }

  // Format seconds to "M:SS"
  const formatTime = (secs) => {
    if (!Number.isFinite(secs) || secs <= 0) return '0:00'
    const m = Math.floor(secs / 60)
    const s = Math.floor(secs % 60)
    return `${m}:${s < 10 ? '0' : ''}${s}`
  }

  const leadStory = articles[0]
  const furtherDispatches = articles.slice(1)

  const voiceName = getVoiceShortName(aiSettings.tts_voice)
  const activePaletteClass = isDark
    ? `${nightPalette} mode-dark`
    : `${dayPalette} mode-light`

  return (
    <div
      className={`${activePaletteClass} min-h-screen font-sans-ui transition-colors duration-300 relative pb-32`}
      style={{ backgroundColor: 'var(--bg-page)', color: 'var(--text-main)' }}
    >
      {/* Hidden HTML5 Audio Element streaming from FastAPI backend */}
      <audio
        ref={audioRef}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleTimeUpdate}
        onDurationChange={handleTimeUpdate}
        onCanPlay={handleTimeUpdate}
        onEnded={() => setIsPlaying(false)}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
      />

      {/* ============================================================== */}
      {/* 1. MASTHEAD / EDITORIAL HEADER */}
      {/* ============================================================== */}
      <header
        className="max-w-5xl mx-auto px-6 md:px-12 pt-8 pb-6 border-b"
        style={{ borderColor: 'var(--border-hairline)' }}
      >
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <div
              className="text-xs uppercase tracking-widest font-semibold mb-2"
              style={{ color: 'var(--accent-primary)' }}
            >
              Autonomous Daily News &amp; Audio Agent • Local Qwen + Kokoro
            </div>
            <h1 className="font-editorial text-3xl md:text-5xl font-bold tracking-tight">
              The Daily Dispatch
            </h1>
          </div>

          {/* Controls: Theme Toggle, Settings Drawer, & Refresh Feeds */}
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={handleThemeToggle}
              className="px-4 py-2 rounded-full text-xs font-semibold border transition hover:opacity-85 cursor-pointer shadow-sm"
              style={{
                borderColor: 'var(--border-strong)',
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-main)',
              }}
              title="Toggle Day / Night Edition"
            >
              {isDark ? '☀️ Day Edition' : '🌑 Night Edition'}
            </button>

            <button
              onClick={() => {
                setPaletteEditMode(isDark ? 'dark' : 'light')
                setIsSettingsOpen(true)
              }}
              className="px-4 py-2 rounded-full text-xs font-semibold border transition hover:opacity-85 cursor-pointer shadow-sm"
              style={{
                borderColor: 'var(--border-strong)',
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-main)',
              }}
              title="Open Theme & AI Settings"
            >
              ⚙ Settings
            </button>

            <button
              onClick={handleSync}
              disabled={isSyncing}
              className="px-4 py-2 rounded-full text-xs font-semibold tracking-wide border transition hover:opacity-90 cursor-pointer shadow-sm flex items-center gap-1.5"
              style={{
                borderColor: 'var(--border-strong)',
                backgroundColor: 'var(--accent-primary)',
                color: 'var(--accent-primary-fg)',
              }}
            >
              {isSyncing ? (
                <>
                  <span className="animate-spin inline-block">↻</span>
                  <span>Synthesizing...</span>
                </>
              ) : (
                <>
                  <span>↻</span>
                  <span>Refresh Feeds</span>
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* ============================================================== */}
      {/* 2. MAIN EDITORIAL CONTENT */}
      {/* ============================================================== */}
      <main className={`max-w-5xl mx-auto px-6 md:px-12 py-10 space-y-14 ${currentTrack ? 'pb-28' : ''}`}>
        {/* Loading Skeleton */}
        {isLoading && (
          <div className="py-24 text-center space-y-3">
            <div
              className="inline-block animate-spin text-2xl font-bold"
              style={{ color: 'var(--accent-primary)' }}
            >
              ↻
            </div>
            <p className="font-editorial text-lg italic" style={{ color: 'var(--text-muted)' }}>
              Gathering briefings and synthesizing local audio...
            </p>
          </div>
        )}

        {!isLoading && articles.length === 0 && (
          <div
            className="rounded-2xl p-10 border text-center space-y-4"
            style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-hairline)' }}
          >
            <h3 className="font-editorial text-2xl font-bold">No articles currently ingested</h3>
            <p className="text-sm max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
              Click &ldquo;Refresh Feeds&rdquo; above to fetch live RSS headlines, extract clean content, and generate AI takeaways.
            </p>
            <button
              onClick={handleSync}
              className="px-5 py-2.5 rounded-full text-xs font-bold uppercase tracking-wider"
              style={{ backgroundColor: 'var(--accent-primary)', color: 'var(--accent-primary-fg)' }}
            >
              Fetch &amp; Synthesize Now
            </button>
          </div>
        )}

        {!isLoading && articles.length > 0 && (
          <>
            {/* ============================================================ */}
            {/* MORNING AUDIO EDITION HERO CAPSULE */}
            {/* ============================================================ */}
            <section
              className="rounded-2xl p-7 md:p-9 border flex flex-col md:flex-row items-start md:items-center justify-between gap-8 shadow-sm transition"
              style={{ backgroundColor: 'var(--bg-hero)', borderColor: 'var(--border-strong)' }}
            >
              <div className="space-y-2.5 max-w-xl">
                <div
                  className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest"
                  style={{ color: 'var(--accent-secondary)' }}
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  <span>Audio Edition</span>
                  <span>•</span>
                  <span>Voice: {voiceName} (Kokoro)</span>
                  <span>•</span>
                  <span>{articles.length} Briefings Ingested</span>
                </div>
                <h2
                  className="font-editorial text-2xl md:text-3xl font-normal leading-snug"
                  style={{ color: 'var(--text-main)' }}
                >
                  Listen to today’s essential technology and science briefings.
                </h2>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                  Synthesized in RAM via local Qwen-2.5 with 0.00ms audio cache hits.
                </p>
              </div>

              <div className="flex items-center gap-5 self-stretch md:self-center shrink-0">
                {/* Audio Waveform Equalizer */}
                <div className={`flex items-end gap-1 h-7 ${!isPlaying ? 'opacity-40' : ''}`}>
                  <span
                    className={`w-1 rounded-full ${isPlaying ? 'animate-pulse h-6' : 'h-3'}`}
                    style={{ backgroundColor: 'var(--accent-primary)' }}
                  ></span>
                  <span
                    className={`w-1 rounded-full ${isPlaying ? 'animate-pulse h-4' : 'h-2'}`}
                    style={{ backgroundColor: 'var(--accent-primary)' }}
                  ></span>
                  <span
                    className={`w-1 rounded-full ${isPlaying ? 'animate-pulse h-7' : 'h-5'}`}
                    style={{ backgroundColor: 'var(--accent-primary)' }}
                  ></span>
                  <span
                    className={`w-1 rounded-full ${isPlaying ? 'animate-pulse h-5' : 'h-3'}`}
                    style={{ backgroundColor: 'var(--accent-primary)' }}
                  ></span>
                  <span
                    className={`w-1 rounded-full ${isPlaying ? 'animate-pulse h-3' : 'h-2'}`}
                    style={{ backgroundColor: 'var(--accent-primary)' }}
                  ></span>
                </div>

                <button
                  onClick={handleToggleHeroBriefing}
                  className="px-6 py-3 rounded-full text-xs font-semibold tracking-wider uppercase transition shadow cursor-pointer hover:opacity-90"
                  style={{
                    backgroundColor: 'var(--accent-primary)',
                    color: 'var(--accent-primary-fg)',
                  }}
                >
                  {isPlaying ? 'Pause Briefing' : 'Play Briefing'}
                </button>
              </div>
            </section>

            {/* ============================================================ */}
            {/* ASYMMETRICAL BENTO ROW: LEAD STORY + RADAR SIDEBAR */}
            {/* ============================================================ */}
            {leadStory && (
              <section className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
                {/* Lead Story Card (8 Columns) */}
                <article
                  className="lg:col-span-8 rounded-2xl p-7 md:p-9 border space-y-6 shadow-sm"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    borderColor: 'var(--border-hairline)',
                  }}
                >
                  <div className="flex items-center justify-between text-xs tracking-wide">
                    <div className="flex items-center gap-2.5">
                      <a
                        href={leadStory.url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-bold uppercase tracking-widest hover:underline cursor-pointer"
                        style={{ color: 'var(--accent-primary)' }}
                        title={`Open original story on ${getSourceName(leadStory.url)}`}
                      >
                        {getSourceName(leadStory.url)} ↗
                      </a>
                      <span style={{ color: 'var(--text-muted)' }}>•</span>
                      <span style={{ color: 'var(--text-muted)' }}>Lead Dispatch</span>
                    </div>
                    <span style={{ color: 'var(--text-muted)' }}>
                      {formatTimeAgo(leadStory.published_at)}
                    </span>
                  </div>

                  <h2
                    className="font-editorial text-2xl md:text-3xl font-bold leading-tight"
                    style={{ color: 'var(--text-main)' }}
                  >
                    {leadStory.title}
                  </h2>

                  {/* Analytical Deep Dive Preview with Fade & Read More */}
                  {leadStory.summary && (
                    <div className="pt-1">
                      <div
                        className={`relative font-editorial text-base md:text-lg leading-relaxed transition-all duration-300 ${
                          expandedSummaries[leadStory.id] ? '' : 'max-h-14 overflow-hidden'
                        }`}
                        style={{
                          color: expandedSummaries[leadStory.id]
                            ? 'var(--text-body)'
                            : 'var(--text-muted)',
                        }}
                      >
                        <p className="whitespace-pre-line leading-relaxed">
                          {leadStory.summary}
                        </p>
                        {!expandedSummaries[leadStory.id] && (
                          <div
                            className="pointer-events-none absolute inset-x-0 bottom-0 h-10"
                            style={{
                              background:
                                'linear-gradient(to bottom, transparent, var(--bg-surface))',
                            }}
                          />
                        )}
                      </div>
                      <button
                        onClick={() => toggleSummary(leadStory.id)}
                        className="mt-1 text-xs font-semibold cursor-pointer transition hover:underline flex items-center gap-1"
                        style={{ color: 'var(--accent-primary)' }}
                      >
                        {expandedSummaries[leadStory.id] ? 'Show less ↑' : 'Read more ↓'}
                      </button>
                    </div>
                  )}

                  {/* 3 Upright Numbered Takeaways */}
                  <div
                    className="pt-2 space-y-4 border-t"
                    style={{ borderColor: 'var(--border-hairline)' }}
                  >
                    <div
                      className="text-xs font-semibold uppercase tracking-widest"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      Executive Summary (Qwen 2.5)
                    </div>

                    <div className="space-y-4">
                      {parseTakeaways(leadStory.takeaways, leadStory.title).map((bullet, idx) => (
                        <div key={idx} className="flex gap-3.5 items-baseline">
                          <span
                            className="font-sans-ui text-xs font-bold tracking-wider shrink-0"
                            style={{ color: 'var(--accent-primary)' }}
                          >
                            0{idx + 1}
                          </span>
                          <p
                            className="font-editorial text-base leading-relaxed"
                            style={{ color: 'var(--text-body)' }}
                          >
                            {bullet}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Lead Story Footer Actions */}
                  <div
                    className="pt-4 border-t flex flex-wrap items-center justify-between gap-4 text-xs"
                    style={{ borderColor: 'var(--border-hairline)' }}
                  >
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => playArticleAudio(leadStory)}
                        className="px-4 py-2 rounded-full font-semibold transition cursor-pointer hover:opacity-90"
                        style={{
                          backgroundColor:
                            currentTrack?.id === leadStory.id && isPlaying
                              ? 'var(--accent-primary)'
                              : 'var(--tag-bg)',
                          color:
                            currentTrack?.id === leadStory.id && isPlaying
                              ? 'var(--accent-primary-fg)'
                              : 'var(--text-main)',
                        }}
                      >
                        {currentTrack?.id === leadStory.id && isPlaying
                          ? '⏸ Pause Audio'
                          : `▶ Listen (${voiceName})`}
                      </button>

                      <button
                        onClick={() => toggleTimeline(leadStory.id)}
                        className="px-4 py-2 rounded-full font-medium border transition cursor-pointer hover:opacity-85"
                        style={{
                          borderColor: 'var(--border-strong)',
                          color: 'var(--text-body)',
                        }}
                      >
                        Historical Context {expandedTimelines[leadStory.id] ? '▲' : '▼'}
                      </button>
                    </div>

                    <div className="flex items-center gap-4" style={{ color: 'var(--text-muted)' }}>
                      <button
                        onClick={() => handleFeedback(leadStory.id, 'up')}
                        className={`cursor-pointer hover:underline ${
                          feedback[leadStory.id] === 'up' ? 'font-bold text-emerald-600' : ''
                        }`}
                      >
                        {feedback[leadStory.id] === 'up' ? '✓ Relevant' : 'More like this'}
                      </button>
                      <span>•</span>
                      <button
                        onClick={() => handleFeedback(leadStory.id, 'down')}
                        className={`cursor-pointer hover:underline ${
                          feedback[leadStory.id] === 'down' ? 'font-bold text-rose-600' : ''
                        }`}
                      >
                        Less
                      </button>
                      <span>•</span>
                      <a
                        href={leadStory.url}
                        target="_blank"
                        rel="noreferrer"
                        className="font-semibold hover:underline"
                        style={{ color: 'var(--accent-primary)' }}
                      >
                        Original ↗
                      </a>
                    </div>
                  </div>

                  {/* Expandable Historical Context Timeline */}
                  {expandedTimelines[leadStory.id] && renderContextPanel(leadStory)}
                </article>

                {/* Sidebar Column: Personalization Radar + Architecture Note (4 Columns) */}
                <aside className="lg:col-span-4 space-y-6">
                  {/* Topic Radar */}
                  <div
                    className="rounded-2xl p-7 border space-y-5"
                    style={{
                      backgroundColor: 'var(--bg-surface)',
                      borderColor: 'var(--border-hairline)',
                    }}
                  >
                    <div className="space-y-1">
                      <div
                        className="text-xs font-bold uppercase tracking-widest"
                        style={{ color: 'var(--accent-ochre)' }}
                      >
                        Curated Profile
                      </div>
                      <h3
                        className="font-editorial text-lg font-bold"
                        style={{ color: 'var(--text-main)' }}
                      >
                        Autonomous Feed Radar
                      </h3>
                    </div>

                    <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
                      Local LinUCB bandit learns topic weights from Like (+1.0) &amp; Less (-0.5) signals:
                    </p>

                    <div className="space-y-3.5 pt-1">
                      {(radarStats?.topics || [
                        { label: 'AI & Local LLMs', affinity_pct: 50 },
                        { label: 'Cybersecurity & Systems', affinity_pct: 50 },
                        { label: 'Semiconductors & Hardware', affinity_pct: 50 },
                        { label: 'Startups & Tech Markets', affinity_pct: 50 },
                        { label: 'Science & Space', affinity_pct: 50 },
                      ]).map((topic, idx) => {
                        const barColors = [
                          'var(--accent-primary)',
                          'var(--accent-secondary)',
                          'var(--accent-ochre)',
                        ]
                        const barColor = barColors[idx % barColors.length]
                        return (
                          <div key={topic.label} className="space-y-1.5">
                            <div className="flex justify-between text-xs gap-2">
                              <span
                                className="font-medium truncate"
                                style={{ color: 'var(--text-body)' }}
                              >
                                {topic.label}
                              </span>
                              <span className="font-mono font-semibold shrink-0" style={{ color: barColor }}>
                                {topic.affinity_pct}%
                              </span>
                            </div>
                            <div
                              className="w-full h-1.5 rounded-full overflow-hidden"
                              style={{ backgroundColor: 'var(--bg-subtle)' }}
                            >
                              <div
                                className="h-full rounded-full transition-all duration-300"
                                style={{
                                  width: `${topic.affinity_pct}%`,
                                  backgroundColor: barColor,
                                }}
                              ></div>
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    <div
                      className="pt-3 border-t flex items-center justify-between text-[11px]"
                      style={{
                        borderColor: 'var(--border-hairline)',
                        color: 'var(--text-muted)',
                      }}
                    >
                      <span>
                        {radarStats
                          ? `${radarStats.total_likes} likes • ${radarStats.total_dislikes} dislikes`
                          : '0 likes • 0 dislikes'}
                      </span>
                      <span className="font-mono">
                        α = {radarStats ? Number(radarStats.alpha).toFixed(2) : Number(aiSettings.bandit_alpha).toFixed(2)}
                      </span>
                    </div>
                  </div>

                  {/* Architecture Note */}
                  <div
                    className="rounded-2xl p-7 border space-y-3"
                    style={{
                      backgroundColor: 'var(--bg-subtle)',
                      borderColor: 'var(--border-hairline)',
                    }}
                  >
                    <div
                      className="text-xs font-bold uppercase tracking-widest"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      On-Device Engine
                    </div>
                    <p
                      className="font-editorial text-sm italic leading-relaxed"
                      style={{ color: 'var(--text-body)' }}
                    >
                      &ldquo;All editorial takeaways, transcripts, and neural voices run 100% locally on your machine with zero external cloud dependencies.&rdquo;
                    </p>
                  </div>
                </aside>
              </section>
            )}

            {/* ============================================================ */}
            {/* FURTHER DISPATCHES (2-Column Grid) */}
            {/* ============================================================ */}
            {furtherDispatches.length > 0 && (
              <section
                className="space-y-8 pt-6 border-t"
                style={{ borderColor: 'var(--border-strong)' }}
              >
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-baseline gap-3">
                    <h3
                      className="font-editorial text-2xl font-bold"
                      style={{ color: 'var(--text-main)' }}
                    >
                      Further Dispatches
                    </h3>
                    <span
                      className="text-xs uppercase tracking-widest"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {furtherDispatches.length} Stories
                    </span>
                  </div>

                  {/* Sort Switcher: LinUCB Personalized vs Latest */}
                  <div
                    className="inline-flex rounded-full p-0.5 border text-xs font-semibold"
                    style={{
                      borderColor: 'var(--border-strong)',
                      backgroundColor: 'var(--bg-surface)',
                    }}
                  >
                    <button
                      onClick={() => handleSortChange('personalized')}
                      className="px-3.5 py-1.5 rounded-full cursor-pointer transition"
                      style={{
                        backgroundColor:
                          sortMode === 'personalized' ? 'var(--accent-primary)' : 'transparent',
                        color:
                          sortMode === 'personalized'
                            ? 'var(--accent-primary-fg)'
                            : 'var(--text-body)',
                      }}
                    >
                      ✦ For You (LinUCB)
                    </button>
                    <button
                      onClick={() => handleSortChange('latest')}
                      className="px-3.5 py-1.5 rounded-full cursor-pointer transition"
                      style={{
                        backgroundColor:
                          sortMode === 'latest' ? 'var(--accent-primary)' : 'transparent',
                        color:
                          sortMode === 'latest' ? 'var(--accent-primary-fg)' : 'var(--text-body)',
                      }}
                    >
                      🕒 Latest
                    </button>
                  </div>
                </div>

                {(() => {
                  const renderDispatchCard = (article) => {
                    const isCurrent = currentTrack?.id === article.id && isPlaying
                    const isExpanded = !!expandedTimelines[article.id]
                    const bullets = parseTakeaways(article.takeaways, article.title)

                    return (
                      <article
                        key={article.id}
                        data-dispatch-card-id={article.id}
                        className="rounded-2xl p-7 md:p-8 border flex flex-col justify-between space-y-6 shadow-sm transition hover:shadow-md"
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          borderColor: isCurrent
                            ? 'var(--accent-primary)'
                            : 'var(--border-hairline)',
                        }}
                      >
                        <div className="space-y-4">
                          <div className="flex items-center justify-between text-xs">
                            <a
                              href={article.url}
                              target="_blank"
                              rel="noreferrer"
                              className="font-bold uppercase tracking-widest hover:underline cursor-pointer"
                              style={{ color: 'var(--accent-secondary)' }}
                              title={`Open original story on ${getSourceName(article.url)}`}
                            >
                              {getSourceName(article.url)} ↗
                            </a>
                            <span style={{ color: 'var(--text-muted)' }}>
                              {formatTimeAgo(article.published_at)}
                            </span>
                          </div>

                          <h4
                            className="font-editorial text-xl md:text-2xl font-bold leading-snug"
                            style={{ color: 'var(--text-main)' }}
                          >
                            {article.title}
                          </h4>

                          {/* Analytical Deep Dive Preview with Fade & Read More */}
                          {article.summary && (
                            <div className="pt-1">
                              <div
                                className={`relative font-editorial text-sm md:text-base leading-relaxed transition-all duration-300 ${
                                  expandedSummaries[article.id] ? '' : 'max-h-12 overflow-hidden'
                                }`}
                                style={{
                                  color: expandedSummaries[article.id]
                                    ? 'var(--text-body)'
                                    : 'var(--text-muted)',
                                }}
                              >
                                <p className="whitespace-pre-line leading-relaxed">
                                  {article.summary}
                                </p>
                                {!expandedSummaries[article.id] && (
                                  <div
                                    className="pointer-events-none absolute inset-x-0 bottom-0 h-8"
                                    style={{
                                      background:
                                        'linear-gradient(to bottom, transparent, var(--bg-surface))',
                                    }}
                                  />
                                )}
                              </div>
                              <button
                                onClick={() => toggleSummary(article.id)}
                                className="mt-1 text-xs font-semibold cursor-pointer transition hover:underline flex items-center gap-1"
                                style={{ color: 'var(--accent-primary)' }}
                              >
                                {expandedSummaries[article.id] ? 'Show less ↑' : 'Read more ↓'}
                              </button>
                            </div>
                          )}

                          <ul
                            className="space-y-3 pt-2 border-t font-editorial text-base leading-relaxed"
                            style={{
                              borderColor: 'var(--border-hairline)',
                              color: 'var(--text-body)',
                            }}
                          >
                            {bullets.map((b, i) => (
                              <li key={i} className="flex gap-2 items-baseline">
                                <span style={{ color: 'var(--accent-primary)' }}>•</span>
                                <span>{b}</span>
                              </li>
                            ))}
                          </ul>
                        </div>

                        <div
                          className="pt-4 border-t flex items-center justify-between text-xs"
                          style={{ borderColor: 'var(--border-hairline)' }}
                        >
                          <div className="flex items-center gap-2.5">
                            <button
                              onClick={() => playArticleAudio(article)}
                              className="px-4 py-2 rounded-full font-semibold transition cursor-pointer hover:opacity-90"
                              style={{
                                backgroundColor: isCurrent
                                  ? 'var(--accent-primary)'
                                  : 'var(--tag-bg)',
                                color: isCurrent
                                  ? 'var(--accent-primary-fg)'
                                  : 'var(--text-main)',
                              }}
                            >
                              {isCurrent ? '⏸ Pause' : `▶ Listen (${voiceName})`}
                            </button>
                            <button
                              onClick={() => toggleTimeline(article.id)}
                              aria-expanded={isExpanded}
                              className="px-3.5 py-2 rounded-full border cursor-pointer hover:opacity-85"
                              style={{
                                borderColor: 'var(--border-strong)',
                                color: 'var(--text-body)',
                              }}
                            >
                              Context {isExpanded ? '▲' : '▼'}
                            </button>
                          </div>

                          <div
                            className="flex items-center gap-3"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            <button
                              onClick={() => handleFeedback(article.id, 'up')}
                              className={`cursor-pointer hover:underline ${
                                feedback[article.id] === 'up'
                                  ? 'font-bold text-emerald-600'
                                  : ''
                              }`}
                              title="Tune personalization bandit: recommend more stories like this"
                            >
                              {feedback[article.id] === 'up' ? '✓ Relevant' : 'More like this'}
                            </button>
                            <span>•</span>
                            <button
                              onClick={() => handleFeedback(article.id, 'down')}
                              className={`cursor-pointer hover:underline ${
                                feedback[article.id] === 'down' ? 'font-bold text-rose-600' : ''
                              }`}
                              title="Downweight similar topics in LinUCB bandit"
                            >
                              {feedback[article.id] === 'down' ? '✕ Less' : 'Less'}
                            </button>
                            <span>•</span>
                            <a
                              href={article.url}
                              target="_blank"
                              rel="noreferrer"
                              className="font-semibold hover:underline"
                              style={{ color: 'var(--accent-primary)' }}
                            >
                              Read ↗
                            </a>
                          </div>
                        </div>

                        {isExpanded && renderContextPanel(article)}
                      </article>
                    )
                  }

                  const leftCol = []
                  const rightCol = []
                  let leftHeight = 0
                  let rightHeight = 0

                  for (const article of furtherDispatches) {
                    const bullets = parseTakeaways(article.takeaways, article.title)
                    const titleLines = Math.ceil((article.title?.length || 32) / 32)
                    const bulletsHeight = bullets.reduce(
                      (sum, b) => sum + Math.ceil((b?.length || 44) / 44) * 26 + 12,
                      0
                    )
                    const estHeight =
                      250 +
                      titleLines * 30 +
                      (article.summary ? 84 : 0) +
                      bulletsHeight
                    const cardSpan = (cardHeights[article.id] || estHeight) + 32

                    if (leftHeight <= rightHeight) {
                      leftCol.push(article)
                      leftHeight += cardSpan
                    } else {
                      rightCol.push(article)
                      rightHeight += cardSpan
                    }
                  }

                  return (
                    <>
                      {/* Mobile: single-column chronological stack */}
                      <div className="flex flex-col gap-8 md:hidden">
                        {furtherDispatches.map(renderDispatchCard)}
                      </div>

                      {/* Desktop: 2-column balanced masonry */}
                      <div className="hidden md:grid md:grid-cols-2 gap-8 items-start">
                        <div className="flex flex-col gap-8">
                          {leftCol.map(renderDispatchCard)}
                        </div>
                        <div className="flex flex-col gap-8">
                          {rightCol.map(renderDispatchCard)}
                        </div>
                      </div>
                    </>
                  )
                })()}
              </section>
            )}
          </>
        )}
      </main>

      {/* ============================================================== */}
      {/* 3. PERSISTENT AUDIO DOCK BAR (Pinned Bottom) */}
      {/* ============================================================== */}
      {currentTrack && (
        <footer
          className="fixed bottom-0 inset-x-0 border-t backdrop-blur-md px-6 md:px-12 py-4 flex flex-wrap items-center justify-between gap-4 z-50 shadow-2xl transition-all"
          style={{
            backgroundColor: 'var(--bg-dock)',
            borderColor: 'var(--border-strong)',
          }}
        >
          <div className="flex items-center gap-4 max-w-xl">
            <button
              onClick={() => playArticleAudio(currentTrack)}
              className="w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold transition shadow-sm cursor-pointer hover:scale-105 shrink-0"
              style={{
                backgroundColor: 'var(--accent-primary)',
                color: 'var(--accent-primary-fg)',
              }}
            >
              {isPlaying ? '⏸' : '▶'}
            </button>
            <div className="truncate">
              <div className="flex items-center gap-2 text-xs truncate">
                <span
                  className="font-bold uppercase tracking-widest shrink-0"
                  style={{ color: 'var(--accent-primary)' }}
                >
                  {getSourceName(currentTrack.url)}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>•</span>
                <span
                  className="font-editorial font-bold text-sm truncate"
                  style={{ color: 'var(--text-main)' }}
                >
                  {currentTrack.title}
                </span>
              </div>
              <p
                className="font-editorial italic text-xs mt-0.5 truncate max-w-lg"
                style={{ color: 'var(--text-muted)' }}
              >
                &ldquo;{currentTrack.audio_script || currentTrack.title}&rdquo;
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 w-full sm:w-auto justify-between sm:justify-end">
            {/* Time Scrub Bar */}
            <div
              className="flex items-center gap-3 w-48 text-xs cursor-pointer select-none"
              style={{ color: 'var(--text-muted)' }}
              onClick={handleSeek}
            >
              <span className="w-8 text-right">{formatTime(audioCurrentTime)}</span>
              <div
                className="flex-1 h-1.5 rounded-full overflow-hidden"
                style={{ backgroundColor: 'var(--border-strong)' }}
              >
                <div
                  className="h-full rounded-full transition-all duration-150"
                  style={{
                    width: `${audioProgress}%`,
                    backgroundColor: 'var(--accent-primary)',
                  }}
                ></div>
              </div>
              <span className="w-8">{formatTime(audioDuration)}</span>
            </div>

            {/* Playback Rate Selector (1.0x, 1.05x, 1.25x) */}
            <button
              onClick={cyclePlaybackRate}
              className="px-2.5 py-1 rounded-full text-xs font-semibold border cursor-pointer hover:opacity-80 transition"
              style={{
                borderColor: 'var(--border-strong)',
                color: 'var(--text-body)',
              }}
              title="Change playback speed"
            >
              {playbackRate}x
            </button>
          </div>
        </footer>
      )}

      {/* ============================================================== */}
      {/* 4. SETTINGS SLIDE-OVER PANEL (Palettes + AI / TTS Parameters) */}
      {/* ============================================================== */}
      {isSettingsOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/50 backdrop-blur-xs"
            onClick={() => setIsSettingsOpen(false)}
          />

          {/* Drawer */}
          <aside
            className="relative z-10 w-full max-w-md h-full overflow-y-auto border-l p-6 md:p-7 space-y-7 shadow-2xl"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-strong)',
              color: 'var(--text-main)',
            }}
          >
            <div
              className="flex items-center justify-between pb-4 border-b"
              style={{ borderColor: 'var(--border-hairline)' }}
            >
              <div>
                <h2 className="font-editorial text-2xl font-bold">Dispatch Settings</h2>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  Customize editorial palettes and local AI inference behavior
                </p>
              </div>
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="w-8 h-8 rounded-full border text-sm font-bold cursor-pointer hover:opacity-80"
                style={{
                  borderColor: 'var(--border-strong)',
                  color: 'var(--text-body)',
                }}
                aria-label="Close settings"
              >
                ✕
              </button>
            </div>

            {/* Section 1: Editorial Color Palettes */}
            <section className="space-y-4">
              <div className="flex items-center justify-between gap-2">
                <h3
                  className="text-xs font-bold uppercase tracking-widest"
                  style={{ color: 'var(--accent-secondary)' }}
                >
                  Color Palette
                </h3>
                <div
                  className="inline-flex rounded-full p-0.5 border text-[11px] font-semibold"
                  style={{
                    borderColor: 'var(--border-strong)',
                    backgroundColor: 'var(--bg-subtle)',
                  }}
                >
                  <button
                    onClick={() => setPaletteEditMode('light')}
                    className="px-3 py-1 rounded-full cursor-pointer transition"
                    style={{
                      backgroundColor:
                        paletteEditMode === 'light' ? 'var(--accent-primary)' : 'transparent',
                      color:
                        paletteEditMode === 'light'
                          ? 'var(--accent-primary-fg)'
                          : 'var(--text-body)',
                    }}
                  >
                    ☀️ Day
                  </button>
                  <button
                    onClick={() => setPaletteEditMode('dark')}
                    className="px-3 py-1 rounded-full cursor-pointer transition"
                    style={{
                      backgroundColor:
                        paletteEditMode === 'dark' ? 'var(--accent-primary)' : 'transparent',
                      color:
                        paletteEditMode === 'dark'
                          ? 'var(--accent-primary-fg)'
                          : 'var(--text-body)',
                    }}
                  >
                    🌑 Night
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                {PALETTES.map((p) => {
                  const selectedId = paletteEditMode === 'dark' ? nightPalette : dayPalette
                  const isSelected = selectedId === p.id
                  const swatches = paletteEditMode === 'dark' ? p.dark : p.light
                  return (
                    <button
                      key={p.id}
                      onClick={() => selectPalette(p.id)}
                      className="text-left p-3 rounded-xl border transition cursor-pointer hover:opacity-90 space-y-1.5"
                      style={{
                        backgroundColor: isSelected ? 'var(--tag-bg)' : 'var(--bg-page)',
                        borderColor: isSelected
                          ? 'var(--accent-primary)'
                          : 'var(--border-hairline)',
                      }}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-xs font-bold truncate">{p.name}</span>
                        <div className="flex items-center gap-1 shrink-0">
                          {swatches.map((hex, i) => (
                            <span
                              key={i}
                              className="w-3 h-3 rounded-full border"
                              style={{
                                backgroundColor: hex,
                                borderColor: 'var(--border-strong)',
                              }}
                            />
                          ))}
                        </div>
                      </div>
                      <div className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>
                        {p.desc}
                      </div>
                    </button>
                  )
                })}
              </div>
            </section>

            {/* Section 2: AI & Audio Parameters */}
            <section
              className="space-y-4 pt-5 border-t"
              style={{ borderColor: 'var(--border-hairline)' }}
            >
              <div className="flex items-center justify-between">
                <h3
                  className="text-xs font-bold uppercase tracking-widest"
                  style={{ color: 'var(--accent-secondary)' }}
                >
                  AI &amp; Retrieval Parameters
                </h3>
                {settingsStatus && (
                  <span
                    className="text-xs font-semibold"
                    style={{ color: 'var(--accent-primary)' }}
                  >
                    {settingsStatus}
                  </span>
                )}
              </div>

              <div className="space-y-4">
                {AI_SLIDERS.map((ctrl) => (
                  <div key={ctrl.key} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <label className="font-semibold" style={{ color: 'var(--text-main)' }}>
                        {ctrl.label}
                      </label>
                      <span
                        className="font-mono font-bold"
                        style={{ color: 'var(--accent-primary)' }}
                      >
                        {ctrl.format(aiSettings[ctrl.key])}
                      </span>
                    </div>
                    <input
                      type="range"
                      min={ctrl.min}
                      max={ctrl.max}
                      step={ctrl.step}
                      value={aiSettings[ctrl.key]}
                      onChange={(e) => {
                        const val = Number.isInteger(ctrl.step)
                          ? parseInt(e.target.value, 10)
                          : parseFloat(e.target.value)
                        setAiSettings((prev) => ({ ...prev, [ctrl.key]: val }))
                      }}
                      className="w-full cursor-pointer"
                      style={{ accentColor: 'var(--accent-primary)' }}
                    />
                    <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      {ctrl.hint}
                    </p>
                  </div>
                ))}

                {/* Kokoro Voice Selector */}
                <div className="space-y-1.5">
                  <label
                    className="block text-xs font-semibold"
                    style={{ color: 'var(--text-main)' }}
                  >
                    Kokoro TTS Narrator Voice
                  </label>
                  <select
                    value={aiSettings.tts_voice}
                    onChange={(e) =>
                      setAiSettings((prev) => ({ ...prev, tts_voice: e.target.value }))
                    }
                    className="w-full px-3 py-2 rounded-lg border text-xs font-medium cursor-pointer"
                    style={{
                      backgroundColor: 'var(--bg-page)',
                      borderColor: 'var(--border-strong)',
                      color: 'var(--text-main)',
                    }}
                  >
                    {VOICE_OPTIONS.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div
                className="pt-4 flex items-center justify-between gap-3 border-t"
                style={{ borderColor: 'var(--border-hairline)' }}
              >
                <button
                  onClick={resetAiSettings}
                  disabled={isSavingSettings}
                  className="px-3.5 py-2 rounded-full text-xs font-semibold border cursor-pointer hover:opacity-85 disabled:opacity-50"
                  style={{
                    borderColor: 'var(--border-strong)',
                    color: 'var(--text-body)',
                  }}
                >
                  Reset Defaults
                </button>
                <button
                  onClick={() => saveAiSettings()}
                  disabled={isSavingSettings}
                  className="px-5 py-2 rounded-full text-xs font-bold cursor-pointer hover:opacity-90 disabled:opacity-50 shadow-sm"
                  style={{
                    backgroundColor: 'var(--accent-primary)',
                    color: 'var(--accent-primary-fg)',
                  }}
                >
                  {isSavingSettings ? 'Saving...' : 'Save AI Settings'}
                </button>
              </div>
            </section>

            {/* Section 3: Custom RSS Feed Sources */}
            <section
              className="space-y-4 pt-5 border-t"
              style={{ borderColor: 'var(--border-hairline)' }}
            >
              <div className="flex items-center justify-between gap-2">
                <h3
                  className="text-xs font-bold uppercase tracking-widest"
                  style={{ color: 'var(--accent-secondary)' }}
                >
                  RSS Feed Sources
                </h3>
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {feeds.filter((f) => f.enabled).length} / {feeds.length} active
                </span>
              </div>

              <div className="max-h-52 overflow-y-auto space-y-2 pr-1">
                {feeds.length === 0 ? (
                  <p className="text-xs italic" style={{ color: 'var(--text-muted)' }}>
                    No feeds loaded yet. Connect backend or add a custom RSS feed below.
                  </p>
                ) : (
                  feeds.map((feed) => (
                    <div
                      key={feed.id}
                      className="flex items-center justify-between gap-2.5 p-2.5 rounded-xl border"
                      style={{
                        backgroundColor: 'var(--bg-page)',
                        borderColor: 'var(--border-hairline)',
                        opacity: feed.enabled ? 1 : 0.6,
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => handleToggleFeed(feed.id, !feed.enabled)}
                        className="px-2.5 py-1 rounded-full text-[11px] font-bold shrink-0 cursor-pointer transition"
                        style={{
                          backgroundColor: feed.enabled
                            ? 'var(--accent-primary)'
                            : 'var(--tag-bg)',
                          color: feed.enabled
                            ? 'var(--accent-primary-fg)'
                            : 'var(--text-muted)',
                        }}
                        title={feed.enabled ? 'Pause this feed' : 'Enable this feed'}
                      >
                        {feed.enabled ? 'On' : 'Paused'}
                      </button>

                      <div className="min-w-0 flex-1">
                        <div className="text-xs font-semibold truncate">{feed.name}</div>
                        <div
                          className="text-[11px] truncate"
                          style={{ color: 'var(--text-muted)' }}
                          title={feed.url}
                        >
                          {feed.url}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleDeleteFeed(feed.id)}
                        className="w-6 h-6 rounded-full text-xs cursor-pointer hover:opacity-75 shrink-0"
                        style={{ color: 'var(--text-muted)' }}
                        title="Remove RSS feed"
                        aria-label={`Remove ${feed.name}`}
                      >
                        ✕
                      </button>
                    </div>
                  ))
                )}
              </div>

              <form onSubmit={handleAddFeed} className="space-y-2 pt-1">
                <input
                  type="url"
                  value={newFeedUrl}
                  onChange={(e) => setNewFeedUrl(e.target.value)}
                  placeholder="https://example.com/rss.xml"
                  className="w-full px-3 py-2 rounded-lg border text-xs"
                  style={{
                    backgroundColor: 'var(--bg-page)',
                    borderColor: 'var(--border-strong)',
                    color: 'var(--text-main)',
                  }}
                />
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={newFeedName}
                    onChange={(e) => setNewFeedName(e.target.value)}
                    placeholder="Display name (optional)"
                    className="flex-1 px-3 py-2 rounded-lg border text-xs"
                    style={{
                      backgroundColor: 'var(--bg-page)',
                      borderColor: 'var(--border-strong)',
                      color: 'var(--text-main)',
                    }}
                  />
                  <button
                    type="submit"
                    disabled={isAddingFeed}
                    className="px-4 py-2 rounded-lg text-xs font-bold cursor-pointer hover:opacity-90 disabled:opacity-50 shrink-0"
                    style={{
                      backgroundColor: 'var(--accent-secondary)',
                      color: '#FFFFFF',
                    }}
                  >
                    {isAddingFeed ? 'Adding...' : '+ Add'}
                  </button>
                </div>
                {feedError && (
                  <p className="text-[11px] font-medium text-rose-500">{feedError}</p>
                )}
              </form>
            </section>
          </aside>
        </div>
      )}
    </div>
  )
}
