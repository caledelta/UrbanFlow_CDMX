"""
src/agent/tools.py — Herramientas del agente conversacional UrbanFlow CDMX.

Fase 2 de Function Calling: define las tres herramientas que el agente usa
para responder consultas de movilidad urbana en la ZMVM. Cada herramienta
está decorada con @function_tool, que genera el schema JSON requerido por
la Anthropic API (campo ``tools`` en ``client.messages.create``).

Herramientas registradas
------------------------
predecir_tiempo_viaje    — simulación Monte Carlo P10/P50/P90 para un trayecto.
consultar_trafico_ahora  — velocidad y congestión en tiempo real (TomTom API).
verificar_perturbaciones — perturbaciones contextuales activas (§5B CLAUDE.md).

Fallbacks
---------
Cada herramienta captura todas las excepciones de APIs externas y devuelve
un resultado degradado en lugar de propagar el error al agente. El campo
``resumen`` (PrediccionViaje) o los valores por defecto (RespuestaTomTom)
indican cuándo los datos son estimados.

Uso rápido
----------
>>> from src.agent.tools import get_tools_schema
>>> tools = get_tools_schema()   # lista lista para la Anthropic API
>>> len(tools)
3
"""

from __future__ import annotations

import datetime
import functools
import inspect
import logging
import math
import os
from typing import Any, Callable

import numpy as np

from src.data_sources.eventos_client import EventosClient
from src.agent.eventos_dinamicos import agregar_factores, resumir_eventos
from src.ingestion.tomtom_client import TomTomAPIError, TomTomTrafficClient
from src.models.schemas import PrediccionViaje, RespuestaTomTom
from src.simulation.markov_chain import MarkovTrafficChain
from src.simulation.monte_carlo import ConsultaViaje, MonteCarloEngine
from src.simulation.evaluador_rutas import evaluar_rutas, generar_explicacion_cambio_ruta

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Decorador @function_tool
# ═══════════════════════════════════════════════════════════════════════════

_REGISTERED_TOOLS: list[dict[str, Any]] = []

_PYTHON_TYPE_MAP: dict[type, str] = {
    str:   "string",
    int:   "integer",
    float: "number",
    bool:  "boolean",
    list:  "array",
    dict:  "object",
}


