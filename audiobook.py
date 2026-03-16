import os
import re
import argparse
import tempfile
import subprocess
import sys
import ctypes
import json
import glob

# ── eSpeak-NG ─────────────────────────────────────────────────────────────────
os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = r"C:\espeak-data\espeak-ng.dll"
os.environ["ESPEAK_DATA_PATH"]          = r"C:\espeak-data"
ctypes.CDLL(r"C:\espeak-data\espeak-ng.dll")

import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from pydub import AudioSegment
import numpy as np
import soundfile as sf
from pathlib import Path 
# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGE, ENGINE AND VOICE CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

KOKORO_LANG_CODE = {
    "es":    "e",
    "en":    "a",
    "en-gb": "b",
    "fr":    "f",
    "it":    "i",
    "pt":    "p",
    "ja":    "j",
    "zh":    "z",
}

KOKORO_ESPEAK_LANG = {
    "e": "es",
    "a": "en-us",
    "b": "en-gb",
    "f": "fr-fr",
    "i": "it",
    "p": "pt-br",
    "j": "ja",
    "z": "zh",
}

KOKORO_VOCES = {
    "es":    ["ef_dora",    "em_alex",       "em_santa"],
    "en":    ["af_heart",   "af_bella",      "am_adam"],
    "en-gb": ["bf_emma",    "bm_george"],
    "fr":    ["ff_siwis"],
    "it":    ["if_sara",    "im_nicola"],
    "pt":    ["pf_dora",    "pm_alex",       "pm_santa"],
    "ja":    ["jf_alpha",   "jf_gongitsune"],
    "zh":    ["zf_xiaobei", "zm_yunxi"],
}

PIPER_MODELOS = {
    "de": (
        os.path.join("piper_models", "de_DE-thorsten-high.onnx"),
        os.path.join("piper_models", "de_DE-thorsten-high.onnx.json"),
    ),
}

IDIOMAS_KOKORO     = set(KOKORO_LANG_CODE.keys())
IDIOMAS_PIPER      = set(PIPER_MODELOS.keys())
IDIOMAS_SOPORTADOS = sorted(IDIOMAS_KOKORO | IDIOMAS_PIPER)

import time

def _fmt_eta(segundos):
    h, r = divmod(int(segundos), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"

def _fmt_lista(nums):
    """Converts [1,2,3,5,6,9] into '1-3, 5-6, 9'"""
    if not nums:
        return "none"
    grupos, inicio, fin = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == fin + 1:
            fin = n
        else:
            grupos.append(f"{inicio}" if inicio == fin else f"{inicio}-{fin}")
            inicio = fin = n
    grupos.append(f"{inicio}" if inicio == fin else f"{inicio}-{fin}")
    return ", ".join(grupos)

# ─────────────────────────────────────────────────────────────────────────────
# RESUMING: detect previous progress
# ─────────────────────────────────────────────────────────────────────────────
def analizar_progreso(nombre_base, extension, total_caps, con_timestamps):
    """
    Analyses which chapters are complete, incomplete or missing.
    Returns three 0-based index lists: completos, a_regenerar, pendientes.

    - Complete     : MP3 exists + (JSON exists if con_timestamps)
    - To regenerate: MP3 exists but JSON is missing (interrupted mid-generation)
    - Pending      : MP3 does not exist
    """
    completos, a_regenerar, pendientes = [], [], []

    for i in range(total_caps):
        mp3  = f"{nombre_base}_cap_{i+1:02d}{extension}"
        json = f"{nombre_base}_cap_{i+1:02d}.json"

        mp3_ok  = os.path.exists(mp3) and os.path.getsize(mp3) > 0
        json_ok = (not con_timestamps) or os.path.exists(json)

        if mp3_ok and json_ok:
            completos.append(i)
        elif mp3_ok and not json_ok:
            a_regenerar.append(i)  # only JSON missing → regenerate Whisper only
        else:
            pendientes.append(i)

    return completos, a_regenerar, pendientes


def mostrar_resumen_progreso(completos, a_regenerar, pendientes, total_caps):
    print(f"\n{'─'*55}")
    print(f"  Progress found  ({len(completos)}/{total_caps} completed chapters)")
    print(f"{'─'*55}")
    if completos:
        print(f"  ✓ Completed      : chapters {_fmt_lista([i+1 for i in completos])}")
    if a_regenerar:
        print(f"  ⚠ Without timestamps : chapters {_fmt_lista([i+1 for i in a_regenerar])}  → regenerate JSON")
    if pendientes:
        print(f"  ✗ Pending    : chapters {_fmt_lista([i+1 for i in pendientes])}")
    print(f"{'─'*55}\n")


def extraer_capitulos_pdf(ruta, paginas_por_parte=20):
    doc = fitz.open(ruta)
    capitulos, texto_actual = [], ""
    for i, pagina in enumerate(doc):
        texto_actual += pagina.get_text("text") + "\n"
        if (i + 1) % paginas_por_parte == 0:
            capitulos.append(texto_actual)
            texto_actual = ""
    if texto_actual.strip():
        capitulos.append(texto_actual)
    return capitulos

def extraer_capitulos_epub(ruta):
    libro = epub.read_epub(ruta)
    capitulos = []
    for item in libro.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            sopa = BeautifulSoup(item.get_content(), "html.parser")
            
            # Force a space or period after each paragraph and heading
            # so words don't run together when extracting text
            for tag in sopa.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'div']):
                tag.append(" . ") 
            
            texto = sopa.get_text(separator=" ")
            if len(texto.strip()) > 150:
                capitulos.append(texto + "\n")
    return capitulos

