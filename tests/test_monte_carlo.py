"""
Tests para src/simulation/monte_carlo.py

Cubre: ConsultaViaje, ResultadoSimulacion, MonteCarloEngine
(construcción, simulación, propiedades estadísticas, errores).
"""

import numpy as np
import pytest

from src.simulation.markov_chain import EstadoTrafico, MarkovTrafficChain
from src.simulation.monte_carlo import (
    ConsultaViaje,
    MonteCarloEngine,
    ResultadoSimulacion,
    VELOCIDAD_PARAMS,
)

# ──────────────────────────────────────────────────────────────────────
# Fixtures compartidos
# ──────────────────────────────────────────────────────────────────────

SERIE_HISTORICA = np.tile([0, 0, 1, 1, 2, 1, 0], 300)   # ~2100 observaciones


@pytest.fixture(scope="module")
def cadena_ajustada() -> MarkovTrafficChain:
    """Cadena ajustada sobre serie representativa; reutilizada en todo el módulo."""
    return MarkovTrafficChain().fit(SERIE_HISTORICA)


@pytest.fixture(scope="module")
def motor(cadena_ajustada) -> MonteCarloEngine:
    """Motor con N=5 000 y semilla fija para rapidez y reproducibilidad."""
    return MonteCarloEngine(
        cadena_ajustada,
        n_simulaciones=5_000,
        rng=np.random.default_rng(42),
    )


@pytest.fixture(scope="module")
def resultado_base(motor) -> ResultadoSimulacion:
    """Resultado para 15 km desde estado Fluido."""
    return motor.correr(ConsultaViaje(distancia_km=15.0, estado_inicial=0))


# ──────────────────────────────────────────────────────────────────────
# Tests de ConsultaViaje
# ──────────────────────────────────────────────────────────────────────

class TestConsultaViaje:
    def test_crea_correctamente(self):
        c = ConsultaViaje(distancia_km=10.0, estado_inicial=1)
        assert c.distancia_km == 10.0
        assert c.estado_inicial == 1

    def test_acepta_enum_estado(self):
        c = ConsultaViaje(distancia_km=5.0, estado_inicial=EstadoTrafico.CONGESTIONADO)
        assert c.estado_inicial == 2

    def test_estado_se_convierte_a_int(self):
        c = ConsultaViaje(distancia_km=5.0, estado_inicial=EstadoTrafico.LENTO)
        assert isinstance(c.estado_inicial, int)

    def test_distancia_cero_lanza_error(self):
        with pytest.raises(ValueError, match="distancia_km"):
            ConsultaViaje(distancia_km=0.0, estado_inicial=0)

    def test_distancia_negativa_lanza_error(self):
        with pytest.raises(ValueError, match="distancia_km"):
            ConsultaViaje(distancia_km=-5.0, estado_inicial=0)

    def test_estado_invalido_lanza_error(self):
        with pytest.raises(ValueError, match="estado_inicial"):
            ConsultaViaje(distancia_km=10.0, estado_inicial=5)

    def test_estado_negativo_lanza_error(self):
        with pytest.raises(ValueError, match="estado_inicial"):
            ConsultaViaje(distancia_km=10.0, estado_inicial=-1)


# ──────────────────────────────────────────────────────────────────────
# Tests de ResultadoSimulacion
# ──────────────────────────────────────────────────────────────────────

