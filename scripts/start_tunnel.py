"""Cloudflare Tunnel Manager for Local News Agent Backend.

Spins up a Cloudflare Quick Tunnel without requiring a Cloudflare account or registration.
Directs public HTTPS traffic straight to your local RTX 4060 GPU FastAPI backend (http://localhost:8000).
"""

import sys
import subprocess
import urllib.request
from pathlib import Path

CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
EXE_PATH = TOOLS_DIR / "cloudflared.exe"

def ensure_cloudflared() -> Path:
    if not EXE_PATH.exists():
        TOOLS_DIR.mkdir(parents=True, exist_ok=True)
        print("[*] Downloading portable Cloudflare Tunnel binary (cloudflared.exe)...")
        urllib.request.urlretrieve(CLOUDFLARED_URL, str(EXE_PATH))
        print("[+] cloudflared.exe downloaded successfully!")
    return EXE_PATH

def main():
    exe = ensure_cloudflared()
    print("=" * 70)
    print("🚀 STARTING CLOUDFLARE QUICK TUNNEL")
    print("• Target: http://127.0.0.1:8000 (Local RTX 4060 GPU Backend)")
    print("• Free tier: Unlimited bandwidth, zero interstitial warning pages")
    print("• Look for the URL ending with '.trycloudflare.com' below!")
    print("=" * 70)
    try:
        subprocess.run([str(exe), "tunnel", "--url", "http://127.0.0.1:8000"])
    except KeyboardInterrupt:
        print("\n[*] Tunnel stopped.")

if __name__ == "__main__":
    main()