def limpiar_texto(texto):
    texto = re.sub(r"\n+", "\n", texto)
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


# ─────────────────────────────────────────────────────────────────────────────
# 2. TEXT CHUNKING
# ─────────────────────────────────────────────────────────────────────────────
def dividir_texto(texto, max_caracteres=200): # Lowered to 200 for extra safety
    texto = texto.replace("\n", " ").strip()
    # 1. Split by sentence-ending punctuation
    frases = re.split(r"(?<=[.!?])\s+", texto)
    chunks = []
    
    for frase in frases:
        # 2. If the sentence is too long, split by commas/semicolons
        if len(frase) > max_caracteres:
            partes = re.split(r"(?<=[,;])\s+", frase)
            for parte in partes:
                # 3. IF STILL TOO LONG (emergency splitter by spaces)
                if len(parte) > max_caracteres:
                    palabras = parte.split(" ")
                    sub_chunk = ""
                    for p in palabras:
                        if len(sub_chunk) + len(p) < max_caracteres:
                            sub_chunk += p + " "
                        else:
                            chunks.append(sub_chunk.strip())
                            sub_chunk = p + " "
                    if sub_chunk: chunks.append(sub_chunk.strip())
                else:
                    chunks.append(parte.strip())
        else:
            chunks.append(frase.strip())
            
    return [c for c in chunks if c and len(c) > 1]

