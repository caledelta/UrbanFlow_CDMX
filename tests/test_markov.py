"""
Tests para src/simulation/markov_chain.py

Cubre: ajuste, forma de la matriz, propiedades estocásticas, predicción,
estado estacionario, simulación y manejo de errores.
"""

import numpy as np
import pandas as pd
import pytest

from src.simulation.markov_chain import (
    EstadoTrafico,
    MarkovTrafficChain,
    NOMBRES_ESTADO,
    N_ESTADOS,
)

# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def serie_simple() -> np.ndarray:
    """Serie determinista que cubre todas las transiciones posibles."""
    return np.array([0, 0, 1, 1, 2, 2, 1, 0, 0, 1, 2, 0])


@pytest.fixture
def cadena_ajustada(serie_simple) -> MarkovTrafficChain:
    """Cadena ya ajustada sobre serie_simple."""
    return MarkovTrafficChain().fit(serie_simple)


@pytest.fixture
def serie_pandas(serie_simple) -> pd.Series:
    """La misma serie como pd.Series con un NaN intercalado."""
    s = pd.Series(serie_simple, dtype=float)
    s.iloc[3] = np.nan
    return s


@pytest.fixture
def rng_fijo() -> np.random.Generator:
    return np.random.default_rng(seed=42)


# ──────────────────────────────────────────────────────────────────────
# Tests de ajuste (fit)
# ──────────────────────────────────────────────────────────────────────

class TestFit:
    def test_devuelve_self(self, serie_simple):
        cadena = MarkovTrafficChain()
        resultado = cadena.fit(serie_simple)
        assert resultado is cadena

    def test_forma_matriz(self, cadena_ajustada):
        assert cadena_ajustada.transition_matrix_.shape == (N_ESTADOS, N_ESTADOS)

    def test_filas_suman_uno(self, cadena_ajustada):
        sumas = cadena_ajustada.transition_matrix_.sum(axis=1)
        np.testing.assert_allclose(sumas, np.ones(N_ESTADOS), atol=1e-10)

    def test_probabilidades_no_negativas(self, cadena_ajustada):
        assert (cadena_ajustada.transition_matrix_ >= 0).all()

    def test_probabilidades_menor_igual_uno(self, cadena_ajustada):
        assert (cadena_ajustada.transition_matrix_ <= 1).all()

    def test_conteo_transiciones(self, serie_simple, cadena_ajustada):
        # La serie tiene len-1 = 11 transiciones
        assert cadena_ajustada.n_transitions_ == len(serie_simple) - 1

    def test_admite_pandas_series(self, serie_pandas):
        cadena = MarkovTrafficChain().fit(serie_pandas)
        assert cadena.transition_matrix_ is not None

    def test_nan_en_pandas_se_ignoran(self, serie_simple, serie_pandas):
        """Un NaN en la serie pandas no debe romper el ajuste."""
        cadena = MarkovTrafficChain().fit(serie_pandas)
        # Con NaN eliminado queda una serie más corta pero válida
        assert cadena.transition_matrix_.shape == (N_ESTADOS, N_ESTADOS)

    def test_serie_numpy_y_pandas_dan_misma_matriz(self, serie_simple):
        """Sin NaN, numpy y pandas deben producir resultados idénticos."""
        c_np = MarkovTrafficChain(suavizado=0).fit(serie_simple)
        c_pd = MarkovTrafficChain(suavizado=0).fit(pd.Series(serie_simple))
        np.testing.assert_allclose(
            c_np.transition_matrix_, c_pd.transition_matrix_
        )

    def test_suavizado_evita_ceros(self):
        """Con una serie corta puede haber transiciones no observadas."""
        serie = np.array([0, 0, 0, 0, 0])   # solo estado 0→0
        cadena = MarkovTrafficChain(suavizado=1e-6).fit(serie)
        # P(0→1) y P(0→2) deben ser > 0 por el suavizado
        assert cadena.transition_matrix_[0, 1] > 0
        assert cadena.transition_matrix_[0, 2] > 0

    def test_transicion_dominante_correcta(self):
        """Si todos los registros dicen 0→1, P(0→1) debe ser ~1."""
        serie = np.array([0, 1, 0, 1, 0, 1])
        cadena = MarkovTrafficChain(suavizado=0).fit(serie)
        assert cadena.transition_matrix_[0, 1] == pytest.approx(1.0, abs=1e-9)

    def test_re_ajuste_sobreescribe(self, cadena_ajustada):
        """Llamar fit() dos veces reemplaza el ajuste anterior."""
        serie2 = np.array([2, 2, 2, 2, 2])
        cadena_ajustada.fit(serie2)
        # Tras re-ajustar solo con estado 2, P(2→2) ≈ 1
        assert cadena_ajustada.transition_matrix_[2, 2] == pytest.approx(1.0, abs=1e-5)


