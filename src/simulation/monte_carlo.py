"""
Motor de simulación Monte Carlo para predicción de tiempos de viaje.

Combina la cadena de Markov de estados de tráfico con distribuciones
estocásticas de velocidad por estado para producir, en cada consulta,
una distribución completa de tiempos de viaje con bandas de incertidumbre
P10 / P50 / P90 calibradas para la ZMVM.

Arquitectura de la simulación
------------------------------
Para una consulta de distancia ``d`` km con estado inicial ``s``:

1. Se generan ``N`` trayectorias de estados de tráfico en paralelo
   usando la matriz de transición de la cadena de Markov.
2. En cada paso temporal de cada trayectoria se muestrea una velocidad
   desde la distribución del estado activo (Normal truncada).
3. La distancia acumulada por trayectoria se computa con ``cumsum``.
4. El tiempo de viaje de cada trayectoria es el instante (interpolado)
   en que la distancia acumulada supera ``d``.
5. Se calculan los percentiles sobre las ``N`` trayectorias.

Toda la simulación es vectorizada sobre el eje de simulaciones para
garantizar rendimiento con N = 10 000.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.simulation.markov_chain import (
    EstadoTrafico,
    MarkovTrafficChain,
    N_ESTADOS,
    NOMBRES_ESTADO,
)

# ──────────────────────────────────────────────────────────────────────
# Parámetros de velocidad por estado — calibrados para ZMVM (km/h)
# Fuente de referencia: TomTom Traffic Index CDMX + SEMOVI aforos
# ──────────────────────────────────────────────────────────────────────

VELOCIDAD_PARAMS: dict[int, dict[str, float]] = {
    int(EstadoTrafico.FLUIDO): {
        "media": 40.0, "std":  8.0, "min": 20.0, "max": 80.0,
    },
    int(EstadoTrafico.LENTO): {
        "media": 18.0, "std":  5.0, "min":  5.0, "max": 35.0,
    },
    int(EstadoTrafico.CONGESTIONADO): {
        "media":  7.0, "std":  3.0, "min":  2.0, "max": 15.0,
    },
}


# ──────────────────────────────────────────────────────────────────────
# Estructuras de datos públicas
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ConsultaViaje:
    """
    Parámetros de una consulta de predicción de tiempo de viaje.

    Parámetros
    ----------
    distancia_km : float
        Distancia del recorrido en kilómetros (> 0).
    estado_inicial : int o EstadoTrafico
        Estado de tráfico observado al inicio del viaje.
        0 = Fluido, 1 = Lento, 2 = Congestionado.
    """
    distancia_km: float
    estado_inicial: int | EstadoTrafico

    def __post_init__(self) -> None:
        self.estado_inicial = int(self.estado_inicial)
        if self.distancia_km <= 0:
            raise ValueError(
                f"'distancia_km' debe ser > 0, se recibió {self.distancia_km}."
            )
        if self.estado_inicial not in (0, 1, 2):
            raise ValueError(
                f"'estado_inicial' debe ser 0, 1 ó 2, "
                f"se recibió {self.estado_inicial}."
            )


@dataclass
class ResultadoSimulacion:
    """
    Resultado completo de una simulación Monte Carlo.

    Atributos
    ---------
    tiempos_minutos : np.ndarray de forma (n_simulaciones,)
        Distribución completa de tiempos de viaje simulados en minutos.
    p10 : float
        Percentil 10: tiempo optimista (viaje rápido, tráfico favorable).
    p50 : float
        Percentil 50 (mediana): tiempo más probable.
    p90 : float
        Percentil 90: tiempo pesimista (tráfico adverso).
    media : float
        Tiempo medio de viaje.
    std : float
        Desviación estándar de los tiempos simulados.
    n_simulaciones : int
        Número de trayectorias simuladas.
    n_recortadas : int
        Simulaciones que alcanzaron ``max_pasos`` sin completar el viaje.
        Un valor alto sugiere aumentar ``max_pasos`` en el motor.
    estado_inicial : int
        Estado de tráfico usado como punto de partida.
    distancia_km : float
        Distancia del recorrido consultado.
    """
    tiempos_minutos: np.ndarray
    p10: float
    p50: float
    p90: float
    media: float
    std: float
    n_simulaciones: int
    n_recortadas: int
    estado_inicial: int
    distancia_km: float

    # ------------------------------------------------------------------
    # Propiedades derivadas
    # ------------------------------------------------------------------

    @property
    def banda_incertidumbre(self) -> float:
        """Amplitud de la banda P90 − P10 en minutos."""
        return self.p90 - self.p10

    @property
    def fraccion_recortadas(self) -> float:
        """Proporción de simulaciones que alcanzaron el límite de pasos."""
        return self.n_recortadas / self.n_simulaciones

    # ------------------------------------------------------------------
    # Consulta de percentiles arbitrarios
    # ------------------------------------------------------------------

    def percentil(self, q: float) -> float:
        """
        Calcula el percentil ``q`` de la distribución de tiempos.

        Parámetros
        ----------
        q : float
            Percentil deseado en el rango [0, 100].

        Devuelve
        --------
        float
            Tiempo de viaje en el percentil ``q``, en minutos.
        """
        if not (0.0 <= q <= 100.0):
            raise ValueError(f"'q' debe estar en [0, 100], se recibió {q}.")
        return float(np.percentile(self.tiempos_minutos, q))

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def a_dict(self) -> dict[str, Any]:
        """
        Convierte el resultado a diccionario serializable (para API REST).

        La distribución completa (``tiempos_minutos``) se excluye para
        reducir el tamaño del payload; usar ``percentil()`` para valores
        adicionales.
        """
        return {
            "distancia_km":       self.distancia_km,
            "estado_inicial":     NOMBRES_ESTADO[EstadoTrafico(self.estado_inicial)],
            "p10_minutos":        round(self.p10, 2),
            "p50_minutos":        round(self.p50, 2),
            "p90_minutos":        round(self.p90, 2),
            "media_minutos":      round(self.media, 2),
            "std_minutos":        round(self.std, 2),
            "banda_incertidumbre": round(self.banda_incertidumbre, 2),
            "n_simulaciones":     self.n_simulaciones,
            "n_recortadas":       self.n_recortadas,
        }

    def __repr__(self) -> str:
        return (
            f"ResultadoSimulacion("
            f"d={self.distancia_km}km, "
            f"P10={self.p10:.1f}min, "
            f"P50={self.p50:.1f}min, "
            f"P90={self.p90:.1f}min)"
        )


# ──────────────────────────────────────────────────────────────────────
# Motor Monte Carlo
# ──────────────────────────────────────────────────────────────────────

class MonteCarloEngine:
    """
    Motor de simulación Monte Carlo para predicción de tiempos de viaje.

    Ejecuta ``n_simulaciones`` trayectorias en paralelo combinando:
    - Una cadena de Markov para la evolución del estado de tráfico.
    - Velocidades estocásticas (Normal truncada) por estado de tráfico,
      calibradas con datos históricos de la ZMVM.

    La simulación es completamente vectorizada sobre el eje de trayectorias
    para garantizar eficiencia con el valor por defecto de 10 000 runs.

    Parámetros
    ----------
    cadena : MarkovTrafficChain
        Cadena de Markov ya ajustada con ``fit()``.
    n_simulaciones : int, opcional
        Número de trayectorias Monte Carlo por consulta. Por defecto 10 000.
    paso_minutos : float, opcional
        Resolución temporal de la simulación en minutos. Por defecto 1.0.
        Valores menores dan mayor precisión pero aumentan el tiempo de cómputo.
    max_pasos : int, opcional
        Límite máximo de pasos por trayectoria (horizonte temporal).
        Por defecto 480 (= 8 horas con paso de 1 minuto).
        Aumentar si se modelan recorridos muy largos o con tráfico severo.
    rng : np.random.Generator o None, opcional
        Generador de números aleatorios. Si es ``None`` se usa
        ``np.random.default_rng()``. Pasar una semilla fija para
        reproducibilidad.

    Raises
    ------
    RuntimeError
        Si ``cadena`` no ha sido ajustada con ``fit()``.
    ValueError
        Si algún parámetro numérico es inválido.

    Ejemplo
    -------
    >>> from src.simulation.markov_chain import MarkovTrafficChain
    >>> import numpy as np
    >>> serie = np.tile([0, 0, 1, 2, 1], 200)
    >>> cadena = MarkovTrafficChain().fit(serie)
    >>> motor = MonteCarloEngine(cadena, n_simulaciones=10_000, rng=np.random.default_rng(0))
    >>> consulta = ConsultaViaje(distancia_km=15.0, estado_inicial=0)
    >>> resultado = motor.correr(consulta)
    >>> print(resultado)
    ResultadoSimulacion(d=15.0km, P10=..., P50=..., P90=...)
    """

    N_SIMULACIONES_DEFAULT = 10_000
    PASO_MINUTOS_DEFAULT   = 1.0
    MAX_PASOS_DEFAULT      = 480       # 8 horas

    def __init__(
        self,
        cadena: MarkovTrafficChain,
        n_simulaciones: int = N_SIMULACIONES_DEFAULT,
        paso_minutos: float = PASO_MINUTOS_DEFAULT,
        max_pasos: int = MAX_PASOS_DEFAULT,
        rng: np.random.Generator | None = None,
        velocidad_params: dict[int, dict[str, float]] | None = None,
    ) -> None:
        _verificar_cadena_ajustada(cadena)
        if n_simulaciones < 1:
            raise ValueError(
                f"'n_simulaciones' debe ser >= 1, se recibió {n_simulaciones}."
            )
        if paso_minutos <= 0:
            raise ValueError(
                f"'paso_minutos' debe ser > 0, se recibió {paso_minutos}."
            )
        if max_pasos < 1:
            raise ValueError(
                f"'max_pasos' debe ser >= 1, se recibió {max_pasos}."
            )

        self.cadena              = cadena
        self.n_simulaciones      = n_simulaciones
        self.paso_minutos        = paso_minutos
        self.max_pasos           = max_pasos
        self._rng                = rng if rng is not None else np.random.default_rng()
        self._velocidad_params   = velocidad_params if velocidad_params is not None else VELOCIDAD_PARAMS

        # Matriz de transición acumulada (filas = origen, cols = destino)
        # Precomputada una vez para acelerar la simulación vectorizada.
        self._P_cumsum: np.ndarray = np.cumsum(
            cadena.transition_matrix_, axis=1
        )  # shape (3, 3)

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def correr(self, consulta: ConsultaViaje) -> ResultadoSimulacion:
        """
        Ejecuta la simulación Monte Carlo para una consulta de viaje.

        Parámetros
        ----------
        consulta : ConsultaViaje
            Distancia y estado de tráfico inicial del viaje.

        Devuelve
        --------
        ResultadoSimulacion
            Distribución completa de tiempos y percentiles P10/P50/P90.
        """
        tiempos, n_recortadas = self._simular_lote(
            distancia_km   = consulta.distancia_km,
            estado_inicial = consulta.estado_inicial,
        )

        return ResultadoSimulacion(
            tiempos_minutos = tiempos,
            p10             = float(np.percentile(tiempos, 10)),
            p50             = float(np.percentile(tiempos, 50)),
            p90             = float(np.percentile(tiempos, 90)),
            media           = float(tiempos.mean()),
            std             = float(tiempos.std()),
            n_simulaciones  = self.n_simulaciones,
            n_recortadas    = n_recortadas,
            estado_inicial  = consulta.estado_inicial,
            distancia_km    = consulta.distancia_km,
        )

    # ------------------------------------------------------------------
    # Núcleo de simulación (privado)
    # ------------------------------------------------------------------

    def _simular_lote(
        self,
        distancia_km: float,
        estado_inicial: int,
    ) -> tuple[np.ndarray, int]:
        """
        Corre todas las trayectorias en paralelo y devuelve los tiempos.

        Devuelve
        --------
        tiempos : np.ndarray de forma (n_simulaciones,)
            Tiempo de viaje en minutos para cada trayectoria.
        n_recortadas : int
            Trayectorias que alcanzaron ``max_pasos`` sin terminar.
        """
        # 1. Generar trayectorias de estados: (n_sims, max_pasos)
        estados = self._simular_estados(estado_inicial)

        # 2. Muestrear velocidades por estado: (n_sims, max_pasos) [km/h]
        velocidades = self._muestrear_velocidades(estados)

        # 3. Distancia cubierta por paso: velocidad × tiempo_del_paso [km]
        paso_horas = self.paso_minutos / 60.0
        distancia_por_paso = velocidades * paso_horas  # (n_sims, max_pasos)

        # 4. Distancia acumulada: (n_sims, max_pasos)
        distancia_acumulada = np.cumsum(distancia_por_paso, axis=1)

        # 5. Tiempo de llegada para cada trayectoria
        tiempos, n_recortadas = self._calcular_tiempos(
            distancia_acumulada, distancia_km
        )
        return tiempos, n_recortadas

    def _simular_estados(self, estado_inicial: int) -> np.ndarray:
        """
        Genera trayectorias de estados Markov para todas las simulaciones.

        Cada columna ``t`` se obtiene aplicando la matriz de transición
        vectorizada sobre todas las simulaciones simultáneamente.

        Devuelve
        --------
        np.ndarray de forma (n_simulaciones, max_pasos), dtype int8.
        """
        n, T = self.n_simulaciones, self.max_pasos
        estados = np.empty((n, T), dtype=np.int8)
        estados[:, 0] = estado_inicial

        for t in range(1, T):
            actual = estados[:, t - 1]             # (n,) int8
            u = self._rng.random(n)                # (n,) uniform [0, 1)

            # P_cumsum[actual] → (n, 3): umbrales acumulados por simulación.
            # Contar cuántos umbrales son < u → índice del siguiente estado.
            siguiente = (u[:, np.newaxis] >= self._P_cumsum[actual]).sum(axis=1)
            estados[:, t] = np.clip(siguiente, 0, N_ESTADOS - 1).astype(np.int8)

        return estados

    def _muestrear_velocidades(self, estados: np.ndarray) -> np.ndarray:
        """
        Muestrea velocidades (km/h) desde distribuciones Normal truncadas
        para cada celda (simulación, paso) según el estado de tráfico.

        Devuelve
        --------
        np.ndarray de forma (n_simulaciones, max_pasos), dtype float32.
        """
        velocidades = np.empty(estados.shape, dtype=np.float32)

        for estado_id, params in self._velocidad_params.items():
            mascara = (estados == estado_id)
            n_celdas = int(mascara.sum())
            if n_celdas == 0:
                continue
            muestras = self._rng.normal(params["media"], params["std"], n_celdas)
            velocidades[mascara] = np.clip(
                muestras, params["min"], params["max"]
            ).astype(np.float32)

        return velocidades

    def _calcular_tiempos(
        self,
        distancia_acumulada: np.ndarray,
        distancia_km: float,
    ) -> tuple[np.ndarray, int]:
        """
        Convierte la matriz de distancia acumulada en tiempos de viaje.

        Para cada trayectoria, localiza el primer paso en que la distancia
        supera ``distancia_km`` e interpola linealmente para obtener
        precisión sub-paso.

        Parámetros
        ----------
        distancia_acumulada : np.ndarray de forma (n_sims, max_pasos)
        distancia_km : float
            Distancia objetivo.

        Devuelve
        --------
        tiempos : np.ndarray de forma (n_sims,) [minutos]
        n_recortadas : int
        """
        n_sims = distancia_acumulada.shape[0]

        llego = distancia_acumulada >= distancia_km          # (n_sims, max_pasos) bool
        nunca_llego = ~llego.any(axis=1)                     # (n_sims,) bool
        n_recortadas = int(nunca_llego.sum())

        # Índice del primer paso donde se supera distancia_km
        idx = np.argmax(llego, axis=1)                       # (n_sims,)
        idx[nunca_llego] = self.max_pasos - 1                # poner en último paso

        sims = np.arange(n_sims)

        # Distancia al inicio y al final del paso de llegada
        dist_al_llegar   = distancia_acumulada[sims, idx]
        dist_paso_previo = np.where(
            idx > 0,
            distancia_acumulada[sims, np.maximum(idx - 1, 0)],
            0.0,
        )

        # Fracción del paso necesaria para cubrir exactamente distancia_km
        delta_paso = dist_al_llegar - dist_paso_previo
        fraccion = np.where(
            delta_paso > 0,
            (distancia_km - dist_paso_previo) / delta_paso,
            1.0,
        )
        fraccion = np.clip(fraccion, 0.0, 1.0)

        tiempos = (idx + fraccion) * self.paso_minutos       # minutos

        # Las trayectorias recortadas reciben el tiempo máximo del horizonte
        tiempos[nunca_llego] = self.max_pasos * self.paso_minutos

        return tiempos.astype(np.float64), n_recortadas


# ──────────────────────────────────────────────────────────────────────
# Función auxiliar privada
# ──────────────────────────────────────────────────────────────────────

def _verificar_cadena_ajustada(cadena: MarkovTrafficChain) -> None:
    """Lanza RuntimeError si la cadena no ha sido ajustada."""
    if cadena.transition_matrix_ is None:
        raise RuntimeError(
            "La cadena de Markov no ha sido ajustada. "
            "Llama a cadena.fit() antes de crear MonteCarloEngine."
        )