def function_tool(func: Callable) -> Callable:
    """
    Decorador que registra una función como herramienta compatible con la
    Anthropic API.

    Construye automáticamente el schema JSON de la herramienta a partir de:

    - **Nombre** — ``func.__name__``
    - **Descripción** — primera sección del docstring (hasta la primera línea
      en blanco o la primera sección con guiones ``---``).
    - **input_schema** — propiedades inferidas desde las anotaciones de tipo.
      Las descripciones de parámetros se extraen de la sección "Parámetros"
      del docstring (estilo NumPy).

    El schema resultante se almacena en ``func._tool_schema`` y se añade al
    registro global ``_REGISTERED_TOOLS``, accesible con ``get_tools_schema()``.

    Parámetros
    ----------
    func : Callable
        Función a decorar. Debe tener anotaciones de tipo y docstring.

    Devuelve
    --------
    Callable
        Wrapper que preserva el comportamiento original de ``func`` y
        expone el atributo ``_tool_schema``.

    Ejemplo
    -------
    >>> @function_tool
    ... def saludar(nombre: str) -> str:
    ...     \"\"\"Genera un saludo personalizado.\"\"\"
    ...     return f"Hola, {nombre}"
    >>> saludar._tool_schema["name"]
    'saludar'
    >>> saludar._tool_schema["input_schema"]["properties"]["nombre"]["type"]
    'string'
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    doc = inspect.getdoc(func) or ""
    descripcion, param_docs = _parsear_docstring_numpy(doc)

    sig = inspect.signature(func)
    hints = {k: v for k, v in func.__annotations__.items() if k != "return"}

    properties: dict[str, Any] = {}
    required: list[str] = []

    for nombre, param in sig.parameters.items():
        tipo = hints.get(nombre, str)
        entry: dict[str, Any] = {"type": _python_type_to_json(tipo)}
        if nombre in param_docs and param_docs[nombre]:
            entry["description"] = param_docs[nombre]
        properties[nombre] = entry
        if param.default is inspect.Parameter.empty:
            required.append(nombre)

    schema: dict[str, Any] = {
        "name": func.__name__,
        "description": descripcion,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }

    wrapper._tool_schema = schema  # type: ignore[attr-defined]
    wrapper._is_tool = True        # type: ignore[attr-defined]
    _REGISTERED_TOOLS.append(schema)

    return wrapper


def get_tools_schema() -> list[dict[str, Any]]:
    """
    Devuelve la lista de schemas de herramientas registradas con @function_tool.

    El resultado es una lista lista para pasarse directamente al parámetro
    ``tools`` de ``anthropic.Anthropic().messages.create()``.

    Devuelve
    --------
    list[dict]
        Copia de ``_REGISTERED_TOOLS`` con el schema de cada herramienta.
    """
    return list(_REGISTERED_TOOLS)


# ═══════════════════════════════════════════════════════════════════════════
# Catálogo de puntos de referencia ZMVM (PUNTOS_CDMX)
# ═══════════════════════════════════════════════════════════════════════════

PUNTOS_CDMX: dict[str, tuple[float, float]] = {
    # ── Corredores viales principales ──────────────────────────────────
    "Insurgentes · Perisur":          (19.3280, -99.1700),
    "Insurgentes · Viaducto":         (19.4010, -99.1700),
    "Insurgentes · Reforma":          (19.4270, -99.1670),
    "Insurgentes · Buenavista":       (19.4530, -99.1700),
    "Reforma · Ángel":                (19.4270, -99.1676),
    "Reforma · Auditorio":            (19.4346, -99.1900),
    "Reforma · Chapultepec":          (19.4250, -99.1780),
    "Viaducto · Observatorio":        (19.4010, -99.2010),
    "Viaducto · TAPO":                (19.4200, -99.1140),
    "Zaragoza · TAPO":                (19.4255, -99.1139),
    "Periférico Norte · Toreo":       (19.5080, -99.2350),
    "Periférico Sur · Perisur":       (19.3280, -99.2050),
    "Periférico Sur · San Jerónimo":  (19.3250, -99.2200),
    "Eje 1 Norte · Buenavista":       (19.4520, -99.1530),
    "Eje Central · Doctores":         (19.4170, -99.1430),
    # ── Nodos de transporte ─────────────────────────────────────────────
    "Aeropuerto Internacional":       (19.4363, -99.0721),
    "Terminal TAPO":                  (19.4255, -99.1139),
    "Terminal Norte":                 (19.4840, -99.1310),
    "Terminal Poniente":              (19.3978, -99.2427),
    "Terminal Sur":                   (19.3500, -99.1640),
    "Metro Pantitlán":                (19.4151, -99.0679),
    "Metro Observatorio":             (19.4010, -99.2010),
    "Metro Indios Verdes":            (19.5332, -99.1220),
    "Metro Tacubaya":                 (19.4033, -99.1857),
    "Metro Taxqueña":                 (19.3508, -99.1362),
    "Metro Cuatro Caminos":           (19.4960, -99.2110),
    "Metro Universidad":              (19.3300, -99.1866),
    # ── Alcaldías y zonas ───────────────────────────────────────────────
    "Zócalo":                         (19.4326, -99.1332),
    "Tepito":                         (19.4490, -99.1230),
    "Tlatelolco":                     (19.4520, -99.1430),
    "Garibaldi":                      (19.4470, -99.1420),
    "Polanco":                        (19.4380, -99.1960),
    "Santa Fe":                       (19.3600, -99.2590),
    "Doctores":                       (19.4170, -99.1430),
    "Del Valle":                      (19.3810, -99.1620),
    "Coyoacán":                       (19.3500, -99.1620),
    "San Ángel":                      (19.3520, -99.1900),
    "Xochimilco":                     (19.2586, -99.1020),
    "Tlalpan":                        (19.2950, -99.1630),
    "Ciudad Universitaria":           (19.3320, -99.1872),
    "Estadio Azteca":                 (19.3030, -99.1510),
    "City Banamex":                   (19.4770, -99.2050),
    "Palacio de los Deportes":        (19.4040, -99.0890),
    "Foro Sol":                       (19.3950, -99.0870),
    "Buenavista":                     (19.4530, -99.1530),
    "Chapultepec":                    (19.4210, -99.1950),
    "Insurgentes Sur 1602":           (19.3810, -99.1700),
}


# ═══════════════════════════════════════════════════════════════════════════
# Catálogo de perturbaciones contextuales — §5B CLAUDE.md
# ═══════════════════════════════════════════════════════════════════════════

PERTURBACIONES: list[dict[str, Any]] = [
    # ── Supuesto base ───────────────────────────────────────────────────
    {
        "tipo":        "base",
        "descripcion": "Día hábil típico — densidad histórica C5 CDMX",
        "factor":       1.00,
        "alcaldias":   None,
        "horas":       (0, 24),
    },
    # ── Cierres de Metro ────────────────────────────────────────────────
    {
        "tipo":        "metro_cierre",
        "descripcion": "Cierre Línea 1 Metro (Observatorio–Pantitlán)",
        "factor":       1.55,
        "alcaldias":   ["CUAUHTEMOC", "VENUSTIANO CARRANZA", "IZTAPALAPA",
                        "BENITO JUAREZ", "IZTACALCO"],
        "horas":       (6, 22),
    },
    {
        "tipo":        "metro_cierre",
        "descripcion": "Cierre Línea 12 Metro (Tláhuac–Mixcoac)",
        "factor":       1.45,
        "alcaldias":   ["TLAHUAC", "IZTAPALAPA", "COYOACAN", "ALVARO OBREGON"],
        "horas":       (6, 22),
    },
    # ── Eventos masivos ─────────────────────────────────────────────────
    {
        "tipo":        "evento_masivo",
        "descripcion": "Evento en City Banamex (Azcapotzalco)",
        "factor":       1.40,
        "alcaldias":   ["AZCAPOTZALCO", "MIGUEL HIDALGO", "GUSTAVO A. MADERO"],
        "horas":       (16, 24),
    },
    {
        "tipo":        "evento_masivo",
        "descripcion": "Evento en Palacio de los Deportes (Iztacalco)",
        "factor":       1.35,
        "alcaldias":   ["IZTACALCO", "VENUSTIANO CARRANZA", "IZTAPALAPA"],
        "horas":       (16, 24),
    },
    {
        "tipo":        "evento_masivo",
        "descripcion": "Partido en Estadio Azteca",
        "factor":       1.50,
        "alcaldias":   ["TLALPAN", "XOCHIMILCO", "COYOACAN", "IZTAPALAPA"],
        "horas":       (17, 23),
    },
    # ── Protestas y marchas ─────────────────────────────────────────────
    {
        "tipo":        "protesta",
        "descripcion": "9 de marzo — Marcha Día de la Mujer (Reforma/Zócalo)",
        "factor":       1.70,
        "alcaldias":   ["CUAUHTEMOC", "MIGUEL HIDALGO", "BENITO JUAREZ"],
        "horas":       (10, 21),
    },
    {
        "tipo":        "protesta",
        "descripcion": "Protesta CNTE — bloqueo Insurgentes/Reforma",
        "factor":       1.60,
        "alcaldias":   ["CUAUHTEMOC", "BENITO JUAREZ", "ALVARO OBREGON"],
        "horas":       (8, 20),
    },
    # ── Días festivos ───────────────────────────────────────────────────
    {
        "tipo":        "festivo",
        "descripcion": "15 sep — Grito de Independencia (Zócalo)",
        "factor":       1.80,
        "alcaldias":   ["CUAUHTEMOC", "MIGUEL HIDALGO", "VENUSTIANO CARRANZA"],
        "horas":       (17, 24),
    },
    {
        "tipo":        "festivo",
        "descripcion": "16 sep — Desfile Militar (Reforma/Zócalo)",
        "factor":       1.65,
        "alcaldias":   ["CUAUHTEMOC", "MIGUEL HIDALGO"],
        "horas":       (8, 15),
    },
    {
        "tipo":        "festivo",
        "descripcion": "2 nov — Día de Muertos Xochimilco",
        "factor":       1.45,
        "alcaldias":   ["XOCHIMILCO", "TLALPAN", "COYOACAN"],
        "horas":       (12, 23),
    },
    {
        "tipo":        "festivo",
        "descripcion": "Navidad / Año Nuevo — ciudad semi-vacía",
        "factor":       0.60,
        "alcaldias":   None,
        "horas":       (0, 24),
    },
]


def seleccionar_perturbacion(
    fecha: datetime.datetime,
    alcaldia: str | None = None,
) -> dict[str, Any]:
    """
    Devuelve la perturbación más severa aplicable a la fecha/hora y alcaldía
    dadas, o el supuesto base si ninguna perturbación especial aplica.

    Porta directamente la lógica del notebook §5B para uso en producción.

    Parámetros
    ----------
    fecha : datetime.datetime
        Fecha y hora de la consulta (naive o con tz).
    alcaldia : str o None
        Alcaldía a verificar. ``None`` considera toda la ZMVM.

    Devuelve
    --------
    dict
        Perturbación activa con claves ``tipo``, ``descripcion``,
        ``factor``, ``alcaldias``, ``horas``.
    """
    hora = fecha.hour
    mes  = fecha.month
    dia  = fecha.day

    candidatas: list[dict[str, Any]] = []
    for p in PERTURBACIONES:
        if p["tipo"] == "base":
            continue

        h_ini, h_fin = p["horas"]
        if not (h_ini <= hora < h_fin):
            continue

        if p["alcaldias"] is not None and alcaldia is not None:
            if alcaldia.upper() not in p["alcaldias"]:
                continue

        # Verificar fecha para festivos con día exacto
        if p["tipo"] == "festivo":
            desc = p["descripcion"]
            if "15 sep"    in desc and not (mes == 9  and dia == 15):
                continue
            if "16 sep"    in desc and not (mes == 9  and dia == 16):
                continue
            if "2 nov"     in desc and not (mes == 11 and dia == 2):
                continue
            if "Navidad"   in desc and not (mes == 12 and dia in (24, 25, 31)):
                continue
            if "9 de marzo" in desc and not (mes == 3 and dia == 9):
                continue

        candidatas.append(p)

    if not candidatas:
        return next(p for p in PERTURBACIONES if p["tipo"] == "base")
    return max(candidatas, key=lambda x: x["factor"])


# ═══════════════════════════════════════════════════════════════════════════
# Motor Monte Carlo con caché lazy (reutilizado entre llamadas al agente)
# ═══════════════════════════════════════════════════════════════════════════

_DEFAULT_ENGINE: MonteCarloEngine | None = None


def _get_default_engine() -> MonteCarloEngine:
    """
    Devuelve el MonteCarloEngine por defecto, creándolo la primera vez.

    La cadena de Markov se calibra con una serie sintética representativa
    de la ZMVM (patrón fluido–lento–congestionado calibrado con C5 CDMX).
    """
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        serie = np.tile([0, 0, 1, 1, 2, 1, 0], 300)
        cadena = MarkovTrafficChain().fit(serie)
        _DEFAULT_ENGINE = MonteCarloEngine(cadena, n_simulaciones=10_000)
    return _DEFAULT_ENGINE


# ═══════════════════════════════════════════════════════════════════════════
# Funciones auxiliares privadas
# ═══════════════════════════════════════════════════════════════════════════

def _haversine_km(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Distancia haversine entre dos puntos WGS84 en kilómetros.

    Parámetros
    ----------
    lat1 : float
        Latitud del punto 1 en grados decimales.
    lon1 : float
        Longitud del punto 1 en grados decimales.
    lat2 : float
        Latitud del punto 2 en grados decimales.
    lon2 : float
        Longitud del punto 2 en grados decimales.

    Devuelve
    --------
    float
        Distancia en kilómetros entre los dos puntos.
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _resolver_punto(nombre: str) -> tuple[float, float] | None:
    """
    Resuelve un nombre de punto a coordenadas (lat, lon) usando PUNTOS_CDMX.

    Primero busca coincidencia exacta; si no la encuentra, busca coincidencia
    parcial insensible a mayúsculas (busca el nombre como subcadena).

    Parámetros
    ----------
    nombre : str
        Nombre o parte del nombre del punto a resolver.

    Devuelve
    --------
    tuple[float, float] o None
        Coordenadas (lat, lon) del punto, o ``None`` si no se encontró.
    """
    if nombre in PUNTOS_CDMX:
        return PUNTOS_CDMX[nombre]

    nombre_lower = nombre.lower()
    for clave, coords in PUNTOS_CDMX.items():
        if nombre_lower in clave.lower():
            return coords

    return None


def _estado_desde_hora_dia(hora: str, dia: str) -> int:
    """
    Estima el estado de tráfico inicial a partir de la hora y el día.

    Parámetros
    ----------
    hora : str
        Hora en formato "HH:MM" (24 h). Ej: "08:30", "17:00".
    dia : str
        Nombre del día en español o inglés. Ej: "lunes", "sabado".

    Devuelve
    --------
    int
        Estado de tráfico estimado: 0=Fluido, 1=Lento, 2=Congestionado.
    """
    try:
        h = int(hora.split(":")[0])
    except (ValueError, IndexError, AttributeError):
        h = 12

    dia_lower = (dia or "").lower().strip()
    es_fin_semana = dia_lower in (
        "sabado", "sábado", "saturday", "sat",
        "domingo", "sunday", "sun",
    )

    if es_fin_semana:
        if 10 <= h <= 14 or 17 <= h <= 20:
            return 1  # LENTO
        return 0      # FLUIDO

    # Día hábil
    if (7 <= h <= 9) or (17 <= h <= 20):
        return 2      # CONGESTIONADO (hora pico)
    if (10 <= h <= 16) or (21 <= h <= 22):
        return 1      # LENTO (hora valle)
    return 0          # FLUIDO (madrugada / noche tardía)


def _nivel_alerta_desde_velocidad(avg_speed_kmh: float) -> str:
    """
    Mapea la velocidad promedio al semáforo de alerta del agente.

    Umbrales calibrados para la ZMVM:
    - ≥ 30 km/h → VERDE   (tráfico fluido)
    - ≥ 15 km/h → AMARILLA (tráfico lento)
    - ≥  8 km/h → NARANJA  (congestión moderada)
    - < 8 km/h  → ROJA    (congestión severa)
    """
    if avg_speed_kmh >= 30.0:
        return "VERDE"
    if avg_speed_kmh >= 15.0:
        return "AMARILLA"
    if avg_speed_kmh >= 8.0:
        return "NARANJA"
    return "ROJA"


def _python_type_to_json(tipo: type) -> str:
    """Convierte un tipo Python básico a su equivalente JSON Schema."""
    return _PYTHON_TYPE_MAP.get(tipo, "string")


def _parsear_docstring_numpy(doc: str) -> tuple[str, dict[str, str]]:
    """
    Extrae la descripción principal y las descripciones de parámetros de un
    docstring en estilo NumPy.

    Parámetros
    ----------
    doc : str
        Docstring completo de la función.

    Devuelve
    --------
    tuple[str, dict[str, str]]
        ``(descripcion_principal, {nombre_param: descripcion_param})``.
    """
    lines = doc.splitlines()
    main_lines: list[str] = []
    param_docs: dict[str, str] = {}

    in_params = False
    current_param: str | None = None

    SECTION_HEADERS = {
        "parámetros", "parametros", "parameters", "args", "arguments",
        "devuelve", "returns", "return", "raises", "notas", "notes",
        "ejemplo", "ejemplos", "example", "examples",
    }

    for line in lines:
        stripped = line.strip()
        stripped_lower = stripped.lower().rstrip(":")

        if stripped_lower in SECTION_HEADERS:
            in_params = stripped_lower in (
                "parámetros", "parametros", "parameters", "args", "arguments"
            )
            current_param = None
            continue

        if stripped.startswith("---") or stripped.startswith("==="):
            continue

        if in_params:
            # Nueva sección no-parámetros (sin sangría y no vacía → fin)
            if stripped and not line.startswith(" ") and " : " not in stripped:
                in_params = False
                current_param = None
                main_lines.append(line)
                continue

            if " : " in stripped:
                current_param = stripped.split(" : ")[0].strip()
                param_docs[current_param] = ""
            elif current_param is not None and stripped:
                sep = " " if param_docs[current_param] else ""
                param_docs[current_param] += sep + stripped
        else:
            main_lines.append(line)

    # Primer párrafo del bloque principal como descripción
    desc_parts: list[str] = []
    for line in main_lines:
        if not line.strip() and desc_parts:
            break
        if line.strip():
            desc_parts.append(line.strip())

    return " ".join(desc_parts), param_docs


# ═══════════════════════════════════════════════════════════════════════════
# Herramienta 1 — predecir_tiempo_viaje
# ═══════════════════════════════════════════════════════════════════════════

@function_tool
def predecir_tiempo_viaje(
    origen: str,
    destino: str,
    hora: str,
    dia: str,
) -> PrediccionViaje:
    """
    Predice el tiempo de viaje entre dos puntos de la ZMVM usando simulación
    Monte Carlo con bandas de incertidumbre P10/P50/P90.

    Usa PUNTOS_CDMX para resolver las coordenadas de origen y destino,
    calcula la distancia haversine y ejecuta el motor de simulación con el
    estado de tráfico estimado para la hora y día indicados. Es la herramienta
    principal del agente para responder preguntas como "¿cuánto tarda ir de
    Reforma a Perisur en hora pico?" o "¿cuánto tiempo hay de CU a TAPO el
    sábado a las 14:00?".

    Parámetros
    ----------
    origen : str
        Nombre del punto de origen. Debe coincidir (parcialmente) con una
        clave de PUNTOS_CDMX. Ej: "Reforma · Ángel", "Zócalo", "Perisur".
    destino : str
        Nombre del punto de destino. Mismo formato que ``origen``.
    hora : str
        Hora de inicio del viaje en formato "HH:MM" (24 h). Ej: "08:30".
    dia : str
        Día de la semana en español. Ej: "lunes", "sabado", "domingo".

    Devuelve
    --------
    PrediccionViaje
        Resultado de la simulación con percentiles P10/P50/P90 en minutos,
        nivel de alerta y resumen textual del trayecto.
    """
    try:
        coords_origen = _resolver_punto(origen)
        coords_destino = _resolver_punto(destino)

        if coords_origen is None:
            logger.warning("Origen '%s' no encontrado en PUNTOS_CDMX — usando Zócalo.", origen)
            coords_origen = PUNTOS_CDMX["Zócalo"]

        if coords_destino is None:
            logger.warning("Destino '%s' no encontrado en PUNTOS_CDMX — usando Zócalo.", destino)
            coords_destino = PUNTOS_CDMX["Zócalo"]

        distancia_km = _haversine_km(*coords_origen, *coords_destino)
        distancia_km = max(distancia_km, 0.5)  # mínimo para evitar división por cero

        estado_inicial = _estado_desde_hora_dia(hora, dia)
        consulta = ConsultaViaje(distancia_km=distancia_km, estado_inicial=estado_inicial)

        motor = _get_default_engine()
        resultado = motor.correr(consulta)

        avg_speed = distancia_km * 60.0 / max(resultado.p50, 0.1)
        nivel = _nivel_alerta_desde_velocidad(avg_speed)

        resumen = (
            f"Trayecto {origen} → {destino} ({distancia_km:.1f} km): "
            f"P50 = {resultado.p50:.0f} min "
            f"(optimista P10 = {resultado.p10:.0f} min, "
            f"pesimista P90 = {resultado.p90:.0f} min). "
            f"Tráfico: {nivel.lower()}."
        )

        return PrediccionViaje(
            origen=origen,
            destino=destino,
            p10_min=round(resultado.p10, 1),
            p50_min=round(resultado.p50, 1),
            p90_min=round(resultado.p90, 1),
            nivel_alerta=nivel,  # type: ignore[arg-type]
            resumen=resumen,
        )

    except Exception as exc:
        logger.error("Error en predecir_tiempo_viaje(%s → %s): %s", origen, destino, exc)
        return _fallback_prediccion(origen, destino, str(exc))


def _fallback_prediccion(origen: str, destino: str, motivo: str) -> PrediccionViaje:
    """Predicción de emergencia cuando el motor falla o los datos no están disponibles."""
    return PrediccionViaje(
        origen=origen,
        destino=destino,
        p10_min=20.0,
        p50_min=35.0,
        p90_min=60.0,
        nivel_alerta="AMARILLA",
        resumen=(
            f"Estimación por defecto para {origen} → {destino} "
            f"(datos no disponibles: {motivo})."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Herramienta 2 — consultar_trafico_ahora
# ═══════════════════════════════════════════════════════════════════════════

@function_tool
def consultar_trafico_ahora(corredor: str) -> RespuestaTomTom:
    """
    Consulta la velocidad y congestión actual en un corredor vial de la ZMVM
    usando la Traffic Flow Segment Data API de TomTom en tiempo real.

    Usa PUNTOS_CDMX para resolver las coordenadas del corredor y llama a
    TomTomTrafficClient. Devuelve velocidad actual, velocidad libre, confianza
    del dato y ratio de flujo (1.0 = fluido, < 0.5 = congestionado). Úsala
    cuando el usuario pregunta por el tráfico actual en una vialidad específica,
    como "¿cómo está el tráfico en Reforma ahorita?" o "¿hay congestión en
    Periférico Norte?".

    Parámetros
    ----------
    corredor : str
        Nombre del corredor vial a consultar. Debe coincidir (parcialmente)
        con una clave de PUNTOS_CDMX. Ej: "Reforma · Ángel",
        "Periférico Norte · Toreo", "Insurgentes · Perisur".

    Devuelve
    --------
    RespuestaTomTom
        Velocidad actual (km/h), velocidad libre (km/h), confianza [0–1]
        y ratio de flujo [0–1]. Si la API no está disponible, devuelve
        valores estimados con confianza = 0.0.
    """
    api_key = os.getenv("TOMTOM_API_KEY", "")

    if not api_key:
        logger.warning(
            "TOMTOM_API_KEY no configurada — devolviendo valores estimados para '%s'.",
            corredor,
        )
        return _fallback_tomtom()

    coords = _resolver_punto(corredor)
    if coords is None:
        logger.warning(
            "Corredor '%s' no encontrado en PUNTOS_CDMX — devolviendo valores estimados.",
            corredor,
        )
        return _fallback_tomtom()

    lat, lon = coords
    try:
        client = TomTomTrafficClient(api_key=api_key)
        segmento = client.obtener_segmento(lat=lat, lon=lon)

        return RespuestaTomTom(
            velocidad_actual_kmh=segmento.velocidad_actual_kmh,
            velocidad_libre_kmh=segmento.velocidad_libre_kmh,
            confianza=segmento.confianza,
            ratio_flujo=segmento.ratio_congestion,
        )

    except TomTomAPIError as exc:
        logger.error("TomTom API error para '%s': %s", corredor, exc)
        return _fallback_tomtom()
    except Exception as exc:
        logger.error("Error inesperado en consultar_trafico_ahora('%s'): %s", corredor, exc)
        return _fallback_tomtom()


def _fallback_tomtom() -> RespuestaTomTom:
    """Respuesta estimada cuando TomTom no está disponible."""
    return RespuestaTomTom(
        velocidad_actual_kmh=18.0,
        velocidad_libre_kmh=50.0,
        confianza=0.0,
        ratio_flujo=0.36,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Herramienta 3 — verificar_perturbaciones
# ═══════════════════════════════════════════════════════════════════════════

@function_tool
def verificar_perturbaciones(fecha: str, alcaldia: str) -> dict:
    """
    Verifica qué perturbación contextual está activa para una fecha, hora y
    alcaldía dadas, aplicando el catálogo del §5B del CLAUDE.md del proyecto.

    Devuelve la perturbación más severa aplicable (cierre de Metro, marcha,
    festivo, etc.) o el supuesto base si el día es hábil sin eventos. El
    campo ``factor`` indica cuánto se multiplica la probabilidad de
    congestión en la cadena de Markov: > 1.0 = más congestión, < 1.0 = menos.
    Úsala cuando el usuario pregunta si hay eventos que afecten el tráfico,
    como "¿hay algo especial mañana en Cuauhtémoc?" o "¿afecta el Grito el
    tráfico del centro?".

    Parámetros
    ----------
    fecha : str
        Fecha y hora en formato ISO 8601: "YYYY-MM-DDTHH:MM:SS" o
        "YYYY-MM-DD HH:MM". Ej: "2024-09-15T20:00:00".
    alcaldia : str
        Nombre de la alcaldía a verificar. Ej: "CUAUHTEMOC", "Iztapalapa".
        Se normaliza a mayúsculas internamente.

    Devuelve
    --------
    dict
        Perturbación activa con claves:
        ``tipo`` (str), ``descripcion`` (str), ``factor`` (float),
        ``alcaldias`` (list[str] | None), ``horas`` (tuple[int, int]).
    """
    try:
        fecha_dt = _parsear_fecha(fecha)
        alcaldia_norm = (alcaldia or "").strip() or None
        return seleccionar_perturbacion(fecha_dt, alcaldia_norm)

    except Exception as exc:
        logger.error("Error en verificar_perturbaciones(fecha='%s'): %s", fecha, exc)
        return next(p for p in PERTURBACIONES if p["tipo"] == "base")


def _parsear_fecha(fecha: str) -> datetime.datetime:
    """
    Parsea una cadena de fecha/hora en los formatos comunes usados por el agente.

    Parámetros
    ----------
    fecha : str
        Cadena de fecha/hora en formato ISO o "YYYY-MM-DD HH:MM".

    Devuelve
    --------
    datetime.datetime
        Objeto datetime resultante.

    Raises
    ------
    ValueError
        Si ningún formato coincide con la cadena dada.
    """
    formatos = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formatos:
        try:
            return datetime.datetime.strptime(fecha, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Formato de fecha no reconocido: '{fecha}'. "
        f"Use 'YYYY-MM-DDTHH:MM:SS' o 'YYYY-MM-DD HH:MM'."
    )


# ═══════════════════════════════════════════════════════════════════════════
# Herramienta 4 — detectar_eventos_activos
# ═══════════════════════════════════════════════════════════════════════════

# Cliente con caché de 5 min; se instancia una vez por proceso
_eventos_client = EventosClient(timeout=5, cache_ttl_min=5)


@function_tool
def detectar_eventos_activos(
    latitud: float = 19.4326,
    longitud: float = -99.1332,
    radio_km: float = 15.0,
) -> dict:
    """
    Detecta eventos activos en cuasi-tiempo-real en la ZMVM.

    Consulta el C5 CDMX y otras fuentes públicas para identificar
    incidentes, manifestaciones, cierres viales o eventos climáticos
    que puedan afectar el tráfico en la zona especificada. Úsala cuando
    el usuario pregunte si hay eventos activos, incidentes o situaciones
    que afecten el tráfico en este momento en la ZMVM.

    Parámetros
    ----------
    latitud : float
        Latitud del punto de interés (default: centro CDMX).
    longitud : float
        Longitud del punto de interés.
    radio_km : float
        Radio de búsqueda en kilómetros.

    Devuelve
    --------
    dict
        Resultado con claves: eventos (lista), factor_dinamico (float),
        resumen (str) y n_eventos (int).
    """
    try:
        eventos = _eventos_client.obtener_eventos_activos(
            lat_centro=latitud,
            lon_centro=longitud,
            radio_km=radio_km,
            horas_atras=6,
        )
        factor = agregar_factores(eventos)
        resumen = resumir_eventos(eventos)

        return {
            "eventos": [
                {
                    "tipo": e.tipo,
                    "descripcion": e.descripcion,
                    "alcaldia": e.alcaldia,
                    "severidad": e.severidad,
                    "radio_km": e.radio_impacto_km,
                }
                for e in eventos[:10]
            ],
            "factor_dinamico": round(factor, 4),
            "resumen": resumen if resumen else "Sin eventos activos detectados.",
            "n_eventos": len(eventos),
        }

    except Exception as exc:
        logger.warning("Error en detección de eventos: %s", exc)
        return {
            "eventos": [],
            "factor_dinamico": 1.0,
            "resumen": "No se pudieron consultar fuentes de eventos.",
            "n_eventos": 0,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Herramienta 5 — seleccionar_mejor_ruta
# ═══════════════════════════════════════════════════════════════════════════

@function_tool
def seleccionar_mejor_ruta(
    origen_lat: float,
    origen_lon: float,
    destino_lat: float,
    destino_lon: float,
    hora: str = "08:00",
    dia: str = "lunes",
    tipo_vehiculo: str = "car",
) -> dict:
    """
    Evalúa múltiples rutas alternativas entre origen y destino, corre Monte
    Carlo sobre cada una y recomienda la óptima basándose en P50 e IC.

    Úsala cuando el usuario pregunte por la mejor ruta, cuando detectes que
    el tráfico está muy comprometido, o cuando pida comparar alternativas.
    Si TomTom Routing no está disponible, evalúa la ruta Haversine como
    única opción y devuelve sus percentiles.

    Parámetros
    ----------
    origen_lat, origen_lon : float
        Coordenadas WGS84 del origen.
    destino_lat, destino_lon : float
        Coordenadas WGS84 del destino.
    hora : str
        Hora de salida en formato "HH:MM" (24 h). Default: "08:00".
    dia : str
        Día de la semana en español o inglés. Default: "lunes".
    tipo_vehiculo : str
        "car" o "motorcycle". Default: "car".

    Devuelve
    --------
    dict
        ruta_recomendada, alternativas, cambio_ruta, explicacion,
        n_rutas_evaluadas.
    """
    try:
        # ── 1. Obtener rutas alternativas ────────────────────────────────────
        rutas_viales: list = []
        tomtom_key = os.getenv("TOMTOM_API_KEY", "")
        if tomtom_key:
            try:
                from src.ingestion.tomtom_routing import TomTomRoutingClient
                _rout = TomTomRoutingClient(api_key=tomtom_key)
                rutas_viales = _rout.calcular_alternativas(
                    origen_lat, origen_lon,
                    destino_lat, destino_lon,
                    max_alternativas=2,
                    travel_mode=tipo_vehiculo,
                )
            except Exception as exc:
                logger.warning("TomTom Routing no disponible en herramienta: %s", exc)

        if not rutas_viales:
            # Fallback: ruta Haversine única
            from src.ingestion.tomtom_routing import _fallback_haversine
            rutas_viales = [_fallback_haversine(
                origen_lat, origen_lon, destino_lat, destino_lon
            )]

        # ── 2. Preparar motor Monte Carlo ────────────────────────────────────
        estado_inicial = _estado_desde_hora_dia(hora, dia)
        motor = _get_default_engine()

        # ── 3. Evaluar cada ruta ─────────────────────────────────────────────
        resultados = evaluar_rutas(
            rutas_viales   = rutas_viales,
            motor_mc       = motor,
            cadena_markov  = None,   # ya embebido en el motor
            estado_inicial = estado_inicial,
        )

        if not resultados:
            return {"error": "No se pudieron evaluar las rutas."}

        mejor     = resultados[0]
        principal = next((r for r in resultados if r.indice == 0), mejor)
        explicacion = generar_explicacion_cambio_ruta(mejor, principal)

        return {
            "ruta_recomendada": {
                "nombre":       mejor.nombre,
                "distancia_km": round(mejor.distancia_km, 1),
                "p10":          round(mejor.p10, 0),
                "p50":          round(mejor.p50, 0),
                "p90":          round(mejor.p90, 0),
                "ic":           round(mejor.ic, 2),
                "semaforo":     mejor.semaforo,
            },
            "alternativas": [
                {
                    "nombre":            r.nombre,
                    "distancia_km":      round(r.distancia_km, 1),
                    "p50":               round(r.p50, 0),
                    "ic":                round(r.ic, 2),
                    "semaforo":          r.semaforo,
                    "ratio_compromiso":  round(r.ratio_compromiso, 2),
                    "es_recomendada":    r.es_recomendada,
                }
                for r in resultados
            ],
            "cambio_ruta":         mejor.indice != 0,
            "explicacion":         explicacion,
            "n_rutas_evaluadas":   len(resultados),
        }

    except Exception as exc:
        logger.warning("Error en selección de mejor ruta: %s", exc)
        return {"error": str(exc)}
