"""Utility script to download Kokoro-82M ONNX model weights and voice libraries.

Source: https://github.com/thewh1teagle/kokoro-onnx/releases
"""

import os
import sys
import urllib.request
from pathlib import Path

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights" / "kokoro"

FILES_TO_DOWNLOAD = [
    {
        "name": "kokoro-v0_19.onnx",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v0_19.onnx",
    },
    {
        "name": "voices-v1.0.bin",
        "url": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
    },
]


def download_file(url: str, dest_path: Path):
    if dest_path.exists():
        print(f"[OK] Already exists: {dest_path.name} ({dest_path.stat().st_size / (1024*1024):.2f} MB)")
        return

    print(f"[*] Downloading {dest_path.name} from {url}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    def progress_hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            percent = downloaded / total_size * 100
            mb_downloaded = downloaded / (1024 * 1024)
            mb_total = total_size / (1024 * 1024)
            sys.stdout.write(f"\r    -> {percent:5.1f}% [{mb_downloaded:.1f}MB / {mb_total:.1f}MB]")
        else:
            sys.stdout.write(f"\r    -> Downloaded {downloaded / (1024*1024):.1f}MB")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, dest_path, reporthook=progress_hook)
    print(f"\n[+] Successfully saved {dest_path.name}")


def main():
    print(f"Kokoro weights directory: {WEIGHTS_DIR}")
    for item in FILES_TO_DOWNLOAD:
        dest = WEIGHTS_DIR / item["name"]
        download_file(item["url"], dest)
    print("\n[Done] All Kokoro ONNX assets ready.")


if __name__ == "__main__":
    main()

