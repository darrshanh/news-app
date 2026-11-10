from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.database import init_db
from backend.app.api.routes import articles

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
    print("[+] All neural models preloaded and ready in memory!")
    yield
    # Shutdown logic (if any) goes here
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
