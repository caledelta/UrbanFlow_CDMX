import pytest
from unittest.mock import patch, MagicMock
from src.agent.voice_io import transcribir_audio, sintetizar_voz


def test_transcribir_audio_vacio():
    assert transcribir_audio(b"") == ""

def test_transcribir_audio_mock():
    fake = MagicMock()
    fake.text = "Llévame de Polanco al AICM"
    with patch("src.agent.voice_io._client.audio.transcriptions.create", return_value=fake):
        assert transcribir_audio(b"fake_bytes") == "Llévame de Polanco al AICM"

def test_sintetizar_voz_vacio():
    assert sintetizar_voz("") == b""

def test_sintetizar_voz_mock():
    fake = MagicMock()
    fake.content = b"ID3fakeaudio"
    with patch("src.agent.voice_io._client.audio.speech.create", return_value=fake):
        assert sintetizar_voz("Tu ruta tarda 32 minutos") == b"ID3fakeaudio"

def test_sintetizar_voz_trunca_500():
    fake = MagicMock()
    fake.content = b"audio"
    with patch("src.agent.voice_io._client.audio.speech.create", return_value=fake) as mock:
        sintetizar_voz("x" * 1000)
        kwargs = mock.call_args.kwargs
        assert len(kwargs["input"]) == 500
