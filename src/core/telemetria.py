"""
src/core/telemetria.py — Telemetría local de VialAI.

Guarda eventos de uso en data/telemetry/eventos.jsonl (append-only).
Arquitectura diseñada para migrar a endpoint externo en producción sin
cambiar la interfaz pública.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data/telemetry")
DATA_DIR.mkdir(parents=True, exist_ok=True)
EVENTS_FILE  = DATA_DIR / "eventos.jsonl"
PROFILE_FILE = DATA_DIR / "perfil_usuario.json"
STATS_FILE   = DATA_DIR / "stats_rutas.json"


# ─────────────────────────────────────────────────────────────────────────────
# ID de sesión persistente por instalación
# ─────────────────────────────────────────────────────────────────────────────

def _session_id() -> str:
    id_file = DATA_DIR / "session_id.txt"
    if id_file.exists():
        return id_file.read_text(encoding="utf-8").strip()
    sid = str(uuid.uuid4())
    id_file.write_text(sid, encoding="utf-8")
    return sid


# ─────────────────────────────────────────────────────────────────────────────
# Eventos
# ─────────────────────────────────────────────────────────────────────────────

def registrar_evento(tipo: str, datos: dict[str, Any]) -> None:
    """Append-only a eventos.jsonl."""
    evento = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "session_id": _session_id(),
        "tipo": tipo,
        **datos,
    }
    with EVENTS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Estadísticas de rutas
# ─────────────────────────────────────────────────────────────────────────────

def incrementar_uso_ruta(origen: str, destino: str) -> int:
    """Cuenta uso de pares origen→destino. Retorna nuevo contador."""
    stats = _load_stats()
    clave = f"{origen} → {destino}"
    stats["rutas"][clave]     = stats["rutas"].get(clave, 0) + 1
    stats["origenes"][origen] = stats["origenes"].get(origen, 0) + 1
    stats["destinos"][destino] = stats["destinos"].get(destino, 0) + 1
    _save_stats(stats)
    return stats["rutas"][clave]


def _load_stats() -> dict:
    if STATS_FILE.exists():
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    return {"rutas": {}, "origenes": {}, "destinos": {}}


def _save_stats(stats: dict) -> None:
    STATS_FILE.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def obtener_stats_usuario() -> dict:
    """Para mostrar al usuario sus rutas más frecuentes."""
    stats = _load_stats()
    top_rutas = sorted(stats["rutas"].items(), key=lambda x: -x[1])[:5]
    return {
        "total_consultas": sum(stats["rutas"].values()),
        "rutas_unicas":    len(stats["rutas"]),
        "top_5_rutas":     top_rutas,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Perfil de usuario
# ─────────────────────────────────────────────────────────────────────────────

def guardar_perfil(perfil: dict) -> None:
    PROFILE_FILE.write_text(
        json.dumps(perfil, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cargar_perfil() -> dict:
    if PROFILE_FILE.exists():
        return json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Feedback
# ─────────────────────────────────────────────────────────────────────────────

def registrar_feedback(
    rating: int | None,
    comentario: str = "",
    exactitud: str | None = None,
    tiempo_real_min: float | None = None,
    tiempo_predicho_min: float | None = None,
) -> None:
    """
    rating: 1-5 o None (pospuesto).
    exactitud: 'exacto' | 'cerca' | 'lejos' | None.
    """
    registrar_evento("feedback", {
        "rating":              rating,
        "comentario":          comentario,
        "exactitud":           exactitud,
        "tiempo_real_min":     tiempo_real_min,
        "tiempo_predicho_min": tiempo_predicho_min,
    })
