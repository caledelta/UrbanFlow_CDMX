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
    """TTS OpenAI. Retorna None si no hay API key o falla cuota."""
    if not texto:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        r = _get_openai_client().audio.speech.create(
            model=MODEL_TTS, voice=VOICE, input=texto[:500]
        )
        return r.content
    except Exception as e:
        logger.warning("TTS falló (%s). Continuando sin audio.", e)
        return None
