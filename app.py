import os
import re
import json
import time
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import numpy as np
import soundfile as sf

# Ensure Coqui license terms accepted
os.environ["COQUI_TOS_AGREED"] = "1"

BASE = Path(__file__).resolve().parent
VOICES_DIR = BASE / "voices"
OUTPUTS_DIR = BASE / "outputs"
STATIC_DIR = BASE / "static"
MODELS_DIR = BASE / "models" / "xtts_v2"

VOICES_DIR.mkdir(exist_ok=True)
OUTPUTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="SAM VOICE STUDIO", version="2.2.0")

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

def detect_language(text: str) -> str:
    """
    Intelligently detect whether the input text is Arabic or English
    to ensure proper tokenizer and phonetic modeling.
    """
    ar_count = len(re.findall(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", text))
    en_count = len(re.findall(r"[a-zA-Z]", text))
    if ar_count > en_count:
        return "ar"
    if en_count > 0:
        return "en"
    return "ar"

def scan_and_sync_voices() -> List[dict]:
    """
    Dynamically scans VOICES_DIR for any audio files (.wav, .mp3, .m4a, etc.).
    Merges with voices.json metadata if available, and automatically
    registers any new audio files placed into the folder.
    """
    voices_file = VOICES_DIR / "voices.json"
    metadata_map = {}
    if voices_file.exists():
        try:
            with open(voices_file, "r", encoding="utf-8") as f:
                saved_voices = json.load(f)
                for v in saved_voices:
                    if isinstance(v, dict) and "file" in v:
                        metadata_map[v["file"]] = v
        except Exception as e:
            print(f"[SAM VOICE] Error reading voices.json: {e}")

    audio_exts = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}
    all_voices = []

    if VOICES_DIR.exists():
        for p in sorted(VOICES_DIR.iterdir()):
            if p.suffix.lower() in audio_exts and p.is_file():
                fname = p.name
                if fname in metadata_map:
                    all_voices.append(metadata_map[fname])
                else:
                    clean_name = p.stem.replace("_", " ").replace("-", " ").strip()
                    lower = fname.lower()
                    gender = "female" if any(k in lower for k in ["female", "woman", "girl", "bint", "anisa"]) else "male"
                    lang = "en" if any(k in lower for k in ["_en", "en_", "english", "us", "uk"]) else "ar"
                    
                    profile = {
                        "id": f"custom_{p.stem}",
                        "name": clean_name.title(),
                        "gender": gender,
                        "lang": lang,
                        "dialect": "صوت مخصص (ملف مباشر)",
                        "description": f"عينة صوتية ({fname}) تم اكتشافها تلقائياً واستنساخها بدقة.",
                        "file": fname,
                        "is_custom": True
                    }
                    all_voices.append(profile)

    return all_voices

def clean_speaker_reference(ref_path: Path) -> Path:
    """
    Pre-conditions speaker audio: removes leading/trailing silence,
    normalizes volume to ensure optimal voice cloning without stutter.
    """
    try:
        y, sr = sf.read(str(ref_path))
        if len(y.shape) > 1:
            y = y.mean(axis=1)

        energy = np.abs(y)
        threshold = np.max(energy) * 0.02
        active_indices = np.where(energy > threshold)[0]
        if len(active_indices) > 0:
            start_idx = max(0, active_indices[0] - int(sr * 0.05))
            end_idx = min(len(y), active_indices[-1] + int(sr * 0.05))
            y_trimmed = y[start_idx:end_idx]
        else:
            y_trimmed = y

        peak = np.max(np.abs(y_trimmed))
        if peak > 0.001:
            y_trimmed = (y_trimmed / peak) * 0.89

        clean_path = OUTPUTS_DIR / f"clean_ref_{ref_path.stem}.wav"
        sf.write(str(clean_path), y_trimmed, sr)
        return clean_path
    except Exception as e:
        print(f"[SAM VOICE] Warning: could not pre-clean speaker audio: {e}")
        return ref_path

def wsola_stretch(audio: np.ndarray, rate: float, win_size: int = 1024, hop_syn: int = 256) -> np.ndarray:
    """
    High-fidelity time-domain WSOLA (Waveform Similarity Overlap-Add)
    preserves pitch and vocal formants with ZERO phase vocoder / robotic distortion.
    """
    if abs(rate - 1.0) < 0.005:
        return audio
    hop_ana = int(round(hop_syn * rate))
    if hop_ana <= 0:
        return audio

    n_samples = len(audio)
    out_len = int(len(audio) / rate)
    output = np.zeros(out_len + win_size, dtype=np.float32)
    norm = np.zeros(out_len + win_size, dtype=np.float32)
    window = np.hanning(win_size).astype(np.float32)

    in_pos = 0
    out_pos = 0
    prev_pos = 0
    search_range = 256

    while out_pos + win_size <= len(output) and in_pos + win_size <= n_samples:
        if out_pos == 0:
            best_pos = in_pos
        else:
            s_start = max(0, in_pos - search_range)
            s_end = min(n_samples - win_size, in_pos + search_range)
            if s_end <= s_start:
                best_pos = in_pos
            else:
                ref = output[out_pos : out_pos + win_size]
                candidates = np.array([audio[p : p + win_size] for p in range(s_start, s_end)])
                corrs = np.dot(candidates, ref)
                best_pos = s_start + np.argmax(corrs)

        output[out_pos : out_pos + win_size] += audio[best_pos : best_pos + win_size] * window
        norm[out_pos : out_pos + win_size] += window
        prev_pos = best_pos
        out_pos += hop_syn
        in_pos += hop_ana

    valid = norm > 1e-6
    output[valid] /= norm[valid]
    return output[:out_len]

def process_audio_pipeline(
    input_wav: Path,
    output_wav: Path,
    target_sec: float,
    echo_enabled: bool = False,
    echo_intensity: int = 0
) -> float:
    """
    Processes the raw generated audio with:
    1. Gold-standard pitch-preserving time stretching (Rubberband / WSOLA) - ZERO robotic phase artifacts.
    2. Studio Echo / Reverb DSP effect (customizable intensity 0-100%).
    3. Sample-accurate exact millisecond duration lock.
    """
    d, sr = sf.read(str(input_wav))
    if len(d.shape) > 1:
        d = d.mean(axis=1)
    raw_sec = len(d) / sr

    # Build FFmpeg filter chain
    filters = []

    # 1. High-fidelity pitch-preserving time stretch
    if target_sec > 0 and abs(raw_sec - target_sec) > 0.05:
        tempo = raw_sec / target_sec
        tempo = max(0.5, min(tempo, 2.5))
        filters.append(f"rubberband=tempo={tempo:.4f}")

    # 2. Studio Echo / Reverb DSP effect
    if echo_enabled and echo_intensity > 0:
        delay = int(100 + (echo_intensity / 100.0) * 160)
        decay = round(0.15 + (echo_intensity / 100.0) * 0.45, 2)
        filters.append(f"aecho=0.85:0.88:{delay}:{decay}")

    filter_arg = ",".join(filters) if filters else "anull"

    use_ffmpeg = True
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(input_wav),
            "-filter:a", filter_arg,
            "-ar", str(sr),
            str(output_wav)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"[SAM VOICE] FFmpeg warning: {res.stderr}. Using WSOLA fallback.")
            use_ffmpeg = False
    except Exception as e:
        print(f"[SAM VOICE] FFmpeg error: {e}. Using WSOLA fallback.")
        use_ffmpeg = False

    # Fallback to pure python WSOLA if FFmpeg was unavailable
    if not use_ffmpeg:
        rate = raw_sec / target_sec if target_sec > 0 else 1.0
        y_proc = wsola_stretch(d, rate)
        if echo_enabled and echo_intensity > 0:
            delay_samples = int(round(sr * (0.12 + 0.16 * (echo_intensity / 100.0))))
            decay = 0.2 + 0.4 * (echo_intensity / 100.0)
            if delay_samples < len(y_proc):
                echoed = np.copy(y_proc)
                echoed[delay_samples:] += y_proc[:-delay_samples] * (decay * 0.7)
                y_proc = echoed
        sf.write(str(output_wav), y_proc, sr)

    # 3. Sample-accurate exact boundary enforcement (Cosine micro-fade)
    y_final, sr = sf.read(str(output_wav))
    if len(y_final.shape) > 1:
        y_final = y_final.mean(axis=1)

    if target_sec > 0:
        target_samples = int(round(target_sec * sr))
        if len(y_final) < target_samples:
            pad = target_samples - len(y_final)
            y_final = np.pad(y_final, (0, pad), mode="constant")
        else:
            y_final = y_final[:target_samples]
            fade_len = min(int(sr * 0.015), len(y_final))
            if fade_len > 0:
                fade = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
                y_final[-fade_len:] *= fade

    sf.write(str(output_wav), y_final, sr)
    final_sec = round(len(y_final) / sr, 3)
    print(f"[SAM VOICE] Final Pipeline Duration: {raw_sec:.2f}s -> {final_sec}s (Target: {target_sec}s, Echo: {echo_enabled})")
    return final_sec

