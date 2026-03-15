"""
Pipeline integrador de fuentes de datos para UrbanFlow CDMX.

Combina las tres fuentes en tiempo real:
- **TomTomTrafficClient**  → velocidades actuales por corredor vial
- **OpenWeatherMapClient** → condiciones climáticas actuales
- ``ajustar_velocidades_por_clima`` → ajuste estocástico por clima

Y produce un ``ContextoViaje`` listo para alimentar ``MonteCarloEngine``.

Flujo típico
------------
::

    pipeline = PipelineIntegrador(tomtom_client, owm_client)
    contexto = pipeline.obtener_contexto(
        coordenadas_corredor=[(19.43, -99.13), (19.44, -99.14)],
        lat_clima=19.43,
        lon_clima=-99.13,
    )
    consulta = contexto.a_consulta(distancia_km=12.5)
    motor    = contexto.crear_motor(cadena)
    resultado = motor.correr(consulta)

Inferencia del estado de tráfico
---------------------------------
El estado inicial para el motor Monte Carlo se infiere del ratio de
congestión promedio de TomTom (velocidad_actual / velocidad_libre):

- ratio ≥ 0.75 → **FLUIDO**        (tráfico fluye al ≥75% de la velocidad libre)
- ratio ≥ 0.45 → **LENTO**         (velocidad reducida, 45–75%)
- ratio <  0.45 → **CONGESTIONADO** (velocidad severa, <45% de la libre)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.ingestion.tomtom_client import (
    TomTomTrafficClient,
    TomTomAPIError,
)
from src.ingestion.weather_client import (
    OpenWeatherMapClient,
    CondicionClimatica,
    FactorClimatico,
    calcular_factor_congestion,
    ajustar_velocidades_por_clima,
)
from src.simulation.markov_chain import EstadoTrafico, MarkovTrafficChain
from src.simulation.monte_carlo import (
    ConsultaViaje,
    MonteCarloEngine,
    ResultadoSimulacion,
    VELOCIDAD_PARAMS,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Umbrales para inferir estado de tráfico desde ratio_congestion TomTom
# ──────────────────────────────────────────────────────────────────────

UMBRAL_FLUIDO = 0.75   # ratio >= 0.75 → FLUIDO
UMBRAL_LENTO  = 0.45   # ratio >= 0.45 → LENTO; ratio < 0.45 → CONGESTIONADO


# ──────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ContextoViaje:
    """
    Contexto en tiempo real del viaje, listo para alimentar MonteCarloEngine.

    Combina el estado de tráfico inferido de TomTom con los parámetros de
    velocidad ajustados por el factor climático de OWM.

    Atributos
    ---------
    estado_inicial : int
        Estado de tráfico inferido del corredor (0=Fluido, 1=Lento, 2=Congestionado).
    velocidad_params : dict
        Parámetros de velocidad por estado ajustados por clima.
        Misma estructura que ``VELOCIDAD_PARAMS`` en ``monte_carlo.py``.
    factor_climatico : FactorClimatico
        Factor de ajuste climático calculado a partir de OWM.
    clima : CondicionClimatica
        Condiciones climáticas en el momento de la consulta.
    segmentos : pd.DataFrame
        Datos brutos de TomTom para los segmentos consultados del corredor.
    timestamp_utc : str
        Marca de tiempo ISO 8601 de la consulta (UTC).
    ratio_congestion_promedio : float
        Ratio de congestión promedio del corredor (velocidad_actual / velocidad_libre).
    n_segmentos : int
        Número de segmentos viales consultados exitosamente.
    """

    estado_inicial:             int
    velocidad_params:           dict[int, dict[str, float]]
    factor_climatico:           FactorClimatico
    clima:                      CondicionClimatica
    segmentos:                  pd.DataFrame
    timestamp_utc:              str
    ratio_congestion_promedio:  float
    n_segmentos:                int

    # ------------------------------------------------------------------
    # Integración con el motor estocástico
    # ------------------------------------------------------------------

    def a_consulta(self, distancia_km: float) -> ConsultaViaje:
        """
        Crea una ``ConsultaViaje`` con el estado inicial inferido del corredor.

        Parámetros
        ----------
        distancia_km : float
            Distancia del recorrido en kilómetros (> 0).

        Devuelve
        --------
        ConsultaViaje
        """
        return ConsultaViaje(
            distancia_km   = distancia_km,
            estado_inicial = self.estado_inicial,
        )

    def crear_motor(
        self,
        cadena:         MarkovTrafficChain,
        n_simulaciones: int = MonteCarloEngine.N_SIMULACIONES_DEFAULT,
        **kwargs: Any,
    ) -> MonteCarloEngine:
        """
        Crea un ``MonteCarloEngine`` con los parámetros de velocidad ajustados
        por el factor climático.

        Parámetros
        ----------
        cadena : MarkovTrafficChain
            Cadena ya ajustada con ``fit()``.
        n_simulaciones : int, opcional
            Número de trayectorias Monte Carlo. Por defecto 10 000.
        **kwargs
            Parámetros adicionales para ``MonteCarloEngine``
            (``paso_minutos``, ``max_pasos``, ``rng``).

        Devuelve
        --------
        MonteCarloEngine
        """
        return MonteCarloEngine(
            cadena           = cadena,
            n_simulaciones   = n_simulaciones,
            velocidad_params = self.velocidad_params,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def a_dict(self) -> dict[str, Any]:
        """
        Serializa el contexto (sin el DataFrame de segmentos) para logging o API.
        """
        return {
            "estado_inicial":            self.estado_inicial,
            "nombre_estado":             EstadoTrafico(self.estado_inicial).name,
            "ratio_congestion_promedio": round(self.ratio_congestion_promedio, 4),
            "n_segmentos":               self.n_segmentos,
            "factor_climatico":          self.factor_climatico.a_dict(),
            "nivel_alerta_clima":        self.factor_climatico.nivel_alerta,
            "timestamp_utc":             self.timestamp_utc,
        }


# ──────────────────────────────────────────────────────────────────────
# Pipeline principal
# ──────────────────────────────────────────────────────────────────────

class PipelineIntegrador:
    """
    Pipeline integrador de fuentes de datos en tiempo real para UrbanFlow CDMX.

    Orquesta las consultas a TomTom y OpenWeatherMap, aplica el ajuste
    climático a los parámetros de velocidad y devuelve un ``ContextoViaje``
    listo para el motor estocástico.

    Parámetros
    ----------
    tomtom : TomTomTrafficClient
        Cliente de TomTom ya configurado con API key.
    owm : OpenWeatherMapClient
        Cliente de OpenWeatherMap ya configurado con API key.

    Raises
    ------
    TypeError
        Si ``tomtom`` u ``owm`` no son instancias de los tipos esperados.

    Ejemplo
    -------
    >>> pipeline = PipelineIntegrador(tomtom_client, owm_client)
    >>> contexto = pipeline.obtener_contexto(
    ...     coordenadas_corredor=[(19.4326, -99.1332), (19.4400, -99.1400)],
    ...     lat_clima=19.4326,
    ...     lon_clima=-99.1332,
    ... )
    >>> motor   = contexto.crear_motor(cadena_ajustada)
    >>> result  = motor.correr(contexto.a_consulta(distancia_km=10.0))
    """

    def __init__(
        self,
        tomtom: TomTomTrafficClient,
        owm:    OpenWeatherMapClient,
    ) -> None:
        if not isinstance(tomtom, TomTomTrafficClient):
            raise TypeError(
                f"'tomtom' debe ser TomTomTrafficClient, "
                f"se recibió {type(tomtom).__name__}."
            )
        if not isinstance(owm, OpenWeatherMapClient):
            raise TypeError(
                f"'owm' debe ser OpenWeatherMapClient, "
                f"se recibió {type(owm).__name__}."
            )
        self.tomtom = tomtom
        self.owm    = owm

    # ------------------------------------------------------------------
    # API pública — contexto en tiempo real
    # ------------------------------------------------------------------

    def obtener_contexto(
        self,
        coordenadas_corredor: list[tuple[float, float]],
        lat_clima:            float,
        lon_clima:            float,
    ) -> ContextoViaje:
        """
        Obtiene el contexto en tiempo real del viaje para un corredor vial.

        Pasos
        -----
        1. Consulta velocidades en todos los puntos del corredor (TomTom).
        2. Infiere el estado de tráfico del corredor a partir del ratio de
           congestión promedio.
        3. Obtiene condiciones climáticas actuales en el punto de referencia (OWM).
        4. Calcula el factor climático y ajusta los parámetros de velocidad.
        5. Devuelve el ``ContextoViaje`` integrado.

        Parámetros
        ----------
        coordenadas_corredor : list de (lat, lon)
            Lista de coordenadas del corredor a consultar.
        lat_clima : float
            Latitud del punto de referencia para la consulta climática
            (normalmente el centroide o punto de origen del corredor).
        lon_clima : float
            Longitud del punto de referencia para la consulta climática.

        Devuelve
        --------
        ContextoViaje

        Raises
        ------
        ValueError
            Si ``coordenadas_corredor`` está vacía.
        TomTomAPIError
            Si todos los segmentos del corredor fallan.
        OWMAPIError
            Si la consulta climática falla.
        """
        if not coordenadas_corredor:
            raise ValueError("'coordenadas_corredor' no puede estar vacía.")

        # 1. Velocidades en tiempo real
        logger.info(
            "Consultando %d segmentos TomTom para el corredor...",
            len(coordenadas_corredor),
        )
        segmentos_df = self.tomtom.obtener_segmentos_lote(coordenadas_corredor)

        if segmentos_df.empty:
            raise TomTomAPIError(
                "No se obtuvieron datos de tráfico para ningún segmento del corredor."
            )

        # 2. Inferir estado de tráfico
        ratio_promedio = float(segmentos_df["ratio_congestion"].mean())
        estado_inicial = _inferir_estado_trafico(ratio_promedio)
        n_segmentos    = len(segmentos_df)

        logger.info(
            "Corredor: %d segmentos, ratio_promedio=%.3f, estado=%s",
            n_segmentos,
            ratio_promedio,
            EstadoTrafico(estado_inicial).name,
        )

        # 3. Condiciones climáticas actuales
        logger.info(
            "Consultando clima OWM en (%.4f, %.4f)...", lat_clima, lon_clima
        )
        clima = self.owm.obtener_clima_actual(lat_clima, lon_clima)

        # 4. Factor climático y ajuste de parámetros de velocidad
        factor                  = calcular_factor_congestion(clima)
        velocidad_params_ajust  = ajustar_velocidades_por_clima(VELOCIDAD_PARAMS, factor)

        logger.info(
            "Factor climático: %.4f (nivel=%s)",
            factor.factor_multiplicador,
            factor.nivel_alerta,
        )

        return ContextoViaje(
            estado_inicial            = estado_inicial,
            velocidad_params          = velocidad_params_ajust,
            factor_climatico          = factor,
            clima                     = clima,
            segmentos                 = segmentos_df,
            timestamp_utc             = pd.Timestamp.utcnow().isoformat(),
            ratio_congestion_promedio = ratio_promedio,
            n_segmentos               = n_segmentos,
        )

    # ------------------------------------------------------------------
    # Método de conveniencia: pipeline completo en una llamada
    # ------------------------------------------------------------------

    def predecir_tiempo_viaje(
        self,
        coordenadas_corredor: list[tuple[float, float]],
        lat_clima:            float,
        lon_clima:            float,
        distancia_km:         float,
        cadena:               MarkovTrafficChain,
        n_simulaciones:       int = MonteCarloEngine.N_SIMULACIONES_DEFAULT,
        **kwargs: Any,
    ) -> tuple[ContextoViaje, ResultadoSimulacion]:
        """
        Ejecuta el pipeline completo y devuelve el resultado de la simulación.

        Combina ``obtener_contexto()`` + ``crear_motor()`` + ``correr()``
        en una sola llamada para casos de uso directos.

        Parámetros
        ----------
        coordenadas_corredor : list de (lat, lon)
        lat_clima, lon_clima : float
        distancia_km : float
            Distancia del recorrido en kilómetros.
        cadena : MarkovTrafficChain
            Cadena ya ajustada con ``fit()``.
        n_simulaciones : int, opcional
        **kwargs
            Parámetros adicionales para ``MonteCarloEngine``.

        Devuelve
        --------
        tuple[ContextoViaje, ResultadoSimulacion]
        """
        contexto  = self.obtener_contexto(coordenadas_corredor, lat_clima, lon_clima)
        consulta  = contexto.a_consulta(distancia_km)
        motor     = contexto.crear_motor(cadena, n_simulaciones=n_simulaciones, **kwargs)
        resultado = motor.correr(consulta)
        return contexto, resultado


# ──────────────────────────────────────────────────────────────────────
# Función auxiliar privada
# ──────────────────────────────────────────────────────────────────────

def _inferir_estado_trafico(ratio_congestion: float) -> int:
    """
    Infiere el estado de tráfico desde el ratio de congestión promedio de TomTom.

    Umbrales calibrados para la ZMVM:

    - ratio ≥ 0.75 → FLUIDO        (≥75% de la velocidad libre)
    - ratio ≥ 0.45 → LENTO         (45–75%)
    - ratio <  0.45 → CONGESTIONADO (<45% de la velocidad libre)

    Parámetros
    ----------
    ratio_congestion : float
        Promedio del ratio de congestión de los segmentos del corredor.

    Devuelve
    --------
    int
        0 (FLUIDO), 1 (LENTO) ó 2 (CONGESTIONADO).
    """
    if ratio_congestion >= UMBRAL_FLUIDO:
        return int(EstadoTrafico.FLUIDO)
    if ratio_congestion >= UMBRAL_LENTO:
        return int(EstadoTrafico.LENTO)
    return int(EstadoTrafico.CONGESTIONADO)