# ──────────────────────────────────────────────────────────────────────
# Tests de predicción
# ──────────────────────────────────────────────────────────────────────

class TestPrediccion:
    def test_distribucion_paso_cero_es_one_hot(self, cadena_ajustada):
        """En paso 0, la distribución debe ser el vector one-hot del estado."""
        for estado in EstadoTrafico:
            dist = cadena_ajustada.predict_distribution(estado, pasos=0)
            esperado = np.zeros(N_ESTADOS)
            esperado[estado] = 1.0
            np.testing.assert_allclose(dist, esperado)

    def test_distribucion_suma_uno(self, cadena_ajustada):
        for estado in EstadoTrafico:
            dist = cadena_ajustada.predict_distribution(estado, pasos=5)
            assert dist.sum() == pytest.approx(1.0, abs=1e-10)

    def test_distribucion_valores_no_negativos(self, cadena_ajustada):
        dist = cadena_ajustada.predict_distribution(EstadoTrafico.FLUIDO, pasos=3)
        assert (dist >= 0).all()

    def test_predict_estado_devuelve_enum(self, cadena_ajustada):
        resultado = cadena_ajustada.predict_estado(EstadoTrafico.FLUIDO, pasos=1)
        assert isinstance(resultado, EstadoTrafico)

    def test_predict_estado_acepta_int(self, cadena_ajustada):
        resultado = cadena_ajustada.predict_estado(0, pasos=1)
        assert isinstance(resultado, EstadoTrafico)

    def test_distribucion_converge_a_estacionaria(self, cadena_ajustada):
        """Con suficientes pasos, la distribución converge al estado estacionario."""
        pi = cadena_ajustada.steady_state()
        for estado in EstadoTrafico:
            dist = cadena_ajustada.predict_distribution(estado, pasos=100)
            np.testing.assert_allclose(dist, pi, atol=1e-6)


# ──────────────────────────────────────────────────────────────────────
# Tests de estado estacionario
# ──────────────────────────────────────────────────────────────────────

class TestEstadoEstacionario:
    def test_forma(self, cadena_ajustada):
        pi = cadena_ajustada.steady_state()
        assert pi.shape == (N_ESTADOS,)

    def test_suma_uno(self, cadena_ajustada):
        pi = cadena_ajustada.steady_state()
        assert pi.sum() == pytest.approx(1.0, abs=1e-10)

    def test_no_negativo(self, cadena_ajustada):
        pi = cadena_ajustada.steady_state()
        assert (pi >= 0).all()

    def test_es_punto_fijo(self, cadena_ajustada):
        """π debe satisfacer π @ P = π (definición de estado estacionario)."""
        pi = cadena_ajustada.steady_state()
        pi_siguiente = pi @ cadena_ajustada.transition_matrix_
        np.testing.assert_allclose(pi_siguiente, pi, atol=1e-8)


# ──────────────────────────────────────────────────────────────────────
# Tests de simulación
# ──────────────────────────────────────────────────────────────────────

