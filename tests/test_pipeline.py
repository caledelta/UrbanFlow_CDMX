"""
Tests para src/ingestion/pipeline.py — PipelineIntegrador.

Estrategia
----------
- Todos los tests usan MagicMock para los clientes (TomTom y OWM).
  No se realizan llamadas HTTP reales.
- La cadena de Markov se ajusta con datos sintéticos para tests de integración
  con MonteCarloEngine.
- Se organizan en clases por módulo de comportamiento.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, call

from src.ingestion.pipeline import (
    PipelineIntegrador,
    ContextoViaje,
    _inferir_estado_trafico,
    UMBRAL_FLUIDO,
    UMBRAL_LENTO,
)
from src.ingestion.tomtom_client import TomTomTrafficClient, TomTomAPIError
from src.ingestion.weather_client import (
    OpenWeatherMapClient,
    CondicionClimatica,
    FactorClimatico,
    OWMAPIError,
)
from src.simulation.markov_chain import EstadoTrafico, MarkovTrafficChain
from src.simulation.monte_carlo import (
    ConsultaViaje,
    MonteCarloEngine,
    VELOCIDAD_PARAMS,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers compartidos
# ──────────────────────────────────────────────────────────────────────

def _clima_normal() -> CondicionClimatica:
    """Condición climática sin precipitación ni viento fuerte."""
    return CondicionClimatica(
        latitud=19.4326,
        longitud=-99.1332,
        temperatura_c=22.0,
        sensacion_termica_c=21.0,
        humedad_pct=60,
        presion_hpa=1013.0,
        visibilidad_m=10_000,
        viento_velocidad_kmh=5.0,
        viento_direccion_grados=180,
        nubosidad_pct=20,
        lluvia_1h_mm=0.0,
        nieve_1h_mm=0.0,
        codigo_condicion=800,
        descripcion="despejado",
        timestamp_utc="2026-03-15T12:00:00+00:00",
        nombre_estacion="CDMX",
    )


def _clima_lluvia_intensa() -> CondicionClimatica:
    """Condición climática con lluvia intensa (≥50 mm/h → factor ≥ 2.0)."""
    return CondicionClimatica(
        latitud=19.4326,
        longitud=-99.1332,
        temperatura_c=17.0,
        sensacion_termica_c=15.0,
        humedad_pct=95,
        presion_hpa=1008.0,
        visibilidad_m=2_000,
        viento_velocidad_kmh=15.0,
        viento_direccion_grados=90,
        nubosidad_pct=100,
        lluvia_1h_mm=55.0,
        nieve_1h_mm=0.0,
        codigo_condicion=502,
        descripcion="lluvia muy intensa",
        timestamp_utc="2026-03-15T18:00:00+00:00",
        nombre_estacion="CDMX",
    )


def _segmentos_df(ratio: float = 0.85, n: int = 3) -> pd.DataFrame:
    """DataFrame mínimo con columnas de SegmentoVial."""
    return pd.DataFrame({
        "latitud":               [19.43 + i * 0.001 for i in range(n)],
        "longitud":              [-99.13 - i * 0.001 for i in range(n)],
        "velocidad_actual_kmh":  [ratio * 60.0] * n,
        "velocidad_libre_kmh":   [60.0] * n,
        "tiempo_viaje_actual_s": [100] * n,
        "tiempo_viaje_libre_s":  [80] * n,
        "confianza":             [0.9] * n,
        "clase_vial":            ["FRC3"] * n,
        "cierre_vial":           [False] * n,
        "ratio_congestion":      [ratio] * n,
        "timestamp_utc":         ["2026-03-15T12:00:00+00:00"] * n,
    })


def _mock_clientes(
    ratio: float = 0.85,
    clima: CondicionClimatica | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Crea mocks de TomTomTrafficClient y OpenWeatherMapClient."""
    tomtom = MagicMock(spec=TomTomTrafficClient)
    owm    = MagicMock(spec=OpenWeatherMapClient)
    tomtom.obtener_segmentos_lote.return_value = _segmentos_df(ratio)
    owm.obtener_clima_actual.return_value = clima or _clima_normal()
    return tomtom, owm


