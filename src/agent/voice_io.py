"""
voice_io.py — Entrada/salida por voz para VialAI.
Soporta dos backends para STT:
  - "openai": Whisper-1 vía API (requiere OPENAI_API_KEY + créditos)
  - "local":  faster-whisper en CPU (gratuito, sin red)
TTS usa OpenAI tts-1 si hay API key; si no, retorna None (sin audio).
"""
import os
import logging
from io import BytesIO
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger(__name__)

STT_BACKEND = os.getenv("VIALAI_STT_BACKEND", "local").lower()  # "local" | "openai"
TTS_BACKEND = os.getenv("VIALAI_TTS_BACKEND", "openai").lower()  # "openai" | "local" | "off"
MODEL_STT_OPENAI = "whisper-1"
MODEL_STT_LOCAL = "base"  # tiny | base | small | medium
MODEL_TTS = "tts-1"
VOICE = "nova"

_openai_client = None
_local_model = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        logger.info("Cargando faster-whisper '%s' en CPU...", MODEL_STT_LOCAL)
        _local_model = WhisperModel(MODEL_STT_LOCAL, device="cpu", compute_type="int8")
    return _local_model


CONTEXTO_CDMX = (
    "Conductor en CDMX pidiendo rutas. Vocabulario: Polanco, Santa Fe, "
    "Periférico, Viaducto, Circuito Interior, Insurgentes, Reforma, "
    "Tlalpan, Coyoacán, AICM, Auditorio Nacional, Zócalo, WTC, Satélite, "
    "Ecatepec, Iztapalapa."
)


class VoiceError(Exception):
    """Error de voz con mensaje amigable para el usuario."""
    def __init__(self, user_msg: str, technical: str = ""):
        super().__init__(technical or user_msg)
        self.user_msg = user_msg


def transcribir_audio(audio_bytes: bytes, filename: str = "voz_vialai.mp3") -> str:
    if not audio_bytes:
        return ""
    try:
        if STT_BACKEND == "openai":
            return _transcribir_openai(audio_bytes, filename)
        return _transcribir_local(audio_bytes, filename)
    except VoiceError:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "insufficient_quota" in msg or "429" in msg:
            raise VoiceError(
                "Sin créditos en OpenAI. Cambia VIALAI_STT_BACKEND=local en .env "
                "para usar transcripción gratuita, o recarga en platform.openai.com.",
                str(e),
            )
        if "api_key" in msg or "authentication" in msg:
            raise VoiceError("API key de OpenAI inválida o ausente.", str(e))
        raise VoiceError(f"No pude transcribir el audio: {e}", str(e))


def _transcribir_openai(audio_bytes: bytes, filename: str) -> str:
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename
    r = _get_openai_client().audio.transcriptions.create(
        model=MODEL_STT_OPENAI,
        file=audio_file,
        language="es",
        prompt=CONTEXTO_CDMX,
    )
    return (r.text or "").strip()


