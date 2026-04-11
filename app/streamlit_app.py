"""
VialAI — Interfaz Streamlit para predicción de tiempos de viaje en la ZMVM.

Arquitectura de la app
----------------------
sidebar  → logo + tagline + rutas frecuentes + selector OD libre + controles
main     → mapa interactivo (clic para fijar A/B) + panel de info del trayecto
           resultados: gauge P50 · banda P10-P90 · semáforo · histograma

Modos de selección de origen-destino
-------------------------------------
1. Autocompletado: selectbox con ~80 puntos conocidos de la ZMVM.
2. Clic en mapa: el usuario hace clic sobre el mapa Folium para fijar
   el marcador A (origen) o B (destino) según el modo activo.
3. Rutas frecuentes: 5 corredores predefinidos de la ZMVM como accesos rápidos.

La app llama al PipelineIntegrador cuando hay API keys configuradas;
si no, usa el modo DEMO con datos precalibrados.
"""

from __future__ import annotations

import base64
import datetime
import math
import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path

# ── Raíz del proyecto en sys.path ───────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ── Variables de entorno (ruta absoluta para que funcione con cualquier cwd) ─
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ── Configuración de página (primera llamada a Streamlit) ────────────────────
st.set_page_config(
    page_title="VialAI — Predicción de tráfico ZMVM",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help":    None,
        "Report a bug": None,
        "About": (
            "### 🚦 VialAI\n"
            "Predicción estocástica de tiempos de viaje en la ZMVM.\n\n"
            "**Motor:** Simulación Monte Carlo + Cadenas de Markov\n\n"
            "**Fuentes:** TomTom Traffic API · OpenWeatherMap · C5 CDMX\n\n"
            "Diplomado en Ciencia de Datos · 2026"
        ),
    },
)

# ── Importaciones del proyecto ───────────────────────────────────────────────
try:
    from src.simulation.markov_chain import MarkovTrafficChain
    from src.simulation.monte_carlo import MonteCarloEngine, ConsultaViaje, VELOCIDAD_PARAMS
    MODULOS_SIMULACION_OK = True
except ImportError:
    MODULOS_SIMULACION_OK = False

try:
    from src.ingestion.tomtom_client import TomTomTrafficClient
    from src.ingestion.weather_client import OpenWeatherMapClient
    from src.ingestion.pipeline import PipelineIntegrador
    MODULOS_PIPELINE_OK = True
except ImportError:
    MODULOS_PIPELINE_OK = False

try:
    from src.ingestion.tomtom_routing import TomTomRoutingClient, RutaVial
    MODULOS_ROUTING_OK = True
except ImportError:
    MODULOS_ROUTING_OK = False

try:
    from src.simulation.evaluador_rutas import (
        evaluar_rutas, generar_explicacion_cambio_ruta, ResultadoRuta,
    )
    MODULOS_EVALUADOR_OK = True
except ImportError:
    MODULOS_EVALUADOR_OK = False

try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False

try:
    from src.agent.agent import VialAIAgent
    VIALAI_OK = True
except ImportError:
    VIALAI_OK = False

try:
    from src.agent.voice_io import transcribir_audio, sintetizar_voz, resumen_para_voz
    VOICE_IO_OK = True
except ImportError:
    VOICE_IO_OK = False


# ════════════════════════════════════════════════════════════════════════════
# UTILIDADES GENERALES
# ════════════════════════════════════════════════════════════════════════════

