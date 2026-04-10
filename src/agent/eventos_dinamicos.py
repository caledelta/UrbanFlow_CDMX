"""
Clasificador de eventos detectados → factores de perturbación Markov.

Traduce EventoDetectado a factores f compatibles con el catálogo
de perturbaciones de tools.py (ecuación 25 del artículo).

Diseño: los factores dinámicos se calibran por analogía con los 11
eventos del catálogo estático. Un accidente leve es ~f=1.05; una
manifestación masiva es ~f=1.30 (análogo a Marcha 9 de marzo).
"""
from __future__ import annotations

from typing import List

from src.data_sources.eventos_client import EventoDetectado


# Mapeo: (tipo, severidad) → factor f estimado
# Calibrados por analogía con el catálogo estático de tools.py.
FACTORES_DINAMICOS: dict[tuple[str, str], float] = {
    # Accidentes
    ("accidente", "baja"):      1.03,
    ("accidente", "media"):     1.08,
    ("accidente", "alta"):      1.15,
    ("accidente", "critica"):   1.22,
    # Cierres viales
    ("cierre_vial", "baja"):    1.05,
    ("cierre_vial", "media"):   1.12,
    ("cierre_vial", "alta"):    1.20,   # ≈ Cierre Línea 12 Metro
    ("cierre_vial", "critica"): 1.28,
    # Manifestaciones
    ("manifestacion", "baja"):  1.10,
    ("manifestacion", "media"): 1.18,
    ("manifestacion", "alta"):  1.27,   # ≈ CNTE
    ("manifestacion", "critica"):1.35,  # ≈ Grito de Independencia
    # Clima severo
    ("clima_severo", "baja"):   1.05,
    ("clima_severo", "media"):  1.12,
    ("clima_severo", "alta"):   1.20,
    ("clima_severo", "critica"):1.30,
    # Infraestructura
    ("infraestructura", "baja"):   1.08,
    ("infraestructura", "media"):  1.15,
    ("infraestructura", "alta"):   1.25,  # ≈ Cierre Línea 1 Metro
    ("infraestructura", "critica"):1.32,
    # Emergencia
    ("emergencia", "baja"):    1.05,
    ("emergencia", "media"):   1.12,
    ("emergencia", "alta"):    1.22,
    ("emergencia", "critica"): 1.30,
}

# Factor por defecto para tipos no mapeados
FACTOR_DEFAULT = 1.05


def estimar_factor(evento: EventoDetectado) -> float:
    """
    Estima el factor de perturbación f para un evento detectado.

    Args:
        evento: EventoDetectado con tipo y severidad.

    Returns:
        Factor f ∈ (1.0, 1.40). Valores > 1 incrementan la probabilidad
        de estado Congestionado en la matriz de transición.
    """
    key = (evento.tipo, evento.severidad)
    return FACTORES_DINAMICOS.get(key, FACTOR_DEFAULT)


def agregar_factores(eventos: List[EventoDetectado]) -> float:
    """
    Agrega múltiples eventos en un factor f combinado.

    Usa composición multiplicativa truncada:
        f_total = min(Π f_i, f_max)

    La truncación a f_max=1.50 evita matrices degeneradas cuando
    hay muchos eventos simultáneos.

    Args:
        eventos: Lista de EventoDetectado activos en la zona.

    Returns:
        Factor f combinado ∈ (1.0, 1.50).
    """
    if not eventos:
        return 1.0

    f_total = 1.0
    for evento in eventos:
        f_total *= estimar_factor(evento)

    F_MAX = 1.50
    return min(f_total, F_MAX)


def resumir_eventos(eventos: List[EventoDetectado]) -> str:
    """
    Genera un resumen en lenguaje natural de los eventos activos
    para que el agente VialAI lo comunique al usuario.

    Returns:
        String con resumen legible, o cadena vacía si no hay eventos.
    """
    if not eventos:
        return ""

    lineas = [f"⚠️ {len(eventos)} evento(s) activo(s) detectado(s):"]
    _EMOJI = {
        "accidente":      "🚗",
        "manifestacion":  "📢",
        "cierre_vial":    "🚧",
        "clima_severo":   "🌧️",
        "infraestructura":"🔧",
        "emergencia":     "🚨",
    }
    for e in eventos[:5]:  # máximo 5 para no saturar
        emoji = _EMOJI.get(e.tipo, "⚠️")
        lineas.append(
            f"  {emoji} {e.descripcion} "
            f"(severidad: {e.severidad}, radio: {e.radio_impacto_km} km)"
        )

    return "\n".join(lineas)