class TestResultadoSimulacion:
    def test_orden_percentiles(self, resultado_base):
        assert resultado_base.p10 <= resultado_base.p50 <= resultado_base.p90

    def test_tiempos_positivos(self, resultado_base):
        assert (resultado_base.tiempos_minutos > 0).all()

    def test_tiempos_finitos(self, resultado_base):
        assert np.isfinite(resultado_base.tiempos_minutos).all()

    def test_longitud_tiempos(self, resultado_base, motor):
        assert len(resultado_base.tiempos_minutos) == motor.n_simulaciones

    def test_banda_incertidumbre(self, resultado_base):
        esperada = resultado_base.p90 - resultado_base.p10
        assert resultado_base.banda_incertidumbre == pytest.approx(esperada)

    def test_banda_incertidumbre_no_negativa(self, resultado_base):
        assert resultado_base.banda_incertidumbre >= 0

    def test_media_entre_p10_y_p90(self, resultado_base):
        assert resultado_base.p10 <= resultado_base.media <= resultado_base.p90

    def test_std_no_negativa(self, resultado_base):
        assert resultado_base.std >= 0

    def test_n_recortadas_no_negativo(self, resultado_base):
        assert resultado_base.n_recortadas >= 0

    def test_fraccion_recortadas_rango(self, resultado_base):
        assert 0.0 <= resultado_base.fraccion_recortadas <= 1.0

    def test_percentil_50_igual_p50(self, resultado_base):
        assert resultado_base.percentil(50) == pytest.approx(resultado_base.p50)

    def test_percentil_10_igual_p10(self, resultado_base):
        assert resultado_base.percentil(10) == pytest.approx(resultado_base.p10)

    def test_percentil_90_igual_p90(self, resultado_base):
        assert resultado_base.percentil(90) == pytest.approx(resultado_base.p90)

    def test_percentil_fuera_de_rango(self, resultado_base):
        with pytest.raises(ValueError, match="q"):
            resultado_base.percentil(101)

    def test_percentil_negativo(self, resultado_base):
        with pytest.raises(ValueError, match="q"):
            resultado_base.percentil(-1)

    def test_a_dict_tiene_claves_requeridas(self, resultado_base):
        d = resultado_base.a_dict()
        claves_requeridas = {
            "distancia_km", "estado_inicial",
            "p10_minutos", "p50_minutos", "p90_minutos",
            "media_minutos", "std_minutos",
            "banda_incertidumbre", "n_simulaciones", "n_recortadas",
        }
        assert claves_requeridas.issubset(d.keys())

    def test_a_dict_estado_inicial_es_string(self, resultado_base):
        d = resultado_base.a_dict()
        assert isinstance(d["estado_inicial"], str)

    def test_repr_contiene_distancia(self, resultado_base):
        assert "15.0" in repr(resultado_base)

    def test_repr_contiene_percentiles(self, resultado_base):
        r = repr(resultado_base)
        assert "P10" in r and "P50" in r and "P90" in r


# ──────────────────────────────────────────────────────────────────────
# Tests de construcción del motor
# ──────────────────────────────────────────────────────────────────────

class TestConstruccionMotor:
    def test_cadena_no_ajustada_lanza_error(self):
        cadena_vacia = MarkovTrafficChain()
        with pytest.raises(RuntimeError, match="fit\\(\\)"):
            MonteCarloEngine(cadena_vacia)

    def test_n_simulaciones_invalido(self, cadena_ajustada):
        with pytest.raises(ValueError, match="n_simulaciones"):
            MonteCarloEngine(cadena_ajustada, n_simulaciones=0)

    def test_paso_minutos_invalido(self, cadena_ajustada):
        with pytest.raises(ValueError, match="paso_minutos"):
            MonteCarloEngine(cadena_ajustada, paso_minutos=0.0)

    def test_paso_minutos_negativo(self, cadena_ajustada):
        with pytest.raises(ValueError, match="paso_minutos"):
            MonteCarloEngine(cadena_ajustada, paso_minutos=-1.0)

    def test_max_pasos_invalido(self, cadena_ajustada):
        with pytest.raises(ValueError, match="max_pasos"):
            MonteCarloEngine(cadena_ajustada, max_pasos=0)

    def test_rng_none_crea_generador(self, cadena_ajustada):
        motor = MonteCarloEngine(cadena_ajustada, rng=None)
        assert motor._rng is not None

    def test_p_cumsum_precomputada_correctamente(self, cadena_ajustada):
        motor = MonteCarloEngine(cadena_ajustada)
        # Cada fila debe terminar en 1.0
        np.testing.assert_allclose(motor._P_cumsum[:, -1], np.ones(3), atol=1e-10)


# ──────────────────────────────────────────────────────────────────────
# Tests del método correr()
# ──────────────────────────────────────────────────────────────────────

