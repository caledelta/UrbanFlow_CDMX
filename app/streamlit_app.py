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

import math
import os
import sys
from pathlib import Path

# ── Raíz del proyecto en sys.path ─────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ── Configuración de página (primera llamada a Streamlit) ──────────────
st.set_page_config(
    page_title="VialAI — Predicción de tráfico ZMVM",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Importaciones del proyecto ─────────────────────────────────────────
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
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False


# ══════════════════════════════════════════════════════════════════════
# CONSTANTES DE COLOR
# ══════════════════════════════════════════════════════════════════════

AZUL_MARINO = "#0C447C"
VERDE       = "#1D9E75"
AMARILLO    = "#F5A623"
ROJO        = "#D0021B"


# ══════════════════════════════════════════════════════════════════════
# CATÁLOGO DE PUNTOS CONOCIDOS DE LA ZMVM
# ── Usado para autocompletado en los selectbox de Origen / Destino ──
# ══════════════════════════════════════════════════════════════════════

OPCION_MAPA = "— Elegir en el mapa —"

# (lat, lon) WGS84 — ~80 puntos representativos
PUNTOS_CDMX: dict[str, tuple[float, float]] = {
    # ── Hitos y monumentos ────────────────────────────────────────────
    "Zócalo · Plaza de la Constitución":        (19.4326, -99.1332),
    "Ángel de la Independencia":                (19.4270, -99.1676),
    "Monumento a la Revolución":                (19.4385, -99.1573),
    "Castillo de Chapultepec":                  (19.4204, -99.1897),
    "Basílica de Guadalupe":                    (19.4848, -99.1175),
    "Estadio Azteca":                           (19.3031, -99.1506),
    "Palacio de los Deportes":                  (19.4089, -99.0866),
    "Plaza Garibaldi":                          (19.4425, -99.1381),
    "Arena México":                             (19.4281, -99.1470),
    # ── Aeropuertos y terminales de transporte ────────────────────────
    "AICM Terminal 1":                          (19.4363, -99.0721),
    "AICM Terminal 2":                          (19.4345, -99.0785),
    "TAPO · Terminal Oriente":                  (19.4255, -99.1139),
    "Terminal Poniente":                        (19.4019, -99.2050),
    "Terminal Norte":                           (19.4832, -99.1286),
    "Terminal Sur · Tasqueña":                  (19.3704, -99.1380),
    "Reforma · Buenavista":                     (19.4500, -99.1550),
    "Buenavista · Tren Suburbano":              (19.4508, -99.1546),
    # ── Corredores viales (extremos de las 5 rutas frecuentes) ────────
    "Insurgentes Sur · Perisur":                (19.3280, -99.1700),
    "Insurgentes Norte · Indios Verdes":        (19.4960, -99.1540),
    "Viaducto · Observatorio":                  (19.4010, -99.2010),
    "Periférico Norte · Toreo":                 (19.5080, -99.2350),
    "Cuatro Caminos":                           (19.5250, -99.2100),
    "Los Reyes La Paz":                         (19.3800, -99.0400),
    # ── Centros universitarios ────────────────────────────────────────
    "Ciudad Universitaria · UNAM":              (19.3318, -99.1873),
    "IPN · Zacatenco":                          (19.5041, -99.1331),
    "UAM Azcapotzalco":                         (19.4876, -99.1879),
    "UAM Iztapalapa":                           (19.3588, -99.0575),
    # ── Hospitales ────────────────────────────────────────────────────
    "Hospital General de México":               (19.4112, -99.1551),
    "IMSS · CMN Siglo XXI":                     (19.3950, -99.1600),
    "Hospital ABC · Observatorio":              (19.4010, -99.2016),
    "Hospital Infantil de México":              (19.4175, -99.1538),
    # ── Centros comerciales y hubs ────────────────────────────────────
    "Santa Fe · Centro Comercial":              (19.3620, -99.2760),
    "Polanco · Presidente Masaryk":             (19.4318, -99.1949),
    "Perisur · Centro Comercial":               (19.3039, -99.1849),
    "Antara Fashion Hall":                      (19.4820, -99.1969),
    "Parque Delta":                             (19.3940, -99.1554),
    # ── Parques y bosques ─────────────────────────────────────────────
    "Bosque de Chapultepec · Entrada":          (19.4207, -99.1965),
    "Parque Bicentenario":                      (19.4808, -99.2091),
    "Parque España · Condesa":                  (19.4190, -99.1700),
    # ── Colonias y alcaldías ──────────────────────────────────────────
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
    # ── Metro (estaciones clave) ──────────────────────────────────────
    "Metro Pantitlán":                          (19.4150, -99.0726),
    "Metro Observatorio":                       (19.4003, -99.2010),
    "Metro Indios Verdes":                      (19.4963, -99.1154),
    "Metro Tasqueña":                           (19.3702, -99.1388),
    "Metro Universidad":                        (19.3272, -99.1736),
    "Metro Cuatro Caminos":                     (19.5070, -99.2175),
    "Metro Balderas":                           (19.4295, -99.1500),
    "Metro Insurgentes":                        (19.4202, -99.1614),
    # ── Municipios conurbados (EDOMEX) ────────────────────────────────
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

# Opciones para selectbox (opción mapa + lista ordenada)
_OPCIONES_OD = [OPCION_MAPA] + sorted(PUNTOS_CDMX.keys())


# ══════════════════════════════════════════════════════════════════════
# CINCO CORREDORES PRINCIPALES — usados como "Rutas frecuentes"
# ══════════════════════════════════════════════════════════════════════

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
        "descripcion":   "12.0 km · Corredor norte · Conecta Naucalpan–CDMX",
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

# Perfil de congestión histórico por hora (0-23)
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

CDMX_CENTRO = (19.4326, -99.1332)   # centro por defecto del mapa


def ratio_historico(hora: int, dia_idx: int) -> float:
    perfil = _PERFIL_FDS if dia_idx >= 5 else _PERFIL_HABIL
    return float(perfil[hora % 24])


def ratio_a_estado(ratio: float) -> int:
    if ratio >= 0.75:
        return 0
    if ratio >= 0.45:
        return 1
    return 2


# ══════════════════════════════════════════════════════════════════════
# UTILIDADES GEOGRÁFICAS
# ══════════════════════════════════════════════════════════════════════

def calcular_distancia(lat1: float, lon1: float,
                       lat2: float, lon2: float) -> float:
    """
    Distancia geodésica entre dos puntos en km (fórmula de Haversine).
    Usa geopy si está disponible; si no, implementación propia.
    """
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
    """
    Genera n puntos interpolados linealmente entre origen y destino.
    Sirve para construir la polilínea del mapa y pasarla al pipeline.
    """
    fracs = np.linspace(0, 1, n)
    return [(lat1 + f * (lat2 - lat1), lon1 + f * (lon2 - lon1))
            for f in fracs]


# ══════════════════════════════════════════════════════════════════════
# CADENA DE MARKOV PRECALIBRADA
# ══════════════════════════════════════════════════════════════════════

def _crear_cadena_calibrada() -> "MarkovTrafficChain | None":
    """Cadena de Markov calibrada con datos C5 CDMX 2023 (EDA Sección 5)."""
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


# ══════════════════════════════════════════════════════════════════════
# CSS PERSONALIZADO
# ══════════════════════════════════════════════════════════════════════

CSS = f"""
<style>
[data-testid="stAppViewContainer"] {{
    background: #F8F9FB;
}}
[data-testid="stSidebar"] {{
    background: {AZUL_MARINO};
}}
[data-testid="stSidebar"] * {{
    color: white !important;
}}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stSlider label {{
    color: #C8D8E8 !important;
    font-size: 0.85rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
[data-testid="stSidebar"] .stSelectbox > div > div {{
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 8px;
}}
/* Botones de ruta rápida en sidebar */
[data-testid="stSidebar"] div.stButton > button {{
    background: rgba(255,255,255,0.10);
    color: white !important;
    border: 1px solid rgba(255,255,255,0.22);
    border-radius: 8px;
    font-size: 0.82rem;
    padding: 0.35rem 0.6rem;
    width: 100%;
    text-align: left;
    transition: background 0.15s;
}}
[data-testid="stSidebar"] div.stButton > button:hover {{
    background: rgba(255,255,255,0.22);
}}
/* Botón principal Predecir */
div.stButton > button[kind="primary"] {{
    background: {VERDE};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6rem 1.4rem;
    font-size: 1rem;
    font-weight: 700;
    width: 100%;
    transition: background 0.2s;
}}
div.stButton > button[kind="primary"]:hover {{
    background: #17866A;
}}
/* Botones de modo mapa (A / B) */
.modo-btn-activo {{
    background: {AZUL_MARINO} !important;
    color: white !important;
    border-radius: 8px;
    padding: 0.4rem 1rem;
    font-weight: 700;
    border: 2px solid white !important;
}}
[data-testid="stMetric"] {{
    background: white;
    border-radius: 12px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
[data-testid="stMetricValue"] {{
    color: {AZUL_MARINO};
    font-size: 2rem !important;
    font-weight: 800;
}}
.semaforo-container {{
    display: flex;
    gap: 0.7rem;
    align-items: center;
    background: white;
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.07);
}}
.luz {{
    width: 44px; height: 44px;
    border-radius: 50%;
    opacity: 0.18;
    transition: opacity 0.3s;
}}
.luz.activa {{ opacity: 1.0; box-shadow: 0 0 16px 4px currentColor; }}
.luz-verde    {{ background: #1D9E75; color: #1D9E75; }}
.luz-amarilla {{ background: #F5A623; color: #F5A623; }}
.luz-roja     {{ background: #D0021B; color: #D0021B; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# INICIALIZACIÓN DEL SESSION STATE
# — Debe ejecutarse antes de cualquier widget ─
# ══════════════════════════════════════════════════════════════════════

_DEFAULTS: dict = {
    # Punto de origen: {"lat", "lon", "nombre"} | None
    "origen":  None,
    # Punto de destino: {"lat", "lon", "nombre"} | None
    "destino": None,
    # Modo de colocación del próximo clic en el mapa: "A" o "B"
    "modo_click": "A",
    # Último clic procesado (evita re-procesar el mismo clic en reruns)
    "ultimo_click": None,
    # Waypoints activos (de ruta rápida) | None → se interpolan
    "waypoints_activos": None,
    # Color de ruta activa
    "color_ruta": AZUL_MARINO,
    # Selectbox origen y destino (controlados programáticamente)
    "sel_origen":  OPCION_MAPA,
    "sel_destino": OPCION_MAPA,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════

with st.sidebar:

    # ── Logo y tagline ────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="text-align:center; padding:1.2rem 0 0.6rem;">
            <div style="font-size:3rem; line-height:1;">🚦</div>
            <div style="font-size:1.9rem; font-weight:900;
                        color:white; letter-spacing:-0.02em;">VialAI</div>
            <div style="font-size:0.78rem; color:#A8C4D8;
                        font-style:italic; margin-top:0.2rem;">
                Predicción inteligente de tráfico en la ZMVM
            </div>
            <hr style="border-color:rgba(255,255,255,0.18);margin:1rem 0 0.5rem;">
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── ⚡ Rutas frecuentes ────────────────────────────────────────────
    # Los 5 corredores predefinidos como acceso rápido.
    # Al hacer clic se pre-rellenan origen, destino y waypoints.
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:4px;'>"
        "⚡ Rutas frecuentes</div>",
        unsafe_allow_html=True,
    )
    for nombre_ruta, datos_ruta in CORREDORES.items():
        etiqueta = f"{datos_ruta['icono']} {nombre_ruta.split('·')[0].strip()}"
        if st.button(etiqueta, key=f"btn_{nombre_ruta[:20]}"):
            # Fijar selectboxes al origen y destino de la ruta
            st.session_state.sel_origen  = datos_ruta["origen_key"]
            st.session_state.sel_destino = datos_ruta["destino_key"]
            # Fijar coordenadas directamente
            lat_o, lon_o = PUNTOS_CDMX[datos_ruta["origen_key"]]
            lat_d, lon_d = PUNTOS_CDMX[datos_ruta["destino_key"]]
            st.session_state.origen  = {"lat": lat_o, "lon": lon_o,
                                         "nombre": datos_ruta["origen_key"]}
            st.session_state.destino = {"lat": lat_d, "lon": lon_d,
                                         "nombre": datos_ruta["destino_key"]}
            st.session_state.waypoints_activos = datos_ruta["waypoints"]
            st.session_state.color_ruta        = datos_ruta["color_mapa"]
            st.session_state.modo_click        = "A"  # resetear modo

    st.markdown("<hr style='border-color:rgba(255,255,255,0.15);'>",
                unsafe_allow_html=True)

    # ── 📍 Origen ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:4px;'>"
        "📍 Origen</div>",
        unsafe_allow_html=True,
    )
    sel_origen = st.selectbox(
        label="Origen",
        options=_OPCIONES_OD,
        key="sel_origen",
        label_visibility="collapsed",
    )
    # Sincronizar selectbox → session state (si el usuario elige un punto)
    if sel_origen != OPCION_MAPA:
        lat_o, lon_o = PUNTOS_CDMX[sel_origen]
        st.session_state.origen = {"lat": lat_o, "lon": lon_o,
                                    "nombre": sel_origen}
        st.session_state.waypoints_activos = None  # invalidar waypoints fijos

    # Mostrar coordenadas activas
    if st.session_state.origen:
        o = st.session_state.origen
        st.markdown(
            f"<div style='font-size:0.75rem;color:#7EC8A4;margin-top:2px;'>"
            f"✅ {o['nombre']}<br>"
            f"<span style='color:#8AADCA;'>{o['lat']:.4f}, {o['lon']:.4f}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Sin fijar — elige del mapa o de la lista")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 🏁 Destino ────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:4px;'>"
        "🏁 Destino</div>",
        unsafe_allow_html=True,
    )
    sel_destino = st.selectbox(
        label="Destino",
        options=_OPCIONES_OD,
        key="sel_destino",
        label_visibility="collapsed",
    )
    if sel_destino != OPCION_MAPA:
        lat_d, lon_d = PUNTOS_CDMX[sel_destino]
        st.session_state.destino = {"lat": lat_d, "lon": lon_d,
                                     "nombre": sel_destino}
        st.session_state.waypoints_activos = None

    if st.session_state.destino:
        d = st.session_state.destino
        st.markdown(
            f"<div style='font-size:0.75rem;color:#E88;margin-top:2px;'>"
            f"✅ {d['nombre']}<br>"
            f"<span style='color:#8AADCA;'>{d['lat']:.4f}, {d['lon']:.4f}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("Sin fijar — elige del mapa o de la lista")

    # ── Distancia calculada ───────────────────────────────────────────
    st.markdown("<hr style='border-color:rgba(255,255,255,0.15);'>",
                unsafe_allow_html=True)

    origen_activo  = st.session_state.origen
    destino_activo = st.session_state.destino

    if origen_activo and destino_activo:
        dist_km = calcular_distancia(
            origen_activo["lat"],  origen_activo["lon"],
            destino_activo["lat"], destino_activo["lon"],
        )
        st.markdown(
            f"<div style='text-align:center;padding:0.5rem;background:rgba(29,158,117,0.2);"
            f"border-radius:8px;font-size:0.9rem;color:white;'>"
            f"📏 Distancia: <b>{dist_km} km</b></div>",
            unsafe_allow_html=True,
        )
    else:
        dist_km = None
        st.markdown(
            "<div style='text-align:center;padding:0.4rem;background:rgba(255,255,255,0.07);"
            "border-radius:8px;font-size:0.8rem;color:#8AADCA;'>"
            "📏 Define origen y destino para calcular la distancia</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='border-color:rgba(255,255,255,0.15);'>",
                unsafe_allow_html=True)

    # ── Hora de salida ────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-bottom:4px;'>"
        "🕐 Hora de salida</div>",
        unsafe_allow_html=True,
    )
    hora_salida = st.slider(
        label="Hora", min_value=0, max_value=23, value=8,
        format="%02d:00 h", label_visibility="collapsed",
    )
    st.caption(f"Salida a las **{hora_salida:02d}:00 h**")

    # ── Día de la semana ──────────────────────────────────────────────
    st.markdown(
        "<div style='font-size:0.78rem;color:#A8C4D8;text-transform:uppercase;"
        "letter-spacing:.06em;font-weight:600;margin-top:0.5rem;margin-bottom:4px;'>"
        "📅 Día de la semana</div>",
        unsafe_allow_html=True,
    )
    dia_nombre = st.selectbox(
        label="Día", options=DIAS_SEMANA, index=0,
        label_visibility="collapsed",
    )
    dia_idx = DIAS_SEMANA.index(dia_nombre)

    st.markdown("<hr style='border-color:rgba(255,255,255,0.15);'>",
                unsafe_allow_html=True)

    # ── Configuración avanzada ────────────────────────────────────────
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

    # ── Botón principal ───────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    boton_deshabilitado = not (origen_activo and destino_activo)
    predecir = st.button(
        "🚀 Predecir trayecto",
        type="primary",
        use_container_width=True,
        disabled=boton_deshabilitado,
    )
    if boton_deshabilitado:
        st.caption("↑ Define origen y destino para habilitar")

    # ── Footer ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="position:fixed;bottom:1.2rem;left:0;width:17rem;
                    text-align:center;font-size:0.7rem;color:#6B9EC0;">
            UrbanFlow CDMX · Diplomado Ciencia de Datos<br>
            Motor: Monte Carlo + Cadenas de Markov
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════
# CONSTRUCCIÓN DE corredor_activo (fuente de verdad para la simulación)
# ══════════════════════════════════════════════════════════════════════

if origen_activo and destino_activo:
    # Calcular distancia final (puede que ya se calculó arriba, pero es barata)
    dist_km_activo = calcular_distancia(
        origen_activo["lat"],  origen_activo["lon"],
        destino_activo["lat"], destino_activo["lon"],
    )
    # Waypoints: usar los de la ruta rápida si existen, si no interpolar
    if st.session_state.waypoints_activos:
        waypoints_activos = st.session_state.waypoints_activos
    else:
        waypoints_activos = interpolar_waypoints(
            origen_activo["lat"],  origen_activo["lon"],
            destino_activo["lat"], destino_activo["lon"],
            n=6,
        )

    corredor_activo: dict | None = {
        "distancia_km": dist_km_activo,
        "lat_clima":    origen_activo["lat"],
        "lon_clima":    origen_activo["lon"],
        "waypoints":    waypoints_activos,
        "color_mapa":   st.session_state.color_ruta,
        "descripcion":  (f"{origen_activo['nombre']} → {destino_activo['nombre']} "
                         f"· {dist_km_activo} km"),
    }
else:
    corredor_activo = None
    dist_km_activo  = None
    waypoints_activos = []


# ══════════════════════════════════════════════════════════════════════
# FUNCIONES DE SIMULACIÓN (sin cambios respecto a la versión anterior)
# ══════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def obtener_cadena() -> "MarkovTrafficChain | None":
    """Carga y cachea la cadena de Markov calibrada."""
    return _crear_cadena_calibrada()


def simular_modo_demo(corredor: dict, hora: int, dia_idx: int,
                      n_simulaciones: int) -> dict:
    """
    Simulación con cadena de Markov calibrada y perfiles históricos de
    congestión (sin llamadas a APIs externas).
    """
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


def _resultado_fallback(corredor: dict, hora: int, dia_idx: int) -> dict:
    """Estimación determinista de respaldo."""
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


def simular_modo_api(corredor: dict, hora: int, dia_idx: int,
                     n_simulaciones: int) -> dict:
    """Predicción con APIs TomTom + OWM en tiempo real."""
    from dotenv import load_dotenv
    load_dotenv()
    tomtom_key = os.getenv("TOMTOM_API_KEY", "")
    owm_key    = os.getenv("OPENWEATHERMAP_API_KEY", "")

    if not tomtom_key or not owm_key:
        st.warning("Faltan API keys — usando modo DEMO.")
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
        st.warning(f"Error API: {e} — usando modo DEMO.")
        return simular_modo_demo(corredor, hora, dia_idx, n_simulaciones)


# ══════════════════════════════════════════════════════════════════════
# FUNCIONES DE VISUALIZACIÓN
# ══════════════════════════════════════════════════════════════════════

def _nivel_riesgo(estado: int, p90: float, p50: float) -> tuple[str, str, str]:
    banda = p90 - p50
    if estado == 0 and banda < 15:
        return "verde",    VERDE,    "Tráfico fluido"
    if estado == 2 or banda > 30:
        return "rojo",     ROJO,     "Congestión severa"
    return "amarillo", AMARILLO, "Tráfico moderado"


def render_gauge(p50: float, p10: float, p90: float,
                 distancia_km: float) -> go.Figure:
    max_val = max(p90 * 1.3, 90)
    fig = go.Figure(go.Indicator(
        mode   = "gauge+number+delta",
        value  = p50,
        delta  = {"reference": distancia_km / 40 * 60, "suffix": " min",
                  "increasing": {"color": ROJO}, "decreasing": {"color": VERDE}},
        number = {"suffix": " min",
                  "font": {"size": 52, "color": AZUL_MARINO, "family": "Arial Black"}},
        title  = {"text": "Tiempo estimado P50<br>"
                           "<span style='font-size:0.8em;color:#888'>"
                           "mediana de las simulaciones</span>",
                  "font": {"size": 15, "color": "#444"}},
        gauge  = {
            "axis": {"range": [0, max_val], "tickwidth": 1,
                     "tickcolor": "#CCC", "tickfont": {"size": 10}},
            "bar":  {"color": AZUL_MARINO, "thickness": 0.28},
            "bgcolor": "white", "borderwidth": 0,
            "steps": [
                {"range": [0,               max_val * 0.40], "color": "#D4EFE4"},
                {"range": [max_val * 0.40,  max_val * 0.70], "color": "#FEF3CD"},
                {"range": [max_val * 0.70,  max_val],        "color": "#FADBD8"},
            ],
            "threshold": {"line": {"color": AZUL_MARINO, "width": 3},
                          "thickness": 0.85, "value": p50},
        },
    ))
    fig.update_layout(height=280, margin=dict(t=30, b=0, l=20, r=20),
                      paper_bgcolor="white", font={"family": "Arial"})
    return fig


def render_banda_incertidumbre(p10: float, p50: float,
                                p90: float) -> go.Figure:
    fig = go.Figure()
    fig.add_shape(type="rect", x0=p10, x1=p90, y0=0.2, y1=0.8,
                  fillcolor="rgba(12,68,124,0.15)",
                  line=dict(color=AZUL_MARINO, width=1.5, dash="dot"))
    fig.add_shape(type="rect", x0=p10, x1=p50, y0=0.2, y1=0.8,
                  fillcolor="rgba(29,158,117,0.25)", line=dict(width=0))
    fig.add_shape(type="line", x0=p50, x1=p50, y0=0.05, y1=0.95,
                  line=dict(color=AZUL_MARINO, width=3))
    for val, etiq, col in [(p10, "P10", VERDE), (p50, "P50", AZUL_MARINO),
                            (p90, "P90", ROJO)]:
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
                   showgrid=True, gridcolor="#EEE"),
        yaxis=dict(visible=False, range=[0, 1]),
        paper_bgcolor="white", plot_bgcolor="white",
        title=dict(text="Banda de incertidumbre P10 – P50 – P90",
                   font=dict(size=13, color="#444"), x=0.5),
    )
    return fig


def render_histograma(tiempos: np.ndarray, p10: float,
                      p50: float, p90: float) -> go.Figure:
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
                   font=dict(size=13, color="#444"), x=0.5),
        xaxis_title="Tiempo de viaje (minutos)", yaxis_title="Frecuencia",
        paper_bgcolor="white", plot_bgcolor="white",
        height=280, margin=dict(t=40, b=40, l=40, r=20),
        bargap=0.05, showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEE")
    return fig


def render_semaforo(nivel: str, etiqueta: str, ratio: float,
                    estado_nombre: str) -> None:
    av = "activa" if nivel == "verde"    else ""
    aa = "activa" if nivel == "amarillo" else ""
    ar = "activa" if nivel == "rojo"     else ""
    st.markdown(
        f"""
        <div class="semaforo-container">
            <div style="display:flex;flex-direction:column;gap:6px;">
                <div class="luz luz-roja {ar}"></div>
                <div class="luz luz-amarilla {aa}"></div>
                <div class="luz luz-verde {av}"></div>
            </div>
            <div style="margin-left:0.8rem;">
                <div style="font-size:1.15rem;font-weight:800;
                            color:{AZUL_MARINO};">{etiqueta}</div>
                <div style="font-size:0.85rem;color:#666;margin-top:2px;">
                    Estado Markov: <b>{estado_nombre}</b>
                </div>
                <div style="font-size:0.78rem;color:#999;margin-top:2px;">
                    Ratio congestión: {ratio:.2f} · 1.0 = flujo libre
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════
# MAPA INTERACTIVO (origen-destino con clic)
# ══════════════════════════════════════════════════════════════════════

def render_mapa_od(
    origen:    dict | None,
    destino:   dict | None,
    waypoints: list[tuple[float, float]],
    color:     str = AZUL_MARINO,
) -> dict | None:
    """
    Mapa Folium interactivo con soporte de clic para fijar origen (A)
    y destino (B).

    Devuelve el dict de salida de st_folium (contiene `last_clicked`).
    """
    if not FOLIUM_OK:
        st.info("Instala `folium` y `streamlit-folium` para ver el mapa.")
        return None

    # Calcular centro y zoom
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

    m = folium.Map(location=centro, zoom_start=zoom,
                   tiles="CartoDB positron",
                   prefer_canvas=True)

    # Polilínea del trayecto (sólo si hay al menos 2 puntos)
    if len(waypoints) >= 2:
        folium.PolyLine(
            locations=waypoints, color=color,
            weight=6, opacity=0.85,
            tooltip="Trayecto activo",
        ).add_to(m)

        # Puntos intermedios (si la ruta es de un corredor predefinido)
        for i, wp in enumerate(waypoints[1:-1], 1):
            folium.CircleMarker(
                location=wp, radius=5, color=color,
                fill=True, fill_color="white", fill_opacity=0.9,
                weight=2.5, tooltip=f"Punto {i}",
            ).add_to(m)

    # Marcador de origen (A) — verde
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

    # Marcador de destino (B) — rojo
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

    # Instrucción flotante dentro del mapa
    modo = st.session_state.modo_click
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

    return st_folium(
        m,
        key="mapa_od",
        width="100%",
        height=400,
        returned_objects=["last_clicked"],
    )


# ══════════════════════════════════════════════════════════════════════
# ÁREA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════

# ── Encabezado ────────────────────────────────────────────────────────
st.markdown(
    f"""
    <h1 style="color:{AZUL_MARINO};font-size:1.9rem;
               font-weight:900;margin-bottom:0.2rem;">
        🚦 VialAI
        <span style="font-size:1rem;font-weight:400;color:#666;margin-left:0.5rem;">
            Predicción de tiempos de viaje · ZMVM
        </span>
    </h1>
    <p style="color:#888;font-size:0.9rem;margin-top:0;">
        Motor estocástico: <b>Monte Carlo + Cadenas de Markov</b> ·
        {n_sims:,} simulaciones por consulta · Bandas P10/P50/P90
    </p>
    <hr style="border-color:#E0E0E0;margin:0.5rem 0 1rem;">
    """,
    unsafe_allow_html=True,
)

# ── Layout: panel de info (izq) + mapa (der) ──────────────────────────
col_info, col_mapa = st.columns([1, 2], gap="large")

with col_info:
    st.markdown("#### Trayecto seleccionado")

    # Origen
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

    # Destino
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

    # Distancia + hora/día + estado previsto
    if corredor_activo:
        ratio_prev  = ratio_historico(hora_salida, dia_idx)
        estado_prev = ratio_a_estado(ratio_prev)
        nivel_prev, color_prev, etiq_prev = _nivel_riesgo(estado_prev, 0, 0)
        st.markdown(
            f"""
            | Campo | Valor |
            |---|---|
            | Distancia | **{dist_km_activo} km** |
            | Hora de salida | **{hora_salida:02d}:00 h** |
            | Día | **{dia_nombre}** |
            | Modo | **{"API en tiempo real" if usar_api else "DEMO histórico"}** |
            """
        )
        st.markdown(
            f"<div style='background:{color_prev}18;border-left:4px solid {color_prev};"
            f"border-radius:8px;padding:0.7rem 1rem;margin-top:0.3rem;'>"
            f"<b style='color:{color_prev};'>{etiq_prev}</b><br>"
            f"<span style='font-size:0.8rem;color:#555;'>"
            f"Ratio histórico {hora_salida:02d}h {dia_nombre}: "
            f"<b>{ratio_prev:.2f}</b></span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Define origen y destino para ver la información del trayecto.")

    # ── Botones para cambiar modo del clic en el mapa ─────────────────
    st.markdown("<br>**Modo de clic en el mapa:**", unsafe_allow_html=True)
    bcol1, bcol2 = st.columns(2)
    with bcol1:
        activo_a = st.session_state.modo_click == "A"
        if st.button(
            f"{'▶' if activo_a else '○'} 📍 Origen (A)",
            key="btn_modo_a",
            type="primary" if activo_a else "secondary",
            use_container_width=True,
        ):
            st.session_state.modo_click = "A"
            st.rerun()
    with bcol2:
        activo_b = st.session_state.modo_click == "B"
        if st.button(
            f"{'▶' if activo_b else '○'} 🏁 Destino (B)",
            key="btn_modo_b",
            type="primary" if activo_b else "secondary",
            use_container_width=True,
        ):
            st.session_state.modo_click = "B"
            st.rerun()

    # Botón para limpiar selección
    if origen_activo or destino_activo:
        if st.button("🗑️ Limpiar selección", use_container_width=True):
            st.session_state.origen           = None
            st.session_state.destino          = None
            st.session_state.sel_origen       = OPCION_MAPA
            st.session_state.sel_destino      = OPCION_MAPA
            st.session_state.waypoints_activos = None
            st.session_state.color_ruta       = AZUL_MARINO
            st.session_state.modo_click       = "A"
            st.session_state.ultimo_click     = None
            st.rerun()


with col_mapa:
    # Renderizar mapa y capturar clic
    mapa_out = render_mapa_od(
        origen_activo,
        destino_activo,
        waypoints_activos,
        color=st.session_state.color_ruta,
    )

    # ── Procesar clic en el mapa ──────────────────────────────────────
    # Compara el clic actual con el último procesado para evitar repetición.
    if mapa_out and mapa_out.get("last_clicked"):
        click      = mapa_out["last_clicked"]
        click_key  = (round(click["lat"], 5), round(click["lng"], 5))

        if click_key != st.session_state.ultimo_click:
            st.session_state.ultimo_click = click_key
            nombre_click = f"{click['lat']:.4f}, {click['lng']:.4f}"
            punto = {"lat": click["lat"], "lon": click["lng"],
                     "nombre": nombre_click}

            if st.session_state.modo_click == "A":
                st.session_state.origen       = punto
                st.session_state.sel_origen   = OPCION_MAPA
                st.session_state.waypoints_activos = None
                st.session_state.color_ruta   = AZUL_MARINO
                # Auto-avanzar al modo B para que el siguiente clic fije destino
                st.session_state.modo_click   = "B"
            else:
                st.session_state.destino      = punto
                st.session_state.sel_destino  = OPCION_MAPA
                st.session_state.waypoints_activos = None
                # Volver a modo A para permitir redefinir origen
                st.session_state.modo_click   = "A"

            st.rerun()


# ══════════════════════════════════════════════════════════════════════
# RESULTADOS — se muestran tras presionar "Predecir trayecto"
# ══════════════════════════════════════════════════════════════════════

if predecir and corredor_activo:

    with st.spinner("Ejecutando simulación Monte Carlo..."):
        if usar_api and MODULOS_PIPELINE_OK:
            res = simular_modo_api(corredor_activo, hora_salida, dia_idx, n_sims)
        else:
            res = simular_modo_demo(corredor_activo, hora_salida, dia_idx, n_sims)

    _NOMBRES_ESTADO = {0: "Fluido", 1: "Lento", 2: "Congestionado"}
    estado_nombre   = _NOMBRES_ESTADO[res["estado_inicial"]]
    nivel, color_nivel, etiq_nivel = _nivel_riesgo(
        res["estado_inicial"], res["p90"], res["p50"]
    )

    st.markdown("---")
    origen_label  = origen_activo["nombre"] if origen_activo else "?"
    destino_label = destino_activo["nombre"] if destino_activo else "?"
    st.markdown(
        f"### Resultados · {origen_label} → {destino_label}  "
        f"<span style='font-size:0.85rem;color:#888;font-weight:400;'>"
        f"{hora_salida:02d}:00 h · {dia_nombre} · "
        f"{corredor_activo['distancia_km']} km</span>",
        unsafe_allow_html=True,
    )

    # ── 5 métricas resumen ────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("P50 — Mediana", f"{res['p50']:.0f} min")
    with m2:
        st.metric("P10 — Optimista", f"{res['p10']:.0f} min",
                  delta=f"{res['p10'] - res['p50']:.0f} min", delta_color="normal")
    with m3:
        st.metric("P90 — Pesimista", f"{res['p90']:.0f} min",
                  delta=f"+{res['p90'] - res['p50']:.0f} min", delta_color="inverse")
    with m4:
        st.metric("Banda P10–P90", f"{res['p90'] - res['p10']:.0f} min")
    with m5:
        vel_media = corredor_activo["distancia_km"] / (res["p50"] / 60)
        st.metric("Velocidad media", f"{vel_media:.1f} km/h")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Gauge + semáforo ──────────────────────────────────────────────
    col_gauge, col_sem = st.columns([1.6, 1], gap="large")

    with col_gauge:
        st.plotly_chart(
            render_gauge(res["p50"], res["p10"], res["p90"],
                         corredor_activo["distancia_km"]),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    with col_sem:
        st.markdown("<br><br>", unsafe_allow_html=True)
        render_semaforo(nivel, etiq_nivel, res["ratio"], estado_nombre)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="background:#F0F4F8;border-radius:10px;
                        padding:0.9rem 1rem;font-size:0.82rem;color:#555;">
                <b>Detalles de la simulación</b><br>
                Simulaciones: <b>{n_sims:,}</b><br>
                Completadas: <b>{n_sims - res['n_recortadas']:,}</b>
                ({(1 - res['n_recortadas'] / n_sims) * 100:.1f}%)<br>
                Estado inicial Markov: <b>{estado_nombre}</b><br>
                Modo: <b>{"API tiempo real" if res['modo'] == 'api' else "DEMO histórico"}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if res.get("clima") and res.get("factor_clima"):
            clima  = res["clima"]
            fclima = res["factor_clima"]
            st.markdown(
                f"""
                <div style="background:#E8F5F1;border-radius:10px;
                            padding:0.9rem 1rem;font-size:0.82rem;
                            color:#1D6B52;margin-top:0.5rem;">
                    <b>☁️ Factor climático OWM</b><br>
                    {clima.descripcion}<br>
                    Factor: ×{fclima.factor_multiplicador:.2f}
                    · Alerta: <b>{fclima.nivel_alerta}</b>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ── Banda de incertidumbre ────────────────────────────────────────
    st.plotly_chart(
        render_banda_incertidumbre(res["p10"], res["p50"], res["p90"]),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    # ── Histograma ────────────────────────────────────────────────────
    st.plotly_chart(
        render_histograma(res["tiempos"], res["p10"], res["p50"], res["p90"]),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    st.caption(
        f"Predicción generada con {n_sims:,} trayectorias Monte Carlo sobre "
        f"la cadena de Markov calibrada con datos C5 CDMX 2023. "
        f"Bandas P10/P50/P90 = percentiles 10, 50 y 90 de los tiempos simulados."
    )

elif not (origen_activo and destino_activo):
    # ── Estado inicial: instrucciones ─────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.info(
        "**Cómo usar VialAI:**\n\n"
        "1. **Ruta rápida** → clic en uno de los 5 corredores del sidebar.\n"
        "2. **Selectbox** → escribe en los campos Origen / Destino para filtrar.\n"
        "3. **Clic en mapa** → usa los botones 📍 A / B y haz clic directamente "
        "sobre el mapa para fijar los puntos.\n\n"
        "Luego pulsa **🚀 Predecir trayecto**.",
        icon="🗺️",
    )
