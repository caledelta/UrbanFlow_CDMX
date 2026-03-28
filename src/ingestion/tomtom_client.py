"""
Cliente para la Traffic Flow Segment Data API de TomTom.

Obtiene velocidades en tiempo real por segmento vial en la ZMVM.
Documentación oficial: https://developer.tomtom.com/traffic-api/documentation/traffic-flow/flow-segment-data

Endpoint utilizado
------------------
GET /traffic/services/4/flowSegmentData/absolute/{zoom}/json
    ?point={lat},{lon}&unit=KMPH&key={api_key}

Respuesta relevante
-------------------
{
  "flowSegmentData": {
    "frc":                 "FRC2",       # Functional Road Class
    "currentSpeed":        32,           # km/h velocidad actual
    "freeFlowSpeed":       60,           # km/h velocidad libre
    "currentTravelTime":   187,          # segundos tiempo actual
    "freeFlowTravelTime":  100,          # segundos tiempo libre
    "confidence":          0.85,         # [0,1] confianza del dato
    "roadClosure":         false,
    "coordinates": { "coordinate": [{...}] }
  }
}
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any

import pandas as pd
import requests
from pydantic import ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# Importación diferida para evitar ciclos si otros módulos importan este
try:
    from src.models.schemas import RespuestaTomTom as _RespuestaTomTom
    _SCHEMAS_OK = True
except ImportError:
    _SCHEMAS_OK = False

# ──────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────

BASE_URL     = "https://api.tomtom.com/traffic/services/4"
API_VERSION  = 4
UNIDAD       = "KMPH"
ZOOM_DEFAULT = 14          # resolución vial urbana (arteriales y calles)

# Bounding box de la ZMVM (WGS84)
ZMVM_BBOX = {
    "lat_min": 19.05,
    "lat_max": 19.85,
    "lon_min": -99.45,
    "lon_max": -98.85,
}

# Categorías de vialidad según Functional Road Class de TomTom
FUNCTIONAL_ROAD_CLASS = {
    "FRC0": "Autopista / Carretera federal",
    "FRC1": "Vía rápida principal",
    "FRC2": "Vía rápida secundaria",
    "FRC3": "Avenida primaria",
    "FRC4": "Avenida secundaria",
    "FRC5": "Calle local",
    "FRC6": "Calle sin salida / privada",
    "FRC7": "Vereda / Peatonal",
}


# ──────────────────────────────────────────────────────────────────────
# Estructura de datos
# ──────────────────────────────────────────────────────────────────────

@dataclass
class SegmentoVial:
    """
    Datos de tráfico en tiempo real para un punto/segmento vial.

    Atributos
    ---------
    latitud : float
        Latitud del punto consultado (WGS84).
    longitud : float
        Longitud del punto consultado (WGS84).
    velocidad_actual_kmh : float
        Velocidad actual observada en el segmento (km/h).
    velocidad_libre_kmh : float
        Velocidad en condiciones de flujo libre (km/h). Referencia del límite.
    tiempo_viaje_actual_s : int
        Tiempo de viaje actual a través del segmento (segundos).
    tiempo_viaje_libre_s : int
        Tiempo de viaje en flujo libre (segundos).
    confianza : float
        Confianza del dato: 1.0 = GPS en vivo, 0.0 = estimado por modelo.
    clase_vial : str
        Functional Road Class de TomTom (FRC0–FRC7).
    cierre_vial : bool
        ``True`` si hay cierre total registrado en el segmento.
    ratio_congestion : float
        ``velocidad_actual / velocidad_libre``. Valores < 0.5 indican
        congestión severa.
    timestamp_utc : str
        Marca de tiempo ISO 8601 de la consulta (UTC).
    """
    latitud:               float
    longitud:              float
    velocidad_actual_kmh:  float
    velocidad_libre_kmh:   float
    tiempo_viaje_actual_s: int
    tiempo_viaje_libre_s:  int
    confianza:             float
    clase_vial:            str
    cierre_vial:           bool
    ratio_congestion:      float
    timestamp_utc:         str

    def a_dict(self) -> dict[str, Any]:
        """Convierte el segmento a diccionario plano."""
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Excepciones personalizadas
# ──────────────────────────────────────────────────────────────────────

class TomTomAPIError(Exception):
    """Error genérico de la API de TomTom."""


class TomTomAuthError(TomTomAPIError):
    """API key inválida o sin permisos (HTTP 401/403)."""


class TomTomRateLimitError(TomTomAPIError):
    """Límite de peticiones superado (HTTP 429)."""


class TomTomNotFoundError(TomTomAPIError):
    """No se encontró segmento vial para las coordenadas indicadas (HTTP 404)."""


# ──────────────────────────────────────────────────────────────────────
# Cliente principal
# ──────────────────────────────────────────────────────────────────────

class TomTomTrafficClient:
    """
    Cliente para la Traffic Flow Segment Data API de TomTom.

    Consulta velocidades en tiempo real en puntos de la red vial de la ZMVM
    y devuelve los resultados como ``SegmentoVial`` o ``pd.DataFrame``.

    Parámetros
    ----------
    api_key : str
        Clave de autenticación de TomTom Developer Portal.
    zoom : int, opcional
        Nivel de detalle del segmento (10–18). Valores más altos devuelven
        segmentos más cortos. Por defecto 14 (arteriales urbanas).
    timeout : int, opcional
        Tiempo máximo de espera por petición HTTP en segundos. Por defecto 10.
    max_reintentos : int, opcional
        Número máximo de reintentos ante errores transitorios. Por defecto 3.
    pausa_entre_lotes : float, opcional
        Segundos de espera entre peticiones consecutivas en un lote para
        respetar el rate limit de TomTom. Por defecto 0.2.
    session : requests.Session o None, opcional
        Sesión HTTP reutilizable. Si es ``None`` se crea una nueva.
        Útil para inyectar mocks en tests.

    Raises
    ------
    ValueError
        Si ``api_key`` está vacía o ``zoom`` está fuera del rango [10, 18].

    Ejemplo
    -------
    >>> from src.ingestion.tomtom_client import TomTomTrafficClient
    >>> client = TomTomTrafficClient(api_key="TU_KEY")
    >>> seg = client.obtener_segmento(lat=19.4326, lon=-99.1332)
    >>> print(seg.velocidad_actual_kmh)
    """

    def __init__(
        self,
        api_key:             str,
        zoom:                int   = ZOOM_DEFAULT,
        timeout:             int   = 10,
        max_reintentos:      int   = 3,
        pausa_entre_lotes:   float = 0.2,
        session:             requests.Session | None = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("'api_key' no puede estar vacía.")
        if not (10 <= zoom <= 18):
            raise ValueError(f"'zoom' debe estar en [10, 18], se recibió {zoom}.")
        if timeout <= 0:
            raise ValueError(f"'timeout' debe ser > 0, se recibió {timeout}.")
        if max_reintentos < 0:
            raise ValueError(
                f"'max_reintentos' debe ser >= 0, se recibió {max_reintentos}."
            )

        self._api_key           = api_key
        self.zoom               = zoom
        self.timeout            = timeout
        self.max_reintentos     = max_reintentos
        self.pausa_entre_lotes  = pausa_entre_lotes
        self._session           = session or requests.Session()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def obtener_segmento(self, lat: float, lon: float) -> SegmentoVial:
        """
        Consulta el flujo de tráfico en un punto vial específico.

        Parámetros
        ----------
        lat : float
            Latitud en WGS84 (rango válido ZMVM: 19.05–19.85).
        lon : float
            Longitud en WGS84 (rango válido ZMVM: −99.45–−98.85).

        Devuelve
        --------
        SegmentoVial
            Datos de velocidad y congestión del segmento más cercano.

        Raises
        ------
        TomTomAuthError
            Si la API key es inválida.
        TomTomRateLimitError
            Si se superó el límite de peticiones.
        TomTomNotFoundError
            Si no existe segmento vial en las coordenadas indicadas.
        TomTomAPIError
            Para cualquier otro error de la API.
        """
        _validar_coordenadas(lat, lon)
        datos = self._get_con_reintentos(lat, lon)
        return _parsear_respuesta(datos, lat, lon)

    def obtener_segmentos_lote(
        self,
        coordenadas: list[tuple[float, float]],
    ) -> pd.DataFrame:
        """
        Consulta el flujo de tráfico para una lista de puntos viales.

        Itera sobre las coordenadas con una pausa configurable entre cada
        petición para respetar el rate limit de TomTom.

        Parámetros
        ----------
        coordenadas : list de tuplas (lat, lon)
            Lista de coordenadas WGS84 a consultar.

        Devuelve
        --------
        pd.DataFrame
            Una fila por segmento con todas las columnas de ``SegmentoVial``.
            Las coordenadas con error se omiten (se registra warning en el log).

        Raises
        ------
        ValueError
            Si ``coordenadas`` está vacía.
        """
        if not coordenadas:
            raise ValueError("La lista de coordenadas no puede estar vacía.")

        segmentos = []
        errores   = 0

        for i, (lat, lon) in enumerate(coordenadas):
            try:
                seg = self.obtener_segmento(lat, lon)
                segmentos.append(seg.a_dict())
            except TomTomAPIError as exc:
                logger.warning(
                    "Error en coordenada %d/%d (%.5f, %.5f): %s",
                    i + 1, len(coordenadas), lat, lon, exc,
                )
                errores += 1
            finally:
                if i < len(coordenadas) - 1:
                    time.sleep(self.pausa_entre_lotes)

        if errores:
            logger.info(
                "Lote completado: %d OK, %d errores de %d coordenadas.",
                len(segmentos), errores, len(coordenadas),
            )

        if not segmentos:
            return pd.DataFrame()

        return pd.DataFrame(segmentos)

    # ------------------------------------------------------------------
    # Lógica HTTP con reintentos (privado)
    # ------------------------------------------------------------------

    def _get_con_reintentos(self, lat: float, lon: float) -> dict[str, Any]:
        """
        Realiza la petición HTTP con reintentos automáticos ante errores
        transitorios (red, timeout, HTTP 5xx).

        Errores de autenticación (401/403) y "no encontrado" (404) no
        se reintentan — son errores permanentes del cliente.
        """
        @retry(
            retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
            stop=stop_after_attempt(self.max_reintentos + 1),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _hacer_peticion() -> dict[str, Any]:
            url    = f"{BASE_URL}/flowSegmentData/absolute/{self.zoom}/json"
            params = {
                "point": f"{lat},{lon}",
                "unit":  UNIDAD,
                "key":   self._api_key,
            }

            try:
                resp = self._session.get(url, params=params, timeout=self.timeout)
            except requests.Timeout:
                raise requests.Timeout(
                    f"Timeout ({self.timeout}s) al consultar ({lat}, {lon})."
                )

            _manejar_errores_http(resp, lat, lon)
            return resp.json()

        return _hacer_peticion()


# ──────────────────────────────────────────────────────────────────────
# Funciones auxiliares privadas
# ──────────────────────────────────────────────────────────────────────

def _manejar_errores_http(
    resp: requests.Response,
    lat: float,
    lon: float,
) -> None:
    """Mapea códigos HTTP a excepciones específicas del dominio."""
    if resp.status_code == 200:
        return

    detalle = f"(lat={lat}, lon={lon}) HTTP {resp.status_code}: {resp.text[:200]}"

    if resp.status_code in (401, 403):
        raise TomTomAuthError(f"API key inválida o sin permisos. {detalle}")
    if resp.status_code == 404:
        raise TomTomNotFoundError(
            f"No se encontró segmento vial en las coordenadas. {detalle}"
        )
    if resp.status_code == 429:
        raise TomTomRateLimitError(f"Rate limit superado. {detalle}")
    if resp.status_code >= 500:
        raise TomTomAPIError(f"Error del servidor TomTom. {detalle}")

    raise TomTomAPIError(f"Error inesperado. {detalle}")


def _parsear_respuesta(
    datos: dict[str, Any],
    lat_consulta: float,
    lon_consulta: float,
) -> SegmentoVial:
    """
    Extrae los campos relevantes del JSON de TomTom y construye un SegmentoVial.

    Raises
    ------
    TomTomAPIError
        Si la respuesta no contiene la clave ``flowSegmentData`` esperada.
    """
    fsd = datos.get("flowSegmentData")
    if not fsd:
        raise TomTomAPIError(
            f"Respuesta inesperada de TomTom: falta 'flowSegmentData'. "
            f"Respuesta: {str(datos)[:300]}"
        )

    vel_actual = float(fsd.get("currentSpeed",        0))
    vel_libre  = float(fsd.get("freeFlowSpeed",       1))   # evitar ÷0
    confianza  = float(fsd.get("confidence",          1.0))
    ratio      = round(vel_actual / vel_libre, 4) if vel_libre > 0 else 0.0

    # ── Validación Pydantic (Fase 1 Structured Outputs) ──────────────
    if _SCHEMAS_OK:
        try:
            _RespuestaTomTom(
                velocidad_actual_kmh=vel_actual,
                velocidad_libre_kmh=vel_libre,
                confianza=confianza,
                ratio_flujo=ratio,
            )
        except ValidationError as exc:
            raise TomTomAPIError(
                f"Datos de TomTom fuera de rango esperado: {exc}"
            ) from exc

    return SegmentoVial(
        latitud               = lat_consulta,
        longitud              = lon_consulta,
        velocidad_actual_kmh  = vel_actual,
        velocidad_libre_kmh   = vel_libre,
        tiempo_viaje_actual_s = int(fsd.get("currentTravelTime",  0)),
        tiempo_viaje_libre_s  = int(fsd.get("freeFlowTravelTime", 0)),
        confianza             = confianza,
        clase_vial            = str(fsd.get("frc",                "FRC_DESCONOCIDA")),
        cierre_vial           = bool(fsd.get("roadClosure",       False)),
        ratio_congestion      = ratio,
        timestamp_utc         = pd.Timestamp.utcnow().isoformat(),
    )


def _validar_coordenadas(lat: float, lon: float) -> None:
    """Lanza ValueError si las coordenadas están fuera de la ZMVM."""
    if not (-90 <= lat <= 90):
        raise ValueError(f"Latitud inválida: {lat}. Rango válido: [-90, 90].")
    if not (-180 <= lon <= 180):
        raise ValueError(f"Longitud inválida: {lon}. Rango válido: [-180, 180].")
