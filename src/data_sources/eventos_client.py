"""
Cliente de detección de eventos en cuasi-tiempo-real para la ZMVM.

Consulta fuentes públicas (C5 CDMX, alertas Metro) y devuelve
eventos activos normalizados como EventoDetectado.

Latencia objetivo: < 3 segundos por consulta.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class EventoDetectado:
    """Evento detectado en cuasi-tiempo-real."""

    tipo: str                          # "accidente", "cierre_vial", "manifestacion", etc.
    descripcion: str                   # Texto descriptivo
    latitud: float
    longitud: float
    alcaldia: str
    timestamp: datetime
    fuente: str                        # "c5_cdmx", "metro_cdmx", "proteccion_civil"
    severidad: str = "media"           # "baja", "media", "alta", "critica"
    radio_impacto_km: float = 2.0      # Radio estimado de afectación
    activo: bool = True


class EventosClient:
    """
    Cliente unificado de detección de eventos en la ZMVM.

    Consulta múltiples fuentes y devuelve una lista normalizada
    de EventoDetectado. Implementa caché de corta duración (5 min)
    para evitar llamadas redundantes.
    """

    CKAN_BASE = "https://datos.cdmx.gob.mx/api/3/action/datastore_search"
    C5_RESOURCE_ID = "59d5ede6-7af8-4384-a114-f84ff1b26fe1"

    # Mapeo de tipos de incidente C5 → tipo normalizado
    MAPEO_TIPOS_C5 = {
        "accidente":    "accidente",
        "choque":       "accidente",
        "volcadura":    "accidente",
        "atropellado":  "accidente",
        "caida":        "accidente",
        "lesionado":    "accidente",
        "cierre":       "cierre_vial",
        "manifestacion":"manifestacion",
        "marcha":       "manifestacion",
        "bloqueo":      "manifestacion",
        "inundacion":   "clima_severo",
        "encharcamiento":"clima_severo",
        "derrumbe":     "infraestructura",
        "hundimiento":  "infraestructura",
        "semaforo":     "infraestructura",
        "incendio":     "emergencia",
    }

    def __init__(
        self,
        timeout: int = 5,
        cache_ttl_min: int = 5,
        metro_alerts_url: Optional[str] = None,
    ) -> None:
        self.timeout = timeout
        self.cache_ttl = timedelta(minutes=cache_ttl_min)
        self.metro_alerts_url = metro_alerts_url
        self._cache: List[EventoDetectado] = []
        self._cache_timestamp: Optional[datetime] = None

    def obtener_eventos_activos(
        self,
        lat_centro: Optional[float] = None,
        lon_centro: Optional[float] = None,
        radio_km: float = 15.0,
        horas_atras: int = 6,
    ) -> List[EventoDetectado]:
        """
        Retorna eventos activos en la ZMVM.

        Args:
            lat_centro: Latitud del punto de interés (default: centro CDMX).
            lon_centro: Longitud del punto de interés.
            radio_km: Radio de búsqueda en km.
            horas_atras: Ventana temporal hacia atrás.

        Returns:
            Lista de EventoDetectado ordenados por severidad descendente.
        """
        if self._cache_valido():
            eventos = self._cache
        else:
            eventos = []
            eventos.extend(self._consultar_c5(horas_atras))
            eventos.extend(self._consultar_metro())
            self._cache = eventos
            self._cache_timestamp = datetime.now()

        if lat_centro is not None and lon_centro is not None:
            eventos = [
                e for e in eventos
                if self._distancia_haversine(
                    lat_centro, lon_centro, e.latitud, e.longitud
                ) <= radio_km
            ]

        orden_severidad = {"critica": 0, "alta": 1, "media": 2, "baja": 3}
        eventos.sort(key=lambda e: orden_severidad.get(e.severidad, 4))

        return eventos

    def _cache_valido(self) -> bool:
        if not self._cache_timestamp:
            return False
        return (datetime.now() - self._cache_timestamp) < self.cache_ttl

    def _consultar_c5(self, horas_atras: int) -> List[EventoDetectado]:
        """Consulta la CKAN API del C5 CDMX."""
        eventos: List[EventoDetectado] = []
        try:
            fecha_limite = (
                datetime.now() - timedelta(hours=horas_atras)
            ).strftime("%Y-%m-%d")

            params = {
                "resource_id": self.C5_RESOURCE_ID,
                "limit": 100,
                "sort": "fecha_creacion desc",
                "filters": '{"codigo_cierre":"A"}',
                "q": fecha_limite,
            }

            resp = requests.get(
                self.CKAN_BASE, params=params, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()

            if not data.get("success"):
                logger.warning("C5 API retornó success=false")
                return []

            for record in data.get("result", {}).get("records", []):
                evento = self._parsear_registro_c5(record)
                if evento:
                    eventos.append(evento)

        except requests.RequestException as e:
            logger.warning("Error consultando C5 CDMX: %s", e)
        except (KeyError, ValueError) as e:
            logger.warning("Error parseando respuesta C5: %s", e)

        return eventos

    def _parsear_registro_c5(self, record: dict) -> Optional[EventoDetectado]:
        """Convierte un registro C5 a EventoDetectado."""
        try:
            lat = float(record.get("latitud", 0))
            lon = float(record.get("longitud", 0))

            if not (19.0 <= lat <= 19.8 and -99.5 <= lon <= -98.7):
                return None

            tipo_raw = str(record.get("tipo_evento", "")).lower().strip()
            tipo = self._clasificar_tipo(tipo_raw)
            severidad = self._estimar_severidad(tipo, record)

            fecha_str = record.get("fecha_creacion", "")
            hora_str = record.get("hora_creacion", "00:00:00")
            try:
                timestamp = datetime.strptime(
                    f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                timestamp = datetime.now()

            return EventoDetectado(
                tipo=tipo,
                descripcion=f"{tipo_raw} en {record.get('alcaldia_hechos', 'N/D')}",
                latitud=lat,
                longitud=lon,
                alcaldia=str(record.get("alcaldia_hechos", "N/D")),
                timestamp=timestamp,
                fuente="c5_cdmx",
                severidad=severidad,
                radio_impacto_km=self._estimar_radio(tipo),
            )
        except Exception as e:
            logger.debug("Registro C5 no parseable: %s", e)
            return None

    def _clasificar_tipo(self, tipo_raw: str) -> str:
        """Clasifica el tipo de evento usando el mapeo."""
        for keyword, tipo_norm in self.MAPEO_TIPOS_C5.items():
            if keyword in tipo_raw:
                return tipo_norm
        return "otro"

    def _estimar_severidad(self, tipo: str, record: dict) -> str:
        """Estima severidad basada en tipo y contexto."""
        severidades = {
            "manifestacion":  "alta",
            "cierre_vial":    "alta",
            "clima_severo":   "media",
            "accidente":      "media",
            "infraestructura":"alta",
            "emergencia":     "critica",
        }
        return severidades.get(tipo, "baja")

    def _estimar_radio(self, tipo: str) -> float:
        """Radio de impacto estimado en km."""
        radios = {
            "manifestacion":  3.0,
            "cierre_vial":    2.0,
            "accidente":      1.5,
            "clima_severo":   5.0,
            "infraestructura":3.0,
            "emergencia":     2.0,
        }
        return radios.get(tipo, 2.0)

    def _consultar_metro(self) -> List[EventoDetectado]:
        """Consulta alertas del Metro CDMX (mock si no hay URL configurada)."""
        if not self.metro_alerts_url:
            return []
        try:
            resp = requests.get(self.metro_alerts_url, timeout=self.timeout)
            resp.raise_for_status()
            return []
        except requests.RequestException as e:
            logger.warning("Error consultando Metro CDMX: %s", e)
            return []

    @staticmethod
    def _distancia_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Distancia Haversine en km entre dos puntos."""
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