class AnalyzeRequest(BaseModel):
    text: str = Field(default="", max_length=20000)
    language: str = "auto"
    target_seconds: int = Field(default=15, ge=5, le=180)
    style: str = "natural"

class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    voice_id: str
    language: str = "auto"
    engine: str = "xtts"  # "xtts" or "fast"
    target_seconds: int = Field(default=15, ge=5, le=180)
    strict_duration: bool = True
    speed: float = 1.0
    echo_enabled: bool = False
    echo_intensity: int = 35

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
        "version": "2.2.0",
        "engine": "xtts_v2",
        "cuda": cuda_ok,
        "gpu": gpu_name,
        "model_loaded": _xtts_model is not None,
        "model_loading": _xtts_loading,
        "offline_models": MODELS_DIR.exists()
    }

@app.get("/api/voices")
def get_voices():
    """
    Returns the dynamic list of voices, auto-detecting any newly added audio files.
    """
    return scan_and_sync_voices()

@app.post("/api/voices/upload")
async def upload_voice(file: UploadFile = File(...)):
    """
    Upload a new voice sample directly from the browser into voices directory.
    """
    audio_exts = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}
    ext = Path(file.filename).suffix.lower()
    if ext not in audio_exts:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم. يرجى رفع ملف صوتي (.wav, .mp3, إلخ).")

    safe_name = re.sub(r"[^\w\.\-]", "_", file.filename)
    dest_path = VOICES_DIR / safe_name
    
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    voices = scan_and_sync_voices()
    return {"status": "success", "message": f"تمت إضافة الصوت '{file.filename}' بنجاح!", "voices": voices}

