import os
import pytest
from unittest.mock import patch, MagicMock
from src.agent import voice_io
from src.agent.voice_io import VoiceError, transcribir_audio, sintetizar_voz, limpiar_para_tts


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_openai_client():
    """Devuelve un cliente OpenAI mockeado listo para parchear."""
    return MagicMock()


# ── STT — vacío ───────────────────────────────────────────────────────────────

def test_transcribir_audio_vacio():
    assert transcribir_audio(b"") == ""


# ── STT — backend openai ──────────────────────────────────────────────────────

def test_transcribir_audio_mock_openai():
    voice_io.STT_BACKEND = "openai"
    fake_resp = MagicMock()
    fake_resp.text = "Llévame de Polanco al AICM"
    client = _mock_openai_client()
    client.audio.transcriptions.create.return_value = fake_resp
    with patch.object(voice_io, "_get_openai_client", return_value=client):
        result = transcribir_audio(b"fake_bytes")
    assert result == "Llévame de Polanco al AICM"


# ── TTS — vacío y sin key ─────────────────────────────────────────────────────

def test_sintetizar_voz_vacio():
    assert sintetizar_voz("") is None


def test_tts_sin_api_key_usa_fallback_local(monkeypatch):
    """Sin API key openai debe caer al backend local (pyttsx3)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import src.agent.voice_io as vio
    vio.TTS_BACKEND = "openai"
    with patch.object(vio, "_tts_local", return_value=b"RIFF_fake_wav") as mock_local:
        result = sintetizar_voz("hola")
    mock_local.assert_called_once_with("hola")
    assert result == b"RIFF_fake_wav"


# ── TTS — mock con key ────────────────────────────────────────────────────────

def test_sintetizar_voz_mock(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_resp = MagicMock()
    fake_resp.content = b"ID3fakeaudio"
    client = _mock_openai_client()
    client.audio.speech.create.return_value = fake_resp
    with patch.object(voice_io, "_get_openai_client", return_value=client):
        result = sintetizar_voz("Tu ruta tarda 32 minutos")
    assert result == b"ID3fakeaudio"


def test_sintetizar_voz_trunca_500(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake_resp = MagicMock()
    fake_resp.content = b"audio"
    client = _mock_openai_client()
    client.audio.speech.create.return_value = fake_resp
    with patch.object(voice_io, "_get_openai_client", return_value=client) as _:
        sintetizar_voz("x" * 1000)
    kwargs = client.audio.speech.create.call_args.kwargs
    assert len(kwargs["input"]) == 500


# ── Error handling ────────────────────────────────────────────────────────────

def test_tts_backend_off():
    import src.agent.voice_io as vio
    vio.TTS_BACKEND = "off"
    assert vio.sintetizar_voz("hola") is None


def test_quota_error_lanza_voice_error():
    voice_io.STT_BACKEND = "openai"
    client = _mock_openai_client()
    client.audio.transcriptions.create.side_effect = Exception("Error 429 insufficient_quota")
    with patch.object(voice_io, "_get_openai_client", return_value=client):
        with pytest.raises(VoiceError) as exc_info:
            transcribir_audio(b"xxx")
    assert "créditos" in exc_info.value.user_msg.lower()


# ── limpiar_para_tts ──────────────────────────────────────────────────────────

def test_limpiar_quita_markdown_basico():
    t = "**Ruta:** Polanco → AICM\n\n- 12 km\n- 26 min"
    out = limpiar_para_tts(t)
    assert "**" not in out
    assert "*" not in out
    assert "→" not in out
    assert " a " in out  # el → se convierte en "a"
    assert "12 km" in out
    assert "26 min" in out

def test_limpiar_quita_headers_y_backticks():
    t = "## Resultados\n`P50=26` minutos"
    out = limpiar_para_tts(t)
    assert "#" not in out
    assert "`" not in out
    assert "P50=26" in out

def test_limpiar_cadena_vacia():
    assert limpiar_para_tts("") == ""
    assert limpiar_para_tts(None) == ""

def test_limpiar_asegura_punto_final():
    assert limpiar_para_tts("Hola mundo").endswith(".")
    assert limpiar_para_tts("¿Cuánto tardo?").endswith("?")
