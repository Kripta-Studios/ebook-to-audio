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
# CONFIGURACIÓN DE IDIOMAS, MOTORES Y VOCES
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

# Modelo Whisper para timestamps (se descarga automáticamente la primera vez)
WHISPER_MODEL = "medium"

import time

def _fmt_eta(segundos):
    h, r = divmod(int(segundos), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"

def _fmt_lista(nums):
    """Convierte [1,2,3,5,6,9] en '1-3, 5-6, 9'"""
    if not nums:
        return "ninguno"
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
# REANUDACIÓN: detectar progreso previo
# ─────────────────────────────────────────────────────────────────────────────
def analizar_progreso(nombre_base, extension, total_caps, con_timestamps):
    """
    Analiza qué capítulos están completos, incompletos o faltantes.
    Devuelve tres listas de índices 0-based: completos, a_regenerar, pendientes.

    - Completo    : MP3 existe + (JSON existe si con_timestamps)
    - A regenerar : MP3 existe pero falta el JSON (interrumpido entre audio y Whisper)
    - Pendiente   : MP3 no existe
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
            a_regenerar.append(i)  # solo falta el JSON → regenerar solo Whisper
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
        print(f"  ⚠ Without timestamps : chapters {_fmt_lista([i+1 for i in a_regenerar])}  → only Whisper")
    if pendientes:
        print(f"  ✗ Left     : chapters {_fmt_lista([i+1 for i in pendientes])}")
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
            
            # Forzamos un espacio o punto tras cada párrafo y encabezado 
            # para que no se peguen las palabras al extraer el texto
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
# 2. CHUNKING DE TEXTO
# ─────────────────────────────────────────────────────────────────────────────
def dividir_texto(texto, max_caracteres=200): # Bajamos a 200 para mayor seguridad
    texto = texto.replace("\n", " ").strip()
    # 1. Dividir por puntos
    frases = re.split(r"(?<=[.!?])\s+", texto)
    chunks = []
    
    for frase in frases:
        # 2. Si la frase es muy larga, dividir por comas/puntos y coma
        if len(frase) > max_caracteres:
            partes = re.split(r"(?<=[,;])\s+", frase)
            for parte in partes:
                # 3. SI AÚN ASÍ ES LARGA (Divisor de emergencia por espacios)
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
# 3. INICIALIZACIÓN DE MODELOS
# ─────────────────────────────────────────────────────────────────────────────
def inicializar_kokoro():
    # --- VINCULACIÓN SOLO PARA KOKORO ---
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
        print("Loading  Kokoro v1.0 (ONNX + CUDA)...")
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

def inicializar_whisper():
    import whisper, torch
    device = "cpu"
    if torch.cuda.is_available():
        try:
            # Prueba real: operación que Whisper necesita
            t = torch.zeros(1, 80, 3000, dtype=torch.float16).cuda()
            _ = t @ t.transpose(-1, -2)
            device = "cuda"
        except Exception as e:
            print(f"⚠ CUDA not available for Whisper ({e.__class__.__name__}), using CPU.")
            device = "cpu"
    print(f"Loading Whisper '{WHISPER_MODEL}' en {device}...")
    try:
        modelo = whisper.load_model(WHISPER_MODEL, device=device)
    except Exception as e:
        print(f"⚠ Error loading in {device} ({e}), using CPU.")
        modelo = whisper.load_model(WHISPER_MODEL, device="cpu")
    print("✓ Whisper loaded.")
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
# 4. TIMESTAMPS CON WHISPER
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
    dispositivo = "GPU" if next(whisper_model.parameters()).is_cuda else "CPU"
    print(f" -> Whisper ({dispositivo}): transcribing {os.path.basename(audio_path)}...")

    audio = AudioSegment.from_file(audio_path)
    duracion_ms = len(audio)
    duracion_seg = duracion_ms / 1000.0

    CHUNK_MS = 10 * 60 * 1000  # 10 minutos por segmento
    palabras = []
    offset_seg = 0.0
    t_inicio = time.time()

    num_chunks = (duracion_ms + CHUNK_MS - 1) // CHUNK_MS
    for idx in range(num_chunks):
        inicio_ms = idx * CHUNK_MS
        fin_ms    = min(inicio_ms + CHUNK_MS, duracion_ms)
        segmento  = audio[inicio_ms:fin_ms]

        pct_global = inicio_ms / duracion_ms
        elapsed    = time.time() - t_inicio
        eta        = (elapsed / pct_global) * (1 - pct_global) if pct_global > 0.01 else 0
        print(
            f"    Whisper: chunk {idx+1}/{num_chunks}  "
            f"({inicio_ms//1000:.0f}s–{fin_ms//1000:.0f}s / {duracion_seg:.0f}s)  "
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
                condition_on_previous_text=False,  # evita alucinaciones en bucle
                temperature=0,                     # determinista
            )
            for segment in result.get("segments", []):
                for w in segment.get("words", []):
                    palabras.append({
                        "word":  w["word"].strip(),
                        "start": round(w["start"] + offset_seg, 3),
                        "end":   round(w["end"]   + offset_seg, 3),
                    })
        finally:
            os.unlink(tmp_path)

        offset_seg = fin_ms / 1000.0

    print()
    return palabras

# ─────────────────────────────────────────────────────────────────────────────
# 5. GENERACIÓN DE AUDIO
# ─────────────────────────────────────────────────────────────────────────────
def _exportar(tmp_wav, archivo_salida):
    extension = archivo_salida.split(".")[-1].lower()
    if extension not in ("mp3", "wav", "ogg", "flac"):
        extension = "wav"
    AudioSegment.from_wav(tmp_wav).export(archivo_salida, format=extension)
    return archivo_salida

def generar_audio_kokoro(kokoro, whisper_model, texto, archivo_salida, idioma, voz):
    chunks = dividir_texto(texto)
    total  = len(chunks)
    lang_interno = KOKORO_LANG_CODE[idioma]
    espeak_lang  = KOKORO_ESPEAK_LANG[lang_interno]
    print(f" -> Kokoro ONNX: {total} frags | voice='{voz}' | lang='{espeak_lang}'...")

    muestras_totales = []
    t_inicio = time.time()

    for i, fragmento in enumerate(chunks):
        if not fragmento.strip():
            continue
        
        try:
            muestras, _ = kokoro.create(fragmento, voice=voz, speed=1.0, lang=espeak_lang)
            muestras_totales.append(muestras)
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

    if whisper_model is not None:
        print(f" -> Whisper: generating timestamps...")
        palabras = generar_timestamps(whisper_model, archivo_salida, idioma)
        json_salida = os.path.splitext(archivo_salida)[0] + ".json"
        with open(json_salida, "w", encoding="utf-8") as f:
            json.dump({
                "texto":    texto,
                "audio":    os.path.basename(archivo_salida),
                "idioma":   idioma,
                "palabras": palabras,
            }, f, ensure_ascii=False, indent=2)
        print(f" [OK] Timestamps: {json_salida} ({len(palabras)} words)")
        
        
def generar_audio_piper(whisper_model, texto, archivo_salida, idioma):
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

    if whisper_model is not None:
        print(f" -> Whisper: generating timestamps...")
        palabras = generar_timestamps(whisper_model, archivo_salida, idioma)
        json_salida = os.path.splitext(archivo_salida)[0] + ".json"
        with open(json_salida, "w", encoding="utf-8") as f:
            json.dump({
                "texto":    texto,
                "audio":    os.path.basename(archivo_salida),
                "idioma":   idioma,
                "palabras": palabras,
            }, f, ensure_ascii=False, indent=2)
        print(f" [OK] Timestamps: {json_salida} ({len(palabras)} words")


def generar_audio(kokoro, whisper_model, texto, archivo_salida, idioma, voz):
    if idioma in IDIOMAS_KOKORO:
        generar_audio_kokoro(kokoro, whisper_model, texto, archivo_salida, idioma, voz)
    elif idioma in IDIOMAS_PIPER:
        generar_audio_piper(whisper_model, texto, archivo_salida, idioma)
    else:
        print(f"Error: language '{idioma}' not supported.")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# 6. PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Convierte un PDF/EPUB a audiolibro con timestamps de palabra.\n"
            "Genera un .mp3 y un .json por cada capítulo o libro completo.\n"
            "Motores: Kokoro v1.0 (ONNX) para ES/EN/FR/IT/PT/JA/ZH, Piper para DE."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("libro",            help="Ruta al archivo PDF o EPUB.")
    parser.add_argument("-o", "--salida",   required=True,
                        help="Nombre del archivo resultante (ej. libro.mp3).")
    parser.add_argument("-l", "--lenguaje", choices=IDIOMAS_SOPORTADOS, default="es",
                        help=f"Idioma. Opciones: {', '.join(IDIOMAS_SOPORTADOS)}")
    parser.add_argument("-v", "--voz",      default=None,
                        help="Nombre de voz Kokoro (ej. ef_dora).")
    parser.add_argument("-c", "--capitulos", action="store_true",
                        help="Genera un archivo por capítulo.")
    parser.add_argument("--sin-timestamps", action="store_true",
                        help="No generar .json de timestamps (más rápido).")
    parser.add_argument("--whisper-modelo", default=WHISPER_MODEL,
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Modelo Whisper para timestamps (default: base).")
    parser.add_argument("--listar-voces",   action="store_true",
                        help="Muestra las voces disponibles para el idioma y termina.")

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
    WHISPER_MODEL = args.whisper_modelo

    if not os.path.exists(archivo):
        print(f"Error: not found '{archivo}'.")
        sys.exit(1)

    voz = args.voz
    if voz is None and idioma in KOKORO_VOCES:
        voz = KOKORO_VOCES[idioma][0]
        print(f"Voice automatically selected: {voz}")

    # Cargar modelos
    

    whisper_model = None
    if not args.sin_timestamps:
        whisper_model = inicializar_whisper()

    kokoro = None
    if idioma in IDIOMAS_KOKORO:
        kokoro = inicializar_kokoro()
    elif idioma in IDIOMAS_PIPER:
        if not verificar_piper():
            sys.exit(1)
            
    # Extraer texto
    print(f"\nExtracting structure from: {archivo}...")
    if archivo.lower().endswith(".pdf"):
        capitulos_crudos = extraer_capitulos_pdf(archivo)
    elif archivo.lower().endswith(".epub"):
        capitulos_crudos = extraer_capitulos_epub(archivo)
    else:
        print("Error: not supported format. Use PDF or EPUB (preferred).")
        sys.exit(1)

    print(f"Found {len(capitulos_crudos)} blocks of text/chapters.")

    # Generar audio
    if por_capitulos:
        print("\nMODE: un file per chapter.")
        nombre_base, extension = os.path.splitext(salida)
        con_timestamps = not args.sin_timestamps

        # ── Detectar progreso previo ──────────────────────────────────────
        completos, a_regenerar, pendientes = analizar_progreso(
            nombre_base, extension, len(capitulos_crudos), con_timestamps
        )

        if completos or a_regenerar:
            mostrar_resumen_progreso(completos, a_regenerar, pendientes, len(capitulos_crudos))

        caps_a_procesar = sorted(a_regenerar + pendientes)

        if not caps_a_procesar:
            print("✓ Al chapterse completed. Finish.")
            sys.exit(0)

        print(f"Processing {len(caps_a_procesar)} chapter(s) left(s)...\n")

        for i in caps_a_procesar:
            texto_limpio = limpiar_texto(capitulos_crudos[i])
            if not texto_limpio:
                continue
            nombre_cap = f"{nombre_base}_cap_{i+1:02d}{extension}"
            json_cap   = f"{nombre_base}_cap_{i+1:02d}.json"

            print(f"\n--- Chapter {i+1}/{len(capitulos_crudos)}: {nombre_cap} ---")

            # Si el MP3 ya existe pero solo falta el JSON → saltar Kokoro
            mp3_existe = os.path.exists(nombre_cap) and os.path.getsize(nombre_cap) > 0
            if mp3_existe and i in a_regenerar and whisper_model is not None:
                print(f"  MP3 already exists, generating only timestamps...")
                palabras = generar_timestamps(whisper_model, nombre_cap, idioma)
                with open(json_cap, "w", encoding="utf-8") as f:
                    json.dump({
                        "texto":    texto_limpio,
                        "audio":    os.path.basename(nombre_cap),
                        "idioma":   idioma,
                        "palabras": palabras,
                    }, f, ensure_ascii=False, indent=2)
                print(f" [OK] Timestamps: {json_cap} ({len(palabras)} words)")
            else:
                generar_audio(kokoro, whisper_model, texto_limpio, nombre_cap, idioma, voz)

    else:
        print("\nMODE: Book completed in one single file.")
        texto_completo = limpiar_texto(" ".join(capitulos_crudos))
        generar_audio(kokoro, whisper_model, texto_completo, salida, idioma, voz)

    print("\nAudiobook created succesfully!")
