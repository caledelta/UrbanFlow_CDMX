"""
src/core/recompensa.py — Análisis personalizado por completar el perfil.

Se activa silenciosamente la primera vez que perfil_completo() es True.
No se anuncia previamente: es una sorpresa entregada como utilidad real.

Dos componentes:
1. Branding contextual de la empresa (delivery / transporte / particular)
2. Análisis de ruta principal: frecuencia, tiempo real promedio, ventana óptima

Módulo 100 % puro (sin imports de Streamlit ni telemetria).
El renderizado queda en streamlit_app.py.
"""

from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Configuración por empresa
# ─────────────────────────────────────────────────────────────────────────────

COMPANY_CONFIG: dict[str, dict[str, str]] = {
    "Uber Eats": {
        "emoji": "🟢",
        "color": "#06C167",
        "bg":    "rgba(6,193,103,0.13)",
        "tip": (
            "Picos de demanda en CDMX: **12:00–14:00 h** y **19:00–21:00 h**. "
            "Planifica recargas y descansos en los valles: 10:00–11:30 h y 16:00–17:30 h. "
            "Zonas calientes: Roma, Condesa, Polanco, Santa Fe."
        ),
    },
    "DiDi Food": {
        "emoji": "🟠",
        "color": "#FA5300",
        "bg":    "rgba(250,83,0,0.13)",
        "tip": (
            "Mayor densidad de pedidos en Narvarte, Del Valle y Coyoacán. "
            "Horario más rentable: **13:00–15:00 h** (comida) y **20:00–22:00 h** (cena). "
            "Evita Insurgentes y Reforma entre 18–19 h: congestión severa."
        ),
    },
    "Rappi": {
        "emoji": "🟡",
        "color": "#FF441F",
        "bg":    "rgba(255,68,31,0.13)",
        "tip": (
            "Alta demanda en supermercados y farmacias. "
            "Zonas clave: Lomas, Polanco, Pedregal. "
            "Pico de entregas: **11:00–15:00 h** y **18:00–22:00 h**."
        ),
    },
    "Didi": {
        "emoji": "🟠",
        "color": "#FA5300",
        "bg":    "rgba(250,83,0,0.13)",
        "tip": (
            "Puntos de alta demanda: AICM, Terminal Norte y TAPO. "
            "Hora dorada: **06:30–09:00 h** (salida al trabajo) y **18:00–20:00 h** (regreso). "
            "Posicionarte cerca de nodos de transporte maximiza aceptaciones."
        ),
    },
    "Uber": {
        "emoji": "⚫",
        "color": "#444444",
        "bg":    "rgba(68,68,68,0.12)",
        "tip": (
            "Mayor demanda cerca de Santa Fe, Polanco y el AICM. "
            "Viernes y sábados de noche (22:00–02:00 h): tarifa surge frecuente. "
            "Insurgentes Norte y Sur entre 7–9 h maximiza aceptaciones."
        ),
    },
    "Cabify": {
        "emoji": "🟣",
        "color": "#7C3AED",
        "bg":    "rgba(124,58,237,0.13)",
        "tip": (
            "Fuerte demanda corporativa en Santa Fe y Reforma. "
            "Lunes–miércoles de **07:00–09:30 h** son los más activos. "
            "Mantén valoración 4.8+ para prioridad en usuarios corporativos."
        ),
    },
    "Domino's": {
        "emoji": "🔵",
        "color": "#006491",
        "bg":    "rgba(0,100,145,0.13)",
        "tip": (
            "Entregas concentradas viernes–domingo. "
            "Radio de cobertura típico: 3–5 km desde la sucursal. "
            "Hora pico: **19:00–22:00 h**. Minimiza kilómetros en rutas de bajo tráfico."
        ),
    },
    "Burger King": {
        "emoji": "🟤",
        "color": "#C8102E",
        "bg":    "rgba(200,16,46,0.13)",
        "tip": (
            "Alta demanda en zonas comerciales y de oficinas. "
            "Comida: **12:00–14:30 h**. Cena: **19:30–21:30 h**. "
            "Rutas cortas entre el restaurante y colonias aledañas."
        ),
    },
    "Sushi Itto": {
        "emoji": "🔴",
        "color": "#C41E3A",
        "bg":    "rgba(196,30,58,0.13)",
        "tip": (
            "Demanda alta en Lomas, Interlomas y Satélite. "
            "Pico: **20:00–22:30 h**. Fines de semana duplican el volumen habitual. "
            "Prioriza zonas residenciales de clase media-alta."
        ),
    },
    "Otra empresa de reparto": {
        "emoji": "📦",
        "color": "#22c55e",
        "bg":    "rgba(34,197,94,0.10)",
        "tip": (
            "En CDMX el tráfico de última milla es más fluido entre **10:00–12:00 h** y **14:00–16:00 h**. "
            "Usa VialAI para identificar la ventana óptima de tu zona de cobertura."
        ),
    },
    "Particular": {
        "emoji": "🚗",
        "color": "#22c55e",
        "bg":    "rgba(34,197,94,0.10)",
        "tip": (
            "Las rutas por ejes viales suelen ser 15–25% más rápidas en hora pico "
            "que Insurgentes o Reforma. "
            "Recuerda el programa **Hoy No Circula** al planificar tus salidas."
        ),
    },
    "Otro": {
        "emoji": "🙌",
        "color": "#22c55e",
        "bg":    "rgba(34,197,94,0.10)",
        "tip": (
            "Analiza tus patrones de uso para identificar las ventanas donde tu "
            "ruta habitual fluye mejor. VialAI registra tu historial para darte "
            "recomendaciones cada vez más precisas."
        ),
    },
}

