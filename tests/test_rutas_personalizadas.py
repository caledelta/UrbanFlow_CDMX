"""
tests/test_rutas_personalizadas.py — Tests unitarios para src/core/rutas_personalizadas.py
y la herramienta usar_ruta_personalizada de src/agent/tools.py.
"""

from __future__ import annotations

import json
import pytest

from src.core.rutas_personalizadas import (
    PuntoRuta,
    agregar_ruta,
    listar_rutas,
    eliminar_ruta,
    cargar_ruta,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def store_vacio() -> list[PuntoRuta]:
    return []


@pytest.fixture
def store_con_puntos() -> list[PuntoRuta]:
    store: list[PuntoRuta] = []
    agregar_ruta("Casa",    19.4326, -99.1332, store)
    agregar_ruta("Trabajo", 19.4500, -99.1600, store)
    return store


# ─────────────────────────────────────────────────────────────────────────────
# agregar_ruta
# ─────────────────────────────────────────────────────────────────────────────

class TestAgregarRuta:
    def test_agrega_punto_nuevo(self, store_vacio):
        punto = agregar_ruta("Casa", 19.4326, -99.1332, store_vacio)
        assert punto == {"lat": 19.4326, "lon": -99.1332, "nombre": "Casa"}
        assert len(store_vacio) == 1

    def test_sobreescribe_nombre_existente(self, store_con_puntos):
        n_antes = len(store_con_puntos)
        agregar_ruta("Casa", 19.9999, -99.9999, store_con_puntos)
        assert len(store_con_puntos) == n_antes          # no crece
        punto = cargar_ruta("Casa", store_con_puntos)
        assert punto["lat"] == 19.9999                   # coordenadas actualizadas

    def test_nombre_con_espacios_se_stripea(self, store_vacio):
        agregar_ruta("  Gym  ", 19.400, -99.150, store_vacio)
        assert store_vacio[0]["nombre"] == "Gym"

    def test_sobreescritura_case_insensitive(self, store_vacio):
        agregar_ruta("CASA", 1.0, 2.0, store_vacio)
        agregar_ruta("casa", 3.0, 4.0, store_vacio)
        assert len(store_vacio) == 1
        assert store_vacio[0]["lat"] == 3.0


# ─────────────────────────────────────────────────────────────────────────────
# listar_rutas
# ─────────────────────────────────────────────────────────────────────────────

class TestListarRutas:
    def test_lista_vacia(self, store_vacio):
        assert listar_rutas(store_vacio) == []

    def test_devuelve_copia(self, store_con_puntos):
        copia = listar_rutas(store_con_puntos)
        assert len(copia) == len(store_con_puntos)
        copia.clear()
        assert len(store_con_puntos) == 2   # original intacto


# ─────────────────────────────────────────────────────────────────────────────
# eliminar_ruta
# ─────────────────────────────────────────────────────────────────────────────

class TestEliminarRuta:
    def test_elimina_existente(self, store_con_puntos):
        resultado = eliminar_ruta("Casa", store_con_puntos)
        assert resultado is True
        assert cargar_ruta("Casa", store_con_puntos) is None

    def test_retorna_false_si_no_existe(self, store_con_puntos):
        assert eliminar_ruta("Gym", store_con_puntos) is False

    def test_eliminacion_case_insensitive(self, store_con_puntos):
        assert eliminar_ruta("TRABAJO", store_con_puntos) is True
        assert len(store_con_puntos) == 1


# ─────────────────────────────────────────────────────────────────────────────
# cargar_ruta
# ─────────────────────────────────────────────────────────────────────────────

class TestCargarRuta:
    def test_encuentra_punto(self, store_con_puntos):
        punto = cargar_ruta("Trabajo", store_con_puntos)
        assert punto is not None
        assert punto["lat"] == 19.4500

    def test_retorna_none_si_no_existe(self, store_con_puntos):
        assert cargar_ruta("Aeropuerto", store_con_puntos) is None

    def test_busqueda_case_insensitive(self, store_con_puntos):
        assert cargar_ruta("CASA", store_con_puntos) is not None


# ─────────────────────────────────────────────────────────────────────────────
# Tool usar_ruta_personalizada (integración)
# ─────────────────────────────────────────────────────────────────────────────

class TestUsarRutaPersonalizadaTool:
    """Prueba la herramienta registrada en tools.py."""

    @pytest.fixture(autouse=True)
    def import_tool(self):
        from src.agent import tools as _tools  # asegura registro
        from src.agent.tools import usar_ruta_personalizada
        self.tool = usar_ruta_personalizada

    def _store_json(self, puntos: list[PuntoRuta]) -> str:
        return json.dumps(puntos)

    def test_encuentra_lugar_existente(self):
        store = [{"lat": 19.4326, "lon": -99.1332, "nombre": "Casa"}]
        resultado = self.tool("Casa", self._store_json(store))
        assert resultado["encontrado"] is True
        assert resultado["lat"] == 19.4326
        assert resultado["nombre"] == "Casa"

    def test_no_encuentra_lugar_inexistente(self):
        store = [{"lat": 19.4326, "lon": -99.1332, "nombre": "Casa"}]
        resultado = self.tool("Gym", self._store_json(store))
        assert resultado["encontrado"] is False
        assert "Gym" in resultado["mensaje"]

    def test_store_vacio(self):
        resultado = self.tool("Casa", "[]")
        assert resultado["encontrado"] is False

    def test_store_json_invalido(self):
        resultado = self.tool("Casa", "NOT_JSON")
        assert resultado["encontrado"] is False

    def test_busqueda_case_insensitive(self):
        store = [{"lat": 19.4500, "lon": -99.1600, "nombre": "Trabajo"}]
        resultado = self.tool("TRABAJO", self._store_json(store))
        assert resultado["encontrado"] is True

    def test_tool_schema_registrado(self):
        """La herramienta debe estar en el registro de tools."""
        from src.agent.tools import get_tools_schema
        schemas = get_tools_schema()
        nombres = [s["name"] for s in schemas]
        assert "usar_ruta_personalizada" in nombres