class TestCorrer:
    def test_devuelve_resultado_simulacion(self, motor):
        r = motor.correr(ConsultaViaje(10.0, 0))
        assert isinstance(r, ResultadoSimulacion)

    def test_distancia_se_preserva_en_resultado(self, motor):
        consulta = ConsultaViaje(distancia_km=7.5, estado_inicial=1)
        r = motor.correr(consulta)
        assert r.distancia_km == 7.5

    def test_estado_inicial_se_preserva(self, motor):
        consulta = ConsultaViaje(distancia_km=10.0, estado_inicial=2)
        r = motor.correr(consulta)
        assert r.estado_inicial == 2

    def test_todos_los_estados_iniciales(self, cadena_ajustada):
        motor_local = MonteCarloEngine(
            cadena_ajustada, n_simulaciones=1_000, rng=np.random.default_rng(0)
        )
        for estado in EstadoTrafico:
            r = motor_local.correr(ConsultaViaje(10.0, estado))
            assert r.p10 <= r.p50 <= r.p90

    def test_reproducibilidad_misma_semilla(self, cadena_ajustada):
        def _correr(semilla):
            m = MonteCarloEngine(
                cadena_ajustada, n_simulaciones=500,
                rng=np.random.default_rng(semilla)
            )
            return m.correr(ConsultaViaje(10.0, 0))

        r1 = _correr(99)
        r2 = _correr(99)
        np.testing.assert_array_equal(r1.tiempos_minutos, r2.tiempos_minutos)

    def test_semillas_distintas_dan_resultados_distintos(self, cadena_ajustada):
        def _correr(semilla):
            m = MonteCarloEngine(
                cadena_ajustada, n_simulaciones=500,
                rng=np.random.default_rng(semilla)
            )
            return m.correr(ConsultaViaje(10.0, 0)).p50

        assert _correr(1) != _correr(2)


# ──────────────────────────────────────────────────────────────────────
# Tests de propiedades estadísticas
# ──────────────────────────────────────────────────────────────────────

class TestPropiedadesEstadisticas:
    """
    Tests que verifican comportamiento estadístico esperado.
    Usan N grande y tolerancias generosas para evitar falsos positivos.
    """

    @pytest.fixture(scope="class")
    def motor_grande(self, cadena_ajustada):
        return MonteCarloEngine(
            cadena_ajustada,
            n_simulaciones=10_000,
            rng=np.random.default_rng(0),
        )

    def test_congestionado_mas_lento_que_fluido(self, motor_grande):
        """P50 en tráfico congestionado debe ser mayor que en tráfico fluido."""
        r_fluido = motor_grande.correr(ConsultaViaje(15.0, EstadoTrafico.FLUIDO))
        r_cong   = motor_grande.correr(ConsultaViaje(15.0, EstadoTrafico.CONGESTIONADO))
        assert r_cong.p50 > r_fluido.p50

    def test_distancia_mayor_tiempo_mayor(self, motor_grande):
        """Duplicar la distancia debe aumentar el tiempo P50."""
        r_corto = motor_grande.correr(ConsultaViaje(10.0, 0))
        r_largo = motor_grande.correr(ConsultaViaje(20.0, 0))
        assert r_largo.p50 > r_corto.p50

    def test_banda_congestionado_mayor_que_fluido(self, motor_grande):
        """El tráfico congestionado tiene mayor variabilidad (banda más ancha)."""
        r_fluido = motor_grande.correr(ConsultaViaje(15.0, EstadoTrafico.FLUIDO))
        r_cong   = motor_grande.correr(ConsultaViaje(15.0, EstadoTrafico.CONGESTIONADO))
        assert r_cong.banda_incertidumbre > r_fluido.banda_incertidumbre

    def test_velocidad_media_fluido_razonable(self, motor_grande):
        """
        A 40 km/h de velocidad media, 10 km deberían tomarse ~15 min.
        Verificamos que el P50 está en un rango plausible [10, 40] min.
        """
        r = motor_grande.correr(ConsultaViaje(10.0, EstadoTrafico.FLUIDO))
        assert 10.0 < r.p50 < 40.0

    def test_velocidad_media_congestionado_razonable(self, motor_grande):
        """
        La cadena mezcla estados tras el arranque, por lo que el P50 refleja
        la velocidad media ponderada del estado estacionario (~18-25 km/h).
        Para 10 km verificamos un rango plausible [15, 120] min que cubre
        tanto escenarios de mezcla rápida como persistencia en congestión.
        """
        r = motor_grande.correr(ConsultaViaje(10.0, EstadoTrafico.CONGESTIONADO))
        assert 15.0 < r.p50 < 120.0

    def test_std_positiva_con_variabilidad(self, motor_grande):
        """Con velocidades estocásticas, la std debe ser estrictamente positiva."""
        r = motor_grande.correr(ConsultaViaje(15.0, 1))
        assert r.std > 0

    def test_p10_mayor_que_cero(self, motor_grande):
        r = motor_grande.correr(ConsultaViaje(5.0, 0))
        assert r.p10 > 0


