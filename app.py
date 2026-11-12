import os
import re
import json
import time
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf
import librosa

# Ensure Coqui license terms accepted
os.environ["COQUI_TOS_AGREED"] = "1"

BASE = Path(__file__).resolve().parent
VOICES_DIR = BASE / "voices"
OUTPUTS_DIR = BASE / "outputs"
STATIC_DIR = BASE / "static"
MODELS_DIR = BASE / "models" / "xtts_v2"

OUTPUTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SAM VOICE STUDIO", version="2.0.0")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/voices", StaticFiles(directory=VOICES_DIR), name="voices")
app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")

# Global TTS model reference
_xtts_model = None
_xtts_loading = False

def get_xtts():
    global _xtts_model, _xtts_loading
    if _xtts_model is not None:
        return _xtts_model
    _xtts_loading = True
    try:
        import torch
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[SAM VOICE] Initializing XTTS-v2 on {device}...")

        if MODELS_DIR.exists() and (MODELS_DIR / "config.json").exists():
            print(f"[SAM VOICE] Loading offline weights from {MODELS_DIR}...")
            _xtts_model = TTS(
                model_path=str(MODELS_DIR),
                config_path=str(MODELS_DIR / "config.json")
            ).to(device)
        else:
            print("[SAM VOICE] Loading model from default cache...")
            _xtts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

        print(f"[SAM VOICE] XTTS-v2 successfully loaded on {device}!")
        return _xtts_model
    finally:
        _xtts_loading = False

def enforce_exact_duration(audio_path: Path, target_sec: float) -> float:
    """
    Enforces the target duration to the exact millisecond using pitch-preserving
    time-stretching and sample-accurate boundary padding/fade.
    """
    y, sr = sf.read(str(audio_path))
    if len(y.shape) > 1:
        y = y.mean(axis=1)

    raw_sec = len(y) / sr
    if target_sec <= 0:
        return raw_sec

    rate = raw_sec / target_sec

    # Stretch while preserving original pitch
    if abs(rate - 1.0) > 0.001:
        y_stretch = librosa.effects.time_stretch(y, rate=rate)
    else:
        y_stretch = y

    # Exact target sample count
    target_samples = int(round(target_sec * sr))
    if len(y_stretch) < target_samples:
        pad_len = target_samples - len(y_stretch)
        y_final = np.pad(y_stretch, (0, pad_len), mode="constant")
    else:
        y_final = y_stretch[:target_samples]
        # Smooth 15ms fade-out to prevent clicks
        fade_len = min(int(sr * 0.015), len(y_final))
        if fade_len > 0:
            fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            y_final[-fade_len:] *= fade

    sf.write(str(audio_path), y_final, sr)
    final_sec = round(len(y_final) / sr, 3)
    print(f"[SAM VOICE] Exact Duration Enforced: {raw_sec:.2f}s -> {final_sec}s (Target: {target_sec}s)")
    return final_sec

class AnalyzeRequest(BaseModel):
    text: str = Field(default="", max_length=20000)
    language: str = "ar"
    target_seconds: int = Field(default=15, ge=5, le=180)
    style: str = "natural"

class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    voice_id: str
    language: str = "ar"
    engine: str = "xtts"  # "xtts" or "fast"
    target_seconds: int = Field(default=15, ge=5, le=180)
    strict_duration: bool = True
    speed: float = 1.0

def count_words(text: str) -> int:
    return len(re.findall(r"[\w\u0600-\u06FF]+(?:['’\-][\w\u0600-\u06FF]+)*", text, re.UNICODE))

@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/favicon.ico")
def favicon():
    fav = STATIC_DIR / "favicon.ico"
    if fav.exists():
        return FileResponse(fav)
    return FileResponse(STATIC_DIR / "app_icon.png")

@app.get("/api/health")
def health():
    gpu_name = "CPU Mode"
    cuda_ok = False
    try:
        import torch
        cuda_ok = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if cuda_ok else "CPU Only (No NVIDIA GPU)"
    except Exception as e:
        gpu_name = f"Error: {e}"

    return {
        "status": "ok",
        "app": "SAM VOICE STUDIO",
        "version": "2.0.0",
        "engine": "xtts_v2",
        "cuda": cuda_ok,
        "gpu": gpu_name,
        "model_loaded": _xtts_model is not None,
        "model_loading": _xtts_loading,
        "offline_models": MODELS_DIR.exists()
    }

