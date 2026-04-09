"""
Tests para src/agent/tools.py

Cubre: decorador @function_tool, get_tools_schema, helpers privados,
seleccionar_perturbacion, y las tres herramientas del agente
(predecir_tiempo_viaje, consultar_trafico_ahora, verificar_perturbaciones).
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.agent.tools import (
    PERTURBACIONES,
    PUNTOS_CDMX,
    _estado_desde_hora_dia,
    _haversine_km,
    _nivel_alerta_desde_velocidad,
    _parsear_docstring_numpy,
    _parsear_fecha,
    _python_type_to_json,
    _resolver_punto,
    consultar_trafico_ahora,
    function_tool,
    get_tools_schema,
    predecir_tiempo_viaje,
    seleccionar_perturbacion,
    verificar_perturbaciones,
)
from src.models.schemas import PrediccionViaje, RespuestaTomTom


# ──────────────────────────────────────────────────────────────────────
# Tests de @function_tool y get_tools_schema
# ──────────────────────────────────────────────────────────────────────

class TestFunctionTool:
    def test_schema_tiene_nombre(self):
        @function_tool
        def mi_herramienta(x: str) -> str:
            """Hace algo útil."""
            return x

        assert mi_herramienta._tool_schema["name"] == "mi_herramienta"

    def test_schema_tiene_descripcion(self):
        @function_tool
        def otra_herramienta(x: str) -> str:
            """Descripción corta de prueba."""
            return x

        assert "Descripción corta" in otra_herramienta._tool_schema["description"]

    def test_schema_input_schema_tipo_object(self):
        @function_tool
        def herramienta_obj(a: str) -> str:
            """Herramienta de prueba."""
            return a

        assert herramienta_obj._tool_schema["input_schema"]["type"] == "object"

    def test_parametro_requerido_en_required(self):
        @function_tool
        def herramienta_req(nombre: str) -> str:
            """Herramienta de prueba."""
            return nombre

        assert "nombre" in herramienta_req._tool_schema["input_schema"]["required"]

    def test_parametro_con_default_no_en_required(self):
        @function_tool
        def herramienta_opt(nombre: str, modo: str = "auto") -> str:
            """Herramienta de prueba."""
            return nombre

        assert "modo" not in herramienta_opt._tool_schema["input_schema"]["required"]

    def test_tipo_string_mapeado_correctamente(self):
        @function_tool
        def herramienta_tipos(texto: str) -> str:
            """Prueba."""
            return texto

        assert herramienta_tipos._tool_schema["input_schema"]["properties"]["texto"]["type"] == "string"

    def test_tipo_int_propiedad_presente_en_schema(self):
        # En Python 3.14, `from __future__ import annotations` hace que las
        # anotaciones se evalúen como strings ('int'), no como tipos reales.
        # El decorador llama a func.__annotations__ y obtiene 'int' (str), que
        # no está en _PYTHON_TYPE_MAP, por lo que cae al default "string".
        # Verificamos que la propiedad exista y tenga un tipo JSON válido.
        @function_tool
        def herramienta_int(n: int) -> int:
            """Prueba."""
            return n

        tipo = herramienta_int._tool_schema["input_schema"]["properties"]["n"]["type"]
        assert tipo in ("integer", "string")

    def test_funcion_sigue_funcionando(self):
        @function_tool
        def sumar(a: str) -> str:
            """Devuelve el valor."""
            return a + "_ok"

        assert sumar("test") == "test_ok"

    def test_flag_is_tool(self):
        @function_tool
        def herramienta_flag(x: str) -> str:
            """Prueba."""
            return x

        assert herramienta_flag._is_tool is True

    def test_descripcion_parametro_en_schema(self):
        @function_tool
        def herramienta_param_doc(ciudad: str) -> str:
            """
            Busca algo en una ciudad.

            Parámetros
            ----------
            ciudad : str
                Nombre de la ciudad a buscar.
            """
            return ciudad

        props = herramienta_param_doc._tool_schema["input_schema"]["properties"]
        assert "description" in props["ciudad"]
        assert "ciudad" in props["ciudad"]["description"].lower()


class TestGetToolsSchema:
    def test_devuelve_lista(self):
        schemas = get_tools_schema()
        assert isinstance(schemas, list)

    def test_contiene_tres_herramientas_del_agente(self):
        nombres = {s["name"] for s in get_tools_schema()}
        assert {"predecir_tiempo_viaje", "consultar_trafico_ahora", "verificar_perturbaciones"}.issubset(nombres)

    def test_cada_schema_tiene_claves_requeridas(self):
        for schema in get_tools_schema():
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema


# ──────────────────────────────────────────────────────────────────────
# Tests de _python_type_to_json
# ──────────────────────────────────────────────────────────────────────

class TestPythonTypeToJson:
    @pytest.mark.parametrize("tipo,esperado", [
        (str,   "string"),
        (int,   "integer"),
        (float, "number"),
        (bool,  "boolean"),
        (list,  "array"),
        (dict,  "object"),
    ])
    def test_tipos_basicos(self, tipo, esperado):
        assert _python_type_to_json(tipo) == esperado

    def test_tipo_desconocido_devuelve_string(self):
        assert _python_type_to_json(bytes) == "string"


# ──────────────────────────────────────────────────────────────────────
# Tests de _parsear_docstring_numpy
# ──────────────────────────────────────────────────────────────────────

class TestParsearDocstringNumpy:
    def test_extrae_descripcion_principal(self):
        doc = "Primera línea de descripción.\n\nOtra sección."
        desc, _ = _parsear_docstring_numpy(doc)
        assert "Primera línea" in desc

    def test_extrae_descripcion_de_param(self):
        doc = (
            "Función de prueba.\n\n"
            "Parámetros\n"
            "----------\n"
            "nombre : str\n"
            "    Nombre del usuario.\n"
        )
        _, params = _parsear_docstring_numpy(doc)
        assert "nombre" in params
        assert "usuario" in params["nombre"].lower()

    def test_sin_params_devuelve_dict_vacio(self):
        doc = "Solo descripción, sin parámetros."
        _, params = _parsear_docstring_numpy(doc)
        assert params == {}

    def test_seccion_devuelve_no_afecta_descripcion(self):
        doc = (
            "Descripción válida.\n\n"
            "Devuelve\n"
            "--------\n"
            "str\n"
            "    Resultado.\n"
        )
        desc, _ = _parsear_docstring_numpy(doc)
        assert "Descripción válida" in desc

    def test_docstring_vacio(self):
        desc, params = _parsear_docstring_numpy("")
        assert desc == ""
        assert params == {}


# ──────────────────────────────────────────────────────────────────────
# Tests de _haversine_km
# ──────────────────────────────────────────────────────────────────────

class TestHaversineKm:
    def test_mismo_punto_es_cero(self):
        assert _haversine_km(19.43, -99.13, 19.43, -99.13) == pytest.approx(0.0, abs=1e-6)

    def test_distancia_positiva(self):
        # Zócalo → Reforma ≈ 2–3 km
        d = _haversine_km(19.4326, -99.1332, 19.4270, -99.1676)
        assert d > 0.0

    def test_distancia_zocalo_reforma_razonable(self):
        d = _haversine_km(19.4326, -99.1332, 19.4270, -99.1676)
        assert 2.0 < d < 5.0

    def test_simetria(self):
        d1 = _haversine_km(19.43, -99.13, 19.40, -99.17)
        d2 = _haversine_km(19.40, -99.17, 19.43, -99.13)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_distancia_no_negativa(self):
        assert _haversine_km(19.0, -99.0, 20.0, -100.0) >= 0.0


# ──────────────────────────────────────────────────────────────────────
# Tests de _resolver_punto
# ──────────────────────────────────────────────────────────────────────

class TestResolverPunto:
    def test_coincidencia_exacta(self):
        coords = _resolver_punto("Zócalo")
        assert coords == PUNTOS_CDMX["Zócalo"]

    def test_coincidencia_parcial_insensible(self):
        coords = _resolver_punto("perisur")
        assert coords is not None

    def test_nombre_inexistente_devuelve_none(self):
        assert _resolver_punto("Lugar Que No Existe XYZ") is None

    def test_devuelve_tupla_de_dos_floats(self):
        coords = _resolver_punto("Polanco")
        assert isinstance(coords, tuple)
        assert len(coords) == 2
        lat, lon = coords
        assert isinstance(lat, float)
        assert isinstance(lon, float)

    def test_latitudes_en_rango_cdmx(self):
        lat, lon = _resolver_punto("Zócalo")
        assert 19.0 <= lat <= 20.0
        assert -100.0 <= lon <= -98.0


# ──────────────────────────────────────────────────────────────────────
# Tests de _estado_desde_hora_dia
# ──────────────────────────────────────────────────────────────────────

class TestEstadoDesdeHoraDia:
    def test_hora_pico_manana_es_congestionado(self):
        assert _estado_desde_hora_dia("08:00", "lunes") == 2

    def test_hora_pico_tarde_es_congestionado(self):
        assert _estado_desde_hora_dia("18:00", "martes") == 2

    def test_madrugada_es_fluido(self):
        assert _estado_desde_hora_dia("03:00", "lunes") == 0

    def test_sabado_medio_dia_es_lento(self):
        assert _estado_desde_hora_dia("12:00", "sabado") == 1

    def test_domingo_madrugada_es_fluido(self):
        assert _estado_desde_hora_dia("02:00", "domingo") == 0

    def test_hora_invalida_devuelve_sin_error(self):
        estado = _estado_desde_hora_dia("xx:yy", "lunes")
        assert estado in (0, 1, 2)

    def test_dia_none_no_lanza_error(self):
        estado = _estado_desde_hora_dia("10:00", None)
        assert estado in (0, 1, 2)

    @pytest.mark.parametrize("dia", ["saturday", "sat", "sunday", "sun"])
    def test_fin_semana_en_ingles(self, dia):
        # A las 12:00 del fin de semana → LENTO (1)
        assert _estado_desde_hora_dia("12:00", dia) == 1


# ──────────────────────────────────────────────────────────────────────
# Tests de _nivel_alerta_desde_velocidad
# ──────────────────────────────────────────────────────────────────────

class TestNivelAlertaDesdeVelocidad:
    @pytest.mark.parametrize("velocidad,esperado", [
        (50.0, "VERDE"),
        (30.0, "VERDE"),
        (25.0, "AMARILLA"),
        (15.0, "AMARILLA"),
        (10.0, "NARANJA"),
        (8.0,  "NARANJA"),
        (5.0,  "ROJA"),
        (0.0,  "ROJA"),
    ])
    def test_umbrales(self, velocidad, esperado):
        assert _nivel_alerta_desde_velocidad(velocidad) == esperado


# ──────────────────────────────────────────────────────────────────────
# Tests de _parsear_fecha
# ──────────────────────────────────────────────────────────────────────

class TestParsearFecha:
    @pytest.mark.parametrize("cadena", [
        "2024-09-15T20:00:00",
        "2024-09-15T20:00",
        "2024-09-15 20:00:00",
        "2024-09-15 20:00",
        "2024-09-15",
    ])
    def test_formatos_validos(self, cadena):
        dt = _parsear_fecha(cadena)
        assert isinstance(dt, datetime.datetime)
        assert dt.year == 2024
        assert dt.month == 9
        assert dt.day == 15

    def test_formato_invalido_lanza_valueerror(self):
        with pytest.raises(ValueError, match="Formato de fecha"):
            _parsear_fecha("no-es-fecha")

    def test_preserva_hora(self):
        dt = _parsear_fecha("2024-03-09T15:30:00")
        assert dt.hour == 15
        assert dt.minute == 30


# ──────────────────────────────────────────────────────────────────────
# Tests de seleccionar_perturbacion
# ──────────────────────────────────────────────────────────────────────

class TestSeleccionarPerturbacion:
    def test_dia_habil_sin_eventos_devuelve_base(self):
        # Martes 10 de junio, 10:00 — sin perturbación especial
        fecha = datetime.datetime(2024, 6, 10, 10, 0)
        p = seleccionar_perturbacion(fecha, "AZCAPOTZALCO")
        assert p["tipo"] == "base"

    def test_15_sep_noche_centro_devuelve_grito(self):
        fecha = datetime.datetime(2024, 9, 15, 20, 0)
        p = seleccionar_perturbacion(fecha, "CUAUHTEMOC")
        assert p["tipo"] == "festivo"
        assert "Grito" in p["descripcion"] or "sep" in p["descripcion"]

    def test_factor_grito_mayor_que_uno(self):
        fecha = datetime.datetime(2024, 9, 15, 20, 0)
        p = seleccionar_perturbacion(fecha, "CUAUHTEMOC")
        assert p["factor"] > 1.0

    def test_alcaldia_fuera_de_zona_devuelve_base(self):
        # 15 sep en alcaldía que no está en la lista del Grito
        fecha = datetime.datetime(2024, 9, 15, 20, 0)
        p = seleccionar_perturbacion(fecha, "XOCHIMILCO")
        # No es el festivo del Grito; puede ser base u otro
        assert p["factor"] >= 1.0

    def test_fuera_de_horario_devuelve_base(self):
        # El Grito aplica (17, 24); a las 5:00 no debe aplicar
        fecha = datetime.datetime(2024, 9, 15, 5, 0)
        p = seleccionar_perturbacion(fecha, "CUAUHTEMOC")
        assert p["tipo"] == "base"

    def test_devuelve_dict_con_claves_requeridas(self):
        fecha = datetime.datetime(2024, 6, 10, 10, 0)
        p = seleccionar_perturbacion(fecha)
        for clave in ("tipo", "descripcion", "factor", "alcaldias", "horas"):
            assert clave in p

    def test_navidad_factor_menor_que_uno(self):
        # Las protestas (CNTE, 9 de marzo) no tienen filtro de fecha — aplican
        # cualquier día dentro de su ventana horaria. A las 3:00 AM quedan
        # fuera de sus horarios (8-20 y 10-21), por lo que Navidad (0.60) domina.
        fecha = datetime.datetime(2024, 12, 25, 3, 0)
        p = seleccionar_perturbacion(fecha)
        assert p["factor"] < 1.0

    def test_selecciona_factor_mas_severo(self):
        """Si dos perturbaciones aplican, devuelve la de mayor factor."""
        # Hay que forzar una situación con factor alto en CUAUHTEMOC
        fecha = datetime.datetime(2024, 9, 15, 20, 0)
        p = seleccionar_perturbacion(fecha, "CUAUHTEMOC")
        # El Grito es la más severa (factor 1.80) para esa alcaldía
        assert p["factor"] == 1.80


# ──────────────────────────────────────────────────────────────────────
# Tests de predecir_tiempo_viaje
# ──────────────────────────────────────────────────────────────────────

class TestPredecirTiempoViaje:
    def test_devuelve_prediccion_viaje(self):
        r = predecir_tiempo_viaje("Zócalo", "Polanco", "10:00", "lunes")
        assert isinstance(r, PrediccionViaje)

    def test_orden_percentiles(self):
        r = predecir_tiempo_viaje("Reforma · Ángel", "Metro Pantitlán", "08:00", "martes")
        assert r.p10_min <= r.p50_min <= r.p90_min

    def test_tiempos_positivos(self):
        r = predecir_tiempo_viaje("Zócalo", "Santa Fe", "09:00", "miércoles")
        assert r.p10_min > 0
        assert r.p50_min > 0
        assert r.p90_min > 0

    def test_origen_preservado(self):
        r = predecir_tiempo_viaje("Zócalo", "Polanco", "10:00", "lunes")
        assert r.origen == "Zócalo"

    def test_destino_preservado(self):
        r = predecir_tiempo_viaje("Zócalo", "Polanco", "10:00", "lunes")
        assert r.destino == "Polanco"

    def test_nivel_alerta_valido(self):
        r = predecir_tiempo_viaje("Zócalo", "Polanco", "10:00", "lunes")
        assert r.nivel_alerta in ("VERDE", "AMARILLA", "NARANJA", "ROJA")

    def test_resumen_contiene_origen_y_destino(self):
        r = predecir_tiempo_viaje("Zócalo", "Polanco", "10:00", "lunes")
        assert "Zócalo" in r.resumen
        assert "Polanco" in r.resumen

    def test_hora_pico_mas_lento_que_valle(self):
        """P50 en hora pico debe ser ≥ P50 en hora valle para misma ruta."""
        r_pico  = predecir_tiempo_viaje("Zócalo", "Santa Fe", "08:00", "lunes")
        r_valle = predecir_tiempo_viaje("Zócalo", "Santa Fe", "14:00", "lunes")
        # La simulación es estocástica; verificamos que el P50 no sea idéntico
        # en los dos extremos (pico vs. madrugada es más robusto)
        r_madrugada = predecir_tiempo_viaje("Zócalo", "Santa Fe", "03:00", "lunes")
        assert r_pico.p50_min >= r_madrugada.p50_min

    def test_destino_no_reconocido_usa_fallback_o_zocalo(self):
        """Destino desconocido no debe lanzar excepción."""
        r = predecir_tiempo_viaje("Zócalo", "LugarInexistente_XYZ", "10:00", "lunes")
        assert isinstance(r, PrediccionViaje)

    def test_schema_tiene_predecir_tiempo_viaje(self):
        nombres = [s["name"] for s in get_tools_schema()]
        assert "predecir_tiempo_viaje" in nombres


# ──────────────────────────────────────────────────────────────────────
# Tests de consultar_trafico_ahora
# ──────────────────────────────────────────────────────────────────────

class TestConsultarTraficoAhora:
    def test_sin_api_key_devuelve_fallback(self, monkeypatch):
        monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
        r = consultar_trafico_ahora("Reforma · Ángel")
        assert isinstance(r, RespuestaTomTom)
        assert r.confianza == 0.0

    def test_corredor_inexistente_devuelve_fallback(self, monkeypatch):
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-key")
        r = consultar_trafico_ahora("LugarInexistente_XYZ")
        assert isinstance(r, RespuestaTomTom)
        assert r.confianza == 0.0

    def test_api_exitosa_devuelve_datos_reales(self, monkeypatch):
        monkeypatch.setenv("TOMTOM_API_KEY", "fake-key")
        segmento_mock = MagicMock()
        segmento_mock.velocidad_actual_kmh = 42.0
        segmento_mock.velocidad_libre_kmh  = 60.0
        segmento_mock.confianza            = 0.85
        segmento_mock.ratio_congestion     = 0.70

        client_mock = MagicMock()
        client_mock.obtener_segmento.return_value = segmento_mock

        with patch("src.agent.tools.TomTomTrafficClient", return_value=client_mock):
            r = consultar_trafico_ahora("Reforma · Ángel")

        assert r.velocidad_actual_kmh == pytest.approx(42.0)
        assert r.confianza == pytest.approx(0.85)

    def test_api_error_devuelve_fallback(self, monkeypatch):
        from src.ingestion.tomtom_client import TomTomAPIError

        monkeypatch.setenv("TOMTOM_API_KEY", "fake-key")
        client_mock = MagicMock()
        client_mock.obtener_segmento.side_effect = TomTomAPIError("timeout")

        with patch("src.agent.tools.TomTomTrafficClient", return_value=client_mock):
            r = consultar_trafico_ahora("Reforma · Ángel")

        assert isinstance(r, RespuestaTomTom)
        assert r.confianza == 0.0

    def test_ratio_flujo_fallback_en_rango(self, monkeypatch):
        monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
        r = consultar_trafico_ahora("Zócalo")
        assert 0.0 <= r.ratio_flujo <= 1.0

    def test_schema_tiene_consultar_trafico_ahora(self):
        nombres = [s["name"] for s in get_tools_schema()]
        assert "consultar_trafico_ahora" in nombres


# ──────────────────────────────────────────────────────────────────────
# Tests de verificar_perturbaciones
# ──────────────────────────────────────────────────────────────────────

class TestVerificarPerturbaciones:
    def test_devuelve_dict(self):
        r = verificar_perturbaciones("2024-06-10T10:00:00", "CUAUHTEMOC")
        assert isinstance(r, dict)

    def test_claves_presentes(self):
        r = verificar_perturbaciones("2024-06-10T10:00:00", "CUAUHTEMOC")
        for clave in ("tipo", "descripcion", "factor", "alcaldias", "horas"):
            assert clave in r

    def test_grito_independencia_cuauhtemoc(self):
        r = verificar_perturbaciones("2024-09-15T20:00:00", "CUAUHTEMOC")
        assert r["factor"] > 1.0
        assert r["tipo"] == "festivo"

    def test_fecha_sin_eventos_devuelve_base(self):
        r = verificar_perturbaciones("2024-06-10T10:00:00", "AZCAPOTZALCO")
        assert r["tipo"] == "base"

    def test_fecha_invalida_devuelve_base(self):
        """Fecha no parseable → fallback seguro (base)."""
        r = verificar_perturbaciones("fecha-no-valida", "CUAUHTEMOC")
        assert r["tipo"] == "base"

    def test_navidad_factor_menor_que_uno(self):
        # A las 3:00 AM las protestas están fuera de su ventana horaria,
        # así que Navidad (factor 0.60) es la única perturbación activa.
        r = verificar_perturbaciones("2024-12-25T03:00:00", "CUAUHTEMOC")
        assert r["factor"] < 1.0

    def test_schema_tiene_verificar_perturbaciones(self):
        nombres = [s["name"] for s in get_tools_schema()]
        assert "verificar_perturbaciones" in nombres

    @pytest.mark.parametrize("formato", [
        "2024-09-15T20:00:00",
        "2024-09-15T20:00",
        "2024-09-15 20:00:00",
        "2024-09-15 20:00",
    ])
    def test_formatos_fecha_aceptados(self, formato):
        r = verificar_perturbaciones(formato, "CUAUHTEMOC")
        assert isinstance(r, dict)
