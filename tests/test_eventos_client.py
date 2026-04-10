"""Tests para el cliente de detección de eventos en cuasi-tiempo-real."""
import pytest
from datetime import datetime

from src.data_sources.eventos_client import EventosClient, EventoDetectado


class TestEventoDetectado:
    """Tests del dataclass EventoDetectado."""

    def test_crear_evento_basico(self):
        e = EventoDetectado(
            tipo="accidente",
            descripcion="Choque múltiple en Periférico Sur",
            latitud=19.35,
            longitud=-99.18,
            alcaldia="Coyoacán",
            timestamp=datetime.now(),
            fuente="c5_cdmx",
        )
        assert e.tipo == "accidente"
        assert e.severidad == "media"  # default
        assert e.activo is True

    def test_evento_con_severidad_alta(self):
        e = EventoDetectado(
            tipo="manifestacion",
            descripcion="Marcha sobre Reforma",
            latitud=19.4326,
            longitud=-99.1532,
            alcaldia="Cuauhtémoc",
            timestamp=datetime.now(),
            fuente="c5_cdmx",
            severidad="alta",
            radio_impacto_km=3.0,
        )
        assert e.severidad == "alta"
        assert e.radio_impacto_km == 3.0


class TestEventosClient:
    """Tests del cliente de eventos."""

    def test_instanciar_cliente(self):
        client = EventosClient(timeout=3, cache_ttl_min=2)
        assert client.timeout == 3

    def test_cache_invalido_al_inicio(self):
        client = EventosClient()
        assert not client._cache_valido()

    def test_clasificar_tipo_accidente(self):
        client = EventosClient()
        assert client._clasificar_tipo("choque múltiple") == "accidente"

    def test_clasificar_tipo_manifestacion(self):
        client = EventosClient()
        assert client._clasificar_tipo("marcha sobre reforma") == "manifestacion"

    def test_clasificar_tipo_desconocido(self):
        client = EventosClient()
        assert client._clasificar_tipo("evento desconocido xyz") == "otro"

    def test_distancia_haversine_cero(self):
        d = EventosClient._distancia_haversine(19.43, -99.13, 19.43, -99.13)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_distancia_haversine_conocida(self):
        # Polanco a Aeropuerto ≈ 12 km
        d = EventosClient._distancia_haversine(19.4333, -99.2000, 19.4361, -99.0719)
        assert 10 < d < 15

    def test_estimar_radio_manifestacion(self):
        client = EventosClient()
        assert client._estimar_radio("manifestacion") == 3.0

    def test_estimar_radio_tipo_desconocido(self):
        client = EventosClient()
        assert client._estimar_radio("tipo_inventado") == 2.0

    def test_obtener_eventos_sin_internet(self):
        """El cliente debe retornar lista vacía si no hay conexión."""
        client = EventosClient(timeout=1)
        # Forzar URL inválida para simular sin internet
        client.CKAN_BASE = "https://localhost:1/api/fake"
        eventos = client.obtener_eventos_activos()
        assert isinstance(eventos, list)
        # No debe lanzar excepción

    def test_parsear_registro_c5_invalido(self):
        client = EventosClient()
        resultado = client._parsear_registro_c5({})
        assert resultado is None

    def test_parsear_registro_c5_fuera_zmvm(self):
        """Coordenadas fuera de la ZMVM deben ser descartadas."""
        client = EventosClient()
        record = {
            "latitud": 20.5,  # Fuera de ZMVM
            "longitud": -99.0,
            "tipo_evento": "accidente",
            "alcaldia_hechos": "N/A",
            "fecha_creacion": "2026-04-10",
            "hora_creacion": "08:00:00",
        }
        resultado = client._parsear_registro_c5(record)
        assert resultado is None

    def test_parsear_registro_c5_valido(self):
        client = EventosClient()
        record = {
            "latitud": "19.43",
            "longitud": "-99.15",
            "tipo_evento": "choque sin lesionados",
            "alcaldia_hechos": "Cuauhtémoc",
            "fecha_creacion": "2026-04-10",
            "hora_creacion": "08:30:00",
            "codigo_cierre": "A",
        }
        resultado = client._parsear_registro_c5(record)
        assert resultado is not None
        assert resultado.tipo == "accidente"
        assert resultado.alcaldia == "Cuauhtémoc"