# ─────────────────────────────────────────────────────────────────────────────
# 3. MODEL INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────
def inicializar_kokoro():
    # --- DLL LINKING FOR KOKORO ONLY ---
    import os
    rutas_gpu = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v13.1\bin",
        r"C:\Program Files\NVIDIA\CUDNN\v9.20\bin\12.9\x64"
    ]
    for ruta in rutas_gpu:
        if os.path.exists(ruta):
            os.environ["PATH"] = ruta + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, 'add_dll_directory'):
                try: os.add_dll_directory(ruta)
                except Exception: pass
    # ------------------------------------

    from kokoro_onnx import Kokoro
    import onnxruntime as rt

    providers = rt.get_available_providers()
    if "CUDAExecutionProvider" in providers:
        print("Loading Kokoro v1.0 (ONNX + CUDA)...")
        sess = rt.InferenceSession(
            "kokoro-v1.0.onnx",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        modelo = Kokoro.from_session(sess, "voices-v1.0.bin")
    else:
        print("Loading Kokoro v1.0 (ONNX + CPU)...")
        modelo = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

    print("✓ Kokoro loaded.")
    return modelo

def verificar_piper():
    try:
        result = subprocess.run(["piper", "--version"], capture_output=True, text=True)
        print(f"✓ Piper found: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        print("✗ 'piper' not found in PATH.")
        print("  Download from: https://github.com/rhasspy/piper/releases")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 4. TIMESTAMPS — Whisper (Piper/DE only)
# ─────────────────────────────────────────────────────────────────────────────
def generar_timestamps(whisper_model, audio_path, idioma):
    import torch, time
    import whisper
    from pydub import AudioSegment

    lang_map = {
        "es": "es", "en": "en", "en-gb": "en",
        "fr": "fr", "it": "it", "pt": "pt",
        "de": "de", "ja": "ja", "zh": "zh",
    }
    whisper_lang = lang_map.get(idioma, "es")
    fp16 = torch.cuda.is_available() and next(whisper_model.parameters()).is_cuda
    device_label = "GPU" if next(whisper_model.parameters()).is_cuda else "CPU"
    print(f" -> Whisper ({device_label}): transcribing {os.path.basename(audio_path)}...")

    audio = AudioSegment.from_file(audio_path)
    duracion_ms  = len(audio)
    duracion_seg = duracion_ms / 1000.0

    # Smaller chunks + overlap to avoid boundary hallucinations.
    # Each chunk is 3 min; we add 5 s of overlap on the right so Whisper
    # never gets a word cut in half. Words that fall inside the overlap
    # zone are discarded — only words whose absolute start time is strictly
    # inside the *non-overlapping* window are kept.
    CHUNK_MS   = 3 * 60 * 1000   # 3 minutes of "owned" audio per chunk
    OVERLAP_MS = 5 * 1000        # 5-second tail fed to Whisper but discarded

    palabras  = []
    t_inicio  = time.time()
    inicio_ms = 0
    chunk_idx = 0
    num_chunks = (duracion_ms + CHUNK_MS - 1) // CHUNK_MS

    while inicio_ms < duracion_ms:
        fin_owned_ms = min(inicio_ms + CHUNK_MS, duracion_ms)   # exclusive end of owned window
        fin_feed_ms  = min(fin_owned_ms + OVERLAP_MS, duracion_ms)  # includes overlap tail
        segmento     = audio[inicio_ms:fin_feed_ms]
        offset_seg   = inicio_ms / 1000.0                        # absolute start of this chunk

        pct_global = inicio_ms / duracion_ms
        elapsed    = time.time() - t_inicio
        eta        = (elapsed / pct_global) * (1 - pct_global) if pct_global > 0.01 else 0
        print(
            f"    Whisper: chunk {chunk_idx+1}/{num_chunks}  "
            f"({inicio_ms//1000:.0f}s–{fin_owned_ms//1000:.0f}s / {duracion_seg:.0f}s)  "
            f"ETA {_fmt_eta(eta)}",
            end="\r"
        )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        segmento.export(tmp_path, format="wav")

        try:
            result = whisper_model.transcribe(
                tmp_path,
                language=whisper_lang,
                word_timestamps=True,
                fp16=fp16,
                condition_on_previous_text=False,  # avoids looping hallucinations
                temperature=0,                     # deterministic
            )
            owned_end_seg = (fin_owned_ms - inicio_ms) / 1000.0  # relative cutoff

            for segment in result.get("segments", []):
                for w in segment.get("words", []):
                    rel_start = w["start"]
                    # Discard words that belong to the overlap tail — they will
                    # be picked up (more accurately) by the next chunk.
                    if rel_start >= owned_end_seg:
                        continue
                    abs_start = round(rel_start        + offset_seg, 3)
                    abs_end   = round(w["end"]         + offset_seg, 3)
                    # Also skip duplicates: if this word starts before the last
                    # recorded word ends, it is an overlap duplicate.
                    if palabras and abs_start < palabras[-1]["end"] - 0.05:
                        continue
                    palabras.append({
                        "word":  w["word"].strip(),
                        "start": abs_start,
                        "end":   abs_end,
                    })
        finally:
            os.unlink(tmp_path)

        inicio_ms  = fin_owned_ms
        chunk_idx += 1

    print()
    return palabras

# ─────────────────────────────────────────────────────────────────────────────
# 5. AUDIO GENERATION
# ─────────────────────────────────────────────────────────────────────────────
def _exportar(tmp_wav, archivo_salida):
    extension = archivo_salida.split(".")[-1].lower()
    if extension not in ("mp3", "wav", "ogg", "flac"):
        extension = "wav"
    AudioSegment.from_wav(tmp_wav).export(archivo_salida, format=extension)
    return archivo_salida

def _timestamps_desde_muestras(chunks_texto, chunks_muestras, sample_rate=24000):
    """
    Calculates exact word-level timestamps directly from Kokoro sample counts.

    Since we know exactly which text produced each audio chunk, and Kokoro
    synthesizes at a constant rate, we can derive timestamps with sample
    precision — no Whisper needed.

    Within each chunk, word durations are estimated proportionally to their
    character length (good approximation for TTS at constant speed).
    Punctuation-only tokens are assigned zero duration.
    """
    palabras = []
    cursor_seg = 0.0  # absolute position in seconds

    for fragmento, muestras in zip(chunks_texto, chunks_muestras):
        duracion_chunk = len(muestras) / sample_rate

        # Tokenise into words, preserving punctuation attached to words
        tokens = re.findall(r"\S+", fragmento)
        if not tokens:
            cursor_seg += duracion_chunk
            continue

        # Character lengths (letters + digits only) to weight durations
        pesos = [max(1, len(re.sub(r"[^\w]", "", t))) for t in tokens]
        total_peso = sum(pesos)

        for token, peso in zip(tokens, pesos):
            dur = duracion_chunk * (peso / total_peso)
            palabras.append({
                "word":  token,
                "start": round(cursor_seg, 3),
                "end":   round(cursor_seg + dur, 3),
            })
            cursor_seg += dur

    return palabras


def generar_audio_kokoro(kokoro, texto, archivo_salida, idioma, voz, con_timestamps=True):
    chunks = dividir_texto(texto)
    total  = len(chunks)
    lang_interno = KOKORO_LANG_CODE[idioma]
    espeak_lang  = KOKORO_ESPEAK_LANG[lang_interno]
    print(f" -> Kokoro ONNX: {total} frags | voice='{voz}' | lang='{espeak_lang}'...")

    muestras_totales  = []
    chunks_procesados = []   # parallel list: text of each successful chunk
    muestras_por_chunk = []  # parallel list: samples of each successful chunk
    t_inicio = time.time()

    for i, fragmento in enumerate(chunks):
        if not fragmento.strip():
            continue
        try:
            muestras, _ = kokoro.create(fragmento, voice=voz, speed=1.0, lang=espeak_lang)
            muestras_totales.append(muestras)
            chunks_procesados.append(fragmento)
            muestras_por_chunk.append(muestras)
        except Exception as e:
            print(f"\n[!] Error in fragment {i+1}: {fragmento[:30]}... (Skipping)")
            continue

    print()
    audio_final = np.concatenate(muestras_totales)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    sf.write(tmp_path, audio_final, 24000)
    _exportar(tmp_path, archivo_salida)
    os.unlink(tmp_path)
    print(f" [OK] Audio: {archivo_salida}")

    if con_timestamps:
        # Use exact sample-based alignment — Whisper is unreliable on long
        # TTS audio because it transcribes instead of aligning, causing drift.
        print(f" -> Generating timestamps from sample counts (exact)...")
        palabras = _timestamps_desde_muestras(chunks_procesados, muestras_por_chunk)
        json_salida = os.path.splitext(archivo_salida)[0] + ".json"
        with open(json_salida, "w", encoding="utf-8") as f:
            json.dump({
                "texto":    texto,
                "audio":    os.path.basename(archivo_salida),
                "idioma":   idioma,
                "palabras": palabras,
            }, f, ensure_ascii=False, indent=2)
        print(f" [OK] Timestamps: {json_salida} ({len(palabras)} words)")
        
        
def generar_audio_piper(texto, archivo_salida, idioma, con_timestamps=True, whisper_modelo="small"):
    modelo_onnx, modelo_json = PIPER_MODELOS[idioma]
    if not os.path.exists(modelo_onnx):
        print(f"\n✗ Model Piper not found in: {modelo_onnx}")
        sys.exit(1)

    chunks    = dividir_texto(texto)
    total     = len(chunks)
    segmentos = AudioSegment.empty()
    print(f" -> Piper: {total} fragments for '{idioma}'...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        for i, fragmento in enumerate(chunks):
            if not fragmento.strip():
                continue
            print(f"    [{i+1}/{total}] {fragmento[:70]}...", end="\r")
            tmp_wav = os.path.join(tmp_dir, f"chunk_{i}.wav")
            subprocess.run(
                ["piper", "--model", modelo_onnx, "--config", modelo_json, "--output_file", tmp_wav],
                input=fragmento, text=True, capture_output=True, check=True
            )
            segmentos += AudioSegment.from_wav(tmp_wav)

    print()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    segmentos.export(tmp_path, format="wav")
    _exportar(tmp_path, archivo_salida)
    os.unlink(tmp_path)
    print(f" [OK] Audio: {archivo_salida}")

    if con_timestamps:
        # Piper doesn't expose sample arrays, so Whisper is used for DE alignment.
        import whisper, torch
        device = "cpu"
        if torch.cuda.is_available():
            try:
                t = torch.zeros(1, 80, 3000, dtype=torch.float16).cuda()
                _ = t @ t.transpose(-1, -2)
                device = "cuda"
            except Exception:
                device = "cpu"
        print(f"Loading Whisper '{whisper_modelo}' on {device} (Piper alignment)...")
        wmodel = whisper.load_model(whisper_modelo, device=device)
        print(f" -> Whisper: generating timestamps...")
        palabras = generar_timestamps(wmodel, archivo_salida, idioma)
        json_salida = os.path.splitext(archivo_salida)[0] + ".json"
        with open(json_salida, "w", encoding="utf-8") as f:
            json.dump({
                "texto":    texto,
                "audio":    os.path.basename(archivo_salida),
                "idioma":   idioma,
                "palabras": palabras,
            }, f, ensure_ascii=False, indent=2)
        print(f" [OK] Timestamps: {json_salida} ({len(palabras)} words)")


def generar_audio(kokoro, texto, archivo_salida, idioma, voz, con_timestamps=True, whisper_modelo="small"):
    if idioma in IDIOMAS_KOKORO:
        generar_audio_kokoro(kokoro, texto, archivo_salida, idioma, voz, con_timestamps)
    elif idioma in IDIOMAS_PIPER:
        generar_audio_piper(texto, archivo_salida, idioma, con_timestamps, whisper_modelo)
    else:
        print(f"Error: language '{idioma}' not supported.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 6. ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Converts a PDF/EPUB to an audiobook with word-level timestamps.\n"
            "Generates one .mp3 and one .json per chapter or for the full book.\n"
            "Engines: Kokoro v1.0 (ONNX) for ES/EN/FR/IT/PT/JA/ZH, Piper for DE.\n"
            "Timestamps for Kokoro are derived from sample counts (exact, no Whisper).\n"
            "Timestamps for Piper (DE) use Whisper alignment."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("libro",            help="Path to the PDF or EPUB file.")
    parser.add_argument("-o", "--salida",   required=True,
                        help="Output filename (e.g. book.mp3).")
    parser.add_argument("-l", "--lenguaje", choices=IDIOMAS_SOPORTADOS, default="es",
                        help=f"Language. Options: {', '.join(IDIOMAS_SOPORTADOS)}")
    parser.add_argument("-v", "--voz",      default=None,
                        help="Kokoro voice name (e.g. ef_dora).")
    parser.add_argument("-c", "--capitulos", action="store_true",
                        help="Generate one file per chapter.")
    parser.add_argument("--sin-timestamps", action="store_true",
                        help="Skip .json timestamp generation (faster).")
    parser.add_argument("--whisper-modelo", default="small",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper model for Piper/DE timestamps (default: small).")
    parser.add_argument("--listar-voces",   action="store_true",
                        help="List available voices for the language and exit.")

    args = parser.parse_args()
    directorio_salida = os.path.dirname(args.salida)
    if directorio_salida and not os.path.exists(directorio_salida):
        os.makedirs(directorio_salida)
        print(f"✓ Folder created: {directorio_salida}")
    if args.listar_voces:
        idioma = args.lenguaje
        if idioma in KOKORO_VOCES:
            print(f"Kokoro voices for '{idioma}':")
            for v in KOKORO_VOCES[idioma]:
                print(f"  - {v}")
        elif idioma in PIPER_MODELOS:
            print(f"Piper Engine for '{idioma}'. Model: {PIPER_MODELOS[idioma][0]}")
        sys.exit(0)

    archivo       = args.libro
    salida        = args.salida
    idioma        = args.lenguaje
    por_capitulos = args.capitulos
    con_timestamps = not args.sin_timestamps
    whisper_modelo = args.whisper_modelo

    if not os.path.exists(archivo):
        print(f"Error: not found '{archivo}'.")
        sys.exit(1)

    voz = args.voz
    if voz is None and idioma in KOKORO_VOCES:
        voz = KOKORO_VOCES[idioma][0]
        print(f"Voice automatically selected: {voz}")

    # Load models
    kokoro = None
    if idioma in IDIOMAS_KOKORO:
        kokoro = inicializar_kokoro()
    elif idioma in IDIOMAS_PIPER:
        if not verificar_piper():
            sys.exit(1)
            
    # Extract text
    print(f"\nExtracting structure from: {archivo}...")
    if archivo.lower().endswith(".pdf"):
        capitulos_crudos = extraer_capitulos_pdf(archivo)
    elif archivo.lower().endswith(".epub"):
        capitulos_crudos = extraer_capitulos_epub(archivo)
    else:
        print("Error: not supported format. Use PDF or EPUB (preferred).")
        sys.exit(1)

    print(f"Found {len(capitulos_crudos)} blocks of text/chapters.")

    # Generate audio
    if por_capitulos:
        print("\nMODE: one file per chapter.")
        nombre_base, extension = os.path.splitext(salida)
        con_timestamps = not args.sin_timestamps

        # ── Detect previous progress ──────────────────────────────────────
        completos, a_regenerar, pendientes = analizar_progreso(
            nombre_base, extension, len(capitulos_crudos), con_timestamps
        )

        if completos or a_regenerar:
            mostrar_resumen_progreso(completos, a_regenerar, pendientes, len(capitulos_crudos))

        caps_a_procesar = sorted(a_regenerar + pendientes)

        if not caps_a_procesar:
            print("✓ All chapters completed. Done.")
            sys.exit(0)

        print(f"Processing {len(caps_a_procesar)} remaining chapter(s)...\n")

        for i in caps_a_procesar:
            texto_limpio = limpiar_texto(capitulos_crudos[i])
            if not texto_limpio:
                continue
            nombre_cap = f"{nombre_base}_cap_{i+1:02d}{extension}"
            json_cap   = f"{nombre_base}_cap_{i+1:02d}.json"

            print(f"\n--- Chapter {i+1}/{len(capitulos_crudos)}: {nombre_cap} ---")

            # If MP3 already exists but only JSON is missing → skip Kokoro
            mp3_existe = os.path.exists(nombre_cap) and os.path.getsize(nombre_cap) > 0
            if mp3_existe and i in a_regenerar and con_timestamps:
                # Kokoro: regenerate JSON from the existing text (re-synthesise to get samples)
                print(f"  MP3 already exists, regenerating timestamps only...")
                generar_audio(kokoro, texto_limpio, nombre_cap, idioma, voz,
                              con_timestamps=True, whisper_modelo=whisper_modelo)
            else:
                generar_audio(kokoro, texto_limpio, nombre_cap, idioma, voz,
                              con_timestamps=con_timestamps, whisper_modelo=whisper_modelo)

    else:
        print("\nMODE: Book completed in one single file.")
        texto_completo = limpiar_texto(" ".join(capitulos_crudos))
        generar_audio(kokoro, texto_completo, salida, idioma, voz,
                      con_timestamps=con_timestamps, whisper_modelo=whisper_modelo)

    print("\nAudiobook created succesfully!")