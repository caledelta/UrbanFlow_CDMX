"""Tests para el clasificador de eventos → factores de perturbación."""
import pytest
from datetime import datetime

from src.data_sources.eventos_client import EventoDetectado
from src.agent.eventos_dinamicos import (
    estimar_factor,
    agregar_factores,
    resumir_eventos,
    FACTORES_DINAMICOS,
)


def _evento(tipo="accidente", severidad="media") -> EventoDetectado:
    """Factory de EventoDetectado para tests."""
    return EventoDetectado(
        tipo=tipo,
        descripcion=f"Test {tipo}",
        latitud=19.43,
        longitud=-99.13,
        alcaldia="Test",
        timestamp=datetime.now(),
        fuente="test",
        severidad=severidad,
    )


class TestEstimarFactor:

    def test_accidente_media(self):
        assert estimar_factor(_evento("accidente", "media")) == 1.08

    def test_manifestacion_alta(self):
        assert estimar_factor(_evento("manifestacion", "alta")) == 1.27

    def test_manifestacion_critica(self):
        assert estimar_factor(_evento("manifestacion", "critica")) == 1.35

    def test_tipo_desconocido(self):
        assert estimar_factor(_evento("tipo_raro", "media")) == 1.05

    def test_todos_los_pares_mapeados(self):
        """Todos los pares en FACTORES_DINAMICOS deben retornar f > 1."""
        for key, f in FACTORES_DINAMICOS.items():
            assert f > 1.0, f"Factor para {key} debe ser > 1.0"
            assert f <= 1.50, f"Factor para {key} debe ser <= 1.50"


class TestAgregarFactores:

    def test_sin_eventos(self):
        assert agregar_factores([]) == 1.0

    def test_un_evento(self):
        f = agregar_factores([_evento("accidente", "media")])
        assert f == pytest.approx(1.08)

    def test_dos_eventos_composicion(self):
        eventos = [_evento("accidente", "media"), _evento("cierre_vial", "alta")]
        f = agregar_factores(eventos)
        assert f == pytest.approx(1.08 * 1.20, rel=1e-3)

    def test_truncacion_a_f_max(self):
        """Muchos eventos no deben superar f_max=1.50."""
        eventos = [_evento("manifestacion", "critica")] * 10
        f = agregar_factores(eventos)
        assert f == 1.50

    def test_resultado_siempre_positivo(self):
        eventos = [_evento("accidente", "baja")]
        assert agregar_factores(eventos) >= 1.0


class TestResumirEventos:

    def test_sin_eventos(self):
        assert resumir_eventos([]) == ""

    def test_un_evento(self):
        resumen = resumir_eventos([_evento("accidente", "media")])
        assert "1 evento(s)" in resumen
        assert "accidente" in resumen.lower() or "🚗" in resumen

    def test_maximo_5_eventos(self):
        eventos = [_evento("accidente", "baja")] * 8
        resumen = resumir_eventos(eventos)
        # Debe mostrar máximo 5 + la línea de encabezado
        lineas = resumen.strip().split("\n")
        assert len(lineas) <= 6
