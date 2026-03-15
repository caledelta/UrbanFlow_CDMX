"""
Módulo de cadenas de Markov para modelado de estados de tráfico.

Modela la evolución temporal del tráfico en la ZMVM como una cadena de Markov
de tiempo discreto con tres estados: fluido, lento y congestionado.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from enum import IntEnum


class EstadoTrafico(IntEnum):
    """Estados posibles del tráfico, ordenados por severidad."""
    FLUIDO       = 0
    LENTO        = 1
    CONGESTIONADO = 2


NOMBRES_ESTADO = {
    EstadoTrafico.FLUIDO:        "Fluido",
    EstadoTrafico.LENTO:         "Lento",
    EstadoTrafico.CONGESTIONADO: "Congestionado",
}

N_ESTADOS = len(EstadoTrafico)


class MarkovTrafficChain:
    """
    Cadena de Markov de tiempo discreto para modelar estados de tráfico.

    Representa el tráfico como una secuencia de transiciones entre tres estados:
    - **Fluido** (0): velocidades cercanas al límite permitido, sin demoras.
    - **Lento** (1): reducción de velocidad perceptible, demoras moderadas.
    - **Congestionado** (2): tráfico detenido o muy lento, demoras severas.

    La cadena se ajusta contando transiciones en una serie histórica y
    normalizando para obtener probabilidades de transición P(i → j).

    Parámetros
    ----------
    suavizado : float, opcional
        Constante de suavizado de Laplace aplicada al conteo de transiciones
        para evitar probabilidades cero. Por defecto 1e-6.

    Atributos
    ---------
    transition_matrix_ : np.ndarray de forma (3, 3)
        Matriz estocástica de transición donde ``transition_matrix_[i, j]``
        es la probabilidad de pasar del estado ``i`` al estado ``j``.
        Disponible tras llamar a ``fit()``.
    counts_ : np.ndarray de forma (3, 3)
        Conteo crudo de transiciones observadas (antes de normalizar).
    n_transitions_ : int
        Número de transiciones observadas en el ajuste.

    Ejemplo
    -------
    >>> import numpy as np
    >>> cadena = MarkovTrafficChain()
    >>> serie = np.array([0, 0, 1, 1, 2, 1, 0, 0, 1, 2])
    >>> cadena.fit(serie)
    >>> cadena.transition_matrix_
    array([[...]])
    """

    def __init__(self, suavizado: float = 1e-6) -> None:
        if suavizado < 0:
            raise ValueError("El parámetro 'suavizado' debe ser >= 0.")
        self.suavizado = suavizado

        self.transition_matrix_: np.ndarray | None = None
        self.counts_: np.ndarray | None = None
        self.n_transitions_: int = 0

    # ------------------------------------------------------------------
    # Ajuste
    # ------------------------------------------------------------------

    def fit(self, series: np.ndarray | pd.Series) -> "MarkovTrafficChain":
        """
        Estima la matriz de transición a partir de una serie histórica de estados.

        Cuenta todas las transiciones consecutivas (t → t+1) en la serie y
        normaliza cada fila para obtener probabilidades.

        Parámetros
        ----------
        series : array-like de enteros (0, 1 ó 2)
            Secuencia temporal de estados de tráfico. Los valores deben
            pertenecer a {0, 1, 2}; cualquier NaN es eliminado antes del ajuste.

        Devuelve
        --------
        self
            La instancia ajustada, para permitir encadenamiento ``fit().predict()``.

        Raises
        ------
        ValueError
            Si la serie tiene menos de 2 observaciones válidas o contiene
            valores fuera del rango {0, 1, 2}.
        """
        arr = _validar_serie(series)

        counts = np.full((N_ESTADOS, N_ESTADOS), self.suavizado)
        for origen, destino in zip(arr[:-1], arr[1:]):
            counts[origen, destino] += 1

        # Normalización fila a fila (suma = 1 por estado de origen).
        # Si una fila suma cero (estado nunca visto como origen), se asigna
        # distribución uniforme para garantizar una matriz estocástica válida.
        totales = counts.sum(axis=1, keepdims=True)
        filas_cero = (totales == 0).flatten()
        totales[filas_cero] = 1.0          # evitar división por cero
        matriz = counts / totales
        matriz[filas_cero] = 1.0 / N_ESTADOS
        self.transition_matrix_ = matriz
        self.counts_ = counts - self.suavizado   # conteos crudos sin suavizado
        self.n_transitions_ = len(arr) - 1
        return self

    # ------------------------------------------------------------------
    # Predicción
    # ------------------------------------------------------------------

    def predict_distribution(
        self,
        estado_inicial: int | EstadoTrafico,
        pasos: int,
    ) -> np.ndarray:
        """
        Calcula la distribución de probabilidad tras ``pasos`` transiciones.

        Aplica la potencia de la matriz: si el vector inicial es ``v``, la
        distribución en el paso ``k`` es ``v @ P^k``.

        Parámetros
        ----------
        estado_inicial : int o EstadoTrafico
            Estado de partida (0=Fluido, 1=Lento, 2=Congestionado).
        pasos : int
            Número de pasos hacia adelante (horizonte de predicción).

        Devuelve
        --------
        np.ndarray de forma (3,)
            Vector de probabilidades [P(Fluido), P(Lento), P(Congestionado)]
            en el paso ``t + pasos``.

        Raises
        ------
        RuntimeError
            Si el modelo no ha sido ajustado con ``fit()`` previamente.
        ValueError
            Si ``estado_inicial`` o ``pasos`` son inválidos.
        """
        self._verificar_ajuste()
        estado_inicial = int(estado_inicial)
        _validar_estado(estado_inicial)
        if pasos < 0:
            raise ValueError(f"'pasos' debe ser >= 0, se recibió {pasos}.")

        v = np.zeros(N_ESTADOS)
        v[estado_inicial] = 1.0

        P_k = np.linalg.matrix_power(self.transition_matrix_, pasos)
        return v @ P_k

    def predict_estado(
        self,
        estado_inicial: int | EstadoTrafico,
        pasos: int,
    ) -> EstadoTrafico:
        """
        Devuelve el estado más probable tras ``pasos`` transiciones.

        Parámetros
        ----------
        estado_inicial : int o EstadoTrafico
            Estado de partida.
        pasos : int
            Horizonte de predicción.

        Devuelve
        --------
        EstadoTrafico
            Estado con mayor probabilidad en ``t + pasos``.
        """
        dist = self.predict_distribution(estado_inicial, pasos)
        return EstadoTrafico(int(np.argmax(dist)))

    # ------------------------------------------------------------------
    # Estado estacionario
    # ------------------------------------------------------------------

    def steady_state(self) -> np.ndarray:
        """
        Calcula la distribución estacionaria de la cadena.

        Resuelve el sistema ``π P = π`` mediante descomposición de
        valores propios izquierdos (equivalente a valores propios derechos
        de ``P^T``). El vector propio asociado al valor propio 1 corresponde
        a la distribución de largo plazo del tráfico.

        Devuelve
        --------
        np.ndarray de forma (3,)
            Vector de probabilidades estacionarias
            [π(Fluido), π(Lento), π(Congestionado)].

        Raises
        ------
        RuntimeError
            Si el modelo no ha sido ajustado.
        """
        self._verificar_ajuste()

        valores, vectores = np.linalg.eig(self.transition_matrix_.T)
        # El vector propio asociado al valor propio más cercano a 1.0
        idx = np.argmin(np.abs(valores - 1.0))
        pi = np.real(vectores[:, idx])
        pi = np.abs(pi)          # garantizar valores positivos
        return pi / pi.sum()     # normalizar a distribución de probabilidad

    # ------------------------------------------------------------------
    # Simulación
    # ------------------------------------------------------------------

    def simulate(
        self,
        n_pasos: int,
        estado_inicial: int | EstadoTrafico | None = None,
        rng: np.random.Generator | None = None,
    ) -> np.ndarray:
        """
        Genera una trayectoria aleatoria de la cadena de Markov.

        Útil para alimentar el motor Monte Carlo con secuencias de
        estados de tráfico sintéticas.

        Parámetros
        ----------
        n_pasos : int
            Longitud de la trayectoria (número de estados a generar,
            incluyendo el estado inicial).
        estado_inicial : int, EstadoTrafico o None
            Estado de partida. Si es ``None``, se muestrea desde la
            distribución estacionaria.
        rng : np.random.Generator o None
            Generador de números aleatorios. Si es ``None`` se usa
            ``np.random.default_rng()``.

        Devuelve
        --------
        np.ndarray de forma (n_pasos,) con dtype int
            Secuencia de estados simulados.

        Raises
        ------
        RuntimeError
            Si el modelo no ha sido ajustado.
        ValueError
            Si ``n_pasos`` < 1 o el estado inicial es inválido.
        """
        self._verificar_ajuste()
        if n_pasos < 1:
            raise ValueError(f"'n_pasos' debe ser >= 1, se recibió {n_pasos}.")
        if rng is None:
            rng = np.random.default_rng()

        if estado_inicial is None:
            pi = self.steady_state()
            estado_actual = int(rng.choice(N_ESTADOS, p=pi))
        else:
            estado_actual = int(estado_inicial)
            _validar_estado(estado_actual)

        trayectoria = np.empty(n_pasos, dtype=int)
        trayectoria[0] = estado_actual

        for t in range(1, n_pasos):
            probs = self.transition_matrix_[estado_actual]
            estado_actual = int(rng.choice(N_ESTADOS, p=probs))
            trayectoria[t] = estado_actual

        return trayectoria

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def resumen(self) -> pd.DataFrame:
        """
        Devuelve la matriz de transición como DataFrame con etiquetas legibles.

        Devuelve
        --------
        pd.DataFrame de forma (3, 3)
            Filas = estado origen, columnas = estado destino.
        """
        self._verificar_ajuste()
        etiquetas = [NOMBRES_ESTADO[e] for e in EstadoTrafico]
        return pd.DataFrame(
            self.transition_matrix_,
            index=etiquetas,
            columns=etiquetas,
        )

    def _verificar_ajuste(self) -> None:
        """Lanza RuntimeError si el modelo no ha sido ajustado."""
        if self.transition_matrix_ is None:
            raise RuntimeError(
                "El modelo no ha sido ajustado. Llama a fit() primero."
            )


# ──────────────────────────────────────────────────────────────────────
# Funciones auxiliares privadas
# ──────────────────────────────────────────────────────────────────────

def _validar_serie(series: np.ndarray | pd.Series) -> np.ndarray:
    """Convierte la serie a array int, elimina NaN y valida valores."""
    if isinstance(series, pd.Series):
        series = series.dropna().to_numpy()
    arr = np.asarray(series, dtype=float)
    arr = arr[~np.isnan(arr)].astype(int)

    if len(arr) < 2:
        raise ValueError(
            f"La serie debe tener al menos 2 observaciones válidas "
            f"(se encontraron {len(arr)})."
        )
    valores_invalidos = set(arr) - {0, 1, 2}
    if valores_invalidos:
        raise ValueError(
            f"La serie contiene valores fuera de {{0, 1, 2}}: {valores_invalidos}."
        )
    return arr


def _validar_estado(estado: int) -> None:
    """Lanza ValueError si el estado no es 0, 1 ó 2."""
    if estado not in (0, 1, 2):
        raise ValueError(
            f"Estado inválido: {estado}. Debe ser 0 (Fluido), "
            f"1 (Lento) o 2 (Congestionado)."
        )
