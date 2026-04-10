"""
Tests para src/agent/agent.py

Cubre: construcción de VialAIAgent, loop de tool_use, despacho de herramientas,
manejo de errores de API con fallback, y extracción de texto.

Todos los tests mockean la Anthropic API — nunca se hacen llamadas reales.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import anthropic
import pytest

from src.agent.agent import (
    MAX_ITERACIONES,
    MAX_TOKENS,
    MODEL,
    VialAIAgent,
    _DISPATCH,
)
from src.agent.prompts import SYSTEM_PROMPT
from src.models.schemas import PrediccionViaje, RespuestaTomTom


# ══════════════════════════════════════════════════════════════════════════
# Helpers para construir mocks de respuestas Anthropic
# ══════════════════════════════════════════════════════════════════════════

def _bloque_texto(texto: str) -> MagicMock:
    """Mock de un TextBlock de Anthropic."""
    bloque = MagicMock()
    bloque.type = "text"
    bloque.text = texto
    return bloque


def _bloque_tool_use(
    tool_id: str,
    nombre: str,
    input_args: dict,
) -> MagicMock:
    """Mock de un ToolUseBlock de Anthropic."""
    bloque = MagicMock()
    bloque.type = "tool_use"
    bloque.id = tool_id
    bloque.name = nombre
    bloque.input = input_args
    return bloque


def _respuesta_texto(texto: str) -> MagicMock:
    """Mock de respuesta con stop_reason == 'end_turn' y un bloque de texto."""
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [_bloque_texto(texto)]
    return resp


def _respuesta_tool_use(*bloques_tool) -> MagicMock:
    """Mock de respuesta con stop_reason == 'tool_use' y uno o más bloques tool_use."""
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = list(bloques_tool)
    return resp


def _mock_client(*respuestas_secuenciales) -> MagicMock:
    """
    Crea un mock de anthropic.Anthropic cuyo messages.create() devuelve
    las respuestas en el orden dado (una por llamada).
    """
    cliente = MagicMock(spec=anthropic.Anthropic)
    cliente.messages.create.side_effect = list(respuestas_secuenciales)
    return cliente


# ══════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def agente_texto() -> VialAIAgent:
    """Agente configurado para devolver siempre una respuesta de texto simple."""
    cliente = _mock_client(_respuesta_texto("Hola desde VialAI."))
    return VialAIAgent(client=cliente)


@pytest.fixture
def args_prediccion() -> dict:
    return {
        "origen": "Zócalo",
        "destino": "Polanco",
        "hora": "08:00",
        "dia": "lunes",
    }


# ══════════════════════════════════════════════════════════════════════════
# TestVialAIAgentConstruccion
# ══════════════════════════════════════════════════════════════════════════

class TestVialAIAgentConstruccion:
    def test_model_por_defecto(self):
        agente = VialAIAgent(client=MagicMock())
        assert agente.model == MODEL

    def test_max_tokens_por_defecto(self):
        agente = VialAIAgent(client=MagicMock())
        assert agente.max_tokens == MAX_TOKENS

    def test_max_iteraciones_por_defecto(self):
        agente = VialAIAgent(client=MagicMock())
        assert agente.max_iteraciones == MAX_ITERACIONES

    def test_model_personalizado(self):
        agente = VialAIAgent(client=MagicMock(), model="claude-opus-4-6")
        assert agente.model == "claude-opus-4-6"

    def test_max_tokens_personalizado(self):
        agente = VialAIAgent(client=MagicMock(), max_tokens=1024)
        assert agente.max_tokens == 1024

    def test_max_iteraciones_personalizado(self):
        agente = VialAIAgent(client=MagicMock(), max_iteraciones=3)
        assert agente.max_iteraciones == 3

    def test_tools_registradas_son_tres(self):
        agente = VialAIAgent(client=MagicMock())
        assert len(agente._tools) >= 3

    def test_tools_contienen_herramientas_esperadas(self):
        agente = VialAIAgent(client=MagicMock())
        nombres = {t["name"] for t in agente._tools}
        assert {"predecir_tiempo_viaje", "consultar_trafico_ahora", "verificar_perturbaciones"}.issubset(nombres)

    def test_client_inyectado_se_usa(self):
        cliente = MagicMock(spec=anthropic.Anthropic)
        agente = VialAIAgent(client=cliente)
        assert agente._client is cliente

    def test_crea_client_anthropic_cuando_no_se_inyecta(self):
        with patch("src.agent.agent.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = MagicMock()
            agente = VialAIAgent(api_key="test-key")
            mock_cls.assert_called_once_with(api_key="test-key")


# ══════════════════════════════════════════════════════════════════════════
# TestRun — comportamiento de la API pública
# ══════════════════════════════════════════════════════════════════════════

class TestRun:
    def test_devuelve_texto_de_respuesta(self, agente_texto):
        resultado = agente_texto.run("¿Cómo está el tráfico?")
        assert resultado == "Hola desde VialAI."

    def test_acepta_historial_none(self, agente_texto):
        resultado = agente_texto.run("¿Hola?", historial=None)
        assert isinstance(resultado, str)

    def test_acepta_historial_vacio(self, agente_texto):
        resultado = agente_texto.run("¿Hola?", historial=[])
        assert isinstance(resultado, str)

    def test_historial_se_incluye_en_messages(self):
        cliente = _mock_client(_respuesta_texto("Respuesta."))
        agente = VialAIAgent(client=cliente)

        historial = [
            {"role": "user",      "content": "Pregunta anterior"},
            {"role": "assistant", "content": "Respuesta anterior"},
        ]
        agente.run("Nueva pregunta", historial=historial)

        _, kwargs = cliente.messages.create.call_args
        messages = kwargs["messages"]
        # Los 2 del historial + 1 nuevo = 3 mensajes
        assert len(messages) == 3
        assert messages[0]["content"] == "Pregunta anterior"
        assert messages[2]["content"] == "Nueva pregunta"

    def test_api_llamada_con_system_prompt(self, agente_texto):
        agente_texto.run("¿Hola?")
        _, kwargs = agente_texto._client.messages.create.call_args
        assert kwargs["system"] == SYSTEM_PROMPT

    def test_api_llamada_con_tools(self, agente_texto):
        agente_texto.run("¿Hola?")
        _, kwargs = agente_texto._client.messages.create.call_args
        assert isinstance(kwargs["tools"], list)
        assert len(kwargs["tools"]) >= 3

    def test_api_llamada_con_modelo_correcto(self, agente_texto):
        agente_texto.run("¿Hola?")
        _, kwargs = agente_texto._client.messages.create.call_args
        assert kwargs["model"] == MODEL

    def test_mensaje_usuario_como_ultimo_mensaje(self, agente_texto):
        agente_texto.run("Consulta específica")
        _, kwargs = agente_texto._client.messages.create.call_args
        ultimo = kwargs["messages"][-1]
        assert ultimo["role"] == "user"
        assert ultimo["content"] == "Consulta específica"


# ══════════════════════════════════════════════════════════════════════════
# TestLoopToolUse — ciclo tool_use → herramienta → respuesta
# ══════════════════════════════════════════════════════════════════════════

class TestLoopToolUse:
    def test_una_iteracion_sin_tool_use(self):
        cliente = _mock_client(_respuesta_texto("Respuesta directa."))
        agente = VialAIAgent(client=cliente)
        resultado = agente.run("¿Cuánto hay de CU a TAPO?")
        assert resultado == "Respuesta directa."
        assert cliente.messages.create.call_count == 1

    def test_tool_use_mas_respuesta_final(self):
        """Simula: tool_use → ejecución → end_turn."""
        bloque_tool = _bloque_tool_use(
            "tool-001",
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "08:00", "dia": "lunes"},
        )
        cliente = _mock_client(
            _respuesta_tool_use(bloque_tool),
            _respuesta_texto("El viaje tarda unos 35 minutos."),
        )
        agente = VialAIAgent(client=cliente)
        resultado = agente.run("¿Cuánto tarda de Zócalo a Polanco?")

        assert resultado == "El viaje tarda unos 35 minutos."
        assert cliente.messages.create.call_count == 2

    def test_dos_herramientas_en_secuencia(self):
        """Dos rondas de tool_use antes del end_turn."""
        bloque_1 = _bloque_tool_use(
            "tool-001",
            "verificar_perturbaciones",
            {"fecha": "2024-09-15T20:00:00", "alcaldia": "CUAUHTEMOC"},
        )
        bloque_2 = _bloque_tool_use(
            "tool-002",
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "20:00", "dia": "domingo"},
        )
        cliente = _mock_client(
            _respuesta_tool_use(bloque_1),
            _respuesta_tool_use(bloque_2),
            _respuesta_texto("Con el Grito, espera 50 min de Zócalo a Polanco."),
        )
        agente = VialAIAgent(client=cliente)
        resultado = agente.run("¿Hay tráfico el 15 de sep en el centro?")
        assert resultado == "Con el Grito, espera 50 min de Zócalo a Polanco."
        assert cliente.messages.create.call_count == 3

    def test_dos_herramientas_en_misma_respuesta(self):
        """Dos bloques tool_use en la misma respuesta (parallel tool use)."""
        bloque_a = _bloque_tool_use(
            "tool-A",
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "08:00", "dia": "lunes"},
        )
        bloque_b = _bloque_tool_use(
            "tool-B",
            "consultar_trafico_ahora",
            {"corredor": "Reforma · Ángel"},
        )
        cliente = _mock_client(
            _respuesta_tool_use(bloque_a, bloque_b),
            _respuesta_texto("Tráfico NARANJA; tarda ~40 min."),
        )
        agente = VialAIAgent(client=cliente)
        resultado = agente.run("¿Cómo está Reforma y cuánto tarda a Polanco?")
        assert "NARANJA" in resultado or "40 min" in resultado
        # Segunda llamada debe incluir dos tool_result
        _, kwargs = cliente.messages.create.call_args_list[1]
        tool_results_msg = kwargs["messages"][-1]
        assert len(tool_results_msg["content"]) == 2

    def test_respeta_max_iteraciones(self):
        """Si todas las respuestas son tool_use, se detiene en max_iteraciones."""
        bloque = _bloque_tool_use(
            "tool-001",
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "08:00", "dia": "lunes"},
        )
        # Siempre responde con tool_use (bucle infinito simulado)
        cliente = MagicMock(spec=anthropic.Anthropic)
        cliente.messages.create.return_value = _respuesta_tool_use(bloque)

        agente = VialAIAgent(client=cliente, max_iteraciones=3)
        resultado = agente.run("Pregunta que genera bucle")

        # No debe haber excepción y el call_count es exactamente max_iteraciones
        assert cliente.messages.create.call_count == 3
        assert isinstance(resultado, str)

    def test_tool_result_tiene_tool_use_id_correcto(self):
        """El tool_use_id en el resultado debe coincidir con el del bloque."""
        bloque = _bloque_tool_use(
            "id-especifico-xyz",
            "consultar_trafico_ahora",
            {"corredor": "Reforma · Ángel"},
        )
        cliente = _mock_client(
            _respuesta_tool_use(bloque),
            _respuesta_texto("OK"),
        )
        agente = VialAIAgent(client=cliente)
        agente.run("¿Cómo está Reforma?")

        # El segundo call debe tener un mensaje user con tool_result
        _, kwargs = cliente.messages.create.call_args_list[1]
        tool_result = kwargs["messages"][-1]["content"][0]
        assert tool_result["tool_use_id"] == "id-especifico-xyz"
        assert tool_result["type"] == "tool_result"

    def test_tool_result_content_es_json_valido(self):
        """El contenido del tool_result debe ser JSON deserializable."""
        bloque = _bloque_tool_use(
            "tool-001",
            "verificar_perturbaciones",
            {"fecha": "2024-06-10T10:00:00", "alcaldia": "CUAUHTEMOC"},
        )
        cliente = _mock_client(
            _respuesta_tool_use(bloque),
            _respuesta_texto("Sin perturbaciones activas."),
        )
        agente = VialAIAgent(client=cliente)
        agente.run("¿Hay algo especial hoy?")

        _, kwargs = cliente.messages.create.call_args_list[1]
        content_str = kwargs["messages"][-1]["content"][0]["content"]
        parsed = json.loads(content_str)
        assert isinstance(parsed, dict)
        assert "tipo" in parsed


# ══════════════════════════════════════════════════════════════════════════
# TestEjecutarHerramienta — despacho y serialización
# ══════════════════════════════════════════════════════════════════════════

class TestEjecutarHerramienta:
    @pytest.fixture
    def agente(self) -> VialAIAgent:
        return VialAIAgent(client=MagicMock())

    def test_predecir_devuelve_dict(self, agente):
        resultado = agente._ejecutar_herramienta(
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "08:00", "dia": "lunes"},
        )
        assert isinstance(resultado, dict)
        assert "p50_min" in resultado

    def test_consultar_trafico_devuelve_dict(self, agente):
        resultado = agente._ejecutar_herramienta(
            "consultar_trafico_ahora",
            {"corredor": "Reforma · Ángel"},
        )
        assert isinstance(resultado, dict)
        assert "velocidad_actual_kmh" in resultado

    def test_verificar_perturbaciones_devuelve_dict(self, agente):
        resultado = agente._ejecutar_herramienta(
            "verificar_perturbaciones",
            {"fecha": "2024-06-10T10:00:00", "alcaldia": "CUAUHTEMOC"},
        )
        assert isinstance(resultado, dict)
        assert "tipo" in resultado

    def test_herramienta_desconocida_devuelve_error(self, agente):
        resultado = agente._ejecutar_herramienta(
            "herramienta_inexistente_xyz",
            {},
        )
        assert "error" in resultado
        assert "herramienta_inexistente_xyz" in resultado["error"].lower() or \
               "desconocida" in resultado["error"].lower()

    def test_resultado_es_serializable_a_json(self, agente):
        resultado = agente._ejecutar_herramienta(
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "10:00", "dia": "martes"},
        )
        # No debe lanzar excepción
        json_str = json.dumps(resultado, ensure_ascii=False, default=str)
        assert isinstance(json_str, str)

    def test_excepcion_en_herramienta_no_propaga(self, agente):
        """Si la función lanza excepción, _ejecutar_herramienta devuelve {"error": ...}."""
        with patch.dict("src.agent.agent._DISPATCH", {"herramienta_rota": lambda: (_ for _ in ()).throw(RuntimeError("fallo"))}):
            resultado = agente._ejecutar_herramienta("herramienta_rota", {})
        assert "error" in resultado

    def test_dispatch_contiene_cuatro_herramientas(self, agente):
        assert len(_DISPATCH) == 4

    def test_dispatch_tiene_claves_correctas(self, agente):
        assert set(_DISPATCH.keys()) == {
            "predecir_tiempo_viaje",
            "consultar_trafico_ahora",
            "verificar_perturbaciones",
            "detectar_eventos_activos",
        }


# ══════════════════════════════════════════════════════════════════════════
# TestExtraerTexto
# ══════════════════════════════════════════════════════════════════════════

class TestExtraerTexto:
    def test_extrae_texto_de_bloque_texto(self):
        response = _respuesta_texto("Hola, soy VialAI.")
        assert VialAIAgent._extraer_texto(response) == "Hola, soy VialAI."

    def test_devuelve_vacio_si_no_hay_bloque_texto(self):
        response = MagicMock()
        bloque = MagicMock()
        del bloque.text  # sin atributo text
        response.content = [bloque]
        assert VialAIAgent._extraer_texto(response) == ""

    def test_devuelve_primer_bloque_de_texto(self):
        """Con múltiples bloques de texto, devuelve el primero."""
        response = MagicMock()
        b1 = MagicMock(); b1.type = "text"; b1.text = "Primero"
        b2 = MagicMock(); b2.type = "text"; b2.text = "Segundo"
        response.content = [b1, b2]
        assert VialAIAgent._extraer_texto(response) == "Primero"

    def test_ignora_bloques_tool_use_sin_texto(self):
        response = _respuesta_tool_use(
            _bloque_tool_use("id", "predecir_tiempo_viaje", {})
        )
        # El bloque tiene type=="tool_use", no "text" → cadena vacía
        assert VialAIAgent._extraer_texto(response) == ""

    def test_extrae_texto_cuando_hay_mix_de_bloques(self):
        """Bloque tool_use seguido de bloque texto → devuelve el texto."""
        response = MagicMock()
        b_tool = _bloque_tool_use("id", "predecir_tiempo_viaje", {})
        del b_tool.text  # sin texto
        b_text = _bloque_texto("Resultado final.")
        response.content = [b_tool, b_text]
        assert VialAIAgent._extraer_texto(response) == "Resultado final."


# ══════════════════════════════════════════════════════════════════════════
# TestProcesarToolUse — construcción del contexto
# ══════════════════════════════════════════════════════════════════════════

class TestProcesarToolUse:
    @pytest.fixture
    def agente(self) -> VialAIAgent:
        return VialAIAgent(client=MagicMock())

    def test_anade_mensaje_asistente(self, agente):
        messages_ini = [{"role": "user", "content": "Pregunta"}]
        bloque = _bloque_tool_use("t1", "consultar_trafico_ahora", {"corredor": "Reforma · Ángel"})
        response = _respuesta_tool_use(bloque)

        messages_out = agente._procesar_tool_use(messages_ini, response)

        assert messages_out[1]["role"] == "assistant"
        assert messages_out[1]["content"] is response.content

    def test_anade_mensaje_usuario_con_tool_result(self, agente):
        messages_ini = [{"role": "user", "content": "Pregunta"}]
        bloque = _bloque_tool_use("t1", "consultar_trafico_ahora", {"corredor": "Reforma · Ángel"})
        response = _respuesta_tool_use(bloque)

        messages_out = agente._procesar_tool_use(messages_ini, response)

        msg_resultado = messages_out[2]
        assert msg_resultado["role"] == "user"
        assert msg_resultado["content"][0]["type"] == "tool_result"

    def test_no_muta_messages_original(self, agente):
        messages_ini = [{"role": "user", "content": "Pregunta"}]
        bloque = _bloque_tool_use("t1", "verificar_perturbaciones",
                                  {"fecha": "2024-06-10T10:00:00", "alcaldia": "CUAUHTEMOC"})
        response = _respuesta_tool_use(bloque)

        agente._procesar_tool_use(messages_ini, response)

        # La lista original no debe haber sido modificada
        assert len(messages_ini) == 1

    def test_longitud_final_de_messages(self, agente):
        """messages inicial (1) + asistente (1) + resultados (1) = 3."""
        messages_ini = [{"role": "user", "content": "Pregunta"}]
        bloque = _bloque_tool_use("t1", "consultar_trafico_ahora", {"corredor": "Zócalo"})
        response = _respuesta_tool_use(bloque)

        messages_out = agente._procesar_tool_use(messages_ini, response)
        assert len(messages_out) == 3

    def test_ignora_bloques_no_tool_use(self, agente):
        """Si hay bloques de texto junto con tool_use, solo procesa los tool_use."""
        messages_ini = [{"role": "user", "content": "Pregunta"}]
        bloque_texto = _bloque_texto("Texto intermedio")
        bloque_tool = _bloque_tool_use("t1", "consultar_trafico_ahora", {"corredor": "Zócalo"})
        response = _respuesta_tool_use(bloque_texto, bloque_tool)

        messages_out = agente._procesar_tool_use(messages_ini, response)
        # Solo un tool_result (el del bloque_tool)
        tool_results = messages_out[-1]["content"]
        assert len(tool_results) == 1
        assert tool_results[0]["tool_use_id"] == "t1"


# ══════════════════════════════════════════════════════════════════════════
# TestFallbackErrores — manejo de excepciones de API
# ══════════════════════════════════════════════════════════════════════════

class TestFallbackErrores:
    """Verifica que cada excepción de Anthropic produce un mensaje de fallback en español."""

    def _agente_con_error(self, excepcion) -> VialAIAgent:
        cliente = MagicMock(spec=anthropic.Anthropic)
        cliente.messages.create.side_effect = excepcion
        return VialAIAgent(client=cliente)

    def test_authentication_error_devuelve_fallback(self):
        exc = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(),
            body={},
        )
        agente = self._agente_con_error(exc)
        resultado = agente.run("¿Hola?")
        assert isinstance(resultado, str)
        assert len(resultado) > 0
        # El mensaje debe estar en español y no contener traceback
        assert "clave" in resultado.lower() or "api" in resultado.lower() or "conectar" in resultado.lower()

    def test_rate_limit_error_devuelve_fallback(self):
        exc = anthropic.RateLimitError(
            message="rate limit exceeded",
            response=MagicMock(),
            body={},
        )
        agente = self._agente_con_error(exc)
        resultado = agente.run("¿Hola?")
        assert isinstance(resultado, str)
        assert "demanda" in resultado.lower() or "intenta" in resultado.lower()

    def test_api_connection_error_devuelve_fallback(self):
        exc = anthropic.APIConnectionError(request=MagicMock())
        agente = self._agente_con_error(exc)
        resultado = agente.run("¿Hola?")
        assert isinstance(resultado, str)
        assert "conexión" in resultado.lower() or "conectar" in resultado.lower()

    def test_api_status_error_devuelve_fallback(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        exc = anthropic.APIStatusError(
            message="internal server error",
            response=mock_response,
            body={},
        )
        agente = self._agente_con_error(exc)
        resultado = agente.run("¿Hola?")
        assert isinstance(resultado, str)
        assert "error" in resultado.lower()

    def test_excepcion_generica_devuelve_fallback(self):
        agente = self._agente_con_error(RuntimeError("error inesperado"))
        resultado = agente.run("¿Hola?")
        assert isinstance(resultado, str)
        assert len(resultado) > 0

    def test_fallback_no_lanza_excepcion(self):
        """El método run() nunca debe propagar excepciones al consumidor."""
        agente = self._agente_con_error(Exception("cualquier error"))
        # No debe lanzar excepción
        resultado = agente.run("¿Hola?")
        assert isinstance(resultado, str)


# ══════════════════════════════════════════════════════════════════════════
# TestIntegracionHerramientas — ejecución real de herramientas (sin mocks de tools)
# ══════════════════════════════════════════════════════════════════════════

class TestIntegracionHerramientas:
    """
    Tests de integración que ejecutan las herramientas reales (con sus propios
    fallbacks) y verifican que el agente maneja correctamente los resultados.
    """

    def test_tool_result_prediccion_viaje_tiene_campos_requeridos(self):
        agente = VialAIAgent(client=MagicMock())
        resultado = agente._ejecutar_herramienta(
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Santa Fe", "hora": "08:00", "dia": "lunes"},
        )
        for campo in ("origen", "destino", "p10_min", "p50_min", "p90_min", "nivel_alerta", "resumen"):
            assert campo in resultado, f"Campo '{campo}' no encontrado en resultado"

    def test_tool_result_trafico_tiene_campos_requeridos(self):
        agente = VialAIAgent(client=MagicMock())
        resultado = agente._ejecutar_herramienta(
            "consultar_trafico_ahora",
            {"corredor": "Reforma · Ángel"},
        )
        for campo in ("velocidad_actual_kmh", "velocidad_libre_kmh", "confianza", "ratio_flujo"):
            assert campo in resultado, f"Campo '{campo}' no encontrado en resultado"

    def test_tool_result_perturbaciones_tiene_campos_requeridos(self):
        agente = VialAIAgent(client=MagicMock())
        resultado = agente._ejecutar_herramienta(
            "verificar_perturbaciones",
            {"fecha": "2024-06-10T10:00:00", "alcaldia": "CUAUHTEMOC"},
        )
        for campo in ("tipo", "descripcion", "factor"):
            assert campo in resultado, f"Campo '{campo}' no encontrado en resultado"

    def test_run_completo_con_tool_use_real(self):
        """
        Simula un ciclo completo: el mock del API solicita predecir_tiempo_viaje,
        el agente la ejecuta con los parámetros reales y devuelve la respuesta final.
        """
        bloque = _bloque_tool_use(
            "t-real",
            "predecir_tiempo_viaje",
            {"origen": "Zócalo", "destino": "Polanco", "hora": "08:00", "dia": "lunes"},
        )
        cliente = _mock_client(
            _respuesta_tool_use(bloque),
            _respuesta_texto("El viaje toma aproximadamente 35 minutos."),
        )
        agente = VialAIAgent(client=cliente)
        resultado = agente.run("¿Cuánto tarda de Zócalo a Polanco?")

        assert resultado == "El viaje toma aproximadamente 35 minutos."
        # Verificar que el tool_result enviado a la segunda llamada tiene datos reales
        _, kwargs = cliente.messages.create.call_args_list[1]
        content_str = kwargs["messages"][-1]["content"][0]["content"]
        datos = json.loads(content_str)
        assert datos["p50_min"] > 0
