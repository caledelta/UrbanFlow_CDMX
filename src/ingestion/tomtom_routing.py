"""
Cliente para la TomTom Routing API (Calculate Route).

Calcula la ruta real por carretera entre dos puntos, devolviendo
la distancia real (km), el tiempo base sin tráfico (min) y la
geometría de la ruta para dibujar en un mapa Folium.

Endpoint utilizado
------------------
GET /routing/1/calculateRoute/{origin}:{destination}/json
    ?key={API_KEY}&travelMode=car&traffic=false&routeType=fastest

Respuesta relevante
-------------------
{
  "routes": [{
    "summary": {
      "lengthInMeters":    15340,
      "travelTimeInSeconds": 1820
    },
    "legs": [{
      "points": [
        {"latitude": 19.4326, "longitude": -99.1332},
        ...
      ]
    }]
  }]
}

Factor de tortuosidad urbana
----------------------------
Cuando la API no está disponible, se aplica el factor empírico 1.4
sobre la distancia Haversine (línea recta), que en la ZMVM produce
una estimación razonable de la distancia real por carretera.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

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

BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"

# Factor empírico de tortuosidad urbana para la ZMVM.
# La distancia real por carretera es ~1.4× la distancia en línea recta.
FACTOR_TORTUOSIDAD = 1.4

# Velocidad base asumida para el fallback (km/h promedio ZMVM sin tráfico)
VELOCIDAD_BASE_KMPH = 30.0

# Número máximo de puntos de geometría a conservar en la polilínea.
# TomTom puede devolver cientos de puntos; se submuestrea para no
# sobrecargar el mapa Folium.
MAX_WAYPOINTS_GEOMETRIA = 120


# ──────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────────────────────────────

@dataclass
class RutaVial:
    """
    Resultado de una consulta de ruta a la TomTom Routing API.

    Atributos
    ---------
    distancia_km : float
        Distancia real por carretera en kilómetros.
    tiempo_base_min : float
        Tiempo estimado sin tráfico en minutos.
    waypoints : list of (lat, lon)
        Puntos de la geometría de la ruta (submuestreados).
    fuente : str
        ``"tomtom"`` si se obtuvo de la API; ``"haversine_estimada"``
        si se usó el fallback.
    """
    distancia_km:    float
    tiempo_base_min: float
    waypoints:       list[tuple[float, float]] = field(default_factory=list)
    fuente:          str = "tomtom"

    def a_dict(self) -> dict[str, Any]:
        return {
            "distancia_km":    self.distancia_km,
            "tiempo_base_min": self.tiempo_base_min,
            "n_waypoints":     len(self.waypoints),
            "fuente":          self.fuente,
        }


class TomTomRoutingError(Exception):
    """Error al calcular la ruta con TomTom Routing API."""


# ──────────────────────────────────────────────────────────────────────
# Cliente principal
# ──────────────────────────────────────────────────────────────────────

class TomTomRoutingClient:
    """
    Cliente para la TomTom Routing API.

    Parámetros
    ----------
    api_key : str
        Clave de la TomTom Developer API.
    session : requests.Session, opcional
        Sesión HTTP inyectable (útil para tests).
    timeout : int
        Timeout HTTP en segundos (por defecto 10).

    Ejemplo
    -------
    >>> client = TomTomRoutingClient(api_key="TU_KEY")
    >>> ruta = client.calcular_ruta(19.4326, -99.1332, 19.3031, -99.1506)
    >>> print(ruta.distancia_km, ruta.tiempo_base_min)
    """

    def __init__(
        self,
        api_key:  str,
        session:  requests.Session | None = None,
        timeout:  int = 10,
    ) -> None:
        if not api_key:
            raise ValueError("'api_key' no puede estar vacío.")
        self._api_key = api_key
        self._session = session or requests.Session()
        self._timeout = timeout

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def calcular_ruta(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> RutaVial:
        """
        Calcula la ruta real por carretera entre (lat1, lon1) y (lat2, lon2).

        Parámetros
        ----------
        lat1, lon1 : float
            Coordenadas del origen (WGS84).
        lat2, lon2 : float
            Coordenadas del destino (WGS84).

        Devuelve
        --------
        RutaVial
            Distancia real, tiempo base y geometría de la ruta.

        Raises
        ------
        TomTomRoutingError
            Si la API devuelve un error irrecuperable.
        """
        try:
            datos = self._get_con_reintentos(lat1, lon1, lat2, lon2)
            return self._parsear_respuesta(datos)
        except TomTomRoutingError:
            raise
        except Exception as exc:
            raise TomTomRoutingError(
                f"Error inesperado al calcular ruta: {exc}"
            ) from exc

    def calcular_ruta_con_fallback(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
    ) -> RutaVial:
        """
        Calcula la ruta; si la API falla, usa Haversine × FACTOR_TORTUOSIDAD.

        Nunca lanza excepción.
        """
        try:
            return self.calcular_ruta(lat1, lon1, lat2, lon2)
        except Exception as exc:
            logger.warning(
                "TomTom Routing API falló (%s); usando fallback Haversine×%.1f.",
                exc,
                FACTOR_TORTUOSIDAD,
            )
            return _fallback_haversine(lat1, lon1, lat2, lon2)

    # ------------------------------------------------------------------
    # Métodos privados
    # ------------------------------------------------------------------

    def _get_con_reintentos(
        self,
        lat1: float, lon1: float,
        lat2: float, lon2: float,
    ) -> dict:
        """Realiza la petición HTTP con reintentos exponenciales."""

        @retry(
            retry=retry_if_exception_type(requests.ConnectionError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        def _get() -> dict:
            url = (
                f"{BASE_URL}/{lat1},{lon1}:{lat2},{lon2}/json"
            )
            params = {
                "key":          self._api_key,
                "travelMode":   "car",
                "traffic":      "false",
                "routeType":    "fastest",
            }
            resp = self._session.get(url, params=params, timeout=self._timeout)

            if resp.status_code == 400:
                raise TomTomRoutingError(
                    f"Parámetros inválidos (400): {resp.text[:200]}"
                )
            if resp.status_code == 403:
                raise TomTomRoutingError(
                    "API key inválida o sin permisos para Routing API (403)."
                )
            if resp.status_code == 429:
                raise TomTomRoutingError("Límite de tasa excedido (429).")
            resp.raise_for_status()
            return resp.json()

        return _get()

    @staticmethod
    def _parsear_respuesta(data: dict) -> RutaVial:
        """Extrae distancia, tiempo y geometría de la respuesta JSON."""
        routes = data.get("routes", [])
        if not routes:
            raise TomTomRoutingError(
                "La API no devolvió rutas. Verifica las coordenadas."
            )

        summary = routes[0].get("summary", {})
        length_m = summary.get("lengthInMeters", 0)
        travel_s = summary.get("travelTimeInSeconds", 0)

        if length_m <= 0:
            raise TomTomRoutingError(
                "La API devolvió distancia 0. Coordenadas posiblemente iguales."
            )

        distancia_km    = round(length_m / 1000, 2)
        tiempo_base_min = round(travel_s / 60, 1)

        # Geometría: todos los puntos de todos los tramos
        puntos_raw: list[dict] = []
        for leg in routes[0].get("legs", []):
            puntos_raw.extend(leg.get("points", []))

        waypoints = _submuestrear(
            [(p["latitude"], p["longitude"]) for p in puntos_raw],
            max_puntos=MAX_WAYPOINTS_GEOMETRIA,
        )

        logger.debug(
            "Ruta TomTom: %.2f km · %.1f min · %d puntos geométricos",
            distancia_km, tiempo_base_min, len(waypoints),
        )
        return RutaVial(
            distancia_km    = distancia_km,
            tiempo_base_min = tiempo_base_min,
            waypoints       = waypoints,
            fuente          = "tomtom",
        )


# ──────────────────────────────────────────────────────────────────────
# Funciones auxiliares
# ──────────────────────────────────────────────────────────────────────

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia Haversine en km (sin dependencias externas)."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def _fallback_haversine(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> RutaVial:
    """
    Devuelve una ``RutaVial`` estimada via Haversine × FACTOR_TORTUOSIDAD.

    La geometría son 6 puntos interpolados linealmente (sin curvas reales).
    """
    dist_lineal  = _haversine_km(lat1, lon1, lat2, lon2)
    dist_km      = round(dist_lineal * FACTOR_TORTUOSIDAD, 2)
    tiempo_min   = round(dist_km / VELOCIDAD_BASE_KMPH * 60, 1)

    n = 6
    fracs = [i / (n - 1) for i in range(n)]
    waypoints = [
        (lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1))
        for f in fracs
    ]
    return RutaVial(
        distancia_km    = dist_km,
        tiempo_base_min = tiempo_min,
        waypoints       = waypoints,
        fuente          = "haversine_estimada",
    )


def _submuestrear(
    puntos: list[tuple[float, float]],
    max_puntos: int,
) -> list[tuple[float, float]]:
    """
    Reduce la lista de puntos a un máximo de ``max_puntos`` conservando
    el primero, el último y puntos igualmente espaciados entre ellos.
    """
    n = len(puntos)
    if n <= max_puntos:
        return puntos
    indices = set()
    indices.add(0)
    indices.add(n - 1)
    step = (n - 1) / (max_puntos - 1)
    for i in range(1, max_puntos - 1):
        indices.add(round(i * step))
    return [puntos[i] for i in sorted(indices)]
