"""
Cliente para la API de OpenWeatherMap (OWM).

Obtiene condiciones climáticas históricas y en tiempo real para estaciones
representativas de la ZMVM y calcula el factor de ajuste climático que
modifica las distribuciones de velocidad del motor Monte Carlo.

Endpoints utilizados
--------------------
Clima actual (gratuito):
    GET https://api.openweathermap.org/data/2.5/weather
        ?lat={lat}&lon={lon}&appid={key}&units=metric

Histórico — One Call API 3.0 (1 000 llamadas/día gratis):
    GET https://api.openweathermap.org/data/3.0/onecall/timemachine
        ?lat={lat}&lon={lon}&dt={unix_timestamp}&appid={key}&units=metric

Integración con el modelo estocástico
--------------------------------------
El ``FactorClimatico`` devuelto por ``calcular_factor_congestion()``
contiene un ``factor_multiplicador`` en [1.0, 2.5] que puede aplicarse
a ``VELOCIDAD_PARAMS`` del motor Monte Carlo mediante
``ajustar_velocidades_por_clima()``, reduciendo las velocidades medias
y mínimas proporcionalmente al deterioro de las condiciones viales.

Ejemplo de uso integrado::

    from src.ingestion.weather_client import (
        OpenWeatherMapClient, calcular_factor_congestion,
        ajustar_velocidades_por_clima,
    )
    from src.simulation.monte_carlo import MonteCarloEngine, VELOCIDAD_PARAMS

    cliente = OpenWeatherMapClient(api_key="TU_KEY")
    clima = cliente.obtener_clima_actual(19.4326, -99.1332)
    factor = calcular_factor_congestion(clima)
    params = ajustar_velocidades_por_clima(VELOCIDAD_PARAMS, factor)
    motor = MonteCarloEngine(cadena, velocidad_params=params)
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field, asdict
from typing import Any

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────

BASE_URL_ACTUAL     = "https://api.openweathermap.org/data/2.5/weather"
BASE_URL_HISTORICO  = "https://api.openweathermap.org/data/3.0/onecall/timemachine"

# Estaciones meteorológicas representativas de la ZMVM
ESTACIONES_ZMVM: dict[str, tuple[float, float]] = {
    "centro":       (19.4326, -99.1332),
    "norte":        (19.5332, -99.2010),
    "sur":          (19.2586, -99.1020),
    "oriente":      (19.3589, -99.0594),
    "poniente":     (19.3590, -99.2588),
    "nororiente":   (19.6010, -99.0320),
    "aeropuerto":   (19.4363, -99.0721),
}

# Rangos de precipitación (mm/h) según escala OMM
_LLUVIA_LLOVIZNA   = 2.5
_LLUVIA_MODERADA   = 7.6
_LLUVIA_INTENSA    = 50.0

# Umbrales de visibilidad (metros)
_VIS_MUY_BAJA      = 200
_VIS_BAJA          = 1_000
_VIS_REDUCIDA      = 5_000

# Umbrales de viento (km/h)
_VIENTO_FUERTE     = 40.0
_VIENTO_MUY_FUERTE = 60.0

# Rangos de códigos de condición OWM que afectan el tráfico
_CODIGOS_TORMENTA   = range(200, 233)
_CODIGOS_LLOVIZNA   = range(300, 322)
_CODIGOS_LLUVIA     = range(500, 532)
_CODIGOS_NIEVE      = range(600, 623)
_CODIGOS_NEBLINA    = range(700, 772)


# ──────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────────────────────────────

@dataclass
class CondicionClimatica:
    """
    Condiciones climáticas observadas en un punto y momento dado.

    Atributos
    ---------
    latitud, longitud : float
        Coordenadas WGS84 del punto de medición.
    temperatura_c : float
        Temperatura del aire en °C.
    sensacion_termica_c : float
        Temperatura percibida («feels like») en °C.
    humedad_pct : int
        Humedad relativa en porcentaje [0, 100].
    presion_hpa : float
        Presión atmosférica en hPa.
    visibilidad_m : int
        Visibilidad horizontal en metros (0–10 000).
    viento_velocidad_kmh : float
        Velocidad del viento en km/h (OWM da m/s; se convierte).
    viento_direccion_grados : int
        Dirección meteorológica del viento en grados [0, 360].
    nubosidad_pct : int
        Cobertura de nubes en porcentaje [0, 100].
    lluvia_1h_mm : float
        Precipitación acumulada en la última hora (mm). 0.0 si no llueve.
    nieve_1h_mm : float
        Precipitación de nieve en la última hora (mm). 0.0 si no nieva.
    codigo_condicion : int
        Código de condición climática OWM (ej. 500 = lluvia ligera).
    descripcion : str
        Descripción en español de la condición (del campo ``description``).
    timestamp_utc : str
        Marca de tiempo ISO 8601 de la medición (UTC).
    nombre_estacion : str
        Nombre de la ciudad / estación devuelto por OWM.
    """
    latitud:                float
    longitud:               float
    temperatura_c:          float
    sensacion_termica_c:    float
    humedad_pct:            int
    presion_hpa:            float
    visibilidad_m:          int
    viento_velocidad_kmh:   float
    viento_direccion_grados: int
    nubosidad_pct:          int
    lluvia_1h_mm:           float
    nieve_1h_mm:            float
    codigo_condicion:       int
    descripcion:            str
    timestamp_utc:          str
    nombre_estacion:        str = ""

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FactorClimatico:
    """
    Factor de ajuste del ratio de congestión basado en condiciones climáticas.

    El ``factor_multiplicador`` escala hacia arriba el tiempo de viaje esperado:
    1.0 = condiciones normales, 2.5 = condiciones extremas (cap máximo).

    El factor se descompone en ``componentes`` individuales para trazabilidad.

    Atributos
    ---------
    factor_multiplicador : float
        Factor compuesto en [1.0, 2.5].  Se aplica dividiendo las velocidades
        medias: ``velocidad_ajustada = velocidad_nominal / factor_multiplicador``.
    componentes : dict
        Contribución individual de cada factor (precipitación, visibilidad,
        viento, condición general).
    descripcion : str
        Resumen legible de las condiciones activas.
    nivel_alerta : str
        "normal" | "moderado" | "severo" | "extremo"
    """
    factor_multiplicador: float
    componentes:          dict[str, float] = field(default_factory=dict)
    descripcion:          str = ""
    nivel_alerta:         str = "normal"

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Excepciones
# ──────────────────────────────────────────────────────────────────────

class OWMAPIError(Exception):
    """Error genérico de la API de OpenWeatherMap."""


class OWMAuthError(OWMAPIError):
    """API key inválida (HTTP 401)."""


class OWMRateLimitError(OWMAPIError):
    """Límite de peticiones superado (HTTP 429)."""


class OWMNotFoundError(OWMAPIError):
    """Coordenadas o timestamp sin datos disponibles (HTTP 404)."""


# ──────────────────────────────────────────────────────────────────────
# Cliente principal
# ──────────────────────────────────────────────────────────────────────

class OpenWeatherMapClient:
    """
    Cliente para los endpoints de clima actual e histórico de OWM.

    Parámetros
    ----------
    api_key : str
        Clave de autenticación de OpenWeatherMap.
    timeout : int, opcional
        Tiempo máximo de espera por petición HTTP en segundos. Por defecto 10.
    max_reintentos : int, opcional
        Reintentos ante errores de red/timeout. Por defecto 3.
    pausa_entre_lotes : float, opcional
        Segundos de espera entre llamadas en un lote. Por defecto 0.25.
    session : requests.Session o None, opcional
        Sesión HTTP inyectable (útil para tests). Si ``None`` se crea una nueva.

    Raises
    ------
    ValueError
        Si ``api_key`` está vacía o los parámetros numéricos son inválidos.
    """

    def __init__(
        self,
        api_key:            str,
        timeout:            int   = 10,
        max_reintentos:     int   = 3,
        pausa_entre_lotes:  float = 0.25,
        session:            requests.Session | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("'api_key' no puede estar vacía.")
        if timeout <= 0:
            raise ValueError(f"'timeout' debe ser > 0, se recibió {timeout}.")
        if max_reintentos < 0:
            raise ValueError(
                f"'max_reintentos' debe ser >= 0, se recibió {max_reintentos}."
            )

        self._api_key          = api_key
        self.timeout           = timeout
        self.max_reintentos    = max_reintentos
        self.pausa_entre_lotes = pausa_entre_lotes
        self._session          = session or requests.Session()

    # ------------------------------------------------------------------
    # API pública — clima actual
    # ------------------------------------------------------------------

    def obtener_clima_actual(self, lat: float, lon: float) -> CondicionClimatica:
        """
        Obtiene las condiciones climáticas actuales en un punto de la ZMVM.

        Parámetros
        ----------
        lat : float
            Latitud WGS84.
        lon : float
            Longitud WGS84.

        Devuelve
        --------
        CondicionClimatica
            Snapshot de las condiciones en el momento de la consulta.

        Raises
        ------
        OWMAuthError, OWMRateLimitError, OWMNotFoundError, OWMAPIError
        """
        _validar_coordenadas(lat, lon)
        datos = self._get_con_reintentos(
            BASE_URL_ACTUAL,
            {"lat": lat, "lon": lon, "units": "metric", "lang": "es"},
        )
        return _parsear_respuesta_actual(datos, lat, lon)

    def obtener_clima_zmvm(self) -> pd.DataFrame:
        """
        Consulta el clima actual en las 7 estaciones representativas de la ZMVM.

        Devuelve
        --------
        pd.DataFrame
            Una fila por estación con todas las columnas de ``CondicionClimatica``,
            más la columna ``estacion`` con el nombre de la zona.
            Las estaciones con error se omiten.
        """
        import time

        registros = []
        estaciones = list(ESTACIONES_ZMVM.items())

        for i, (nombre, (lat, lon)) in enumerate(estaciones):
            try:
                condicion = self.obtener_clima_actual(lat, lon)
                fila = condicion.a_dict()
                fila["estacion"] = nombre
                registros.append(fila)
            except OWMAPIError as exc:
                logger.warning("Error al consultar estación '%s': %s", nombre, exc)
            finally:
                if i < len(estaciones) - 1:
                    time.sleep(self.pausa_entre_lotes)

        return pd.DataFrame(registros) if registros else pd.DataFrame()

    # ------------------------------------------------------------------
    # API pública — clima histórico
    # ------------------------------------------------------------------

    def obtener_clima_historico(
        self,
        lat:       float,
        lon:       float,
        timestamp: int,
    ) -> CondicionClimatica:
        """
        Obtiene las condiciones climáticas en un instante pasado (One Call 3.0).

        Parámetros
        ----------
        lat, lon : float
            Coordenadas WGS84.
        timestamp : int
            Fecha/hora deseada como Unix timestamp UTC. Debe ser anterior
            al momento actual y dentro del histórico disponible en OWM.

        Devuelve
        --------
        CondicionClimatica

        Raises
        ------
        ValueError
            Si ``timestamp`` es <= 0.
        OWMAuthError, OWMRateLimitError, OWMNotFoundError, OWMAPIError
        """
        _validar_coordenadas(lat, lon)
        if timestamp <= 0:
            raise ValueError(
                f"'timestamp' debe ser un Unix timestamp positivo, "
                f"se recibió {timestamp}."
            )

        datos = self._get_con_reintentos(
            BASE_URL_HISTORICO,
            {"lat": lat, "lon": lon, "dt": timestamp, "units": "metric"},
        )
        return _parsear_respuesta_historico(datos, lat, lon)

    # ------------------------------------------------------------------
    # HTTP con reintentos (privado)
    # ------------------------------------------------------------------

    def _get_con_reintentos(
        self,
        url:    str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Realiza la petición GET con reintentos para errores transitorios."""

        params_completos = {**params, "appid": self._api_key}

        @retry(
            retry=retry_if_exception_type(
                (requests.Timeout, requests.ConnectionError)
            ),
            stop=stop_after_attempt(self.max_reintentos + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _hacer_peticion() -> dict[str, Any]:
            try:
                resp = self._session.get(
                    url, params=params_completos, timeout=self.timeout
                )
            except requests.Timeout:
                raise requests.Timeout(
                    f"Timeout ({self.timeout}s) consultando {url}."
                )
            _manejar_errores_http(resp)
            return resp.json()

        return _hacer_peticion()


# ──────────────────────────────────────────────────────────────────────
# Lógica de factor climático — integración con el modelo estocástico
# ──────────────────────────────────────────────────────────────────────

def calcular_factor_congestion(condicion: CondicionClimatica) -> FactorClimatico:
    """
    Calcula el factor multiplicador de congestión a partir de las condiciones
    climáticas observadas.

    El factor compuesto se construye multiplicando los sub-factores
    individuales y se limita a [1.0, 2.5] para evitar predicciones irreales.

    Tabla de factores
    -----------------
    Precipitación:
        - Llovizna (< 2.5 mm/h)        → ×1.20
        - Lluvia moderada (< 7.6 mm/h) → ×1.40
        - Lluvia intensa (< 50 mm/h)   → ×1.70
        - Lluvia torrencial (≥ 50 mm/h)→ ×2.00

    Visibilidad:
        - < 200 m (niebla densa)       → ×1.50
        - < 1 000 m (niebla)           → ×1.30
        - < 5 000 m (neblina)          → ×1.10

    Viento:
        - > 60 km/h (muy fuerte)       → ×1.30
        - > 40 km/h (fuerte)           → ×1.15

    Condición general:
        - Tormenta eléctrica           → mínimo 1.80
        - Nieve                        → mínimo 1.70

    Parámetros
    ----------
    condicion : CondicionClimatica

    Devuelve
    --------
    FactorClimatico
        Factor compuesto con desglose por componente.
    """
    componentes: dict[str, float] = {}

    # ── Precipitación ─────────────────────────────────────────────────
    f_lluvia = 1.0
    mm = condicion.lluvia_1h_mm
    if mm >= _LLUVIA_INTENSA:
        f_lluvia = 2.00
    elif mm >= _LLUVIA_MODERADA:
        f_lluvia = 1.70
    elif mm >= _LLUVIA_LLOVIZNA:
        f_lluvia = 1.40
    elif mm > 0:
        f_lluvia = 1.20
    componentes["precipitacion"] = f_lluvia

    # ── Visibilidad ───────────────────────────────────────────────────
    f_vis = 1.0
    v = condicion.visibilidad_m
    if v < _VIS_MUY_BAJA:
        f_vis = 1.50
    elif v < _VIS_BAJA:
        f_vis = 1.30
    elif v < _VIS_REDUCIDA:
        f_vis = 1.10
    componentes["visibilidad"] = f_vis

    # ── Viento ────────────────────────────────────────────────────────
    f_viento = 1.0
    w = condicion.viento_velocidad_kmh
    if w > _VIENTO_MUY_FUERTE:
        f_viento = 1.30
    elif w > _VIENTO_FUERTE:
        f_viento = 1.15
    componentes["viento"] = f_viento

    # ── Condición general (OWM weather code) ─────────────────────────
    f_codigo = 1.0
    cod = condicion.codigo_condicion
    if cod in _CODIGOS_TORMENTA:
        f_codigo = 1.80
    elif cod in _CODIGOS_NIEVE:
        f_codigo = 1.70
    elif cod in _CODIGOS_NEBLINA:
        f_codigo = max(f_codigo, 1.20)
    componentes["codigo_condicion"] = f_codigo

    # ── Factor compuesto ──────────────────────────────────────────────
    factor_raw = f_lluvia * f_vis * f_viento
    # El código general impone un mínimo (no se multiplica para evitar
    # doble conteo con lluvia/niebla que ya tiene su propio sub-factor)
    factor_final = max(factor_raw, f_codigo)
    factor_final = round(min(factor_final, 2.5), 4)

    # ── Nivel de alerta ───────────────────────────────────────────────
    if factor_final >= 1.8:
        nivel = "extremo"
    elif factor_final >= 1.4:
        nivel = "severo"
    elif factor_final > 1.0:
        nivel = "moderado"
    else:
        nivel = "normal"

    # ── Descripción humana ────────────────────────────────────────────
    partes = []
    if f_lluvia > 1.0:
        partes.append(f"lluvia ({mm:.1f} mm/h)")
    if f_vis > 1.0:
        partes.append(f"visibilidad reducida ({v} m)")
    if f_viento > 1.0:
        partes.append(f"viento fuerte ({w:.1f} km/h)")
    if f_codigo > 1.0:
        partes.append(condicion.descripcion)
    descripcion = "; ".join(partes) if partes else "condiciones normales"

    return FactorClimatico(
        factor_multiplicador = factor_final,
        componentes          = componentes,
        descripcion          = descripcion,
        nivel_alerta         = nivel,
    )


def ajustar_velocidades_por_clima(
    velocidad_params: dict[int, dict[str, float]],
    factor:           FactorClimatico,
) -> dict[int, dict[str, float]]:
    """
    Aplica el factor climático a los parámetros de velocidad del motor Monte Carlo.

    Divide las velocidades ``media`` y ``min`` entre ``factor_multiplicador``
    para reflejar el aumento del tiempo de viaje esperado por condiciones
    climáticas adversas. Los límites superiores (``max``) no se modifican
    ya que las condiciones adversas nunca elevan las velocidades máximas.

    Parámetros
    ----------
    velocidad_params : dict
        Diccionario con la misma estructura que ``VELOCIDAD_PARAMS`` en
        ``src/simulation/monte_carlo.py``.
    factor : FactorClimatico
        Factor calculado por ``calcular_factor_congestion()``.

    Devuelve
    --------
    dict
        Copia profunda de ``velocidad_params`` con velocidades ajustadas.
        La velocidad mínima absoluta es siempre 1.0 km/h.

    Ejemplo
    -------
    >>> from src.simulation.monte_carlo import VELOCIDAD_PARAMS
    >>> factor = FactorClimatico(factor_multiplicador=1.4, ...)
    >>> params = ajustar_velocidades_por_clima(VELOCIDAD_PARAMS, factor)
    >>> params[0]["media"]   # Fluido: 40 / 1.4 ≈ 28.6 km/h
    28.57...
    """
    if not velocidad_params:
        raise ValueError("'velocidad_params' no puede estar vacío.")

    f = factor.factor_multiplicador
    ajustados = copy.deepcopy(velocidad_params)

    for estado_id, params in ajustados.items():
        params["media"] = max(round(params["media"] / f, 4), 1.0)
        params["min"]   = max(round(params["min"]   / f, 4), 1.0)
        # std se reduce proporcionalmente (menos varianza en tráfico severo)
        params["std"]   = max(round(params["std"]   / f, 4), 0.5)

    return ajustados


# ──────────────────────────────────────────────────────────────────────
# Funciones auxiliares privadas
# ──────────────────────────────────────────────────────────────────────

def _manejar_errores_http(resp: requests.Response) -> None:
    """Mapea códigos HTTP de OWM a excepciones del dominio."""
    if resp.status_code == 200:
        return
    detalle = f"HTTP {resp.status_code}: {resp.text[:200]}"
    if resp.status_code == 401:
        raise OWMAuthError(f"API key inválida. {detalle}")
    if resp.status_code == 404:
        raise OWMNotFoundError(f"Sin datos para las coordenadas/timestamp. {detalle}")
    if resp.status_code == 429:
        raise OWMRateLimitError(f"Rate limit superado. {detalle}")
    if resp.status_code >= 500:
        raise OWMAPIError(f"Error del servidor OWM. {detalle}")
    raise OWMAPIError(f"Error inesperado. {detalle}")


def _parsear_respuesta_actual(
    datos: dict[str, Any],
    lat: float,
    lon: float,
) -> CondicionClimatica:
    """Extrae campos del JSON de /data/2.5/weather."""
    if "main" not in datos:
        raise OWMAPIError(
            f"Respuesta inesperada de OWM: falta 'main'. "
            f"Respuesta: {str(datos)[:300]}"
        )

    main    = datos.get("main", {})
    viento  = datos.get("wind", {})
    nubes   = datos.get("clouds", {})
    weather = datos.get("weather", [{}])[0]
    lluvia  = datos.get("rain",  {})
    nieve   = datos.get("snow",  {})

    # OWM devuelve viento en m/s → convertir a km/h
    viento_ms  = float(viento.get("speed", 0.0))
    viento_kmh = round(viento_ms * 3.6, 2)

    return CondicionClimatica(
        latitud                 = lat,
        longitud                = lon,
        temperatura_c           = float(main.get("temp",       0.0)),
        sensacion_termica_c     = float(main.get("feels_like", 0.0)),
        humedad_pct             = int(main.get("humidity",    0)),
        presion_hpa             = float(main.get("pressure",   1013.0)),
        visibilidad_m           = int(datos.get("visibility",  10_000)),
        viento_velocidad_kmh    = viento_kmh,
        viento_direccion_grados = int(viento.get("deg", 0)),
        nubosidad_pct           = int(nubes.get("all", 0)),
        lluvia_1h_mm            = float(lluvia.get("1h", 0.0)),
        nieve_1h_mm             = float(nieve.get("1h",  0.0)),
        codigo_condicion        = int(weather.get("id",          800)),
        descripcion             = str(weather.get("description", "despejado")),
        timestamp_utc           = pd.Timestamp(
            datos.get("dt", 0), unit="s", tz="UTC"
        ).isoformat(),
        nombre_estacion         = str(datos.get("name", "")),
    )


def _parsear_respuesta_historico(
    datos: dict[str, Any],
    lat: float,
    lon: float,
) -> CondicionClimatica:
    """Extrae campos del JSON de One Call 3.0 /timemachine."""
    data_list = datos.get("data", [])
    if not data_list:
        raise OWMAPIError(
            f"Respuesta histórica de OWM sin campo 'data'. "
            f"Respuesta: {str(datos)[:300]}"
        )

    entrada = data_list[0]
    weather = entrada.get("weather", [{}])[0]
    lluvia  = entrada.get("rain",  {})
    nieve   = entrada.get("snow",  {})

    viento_ms  = float(entrada.get("wind_speed", 0.0))
    viento_kmh = round(viento_ms * 3.6, 2)

    return CondicionClimatica(
        latitud                 = lat,
        longitud                = lon,
        temperatura_c           = float(entrada.get("temp",       0.0)),
        sensacion_termica_c     = float(entrada.get("feels_like", 0.0)),
        humedad_pct             = int(entrada.get("humidity",    0)),
        presion_hpa             = float(entrada.get("pressure",   1013.0)),
        visibilidad_m           = int(entrada.get("visibility",   10_000)),
        viento_velocidad_kmh    = viento_kmh,
        viento_direccion_grados = int(entrada.get("wind_deg", 0)),
        nubosidad_pct           = int(entrada.get("clouds",   0)),
        lluvia_1h_mm            = float(lluvia.get("1h", 0.0)),
        nieve_1h_mm             = float(nieve.get("1h",  0.0)),
        codigo_condicion        = int(weather.get("id",          800)),
        descripcion             = str(weather.get("description", "despejado")),
        timestamp_utc           = pd.Timestamp(
            entrada.get("dt", 0), unit="s", tz="UTC"
        ).isoformat(),
        nombre_estacion         = "",
    )


def _validar_coordenadas(lat: float, lon: float) -> None:
    """Lanza ValueError si las coordenadas están fuera de rango global."""
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitud inválida: {lat}. Rango válido: [-90, 90].")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitud inválida: {lon}. Rango válido: [-180, 180].")
