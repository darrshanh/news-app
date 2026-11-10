# Autonomous Daily News & Timeline Agent: Project Plan

## 1. Executive Summary & Core Objectives

This project builds an autonomous, self-hosted personal news intelligence platform designed for daily lifestyle optimization. Rather than acting as a simple RSS reader or basic LLM prompt wrapper, the application functions as a proactive, stateful agentic system that gathers, synthesizes, cross-checks, and surfaces news tailored to your evolving interests.

### Primary Capabilities
1. **Adaptive Multi-Modal Consumption:** Scannable text summaries (3-bullet atomic context) with on-demand, sub-second neural audio generation (via local CPU-friendly TTS).
2. **Retrospective Horizon Stitching:** On-demand construction of chronological event graphs (timelines) tracing the historical precedents leading up to any specific current event.
3. **Sample-Efficient Preference Learning:** A recommendation feedback loop based on contextual multi-armed bandits ($\text{LinUCB}$) that adapts dynamically to Likes and Dislikes without requiring massive training datasets.
4. **Deterministic Calendar & Notification Automation:** Extraction of verifiable deadlines, conference dates, and milestones into calendar web intents and instant mobile notifications.

---

## 2. Tech Stack Specification

The application uses a decoupled client-server architecture. The backend manages all heavy web scraping, vector math, LLM agent loops, and neural audio synthesis, while the frontend functions as a responsive Progressive Web App (PWA) compatible with desktop browsers and mobile devices.

| Layer | Technology | Justification & Role |
| :--- | :--- | :--- |
| **Backend Framework** | **Python 3.11+ / FastAPI** | High-performance asynchronous runtime; native support for streaming binary audio buffers without saving intermediate `.mp3` files to disk. |
| **Task Scheduling** | **APScheduler** | In-process background scheduler for autonomous morning feed crawls and topic tracking. |
| **Extraction & Ingestion** | **Trafilatura + Feedparser** | Robust, boilerplate-free web body extraction that strips navigation bars, ads, and paywall banners from raw HTML. |
| **Language Models** | **Local Ollama (Qwen 2.5 3B/7B) or Gemini API** | Fast, structured JSON extraction for entities, timelines, and scannable summaries. |
| **Neural TTS** | **Kokoro-82M (via `kokoro-onnx`)** | 82-million parameter open-weight TTS engine; runs on CPU with a Real-Time Factor (RTF) $< 0.2$ for instantaneous audio synthesis. |
| **Database & Vectors** | **SQLite + `sqlite-vec` (WAL Mode)** | Zero-maintenance single-file storage for article caches, user feedback matrices, and semantic embeddings. |
| **Frontend Shell** | **Vite + React (Tailwind CSS)** | Clean, responsive card deck layout with native HTML5 audio binding and touch-friendly swipe actions. |
| **PWA Layer** | **Web App Manifest + Service Worker** | Enables "Add to Home Screen" on Android for a full-screen, native-feeling mobile experience. |
| **Push Notifications** | **ntfy.sh / Telegram Bot API** | Zero-configuration, lightweight push notification delivery directly to mobile lock screens. |
| **Calendar Sync** | **RFC 5545 Web Intents & `.ics`** | Programmatic URL generation pre-populating Google Calendar or native device calendars with zero OAuth setup. |

---

## 3. System Architecture & Data Flow

The architecture operates via a decoupled multi-agent loop with on-demand client evaluation paths.

```
                      [ External Web Sources ]
               (RSS Feeds, Targeted Conference Sites)
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                     1. SCOUT & INGESTION AGENT                  │
 │   - Scheduled morning polling via APScheduler                   │
 │   - Trafilatura extracts clean body markdown                   │
 │   - Embedding generation (sentence-transformers / all-MiniLM)   │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │               2. CONTEXTUAL BANDIT RANKER (LinUCB)              │
 │   - Computes upper confidence bounds against user context       │
 │   - Filters out redundant or low-interest stories               │
 └────────────────────────────────┬────────────────────────────────┘
                                  │
                                  ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                  3. EDITORIAL SYNTHESIS AGENT                   │
 │   - Distills 3-bullet core takeaways                            │
 │   - Extracts structured dates/deadlines into JSON schema        │
 └─────────────────┬─────────────────────────────┬─────────────────┘
                   │                             │
                   ▼                             ▼
       [ Auto Alert Trigger ]          [ SQLite Vector Store ]
       (ntfy.sh / Telegram push)                 │
                                                 │ Serves REST / SSE
                                                 ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │                   4. FRONTEND INTERACTION (PWA)                 │
 │   - News Feed Cards (Digest bullets + citations)                │
 │   - User Actions:                                               │
 │       * "Like / Dislike"  ──► Updates LinUCB covariance matrix  │
 │       * "Add Event"       ──► Launches Google Calendar intent   │
 └─────────────────┬─────────────────────────────┬─────────────────┘
                   │                             │
       "Listen" Click              "Trace Timeline" Click
                   │                             │
                   ▼                             ▼
 ┌───────────────────────────┐ ┌───────────────────────────────────┐
 │    KOKORO TTS STREAMER    │ │    RETROSPECTIVE TIMELINE AGENT   │
 │ - Generates WAV in RAM    │ │ - Extracts historical entities    │
 │ - Streams chunked audio   │ │ - Queries retrospective news API  │
 └───────────────────────────┘ │ - Returns chronological DAG JSON  │
                               └───────────────────────────────────┘
```

