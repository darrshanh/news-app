from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.database import init_db
from backend.app.api.routes import articles, feeds, settings
import asyncio
import logging

logger = logging.getLogger(__name__)
SYNC_INTERVAL_SECONDS = 30 * 60

async def periodic_feed_sync():
    from backend.app.services.ingestion import sync_all_feeds
    while True:
        try:
            logger.info("[*] Running scheduled 30-minute background feed sync")
            result = await asyncio.to_thread(sync_all_feeds)
            logger.info(f"[+] Scheduled sync complete: {result}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[-] Scheduled sync failed: {e}")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the database and preload neural models into RAM
    print("[*] Starting News Intelligence Agent API...")
    init_db()
    from backend.app.core.device import get_device_profile
    profile = get_device_profile()
    print(f"[*] Hardware Profile: {profile.summary()}")
    print("[*] Preloading Qwen 2.5 local LLM...")
    from backend.app.services.synthesizer import get_synthesizer
    get_synthesizer()._ensure_loaded()
    print("[*] Preloading Kokoro TTS neural voice engine...")
    from backend.app.services.tts import get_tts
    get_tts()
    print("[*] Preloading CPU semantic embedding model...")
    from backend.app.services.embeddings import get_embedding_service
    get_embedding_service()._ensure_loaded()
    print("[+] All neural models preloaded and ready in memory!")
    sync_task = asyncio.create_task(periodic_feed_sync())
    yield
    # Shutdown logic (if any) goes here
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    print("[*] Shutting down...")

app = FastAPI(
    title="Autonomous News Scraper Agent",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Register our routes
app.include_router(articles.router, prefix="/api")
app.include_router(feeds.router, prefix="/api")
app.include_router(settings.router, prefix="/api")

@app.get("/api/health")
def health_check():
    from backend.app.core.device import get_device_profile
    profile = get_device_profile()
    return {
        "status": "ok",
        "service": "news-agent",
        "device": profile.device,
        "device_name": profile.device_name,
        "is_cuda": profile.is_cuda,
        "torch_dtype": str(profile.torch_dtype),
        "onnx_provider": profile.onnx_providers[0] if profile.onnx_providers else "CPUExecutionProvider",
    }