# ──────────────────────────────────────────────────────────────────────
# Tests de componentes internos
# ──────────────────────────────────────────────────────────────────────

class TestComponentesInternos:
    @pytest.fixture(scope="class")
    def motor_pequeno(self, cadena_ajustada):
        return MonteCarloEngine(
            cadena_ajustada,
            n_simulaciones=200,
            max_pasos=60,
            rng=np.random.default_rng(7),
        )

    def test_simular_estados_forma(self, motor_pequeno):
        estados = motor_pequeno._simular_estados(estado_inicial=0)
        assert estados.shape == (200, 60)

    def test_simular_estados_valores_validos(self, motor_pequeno):
        estados = motor_pequeno._simular_estados(estado_inicial=1)
        assert set(np.unique(estados)).issubset({0, 1, 2})

    def test_simular_estados_primer_columna(self, motor_pequeno):
        estados = motor_pequeno._simular_estados(estado_inicial=2)
        assert (estados[:, 0] == 2).all()

    def test_muestrear_velocidades_forma(self, motor_pequeno):
        estados = motor_pequeno._simular_estados(0)
        velocidades = motor_pequeno._muestrear_velocidades(estados)
        assert velocidades.shape == estados.shape

    def test_velocidades_dentro_de_limites(self, motor_pequeno):
        estados = motor_pequeno._simular_estados(0)
        velocidades = motor_pequeno._muestrear_velocidades(estados)
        min_global = min(p["min"] for p in VELOCIDAD_PARAMS.values())
        max_global = max(p["max"] for p in VELOCIDAD_PARAMS.values())
        assert (velocidades >= min_global).all()
        assert (velocidades <= max_global).all()

    def test_velocidades_positivas(self, motor_pequeno):
        estados = motor_pequeno._simular_estados(0)
        velocidades = motor_pequeno._muestrear_velocidades(estados)
        assert (velocidades > 0).all()


# ──────────────────────────────────────────────────────────────────────
# Tests de trayectorias recortadas
# ──────────────────────────────────────────────────────────────────────

class TestTrayectoriasRecortadas:
    def test_recortadas_con_max_pasos_muy_bajo(self, cadena_ajustada):
        """Con max_pasos=1 y distancia grande, todas deben recortarse."""
        motor_lim = MonteCarloEngine(
            cadena_ajustada,
            n_simulaciones=100,
            max_pasos=1,
            rng=np.random.default_rng(0),
        )
        r = motor_lim.correr(ConsultaViaje(distancia_km=500.0, estado_inicial=0))
        assert r.n_recortadas == 100

    def test_recortadas_con_distancia_corta_son_pocas(self, cadena_ajustada):
        """Con distancia muy corta y max_pasos generoso, no debería haber recortes."""
        motor_ok = MonteCarloEngine(
            cadena_ajustada,
            n_simulaciones=500,
            max_pasos=480,
            rng=np.random.default_rng(0),
        )
        r = motor_ok.correr(ConsultaViaje(distancia_km=1.0, estado_inicial=0))
        assert r.n_recortadas == 0

    def test_tiempos_recortados_son_tiempo_maximo(self, cadena_ajustada):
        """
        Con max_pasos=2 y distancia imposible, todos los tiempos deben ser
        exactamente max_pasos * paso_minutos.
        """
        max_p, paso = 2, 1.0
        motor_lim = MonteCarloEngine(
            cadena_ajustada,
            n_simulaciones=50,
            max_pasos=max_p,
            paso_minutos=paso,
            rng=np.random.default_rng(0),
        )
        r = motor_lim.correr(ConsultaViaje(distancia_km=9999.0, estado_inicial=0))
        tiempo_max = max_p * paso
        assert (r.tiempos_minutos == tiempo_max).all()