---

## 4. Theoretical & Practical Concepts to Learn

### A. Contextual Multi-Armed Bandits ($\text{LinUCB}$)
Instead of deep reinforcement learning (which fails in single-user setups due to data starvation), contextual bandits balance **Exploration** (testing adjacent topics) with **Exploitation** (recommending confirmed interests).

* **Mathematical Foundation:** For each article $a$ with $d$-dimensional embedding feature vector $\mathbf{x}_{t,a} \in \mathbb{R}^d$, the expected reward (interest level) is modeled as a linear payoff:
  $$\mathbb{E}[r_{t,a} \mid \mathbf{x}_{t,a}] = \mathbf{x}_{t,a}^T \boldsymbol{\theta}^*$$
  where $\boldsymbol{\theta}^* \in \mathbb{R}^d$ is an unknown parameter vector representing user preferences.

* **Ridge Regression Update:** Using historical feedback (e.g., $r = +1.0$ for Like, $r = -0.5$ for Dislike), we maintain a design matrix $\mathbf{A} \in \mathbb{R}^{d \times d}$ and bias vector $\mathbf{b} \in \mathbb{R}^d$:
  $$\mathbf{A} \leftarrow \mathbf{A} + \mathbf{x}_{t,a} \mathbf{x}_{t,a}^T, \quad \mathbf{b} \leftarrow \mathbf{b} + r_{t,a} \mathbf{x}_{t,a}$$
  The ridge estimator is:
  $$\hat{\boldsymbol{\theta}} = \mathbf{A}^{-1} \mathbf{b}$$

* **Upper Confidence Bound (UCB) Decision Rule:**
  $$a_t = \arg\max_{a} \left( \mathbf{x}_{t,a}^T \hat{\boldsymbol{\theta}} + \alpha \sqrt{\mathbf{x}_{t,a}^T \mathbf{A}^{-1} \mathbf{x}_{t,a}} \right)$$
  The first term exploits topics you enjoy; the second term explores novel or under-sampled topics scaled by exploration hyperparameter $\alpha$.

### B. Directed Acyclic Graph (DAG) Timeline Stitching
* Extracting named entities and event anchors using structured outputs (`Pydantic`).
* De-biasing temporal ordering: converting relative references (*"last Tuesday"*, *"three months ago"*) into absolute ISO 8601 timestamps using publication date metadata.
* Eliminating historical duplicate reporting using reciprocal entity matching.

### C. Low-Latency Audio Streaming Architecture
* Avoiding disk I/O bottlenecks: synthesizing raw audio samples directly into an in-memory `io.BytesIO` buffer.
* FastAPI chunked transfer encoding (`StreamingResponse`) with MIME type `audio/wav`.
* Frontend HTML5 `MediaElement` stream consumption.

---

## 5. Modular Implementation Sequence

This roadmap is ordered by architectural dependency. Each phase produces an immediately usable component.

```
 Phase 1: Ingestion & Local Audio Engine  [Usable Personal Tool]
                        │
                        ▼
 Phase 2: Structured Distillation & PWA   [Mobile-Ready UI]
                        │
                        ▼
 Phase 3: The Retrospective Timeline     [Agentic Search & Graph]
                        │
                        ▼
 Phase 4: Contextual Bandit Feedback     [Adaptive Intelligence]
                        │
                        ▼
 Phase 5: Calendar & Push Automations    [Full Daily Autonomy]
```

---