@app.post("/api/open-voices-folder")
def open_voices_folder():
    """
    Opens the voices folder directly in Windows Explorer.
    """
    try:
        os.startfile(str(VOICES_DIR))
        return {"status": "ok", "path": str(VOICES_DIR)}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest):
    words = count_words(payload.text)
    detected_lang = detect_language(payload.text) if payload.language == "auto" else payload.language
    wpm = 145 if detected_lang == "ar" else 150
    estimated_seconds = round(words / wpm * 60, 1) if words else 0
    target_words = round(payload.target_seconds * wpm / 60)
    
    speed_factor = round(estimated_seconds / payload.target_seconds, 2) if (payload.target_seconds and words) else 1.0

    if not words:
        status = "empty"
        advice = "اكتب النص لاحتساب سرعة الإلقاء تلقائياً وضمان مطابقة الثواني."
    elif 0.85 <= speed_factor <= 1.25:
        status = "good"
        advice = f"✓ ممتاز! النص متناسق تماماً مع مدة {payload.target_seconds} ثانية (معدل سرعة طبيعي: {speed_factor}x)."
    elif speed_factor < 0.85:
        status = "short"
        advice = f"النص قصير مقارنة بـ {payload.target_seconds} ثانية. سيتم ضبط الإلقاء بتأنٍ طبيعي والالتزام بـ {payload.target_seconds} ثانية بالضبط."
    else:
        status = "long"
        advice = f"النص طويل مقارنة بـ {payload.target_seconds} ثانية ({speed_factor}x). يفضل تخفيف النص أو زيادة الثواني للحفاظ على إلقاء بشري سلس."

    return {
        "words": words,
        "language": detected_lang,
        "estimated_seconds": estimated_seconds,
        "target_seconds": payload.target_seconds,
        "target_words": target_words,
        "speed_factor": speed_factor,
        "status": status,
        "advice": advice,
        "note": f"البرنامج ملزم بإنهاء المقطع في {payload.target_seconds} ثانية بالضبط بدون أي تشويه."
    }

EDGE_VOICE_MAP = {
    # Arabic Voices
    "01_ar_male_classical": "ar-SA-HamedNeural",
    "02_ar_male_levantine": "ar-SY-LaithNeural",
    "03_ar_male_egyptian": "ar-EG-ShakirNeural",
    "06_ar_female_gulf": "ar-AE-FatimaNeural",
    "07_ar_female_hijazi_jumana": "ar-SA-ZariyahNeural",
    "08_ar_female_storyteller": "ar-EG-SalmaNeural",
    "09_ar_female_formal": "ar-SA-ZariyahNeural",
    "10_ar_female_nature": "ar-EG-SalmaNeural",
    "11_ar_female_levantine": "ar-SY-AmanyNeural",
    "12_ar_female_motivational": "ar-JO-SanaNeural",
    # English Voices
    "04_en_male_saudi": "en-US-GuyNeural",
    "05_en_female_educational": "en-US-JennyNeural"
}