_TIP_GENERICO = (
    "Analiza tus patrones de tráfico para identificar las ventanas horarias "
    "donde tu ruta habitual fluye mejor. VialAI registra tu historial de "
    "consultas para darte recomendaciones cada vez más precisas."
)

# Ventanas horarias CDMX (basadas en patrones históricos C5 CDMX 2023)
_PICOS:  tuple[tuple[int, int], ...] = ((7, 9), (17, 20))
_VALLES: tuple[tuple[int, int], ...] = ((6, 7), (14, 16), (21, 23))


# ─────────────────────────────────────────────────────────────────────────────
# Funciones públicas
# ─────────────────────────────────────────────────────────────────────────────

def perfil_completo(perfil: dict) -> bool:
    """True si tipo, género y edad están todos informados."""
    return bool(
        perfil.get("tipo")
        and perfil.get("genero")
        and perfil.get("edad")
    )


def get_company_config(tipo: str) -> dict[str, str] | None:
    return COMPANY_CONFIG.get(tipo)


def sugerir_ventana_optima(hora_habitual: int | None = None) -> dict[str, str]:
    """Devuelve sugerencia de mejor/peor hora basada en patrones C5."""
    if hora_habitual is not None:
        for inicio, fin in _PICOS:
            if inicio <= hora_habitual < fin:
                return {
                    "estado":  "⚠️ Hora pico",
                    "consejo": (
                        f"Las **{hora_habitual:02d}:00 h** es hora pico en CDMX. "
                        f"Salir 45–60 min antes reduciría tu P50 estimado en ~30%."
                    ),
                    "mejor": "06:00–07:00 h  ·  14:00–16:00 h",
                    "peor":  f"{hora_habitual:02d}:00 h (hora seleccionada)",
                }
        for inicio, fin in _VALLES:
            if inicio <= hora_habitual < fin:
                return {
                    "estado":  "✅ Hora favorable",
                    "consejo": (
                        f"Las **{hora_habitual:02d}:00 h** es una ventana de bajo tráfico."
                    ),
                    "mejor": f"{hora_habitual:02d}:00 h (hora seleccionada)",
                    "peor":  "07:00–09:00 h  ·  17:00–20:00 h",
                }
    return {
        "estado":  "📊 Ventanas óptimas CDMX",
        "consejo": "Basado en patrones históricos del C5 CDMX 2023.",
        "mejor":   "06:00–07:00 h  ·  14:00–16:00 h",
        "peor":    "07:00–09:00 h  ·  17:00–20:00 h",
    }


def generar_analisis(
    perfil: dict,
    stats: dict,
    feedback_historial: list[dict[str, Any]],
    hora_habitual: int | None = None,
) -> dict[str, Any]:
    """
    Construye el análisis personalizado.

    Nunca lanza excepción: los campos ausentes quedan como None.
    """
    tipo    = perfil.get("tipo", "")
    company = get_company_config(tipo)

    top_rutas       = stats.get("top_5_rutas", [])
    ruta_principal  = top_rutas[0] if top_rutas else None  # (nombre, n_usos)

    tiempos_reales = [
        f["real_min"] for f in feedback_historial
        if isinstance(f.get("real_min"), (int, float))
    ]
    avg_real = (
        round(sum(tiempos_reales) / len(tiempos_reales), 1)
        if tiempos_reales else None
    )

    return {
        "tipo":            tipo,
        "company":         company,
        "ruta_principal":  ruta_principal,
        "total_consultas": stats.get("total_consultas", 0),
        "avg_real_min":    avg_real,
        "n_viajes_reales": len(tiempos_reales),
        "ventana":         sugerir_ventana_optima(hora_habitual),
        "tip":             company["tip"] if company else _TIP_GENERICO,
    }
