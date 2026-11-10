"""Helper script to download Kokoro-ONNX neural voice weights."""

import os
import sys
from pathlib import Path
import urllib.request

KOKORO_MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v0_19.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

def download_file(url: str, dest_path: Path):
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"[✓] Already present: {dest_path.name} ({dest_path.stat().st_size / (1024*1024):.1f} MB)")
        return
    print(f"[*] Downloading {dest_path.name} from {url}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest_path))
    print(f"[+] Downloaded: {dest_path.name} ({dest_path.stat().st_size / (1024*1024):.1f} MB)")

def main():
    root = Path(__file__).resolve().parent.parent
    weights_dir = root / "backend" / "weights" / "kokoro"
    print(f"[*] Ensuring Kokoro weights in: {weights_dir}")
    download_file(KOKORO_MODEL_URL, weights_dir / "kokoro-v0_19.onnx")
    download_file(VOICES_URL, weights_dir / "voices-v1.0.bin")
    print("[+] All neural weights are ready!")

if __name__ == "__main__":
    main()