### Phase 1: Core Scraper & Local Audio Engine
* **Goal:** Scrape 3–5 RSS feeds, parse article text, and synthesize local neural audio on demand.
* **Key Tasks:**
  1. Write an ingestion worker using `feedparser` to extract top links and `trafilatura` to extract clean article markdown.
  2. Set up `kokoro-onnx` with the 82M parameter model.
  3. Create a Python script that takes article text, generates audio in memory, and validates that generation completes in under 3 seconds on CPU.
* **Deliverable:** Working CLI tool that fetches the latest headlines and speaks them aloud locally.

---

### Phase 2: FastAPI Backend & Responsive Frontend (PWA)
* **Goal:** Build a functional web interface accessible from your PC browser and Android home screen.
* **Key Tasks:**
  1. Initialize a FastAPI backend with SQLite storage to cache scraped articles and text summaries.
  2. Implement an audio streaming endpoint: `GET /api/articles/{id}/audio`.
  3. Build a lightweight React (Tailwind CSS) frontend displaying news as responsive cards.
  4. Add an HTML5 `<audio>` player bound to the streaming endpoint.
  5. Add a `manifest.json` and basic service worker to enable Android PWA installation.
* **Deliverable:** An installable PWA that displays daily summaries and streams sub-second audio briefings on click.

---

### Phase 3: The Retrospective Timeline Agent
* **Goal:** Allow the user to "trace back in time" to understand the historical context of any story.
* **Key Tasks:**
  1. Engineer a prompt utilizing structured `Pydantic` outputs to extract core subjects, involved entities, and temporal keywords from an active article.
  2. Implement a search retriever tool that queries web search APIs or past news archives across parameterized historical time windows.
  3. Build the Chrono-Stitcher module: sorts retrieved events, resolves contradictions, deduplicates overlapping milestones, and outputs an ordered JSON list.
  4. Add a vertical step-tracker component to the frontend news card that animates the timeline upon clicking "Trace History".
* **Deliverable:** Interactive timeline visualizer uncovering prior events behind breaking stories.

---

### Phase 4: Contextual Bandit Personalization Loop
* **Goal:** Replace static topic filters with an intelligent recommendation engine that learns from daily feedback.
* **Key Tasks:**
  1. Generate dense representations of incoming articles using a local embedding model (`all-MiniLM-L6-v2`).
  2. Implement the **$\text{LinUCB}$ Algorithm** from scratch using NumPy (matrix initialization, rank-1 updates, and UCB score calculation).
  3. Expose a feedback endpoint `POST /api/articles/{id}/feedback` taking binary/scaled rewards ($+1.0$ for Like, $-0.5$ for Dislike).
  4. Wire up Thumbs Up / Thumbs Down actions in the frontend UI.
  5. Validate that the engine favors preferred topics while periodically introducing exploratory articles.
* **Deliverable:** A feed that shifts topic balance dynamically based on your interaction history.

---

### Phase 5: Automated Tracking, Calendar Sync & Push Alerts
* **Goal:** Enable the app to run in the background, alert you to critical deadlines, and schedule events.
* **Key Tasks:**
  1. Set up `APScheduler` in FastAPI to poll sources every morning (e.g., 7:00 AM) or on a scheduled cron trigger.
  2. Build the Event Extraction Agent: detects announcements, conferences, submission deadlines, or product launches with explicit dates.
  3. Generate dynamic Google Calendar Web Intent URLs:
     `https://calendar.google.com/calendar/render?action=TEMPLATE&text=...&dates=...`
  4. Connect `ntfy.sh` or a private Telegram bot to push immediate notifications to your mobile tray for high-priority tracked keywords.
* **Deliverable:** A fully autonomous personal intelligence system that keeps your calendar and morning routine synchronized with the real world.

---

## 6. Verification & Quality Checklist

* [ ] **Audio Latency:** Kokoro ONNX RTF is $< 0.25$; streaming begins within 1.5 seconds of pressing "Listen".
* [ ] **Hallucination Guardrails:** Summaries contain citations linking to the exact source paragraphs.
* [ ] **Timeline Grounding:** Every node in the retrospective timeline contains an absolute ISO timestamp verified against search results.
* [ ] **Bandit Stability:** Matrix $\mathbf{A}$ updates remain numerically stable without matrix singularity issues (regularized with identity matrix $\mathbf{I}_d$).
* [ ] **Mobile Usability:** PWA launches in standalone mode on Android without address bar clutter and handles lock-screen audio playback.