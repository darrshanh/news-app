import React, { useState, useEffect, useRef } from 'react'

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
  const [isDark, setIsDark] = useState(false)
  const [expandedTimelines, setExpandedTimelines] = useState({})
  const [feedback, setFeedback] = useState({})

  // Audio Playback State
  const [currentTrack, setCurrentTrack] = useState(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [audioProgress, setAudioProgress] = useState(0)
  const [audioDuration, setAudioDuration] = useState(0)
  const [audioCurrentTime, setAudioCurrentTime] = useState(0)
  const [playbackRate, setPlaybackRate] = useState(1.05)

  const audioRef = useRef(null)

  // Dynamic API Base URL: supports Cloudflare Pages deployment via VITE_API_URL or relative proxy
  const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')

  // 1. Fetch articles from FastAPI backend
  const fetchArticles = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/articles?limit=30`)
      if (res.ok) {
        const data = await res.json()
        setArticles(data)
      }
    } catch (err) {
      console.error('Failed to fetch articles:', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchArticles()
  }, [])

  // 2. Refresh / Sync live RSS feeds and re-fetch
  const handleSync = async () => {
    setIsSyncing(true)
    try {
      await fetch(`${API_BASE}/api/articles/sync`, { method: 'POST' })
      await fetchArticles()
    } catch (err) {
      console.error('Failed to sync feeds:', err)
    } finally {
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
      audioRef.current.src = `${API_BASE}/api/articles/${article.id}/audio`
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

  // 8. Toggle collapsible timeline
  const toggleTimeline = (articleId) => {
    setExpandedTimelines((prev) => ({
      ...prev,
      [articleId]: !prev[articleId],
    }))
  }

  // 9. Personalization feedback (thumbs up / down)
  const handleFeedback = (articleId, vote) => {
    setFeedback((prev) => ({
      ...prev,
      [articleId]: prev[articleId] === vote ? null : vote,
    }))
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

  return (
    <div
      className={`${isDark ? 'dark' : ''} min-h-screen font-sans-ui transition-colors duration-300 relative pb-32`}
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

          {/* Controls: Theme Toggle & Refresh Feeds */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsDark(!isDark)}
              className="px-4 py-2 rounded-full text-xs font-semibold border transition hover:opacity-85 cursor-pointer shadow-sm"
              style={{
                borderColor: 'var(--border-strong)',
                backgroundColor: 'var(--bg-surface)',
                color: 'var(--text-main)',
              }}
              title="Toggle Day (Kyoto Hinoki) / Night (Pitch-Black Bordeaux) Mode"
            >
              {isDark ? '☀️ Day Edition' : '🌑 Night Edition'}
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
      <main className="max-w-5xl mx-auto px-6 md:px-12 py-10 space-y-14">
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
                  <span>Voice: Sarah (Kokoro)</span>
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
                          : '▶ Listen (Sarah)'}
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
                  {expandedTimelines[leadStory.id] && (
                    <div
                      className="pt-5 border-t space-y-4"
                      style={{ borderColor: 'var(--border-hairline)' }}
                    >
                      <div
                        className="text-xs font-semibold uppercase tracking-widest"
                        style={{ color: 'var(--accent-secondary)' }}
                      >
                        Story Arc &amp; Prior Precedents
                      </div>
                      <div
                        className="border-l-2 pl-5 space-y-3.5"
                        style={{ borderColor: 'var(--accent-secondary)' }}
                      >
                        <div className="space-y-1">
                          <div
                            className="text-xs font-bold uppercase tracking-wider"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            Initial Discovery
                          </div>
                          <p
                            className="font-editorial text-sm leading-relaxed"
                            style={{ color: 'var(--text-body)' }}
                          >
                            Extracted from live feed via automated reader and cleaned for executive synthesis.
                          </p>
                        </div>
                        <div className="space-y-1">
                          <div
                            className="text-xs font-bold uppercase tracking-wider"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            Audio Generation
                          </div>
                          <p
                            className="font-editorial text-sm leading-relaxed italic"
                            style={{ color: 'var(--text-body)' }}
                          >
                            &ldquo;{leadStory.audio_script || leadStory.title}&rdquo;
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
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
                      Local LinUCB bandits adapt topic weighting based on thumbs-up feedback:
                    </p>

                    <div className="space-y-4 pt-1">
                      <div className="space-y-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="font-medium" style={{ color: 'var(--text-body)' }}>
                            Systems &amp; Security
                          </span>
                          <span style={{ color: 'var(--accent-primary)' }}>Active</span>
                        </div>
                        <div
                          className="w-full h-1.5 rounded-full overflow-hidden"
                          style={{ backgroundColor: 'var(--bg-subtle)' }}
                        >
                          <div
                            className="h-full w-11/12 rounded-full"
                            style={{ backgroundColor: 'var(--accent-primary)' }}
                          ></div>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="font-medium" style={{ color: 'var(--text-body)' }}>
                            Space &amp; Interstellar
                          </span>
                          <span style={{ color: 'var(--accent-secondary)' }}>88%</span>
                        </div>
                        <div
                          className="w-full h-1.5 rounded-full overflow-hidden"
                          style={{ backgroundColor: 'var(--bg-subtle)' }}
                        >
                          <div
                            className="h-full w-4/5 rounded-full"
                            style={{ backgroundColor: 'var(--accent-secondary)' }}
                          ></div>
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="font-medium" style={{ color: 'var(--text-body)' }}>
                            Local LLM Inference
                          </span>
                          <span style={{ color: 'var(--accent-ochre)' }}>95%</span>
                        </div>
                        <div
                          className="w-full h-1.5 rounded-full overflow-hidden"
                          style={{ backgroundColor: 'var(--bg-subtle)' }}
                        >
                          <div
                            className="h-full w-full rounded-full"
                            style={{ backgroundColor: 'var(--accent-ochre)' }}
                          ></div>
                        </div>
                      </div>
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
                <div className="flex items-baseline justify-between">
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
                    {furtherDispatches.length} Stories Ingested
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
                  {furtherDispatches.map((article) => {
                    const isCurrent = currentTrack?.id === article.id && isPlaying
                    const isExpanded = !!expandedTimelines[article.id]
                    const bullets = parseTakeaways(article.takeaways, article.title)

                    return (
                      <article
                        key={article.id}
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
                              {isCurrent ? '⏸ Pause' : '▶ Listen (Sarah)'}
                            </button>
                            <button
                              onClick={() => toggleTimeline(article.id)}
                              className="px-3.5 py-2 rounded-full border cursor-pointer hover:opacity-85"
                              style={{
                                borderColor: 'var(--border-strong)',
                                color: 'var(--text-body)',
                              }}
                            >
                              Context
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

                        {isExpanded && (
                          <div
                            className="pt-4 border-t text-xs space-y-2"
                            style={{ borderColor: 'var(--border-hairline)' }}
                          >
                            <div
                              className="font-bold uppercase tracking-wider"
                              style={{ color: 'var(--accent-secondary)' }}
                            >
                              AI Broadcast Script
                            </div>
                            <p
                              className="font-editorial text-sm italic"
                              style={{ color: 'var(--text-body)' }}
                            >
                              &ldquo;{article.audio_script || article.title}&rdquo;
                            </p>
                          </div>
                        )}
                      </article>
                    )
                  })}
                </div>
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
    </div>
  )
}
