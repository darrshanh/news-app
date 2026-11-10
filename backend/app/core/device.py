"""Hardware detection and execution device configuration.

Dynamically scans the runtime environment (Bare-metal Windows/Linux or Docker container)
to configure the best available hardware accelerator (CUDA GPU) or fall back cleanly to CPU.

Environment Variables:
    DEVICE: "auto" (default), "cuda", "gpu", or "cpu".
    FORCE_CPU: "1", "true" forces CPU execution regardless of hardware.
"""

import os
import sys
import logging
from dataclasses import dataclass
import torch
import onnxruntime as rt

logger = logging.getLogger(__name__)

@dataclass
class DeviceProfile:
    device: str  # "cuda" or "cpu"
    is_cuda: bool
    device_name: str
    torch_dtype: torch.dtype
    device_map: str
    onnx_providers: list[str]
    onnx_session_options: rt.SessionOptions

    def summary(self) -> str:
        if self.is_cuda:
            return f"GPU Acceleration Active [{self.device_name}] (PyTorch: {self.torch_dtype}, ONNX: {self.onnx_providers[0]})"
        return f"CPU Mode Active [{self.device_name}] (PyTorch: float32, ONNX: CPUExecutionProvider)"


def _register_windows_cuda_dlls():
    """Dynamically register NVIDIA cuDNN & cuBLAS DLL folders on Windows if present."""
    if sys.platform != "win32":
        return
    try:
        import nvidia.cudnn
        import nvidia.cublas
        cudnn_bin = os.path.join(list(nvidia.cudnn.__path__)[0], "bin")
        cublas_bin = os.path.join(list(nvidia.cublas.__path__)[0], "bin")
        if os.path.exists(cudnn_bin):
            os.add_dll_directory(cudnn_bin)
            os.environ["PATH"] = cudnn_bin + ";" + os.environ.get("PATH", "")
        if os.path.exists(cublas_bin):
            os.add_dll_directory(cublas_bin)
            os.environ["PATH"] = cublas_bin + ";" + os.environ.get("PATH", "")
    except Exception as e:
        logger.debug(f"Optional Windows NVIDIA DLL registration skipped: {e}")


def detect_device() -> DeviceProfile:
    """Scan hardware and environment variables to construct the optimal DeviceProfile."""
    env_device = os.getenv("DEVICE", "auto").strip().lower()
    force_cpu = os.getenv("FORCE_CPU", "false").strip().lower() in ("1", "true", "yes")

    # Check if CPU is explicitly forced
    wants_cpu = force_cpu or env_device == "cpu"

    is_cuda = False
    device_name = f"CPU ({os.cpu_count() or 4} cores)"
    
    if not wants_cpu:
        _register_windows_cuda_dlls()
        if torch.cuda.is_available():
            try:
                gpu_name = torch.cuda.get_device_name(0)
                vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
                device_name = f"{gpu_name} ({vram_gb:.1f}GB VRAM)"
                is_cuda = True
            except Exception as e:
                logger.warning(f"CUDA detected but failed to query properties: {e}")
                is_cuda = False

    # ONNX Session Configuration
    onnx_opts = rt.SessionOptions()
    onnx_opts.log_severity_level = 3  # Suppress informational graph rewrite notices

    if is_cuda:
        device = "cuda"
        torch_dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        device_map = "auto"

        # Check ONNX CUDAExecutionProvider
        available_onnx = rt.get_available_providers()
        if "CUDAExecutionProvider" in available_onnx:
            onnx_providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            logger.warning("PyTorch has CUDA, but onnxruntime CUDAExecutionProvider is unavailable. Falling back to CPU for ONNX.")
            onnx_providers = ["CPUExecutionProvider"]
            onnx_opts.intra_op_num_threads = os.cpu_count() or 4
    else:
        device = "cpu"
        torch_dtype = torch.float32
        device_map = "cpu"
        onnx_providers = ["CPUExecutionProvider"]
        onnx_opts.intra_op_num_threads = os.cpu_count() or 4
        # Optimize CPU PyTorch threads
        torch.set_num_threads(os.cpu_count() or 4)

    profile = DeviceProfile(
        device=device,
        is_cuda=is_cuda,
        device_name=device_name,
        torch_dtype=torch_dtype,
        device_map=device_map,
        onnx_providers=onnx_providers,
        onnx_session_options=onnx_opts,
    )

    logger.info(f"[+] {profile.summary()}")
    return profile


_cached_profile: DeviceProfile | None = None

def get_device_profile() -> DeviceProfile:
    """Return the cached runtime DeviceProfile."""
    global _cached_profile
    if _cached_profile is None:
        _cached_profile = detect_device()
    return _cached_profile
