"""Local image generation with Stable Diffusion / FLUX via Hugging Face diffusers.

Models download once (several GB) on first use and then run fully offline.
Requires the extra packages in requirements-images.txt. A GPU (NVIDIA, or Apple Silicon) is
strongly recommended; CPU works but takes minutes per image.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import gc

from .config import OUTPUT_DIR, total_ram_gb

RAM_GB = total_ram_gb()
LOW_MEMORY = RAM_GB <= 8.5
MIN_RAM = {"sdxl-turbo": 8, "sdxl-base": 16, "flux-schnell": 24}

PRESETS = {
    "sdxl-turbo": {
        "repo": "stabilityai/sdxl-turbo", "steps": 4, "guidance": 0.0, "base": 512,
        "note": "Fastest (seconds on a GPU, usable on CPU). Lower detail. Check Stability AI's community licence for commercial use.",
    },
    "sdxl-base": {
        "repo": "stabilityai/stable-diffusion-xl-base-1.0", "steps": 30, "guidance": 6.5, "base": 1024,
        "note": "Best all-rounder. OpenRAIL++ licence allows commercial use. ~8 GB VRAM recommended.",
    },
    "flux-schnell": {
        "repo": "black-forest-labs/FLUX.1-schnell", "steps": 4, "guidance": 0.0, "base": 1024,
        "note": "Highest quality and best at hands/fabric. Apache-2.0 licence. Needs 16 GB+ VRAM or lots of RAM; may ask you to accept terms on Hugging Face once.",
    },
}

ASPECTS = {"1:1 (feed)": (1, 1), "4:5 (IG portrait)": (4, 5), "9:16 (Reels/TikTok/Stories)": (9, 16),
           "2:3 (Pinterest)": (2, 3), "16:9 (banner)": (16, 9)}

DEFAULT_NEGATIVE = ("text, watermark, logo, words, letters, blurry, low quality, deformed hands, extra fingers, "
                    "distorted face, bad anatomy, oversaturated, plastic skin, cropped head")

_pipe = None
_pipe_name = None
_img2img = None


def available() -> tuple[bool, str]:
    """Check the image packages are installed WITHOUT importing them (importing torch is slow and
    memory-hungry, so it only happens when you actually make an image)."""
    import importlib.util
    if not (importlib.util.find_spec("torch") and importlib.util.find_spec("diffusers")):
        return False, ("Image generation packages aren't installed. Run: "
                       "`pip install -r requirements-images.txt` (see README for GPU instructions).")
    note = " · 8 GB mode: one model at a time, sdxl-turbo only" if LOW_MEMORY else ""
    return True, f"Image engine installed (loads when you make your first image){note}"


def check_compat() -> None:
    """PyTorch 2.15+ uses Metal features that only exist on macOS 15+. On macOS 14 it hard-crashes the
    whole app, so stop early with a clear fix instead."""
    import platform
    from importlib.metadata import PackageNotFoundError, version
    mac = platform.mac_ver()[0]
    if not mac:
        return
    try:
        tv = tuple(int(x) for x in version("torch").split("+")[0].split(".")[:2])
    except (PackageNotFoundError, ValueError):
        return
    if int(mac.split(".")[0]) < 15 and tv >= (2, 15):
        raise RuntimeError(f"Your image engine (PyTorch {tv[0]}.{tv[1]}) needs macOS 15, and this Mac runs macOS {mac}. "
                           "Double-click 'Fix Image Engine.command' in the brand_studio folder (installs the macOS 14 "
                           "version), or update macOS.")


def device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def dims(aspect: str, base: int) -> tuple[int, int]:
    w, h = ASPECTS.get(aspect, (1, 1))
    area = base * base
    width = (area * w / h) ** 0.5
    height = width * h / w
    return int(width // 64 * 64), int(height // 64 * 64)


def _load(name: str, low_vram: bool):
    global _pipe, _pipe_name, _img2img
    if _pipe is not None and _pipe_name == name:
        return _pipe
    import torch
    from diffusers import AutoPipelineForText2Image

    _pipe = _img2img = None
    if device() == "cuda":
        torch.cuda.empty_cache()
    p = PRESETS[name]
    dev = device()
    dtype = torch.float32 if dev == "cpu" else (torch.bfloat16 if name == "flux-schnell" else torch.float16)
    kwargs = {"torch_dtype": dtype}
    if name in ("sdxl-base", "sdxl-turbo") and dev != "cpu":
        kwargs["variant"] = "fp16"
        try:
            from diffusers import AutoencoderKL
            kwargs["vae"] = AutoencoderKL.from_pretrained("madebyollin/sdxl-vae-fp16-fix", torch_dtype=dtype)
        except Exception:  # noqa: BLE001 — fall back to the bundled VAE
            pass
    pipe = AutoPipelineForText2Image.from_pretrained(p["repo"], **kwargs)
    if dev == "cuda" and (low_vram or name == "flux-schnell"):
        pipe.enable_model_cpu_offload()
    else:
        pipe = pipe.to(dev)
    if dev in ("mps", "cpu") or low_vram:
        pipe.enable_attention_slicing()
        try:
            pipe.enable_vae_slicing()
        except AttributeError:
            pass
    _pipe, _pipe_name = pipe, name
    return pipe


def generate(prompt: str, style: str = "", negative: str = DEFAULT_NEGATIVE, preset: str = "sdxl-base",
             aspect: str = "4:5 (IG portrait)", n: int = 2, seed: int = -1, steps: int | None = None,
             init_image=None, strength: float = 0.55, low_vram: bool = False, progress=None) -> list[str]:
    check_compat()
    import torch

    from . import llm

    p = PRESETS[preset]
    if device() != "cuda" and RAM_GB + 0.5 < MIN_RAM[preset]:
        raise RuntimeError(f"{preset} needs about {MIN_RAM[preset]} GB of memory and this computer has "
                           f"{RAM_GB:.0f} GB. Running it could freeze the computer, so use sdxl-turbo instead.")
    if LOW_MEMORY:
        n = min(int(n), 2)  # one batch at a time keeps memory in check
        low_vram = True
    llm.unload()  # give the image model the memory the text model was using
    pipe = _load(preset, low_vram)
    width, height = dims(aspect, p["base"])
    full_prompt = f"{prompt}. {style}".strip(". ") if style else prompt
    steps = int(steps or p["steps"])
    gen_dev = "cpu" if device() == "mps" else device()

    common = {"num_inference_steps": steps, "guidance_scale": p["guidance"]}
    if p["guidance"] > 0 and negative:
        common["negative_prompt"] = negative
    if preset == "flux-schnell":
        common["max_sequence_length"] = 256

    paths = []
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base_seed = seed if seed is not None and seed >= 0 else int(time.time()) % 2**31
    for i in range(int(n)):
        if progress:
            progress(i / n, desc=f"Generating image {i + 1}/{n}…")
        g = torch.Generator(gen_dev).manual_seed(base_seed + i)
        if init_image is not None:
            global _img2img
            from diffusers import AutoPipelineForImage2Image
            if _img2img is None:
                _img2img = AutoPipelineForImage2Image.from_pipe(pipe)
            src = init_image.convert("RGB").resize((width, height))
            st = max(steps, int(1 / max(strength, 0.05)) + 1)  # turbo needs steps*strength >= 1
            img = _img2img(prompt=full_prompt, image=src, strength=strength, generator=g,
                           **{**common, "num_inference_steps": st}).images[0]
        else:
            img = pipe(prompt=full_prompt, width=width, height=height, generator=g, **common).images[0]
        path = OUTPUT_DIR / f"gen-{stamp}-{i + 1}.png"
        img.save(path)
        Path(str(path) + ".json").write_text(json.dumps({
            "prompt": full_prompt, "negative": common.get("negative_prompt", ""), "preset": preset,
            "seed": base_seed + i, "steps": common["num_inference_steps"], "size": [width, height],
            "img2img_strength": strength if init_image is not None else None}, indent=2))
        paths.append(str(path))
    if LOW_MEMORY:
        release()  # hand the memory back so the rest of the Mac stays responsive
    return paths


def release() -> None:
    """Drop the image model from memory."""
    global _pipe, _pipe_name, _img2img
    _pipe = _pipe_name = _img2img = None
    gc.collect()
    try:
        import torch
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass
