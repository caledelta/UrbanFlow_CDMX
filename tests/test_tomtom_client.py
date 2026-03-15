"""
Tests para src/ingestion/tomtom_client.py

Todos los tests usan mocks de requests.Session — nunca hacen llamadas
reales a la API de TomTom.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call
from datetime import timezone

import pandas as pd
import pytest
import requests

from src.ingestion.tomtom_client import (
    TomTomTrafficClient,
    TomTomAPIError,
    TomTomAuthError,
    TomTomRateLimitError,
    TomTomNotFoundError,
    SegmentoVial,
    _parsear_respuesta,
    _validar_coordenadas,
    ZMVM_BBOX,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers y fixtures
# ──────────────────────────────────────────────────────────────────────

RESPUESTA_OK = {
    "flowSegmentData": {
        "frc":                "FRC3",
        "currentSpeed":       35,
        "freeFlowSpeed":      60,
        "currentTravelTime":  210,
        "freeFlowTravelTime": 120,
        "confidence":         0.92,
        "roadClosure":        False,
        "coordinates": {
            "coordinate": [
                {"latitude": 19.4326, "longitude": -99.1332},
                {"latitude": 19.4330, "longitude": -99.1340},
            ]
        },
    }
}

LAT_CDMX = 19.4326
LON_CDMX = -99.1332


def _mock_session(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Devuelve una sesión mock que responde con el status y JSON indicados."""
    mock_resp           = MagicMock(spec=requests.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data if json_data is not None else RESPUESTA_OK
    mock_resp.text      = json.dumps(mock_resp.json.return_value)
    session             = MagicMock(spec=requests.Session)
    session.get.return_value = mock_resp
    return session


@pytest.fixture
def cliente_ok() -> TomTomTrafficClient:
    """Cliente con sesión mock que siempre devuelve HTTP 200 OK."""
    return TomTomTrafficClient(
        api_key="key-de-test",
        session=_mock_session(200, RESPUESTA_OK),
    )


@pytest.fixture
def coords_zmvm() -> list[tuple[float, float]]:
    """Tres puntos dentro de la ZMVM para tests de lote."""
    return [
        (19.4326, -99.1332),   # Centro Histórico
        (19.3600, -99.1800),   # Coyoacán
        (19.5000, -99.1500),   # Tlalnepantla
    ]


# ──────────────────────────────────────────────────────────────────────
# Tests de construcción del cliente
# ──────────────────────────────────────────────────────────────────────

class TestConstruccion:
    def test_crea_correctamente(self):
        c = TomTomTrafficClient(api_key="abc123")
        assert c.zoom == 14

    def test_zoom_personalizado(self):
        c = TomTomTrafficClient(api_key="abc123", zoom=12)
        assert c.zoom == 12

    def test_api_key_vacia_lanza_error(self):
        with pytest.raises(ValueError, match="api_key"):
            TomTomTrafficClient(api_key="")

    def test_api_key_solo_espacios_lanza_error(self):
        with pytest.raises(ValueError, match="api_key"):
            TomTomTrafficClient(api_key="   ")

    def test_zoom_bajo_lanza_error(self):
        with pytest.raises(ValueError, match="zoom"):
            TomTomTrafficClient(api_key="abc", zoom=9)

    def test_zoom_alto_lanza_error(self):
        with pytest.raises(ValueError, match="zoom"):
            TomTomTrafficClient(api_key="abc", zoom=19)

    def test_timeout_invalido_lanza_error(self):
        with pytest.raises(ValueError, match="timeout"):
            TomTomTrafficClient(api_key="abc", timeout=0)

    def test_max_reintentos_negativo_lanza_error(self):
        with pytest.raises(ValueError, match="max_reintentos"):
            TomTomTrafficClient(api_key="abc", max_reintentos=-1)

    def test_session_inyectada_se_usa(self):
        session = _mock_session()
        c = TomTomTrafficClient(api_key="abc", session=session)
        assert c._session is session

    def test_session_none_crea_nueva(self):
        c = TomTomTrafficClient(api_key="abc", session=None)
        assert isinstance(c._session, requests.Session)


# ──────────────────────────────────────────────────────────────────────
# Tests de obtener_segmento (éxito)
# ──────────────────────────────────────────────────────────────────────

class TestObtenerSegmento:
    def test_devuelve_segmento_vial(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert isinstance(seg, SegmentoVial)

    def test_velocidad_actual(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.velocidad_actual_kmh == 35.0

    def test_velocidad_libre(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.velocidad_libre_kmh == 60.0

    def test_tiempo_actual(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.tiempo_viaje_actual_s == 210

    def test_tiempo_libre(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.tiempo_viaje_libre_s == 120

    def test_confianza(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.confianza == pytest.approx(0.92)

    def test_clase_vial(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.clase_vial == "FRC3"

    def test_sin_cierre_vial(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.cierre_vial is False

    def test_ratio_congestion_calculado(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        # 35 / 60 = 0.5833...
        assert seg.ratio_congestion == pytest.approx(35 / 60, abs=1e-3)

    def test_coordenadas_preservadas(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.latitud  == LAT_CDMX
        assert seg.longitud == LON_CDMX

    def test_timestamp_es_string(self, cliente_ok):
        seg = cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert isinstance(seg.timestamp_utc, str)
        assert len(seg.timestamp_utc) > 0

    def test_url_contiene_zoom(self, cliente_ok):
        cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        url_llamada = cliente_ok._session.get.call_args[0][0]
        assert "/14/" in url_llamada

    def test_params_contienen_point(self, cliente_ok):
        cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        kwargs = cliente_ok._session.get.call_args[1]
        assert f"{LAT_CDMX},{LON_CDMX}" == kwargs["params"]["point"]

    def test_params_unidad_kmph(self, cliente_ok):
        cliente_ok.obtener_segmento(LAT_CDMX, LON_CDMX)
        kwargs = cliente_ok._session.get.call_args[1]
        assert kwargs["params"]["unit"] == "KMPH"

    def test_cierre_vial_true(self):
        resp_cierre = {
            "flowSegmentData": {**RESPUESTA_OK["flowSegmentData"], "roadClosure": True}
        }
        c = TomTomTrafficClient(api_key="k", session=_mock_session(200, resp_cierre))
        seg = c.obtener_segmento(LAT_CDMX, LON_CDMX)
        assert seg.cierre_vial is True


# ──────────────────────────────────────────────────────────────────────
# Tests de manejo de errores HTTP
# ──────────────────────────────────────────────────────────────────────

class TestErroresHTTP:
    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_error(self, status_code):
        c = TomTomTrafficClient(api_key="k", session=_mock_session(status_code, {}))
        with pytest.raises(TomTomAuthError):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)

    def test_not_found(self):
        c = TomTomTrafficClient(api_key="k", session=_mock_session(404, {}))
        with pytest.raises(TomTomNotFoundError):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)

    def test_rate_limit(self):
        c = TomTomTrafficClient(api_key="k", session=_mock_session(429, {}))
        with pytest.raises(TomTomRateLimitError):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)

    def test_server_error_500(self):
        c = TomTomTrafficClient(api_key="k", session=_mock_session(500, {}))
        with pytest.raises(TomTomAPIError):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)

    def test_error_inesperado_400(self):
        c = TomTomTrafficClient(api_key="k", session=_mock_session(400, {}))
        with pytest.raises(TomTomAPIError):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)

    def test_respuesta_sin_flow_segment_data(self):
        c = TomTomTrafficClient(api_key="k", session=_mock_session(200, {"otro": "campo"}))
        with pytest.raises(TomTomAPIError, match="flowSegmentData"):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)

    def test_auth_error_no_se_reintenta(self):
        """Los errores 401 no deben generar reintentos."""
        session = _mock_session(401, {})
        c = TomTomTrafficClient(api_key="k", session=session, max_reintentos=3)
        with pytest.raises(TomTomAuthError):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)
        # Solo una llamada — sin reintentos para errores de auth
        assert session.get.call_count == 1

    def test_timeout_se_propaga(self):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.Timeout("timeout simulado")
        # max_reintentos=0 para que falle rápido
        c = TomTomTrafficClient(api_key="k", session=session, max_reintentos=0)
        with pytest.raises(requests.Timeout):
            c.obtener_segmento(LAT_CDMX, LON_CDMX)


# ──────────────────────────────────────────────────────────────────────
# Tests de validación de coordenadas
# ──────────────────────────────────────────────────────────────────────

class TestValidacionCoordenadas:
    def test_latitud_invalida_alta(self, cliente_ok):
        with pytest.raises(ValueError, match="Latitud"):
            cliente_ok.obtener_segmento(lat=91.0, lon=LON_CDMX)

    def test_latitud_invalida_baja(self, cliente_ok):
        with pytest.raises(ValueError, match="Latitud"):
            cliente_ok.obtener_segmento(lat=-91.0, lon=LON_CDMX)

    def test_longitud_invalida_alta(self, cliente_ok):
        with pytest.raises(ValueError, match="Longitud"):
            cliente_ok.obtener_segmento(lat=LAT_CDMX, lon=181.0)

    def test_longitud_invalida_baja(self, cliente_ok):
        with pytest.raises(ValueError, match="Longitud"):
            cliente_ok.obtener_segmento(lat=LAT_CDMX, lon=-181.0)

    def test_coordenadas_limite_validas(self):
        """Las coordenadas en los límites exactos son válidas."""
        _validar_coordenadas(90.0, 180.0)
        _validar_coordenadas(-90.0, -180.0)

    @pytest.mark.parametrize("lat,lon", [
        (ZMVM_BBOX["lat_min"], ZMVM_BBOX["lon_min"]),
        (ZMVM_BBOX["lat_max"], ZMVM_BBOX["lon_max"]),
        (19.4326, -99.1332),   # Centro CDMX
    ])
    def test_coordenadas_zmvm_validas(self, lat, lon):
        _validar_coordenadas(lat, lon)  # no debe lanzar


# ──────────────────────────────────────────────────────────────────────
# Tests de obtener_segmentos_lote
# ──────────────────────────────────────────────────────────────────────

class TestObtenerSegmentosLote:
    def test_devuelve_dataframe(self, coords_zmvm):
        session = _mock_session(200, RESPUESTA_OK)
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_segmentos_lote(coords_zmvm)
        assert isinstance(df, pd.DataFrame)

    def test_filas_correctas(self, coords_zmvm):
        session = _mock_session(200, RESPUESTA_OK)
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_segmentos_lote(coords_zmvm)
        assert len(df) == len(coords_zmvm)

    def test_columnas_esperadas(self, coords_zmvm):
        session = _mock_session(200, RESPUESTA_OK)
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_segmentos_lote(coords_zmvm)
        columnas_requeridas = {
            "latitud", "longitud",
            "velocidad_actual_kmh", "velocidad_libre_kmh",
            "tiempo_viaje_actual_s", "tiempo_viaje_libre_s",
            "confianza", "clase_vial", "cierre_vial",
            "ratio_congestion", "timestamp_utc",
        }
        assert columnas_requeridas.issubset(df.columns)

    def test_lista_vacia_lanza_error(self):
        c = TomTomTrafficClient(api_key="k")
        with pytest.raises(ValueError, match="vacía"):
            c.obtener_segmentos_lote([])

    def test_error_parcial_omite_fila(self):
        """Si un punto falla (404), el lote continúa y omite ese punto."""
        respuestas = [
            MagicMock(status_code=200, json=MagicMock(return_value=RESPUESTA_OK), text="ok"),
            MagicMock(status_code=404, json=MagicMock(return_value={}),           text="nf"),
            MagicMock(status_code=200, json=MagicMock(return_value=RESPUESTA_OK), text="ok"),
        ]
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = respuestas
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_segmentos_lote([(19.43, -99.13), (19.44, -99.14), (19.45, -99.15)])
        assert len(df) == 2   # solo los 2 que respondieron OK

    def test_todos_errores_devuelve_dataframe_vacio(self):
        session = _mock_session(500, {})
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0)
        df = c.obtener_segmentos_lote([(19.43, -99.13)])
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_numero_llamadas_http(self, coords_zmvm):
        session = _mock_session(200, RESPUESTA_OK)
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0)
        c.obtener_segmentos_lote(coords_zmvm)
        assert session.get.call_count == len(coords_zmvm)

    def test_pausa_entre_lotes_se_respeta(self):
        """Verifica que se llama time.sleep entre peticiones."""
        session = _mock_session(200, RESPUESTA_OK)
        c = TomTomTrafficClient(api_key="k", session=session, pausa_entre_lotes=0.05)
        with patch("src.ingestion.tomtom_client.time.sleep") as mock_sleep:
            c.obtener_segmentos_lote([(19.43, -99.13), (19.44, -99.14)])
        # Se duerme entre peticiones (N-1 pausas para N coordenadas)
        assert mock_sleep.call_count == 1
        assert mock_sleep.call_args == call(0.05)


# ──────────────────────────────────────────────────────────────────────
# Tests de SegmentoVial
# ──────────────────────────────────────────────────────────────────────

class TestSegmentoVial:
    @pytest.fixture
    def segmento(self) -> SegmentoVial:
        return SegmentoVial(
            latitud=LAT_CDMX, longitud=LON_CDMX,
            velocidad_actual_kmh=35.0, velocidad_libre_kmh=60.0,
            tiempo_viaje_actual_s=210, tiempo_viaje_libre_s=120,
            confianza=0.92, clase_vial="FRC3", cierre_vial=False,
            ratio_congestion=round(35/60, 4), timestamp_utc="2026-03-15T12:00:00",
        )

    def test_a_dict_es_dict(self, segmento):
        assert isinstance(segmento.a_dict(), dict)

    def test_a_dict_tiene_todas_las_claves(self, segmento):
        d = segmento.a_dict()
        campos = {
            "latitud", "longitud", "velocidad_actual_kmh", "velocidad_libre_kmh",
            "tiempo_viaje_actual_s", "tiempo_viaje_libre_s", "confianza",
            "clase_vial", "cierre_vial", "ratio_congestion", "timestamp_utc",
        }
        assert campos == set(d.keys())

    def test_a_dict_preserva_valores(self, segmento):
        d = segmento.a_dict()
        assert d["velocidad_actual_kmh"] == 35.0
        assert d["clase_vial"] == "FRC3"


# ──────────────────────────────────────────────────────────────────────
# Tests de _parsear_respuesta
# ──────────────────────────────────────────────────────────────────────

class TestParsearRespuesta:
    def test_parsea_respuesta_completa(self):
        seg = _parsear_respuesta(RESPUESTA_OK, LAT_CDMX, LON_CDMX)
        assert seg.velocidad_actual_kmh == 35.0

    def test_falta_flow_segment_data_lanza_error(self):
        with pytest.raises(TomTomAPIError, match="flowSegmentData"):
            _parsear_respuesta({}, LAT_CDMX, LON_CDMX)

    def test_ratio_cero_cuando_velocidad_libre_es_cero(self):
        resp = {
            "flowSegmentData": {**RESPUESTA_OK["flowSegmentData"], "freeFlowSpeed": 0}
        }
        seg = _parsear_respuesta(resp, LAT_CDMX, LON_CDMX)
        assert seg.ratio_congestion == 0.0

    def test_campos_opcionales_con_defaults(self):
        """Si faltan campos opcionales, se usan valores por defecto."""
        resp = {"flowSegmentData": {"currentSpeed": 20, "freeFlowSpeed": 50}}
        seg = _parsear_respuesta(resp, LAT_CDMX, LON_CDMX)
        assert seg.confianza  == 1.0
        assert seg.cierre_vial is False
        assert seg.clase_vial == "FRC_DESCONOCIDA"