class TestSimulacion:
    def test_longitud_correcta(self, cadena_ajustada, rng_fijo):
        for n in [1, 10, 100]:
            traj = cadena_ajustada.simulate(n, estado_inicial=0, rng=rng_fijo)
            assert len(traj) == n

    def test_estados_validos(self, cadena_ajustada, rng_fijo):
        traj = cadena_ajustada.simulate(200, estado_inicial=0, rng=rng_fijo)
        assert set(traj).issubset({0, 1, 2})

    def test_estado_inicial_respetado(self, cadena_ajustada, rng_fijo):
        for estado in EstadoTrafico:
            traj = cadena_ajustada.simulate(50, estado_inicial=estado, rng=rng_fijo)
            assert traj[0] == int(estado)

    def test_sin_estado_inicial_usa_estacionaria(self, cadena_ajustada):
        """Con estado_inicial=None no debe lanzar excepción."""
        traj = cadena_ajustada.simulate(
            1000, estado_inicial=None, rng=np.random.default_rng(0)
        )
        assert len(traj) == 1000

    def test_reproducible_con_misma_semilla(self, cadena_ajustada):
        t1 = cadena_ajustada.simulate(50, estado_inicial=0, rng=np.random.default_rng(7))
        t2 = cadena_ajustada.simulate(50, estado_inicial=0, rng=np.random.default_rng(7))
        np.testing.assert_array_equal(t1, t2)

    def test_frecuencias_convergen_a_estacionaria(self, cadena_ajustada):
        """Con N grande, la frecuencia empírica aproxima π."""
        pi = cadena_ajustada.steady_state()
        traj = cadena_ajustada.simulate(
            100_000, estado_inicial=0, rng=np.random.default_rng(99)
        )
        frecuencias = np.bincount(traj, minlength=N_ESTADOS) / len(traj)
        np.testing.assert_allclose(frecuencias, pi, atol=0.02)


# ──────────────────────────────────────────────────────────────────────
# Tests del método resumen
# ──────────────────────────────────────────────────────────────────────

class TestResumen:
    def test_devuelve_dataframe(self, cadena_ajustada):
        df = cadena_ajustada.resumen()
        assert isinstance(df, pd.DataFrame)

    def test_forma_dataframe(self, cadena_ajustada):
        df = cadena_ajustada.resumen()
        assert df.shape == (N_ESTADOS, N_ESTADOS)

    def test_etiquetas_correctas(self, cadena_ajustada):
        df = cadena_ajustada.resumen()
        assert list(df.index) == ["Fluido", "Lento", "Congestionado"]
        assert list(df.columns) == ["Fluido", "Lento", "Congestionado"]


# ──────────────────────────────────────────────────────────────────────
# Tests de manejo de errores
# ──────────────────────────────────────────────────────────────────────

class TestErrores:
    def test_fit_serie_demasiado_corta(self):
        with pytest.raises(ValueError, match="al menos 2"):
            MarkovTrafficChain().fit(np.array([0]))

    def test_fit_serie_vacia(self):
        with pytest.raises(ValueError, match="al menos 2"):
            MarkovTrafficChain().fit(np.array([]))

    def test_fit_valor_invalido(self):
        with pytest.raises(ValueError, match="fuera de"):
            MarkovTrafficChain().fit(np.array([0, 1, 3]))

    def test_fit_valor_negativo(self):
        with pytest.raises(ValueError, match="fuera de"):
            MarkovTrafficChain().fit(np.array([0, -1, 1]))

    def test_predict_sin_ajuste(self):
        with pytest.raises(RuntimeError, match="fit\\(\\)"):
            MarkovTrafficChain().predict_distribution(0, pasos=1)

    def test_simulate_sin_ajuste(self):
        with pytest.raises(RuntimeError, match="fit\\(\\)"):
            MarkovTrafficChain().simulate(10)

    def test_steady_state_sin_ajuste(self):
        with pytest.raises(RuntimeError, match="fit\\(\\)"):
            MarkovTrafficChain().steady_state()

    def test_predict_estado_invalido(self, cadena_ajustada):
        with pytest.raises(ValueError, match="inválido"):
            cadena_ajustada.predict_distribution(5, pasos=1)

    def test_predict_pasos_negativos(self, cadena_ajustada):
        with pytest.raises(ValueError, match="pasos"):
            cadena_ajustada.predict_distribution(0, pasos=-1)

    def test_simulate_n_pasos_invalido(self, cadena_ajustada):
        with pytest.raises(ValueError, match="n_pasos"):
            cadena_ajustada.simulate(0)

    def test_suavizado_negativo(self):
        with pytest.raises(ValueError, match="suavizado"):
            MarkovTrafficChain(suavizado=-1)


# ──────────────────────────────────────────────────────────────────────
# Tests de EstadoTrafico
# ──────────────────────────────────────────────────────────────────────

class TestEstadoTrafico:
    def test_valores_enteros(self):
        assert int(EstadoTrafico.FLUIDO) == 0
        assert int(EstadoTrafico.LENTO) == 1
        assert int(EstadoTrafico.CONGESTIONADO) == 2

    def test_nombres_estado_completos(self):
        for estado in EstadoTrafico:
            assert estado in NOMBRES_ESTADO
