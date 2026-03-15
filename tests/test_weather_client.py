"""
Tests para src/ingestion/weather_client.py

Cubre: CondicionClimatica, FactorClimatico, OpenWeatherMapClient (actual e
histórico), calcular_factor_congestion, ajustar_velocidades_por_clima.
Todos los tests usan mocks — nunca hacen llamadas reales a la API.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest
import requests

from src.ingestion.weather_client import (
    CondicionClimatica,
    FactorClimatico,
    OpenWeatherMapClient,
    OWMAPIError,
    OWMAuthError,
    OWMRateLimitError,
    OWMNotFoundError,
    ESTACIONES_ZMVM,
    calcular_factor_congestion,
    ajustar_velocidades_por_clima,
    _parsear_respuesta_actual,
    _parsear_respuesta_historico,
    _validar_coordenadas,
)

# ──────────────────────────────────────────────────────────────────────
# Payloads de referencia
# ──────────────────────────────────────────────────────────────────────

PAYLOAD_ACTUAL_OK = {
    "weather": [{"id": 500, "main": "Rain", "description": "lluvia ligera"}],
    "main": {
        "temp": 17.5, "feels_like": 16.0,
        "humidity": 88, "pressure": 1012.0,
    },
    "visibility": 6000,
    "wind":   {"speed": 4.2, "deg": 180},
    "clouds": {"all": 80},
    "rain":   {"1h": 3.5},
    "dt":     1710500000,
    "name":   "Mexico City",
}

PAYLOAD_HISTORICO_OK = {
    "lat": 19.4326, "lon": -99.1332,
    "timezone": "America/Mexico_City",
    "data": [{
        "dt":         1710500000,
        "temp":       15.0,
        "feels_like": 14.0,
        "humidity":   90,
        "pressure":   1010.0,
        "visibility": 4000,
        "wind_speed": 3.0,
        "wind_deg":   200,
        "clouds":     90,
        "rain":       {"1h": 8.0},
        "weather":    [{"id": 501, "main": "Rain", "description": "lluvia moderada"}],
    }],
}

PAYLOAD_DESPEJADO = {
    "weather": [{"id": 800, "main": "Clear", "description": "cielo despejado"}],
    "main":    {"temp": 22.0, "feels_like": 21.0, "humidity": 40, "pressure": 1015.0},
    "visibility": 10000,
    "wind":   {"speed": 2.0, "deg": 90},
    "clouds": {"all": 0},
    "dt":     1710500000,
    "name":   "Mexico City",
}

LAT = 19.4326
LON = -99.1332


def _mock_session(status_code: int = 200, payload: dict | None = None) -> MagicMock:
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = payload if payload is not None else PAYLOAD_ACTUAL_OK
    mock_resp.text = json.dumps(mock_resp.json.return_value)
    session = MagicMock(spec=requests.Session)
    session.get.return_value = mock_resp
    return session


@pytest.fixture
def cliente_ok() -> OpenWeatherMapClient:
    return OpenWeatherMapClient(api_key="test-key", session=_mock_session())


@pytest.fixture
def condicion_lluvia() -> CondicionClimatica:
    """Condición con lluvia moderada para tests de factor."""
    return CondicionClimatica(
        latitud=LAT, longitud=LON,
        temperatura_c=17.5, sensacion_termica_c=16.0,
        humedad_pct=88, presion_hpa=1012.0,
        visibilidad_m=6000, viento_velocidad_kmh=15.1,
        viento_direccion_grados=180, nubosidad_pct=80,
        lluvia_1h_mm=3.5, nieve_1h_mm=0.0,
        codigo_condicion=500, descripcion="lluvia ligera",
        timestamp_utc="2026-03-15T12:00:00+00:00",
    )


@pytest.fixture
def condicion_despejada() -> CondicionClimatica:
    return CondicionClimatica(
        latitud=LAT, longitud=LON,
        temperatura_c=22.0, sensacion_termica_c=21.0,
        humedad_pct=40, presion_hpa=1015.0,
        visibilidad_m=10000, viento_velocidad_kmh=7.2,
        viento_direccion_grados=90, nubosidad_pct=0,
        lluvia_1h_mm=0.0, nieve_1h_mm=0.0,
        codigo_condicion=800, descripcion="cielo despejado",
        timestamp_utc="2026-03-15T12:00:00+00:00",
    )


# ──────────────────────────────────────────────────────────────────────
# Tests de construcción del cliente
# ──────────────────────────────────────────────────────────────────────

class TestConstruccion:
    def test_crea_correctamente(self):
        c = OpenWeatherMapClient(api_key="abc123")
        assert c.timeout == 10

    def test_api_key_vacia_lanza_error(self):
        with pytest.raises(ValueError, match="api_key"):
            OpenWeatherMapClient(api_key="")

    def test_api_key_espacios_lanza_error(self):
        with pytest.raises(ValueError, match="api_key"):
            OpenWeatherMapClient(api_key="   ")

    def test_timeout_invalido(self):
        with pytest.raises(ValueError, match="timeout"):
            OpenWeatherMapClient(api_key="k", timeout=0)

    def test_reintentos_negativos(self):
        with pytest.raises(ValueError, match="max_reintentos"):
            OpenWeatherMapClient(api_key="k", max_reintentos=-1)

    def test_session_inyectada(self):
        s = _mock_session()
        c = OpenWeatherMapClient(api_key="k", session=s)
        assert c._session is s

    def test_session_none_crea_nueva(self):
        c = OpenWeatherMapClient(api_key="k", session=None)
        assert isinstance(c._session, requests.Session)


# ──────────────────────────────────────────────────────────────────────
# Tests de obtener_clima_actual
# ──────────────────────────────────────────────────────────────────────

class TestObtenerClimaActual:
    def test_devuelve_condicion_climatica(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert isinstance(c, CondicionClimatica)

    def test_temperatura(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.temperatura_c == 17.5

    def test_humedad(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.humedad_pct == 88

    def test_visibilidad(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.visibilidad_m == 6000

    def test_viento_convertido_a_kmh(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        # 4.2 m/s × 3.6 = 15.12 km/h
        assert c.viento_velocidad_kmh == pytest.approx(4.2 * 3.6, abs=0.01)

    def test_lluvia_1h(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.lluvia_1h_mm == 3.5

    def test_codigo_condicion(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.codigo_condicion == 500

    def test_descripcion(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.descripcion == "lluvia ligera"

    def test_coordenadas_preservadas(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.latitud == LAT
        assert c.longitud == LON

    def test_timestamp_es_string(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert isinstance(c.timestamp_utc, str)

    def test_nombre_estacion(self, cliente_ok):
        c = cliente_ok.obtener_clima_actual(LAT, LON)
        assert c.nombre_estacion == "Mexico City"

    def test_sin_lluvia_campo_es_cero(self):
        s = _mock_session(200, PAYLOAD_DESPEJADO)
        c = OpenWeatherMapClient(api_key="k", session=s)
        condicion = c.obtener_clima_actual(LAT, LON)
        assert condicion.lluvia_1h_mm == 0.0

    def test_params_contienen_appid(self, cliente_ok):
        cliente_ok.obtener_clima_actual(LAT, LON)
        kwargs = cliente_ok._session.get.call_args[1]
        assert "appid" in kwargs["params"]

    def test_params_unidades_metric(self, cliente_ok):
        cliente_ok.obtener_clima_actual(LAT, LON)
        kwargs = cliente_ok._session.get.call_args[1]
        assert kwargs["params"]["units"] == "metric"

    def test_latitud_invalida_lanza_error(self, cliente_ok):
        with pytest.raises(ValueError, match="Latitud"):
            cliente_ok.obtener_clima_actual(lat=100.0, lon=LON)

    def test_longitud_invalida_lanza_error(self, cliente_ok):
        with pytest.raises(ValueError, match="Longitud"):
            cliente_ok.obtener_clima_actual(lat=LAT, lon=200.0)

    def test_respuesta_sin_main_lanza_error(self):
        s = _mock_session(200, {"weather": []})
        c = OpenWeatherMapClient(api_key="k", session=s)
        with pytest.raises(OWMAPIError, match="main"):
            c.obtener_clima_actual(LAT, LON)


# ──────────────────────────────────────────────────────────────────────
# Tests de obtener_clima_historico
# ──────────────────────────────────────────────────────────────────────

class TestObtenerClimaHistorico:
    @pytest.fixture
    def cliente_historico(self):
        return OpenWeatherMapClient(
            api_key="k", session=_mock_session(200, PAYLOAD_HISTORICO_OK)
        )

    def test_devuelve_condicion_climatica(self, cliente_historico):
        c = cliente_historico.obtener_clima_historico(LAT, LON, 1710500000)
        assert isinstance(c, CondicionClimatica)

    def test_temperatura_historica(self, cliente_historico):
        c = cliente_historico.obtener_clima_historico(LAT, LON, 1710500000)
        assert c.temperatura_c == 15.0

    def test_lluvia_historica(self, cliente_historico):
        c = cliente_historico.obtener_clima_historico(LAT, LON, 1710500000)
        assert c.lluvia_1h_mm == 8.0

    def test_viento_convertido(self, cliente_historico):
        c = cliente_historico.obtener_clima_historico(LAT, LON, 1710500000)
        assert c.viento_velocidad_kmh == pytest.approx(3.0 * 3.6, abs=0.01)

    def test_timestamp_invalido_lanza_error(self, cliente_historico):
        with pytest.raises(ValueError, match="timestamp"):
            cliente_historico.obtener_clima_historico(LAT, LON, 0)

    def test_timestamp_negativo_lanza_error(self, cliente_historico):
        with pytest.raises(ValueError, match="timestamp"):
            cliente_historico.obtener_clima_historico(LAT, LON, -1)

    def test_respuesta_sin_data_lanza_error(self):
        s = _mock_session(200, {"lat": LAT, "lon": LON})
        c = OpenWeatherMapClient(api_key="k", session=s)
        with pytest.raises(OWMAPIError, match="data"):
            c.obtener_clima_historico(LAT, LON, 1710500000)

    def test_data_vacia_lanza_error(self):
        s = _mock_session(200, {"data": []})
        c = OpenWeatherMapClient(api_key="k", session=s)
        with pytest.raises(OWMAPIError):
            c.obtener_clima_historico(LAT, LON, 1710500000)


# ──────────────────────────────────────────────────────────────────────
# Tests de errores HTTP
# ──────────────────────────────────────────────────────────────────────

class TestErroresHTTP:
    def test_401_lanza_auth_error(self):
        c = OpenWeatherMapClient(api_key="k", session=_mock_session(401, {}))
        with pytest.raises(OWMAuthError):
            c.obtener_clima_actual(LAT, LON)

    def test_404_lanza_not_found(self):
        c = OpenWeatherMapClient(api_key="k", session=_mock_session(404, {}))
        with pytest.raises(OWMNotFoundError):
            c.obtener_clima_actual(LAT, LON)

    def test_429_lanza_rate_limit(self):
        c = OpenWeatherMapClient(api_key="k", session=_mock_session(429, {}))
        with pytest.raises(OWMRateLimitError):
            c.obtener_clima_actual(LAT, LON)

    def test_500_lanza_api_error(self):
        c = OpenWeatherMapClient(api_key="k", session=_mock_session(500, {}))
        with pytest.raises(OWMAPIError):
            c.obtener_clima_actual(LAT, LON)

    def test_401_no_se_reintenta(self):
        session = _mock_session(401, {})
        c = OpenWeatherMapClient(api_key="k", session=session, max_reintentos=3)
        with pytest.raises(OWMAuthError):
            c.obtener_clima_actual(LAT, LON)
        assert session.get.call_count == 1

    def test_timeout_se_propaga(self):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.Timeout("timeout")
        c = OpenWeatherMapClient(api_key="k", session=session, max_reintentos=0)
        with pytest.raises(requests.Timeout):
            c.obtener_clima_actual(LAT, LON)


# ──────────────────────────────────────────────────────────────────────
# Tests de obtener_clima_zmvm
# ──────────────────────────────────────────────────────────────────────

class TestObtenerClimaZMVM:
    def test_devuelve_dataframe(self):
        session = _mock_session(200, PAYLOAD_ACTUAL_OK)
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_clima_zmvm()
        assert isinstance(df, pd.DataFrame)

    def test_numero_de_filas(self):
        session = _mock_session(200, PAYLOAD_ACTUAL_OK)
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_clima_zmvm()
        assert len(df) == len(ESTACIONES_ZMVM)

    def test_columna_estacion_presente(self):
        session = _mock_session(200, PAYLOAD_ACTUAL_OK)
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_clima_zmvm()
        assert "estacion" in df.columns

    def test_nombres_estaciones_correctos(self):
        session = _mock_session(200, PAYLOAD_ACTUAL_OK)
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_clima_zmvm()
        assert set(df["estacion"]) == set(ESTACIONES_ZMVM.keys())

    def test_error_parcial_omite_estacion(self):
        respuestas = []
        for i in range(len(ESTACIONES_ZMVM)):
            mock = MagicMock(spec=requests.Response)
            if i == 2:   # tercera estación falla
                mock.status_code = 500
                mock.text = "error"
                mock.json.return_value = {}
            else:
                mock.status_code = 200
                mock.text = json.dumps(PAYLOAD_ACTUAL_OK)
                mock.json.return_value = PAYLOAD_ACTUAL_OK
            respuestas.append(mock)
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = respuestas
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_clima_zmvm()
        assert len(df) == len(ESTACIONES_ZMVM) - 1

    def test_todos_errores_devuelve_dataframe_vacio(self):
        session = _mock_session(500, {})
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_clima_zmvm()
        assert df.empty

    def test_numero_llamadas_es_numero_estaciones(self):
        session = _mock_session(200, PAYLOAD_ACTUAL_OK)
        c = OpenWeatherMapClient(api_key="k", session=session, pausa_entre_lotes=0)
        c.obtener_clima_zmvm()
        assert session.get.call_count == len(ESTACIONES_ZMVM)


# ──────────────────────────────────────────────────────────────────────
# Tests de calcular_factor_congestion
# ──────────────────────────────────────────────────────────────────────

class TestCalcularFactorCongestion:
    def test_despejado_factor_uno(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador == pytest.approx(1.0)

    def test_despejado_nivel_normal(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        assert f.nivel_alerta == "normal"

    def test_lluvia_llovizna(self, condicion_despejada):
        condicion_despejada.lluvia_1h_mm = 1.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador == pytest.approx(1.20)

    def test_lluvia_moderada(self, condicion_despejada):
        condicion_despejada.lluvia_1h_mm = 5.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador == pytest.approx(1.40)

    def test_lluvia_intensa(self, condicion_despejada):
        condicion_despejada.lluvia_1h_mm = 20.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador == pytest.approx(1.70)

    def test_lluvia_torrencial(self, condicion_despejada):
        condicion_despejada.lluvia_1h_mm = 60.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador == pytest.approx(2.00)

    def test_visibilidad_muy_baja(self, condicion_despejada):
        condicion_despejada.visibilidad_m = 100
        f = calcular_factor_congestion(condicion_despejada)
        assert f.componentes["visibilidad"] == pytest.approx(1.50)

    def test_visibilidad_baja(self, condicion_despejada):
        condicion_despejada.visibilidad_m = 500
        f = calcular_factor_congestion(condicion_despejada)
        assert f.componentes["visibilidad"] == pytest.approx(1.30)

    def test_visibilidad_reducida(self, condicion_despejada):
        condicion_despejada.visibilidad_m = 3000
        f = calcular_factor_congestion(condicion_despejada)
        assert f.componentes["visibilidad"] == pytest.approx(1.10)

    def test_viento_fuerte(self, condicion_despejada):
        condicion_despejada.viento_velocidad_kmh = 50.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.componentes["viento"] == pytest.approx(1.15)

    def test_viento_muy_fuerte(self, condicion_despejada):
        condicion_despejada.viento_velocidad_kmh = 70.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.componentes["viento"] == pytest.approx(1.30)

    def test_tormenta_factor_minimo_18(self, condicion_despejada):
        condicion_despejada.codigo_condicion = 211   # tormenta
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador >= 1.80

    def test_nieve_factor_minimo_17(self, condicion_despejada):
        condicion_despejada.codigo_condicion = 601   # nieve moderada
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador >= 1.70

    def test_factor_capped_en_25(self, condicion_despejada):
        # Escenario extremo: tormenta + lluvia torrencial + niebla densa
        condicion_despejada.lluvia_1h_mm       = 80.0
        condicion_despejada.visibilidad_m      = 50
        condicion_despejada.viento_velocidad_kmh = 80.0
        condicion_despejada.codigo_condicion   = 212
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador <= 2.5

    def test_factor_no_negativo(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        assert f.factor_multiplicador >= 1.0

    def test_nivel_moderado_con_llovizna(self, condicion_despejada):
        condicion_despejada.lluvia_1h_mm = 1.5
        f = calcular_factor_congestion(condicion_despejada)
        assert f.nivel_alerta == "moderado"

    def test_nivel_severo_con_lluvia_moderada(self, condicion_despejada):
        condicion_despejada.lluvia_1h_mm = 5.0
        f = calcular_factor_congestion(condicion_despejada)
        assert f.nivel_alerta == "severo"

    def test_nivel_extremo_con_tormenta(self, condicion_despejada):
        condicion_despejada.codigo_condicion = 202
        f = calcular_factor_congestion(condicion_despejada)
        assert f.nivel_alerta == "extremo"

    def test_devuelve_factor_climatico(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        assert isinstance(f, FactorClimatico)

    def test_componentes_presentes(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        assert {"precipitacion", "visibilidad", "viento", "codigo_condicion"} \
               == set(f.componentes.keys())

    def test_descripcion_vacia_con_despejado(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        assert "normales" in f.descripcion

    def test_descripcion_menciona_lluvia(self, condicion_lluvia):
        f = calcular_factor_congestion(condicion_lluvia)
        assert "lluvia" in f.descripcion

    def test_a_dict_serializable(self, condicion_despejada):
        f = calcular_factor_congestion(condicion_despejada)
        d = f.a_dict()
        assert isinstance(d, dict)
        assert "factor_multiplicador" in d


# ──────────────────────────────────────────────────────────────────────
# Tests de ajustar_velocidades_por_clima
# ──────────────────────────────────────────────────────────────────────

class TestAjustarVelocidades:
    PARAMS_BASE = {
        0: {"media": 40.0, "std": 8.0,  "min": 20.0, "max": 80.0},
        1: {"media": 18.0, "std": 5.0,  "min":  5.0, "max": 35.0},
        2: {"media":  7.0, "std": 3.0,  "min":  2.0, "max": 15.0},
    }

    def _factor(self, valor: float) -> FactorClimatico:
        return FactorClimatico(factor_multiplicador=valor)

    def test_factor_uno_no_modifica_media(self):
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(1.0))
        assert resultado[0]["media"] == pytest.approx(40.0)

    def test_factor_reduce_velocidad_media(self):
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(1.4))
        assert resultado[0]["media"] == pytest.approx(40.0 / 1.4, abs=0.01)

    def test_factor_reduce_velocidad_minima(self):
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(2.0))
        assert resultado[0]["min"] == pytest.approx(20.0 / 2.0, abs=0.01)

    def test_max_no_se_modifica(self):
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(2.0))
        for estado in resultado:
            assert resultado[estado]["max"] == self.PARAMS_BASE[estado]["max"]

    def test_velocidad_minima_nunca_menor_a_1(self):
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(2.5))
        for estado in resultado:
            assert resultado[estado]["min"] >= 1.0

    def test_no_modifica_params_originales(self):
        import copy
        original = copy.deepcopy(self.PARAMS_BASE)
        ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(2.0))
        assert self.PARAMS_BASE == original

    def test_todos_los_estados_ajustados(self):
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(1.5))
        assert set(resultado.keys()) == {0, 1, 2}

    def test_params_vacio_lanza_error(self):
        with pytest.raises(ValueError, match="vacío"):
            ajustar_velocidades_por_clima({}, self._factor(1.0))

    def test_factor_extremo_estado_congestionado(self):
        """Con factor 2.5 el estado congestionado (7 km/h) baja a ~2.8 km/h."""
        resultado = ajustar_velocidades_por_clima(self.PARAMS_BASE, self._factor(2.5))
        assert resultado[2]["media"] == pytest.approx(7.0 / 2.5, abs=0.01)


# ──────────────────────────────────────────────────────────────────────
# Tests de CondicionClimatica y FactorClimatico
# ──────────────────────────────────────────────────────────────────────

class TestDataclasses:
    def test_condicion_a_dict_es_dict(self, condicion_despejada):
        assert isinstance(condicion_despejada.a_dict(), dict)

    def test_condicion_a_dict_claves(self, condicion_despejada):
        d = condicion_despejada.a_dict()
        campos = {
            "latitud", "longitud", "temperatura_c", "humedad_pct",
            "visibilidad_m", "viento_velocidad_kmh", "lluvia_1h_mm",
            "codigo_condicion", "descripcion", "timestamp_utc",
        }
        assert campos.issubset(d.keys())

    def test_factor_a_dict(self):
        f = FactorClimatico(
            factor_multiplicador=1.4,
            componentes={"lluvia": 1.4},
            descripcion="lluvia moderada",
            nivel_alerta="severo",
        )
        d = f.a_dict()
        assert d["factor_multiplicador"] == 1.4
        assert d["nivel_alerta"] == "severo"


# ──────────────────────────────────────────────────────────────────────
# Tests de validación de coordenadas
# ──────────────────────────────────────────────────────────────────────

class TestValidacionCoordenadas:
    @pytest.mark.parametrize("lat,lon", [
        (91.0, LON), (-91.0, LON),
    ])
    def test_latitud_invalida(self, lat, lon):
        with pytest.raises(ValueError, match="Latitud"):
            _validar_coordenadas(lat, lon)

    @pytest.mark.parametrize("lat,lon", [
        (LAT, 181.0), (LAT, -181.0),
    ])
    def test_longitud_invalida(self, lat, lon):
        with pytest.raises(ValueError, match="Longitud"):
            _validar_coordenadas(lat, lon)

    @pytest.mark.parametrize("lat,lon", list(ESTACIONES_ZMVM.values()))
    def test_estaciones_zmvm_validas(self, lat, lon):
        _validar_coordenadas(lat, lon)   # no debe lanzar
