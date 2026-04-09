"""
src/agent/agent.py — Agente conversacional VialAI.

Fase 3 de la arquitectura UrbanFlow CDMX: convierte lenguaje natural en llamadas
a las herramientas del motor Monte Carlo y la API de TomTom, usando la
Anthropic API (claude-sonnet-4-5) con Function Calling.

Loop de tool_use
----------------
1. Se construye el contexto: historial previo + nuevo mensaje del usuario.
2. Se llama a ``client.messages.create()`` con el system prompt y las herramientas.
3. Si ``stop_reason == "tool_use"``: se ejecuta cada herramienta solicitada,
   se añade el resultado al contexto y se repite desde el paso 2.
4. Si ``stop_reason == "end_turn"`` (o se alcanza MAX_ITERACIONES): se devuelve
   el primer bloque de texto de la respuesta.

Fallbacks
---------
Cada excepción de la Anthropic API se captura en ``run()`` y devuelve un
mensaje de error en español sin propagar la excepción al consumidor.

Uso rápido
----------
>>> from src.agent.agent import VialAIAgent
>>> agente = VialAIAgent()
>>> respuesta = agente.run("¿Cuánto tarda de Zócalo a Polanco a las 8am el lunes?")
>>> print(respuesta)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import (
    consultar_trafico_ahora,
    get_tools_schema,
    predecir_tiempo_viaje,
    verificar_perturbaciones,
)

# Ruta absoluta al .env para que funcione independientemente del cwd
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError(
        f"ANTHROPIC_API_KEY no encontrada. Verificado en: {ENV_PATH}. "
        f"Existe archivo: {ENV_PATH.exists()}"
    )

logger = logging.getLogger(__name__)

MODEL: str = "claude-sonnet-4-5"
MAX_TOKENS: int = 4_096
MAX_ITERACIONES: int = 10  # Límite del loop para evitar bucles infinitos

# Tabla de despacho: nombre de herramienta → función Python
_DISPATCH: dict[str, Any] = {
    "predecir_tiempo_viaje":   predecir_tiempo_viaje,
    "consultar_trafico_ahora": consultar_trafico_ahora,
    "verificar_perturbaciones": verificar_perturbaciones,
}


# ═══════════════════════════════════════════════════════════════════════════
# Clase VialAIAgent
# ═══════════════════════════════════════════════════════════════════════════

class VialAIAgent:
    """
    Agente conversacional de movilidad urbana para la ZMVM.

    Usa la Anthropic API con Function Calling para convertir preguntas en
    lenguaje natural en llamadas a las tres herramientas del motor UrbanFlow:
    predicción Monte Carlo, tráfico en tiempo real (TomTom) y perturbaciones
    contextuales.

    Parámetros
    ----------
    api_key : str o None
        Clave de la Anthropic API. Si es ``None``, se lee de la variable de
        entorno ``ANTHROPIC_API_KEY`` (vía ``.env``).
    model : str
        Identificador del modelo Anthropic. Por defecto: ``"claude-sonnet-4-5"``.
    max_tokens : int
        Tokens máximos en la respuesta del modelo. Por defecto: 4 096.
    max_iteraciones : int
        Rondas máximas del loop de tool_use antes de abortar. Por defecto: 10.
    client : anthropic.Anthropic o None
        Cliente Anthropic ya instanciado. Útil para inyección en tests;
        si es ``None`` se crea uno nuevo con ``api_key``.

    Ejemplo
    -------
    >>> agente = VialAIAgent()
    >>> print(agente.run("¿Hay tráfico en Reforma ahorita?"))
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MODEL,
        max_tokens: int = MAX_TOKENS,
        max_iteraciones: int = MAX_ITERACIONES,
        client: anthropic.Anthropic | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")
        self.model = model
        self.max_tokens = max_tokens
        self.max_iteraciones = max_iteraciones
        self._client: anthropic.Anthropic = client or anthropic.Anthropic(
            api_key=self._api_key
        )
        self._tools: list[dict[str, Any]] = get_tools_schema()

    # ──────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────

    def run(
        self,
        mensaje: str,
        historial: list[dict[str, Any]] | None = None,
    ) -> str:
        """
        Procesa un mensaje del usuario y devuelve la respuesta del agente.

        Construye el contexto de conversación a partir de ``historial`` más
        el nuevo mensaje, ejecuta el loop de tool_use con la Anthropic API y
        devuelve la respuesta en texto plano.

        Parámetros
        ----------
        mensaje : str
            Mensaje del usuario en lenguaje natural.
        historial : list[dict] o None
            Mensajes previos de la conversación en formato Anthropic::

                [
                    {"role": "user",      "content": "..."},
                    {"role": "assistant", "content": "..."},
                    ...
                ]

            ``None`` equivale a conversación nueva sin historial.

        Devuelve
        --------
        str
            Respuesta en texto del agente. En caso de error de API devuelve
            un mensaje de fallback en español sin propagar la excepción.
        """
        messages = list(historial or []) + [{"role": "user", "content": mensaje}]

        try:
            return self._loop_tool_use(messages)

        except (anthropic.AuthenticationError, TypeError) as exc:
            logger.error("ANTHROPIC_API_KEY inválida o no configurada: %s", exc)
            return (
                "No puedo conectarme al servicio en este momento. "
                "Verifica que la clave de API esté configurada correctamente."
            )
        except anthropic.RateLimitError:
            logger.warning("Rate limit de Anthropic API alcanzado.")
            return (
                "El servicio está experimentando alta demanda en este momento. "
                "Por favor, intenta de nuevo en unos segundos."
            )
        except anthropic.APIConnectionError as exc:
            logger.error("Error de conexión con Anthropic API: %s", exc)
            return (
                "No se pudo establecer conexión con el servicio. "
                "Verifica tu conexión a internet e intenta de nuevo."
            )
        except anthropic.APIStatusError as exc:
            logger.error("Error de API (status %s): %s", exc.status_code, exc.message)
            return (
                "El servicio devolvió un error inesperado. "
                "Si el problema persiste, contacta al soporte de UrbanFlow CDMX."
            )
        except Exception as exc:
            logger.error("Error inesperado en VialAIAgent.run: %s", exc, exc_info=True)
            return (
                "Ocurrió un error inesperado al procesar tu consulta. "
                "Por favor, intenta de nuevo."
            )

    # ──────────────────────────────────────────────────────────────────────
    # Loop de tool_use
    # ──────────────────────────────────────────────────────────────────────

    def _loop_tool_use(self, messages: list[dict[str, Any]]) -> str:
        """
        Ejecuta el loop de tool_use hasta obtener ``stop_reason == "end_turn"``.

        Parámetros
        ----------
        messages : list[dict]
            Contexto inicial (historial + mensaje del usuario).

        Devuelve
        --------
        str
            Texto de la respuesta final del modelo.

        Raises
        ------
        Cualquier excepción de ``anthropic`` (capturada por ``run()``).
        """
        response: Any = None

        for iteracion in range(self.max_iteraciones):
            logger.debug(
                "Loop tool_use — iteración %d/%d", iteracion + 1, self.max_iteraciones
            )

            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=self._tools,
                messages=messages,
            )

            if response.stop_reason == "tool_use":
                messages = self._procesar_tool_use(messages, response)
            else:
                return self._extraer_texto(response)

        # Agotadas las iteraciones: devolvemos lo que haya en la última respuesta
        logger.warning(
            "Se alcanzó el límite de iteraciones (%d) sin end_turn.",
            self.max_iteraciones,
        )
        return self._extraer_texto(response) if response is not None else ""

    def _procesar_tool_use(
        self,
        messages: list[dict[str, Any]],
        response: Any,
    ) -> list[dict[str, Any]]:
        """
        Ejecuta las herramientas solicitadas por el modelo y actualiza messages.

        Añade el mensaje del asistente (con bloques ``tool_use``) y la respuesta
        del usuario (con bloques ``tool_result``) al contexto de la conversación.

        Parámetros
        ----------
        messages : list[dict]
            Contexto acumulado hasta la iteración actual.
        response : anthropic.types.Message
            Respuesta con ``stop_reason == "tool_use"``.

        Devuelve
        --------
        list[dict]
            Contexto actualizado listo para la siguiente iteración.
        """
        # El asistente "habló": añadimos su mensaje con los bloques tool_use
        messages = messages + [{"role": "assistant", "content": response.content}]

        # Ejecutamos cada herramienta y construimos los tool_result
        resultados: list[dict[str, Any]] = []
        for bloque in response.content:
            if bloque.type != "tool_use":
                continue

            logger.debug(
                "Ejecutando herramienta '%s' con args: %s", bloque.name, bloque.input
            )
            resultado = self._ejecutar_herramienta(bloque.name, bloque.input)

            resultados.append(
                {
                    "type": "tool_result",
                    "tool_use_id": bloque.id,
                    "content": json.dumps(resultado, ensure_ascii=False, default=str),
                }
            )

        # Los resultados se envían como siguiente turno del usuario
        messages = messages + [{"role": "user", "content": resultados}]
        return messages

    def _ejecutar_herramienta(
        self,
        nombre: str,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Despacha la llamada a la herramienta y serializa el resultado.

        Los modelos Pydantic se convierten a ``dict`` con ``model_dump()``.
        Los ``dict`` se devuelven directamente. Las excepciones se capturan y
        devuelven como ``{"error": "..."}`` para no romper el loop del agente.

        Parámetros
        ----------
        nombre : str
            Nombre de la herramienta (clave en ``_DISPATCH``).
        args : dict
            Argumentos según el ``input_schema`` de la herramienta.

        Devuelve
        --------
        dict
            Resultado serializable a JSON.
        """
        func = _DISPATCH.get(nombre)
        if func is None:
            logger.error("Herramienta desconocida solicitada por el modelo: '%s'", nombre)
            return {"error": f"Herramienta desconocida: '{nombre}'"}

        try:
            resultado = func(**args)
            # Pydantic BaseModel → dict
            if hasattr(resultado, "model_dump"):
                return resultado.model_dump()
            # dict (verificar_perturbaciones) → devolver tal cual
            if isinstance(resultado, dict):
                return resultado
            # Fallback para cualquier otro tipo
            return {"resultado": str(resultado)}
        except Exception as exc:
            logger.error("Error ejecutando herramienta '%s': %s", nombre, exc)
            return {"error": str(exc)}

    # ──────────────────────────────────────────────────────────────────────
    # Utilidades estáticas
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extraer_texto(response: Any) -> str:
        """
        Extrae el primer bloque de texto de la respuesta del modelo.

        Parámetros
        ----------
        response : anthropic.types.Message
            Respuesta de la API de Anthropic.

        Devuelve
        --------
        str
            Texto del primer bloque de tipo ``"text"``, o cadena vacía.
        """
        for bloque in response.content:
            if getattr(bloque, "type", None) == "text" and hasattr(bloque, "text"):
                return bloque.text
        return ""
