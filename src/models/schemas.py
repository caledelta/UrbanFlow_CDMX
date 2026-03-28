"""
Pydantic schemas — capa de validación de tipos para UrbanFlow CDMX.

Fase 1 de Structured Outputs: garantiza que los datos provenientes de
fuentes externas (TomTom, OpenWeatherMap) y los resultados del motor de
simulación tengan tipos correctos y rangos válidos antes de ser consumidos
por capas superiores (API, dashboard, agente conversacional).

Modelos
-------
RespuestaTomTom      — campos clave del Traffic Flow API de TomTom.
RespuestaClima       — condición climática procesada de OpenWeatherMap.
PrediccionViaje      — resultado de simulación Monte Carlo (P10/P50/P90).
PerturbacionActiva   — perturbación contextual activa sobre la cadena de Markov.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ──────────────────────────────────────────────────────────────────────
# Colores semáforo compartidos
# ──────────────────────────────────────────────────────────────────────

NivelAlerta = Literal["VERDE", "AMARILLA", "NARANJA", "ROJA"]

# Mapeo desde los niveles internos de FactorClimatico → NivelAlerta
NIVEL_INTERNO_A_COLOR: dict[str, NivelAlerta] = {
    "normal":   "VERDE",
    "moderado": "AMARILLA",
    "severo":   "NARANJA",
    "extremo":  "ROJA",
}


# ──────────────────────────────────────────────────────────────────────
# RespuestaTomTom
# ──────────────────────────────────────────────────────────────────────

class RespuestaTomTom(BaseModel):
    """
    Validación de los campos clave devueltos por la Traffic Flow API de TomTom.

    Se construye a partir del bloque ``flowSegmentData`` del JSON de respuesta
    antes de que los valores sean escritos en un ``SegmentoVial``.

    Atributos
    ---------
    velocidad_actual_kmh : float
        Velocidad observada en el segmento [0, 300] km/h.
    velocidad_libre_kmh : float
        Velocidad en flujo libre [0, 300] km/h.
    confianza : float
        Confianza del dato en [0.0, 1.0].
        1.0 = GPS en vivo; 0.0 = estimado por modelo.
    ratio_flujo : float
        ``velocidad_actual / velocidad_libre`` en [0.0, 1.0].
        Valores < 0.5 indican congestión severa.
    """

    velocidad_actual_kmh: float = Field(ge=0.0, le=300.0)
    velocidad_libre_kmh: float = Field(ge=0.0, le=300.0)
    confianza: float = Field(ge=0.0, le=1.0)
    ratio_flujo: float = Field(ge=0.0, le=1.0)


# ──────────────────────────────────────────────────────────────────────
# RespuestaClima
# ──────────────────────────────────────────────────────────────────────

class RespuestaClima(BaseModel):
    """
    Condición climática procesada de OpenWeatherMap, lista para el motor
    de simulación.

    Combina datos de ``CondicionClimatica`` con el resultado de
    ``calcular_factor_congestion()`` en un objeto validado.

    Atributos
    ---------
    descripcion : str
        Resumen legible de las condiciones activas (ej. "lluvia 5.0 mm/h").
    lluvia_mm_h : float
        Precipitación acumulada en la última hora (mm/h ≥ 0).
    visibilidad_km : float
        Visibilidad horizontal en km [0, 100].
    factor_velocidad : float
        Factor multiplicador de congestión climática [1.0, 2.5].
        Se aplica como divisor de las velocidades del motor Monte Carlo.
    nivel_alerta : NivelAlerta
        Semáforo de condición climática:
        VERDE (normal) · AMARILLA (moderado) · NARANJA (severo) · ROJA (extremo).
    """

    descripcion: str
    lluvia_mm_h: float = Field(ge=0.0)
    visibilidad_km: float = Field(ge=0.0, le=100.0)
    factor_velocidad: float = Field(ge=1.0, le=2.5)
    nivel_alerta: NivelAlerta


# ──────────────────────────────────────────────────────────────────────
# PrediccionViaje
# ──────────────────────────────────────────────────────────────────────

class PrediccionViaje(BaseModel):
    """
    Resultado de la simulación Monte Carlo para un origen–destino dado.

    Atributos
    ---------
    origen : str
        Nombre o descripción del punto de origen.
    destino : str
        Nombre o descripción del punto de destino.
    p10_min : float
        Percentil 10 del tiempo de viaje simulado (minutos ≥ 0).
        Escenario optimista.
    p50_min : float
        Percentil 50 / mediana (minutos ≥ 0).
        Estimación central.
    p90_min : float
        Percentil 90 (minutos ≥ 0).
        Escenario pesimista.
    nivel_alerta : NivelAlerta
        Condición de tráfico al momento de la predicción.
    resumen : str
        Texto descriptivo del trayecto para la interfaz de usuario.

    Validaciones
    ------------
    p10_min ≤ p50_min ≤ p90_min  (invariante de orden de percentiles).
    """

    origen: str
    destino: str
    p10_min: float = Field(ge=0.0)
    p50_min: float = Field(ge=0.0)
    p90_min: float = Field(ge=0.0)
    nivel_alerta: NivelAlerta
    resumen: str

    @model_validator(mode="after")
    def _orden_percentiles(self) -> "PrediccionViaje":
        if not (self.p10_min <= self.p50_min <= self.p90_min):
            raise ValueError(
                f"Los percentiles deben cumplir p10 ≤ p50 ≤ p90. "
                f"Recibidos: p10={self.p10_min}, p50={self.p50_min}, "
                f"p90={self.p90_min}."
            )
        return self


# ──────────────────────────────────────────────────────────────────────
# PerturbacionActiva
# ──────────────────────────────────────────────────────────────────────

class PerturbacionActiva(BaseModel):
    """
    Perturbación contextual activa que modifica la matriz de Markov.

    Corresponde a un evento atípico recurrente de la ZMVM (cierre de Metro,
    marcha, festivo, etc.) que sesga la probabilidad de transición al estado
    Congestionado antes de la simulación Monte Carlo.

    Atributos
    ---------
    tipo : str
        Categoría del evento (ej. "cierre_metro", "marcha", "festivo").
    descripcion : str
        Descripción legible del evento activo.
    factor : float
        Multiplicador sobre P[i,2] de la matriz de Markov [0.1, 5.0].
        Factor < 1 reduce congestión (temporada baja); > 1 la incrementa.
    alcaldias : list[str]
        Alcaldías/municipios afectados. Lista vacía = afecta toda la ZMVM.
    horas : tuple[int, int]
        Ventana horaria de efecto (hora_inicio, hora_fin) en [0, 23].
        Ej: (16, 22) = impacto de 16:00 a 22:00 h.

    Validaciones
    ------------
    - Cada hora en horas debe estar en [0, 23].
    - hora_inicio ≤ hora_fin.
    """

    tipo: str
    descripcion: str
    factor: float = Field(ge=0.1, le=5.0)
    alcaldias: list[str]
    horas: tuple[int, int]

    @model_validator(mode="after")
    def _validar_horas(self) -> "PerturbacionActiva":
        h_ini, h_fin = self.horas
        if not (0 <= h_ini <= 23):
            raise ValueError(
                f"hora_inicio debe estar en [0, 23], se recibió {h_ini}."
            )
        if not (0 <= h_fin <= 23):
            raise ValueError(
                f"hora_fin debe estar en [0, 23], se recibió {h_fin}."
            )
        if h_ini > h_fin:
            raise ValueError(
                f"hora_inicio ({h_ini}) no puede ser mayor que hora_fin ({h_fin})."
            )
        return self