def safe_get(obj, key, default=None):
    """Accede a atributo o clave de dict de forma segura."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ════════════════════════════════════════════════════════════════════════════
# CONSTANTES DE COLOR
# ════════════════════════════════════════════════════════════════════════════

AZUL_MARINO = "#0C447C"
VERDE       = "#1D9E75"
AMARILLO    = "#F5A623"
ROJO        = "#D0021B"

# Colores por índice de ruta (0=recomendada, 1=alternativa 1, 2=alternativa 2)
COLORES_RUTAS       = {0: VERDE, 1: AMARILLO, 2: "#4A6FA5"}
COLOR_COMPROMETIDA  = ROJO


# ════════════════════════════════════════════════════════════════════════════
# CATÁLOGO DE PUNTOS CONOCIDOS DE LA ZMVM
# ════════════════════════════════════════════════════════════════════════════

OPCION_MAPA = "📍 Elegir en el mapa 📍"

PUNTOS_CDMX: dict[str, tuple[float, float]] = {
    "Zócalo · Plaza de la Constitución":        (19.4326, -99.1332),
    "Ángel de la Independencia":                (19.4270, -99.1676),
    "Monumento a la Revolución":                (19.4385, -99.1573),
    "Castillo de Chapultepec":                  (19.4204, -99.1897),
    "Basílica de Guadalupe":                    (19.4848, -99.1175),
    "Estadio Azteca":                           (19.3031, -99.1506),
    "Palacio de los Deportes":                  (19.4089, -99.0866),
    "Plaza Garibaldi":                          (19.4425, -99.1381),
    "Arena México":                             (19.4281, -99.1470),
    "AICM Terminal 1":                          (19.4363, -99.0721),
    "AICM Terminal 2":                          (19.4345, -99.0785),
    "TAPO · Terminal Oriente":                  (19.4255, -99.1139),
    "Terminal Poniente":                        (19.4019, -99.2050),
    "Terminal Norte":                           (19.4832, -99.1286),
    "Terminal Sur · Tasqueña":                  (19.3704, -99.1380),
    "Reforma · Buenavista":                     (19.4500, -99.1550),
    "Buenavista · Tren Suburbano":              (19.4508, -99.1546),
    "Insurgentes Sur · Perisur":                (19.3280, -99.1700),
    "Insurgentes Norte · Indios Verdes":        (19.4960, -99.1540),
    "Viaducto · Observatorio":                  (19.4010, -99.2010),
    "Periférico Norte · Toreo":                 (19.5080, -99.2350),
    "Cuatro Caminos":                           (19.5250, -99.2100),
    "Los Reyes La Paz":                         (19.3800, -99.0400),
    "Ciudad Universitaria · UNAM":              (19.3318, -99.1873),
    "IPN · Zacatenco":                          (19.5041, -99.1331),
    "UAM Azcapotzalco":                         (19.4876, -99.1879),
    "UAM Iztapalapa":                           (19.3588, -99.0575),
    "Hospital General de México":               (19.4112, -99.1551),
    "IMSS · CMN Siglo XXI":                     (19.3950, -99.1600),
    "Hospital ABC · Observatorio":              (19.4010, -99.2016),
    "Hospital Infantil de México":              (19.4175, -99.1538),
    "Santa Fe · Centro Comercial":              (19.3620, -99.2760),
    "Polanco · Presidente Masaryk":             (19.4318, -99.1949),
    "Perisur · Centro Comercial":               (19.3039, -99.1849),
    "Antara Fashion Hall":                      (19.4820, -99.1969),
    "Parque Delta":                             (19.3940, -99.1554),
    "Bosque de Chapultepec · Entrada":          (19.4207, -99.1965),
    "Parque Bicentenario":                      (19.4808, -99.2091),
    "Parque España · Condesa":                  (19.4190, -99.1700),
    "Colonia Roma Norte":                       (19.4170, -99.1620),
    "Colonia Condesa":                          (19.4120, -99.1769),
    "Colonia Doctores":                         (19.4120, -99.1530),
    "Colonia Narvarte":                         (19.3960, -99.1620),
    "Colonia Del Valle":                        (19.3910, -99.1650),
    "Colonia Lindavista":                       (19.4850, -99.1360),
    "Colonia Tepito":                           (19.4490, -99.1210),
    "Colonia Guerrero":                         (19.4450, -99.1450),
    "Colonia Santa María la Ribera":            (19.4480, -99.1560),
    "Colonia Polanco":                          (19.4300, -99.1950),
    "Colonia Lomas de Chapultepec":             (19.4100, -99.2100),
    "Colonia San Rafael":                       (19.4370, -99.1650),
    "Colonia Iztapalapa · Centro":              (19.3459, -99.0559),
    "Colonia Gustavo A. Madero":                (19.4988, -99.1150),
    "Colonia Venustiano Carranza":              (19.4300, -99.1100),
    "Colonia Azcapotzalco":                     (19.4880, -99.1850),
    "Colonia Iztacalco":                        (19.3950, -99.1050),
    "Colonia Coyoacán · Centro":                (19.3500, -99.1630),
    "Colonia Xochimilco · Embarcadero":         (19.2650, -99.1050),
    "Colonia Tlalpan · Centro":                 (19.2950, -99.1650),
    "Colonia Álvaro Obregón · Centro":          (19.3620, -99.2050),
    "Colonia Cuajimalpa":                       (19.3630, -99.3000),
    "Colonia Tláhuac · Centro":                 (19.2860, -99.0070),
    "Colonia Miguel Hidalgo":                   (19.4100, -99.2000),
    "Colonia Benito Juárez":                    (19.3910, -99.1650),
    "Metro Pantitlán":                          (19.4150, -99.0726),
    "Metro Observatorio":                       (19.4003, -99.2010),
    "Metro Indios Verdes":                      (19.4963, -99.1154),
    "Metro Tasqueña":                           (19.3702, -99.1388),
    "Metro Universidad":                        (19.3272, -99.1736),
    "Metro Cuatro Caminos":                     (19.5070, -99.2175),
    "Metro Balderas":                           (19.4295, -99.1500),
    "Metro Insurgentes":                        (19.4202, -99.1614),
    "Naucalpan · Las Arboledas":                (19.5200, -99.2180),
    "Naucalpan · Centro":                       (19.4760, -99.2390),
    "Tlalnepantla · Centro":                    (19.5390, -99.1977),
    "Ecatepec · Centro":                        (19.6010, -99.0320),
    "Nezahualcóyotl · Ciudad Azteca":           (19.4069, -98.9979),
    "Chimalhuacán · Centro":                    (19.4209, -98.9553),
    "Chalco · Centro":                          (19.2591, -98.8975),
    "Texcoco · Centro":                         (19.5137, -98.8803),
    "La Paz · Centro":                          (19.3950, -99.0700),
    "Tultitlán · Centro":                       (19.6462, -99.1743),
}

_OPCIONES_OD = [OPCION_MAPA] + sorted(PUNTOS_CDMX.keys())


# ════════════════════════════════════════════════════════════════════════════
# CINCO CORREDORES PRINCIPALES
# ════════════════════════════════════════════════════════════════════════════

CORREDORES: dict[str, dict] = {
    "Insurgentes Sur · Del Valle → Indios Verdes": {
        "distancia_km":  22.5,
        "origen_key":    "Insurgentes Sur · Perisur",
        "destino_key":   "Insurgentes Norte · Indios Verdes",
        "lat_clima":     19.4326,
        "lon_clima":     -99.1700,
        "waypoints": [
            (19.3280, -99.1700),
            (19.3590, -99.1680),
            (19.3910, -99.1650),
            (19.4200, -99.1620),
            (19.4500, -99.1580),
            (19.4960, -99.1540),
        ],
        "color_mapa":    AZUL_MARINO,
        "icono":         "🔵",
        "descripcion":   "22.5 km · Eje norte-sur · Pico vespertino 17-19 h",
    },
    "Viaducto · Observatorio → Aeropuerto": {
        "distancia_km":  18.0,
        "origen_key":    "Viaducto · Observatorio",
        "destino_key":   "AICM Terminal 1",
        "lat_clima":     19.3989,
        "lon_clima":     -99.1200,
        "waypoints": [
            (19.4010, -99.2010),
            (19.3989, -99.1700),
            (19.3989, -99.1332),
            (19.3989, -99.1000),
            (19.4363, -99.0721),
        ],
        "color_mapa":    VERDE,
        "icono":         "🟢",
        "descripcion":   "18.0 km · Eje oriente-poniente · Ruta aeropuerto",
    },
    "Reforma · Santa Fe → Buenavista": {
        "distancia_km":  14.5,
        "origen_key":    "Santa Fe · Centro Comercial",
        "destino_key":   "Reforma · Buenavista",
        "lat_clima":     19.4326,
        "lon_clima":     -99.1950,
        "waypoints": [
            (19.3620, -99.2760),
            (19.3950, -99.2500),
            (19.4200, -99.2000),
            (19.4326, -99.1750),
            (19.4500, -99.1550),
        ],
        "color_mapa":    "#8B5CF6",
        "icono":         "🟣",
        "descripcion":   "14.5 km · Paseo de la Reforma · Alto congestionamiento",
    },
    "Periférico Norte · Toreo → Cuatro Caminos": {
        "distancia_km":  12.0,
        "origen_key":    "Periférico Norte · Toreo",
        "destino_key":   "Cuatro Caminos",
        "lat_clima":     19.5100,
        "lon_clima":     -99.2200,
        "waypoints": [
            (19.5080, -99.2350),
            (19.5120, -99.2250),
            (19.5200, -99.2180),
            (19.5250, -99.2100),
        ],
        "color_mapa":    "#F59E0B",
        "icono":         "🟡",
        "descripcion":   "12.0 km · Corredor norte · Conecta Naucalpan→CDMX",
    },
    "Zaragoza · TAPO → Los Reyes": {
        "distancia_km":  16.5,
        "origen_key":    "TAPO · Terminal Oriente",
        "destino_key":   "Los Reyes La Paz",
        "lat_clima":     19.4050,
        "lon_clima":     -99.0500,
        "waypoints": [
            (19.4255, -99.1139),
            (19.4100, -99.0900),
            (19.3950, -99.0700),
            (19.3800, -99.0400),
        ],
        "color_mapa":    ROJO,
        "icono":         "🔴",
        "descripcion":   "16.5 km · Eje oriente · Alta densidad de incidentes",
    },
}

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves",
               "Viernes", "Sábado", "Domingo"]

_PERFIL_HABIL = np.array([
    0.95, 0.97, 0.98, 0.97, 0.90, 0.75,
    0.58, 0.42, 0.38, 0.45, 0.52, 0.55,
    0.50, 0.52, 0.55, 0.48, 0.38, 0.35,
    0.40, 0.50, 0.62, 0.72, 0.82, 0.92,
])
_PERFIL_FDS = np.array([
    0.95, 0.97, 0.98, 0.97, 0.95, 0.90,
    0.85, 0.78, 0.72, 0.68, 0.65, 0.62,
    0.60, 0.62, 0.65, 0.68, 0.65, 0.62,
    0.65, 0.70, 0.78, 0.85, 0.90, 0.93,
])

CDMX_CENTRO = (19.4326, -99.1332)


def ratio_historico(hora: int, dia_idx: int) -> float:
    perfil = _PERFIL_FDS if dia_idx >= 5 else _PERFIL_HABIL
    return float(perfil[int(hora) % 24])


def ratio_a_estado(ratio: float) -> int:
    if ratio >= 0.75:
        return 0
    if ratio >= 0.45:
        return 1
    return 2


# ════════════════════════════════════════════════════════════════════════════
# UTILIDADES GEOGRÁFICAS
# ════════════════════════════════════════════════════════════════════════════

def _reverse_geocode(lat: float, lon: float) -> str:
    for nombre, (plat, plon) in PUNTOS_CDMX.items():
        if calcular_distancia(lat, lon, plat, plon) <= 0.3:
            return nombre
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderServiceError
        geolocator = Nominatim(user_agent="vialai_cdmx", timeout=3)
        location   = geolocator.reverse((lat, lon), language="es", exactly_one=True)
        if location and location.address:
            partes = [p.strip() for p in location.address.split(",")]
            return ", ".join(partes[:3])
    except Exception:
        pass
    return f"Punto ({lat:.4f}, {lon:.4f})"


def calcular_distancia(lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
    try:
        from geopy.distance import geodesic
        return round(geodesic((lat1, lon1), (lat2, lon2)).km, 2)
    except ImportError:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat1))
             * math.cos(math.radians(lat2))
             * math.sin(dlon / 2) ** 2)
        return round(R * 2 * math.asin(math.sqrt(a)), 2)


def interpolar_waypoints(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    n: int = 5,
) -> list[tuple[float, float]]:
    fracs = np.linspace(0, 1, n)
    return [(lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1))
            for f in fracs]


# ════════════════════════════════════════════════════════════════════════════
# RUTA REAL POR CARRETERA
# ════════════════════════════════════════════════════════════════════════════

@st.cache_data(show_spinner=False, ttl=3600)
def _obtener_ruta(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    api_key = os.getenv("TOMTOM_API_KEY", "")
    if api_key and MODULOS_ROUTING_OK:
        try:
            cliente = TomTomRoutingClient(api_key=api_key)
            ruta    = cliente.calcular_ruta(lat1, lon1, lat2, lon2)
            return {
                "distancia_km":    ruta.distancia_km,
                "tiempo_base_min": ruta.tiempo_base_min,
                "waypoints":       ruta.waypoints,
                "fuente":          ruta.fuente,
            }
        except Exception:
            pass
    dist_lineal = calcular_distancia(lat1, lon1, lat2, lon2)
    dist_km     = round(dist_lineal * 1.4, 2)
    return {
        "distancia_km":    dist_km,
        "tiempo_base_min": round(dist_km / 30 * 60, 1),
        "waypoints":       interpolar_waypoints(lat1, lon1, lat2, lon2, n=8),
        "fuente":          "haversine_estimada",
    }


@st.cache_data(show_spinner=False, ttl=3600)
def _obtener_alternativas(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
    travel_mode: str = "car",
) -> list:
    """
    Devuelve hasta 3 RutaVial (lista). El índice 0 es la ruta principal.
    Si TomTom no está disponible o falla, retorna la ruta Haversine única.
    Nunca lanza excepción.
    """
    api_key = os.getenv("TOMTOM_API_KEY", "")
    if api_key and MODULOS_ROUTING_OK:
        try:
            cliente = TomTomRoutingClient(api_key=api_key)
            rutas   = cliente.calcular_alternativas(
                lat1, lon1, lat2, lon2,
                max_alternativas=2,
                travel_mode=travel_mode,
            )
            if rutas:
                return rutas
        except Exception:
            pass
    # Fallback: una sola ruta Haversine
    dist_lineal = calcular_distancia(lat1, lon1, lat2, lon2)
    dist_km     = round(dist_lineal * 1.4, 2)
    if MODULOS_ROUTING_OK:
        from src.ingestion.tomtom_routing import RutaVial as _RutaVial
        return [_RutaVial(
            distancia_km    = dist_km,
            tiempo_base_min = round(dist_km / 30 * 60, 1),
            waypoints       = interpolar_waypoints(lat1, lon1, lat2, lon2, n=8),
            fuente          = "haversine_estimada",
        )]
    # RutaVial no disponible: devolver dict compatible con evaluar_rutas
    class _Ruta:
        def __init__(self, dist, wp):
            self.distancia_km = dist
            self.waypoints    = wp
    return [_Ruta(dist_km, interpolar_waypoints(lat1, lon1, lat2, lon2, n=8))]


# ════════════════════════════════════════════════════════════════════════════
# CADENA DE MARKOV PRECALIBRADA
# ════════════════════════════════════════════════════════════════════════════

def _crear_cadena_calibrada() -> "MarkovTrafficChain | None":
    if not MODULOS_SIMULACION_OK:
        return None
    P = np.array([
        [0.6820, 0.2510, 0.0670],
        [0.3150, 0.4820, 0.2030],
        [0.1020, 0.3480, 0.5500],
    ])
    serie = np.array([0]*70 + [1]*50 + [2]*40 + [1]*30 + [0]*60 + [2]*20 + [1]*30)
    cadena = MarkovTrafficChain().fit(serie)
    cadena.transition_matrix_ = P
    return cadena


# ════════════════════════════════════════════════════════════════════════════
# CSS — RESET LIMPIO SIN CONFLICTOS
# ════════════════════════════════════════════════════════════════════════════

def _get_logo_b64() -> str | None:
    _candidates = [
        ROOT / "app" / "assets" / "logo_vialai.png",
        ROOT / "Logo VialAI.png",
    ]
    _src = ROOT / "Logo VialAI.png"
    _dst = ROOT / "app" / "assets" / "logo_vialai.png"
    if _src.exists() and not _dst.exists():
        _dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(_src, _dst)
    for _p in _candidates:
        if _p.exists():
            with open(_p, "rb") as _f:
                return "data:image/png;base64," + base64.b64encode(_f.read()).decode()
    return None


_LOGO_B64 = _get_logo_b64()

CSS = f"""
<style>
/* ── Fondo general ──────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {{
    background: #0D1B2A !important;
    color: #F0F4F8;
}}
[data-testid="stHeader"] {{
    background: #0D1B2A !important;
    border-bottom: 1px solid rgba(29,158,117,0.25);
    height: 0px !important;
}}
[data-testid="stToolbar"] {{
    visibility: hidden !important;
}}
#MainMenu {{
    visibility: hidden !important;
}}
button[data-testid="stBaseButton-header"] {{
    display: none !important;
}}

/* ── Texto global ───────────────────────────────────────────────────────── */
h1, h2, h3, h4 {{ color: #F0F4F8; }}
.stMarkdown p, .stMarkdown li {{ color: #C8D8E8; }}

/* ── Sidebar: estructura y fondo ────────────────────────────────────────── */
section[data-testid="stSidebar"] {{
    background: #0D1B2A !important;
    border-right: 1px solid rgba(29,158,117,0.3) !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
    padding-top: 1rem !important;
}}

/* ── Sidebar: texto blanco universal ────────────────────────────────────── */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {{
    color: #F0F4F8 !important;
}}

/* ── Sidebar: captions / subtítulos ─────────────────────────────────────── */
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
section[data-testid="stSidebar"] .stCaption {{
    color: #8BA7BE !important;
}}

/* ── Sidebar: selectbox control (borde verde) ───────────────────────────── */
section[data-testid="stSidebar"] [data-baseweb="select"] > div {{
    background-color: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(29,158,117,0.45) !important;
    border-radius: 8px !important;
    color: #F0F4F8 !important;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] [data-testid="stMarkdownContainer"] p {{
    color: #F0F4F8 !important;
    white-space: nowrap !important;
}}

/* ── Sidebar: botones de ruta rápida ────────────────────────────────────── */
section[data-testid="stSidebar"] div.stButton > button {{
    background: rgba(255,255,255,0.06) !important;
    color: #F0F4F8 !important;
    border: 1px solid rgba(29,158,117,0.35) !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    padding: 0.3rem 0.55rem !important;
    width: 100% !important;
    text-align: left !important;
    transition: background 0.15s, border-color 0.15s !important;
}}
section[data-testid="stSidebar"] div.stButton > button:hover {{
    background: rgba(29,158,117,0.18) !important;
    border-color: {VERDE} !important;
}}

/* ── Botón colapsar sidebar ─────────────────────────────────────────────── */
button[data-testid="collapsedControl"] {{
    background: #0D1B2A !important;
    border: 1.5px solid {VERDE} !important;
    border-radius: 8px !important;
    color: {VERDE} !important;
}}
button[data-testid="collapsedControl"] svg {{
    fill: {VERDE} !important;
}}

/* ── Selector hora: columnas compactas ──────────────────────────────────── */
section[data-testid="stSidebar"] [data-testid="column"] {{
    padding: 0 2px !important;
}}

/* ── Dropdown global (BaseWeb popover) ──────────────────────────────────── */
div[data-baseweb="popover"] {{
    background-color: #112233 !important;
}}
div[data-baseweb="popover"] ul {{
    background-color: #112233 !important;
}}
div[data-baseweb="popover"] li {{
    background-color: #112233 !important;
    color: #F0F4F8 !important;
}}
div[data-baseweb="popover"] li:hover {{
    background-color: #0C447C !important;
}}
div[data-baseweb="popover"] li[aria-selected="true"] {{
    background-color: {VERDE} !important;
}}
div[data-baseweb="popover"] * {{
    color: #F0F4F8 !important;
}}

/* ── Selectbox área principal ───────────────────────────────────────────── */
[data-baseweb="select"] > div {{
    background-color: #112233 !important;
    border-color: {VERDE} !important;
    color: #F0F4F8 !important;
}}

/* ── Botón principal Predecir ───────────────────────────────────────────── */
div.stButton > button[kind="primary"] {{
    background: {VERDE} !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.65rem 1.4rem !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    width: 100% !important;
    transition: background 0.2s, box-shadow 0.2s !important;
    box-shadow: 0 0 18px rgba(29,158,117,0.45) !important;
}}
div.stButton > button[kind="primary"]:hover {{
    background: #17866A !important;
    box-shadow: 0 0 26px rgba(29,158,117,0.65) !important;
}}

/* ── Botones secundarios ─────────────────────────────────────────────────── */
button[data-testid="baseButton-secondary"] {{
    color: #FFFFFF !important;
    font-weight: 500 !important;
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(29,158,117,0.35) !important;
}}
button[data-testid="baseButton-secondary"]:hover {{
    background: rgba(29,158,117,0.18) !important;
    border-color: {VERDE} !important;
}}

/* ── Cards / métricas ───────────────────────────────────────────────────── */
[data-testid="stMetric"] {{
    background: #112233;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    border: 1px solid rgba(29,158,117,0.30);
}}
[data-testid="stMetricValue"] {{
    color: {VERDE} !important;
    font-size: 2rem !important;
    font-weight: 800;
}}

/* ── Info / alert boxes ─────────────────────────────────────────────────── */
[data-testid="stInfo"] {{
    background: rgba(12,68,124,0.25);
    border-left: 4px solid {AZUL_MARINO};
    border-radius: 8px;
}}

/* ── Expanders ──────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {{
    background: #112233;
    border: 1px solid rgba(29,158,117,0.25);
    border-radius: 10px;
}}
[data-testid="stExpander"] summary {{
    color: #8BA7BE !important;
    font-size: 0.85rem;
}}

/* ── Semáforo ───────────────────────────────────────────────────────────── */
.luz {{
    width: 44px; height: 44px;
    border-radius: 50%;
    opacity: 0.18;
    transition: opacity 0.3s;
}}
.luz.activa {{ opacity: 1.0; box-shadow: 0 0 18px 5px currentColor; }}
.luz-verde    {{ background: #1D9E75; color: #1D9E75; }}
.luz-amarilla {{ background: #F5A623; color: #F5A623; }}
.luz-roja     {{ background: #D0021B; color: #D0021B; }}

/* ── Caption / small text ───────────────────────────────────────────────── */
.stCaption, [data-testid="stCaptionContainer"] p {{
    color: #8BA7BE !important;
}}

/* ── hr ─────────────────────────────────────────────────────────────────── */
hr {{ border-color: rgba(29,158,117,0.25) !important; }}

/* ── VialAI header fijo ─────────────────────────────────────────────────── */
.vialai-header {{
    position: fixed !important;
    top: 0 !important; left: 0 !important; right: 0 !important;
    height: 56px !important;
    background: #0D1B2A !important;
    border-bottom: 2px solid {VERDE} !important;
    display: flex !important;
    align-items: center !important;
    padding: 0 2rem !important;
    gap: 1.2rem !important;
    z-index: 999999 !important;
}}
.vh-logo {{ font-size: 1.4rem; font-weight: 800; letter-spacing: -0.03em; }}
.vh-logo .v  {{ color: #FFFFFF; }}
.vh-logo .ai {{ color: {VERDE}; }}
.vh-sep {{ width: 1px; height: 24px; background: rgba(255,255,255,0.15); }}
.vh-tag {{ font-size: 0.78rem; color: #8BA7BE; }}
.vh-right {{
    margin-left: auto;
    display: flex;
    gap: 1.5rem;
    font-size: 0.75rem;
    color: #8BA7BE;
}}
.vh-right span:hover {{ color: {VERDE}; cursor: pointer; }}

/* ── Empujar contenido debajo del header ────────────────────────────────── */
.main .block-container {{
    padding-top: 72px !important;
}}

/* ── Hora de salida: pill de confirmación ───────────────────────────────── */
.hora-pill {{
    text-align: center;
    margin-top: 6px;
    padding: 5px 0;
    background: rgba(29,158,117,0.12);
    border: 1px solid rgba(29,158,117,0.28);
    border-radius: 6px;
    font-size: 0.82rem;
    color: #8BA7BE;
}}
.hora-pill b {{
    color: {VERDE};
    font-size: 0.95rem;
}}

/* ── Sidebar: botones secundarios (gris, hover rojo) ────────────────────── */
section[data-testid="stSidebar"] button[kind="secondary"],
section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
    background: rgba(255,255,255,0.08) !important;
    color: #C8D8E8 !important;
    border: 1px solid rgba(255,255,255,0.20) !important;
    border-radius: 8px !important;
}}
section[data-testid="stSidebar"] button[kind="secondary"]:hover,
section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
    background: rgba(208,2,27,0.18) !important;
    border-color: {ROJO} !important;
    color: #FFFFFF !important;
}}

/* ── Sidebar: cabecera de expander (texto azul, fondo azul tenue) ─────── */
section[data-testid="stSidebar"] [data-testid="stExpander"] summary {{
    background: rgba(29,158,117,0.10) !important;
    border-radius: 8px !important;
    color: {VERDE} !important;
}}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary p,
section[data-testid="stSidebar"] [data-testid="stExpander"] summary span {{
    color: {VERDE} !important;
    font-weight: 600 !important;
}}

/* ══ CALENDARIO — FONDO OSCURO, TEXTO VERDE ══ */
div[data-testid="stSidebar"] div[data-testid="stDateInput"] > div {{
    background-color: #0F1B2D !important;
}}
div[data-baseweb="calendar"] {{
    background-color: #0F1B2D !important;
}}
div[data-baseweb="calendar"] * {{
    color: {VERDE} !important;
}}
div[data-baseweb="calendar"] button {{
    color: {VERDE} !important;
    background-color: transparent !important;
}}
div[data-baseweb="calendar"] button:hover {{
    background-color: {VERDE} !important;
    color: #000000 !important;
}}
div[data-baseweb="calendar"] button[aria-selected="true"] {{
    background-color: #F5A623 !important;
    color: #000000 !important;
    font-weight: 700 !important;
}}
div[data-baseweb="calendar"] button[aria-disabled="true"] {{
    color: #2A3F5F !important;
}}
div[data-baseweb="calendar"] svg {{
    fill: {VERDE} !important;
}}
div[data-baseweb="input"] input {{
    color: {VERDE} !important;
    background-color: #0F1B2D !important;
}}
div[data-baseweb="popover"] {{
    background-color: #0F1B2D !important;
    border: 1px solid {VERDE} !important;
}}
div[data-baseweb="select"] span,
div[data-baseweb="select"] div {{
    color: {VERDE} !important;
}}
div[data-baseweb="menu"] {{
    background-color: #0F1B2D !important;
}}
div[data-baseweb="menu"] li {{
    color: {VERDE} !important;
}}
div[data-baseweb="menu"] li:hover {{
    background-color: {VERDE} !important;
    color: #000000 !important;
}}

/* ── NUCLEAR: todos los botones del sidebar — fondo oscuro, texto blanco ─ */
div[data-testid="stSidebar"] button {{
    background-color: #1A2940 !important;
    color: #FFFFFF !important;
    border: 1.5px solid #4A6FA5 !important;
    font-weight: 600 !important;
}}
div[data-testid="stSidebar"] button:hover {{
    background-color: #F5A623 !important;
    color: #000000 !important;
    border-color: #F5A623 !important;
}}
div[data-testid="stSidebar"] button p,
div[data-testid="stSidebar"] button span,
div[data-testid="stSidebar"] button div {{
    color: #FFFFFF !important;
}}
div[data-testid="stSidebar"] button:hover p,
div[data-testid="stSidebar"] button:hover span,
div[data-testid="stSidebar"] button:hover div {{
    color: #000000 !important;
}}

/* ── Expander Configuración Avanzada ──────────────────────────────────── */
div[data-testid="stSidebar"] .streamlit-expanderHeader {{
    color: #E0E0E0 !important;
    font-weight: 600 !important;
    background-color: rgba(61, 90, 128, 0.3) !important;
    border-radius: 6px !important;
    padding: 8px !important;
}}

/* ── Caption y labels del sidebar ─────────────────────────────────────── */
div[data-testid="stSidebar"] .stCaption,
div[data-testid="stSidebar"] small {{
    color: #B0C4DE !important;
}}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)

st.markdown("""
<style>
/* Ocultar mensaje de error residual del widget st.audio_input */
[data-testid="stAudioInput"] [class*="error"],
[data-testid="stAudioInput"] div:has(> svg[aria-label*="error"]) {
    display: none !important;
}
/* Texto del contador de tiempo en verde VialAI */
[data-testid="stAudioInput"] * {
    color: #22c55e !important;
}
[data-testid="stAudioInput"] input,
[data-testid="stAudioInput"] span {
    color: #22c55e !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)

_logo_html = (
    f'<img src="{_LOGO_B64}" style="height:44px;width:auto;object-fit:contain;">'
    if _LOGO_B64
    else '<div class="vh-logo"><span class="v">Vial</span><span class="ai">AI</span></div>'
)
st.markdown(
    f"<div class='vialai-header'>"
    f"{_logo_html}"
    f"<div class='vh-sep'></div>"
    f"<div class='vh-tag'>Predicción estocástica · ZMVM</div>"
    f"<div class='vh-right'>"
    f"<span>Monte Carlo + Markov</span>"
    f"<span>·</span>"
    f"<span>Diplomado Ciencia de Datos 2026</span>"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)


# ════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════════════════════

_DEFAULTS: dict = {
    "origen":  None,
    "destino": None,
    "modo_click": "A",
    "ultimo_click": None,
    "waypoints_activos": None,
    "color_ruta": AZUL_MARINO,
    "ruta_rapida_origen":  None,
    "ruta_rapida_destino": None,
    "capa_mapa": "estandar",
    "chat_historial": [],
    "perfil_vehiculo": "🚗 Automóvil",
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════

with st.sidebar:

    st.markdown(
        "<hr style='border-color:rgba(29,158,117,0.30);margin:0.4rem 0 0.4rem;'>",
        unsafe_allow_html=True,
    )

    # ── Origen ──────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:4px;'>"
        "📍 Origen</div>",
        unsafe_allow_html=True,
    )
    _idx_origen = (
        _OPCIONES_OD.index(st.session_state.ruta_rapida_origen)
        if st.session_state.ruta_rapida_origen in _OPCIONES_OD
        else 0
    )
    sel_origen = st.selectbox(
        label="Origen",
        options=_OPCIONES_OD,
        index=_idx_origen,
        label_visibility="collapsed",
    )
    if sel_origen != OPCION_MAPA:
        st.session_state.ruta_rapida_origen = sel_origen
        lat_o, lon_o = PUNTOS_CDMX[sel_origen]
        st.session_state.origen = {"lat": lat_o, "lon": lon_o, "nombre": sel_origen}
        st.session_state.waypoints_activos = None

    if st.session_state.origen:
        o = st.session_state.origen
        st.markdown(
            f"<div style='font-size:0.75rem;color:#7EC8A4;margin-top:2px;'>"
            f"✔ {o['nombre']}<br>"
            f"<span style='color:#8AADCA;'>{o['lat']:.4f}, {o['lon']:.4f}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Selecciona en el mapa o lista")

    # ── Destino ──────────────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:4px;margin-top:8px;'>"
        "🏁 Destino</div>",
        unsafe_allow_html=True,
    )
    _idx_destino = (
        _OPCIONES_OD.index(st.session_state.ruta_rapida_destino)
        if st.session_state.ruta_rapida_destino in _OPCIONES_OD
        else 0
    )
    sel_destino = st.selectbox(
        label="Destino",
        options=_OPCIONES_OD,
        index=_idx_destino,
        label_visibility="collapsed",
    )
    if sel_destino != OPCION_MAPA:
        st.session_state.ruta_rapida_destino = sel_destino
        lat_d, lon_d = PUNTOS_CDMX[sel_destino]
        st.session_state.destino = {"lat": lat_d, "lon": lon_d, "nombre": sel_destino}
        st.session_state.waypoints_activos = None

    if st.session_state.destino:
        d = st.session_state.destino
        st.markdown(
            f"<div style='font-size:0.75rem;color:#E88;margin-top:2px;'>"
            f"✔ {d['nombre']}<br>"
            f"<span style='color:#8AADCA;'>{d['lat']:.4f}, {d['lon']:.4f}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Selecciona en el mapa o lista")

    # ── Distancia ────────────────────────────────────────────────────────────
    st.markdown(
        "<hr style='border-color:rgba(255,255,255,0.15);margin:0.6rem 0;'>",
        unsafe_allow_html=True,
    )

    origen_activo  = st.session_state.origen
    destino_activo = st.session_state.destino

    if origen_activo and destino_activo:
        _ruta_sidebar = _obtener_ruta(
            origen_activo["lat"],  origen_activo["lon"],
            destino_activo["lat"], destino_activo["lon"],
        )
        dist_km     = _ruta_sidebar["distancia_km"]
        _fuente_ico = "🛣️" if _ruta_sidebar["fuente"] == "tomtom" else "📐"
        _fuente_tip = ("Ruta real por carretera (TomTom)"
                       if _ruta_sidebar["fuente"] == "tomtom"
                       else "Estimación: Haversine × 1.4")
        st.markdown(
            f"<div style='text-align:center;padding:0.5rem;"
            f"background:rgba(29,158,117,0.2);border-radius:8px;"
            f"font-size:0.9rem;color:white;' title='{_fuente_tip}'>"
            f"{_fuente_ico} Distancia: <b>{dist_km} km</b></div>",
            unsafe_allow_html=True,
        )
    else:
        dist_km = None

    # ── Rutas frecuentes ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.72rem;color:#7B9DB8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin:8px 0 6px;'>"
        "⚡ Rutas frecuentes</div>",
        unsafe_allow_html=True,
    )
    for nombre_ruta, datos_ruta in CORREDORES.items():
        etiqueta = f"{datos_ruta['icono']} {nombre_ruta.split('·')[0].strip()}"
        if st.button(etiqueta, key=f"btn_{nombre_ruta[:20]}", use_container_width=True):
            st.session_state.ruta_rapida_origen  = datos_ruta["origen_key"]
            st.session_state.ruta_rapida_destino = datos_ruta["destino_key"]
            lat_o, lon_o = PUNTOS_CDMX[datos_ruta["origen_key"]]
            lat_d, lon_d = PUNTOS_CDMX[datos_ruta["destino_key"]]
            st.session_state.origen  = {"lat": lat_o, "lon": lon_o, "nombre": datos_ruta["origen_key"]}
            st.session_state.destino = {"lat": lat_d, "lon": lon_d, "nombre": datos_ruta["destino_key"]}
            st.session_state.waypoints_activos = datos_ruta["waypoints"]
            st.session_state.color_ruta        = datos_ruta["color_mapa"]
            st.session_state.modo_click        = "A"

    st.markdown(
        "<hr style='border-color:rgba(255,255,255,0.15);margin:0.6rem 0;'>",
        unsafe_allow_html=True,
    )

    # ── Hora de salida ───────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:6px;'>"
        "🕐 Hora de salida</div>",
        unsafe_allow_html=True,
    )

    # Opciones cortas para que no se trunquen en columnas angostas
    _horas_opciones   = [f"{h:02d}:00" for h in range(24)]
    _minutos_opciones = [f":{m:02d}" for m in range(0, 60, 5)]

    _col_h, _col_m = st.columns([3, 2])
    with _col_h:
        st.markdown(
            "<div style='font-size:0.72rem;color:#8BA7BE;margin-bottom:2px;'>HORA</div>",
            unsafe_allow_html=True,
        )
        _hora_sel = st.selectbox(
            "Hora", _horas_opciones,
            index=8,
            label_visibility="collapsed",
            key="sel_hora",
        )
    with _col_m:
        st.markdown(
            "<div style='font-size:0.72rem;color:#8BA7BE;margin-bottom:2px;'>MIN</div>",
            unsafe_allow_html=True,
        )
        _min_sel = st.selectbox(
            "Min", _minutos_opciones,
            index=0,
            label_visibility="collapsed",
            key="sel_min",
        )

    _hora    = int(_hora_sel.split(":")[0])
    _minutos = int(_min_sel.replace(":", ""))
    hora_salida = _hora + _minutos / 60

    st.markdown(
        f"<div class='hora-pill'>Salida a las <b>{_hora:02d}:{_minutos:02d} h</b></div>",
        unsafe_allow_html=True,
    )

    # ── Fecha de viaje ────────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-top:10px;margin-bottom:4px;'>"
        "📅 Fecha de viaje</div>",
        unsafe_allow_html=True,
    )
    _fecha_sel = st.date_input(
        label="Fecha",
        value=datetime.date.today(),
        min_value=datetime.date.today(),
        max_value=datetime.date.today() + datetime.timedelta(days=30),
        label_visibility="collapsed",
        format="DD/MM/YYYY",
    )
    # Derivar día de la semana en español a partir de la fecha
    _DIA_ISO_A_NOMBRE = {
        0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
        4: "Viernes", 5: "Sábado", 6: "Domingo",
    }
    dia_nombre = _DIA_ISO_A_NOMBRE[_fecha_sel.weekday()]
    dia_idx = DIAS_SEMANA.index(dia_nombre)
    st.markdown(
        f"<div style='font-size:0.78rem;color:#7EC8A4;margin-top:3px;'>"
        f"📌 {dia_nombre}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<hr style='border-color:rgba(255,255,255,0.15);margin:0.6rem 0;'>",
        unsafe_allow_html=True,
    )

    # ── Botón principal ──────────────────────────────────────────────────────
    boton_deshabilitado = not (origen_activo and destino_activo)
    predecir = st.button(
        "🚀 Predecir trayecto",
        type="primary",
        use_container_width=True,
        disabled=boton_deshabilitado,
    )
    if boton_deshabilitado:
        st.caption("⚠ Define origen y destino para habilitar")

    # ── Configuración avanzada ───────────────────────────────────────────────
    with st.expander("⚙️ Configuración avanzada"):
        n_sims = st.select_slider(
            "Simulaciones Monte Carlo",
            options=[500, 1_000, 5_000, 10_000],
            value=5_000,
        )
        usar_api = st.toggle(
            "Usar APIs en tiempo real",
            value=False,
            help="Requiere TOMTOM_API_KEY y OPENWEATHERMAP_API_KEY en .env",
        )

    # ── Tipo de vehículo ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-top:10px;margin-bottom:4px;'>"
        "🚗 Tipo de vehículo</div>",
        unsafe_allow_html=True,
    )
    tipo_vehiculo = st.radio(
        "Tipo de vehículo",
        options=["🚗 Automóvil", "🏍️ Motocicleta"],
        horizontal=True,
        label_visibility="collapsed",
        index=["🚗 Automóvil", "🏍️ Motocicleta"].index(
            st.session_state.perfil_vehiculo
        ),
        key="perfil_vehiculo",
    )

    # ── Chat VialAI ──────────────────────────────────────────────────────────
    st.markdown(
        "<hr style='border-color:rgba(255,255,255,0.25);margin:1.1rem 0 0.8rem;'>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:6px;'>"
        "💬 Asistente VialAI</div>",
        unsafe_allow_html=True,
    )

    _BIENVENIDA = (
        "Hola, soy VialAI 🚦 Pregúntame sobre tu trayecto, "
        "condiciones de tráfico o el mejor horario para salir."
    )

    # Contenedor scrollable para el historial de mensajes
    _chat_box = st.container(height=260, border=False)
    with _chat_box:
        with st.chat_message("assistant"):
            st.write(_BIENVENIDA)
        for _i, _msg in enumerate(st.session_state.chat_historial):
            with st.chat_message(_msg["role"]):
                st.write(_msg["content"])
                # Reproduce el audio solo del último mensaje del asistente
                if (
                    _msg.get("audio")
                    and _i == len(st.session_state.chat_historial) - 1
                ):
                    # pyttsx3 produce WAV, tts-1 produce MP3
                    _fmt = "audio/wav" if _msg["audio"][:4] == b"RIFF" else "audio/mp3"
                    st.audio(_msg["audio"], format=_fmt, autoplay=True)

    # Auto-scroll al último mensaje del asistente
    st.markdown("""
<script>
setTimeout(function() {
    const messages = window.parent.document.querySelectorAll(
        '[data-testid="stChatMessage"]'
    );
    if (messages.length > 0) {
        const last = messages[messages.length - 1];
        last.scrollIntoView({behavior: 'smooth', block: 'start'});
    }
}, 300);
</script>
""", unsafe_allow_html=True)

    # ── Entrada por voz ──────────────────────────────────────────────────────
    if VOICE_IO_OK:
        st.markdown("### 🎤 VialAI — Comando por voz")
        st.caption("Manos al volante: habla tu ruta y VialAI la calcula.")
        audio_value = st.audio_input(
            "Pulsa para grabar",
            key="vialai_audio_input",
        )
        _col_v1, _col_v2 = st.columns(2)
        with _col_v1:
            send_voice = st.button("🚀 Enviar consulta", use_container_width=True)
        with _col_v2:
            tts_enabled = st.toggle(
                "🔊 Respuesta hablada",
                value=False,
                help="Actívalo si vas manejando. Consume API de OpenAI TTS."
            )
    else:
        audio_value = None
        send_voice = False
        tts_enabled = False

    # ── Input de lenguaje natural ─────────────────────────────────────────────
    _prompt = st.chat_input("Pregunta a VialAI…")

    # ── Procesamiento de voz ──────────────────────────────────────────────────
    _prompt_voz = None
    if send_voice:
        if audio_value is not None:
            try:
                with st.spinner("🎧 Transcribiendo tu comando..."):
                    _prompt_voz_raw = transcribir_audio(audio_value.getvalue())
                if _prompt_voz_raw:
                    _prompt_voz = _prompt_voz_raw
                    st.sidebar.success(f"📝 Entendí: *{_prompt_voz_raw}*")
                else:
                    st.sidebar.warning("No entendí el audio. Intenta de nuevo.")
            except Exception as _ve:
                from src.agent.voice_io import VoiceError
                if isinstance(_ve, VoiceError):
                    st.sidebar.error(f"🎤 {_ve.user_msg}")
                else:
                    st.sidebar.error(f"🎤 Error inesperado: {_ve}")
        else:
            st.sidebar.warning("Graba un mensaje antes de enviar.")

    # Prioridad: voz > texto
    _prompt_final = _prompt_voz or _prompt

    if _prompt_final:
        st.session_state.chat_historial.append({"role": "user", "content": _prompt_final})
        _historial_api = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.chat_historial[:-1]
        ]
        with st.spinner("VialAI está pensando…"):
            if VIALAI_OK:
                try:
                    _vialai = VialAIAgent()
                    _respuesta = _vialai.run(_prompt_final, historial=_historial_api)
                except Exception as _exc:
                    st.error(f"Error al inicializar el agente: {_exc}")
                    _respuesta = f"⚠️ Error al inicializar el agente: {_exc}"
            else:
                _respuesta = (
                    "⚠️ El módulo del agente no está disponible. "
                    "Verifica la instalación de src/agent/agent.py."
                )

        # TTS: solo si la entrada fue por voz y el toggle está activo
        _audio_respuesta = None
        if tts_enabled and _prompt_voz and VOICE_IO_OK:
            with st.spinner("🔊 Generando respuesta hablada..."):
                _texto_hablable = resumen_para_voz(_respuesta)
                _audio_respuesta = sintetizar_voz(_texto_hablable)

        st.session_state.chat_historial.append(
            {"role": "assistant", "content": _respuesta, "audio": _audio_respuesta}
        )
        st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# CORREDOR ACTIVO
# ════════════════════════════════════════════════════════════════════════════

if origen_activo and destino_activo:
    _travel_mode = "motorcycle" if "Motocicleta" in tipo_vehiculo else "car"
    _ruta = _obtener_ruta(
        origen_activo["lat"],  origen_activo["lon"],
        destino_activo["lat"], destino_activo["lon"],
    )
    _rutas_alternativas = _obtener_alternativas(
        origen_activo["lat"],  origen_activo["lon"],
        destino_activo["lat"], destino_activo["lon"],
        travel_mode=_travel_mode,
    )
    # ── DEBUG TEMPORAL: número de rutas recibidas ────────────────────────────
    _fuente_alt = getattr(_rutas_alternativas[0], "fuente", "?") if _rutas_alternativas else "—"
    st.sidebar.info(
        f"🛣️ Rutas recibidas: **{len(_rutas_alternativas)}** "
        f"(fuente: `{_fuente_alt}`)"
    )
    # ────────────────────────────────────────────────────────────────────────
    dist_km_activo    = _ruta["distancia_km"]
    waypoints_activos = _ruta["waypoints"]
    corredor_activo: dict | None = {
        "distancia_km":    dist_km_activo,
        "tiempo_base_min": _ruta["tiempo_base_min"],
        "fuente_ruta":     _ruta["fuente"],
        "lat_clima":       origen_activo["lat"],
        "lon_clima":       origen_activo["lon"],
        "waypoints":       waypoints_activos,
        "color_mapa":      st.session_state.color_ruta,
        "descripcion":     (f"{origen_activo['nombre']} → {destino_activo['nombre']} "
                            f"· {dist_km_activo} km"),
    }
else:
    corredor_activo     = None
    dist_km_activo      = None
    waypoints_activos   = []
    _rutas_alternativas = []


# ════════════════════════════════════════════════════════════════════════════
# SIMULACIÓN
# ════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def obtener_cadena() -> "MarkovTrafficChain | None":
    return _crear_cadena_calibrada()


def ajustar_velocidad_por_vehiculo(params: dict, tipo: str) -> dict:
    """Aplica un factor multiplicador a los parámetros de velocidad según el tipo de vehículo."""
    ajustado = deepcopy(params)
    if "Motocicleta" in tipo:
        # Las motos navegan ~15 % más rápido en tráfico denso
        for estado in ajustado:
            ajustado[estado]["media"] = round(ajustado[estado]["media"] * 1.15, 2)
            ajustado[estado]["min"]   = round(ajustado[estado]["min"]   * 1.10, 2)
            ajustado[estado]["max"]   = round(ajustado[estado]["max"]   * 1.12, 2)
    return ajustado


def simular_modo_demo(
    corredor: dict, hora: int, dia_idx: int, n_simulaciones: int,
    tipo_vehiculo: str = "🚗 Automóvil",
) -> dict:
    cadena = obtener_cadena()
    if cadena is None or not MODULOS_SIMULACION_OK:
        return _resultado_fallback(corredor, hora, dia_idx)
    ratio          = ratio_historico(hora, dia_idx)
    estado_inicial = ratio_a_estado(ratio)
    factor_cong    = 1.0 + max(0, (0.6 - ratio)) * 0.8
    params_ajust = {
        k: {
            "media": max(round(v["media"] / factor_cong, 2), 1.0),
            "std":   max(round(v["std"]   / factor_cong, 2), 0.5),
            "min":   max(round(v["min"]   / factor_cong, 2), 1.0),
            "max":   v["max"],
        }
        for k, v in VELOCIDAD_PARAMS.items()
    }
    params_ajust = ajustar_velocidad_por_vehiculo(params_ajust, tipo_vehiculo)
    try:
        motor    = MonteCarloEngine(cadena, n_simulaciones=n_simulaciones,
                                    velocidad_params=params_ajust,
                                    rng=np.random.default_rng(42))
        consulta = ConsultaViaje(distancia_km=corredor["distancia_km"],
                                 estado_inicial=estado_inicial)
        resultado = motor.correr(consulta)
        return {
            "p10": round(resultado.p10, 1), "p50": round(resultado.p50, 1),
            "p90": round(resultado.p90, 1), "media": round(resultado.media, 1),
            "std": round(resultado.std, 1), "estado_inicial": estado_inicial,
            "ratio": ratio, "tiempos": resultado.tiempos_minutos,
            "n_recortadas": resultado.n_recortadas, "modo": "demo",
        }
    except Exception as e:
        st.warning(f"Error en simulación: {e}")
        return _resultado_fallback(corredor, hora, dia_idx)


def _simular_multi_ruta(
    rutas_viales: list,
    hora: int,
    dia_idx: int,
    n_simulaciones: int,
    tipo_vehiculo: str = "🚗 Automóvil",
) -> list:
    """
    Evalúa múltiples rutas con Monte Carlo. Retorna lista[ResultadoRuta].
    Si no hay módulos disponibles, retorna lista vacía.
    """
    if not MODULOS_SIMULACION_OK or not MODULOS_EVALUADOR_OK or not rutas_viales:
        return []
    cadena = obtener_cadena()
    if cadena is None:
        return []
    ratio          = ratio_historico(hora, dia_idx)
    estado_inicial = ratio_a_estado(ratio)
    factor_cong    = 1.0 + max(0, (0.6 - ratio)) * 0.8
    params_ajust = {
        k: {
            "media": max(round(v["media"] / factor_cong, 2), 1.0),
            "std":   max(round(v["std"]   / factor_cong, 2), 0.5),
            "min":   max(round(v["min"]   / factor_cong, 2), 1.0),
            "max":   v["max"],
        }
        for k, v in VELOCIDAD_PARAMS.items()
    }
    params_ajust = ajustar_velocidad_por_vehiculo(params_ajust, tipo_vehiculo)
    motor = MonteCarloEngine(
        cadena, n_simulaciones=n_simulaciones,
        velocidad_params=params_ajust,
        rng=np.random.default_rng(42),
    )
    return evaluar_rutas(rutas_viales, motor, cadena, estado_inicial)


def _resultado_fallback(corredor: dict, hora: int, dia_idx: int) -> dict:
    ratio  = ratio_historico(hora, dia_idx)
    vel    = 40 * ratio + 7 * (1 - ratio)
    p50    = round(corredor["distancia_km"] / vel * 60, 1)
    spread = p50 * 0.3
    rng    = np.random.default_rng(hora + dia_idx * 24)
    tiempos = rng.normal(p50, spread * 0.4, 1000).clip(p50 * 0.5, p50 * 2.5)
    return {
        "p10": round(p50 - spread * 0.6, 1), "p50": p50,
        "p90": round(p50 + spread, 1),       "media": p50,
        "std": round(spread * 0.4, 1),       "estado_inicial": ratio_a_estado(ratio),
        "ratio": ratio, "tiempos": tiempos,  "n_recortadas": 0, "modo": "fallback",
    }


def simular_modo_api(corredor: dict, hora: int, dia_idx: int, n_simulaciones: int) -> dict:
    from dotenv import load_dotenv
    load_dotenv()
    tomtom_key = os.getenv("TOMTOM_API_KEY", "")
    owm_key    = os.getenv("OPENWEATHERMAP_API_KEY", "")
    if not tomtom_key or not owm_key:
        st.warning("Faltan API keys → usando modo DEMO.")
        return simular_modo_demo(corredor, hora, dia_idx, n_simulaciones)
    try:
        pipeline = PipelineIntegrador(
            TomTomTrafficClient(api_key=tomtom_key, pausa_entre_lotes=0.3),
            OpenWeatherMapClient(api_key=owm_key),
        )
        with st.spinner("Consultando TomTom Traffic API..."):
            ctx, resultado = pipeline.predecir_tiempo_viaje(
                coordenadas_corredor = corredor["waypoints"],
                lat_clima            = corredor["lat_clima"],
                lon_clima            = corredor["lon_clima"],
                distancia_km         = corredor["distancia_km"],
                cadena               = obtener_cadena(),
                n_simulaciones       = n_simulaciones,
                rng                  = np.random.default_rng(42),
            )
        return {
            "p10": round(resultado.p10, 1), "p50": round(resultado.p50, 1),
            "p90": round(resultado.p90, 1), "media": round(resultado.media, 1),
            "std": round(resultado.std, 1), "estado_inicial": ctx.estado_inicial,
            "ratio": ctx.ratio_congestion_promedio, "tiempos": resultado.tiempos_minutos,
            "n_recortadas": resultado.n_recortadas, "modo": "api",
            "clima": ctx.clima, "factor_clima": ctx.factor_climatico,
        }
    except Exception as e:
        st.warning(f"Error API: {e} → usando modo DEMO.")
        return simular_modo_demo(corredor, hora, dia_idx, n_simulaciones)


# ════════════════════════════════════════════════════════════════════════════
# VISUALIZACIÓN
# ════════════════════════════════════════════════════════════════════════════

def _nivel_riesgo(estado: int, p90: float, p50: float) -> tuple[str, str, str]:
    banda = p90 - p50
    if estado == 0 and banda < 15:
        return "verde",    VERDE,    "Tráfico fluido"
    if estado == 2 or banda > 30:
        return "rojo",     ROJO,     "Congestión severa"
    return "amarillo", AMARILLO, "Tráfico moderado"


def render_gauge(p50: float, p10: float, p90: float, distancia_km: float) -> go.Figure:
    max_val = max(p90 * 1.3, 90)
    fig = go.Figure(go.Indicator(
        mode   = "gauge+number+delta",
        value  = p50,
        delta  = {
            "reference":  distancia_km / 40 * 60,
            "suffix":     " min",
            "increasing": {"color": ROJO},
            "decreasing": {"color": VERDE},
            "font":       {"size": 16},
        },
        number = {
            "suffix":      " min",
            "font":        {"size": 52, "color": AZUL_MARINO, "family": "Arial Black"},
            "valueformat": ".0f",
        },
        title  = {
            "text": (
                "Tiempo estimado <b>P50</b><br>"
                "<span style='font-size:0.78em;color:#888;font-weight:400;'>"
                "mediana de las simulaciones</span>"
            ),
            "font": {"size": 16, "color": "#333"},
        },
        domain = {"x": [0.0, 1.0], "y": [0.0, 1.0]},
        gauge  = {
            "axis": {
                "range":     [0, max_val],
                "tickwidth": 1,
                "tickcolor": "#CCC",
                "tickfont":  {"size": 11},
            },
            "bar":         {"color": AZUL_MARINO, "thickness": 0.30},
            "bgcolor":     "white",
            "borderwidth": 0,
            "steps": [
                {"range": [0,              max_val * 0.40], "color": "#D4EFE4"},
                {"range": [max_val * 0.40, max_val * 0.70], "color": "#FEF3CD"},
                {"range": [max_val * 0.70, max_val],        "color": "#FADBD8"},
            ],
            "threshold": {
                "line":      {"color": AZUL_MARINO, "width": 3},
                "thickness": 0.85,
                "value":     p50,
            },
        },
    ))
    fig.update_layout(
        height=320,
        margin=dict(t=60, b=20, l=40, r=40),
        paper_bgcolor="#112233",
        plot_bgcolor="#112233",
        font={"family": "Arial", "color": "#F0F4F8"},
    )
    return fig


def render_banda_incertidumbre(p10: float, p50: float, p90: float) -> go.Figure:
    fig = go.Figure()
    fig.add_shape(type="rect", x0=p10, x1=p90, y0=0.2, y1=0.8,
                  fillcolor="rgba(12,68,124,0.15)",
                  line=dict(color=AZUL_MARINO, width=1.5, dash="dot"))
    fig.add_shape(type="rect", x0=p10, x1=p50, y0=0.2, y1=0.8,
                  fillcolor="rgba(29,158,117,0.25)", line=dict(width=0))
    fig.add_shape(type="line", x0=p50, x1=p50, y0=0.05, y1=0.95,
                  line=dict(color=AZUL_MARINO, width=3))
    for val, etiq, col in [(p10, "P10", VERDE), (p50, "P50", AZUL_MARINO), (p90, "P90", ROJO)]:
        fig.add_trace(go.Scatter(
            x=[val], y=[0.5], mode="markers+text",
            marker=dict(size=14, color=col, symbol="diamond"),
            text=[f"<b>{etiq}</b><br>{val:.0f} min"],
            textposition="top center",
            textfont=dict(size=11, color=col),
            showlegend=False,
        ))
    fig.update_layout(
        height=160, margin=dict(t=30, b=20, l=10, r=10),
        xaxis=dict(title="Tiempo de viaje (minutos)",
                   range=[max(0, p10 - 10), p90 + 10],
                   showgrid=True, gridcolor="rgba(255,255,255,0.08)",
                   tickfont=dict(color="#8BA7BE"),
                   title_font=dict(color="#8BA7BE")),
        yaxis=dict(visible=False, range=[0, 1]),
        paper_bgcolor="#0D1B2A", plot_bgcolor="#0D1B2A",
        title=dict(text="Banda de incertidumbre P10 — P50 — P90",
                   font=dict(size=13, color="#C8D8E8"), x=0.5),
    )
    return fig


def render_histograma(tiempos: np.ndarray, p10: float, p50: float, p90: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=tiempos, nbinsx=60,
        marker_color="rgba(12,68,124,0.65)",
        marker_line=dict(color="white", width=0.3),
        hovertemplate="Tiempo: %{x:.1f} min<br>Frecuencia: %{y}<extra></extra>",
    ))
    for val, etiq, col, dash in [(p10, "P10", VERDE, "dash"),
                                   (p50, "P50", AZUL_MARINO, "solid"),
                                   (p90, "P90", ROJO, "dash")]:
        fig.add_vline(x=val, line_color=col, line_width=2.5, line_dash=dash,
                      annotation_text=f"<b>{etiq}: {val:.0f} min</b>",
                      annotation_position="top",
                      annotation_font=dict(size=11, color=col))
    fig.update_layout(
        title=dict(text=f"Distribución de {len(tiempos):,} tiempos simulados",
                   font=dict(size=13, color="#C8D8E8"), x=0.5),
        xaxis_title="Tiempo de viaje (minutos)",
        yaxis_title="Frecuencia",
        xaxis=dict(title_font=dict(color="#8BA7BE"), tickfont=dict(color="#8BA7BE")),
        yaxis=dict(title_font=dict(color="#8BA7BE"), tickfont=dict(color="#8BA7BE")),
        paper_bgcolor="#0D1B2A", plot_bgcolor="#0D1B2A",
        height=280, margin=dict(t=40, b=40, l=40, r=20),
        bargap=0.05, showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.07)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.07)")
    return fig


def render_semaforo(nivel: str, etiqueta: str, ratio: float,
                    estado_nombre: str, color_nivel: str) -> None:
    av = "activa" if nivel == "verde"    else ""
    aa = "activa" if nivel == "amarillo" else ""
    ar = "activa" if nivel == "rojo"     else ""
    st.markdown(
        f"""
        <div style="background:#112233;border-radius:14px;
                    border:2px solid {color_nivel};
                    padding:1.4rem 1.8rem;
                    display:grid;
                    grid-template-columns:72px 1fr;
                    align-items:center;
                    gap:1.5rem;
                    box-shadow:0 2px 18px rgba(0,0,0,0.40);">
            <div style="display:flex;flex-direction:column;align-items:center;gap:7px;">
                <div class="luz luz-roja {ar}"></div>
                <div class="luz luz-amarilla {aa}"></div>
                <div class="luz luz-verde {av}"></div>
            </div>
            <div>
                <div style="font-size:1.45rem;font-weight:800;color:{color_nivel};line-height:1.2;">
                    {etiqueta}
                </div>
                <div style="font-size:0.9rem;color:#555;margin-top:0.35rem;">
                    Estado Markov: <b>{estado_nombre}</b>
                </div>
                <div style="font-size:0.78rem;color:#999;margin-top:0.2rem;">
                    Ratio de congestión: {ratio:.2f}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════════════
# MAPA INTERACTIVO
# ════════════════════════════════════════════════════════════════════════════

def render_mapa_od(
    origen: dict | None,
    destino: dict | None,
    waypoints: list[tuple[float, float]],
    color: str = AZUL_MARINO,
    height: int = 400,
    capa_mapa: str = "estandar",
) -> dict | None:
    if not FOLIUM_OK:
        st.info("Instala `folium` y `streamlit-folium` para ver el mapa.")
        return None
    if origen and destino:
        centro = ((origen["lat"] + destino["lat"]) / 2,
                  (origen["lon"] + destino["lon"]) / 2)
        zoom   = 12
    elif origen:
        centro = (origen["lat"], origen["lon"]); zoom = 13
    elif destino:
        centro = (destino["lat"], destino["lon"]); zoom = 13
    else:
        centro = CDMX_CENTRO; zoom = 11

    _tile = "CartoDB dark_matter" if capa_mapa == "oscuro" else "OpenStreetMap"
    m = folium.Map(location=centro, zoom_start=zoom, tiles=_tile, prefer_canvas=True)

    if len(waypoints) >= 2:
        folium.PolyLine(locations=waypoints, color=color, weight=6, opacity=0.85,
                        tooltip="Trayecto activo").add_to(m)
        for i, wp in enumerate(waypoints[1:-1], 1):
            folium.CircleMarker(location=wp, radius=5, color=color,
                                fill=True, fill_color="white", fill_opacity=0.9,
                                weight=2.5, tooltip=f"Punto {i}").add_to(m)

    if origen:
        folium.Marker(
            location=[origen["lat"], origen["lon"]],
            icon=folium.DivIcon(html=f"""
                <div style="background:{VERDE};color:white;border-radius:50%;
                            width:30px;height:30px;display:flex;
                            align-items:center;justify-content:center;
                            font-weight:900;font-size:14px;
                            box-shadow:0 2px 8px rgba(0,0,0,0.4);">A</div>
            """),
            tooltip=f"Origen: {origen['nombre']}",
        ).add_to(m)

    if destino:
        folium.Marker(
            location=[destino["lat"], destino["lon"]],
            icon=folium.DivIcon(html=f"""
                <div style="background:{ROJO};color:white;border-radius:50%;
                            width:30px;height:30px;display:flex;
                            align-items:center;justify-content:center;
                            font-weight:900;font-size:14px;
                            box-shadow:0 2px 8px rgba(0,0,0,0.4);">B</div>
            """),
            tooltip=f"Destino: {destino['nombre']}",
        ).add_to(m)

    modo        = st.session_state.modo_click
    color_modo  = VERDE if modo == "A" else ROJO
    letra_modo  = "A (Origen)" if modo == "A" else "B (Destino)"
    instruccion = folium.Element(
        f"""
        <div style="position:absolute;top:10px;left:50%;transform:translateX(-50%);
                    background:white;padding:6px 14px;border-radius:20px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.25);z-index:1000;
                    font-family:sans-serif;font-size:13px;font-weight:600;
                    color:{color_modo};border:2px solid {color_modo};">
            📍 Próximo clic: Marcador {letra_modo}
        </div>
        """
    )
    m.get_root().html.add_child(instruccion)

    return st_folium(m, key="mapa_od", width="100%", height=height,
                     returned_objects=["last_clicked"])


# ════════════════════════════════════════════════════════════════════════════
# ÁREA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

# ── Mejora 2: cabecera con reloj y fecha ─────────────────────────────────────
_col_titulo, _col_reloj = st.columns([4, 1])
with _col_titulo:
    st.markdown("### 🗺️ Mapa interactivo — ZMVM")
with _col_reloj:
    _ahora = datetime.datetime.now()
    _MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                 "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    _DIAS_ES  = ["Lunes", "Martes", "Miércoles", "Jueves",
                 "Viernes", "Sábado", "Domingo"]
    _fecha_larga = (
        f"{_DIAS_ES[_ahora.weekday()]} {_ahora.day} "
        f"de {_MESES_ES[_ahora.month - 1]} de {_ahora.year}"
    )
    st.markdown(
        f"<div style='text-align:right;padding-top:6px;'>"
        f"<div style='font-size:1.4rem;font-weight:800;color:#F0F4F8;"
        f"line-height:1.1;'>{_ahora.strftime('%H:%M')}</div>"
        f"<div style='font-size:0.72rem;color:#B0C4DE;'>"
        f"{_fecha_larga}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

col_info, col_mapa = st.columns([1, 2], gap="large")

with col_info:
    st.markdown("#### Trayecto seleccionado")

    if origen_activo:
        st.markdown(
            f"<div style='padding:0.6rem 0.9rem;background:#E8F5F0;"
            f"border-left:4px solid {VERDE};border-radius:8px;margin-bottom:0.5rem;'>"
            f"<span style='font-size:0.75rem;color:#555;'>📍 ORIGEN (A)</span><br>"
            f"<b style='color:#1A6B4E;'>{origen_activo['nombre']}</b><br>"
            f"<span style='font-size:0.75rem;color:#888;'>"
            f"{origen_activo['lat']:.4f}, {origen_activo['lon']:.4f}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='padding:0.6rem 0.9rem;background:#F5F5F5;"
            f"border-left:4px solid #CCC;border-radius:8px;margin-bottom:0.5rem;'>"
            f"<span style='font-size:0.75rem;color:#AAA;'>📍 ORIGEN (A)</span><br>"
            f"<i style='color:#BBB;'>Sin definir</i></div>",
            unsafe_allow_html=True,
        )

    if destino_activo:
        st.markdown(
            f"<div style='padding:0.6rem 0.9rem;background:#FEF0F0;"
            f"border-left:4px solid {ROJO};border-radius:8px;margin-bottom:0.5rem;'>"
            f"<span style='font-size:0.75rem;color:#555;'>🏁 DESTINO (B)</span><br>"
            f"<b style='color:#8B0000;'>{destino_activo['nombre']}</b><br>"
            f"<span style='font-size:0.75rem;color:#888;'>"
            f"{destino_activo['lat']:.4f}, {destino_activo['lon']:.4f}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='padding:0.6rem 0.9rem;background:#F5F5F5;"
            f"border-left:4px solid #CCC;border-radius:8px;margin-bottom:0.5rem;'>"
            f"<span style='font-size:0.75rem;color:#AAA;'>🏁 DESTINO (B)</span><br>"
            f"<i style='color:#BBB;'>Sin definir</i></div>",
            unsafe_allow_html=True,
        )

    if corredor_activo:
        ratio_prev  = ratio_historico(hora_salida, dia_idx)
        estado_prev = ratio_a_estado(ratio_prev)
        nivel_prev, color_prev, etiq_prev = _nivel_riesgo(estado_prev, 0, 0)
        st.markdown(
            f"""
            | Campo | Valor |
            |---|---|
            | Distancia | **{dist_km_activo} km** |
            | Hora de salida | **{_hora:02d}:{_minutos:02d} h** |
            | Día | **{dia_nombre}** |
            | Modo | **{"API en tiempo real" if usar_api else "DEMO histórico"}** |
            """
        )
        st.markdown(
            f"<div style='background:{color_prev}18;border-left:4px solid {color_prev};"
            f"border-radius:8px;padding:0.7rem 1rem;margin-top:0.3rem;'>"
            f"<b style='color:{color_prev};'>{etiq_prev}</b><br>"
            f"<span style='font-size:0.8rem;color:#555;'>"
            f"Ratio histórico {_hora:02d}:{_minutos:02d}h {dia_nombre}: "
            f"<b>{ratio_prev:.2f}</b></span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Define origen y destino para ver la información del trayecto.")

    st.markdown(
        "<div style='font-size:0.72rem;color:#8BA7BE;text-transform:uppercase;"
        "letter-spacing:.05em;font-weight:600;margin-bottom:6px;'>"
        "Clic en mapa</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <style>
        button[aria-label="🟢"],
        button[aria-label="🔴"] {
            width: 52px !important; height: 52px !important;
            min-width: 52px !important; max-width: 52px !important;
            padding: 0 !important; font-size: 1.5rem !important;
            border-radius: 12px !important;
            display: flex !important; align-items: center !important;
            justify-content: center !important;
            color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    bcol1, bcol2, _ = st.columns([1, 1, 3], gap="small")
    with bcol1:
        activo_a = st.session_state.modo_click == "A"
        if st.button("🟢", key="btn_modo_a", help="Establecer origen (A)",
                     type="primary" if activo_a else "secondary"):
            st.session_state.modo_click = "A"
            st.rerun()
    with bcol2:
        activo_b = st.session_state.modo_click == "B"
        if st.button("🔴", key="btn_modo_b", help="Establecer destino (B)",
                     type="primary" if activo_b else "secondary"):
            st.session_state.modo_click = "B"
            st.rerun()

    if origen_activo or destino_activo:
        if st.button("🗑️ Limpiar selección", type="primary", use_container_width=True):
            st.session_state.origen              = None
            st.session_state.destino             = None
            st.session_state.ruta_rapida_origen  = None
            st.session_state.ruta_rapida_destino = None
            st.session_state.waypoints_activos   = None
            st.session_state.color_ruta          = AZUL_MARINO
            st.session_state.modo_click          = "A"
            st.session_state.ultimo_click        = None
            st.rerun()


with col_mapa:
    _modo_oscuro = st.checkbox("🌙 Mapa oscuro", value=False)
    st.session_state.capa_mapa = "oscuro" if _modo_oscuro else "estandar"
    st.markdown(
        """<style>
        iframe[title="streamlit_folium.st_folium"] {
            display: block !important;
            margin-bottom: 0 !important;
            margin-top: 0 !important;
        }
        [data-testid="stCustomComponentV1"] {
            line-height: 0 !important;
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    mapa_out = render_mapa_od(
        origen_activo, destino_activo, waypoints_activos,
        color=st.session_state.color_ruta,
        capa_mapa=st.session_state.capa_mapa,
    )
    if mapa_out and mapa_out.get("last_clicked"):
        click     = mapa_out["last_clicked"]
        click_key = (round(click["lat"], 5), round(click["lng"], 5))
        if click_key != st.session_state.ultimo_click:
            st.session_state.ultimo_click = click_key
            nombre_click = _reverse_geocode(click["lat"], click["lng"])
            punto = {"lat": click["lat"], "lon": click["lng"], "nombre": nombre_click}
            if st.session_state.modo_click == "A":
                st.session_state.origen             = punto
                st.session_state.ruta_rapida_origen = None
                st.session_state.waypoints_activos  = None
                st.session_state.color_ruta         = AZUL_MARINO
                st.session_state.modo_click         = "B"
            else:
                st.session_state.destino              = punto
                st.session_state.ruta_rapida_destino  = None
                st.session_state.waypoints_activos    = None
                st.session_state.modo_click           = "A"
            st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# RESULTADOS
# ════════════════════════════════════════════════════════════════════════════

if predecir and corredor_activo:

    with st.spinner("🔄 Calculando ruta y simulando 10,000 trayectorias..."):
        if usar_api and MODULOS_PIPELINE_OK:
            res = simular_modo_api(corredor_activo, hora_salida, dia_idx, n_sims)
            _resultados_rutas: list = []
        else:
            res = simular_modo_demo(
                corredor_activo, hora_salida, dia_idx, n_sims,
                tipo_vehiculo=tipo_vehiculo,
            )
            # Evaluación multi-ruta (sobre las alternativas obtenidas antes)
            _resultados_rutas = _simular_multi_ruta(
                _rutas_alternativas, hora_salida, dia_idx, n_sims, tipo_vehiculo,
            ) if _rutas_alternativas else []

    _NOMBRES_ESTADO = {0: "Fluido", 1: "Lento", 2: "Congestionado"}
    estado_nombre   = _NOMBRES_ESTADO[res["estado_inicial"]]
    nivel, color_nivel, etiq_nivel = _nivel_riesgo(res["estado_inicial"], res["p90"], res["p50"])

    origen_label  = origen_activo["nombre"] if origen_activo else "?"
    destino_label = destino_activo["nombre"] if destino_activo else "?"
    _fuente_ruta  = corredor_activo.get("fuente_ruta", "haversine_estimada")
    _icono_ruta   = "🛣️" if _fuente_ruta == "tomtom" else "📐"
    _tip_ruta     = ("ruta real TomTom" if _fuente_ruta == "tomtom" else "estimación Haversine×1.4")

    st.markdown(
        f"### Resultados · {origen_label} → {destino_label}  "
        f"<span style='font-size:0.85rem;color:#888;font-weight:400;'>"
        f"{_hora:02d}:{_minutos:02d} h · {dia_nombre} · "
        f"{_icono_ruta} {corredor_activo['distancia_km']} km "
        f"<span style='font-size:0.75rem;'>({_tip_ruta})</span></span>",
        unsafe_allow_html=True,
    )

    vel_media = corredor_activo["distancia_km"] / (res["p50"] / 60)
    st.markdown(
        f"""
        <div style="background:{AZUL_MARINO};border-radius:12px;
                    padding:1rem 1.5rem;margin-bottom:0.75rem;
                    display:flex;align-items:center;gap:2rem;">
            <div>
                <div style="color:#A8C7E8;font-size:0.8rem;
                            text-transform:uppercase;letter-spacing:.05em;">
                    Tiempo estimado (P50 · mediana)
                </div>
                <div style="color:white;font-size:2.6rem;font-weight:800;
                            line-height:1.1;margin-top:2px;">
                    {res['p50']:.0f} <span style="font-size:1.2rem;font-weight:400;">min</span>
                </div>
            </div>
            <div style="color:#A8C7E8;font-size:0.85rem;line-height:1.7;">
                Distancia: <b style="color:white;">{corredor_activo['distancia_km']} km</b><br>
                Velocidad media: <b style="color:white;">{vel_media:.1f} km/h</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _CARD = (
        "<div style='background:#112233;border:1px solid rgba(29,158,117,0.30);"
        "border-radius:10px;padding:1rem 1.2rem;min-width:160px;"
        "box-shadow:0 2px 10px rgba(0,0,0,0.30);'>"
        "<div style='font-size:12px;color:#8BA7BE;white-space:nowrap;"
        "text-transform:uppercase;letter-spacing:.04em;'>{label}</div>"
        "<div style='font-size:28px;font-weight:700;color:{vcolor};"
        "white-space:nowrap;line-height:1.2;margin-top:4px;'>{value}</div>"
        "<div style='font-size:13px;color:{dcolor};white-space:nowrap;"
        "margin-top:3px;'>{delta}</div>"
        "</div>"
    )
    m2, m3, m4, m5 = st.columns(4)
    with m2:
        delta_p10 = res["p10"] - res["p50"]
        st.markdown(_CARD.format(label="P10 · Optimista", value=f"{res['p10']:.0f} min",
                                  vcolor=VERDE, delta=f"{delta_p10:.0f} min vs P50", dcolor=VERDE),
                    unsafe_allow_html=True)
    with m3:
        delta_p90 = res["p90"] - res["p50"]
        st.markdown(_CARD.format(label="P90 · Pesimista", value=f"{res['p90']:.0f} min",
                                  vcolor=ROJO, delta=f"+{delta_p90:.0f} min vs P50", dcolor=ROJO),
                    unsafe_allow_html=True)
    with m4:
        banda = res["p90"] - res["p10"]
        st.markdown(_CARD.format(label="Banda P10 — P90", value=f"{banda:.0f} min",
                                  vcolor=AZUL_MARINO, delta="amplitud de incertidumbre", dcolor="#999"),
                    unsafe_allow_html=True)
    with m5:
        st.markdown(_CARD.format(label="Velocidad media", value=f"{vel_media:.1f} km/h",
                                  vcolor=AZUL_MARINO, delta=f"{corredor_activo['distancia_km']} km / P50",
                                  dcolor="#999"),
                    unsafe_allow_html=True)

    # ── Mejora 4: detección de compromiso de ruta ────────────────────────────
    VELOCIDAD_FLUJO_LIBRE = 35.0  # km/h referencia libre de tráfico
    _tiempo_fluido_min = corredor_activo["distancia_km"] / VELOCIDAD_FLUJO_LIBRE * 60
    _ratio_compromiso  = res["p50"] / _tiempo_fluido_min if _tiempo_fluido_min > 0 else 1.0
    if _ratio_compromiso >= 1.8:
        _gmaps_url = (
            f"https://www.google.com/maps/dir/{origen_activo['lat']},{origen_activo['lon']}/"
            f"{destino_activo['lat']},{destino_activo['lon']}"
        )
        st.warning(
            f"⚠️ **Trayecto muy comprometido** — El tiempo estimado (P50 = {res['p50']:.0f} min) "
            f"es **{_ratio_compromiso:.1f}×** el tiempo en vía libre ({_tiempo_fluido_min:.0f} min). "
            f"Considera rutas alternativas. [Ver en Google Maps]({_gmaps_url})"
        )
    elif _ratio_compromiso >= 1.4:
        st.info(
            f"ℹ️ **Tráfico moderado** — El tiempo estimado es **{_ratio_compromiso:.1f}×** "
            f"el tiempo en vía libre ({_tiempo_fluido_min:.0f} min)."
        )
    else:
        st.success(
            f"✅ **Condiciones favorables** — El trayecto fluye cerca de la velocidad libre "
            f"({_ratio_compromiso:.1f}× vs referencia de {_tiempo_fluido_min:.0f} min)."
        )

    st.divider()

    _, col_g, _ = st.columns([1, 3, 1])
    with col_g:
        st.plotly_chart(
            render_gauge(res["p50"], res["p10"], res["p90"], corredor_activo["distancia_km"]),
            use_container_width=True, config={"displayModeBar": False},
        )

    st.divider()

    _, col_s, _ = st.columns([1, 3, 1])
    with col_s:
        render_semaforo(nivel, etiq_nivel, res["ratio"], estado_nombre, color_nivel)

    st.divider()

    st.plotly_chart(
        render_banda_incertidumbre(res["p10"], res["p50"], res["p90"]),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.divider()

    st.plotly_chart(
        render_histograma(res["tiempos"], res["p10"], res["p50"], res["p90"]),
        use_container_width=True, config={"displayModeBar": False},
    )

    st.divider()

    # ── Mejora 5: Diagnóstico del tráfico ────────────────────────────────────
    with st.expander("📋 Diagnóstico del tráfico", expanded=False):
        _hora_pico = 7 <= int(hora_salida) <= 9 or 17 <= int(hora_salida) <= 20
        _razones: list[str] = []
        _razones.append(
            f"**Estado de tráfico inicial:** {estado_nombre} "
            f"(ratio de fluidez = {res['ratio']:.2f})"
        )
        if res.get("clima"):
            _fclima_val = safe_get(res.get("factor_clima"), "factor_multiplicador", 1.0)
            _razones.append(
                f"**Condición climática:** {safe_get(res['clima'], 'descripcion', '')} "
                f"(factor ×{_fclima_val:.2f})"
            )
        if res.get("perturbacion"):
            _razones.append(f"**Perturbación contextual:** factor ×{res.get('perturbacion', 1.0):.2f}")
        if _hora_pico:
            _razones.append(
                f"**Hora punta detectada** ({int(hora_salida):02d}:00 h) — "
                f"mayor probabilidad de congestión"
            )
        _razones.append(f"**Vehículo:** {tipo_vehiculo}")
        _razones.append(
            f"**Banda de incertidumbre P10–P90:** "
            f"{res['p10']:.0f} – {res['p90']:.0f} min "
            f"(amplitud {res['p90'] - res['p10']:.0f} min)"
        )
        for _r in _razones:
            st.markdown(f"- {_r}")

        st.markdown("---")
        _msg_cliente = (
            f"Hola, consulté tu trayecto {origen_activo['nombre']} → {destino_activo['nombre']} "
            f"para el {dia_nombre} a las {int(hora_salida):02d}:{(_minutos):02d} h.\n"
            f"Tiempo estimado (mediana): {res['p50']:.0f} min. "
            f"Rango probable: {res['p10']:.0f} – {res['p90']:.0f} min.\n"
            f"Estado del tráfico: {estado_nombre}. Vehículo: {tipo_vehiculo}.\n"
            f"Predicción generada por VialAI · UrbanFlow CDMX."
        )
        st.text_area(
            "💬 Mensaje listo para compartir",
            value=_msg_cliente,
            height=130,
            key="msg_cliente_diagnostico",
        )

    st.divider()

    if FOLIUM_OK and origen_activo and destino_activo:
        st.markdown(
            "<div style='font-size:0.85rem;font-weight:600;color:#444;"
            "margin-bottom:0.4rem;'>🗺️ Rutas en el mapa</div>",
            unsafe_allow_html=True,
        )
        _m = __import__("folium").Map(
            location=[origen_activo["lat"], origen_activo["lon"]],
            zoom_start=12, tiles="CartoDB positron",
        )
        # Dibujar rutas alternativas si hay evaluación multi-ruta
        if _resultados_rutas:
            for _rr in _resultados_rutas:
                if not _rr.waypoints:
                    continue
                if _rr.es_recomendada:
                    _rc, _rw, _ro = VERDE, 6, 0.9
                elif _rr.ratio_compromiso > 1.8:
                    _rc, _rw, _ro = COLOR_COMPROMETIDA, 3, 0.55
                else:
                    _rc = COLORES_RUTAS.get(_rr.indice, "#4A6FA5")
                    _rw, _ro = 3, 0.65
                __import__("folium").PolyLine(
                    locations=_rr.waypoints,
                    color=_rc, weight=_rw, opacity=_ro,
                    tooltip=f"{_rr.nombre}: P50={_rr.p50:.0f} min · IC={_rr.ic:.2f}",
                ).add_to(_m)
        elif len(corredor_activo["waypoints"]) >= 2:
            # Sin alternativas: dibujar ruta única
            __import__("folium").PolyLine(
                locations=corredor_activo["waypoints"],
                color=corredor_activo["color_mapa"],
                weight=6, opacity=0.85, tooltip="Ruta simulada",
            ).add_to(_m)
        for _pt, _ico, _bg in [(origen_activo, "A", VERDE), (destino_activo, "B", ROJO)]:
            __import__("folium").Marker(
                location=[_pt["lat"], _pt["lon"]],
                icon=__import__("folium").DivIcon(html=(
                    f"<div style='background:{_bg};color:white;"
                    f"border-radius:50%;width:28px;height:28px;"
                    f"display:flex;align-items:center;justify-content:center;"
                    f"font-weight:900;font-size:13px;"
                    f"box-shadow:0 2px 6px rgba(0,0,0,0.35);'>{_ico}</div>"
                )),
                tooltip=_pt["nombre"],
            ).add_to(_m)
        from streamlit_folium import st_folium as _stf
        _stf(_m, key="mapa_resultados", width="100%", height=320, returned_objects=[])
        st.divider()

    # ── Panel de comparación multi-ruta ──────────────────────────────────────
    if _resultados_rutas:
        st.subheader("🗺️ Comparación de rutas alternativas")

        if len(_resultados_rutas) == 1:
            st.caption(
                "ℹ️ TomTom no encontró rutas alternativas para este trayecto. "
                "Se muestra la ruta única disponible."
            )

        _cols_rutas = st.columns(max(len(_resultados_rutas), 1))
        for _ci, (_col_r, _rr) in enumerate(zip(_cols_rutas, _resultados_rutas)):
            with _col_r:
                _emoji_sem = {"verde": "🟢", "amarillo": "🟡", "rojo": "🔴"}.get(
                    _rr.semaforo, "⚪"
                )
                if _rr.es_recomendada:
                    st.success(f"⭐ {_rr.nombre}")
                elif _rr.ratio_compromiso > 1.8:
                    st.error(f"❌ {_rr.nombre}")
                else:
                    st.info(f"➡️ {_rr.nombre}")
                st.metric("P50", f"{_rr.p50:.0f} min")
                st.metric("Distancia", f"{_rr.distancia_km:.1f} km")
                st.metric("IC", f"{_rr.ic:.2f}", delta=_emoji_sem,
                          delta_color="off")
                if _rr.ratio_compromiso > 1.8:
                    st.caption(f"⚠️ {_rr.ratio_compromiso:.1f}× flujo libre")

        _mejor_rr = _resultados_rutas[0]
        _princ_rr = next((r for r in _resultados_rutas if r.indice == 0), _mejor_rr)
        if _mejor_rr.razon_recomendacion and len(_resultados_rutas) > 1:
            st.info(_mejor_rr.razon_recomendacion)

        # Mensaje de cambio de ruta para el cliente (solo si hay alternativas reales)
        if _mejor_rr.indice != 0 and MODULOS_EVALUADOR_OK:
            _expl = generar_explicacion_cambio_ruta(
                _mejor_rr, _princ_rr,
                condicion_clima=safe_get(res.get("clima"), "descripcion", ""),
            )
            st.text_area(
                "📱 Mensaje para tu cliente (cambio de ruta recomendado):",
                value=_expl,
                height=130,
                key="msg_cambio_ruta",
            )
        st.divider()

    st.caption(
        f"Predicción generada con {n_sims:,} trayectorias Monte Carlo · "
        f"Cadena de Markov calibrada con datos C5 CDMX 2023 · "
        f"P10/P50/P90 = percentiles 10, 50 y 90 de los tiempos simulados."
    )

    with st.expander("🔬 Detalles técnicos de la simulación", expanded=False):
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown(
                f"""
                <div style="font-size:0.85rem;color:#444;line-height:1.8;">
                    <b>Parámetros de simulación</b><br>
                    Trayectorias totales: <code>{n_sims:,}</code><br>
                    Completadas: <code>{n_sims - res['n_recortadas']:,}</code>
                    &nbsp;({(1 - res['n_recortadas'] / n_sims) * 100:.1f}%)<br>
                    Recortadas (timeout): <code>{res['n_recortadas']:,}</code><br>
                    Estado inicial Markov: <code>{estado_nombre}</code><br>
                    Modo de datos: <code>{"API tiempo real" if res['modo'] == 'api' else "DEMO histórico"}</code>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_d2:
            st.markdown(
                f"""
                <div style="font-size:0.85rem;color:#444;line-height:1.8;">
                    <b>Ruta calculada</b><br>
                    Distancia: <code>{corredor_activo['distancia_km']} km</code><br>
                    Fuente distancia: <code>{corredor_activo.get('fuente_ruta','?')}</code><br>
                    Tiempo base (sin tráfico):
                    <code>{corredor_activo.get('tiempo_base_min','?')} min</code><br>
                    Ratio congestión: <code>{res['ratio']:.3f}</code>
                </div>
                """,
                unsafe_allow_html=True,
            )
        if res.get("clima") and res.get("factor_clima"):
            clima  = res["clima"]
            fclima = res["factor_clima"]
            st.markdown(
                f"""
                <div style="background:#E8F5F1;border-radius:8px;
                            padding:0.7rem 1rem;font-size:0.83rem;
                            color:#1D6B52;margin-top:0.5rem;">
                    <b>🌤 Factor climático OWM</b> —
                    {clima.descripcion} ·
                    Factor: ×{fclima.factor_multiplicador:.2f} ·
                    Alerta: <b>{fclima.nivel_alerta}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

elif not (origen_activo and destino_activo):
    st.info(
        "**Cómo usar VialAI:**\n\n"
        "1. **Ruta rápida** — clic en uno de los 5 corredores del sidebar.\n"
        "2. **Selectbox** — escribe en los campos Origen / Destino para filtrar.\n"
        "3. **Clic en mapa** — usa los botones 🟢 A / 🔴 B y haz clic directamente "
        "sobre el mapa para fijar los puntos.\n\n"
        "Luego pulsa **🚀 Predecir trayecto**.",
        icon="🗺️",
    )
    st.markdown("""
---
#### 💡 Ejemplos de consulta

**Por voz** 🎤 (recomendado al volante):
> *"Llévame de la estación del Metro Cuatro Caminos al Aeropuerto
> Internacional de la Ciudad de México hoy 11 de abril a las 6 de la
> mañana."*

**Por texto** ⌨️:
> *"¿Cuánto tardo de Polanco a Santa Fe a las 7 PM viernes?"*

VialAI interpreta lenguaje natural: puedes mencionar origen, destino,
fecha y hora en la misma frase. Si omites la hora, se asume la actual.
""")


# ════════════════════════════════════════════════════════════════════════════
# PIE DE PÁGINA
# ════════════════════════════════════════════════════════════════════════════

st.markdown(
    "<div style='background:#0a1628;border-top:1px solid rgba(29,158,117,0.25);"
    "margin-top:3rem;padding:1.5rem 2rem 0.5rem;'>"
    "<div style='display:flex;align-items:center;gap:0.8rem;margin-bottom:1rem;'>"
    "<div style='font-size:1.5rem;font-weight:800;letter-spacing:-0.02em;'>"
    "<span style='color:#0C447C;'>Vial</span><span style='color:#1D9E75;'>AI</span>"
    "</div>"
    "<div style='color:#8BA7BE;font-size:0.8rem;line-height:1.4;'>"
    "Predicción estocástica de tiempos de viaje · ZMVM"
    "</div></div></div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div style='background:#0a1628;padding:0 2rem 0.5rem;'>"
    "<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:0.8rem;margin-bottom:1rem;'>"
    "<a href='https://es.wikipedia.org/wiki/Cadena_de_M%C3%A1rkov' target='_blank' style='text-decoration:none;'>"
    "<div style='background:#112233;border:1px solid rgba(29,158,117,0.25);border-radius:8px;padding:0.7rem 0.9rem;'>"
    "<div style='font-size:0.75rem;color:#1D9E75;font-weight:700;margin-bottom:3px;'>🔗 Cadenas de Markov</div>"
    "<div style='font-size:0.7rem;color:#8BA7BE;line-height:1.4;'>Modelo de transición entre estados de tráfico.</div>"
    "</div></a>"
    "<a href='https://es.wikipedia.org/wiki/M%C3%A9todo_de_Montecarlo' target='_blank' style='text-decoration:none;'>"
    "<div style='background:#112233;border:1px solid rgba(29,158,117,0.25);border-radius:8px;padding:0.7rem 0.9rem;'>"
    "<div style='font-size:0.75rem;color:#1D9E75;font-weight:700;margin-bottom:3px;'>🎲 Simulación Monte Carlo</div>"
    "<div style='font-size:0.7rem;color:#8BA7BE;line-height:1.4;'>10 000 trayectorias estocásticas.</div>"
    "</div></a>"
    "<a href='https://docs.scipy.org/doc/scipy/reference/stats.html' target='_blank' style='text-decoration:none;'>"
    "<div style='background:#112233;border:1px solid rgba(29,158,117,0.25);border-radius:8px;padding:0.7rem 0.9rem;'>"
    "<div style='font-size:0.75rem;color:#1D9E75;font-weight:700;margin-bottom:3px;'>📊 Distribuciones de probabilidad</div>"
    "<div style='font-size:0.7rem;color:#8BA7BE;line-height:1.4;'>Distribuciones Normal truncada con SciPy Stats.</div>"
    "</div></a>"
    "</div>"
    "<div style='text-align:center;font-size:0.72rem;color:#4A6070;"
    "border-top:1px solid rgba(255,255,255,0.06);padding:0.9rem 0 1rem;'>"
    "© 2026 VialAI · Diplomado en Ciencia de Datos · Datos: TomTom · OpenWeatherMap · C5 CDMX"
    "</div></div>",
    unsafe_allow_html=True,
)