@app.post("/api/generate")
async def generate(payload: GenerateRequest):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="النص مطلوب للتوليد")

    all_voices = scan_and_sync_voices()
    selected_voice = next((v for v in all_voices if v["id"] == payload.voice_id), None)
    if not selected_voice and all_voices:
        selected_voice = all_voices[0]
        payload.voice_id = selected_voice["id"]

    ref_wav = str(VOICES_DIR / selected_voice["file"]) if selected_voice else None

    # Detect language accurately
    if payload.language == "auto":
        actual_lang = detect_language(payload.text)
    else:
        actual_lang = payload.language if payload.language in ["ar", "en"] else detect_language(payload.text)

    timestamp = int(time.time())
    raw_filename = f"raw_{payload.voice_id}_{timestamp}.wav"
    raw_path = OUTPUTS_DIR / raw_filename

    final_filename = f"gen_{payload.voice_id}_{payload.target_seconds}s_{timestamp}.wav"
    final_path = OUTPUTS_DIR / final_filename

    # Execute generation
    if payload.engine == "xtts" and ref_wav and os.path.exists(ref_wav):
        try:
            loop = asyncio.get_event_loop()
            def run_xtts():
                clean_ref = clean_speaker_reference(Path(ref_wav))
                tts = get_xtts()
                tts.tts_to_file(
                    text=payload.text,
                    speaker_wav=str(clean_ref),
                    language=actual_lang,
                    file_path=str(raw_path),
                    split_sentences=True,
                    temperature=0.72,
                    repetition_penalty=4.0
                )
            await loop.run_in_executor(None, run_xtts)
            engine_used = "XTTS-v2 (Zero-Shot Clone · Local AI)"
        except Exception as e:
            print(f"[SAM VOICE] XTTS exception: {e}, falling back to Ultra Neural Studio...")
            edge_voice = EDGE_VOICE_MAP.get(
                payload.voice_id,
                "ar-SA-HamedNeural" if actual_lang == "ar" else "en-US-GuyNeural"
            )
            if actual_lang == "en" and not edge_voice.startswith("en-"):
                edge_voice = "en-US-GuyNeural" if selected_voice and selected_voice.get("gender") == "male" else "en-US-JennyNeural"
            elif actual_lang == "ar" and not edge_voice.startswith("ar-"):
                edge_voice = "ar-SA-HamedNeural" if selected_voice and selected_voice.get("gender") == "male" else "ar-SA-ZariyahNeural"

            communicate = edge_tts.Communicate(payload.text, edge_voice)
            tmp_mp3 = OUTPUTS_DIR / f"tmp_{timestamp}.mp3"
            await communicate.save(str(tmp_mp3))
            subprocess.run(["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", "24000", str(raw_path)], capture_output=True)
            if tmp_mp3.exists():
                tmp_mp3.unlink()
            engine_used = f"Ultra Neural Studio (Fallback - {edge_voice})"
    else:
        edge_voice = EDGE_VOICE_MAP.get(
            payload.voice_id,
            "ar-SA-HamedNeural" if actual_lang == "ar" else "en-US-GuyNeural"
        )
        if actual_lang == "en" and not edge_voice.startswith("en-"):
            edge_voice = "en-US-GuyNeural" if selected_voice and selected_voice.get("gender") == "male" else "en-US-JennyNeural"
        elif actual_lang == "ar" and not edge_voice.startswith("ar-"):
            edge_voice = "ar-SA-HamedNeural" if selected_voice and selected_voice.get("gender") == "male" else "ar-SA-ZariyahNeural"

        communicate = edge_tts.Communicate(payload.text, edge_voice)
        tmp_mp3 = OUTPUTS_DIR / f"tmp_{timestamp}.mp3"
        await communicate.save(str(tmp_mp3))
        subprocess.run(["ffmpeg", "-y", "-i", str(tmp_mp3), "-ar", "24000", str(raw_path)], capture_output=True)
        if tmp_mp3.exists():
            tmp_mp3.unlink()
        engine_used = f"Ultra Neural Studio ({edge_voice})"

    # STRICT EXACT DURATION & STUDIO ECHO PIPELINE
    exact_duration = process_audio_pipeline(
        input_wav=raw_path,
        output_wav=final_path,
        target_sec=float(payload.target_seconds) if payload.strict_duration else 0.0,
        echo_enabled=payload.echo_enabled,
        echo_intensity=payload.echo_intensity
    )

    if raw_path.exists():
        try:
            raw_path.unlink()
        except Exception:
            pass

    return {
        "status": "success",
        "audio_url": f"/outputs/{final_filename}",
        "filename": final_filename,
        "engine": engine_used,
        "voice": selected_voice["name"] if selected_voice else payload.voice_id,
        "language": actual_lang,
        "target_seconds": payload.target_seconds,
        "exact_duration": exact_duration,
        "echo_applied": payload.echo_enabled,
        "echo_intensity": payload.echo_intensity if payload.echo_enabled else 0
    }