@app.get("/api/voices")
def get_voices():
    voices_file = VOICES_DIR / "voices.json"
    if voices_file.exists():
        with open(voices_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    words = count_words(payload.text)
    wpm = 145 if payload.language == "ar" else 150
    estimated_seconds = round(words / wpm * 60, 1) if words else 0
    target_words = round(payload.target_seconds * wpm / 60)
    
    # Calculate required speed ratio to hit exact target
    speed_factor = round(estimated_seconds / payload.target_seconds, 2) if (payload.target_seconds and words) else 1.0
    
    low = round(target_words * 0.90)
    high = round(target_words * 1.10)
    delta = words - target_words
    
    if not words:
        status = "empty"
        advice = "اكتب النص لبدء الحساب الدقيق للمدة والسرعة."
    elif 0.85 <= speed_factor <= 1.25:
        status = "good"
        advice = f"✓ ممتاز! النص متناسق جداً مع مدة {payload.target_seconds} ثانية (معدل السرعة: {speed_factor}x - طبيعي)."
    elif speed_factor < 0.85:
        status = "short"
        advice = f"النص قصير بالنسبة لـ {payload.target_seconds} ثانية. سيتم ضبط الإلقاء بتأنٍ وتطبيق {payload.target_seconds} ثانية بدقة صارمة."
    else:
        status = "long"
        advice = f"النص طويل بالنسبة لـ {payload.target_seconds} ثانية (سرعة {speed_factor}x). يفضل تخفيف النص أو زيادة الثواني للحفاظ على نبرة طبيعية."

    return {
        "words": words,
        "estimated_seconds": estimated_seconds,
        "target_seconds": payload.target_seconds,
        "target_words": target_words,
        "speed_factor": speed_factor,
        "status": status,
        "advice": advice,
        "note": f"البرنامج ملزم بإنهاء المقطع في {payload.target_seconds} ثانية بالضبط."
    }

EDGE_VOICE_MAP = {
    "01_ar_male_classical": "ar-SA-HamedNeural",
    "02_ar_male_levantine": "ar-SY-LaithNeural",
    "03_ar_male_egyptian": "ar-EG-ShakirNeural",
    "04_en_male_saudi": "en-US-GuyNeural",
    "05_en_female_educational": "en-US-JennyNeural",
    "06_ar_female_gulf": "ar-AE-FatimaNeural",
    "07_ar_female_hijazi_jumana": "ar-SA-ZariyahNeural",
    "08_ar_female_storyteller": "ar-EG-SalmaNeural",
    "09_ar_female_formal": "ar-SA-ZariyahNeural",
    "10_ar_female_nature": "ar-EG-SalmaNeural",
    "11_ar_female_levantine": "ar-SY-AmanyNeural",
    "12_ar_female_motivational": "ar-JO-SanaNeural"
}

@app.post("/api/generate")
async def generate(payload: GenerateRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="النص مطلوب للتوليد")

    voices_file = VOICES_DIR / "voices.json"
    voices = []
    if voices_file.exists():
        with open(voices_file, "r", encoding="utf-8") as f:
            voices = json.load(f)
    
    selected_voice = next((v for v in voices if v["id"] == payload.voice_id), None)
    if not selected_voice and voices:
        selected_voice = voices[0]
        payload.voice_id = selected_voice["id"]

    ref_wav = str(VOICES_DIR / selected_voice["file"]) if selected_voice else None

    timestamp = int(time.time())
    out_filename = f"gen_{payload.voice_id}_{payload.target_seconds}s_{timestamp}.wav"
    out_path = OUTPUTS_DIR / out_filename

    lang = payload.language if payload.language in ["ar", "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "zh-cn", "ja", "ko", "hu", "hi"] else "ar"

    if payload.engine == "xtts" and ref_wav and os.path.exists(ref_wav):
        try:
            loop = asyncio.get_event_loop()
            def run_xtts():
                tts = get_xtts()
                tts.tts_to_file(
                    text=payload.text,
                    speaker_wav=ref_wav,
                    language=lang,
                    file_path=str(out_path),
                    speed=payload.speed
                )
            await loop.run_in_executor(None, run_xtts)
            engine_used = "XTTS-v2 (Zero-Shot Clone · Local AI)"
        except Exception as e:
            print(f"[SAM VOICE] XTTS exception: {e}, falling back to Edge Neural...")
            import edge_tts
            edge_voice = EDGE_VOICE_MAP.get(payload.voice_id, "ar-SA-HamedNeural" if lang == "ar" else "en-US-JennyNeural")
            communicate = edge_tts.Communicate(payload.text, edge_voice)
            await communicate.save(str(out_path))
            engine_used = f"Neural Fast Engine (Fallback - {edge_voice})"
    else:
        import edge_tts
        edge_voice = EDGE_VOICE_MAP.get(payload.voice_id, "ar-SA-HamedNeural" if lang == "ar" else "en-US-JennyNeural")
        communicate = edge_tts.Communicate(payload.text, edge_voice)
        await communicate.save(str(out_path))
        engine_used = f"Neural Fast Engine ({edge_voice})"

    # STRICT EXACT DURATION ENFORCEMENT
    final_duration = payload.target_seconds
    if payload.strict_duration and payload.target_seconds > 0:
        final_duration = enforce_exact_duration(out_path, float(payload.target_seconds))

    return {
        "status": "success",
        "audio_url": f"/outputs/{out_filename}",
        "filename": out_filename,
        "engine": engine_used,
        "voice": selected_voice["name"] if selected_voice else payload.voice_id,
        "language": lang,
        "target_seconds": payload.target_seconds,
        "exact_duration": final_duration
    }