def _transcribir_local(audio_bytes: bytes, filename: str) -> str:
    import tempfile, os as _os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        segments, _info = _get_local_model().transcribe(
            tmp_path, language="es", initial_prompt=CONTEXTO_CDMX, beam_size=5,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()
    finally:
        try: _os.unlink(tmp_path)
        except OSError: pass


def sintetizar_voz(texto: str) -> bytes | None:
    """
    TTS con fallback. Retorna bytes MP3/WAV o None si falla/desactivado.
    Backends: 'openai' (tts-1), 'local' (pyttsx3 SAPI5), 'off'.
    """
    if not texto or TTS_BACKEND == "off":
        return None
    texto_corto = texto[:500]

    if TTS_BACKEND == "local":
        return _tts_local(texto_corto)

    # Backend openai con fallback automático a local si falla
    try:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("Sin OPENAI_API_KEY")
        r = _get_openai_client().audio.speech.create(
            model=MODEL_TTS, voice=VOICE, input=texto_corto
        )
        return r.content
    except Exception as e:
        logger.warning("TTS OpenAI falló (%s). Intentando local...", e)
        return _tts_local(texto_corto)


def _tts_local(texto: str) -> bytes | None:
    """TTS Windows SAPI5 vía pyttsx3. Voz es-MX si está disponible."""
    try:
        import pyttsx3
        import tempfile
        import os as _os
        engine = pyttsx3.init()
        # Intentar voz en español
        for voice in engine.getProperty("voices"):
            if "spanish" in voice.name.lower() or "español" in voice.name.lower() \
               or "es-" in (voice.id or "").lower():
                engine.setProperty("voice", voice.id)
                break
        engine.setProperty("rate", 180)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        engine.save_to_file(texto, tmp_path)
        engine.runAndWait()
        with open(tmp_path, "rb") as f:
            data = f.read()
        try: _os.unlink(tmp_path)
        except OSError: pass
        return data
    except Exception as e:
        logger.warning("TTS local falló (%s). Continuando sin audio.", e)
        return None


# ── Síntesis limpia para TTS ─────────────────────────────────────────────────

import re


def limpiar_para_tts(texto: str) -> str:
    """
    Limpia markdown y símbolos que TTS leería literalmente ("asterisco").
    Deja solo palabras y puntuación natural que el sintetizador entona bien.
    """
    if not texto:
        return ""
    t = texto
    # Quitar bloques de código y backticks
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    # Quitar headers markdown (# ## ###)
    t = re.sub(r"^#{1,6}\s*", "", t, flags=re.MULTILINE)
    # Quitar negritas/cursivas **texto**, __texto__, *texto*, _texto_
    t = re.sub(r"\*\*\*([^\*]+)\*\*\*", r"\1", t)
    t = re.sub(r"\*\*([^\*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^\*]+)\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    t = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", t)
    # Quitar enlaces [texto](url) → texto
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    # Quitar viñetas y guiones de lista
    t = re.sub(r"^\s*[-•*]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    # Símbolos residuales molestos
    t = t.replace("→", " a ").replace("·", ",").replace("—", ",").replace("–", ",")
    t = t.replace("#", "").replace("*", "").replace("~", "").replace("|", "")
    # Colapsar espacios y saltos múltiples
    t = re.sub(r"\n{2,}", ". ", t)
    t = re.sub(r"\n", " ", t)
    t = re.sub(r"\s{2,}", " ", t)
    # Asegurar punto final para entonación natural
    t = t.strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


def resumen_para_voz(respuesta_completa: str) -> str:
    """
    Genera un resumen hablable de ~25 palabras con lo esencial:
    distancia, P50, incertidumbre, y perturbaciones relevantes.
    Usa Claude Haiku por velocidad y costo.
    """
    if not respuesta_completa:
        return ""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        prompt = (
            "Eres un copiloto de voz para conductores en CDMX. "
            "Resume la siguiente respuesta en UNA sola oración natural "
            "de máximo 30 palabras, en español neutro, sin markdown, sin "
            "símbolos, sin listas, sin números entre paréntesis. Incluye "
            "SOLO: distancia en kilómetros, tiempo estimado P50 en "
            "minutos, y si hay alguna perturbación o evento relevante. "
            "No saludes, no despidas, no digas 'tu ruta' — ve directo al "
            "dato. Ejemplo del tono esperado: 'Son 12 kilómetros, "
            "tardarás unos 26 minutos, hay tráfico ligero en Periférico.'"
            "\n\nRespuesta a resumir:\n" + respuesta_completa[:2000]
        )
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = msg.content[0].text if msg.content else ""
        return limpiar_para_tts(texto)
    except Exception as e:
        logger.warning("Resumen para voz falló (%s). Usando limpieza simple.", e)
        # Fallback: limpiar el original y tomar las primeras 2 oraciones
        limpio = limpiar_para_tts(respuesta_completa)
        oraciones = re.split(r"(?<=[.!?])\s+", limpio)
        return " ".join(oraciones[:2])[:400]
