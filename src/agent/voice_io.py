"""
voice_io.py — Entrada/salida por voz para VialAI.
Usa OpenAI Whisper para STT y OpenAI TTS para respuesta hablada.
Basado en el patrón de main_04.py del Prof. Fernando Barranco,
adaptado al tool use loop de Anthropic Claude.
"""
import os
from io import BytesIO
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL_STT = "whisper-1"
MODEL_TTS = "tts-1"
VOICE = "nova"  # alternativas: alloy, echo, fable, onyx, shimmer


def transcribir_audio(audio_bytes: bytes, filename: str = "voz_vialai.mp3") -> str:
    """
    Transcribe audio a texto usando Whisper-1.
    Optimizado para español mexicano con vocabulario vial de CDMX.
    """
    if not audio_bytes:
        return ""
    audio_file = BytesIO(audio_bytes)
    audio_file.name = filename
    transcription = _client.audio.transcriptions.create(
        model=MODEL_STT,
        file=audio_file,
        language="es",
        prompt=(
            "Conductor en CDMX pidiendo rutas. Vocabulario: Polanco, "
            "Santa Fe, Periférico, Viaducto, Circuito Interior, Insurgentes, "
            "Reforma, Tlalpan, Coyoacán, AICM, Auditorio Nacional, "
            "Zócalo, WTC, Satélite, Ecatepec, Iztapalapa."
        ),
    )
    return (transcription.text or "").strip()


def sintetizar_voz(texto: str) -> bytes:
    """
    Convierte texto a audio MP3 usando TTS-1.
    Retorna bytes listos para st.audio().
    """
    if not texto:
        return b""
    # Limitar longitud para latencia < 2s
    texto_corto = texto[:500]
    response = _client.audio.speech.create(
        model=MODEL_TTS,
        voice=VOICE,
        input=texto_corto,
    )
    return response.content