def _cadena_ajustada() -> MarkovTrafficChain:
    """Cadena de Markov ajustada con datos sintéticos."""
    serie = np.tile([0, 0, 1, 2, 1, 0, 2, 0], 100)
    return MarkovTrafficChain().fit(serie)


COORDENADAS_CORREDOR = [(19.4326, -99.1332), (19.4400, -99.1400), (19.4450, -99.1450)]
LAT_CLIMA, LON_CLIMA = 19.4326, -99.1332


# ──────────────────────────────────────────────────────────────────────
# 1. TestPipelineIntegradorInit
# ──────────────────────────────────────────────────────────────────────

class TestPipelineIntegradorInit:

    def test_init_valido(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        assert pipeline.tomtom is tomtom
        assert pipeline.owm is owm

    def test_init_tomtom_tipo_incorrecto_lanza_typeerror(self):
        _, owm = _mock_clientes()
        with pytest.raises(TypeError, match="TomTomTrafficClient"):
            PipelineIntegrador("no_es_cliente", owm)

    def test_init_owm_tipo_incorrecto_lanza_typeerror(self):
        tomtom, _ = _mock_clientes()
        with pytest.raises(TypeError, match="OpenWeatherMapClient"):
            PipelineIntegrador(tomtom, "no_es_cliente")

    def test_init_ambos_tipos_incorrectos_lanza_typeerror(self):
        with pytest.raises(TypeError):
            PipelineIntegrador(None, None)


# ──────────────────────────────────────────────────────────────────────
# 2. TestInferirEstadoTrafico
# ──────────────────────────────────────────────────────────────────────

class TestInferirEstadoTrafico:

    def test_fluido_ratio_alto(self):
        assert _inferir_estado_trafico(0.95) == int(EstadoTrafico.FLUIDO)

    def test_fluido_en_umbral_exacto(self):
        assert _inferir_estado_trafico(UMBRAL_FLUIDO) == int(EstadoTrafico.FLUIDO)

    def test_lento_justo_bajo_umbral_fluido(self):
        assert _inferir_estado_trafico(0.74) == int(EstadoTrafico.LENTO)

    def test_lento_en_umbral_lento(self):
        assert _inferir_estado_trafico(UMBRAL_LENTO) == int(EstadoTrafico.LENTO)

    def test_congestionado_justo_bajo_umbral_lento(self):
        assert _inferir_estado_trafico(0.44) == int(EstadoTrafico.CONGESTIONADO)

    def test_congestionado_ratio_muy_bajo(self):
        assert _inferir_estado_trafico(0.10) == int(EstadoTrafico.CONGESTIONADO)

    def test_congestionado_ratio_cero(self):
        assert _inferir_estado_trafico(0.0) == int(EstadoTrafico.CONGESTIONADO)

    def test_fluido_ratio_uno(self):
        assert _inferir_estado_trafico(1.0) == int(EstadoTrafico.FLUIDO)

    def test_devuelve_int(self):
        resultado = _inferir_estado_trafico(0.85)
        assert isinstance(resultado, int)


# ──────────────────────────────────────────────────────────────────────
# 3. TestObtenerContexto
# ──────────────────────────────────────────────────────────────────────

class TestObtenerContexto:

    def test_devuelve_contexto_viaje(self):
        tomtom, owm = _mock_clientes(ratio=0.85)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert isinstance(ctx, ContextoViaje)

    def test_estado_fluido_cuando_ratio_alto(self):
        tomtom, owm = _mock_clientes(ratio=0.90)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.estado_inicial == int(EstadoTrafico.FLUIDO)

    def test_estado_lento_cuando_ratio_medio(self):
        tomtom, owm = _mock_clientes(ratio=0.60)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.estado_inicial == int(EstadoTrafico.LENTO)

    def test_estado_congestionado_cuando_ratio_bajo(self):
        tomtom, owm = _mock_clientes(ratio=0.30)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.estado_inicial == int(EstadoTrafico.CONGESTIONADO)

    def test_ratio_congestion_promedio_correcto(self):
        tomtom, owm = _mock_clientes(ratio=0.65)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.ratio_congestion_promedio == pytest.approx(0.65, abs=1e-6)

    def test_n_segmentos_correcto(self):
        tomtom, owm = _mock_clientes(ratio=0.85)
        tomtom.obtener_segmentos_lote.return_value = _segmentos_df(n=5)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.n_segmentos == 5

    def test_segmentos_df_en_contexto(self):
        tomtom, owm = _mock_clientes(ratio=0.85)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert isinstance(ctx.segmentos, pd.DataFrame)
        assert not ctx.segmentos.empty

    def test_clima_en_contexto(self):
        tomtom, owm = _mock_clientes(ratio=0.85)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert isinstance(ctx.clima, CondicionClimatica)

    def test_factor_climatico_en_contexto(self):
        tomtom, owm = _mock_clientes(ratio=0.85)
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert isinstance(ctx.factor_climatico, FactorClimatico)

    def test_factor_climatico_normal_sin_lluvia(self):
        tomtom, owm = _mock_clientes(ratio=0.85, clima=_clima_normal())
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.factor_climatico.factor_multiplicador == pytest.approx(1.0)
        assert ctx.factor_climatico.nivel_alerta == "normal"

    def test_factor_climatico_severo_con_lluvia_intensa(self):
        tomtom, owm = _mock_clientes(ratio=0.85, clima=_clima_lluvia_intensa())
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.factor_climatico.factor_multiplicador >= 2.0

    def test_velocidad_params_ajustados_por_clima_lluvia(self):
        tomtom, owm = _mock_clientes(ratio=0.85, clima=_clima_lluvia_intensa())
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        # Con lluvia intensa, las velocidades deben ser menores que las nominales
        assert ctx.velocidad_params[0]["media"] < VELOCIDAD_PARAMS[0]["media"]
        assert ctx.velocidad_params[1]["media"] < VELOCIDAD_PARAMS[1]["media"]
        assert ctx.velocidad_params[2]["media"] < VELOCIDAD_PARAMS[2]["media"]

    def test_velocidad_params_sin_cambio_clima_normal(self):
        tomtom, owm = _mock_clientes(ratio=0.85, clima=_clima_normal())
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        # Factor 1.0 → velocidades sin cambio
        assert ctx.velocidad_params[0]["media"] == pytest.approx(VELOCIDAD_PARAMS[0]["media"])

    def test_corredor_vacio_lanza_valueerror(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        with pytest.raises(ValueError, match="coordenadas_corredor"):
            pipeline.obtener_contexto([], LAT_CLIMA, LON_CLIMA)

    def test_todos_segmentos_fallidos_lanza_tomtom_error(self):
        tomtom, owm = _mock_clientes()
        tomtom.obtener_segmentos_lote.return_value = pd.DataFrame()
        pipeline = PipelineIntegrador(tomtom, owm)
        with pytest.raises(TomTomAPIError):
            pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)

    def test_error_owm_se_propaga(self):
        tomtom, owm = _mock_clientes()
        owm.obtener_clima_actual.side_effect = OWMAPIError("fallo OWM")
        pipeline = PipelineIntegrador(tomtom, owm)
        with pytest.raises(OWMAPIError):
            pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)

    def test_tomtom_llamado_con_coordenadas_corredor(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        tomtom.obtener_segmentos_lote.assert_called_once_with(COORDENADAS_CORREDOR)

    def test_owm_llamado_con_lat_lon_clima(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        owm.obtener_clima_actual.assert_called_once_with(LAT_CLIMA, LON_CLIMA)

    def test_timestamp_utc_presente(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        assert ctx.timestamp_utc
        assert "T" in ctx.timestamp_utc  # formato ISO 8601


# ──────────────────────────────────────────────────────────────────────
# 4. TestContextoViaje
# ──────────────────────────────────────────────────────────────────────

class TestContextoViaje:

    def _contexto(self, ratio: float = 0.85) -> ContextoViaje:
        tomtom, owm = _mock_clientes(ratio=ratio)
        pipeline = PipelineIntegrador(tomtom, owm)
        return pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)

    def test_a_consulta_devuelve_consulta_viaje(self):
        ctx = self._contexto()
        consulta = ctx.a_consulta(distancia_km=10.0)
        assert isinstance(consulta, ConsultaViaje)

    def test_a_consulta_distancia_correcta(self):
        ctx = self._contexto()
        consulta = ctx.a_consulta(distancia_km=15.5)
        assert consulta.distancia_km == 15.5

    def test_a_consulta_estado_inicial_correcto(self):
        ctx = self._contexto(ratio=0.85)
        consulta = ctx.a_consulta(distancia_km=5.0)
        assert consulta.estado_inicial == ctx.estado_inicial

    def test_a_consulta_distancia_invalida_lanza_valueerror(self):
        ctx = self._contexto()
        with pytest.raises(ValueError):
            ctx.a_consulta(distancia_km=-1.0)

    def test_crear_motor_devuelve_montecarlo_engine(self):
        ctx = self._contexto()
        cadena = _cadena_ajustada()
        motor = ctx.crear_motor(cadena, n_simulaciones=100)
        assert isinstance(motor, MonteCarloEngine)

    def test_crear_motor_usa_velocidad_params_ajustados(self):
        tomtom, owm = _mock_clientes(ratio=0.85, clima=_clima_lluvia_intensa())
        pipeline = PipelineIntegrador(tomtom, owm)
        ctx = pipeline.obtener_contexto(COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA)
        cadena = _cadena_ajustada()
        motor = ctx.crear_motor(cadena, n_simulaciones=100)
        # Los params del motor deben coincidir con los del contexto (ajustados)
        assert motor._velocidad_params[0]["media"] == pytest.approx(
            ctx.velocidad_params[0]["media"]
        )

    def test_crear_motor_n_simulaciones_respetado(self):
        ctx = self._contexto()
        cadena = _cadena_ajustada()
        motor = ctx.crear_motor(cadena, n_simulaciones=500)
        assert motor.n_simulaciones == 500

    def test_a_dict_contiene_campos_esperados(self):
        ctx = self._contexto()
        d = ctx.a_dict()
        assert "estado_inicial" in d
        assert "nombre_estado" in d
        assert "ratio_congestion_promedio" in d
        assert "n_segmentos" in d
        assert "factor_climatico" in d
        assert "nivel_alerta_clima" in d
        assert "timestamp_utc" in d

    def test_a_dict_nombre_estado_fluido(self):
        ctx = self._contexto(ratio=0.90)
        assert ctx.a_dict()["nombre_estado"] == "FLUIDO"

    def test_a_dict_nombre_estado_lento(self):
        ctx = self._contexto(ratio=0.60)
        assert ctx.a_dict()["nombre_estado"] == "LENTO"

    def test_a_dict_nombre_estado_congestionado(self):
        ctx = self._contexto(ratio=0.30)
        assert ctx.a_dict()["nombre_estado"] == "CONGESTIONADO"


# ──────────────────────────────────────────────────────────────────────
# 5. TestPredecirTiempoViaje
# ──────────────────────────────────────────────────────────────────────

class TestPredecirTiempoViaje:

    def test_devuelve_tupla_contexto_resultado(self):
        tomtom, owm = _mock_clientes(ratio=0.85)
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena = _cadena_ajustada()
        resultado = pipeline.predecir_tiempo_viaje(
            COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA,
            distancia_km=10.0,
            cadena=cadena,
            n_simulaciones=100,
            rng=np.random.default_rng(42),
        )
        assert isinstance(resultado, tuple)
        assert len(resultado) == 2

    def test_contexto_en_resultado(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena = _cadena_ajustada()
        ctx, _ = pipeline.predecir_tiempo_viaje(
            COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA,
            distancia_km=10.0, cadena=cadena,
            n_simulaciones=50, rng=np.random.default_rng(0),
        )
        assert isinstance(ctx, ContextoViaje)

    def test_resultado_simulacion_tiene_p50(self):
        from src.simulation.monte_carlo import ResultadoSimulacion
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena = _cadena_ajustada()
        _, res = pipeline.predecir_tiempo_viaje(
            COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA,
            distancia_km=10.0, cadena=cadena,
            n_simulaciones=50, rng=np.random.default_rng(1),
        )
        assert isinstance(res, ResultadoSimulacion)
        assert res.p50 > 0

    def test_distancia_km_propagada_al_resultado(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena = _cadena_ajustada()
        _, res = pipeline.predecir_tiempo_viaje(
            COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA,
            distancia_km=7.3, cadena=cadena,
            n_simulaciones=50, rng=np.random.default_rng(2),
        )
        assert res.distancia_km == pytest.approx(7.3)

    def test_corredor_vacio_lanza_valueerror(self):
        tomtom, owm = _mock_clientes()
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena = _cadena_ajustada()
        with pytest.raises(ValueError):
            pipeline.predecir_tiempo_viaje(
                [], LAT_CLIMA, LON_CLIMA,
                distancia_km=10.0, cadena=cadena,
            )

    def test_p10_menor_o_igual_p50_menor_o_igual_p90(self):
        tomtom, owm = _mock_clientes(ratio=0.60)
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena = _cadena_ajustada()
        _, res = pipeline.predecir_tiempo_viaje(
            COORDENADAS_CORREDOR, LAT_CLIMA, LON_CLIMA,
            distancia_km=5.0, cadena=cadena,
            n_simulaciones=200, rng=np.random.default_rng(7),
        )
        assert res.p10 <= res.p50 <= res.p90


# ──────────────────────────────────────────────────────────────────────
# 6. TestMonteCarloEngineVelocidadParamsInyectados
# ──────────────────────────────────────────────────────────────────────

class TestMonteCarloEngineVelocidadParamsInyectados:
    """
    Verifica que MonteCarloEngine respeta los velocidad_params inyectados
    (funcionalidad añadida para soportar el ajuste climático del pipeline).
    """

    def _cadena(self) -> MarkovTrafficChain:
        return _cadena_ajustada()

    def test_motor_sin_params_usa_defaults(self):
        cadena = self._cadena()
        motor = MonteCarloEngine(cadena, n_simulaciones=100, rng=np.random.default_rng(0))
        assert motor._velocidad_params is VELOCIDAD_PARAMS

    def test_motor_con_params_inyectados_usa_custom(self):
        cadena = self._cadena()
        params_custom = {
            0: {"media": 30.0, "std": 5.0, "min": 15.0, "max": 60.0},
            1: {"media": 12.0, "std": 3.0, "min":  3.0, "max": 25.0},
            2: {"media":  4.0, "std": 2.0, "min":  1.0, "max": 10.0},
        }
        motor = MonteCarloEngine(
            cadena, n_simulaciones=100,
            velocidad_params=params_custom,
            rng=np.random.default_rng(0),
        )
        assert motor._velocidad_params is params_custom

    def test_simulacion_con_params_reducidos_produce_tiempos_mayores(self):
        """Con velocidades reducidas (clima adverso), el tiempo P50 debe ser mayor."""
        cadena = self._cadena()
        rng_a  = np.random.default_rng(42)
        rng_b  = np.random.default_rng(42)

        motor_normal = MonteCarloEngine(
            cadena, n_simulaciones=500,
            velocidad_params=VELOCIDAD_PARAMS,
            rng=rng_a,
        )
        # Simular clima severo: velocidades a la mitad
        params_reducidos = {
            k: {**v, "media": v["media"] / 2.0, "min": max(v["min"] / 2.0, 1.0)}
            for k, v in VELOCIDAD_PARAMS.items()
        }
        motor_severo = MonteCarloEngine(
            cadena, n_simulaciones=500,
            velocidad_params=params_reducidos,
            rng=rng_b,
        )

        from src.simulation.monte_carlo import ConsultaViaje
        consulta = ConsultaViaje(distancia_km=10.0, estado_inicial=0)

        res_normal = motor_normal.correr(consulta)
        res_severo = motor_severo.correr(consulta)

        # P50 con velocidades reducidas debe ser mayor
        assert res_severo.p50 > res_normal.p50
