"""
tests/test_telemetria.py — Tests unitarios para src/core/telemetria.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.telemetria import (
    registrar_evento,
    incrementar_uso_ruta,
    obtener_stats_usuario,
    guardar_perfil,
    cargar_perfil,
    registrar_feedback,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — redirigir archivos a tmp_path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _patch_paths(tmp_path, monkeypatch):
    import src.core.telemetria as tel
    monkeypatch.setattr(tel, "DATA_DIR",      tmp_path)
    monkeypatch.setattr(tel, "EVENTS_FILE",   tmp_path / "eventos.jsonl")
    monkeypatch.setattr(tel, "PROFILE_FILE",  tmp_path / "perfil_usuario.json")
    monkeypatch.setattr(tel, "STATS_FILE",    tmp_path / "stats_rutas.json")


# ─────────────────────────────────────────────────────────────────────────────
# registrar_evento
# ─────────────────────────────────────────────────────────────────────────────

def test_registrar_evento_crea_jsonl(tmp_path):
    registrar_evento("test", {"x": 1})
    content = (tmp_path / "eventos.jsonl").read_text(encoding="utf-8")
    assert '"tipo": "test"' in content
    assert '"x": 1' in content


def test_registrar_evento_append(tmp_path):
    registrar_evento("a", {"n": 1})
    registrar_evento("b", {"n": 2})
    lines = (tmp_path / "eventos.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["tipo"] == "a"
    assert json.loads(lines[1])["tipo"] == "b"


def test_registrar_evento_tiene_ts_y_session(tmp_path):
    registrar_evento("check", {})
    ev = json.loads((tmp_path / "eventos.jsonl").read_text(encoding="utf-8"))
    assert "ts" in ev
    assert "session_id" in ev


# ─────────────────────────────────────────────────────────────────────────────
# incrementar_uso_ruta
# ─────────────────────────────────────────────────────────────────────────────

def test_incremento_ruta(tmp_path):
    n1 = incrementar_uso_ruta("Polanco", "AICM")
    n2 = incrementar_uso_ruta("Polanco", "AICM")
    assert n1 == 1
    assert n2 == 2


def test_incremento_ruta_distinta(tmp_path):
    incrementar_uso_ruta("A", "B")
    n = incrementar_uso_ruta("A", "C")
    assert n == 1   # par distinto, contador propio


def test_obtener_stats(tmp_path):
    incrementar_uso_ruta("X", "Y")
    incrementar_uso_ruta("X", "Y")
    incrementar_uso_ruta("P", "Q")
    stats = obtener_stats_usuario()
    assert stats["total_consultas"] == 3
    assert stats["rutas_unicas"] == 2
    assert stats["top_5_rutas"][0][0] == "X → Y"
    assert stats["top_5_rutas"][0][1] == 2


# ─────────────────────────────────────────────────────────────────────────────
# perfil
# ─────────────────────────────────────────────────────────────────────────────

def test_perfil_round_trip(tmp_path):
    guardar_perfil({"tipo": "Uber Eats", "edad": 28})
    cargado = cargar_perfil()
    assert cargado["tipo"] == "Uber Eats"
    assert cargado["edad"] == 28


def test_cargar_perfil_vacio(tmp_path):
    assert cargar_perfil() == {}


# ─────────────────────────────────────────────────────────────────────────────
# registrar_feedback
# ─────────────────────────────────────────────────────────────────────────────

def test_registrar_feedback_rating(tmp_path):
    registrar_feedback(rating=5)
    ev = json.loads((tmp_path / "eventos.jsonl").read_text(encoding="utf-8"))
    assert ev["tipo"] == "feedback"
    assert ev["rating"] == 5


def test_registrar_feedback_exactitud(tmp_path):
    registrar_feedback(
        rating=None,
        exactitud="exacto",
        tiempo_real_min=12.5,
        tiempo_predicho_min=11.0,
    )
    ev = json.loads((tmp_path / "eventos.jsonl").read_text(encoding="utf-8"))
    assert ev["exactitud"] == "exacto"
    assert ev["tiempo_real_min"] == 12.5
