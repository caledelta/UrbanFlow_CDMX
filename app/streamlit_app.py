"""
VialAI — Interfaz Streamlit para predicción de tiempos de viaje en la ZMVM.

Arquitectura de la app
----------------------
sidebar  → logo + tagline + selector de corredor + controles de tiempo
main     → resultados: gauge P50 · banda P10-P90 · semáforo de riesgo
           mapa Folium del corredor · histograma de simulaciones

La app llama al PipelineIntegrador cuando hay API keys configuradas;
si no, usa el modo DEMO con datos precalibrados para que funcione
sin credenciales (ideal para presentaciones y desarrollo local).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ── Asegurar que el raíz del proyecto esté en sys.path ────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px

# ── Configuración de página (debe ser la primera llamada a Streamlit) ──
st.set_page_config(
    page_title="VialAI — Predicción de tráfico ZMVM",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Importaciones del proyecto (con manejo de errores) ────────────────
try:
    from src.simulation.markov_chain import MarkovTrafficChain, EstadoTrafico
    from src.simulation.monte_carlo import MonteCarloEngine, ConsultaViaje, VELOCIDAD_PARAMS
    MODULOS_SIMULACION_OK = True
except ImportError:
    MODULOS_SIMULACION_OK = False

try:
    from src.ingestion.tomtom_client import TomTomTrafficClient
    from src.ingestion.weather_client import (
        OpenWeatherMapClient, calcular_factor_congestion,
        ajustar_velocidades_por_clima,
    )
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
# CONSTANTES Y DATOS DE LOS CORREDORES
# ══════════════════════════════════════════════════════════════════════

AZUL_MARINO = "#0C447C"
VERDE       = "#1D9E75"
AMARILLO    = "#F5A623"
ROJO        = "#D0021B"

# Cinco corredores principales de la ZMVM
# Cada corredor define: nombre, distancia_km, coordenadas de waypoints,
# centroide para la consulta climática y perfil histórico de tiempo (min).
CORREDORES: dict[str, dict] = {
    "Insurgentes Sur · Del Valle → Indios Verdes": {
        "distancia_km": 22.5,
        "lat_clima": 19.4326,
        "lon_clima": -99.1700,
        "waypoints": [
            (19.3280, -99.1700),  # Perisur
            (19.3590, -99.1680),  # Insurgentes / Viaducto
            (19.3910, -99.1650),  # Benito Juárez
            (19.4200, -99.1620),  # Zona Rosa
            (19.4500, -99.1580),  # Buenavista
            (19.4960, -99.1540),  # Indios Verdes
        ],
        "color_mapa": "#0C447C",
        "descripcion": "22.5 km · Eje norte-sur · Pico vespertino 17-19 h",
    },
    "Viaducto · Observatorio → Aeropuerto": {
        "distancia_km": 18.0,
        "lat_clima": 19.3989,
        "lon_clima": -99.1200,
        "waypoints": [
            (19.4010, -99.2010),  # Observatorio
            (19.3989, -99.1700),  # Centro Médico
            (19.3989, -99.1332),  # Cuauhtémoc
            (19.3989, -99.1000),  # Aeropuerto oriente
            (19.4363, -99.0721),  # AICM Terminal 1
        ],
        "color_mapa": "#1D9E75",
        "descripcion": "18.0 km · Eje oriente-poniente · Ruta aeropuerto",
    },
    "Reforma · Santa Fe → Buenavista": {
        "distancia_km": 14.5,
        "lat_clima": 19.4326,
        "lon_clima": -99.1950,
        "waypoints": [
            (19.3620, -99.2760),  # Santa Fe
            (19.3950, -99.2500),  # Lomas
            (19.4200, -99.2000),  # Auditorio
            (19.4326, -99.1750),  # Ángel Independencia
            (19.4500, -99.1550),  # Buenavista
        ],
        "color_mapa": "#8B5CF6",
        "descripcion": "14.5 km · Paseo de la Reforma · Alto congestionamiento",
    },
    "Periférico Norte · Toreo → Cuatro Caminos": {
        "distancia_km": 12.0,
        "lat_clima": 19.5100,
        "lon_clima": -99.2200,
        "waypoints": [
            (19.5080, -99.2350),  # Toreo
            (19.5120, -99.2250),  # Tecnológico
            (19.5200, -99.2180),  # Las Arboledas
            (19.5250, -99.2100),  # Cuatro Caminos
        ],
        "color_mapa": "#F59E0B",
        "descripcion": "12.0 km · Corredor norte · Conecta Naucalpan–CDMX",
    },
    "Zaragoza · TAPO → Los Reyes": {
        "distancia_km": 16.5,
        "lat_clima": 19.4050,
        "lon_clima": -99.0500,
        "waypoints": [
            (19.4250, -99.1150),  # TAPO
            (19.4100, -99.0900),  # Pantitlán
            (19.3950, -99.0700),  # La Paz
            (19.3800, -99.0400),  # Los Reyes La Paz
        ],
        "color_mapa": "#EF4444",
        "descripcion": "16.5 km · Eje oriente · Alta densidad de incidentes",
    },
}

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves",
               "Viernes", "Sábado", "Domingo"]

# Perfil de congestión histórico por hora (0-23) para cada día tipo
# Valores: ratio de congestión promedio [0,1] basado en datos C5 + TomTom
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


def ratio_historico(hora: int, dia_idx: int) -> float:
    """Devuelve el ratio de congestión histórico para hora y día dados."""
    perfil = _PERFIL_FDS if dia_idx >= 5 else _PERFIL_HABIL
    return float(perfil[hora % 24])


def ratio_a_estado(ratio: float) -> int:
    """Convierte ratio_congestion → estado Markov (0=Fluido,1=Lento,2=Cong.)."""
    if ratio >= 0.75:
        return 0  # FLUIDO
    if ratio >= 0.45:
        return 1  # LENTO
    return 2      # CONGESTIONADO


# ══════════════════════════════════════════════════════════════════════
# CADENA DE MARKOV PRECALIBRADA (parámetros derivados del EDA)
# ══════════════════════════════════════════════════════════════════════

def _crear_cadena_calibrada() -> "MarkovTrafficChain":
    """
    Cadena de Markov calibrada con datos C5 CDMX 2023.
    Matriz derivada del notebook EDA_UrbanFlow_CDMX.ipynb (Sección 5).
    """
    if not MODULOS_SIMULACION_OK:
        return None
    P = np.array([
        [0.6820, 0.2510, 0.0670],   # FLUIDO      → FLUIDO/LENTO/CONG.
        [0.3150, 0.4820, 0.2030],   # LENTO       → FLUIDO/LENTO/CONG.
        [0.1020, 0.3480, 0.5500],   # CONGESTIONADO → FLUIDO/LENTO/CONG.
    ])
    serie_sintetica = np.array(
        [0]*70 + [1]*50 + [2]*40 + [1]*30 + [0]*60 + [2]*20 + [1]*30
    )
    cadena = MarkovTrafficChain()
    cadena.fit(serie_sintetica)
    # Reemplazar con la matriz calibrada del EDA
    cadena.transition_matrix_ = P
    return cadena


# ══════════════════════════════════════════════════════════════════════
# CSS PERSONALIZADO
# ══════════════════════════════════════════════════════════════════════

CSS = f"""
<style>
/* ── Fondo y tipografía ── */
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
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stRadio label {{
    color: #C8D8E8 !important;
    font-size: 0.85rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
[data-testid="stSidebar"] .stSelectbox > div > div {{
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.25);
    color: white !important;
    border-radius: 8px;
}}
/* ── Botón principal ── */
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
/* ── Métricas ── */
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
/* ── Sección de resultados ── */
.resultado-card {{
    background: white;
    border-radius: 14px;
    padding: 1.4rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.07);
    margin-bottom: 1rem;
}}
/* ── Semáforo ── */
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
.luz-verde   {{ background: #1D9E75; color: #1D9E75; }}
.luz-amarilla {{ background: #F5A623; color: #F5A623; }}
.luz-roja    {{ background: #D0021B; color: #D0021B; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════

with st.sidebar:

    # ── Logo y tagline ────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="text-align:center; padding: 1.2rem 0 0.6rem;">
            <div style="font-size:3rem; line-height:1;">🚦</div>
            <div style="font-size:1.9rem; font-weight:900;
                        color:white; letter-spacing:-0.02em;">
                VialAI
            </div>
            <div style="font-size:0.78rem; color:#A8C4D8;
                        font-style:italic; margin-top:0.2rem;">
                Predicción inteligente de tráfico en la ZMVM
            </div>
            <hr style="border-color:rgba(255,255,255,0.18);
                       margin:1rem 0 0.5rem;">
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Selector de corredor ──────────────────────────────────────────
    st.markdown("**Corredor vial**")
    nombre_corredor = st.selectbox(
        label="Corredor",
        options=list(CORREDORES.keys()),
        label_visibility="collapsed",
    )
    corredor = CORREDORES[nombre_corredor]
    st.caption(corredor["descripcion"])

    st.markdown("<hr style='border-color:rgba(255,255,255,0.15);'>",
                unsafe_allow_html=True)

    # ── Hora de salida ────────────────────────────────────────────────
    st.markdown("**Hora de salida**")
    hora_salida = st.slider(
        label="Hora",
        min_value=0,
        max_value=23,
        value=8,
        format="%02d:00 h",
        label_visibility="collapsed",
    )
    st.caption(f"Salida a las **{hora_salida:02d}:00 h**")

    # ── Día de la semana ──────────────────────────────────────────────
    st.markdown("**Día de la semana**")
    dia_nombre = st.selectbox(
        label="Día",
        options=DIAS_SEMANA,
        index=0,
        label_visibility="collapsed",
    )
    dia_idx = DIAS_SEMANA.index(dia_nombre)

    st.markdown("<hr style='border-color:rgba(255,255,255,0.15);'>",
                unsafe_allow_html=True)

    # ── Configuración avanzada (expander) ────────────────────────────
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
    predecir = st.button("🚀 Predecir trayecto", type="primary", use_container_width=True)

    # ── Footer del sidebar ────────────────────────────────────────────
    st.markdown(
        """
        <div style="position:fixed; bottom:1.2rem; left:0; width:17rem;
                    text-align:center; font-size:0.7rem; color:#6B9EC0;">
            UrbanFlow CDMX · Diplomado Ciencia de Datos<br>
            Motor: Monte Carlo + Cadenas de Markov
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════
# FUNCIONES DE SIMULACIÓN
# ══════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def obtener_cadena() -> "MarkovTrafficChain | None":
    """Carga (y cachea) la cadena de Markov calibrada."""
    return _crear_cadena_calibrada()


def simular_modo_demo(
    corredor: dict,
    hora: int,
    dia_idx: int,
    n_simulaciones: int,
) -> dict:
    """
    Simula el tiempo de viaje usando la cadena de Markov calibrada
    y los perfiles históricos de congestión (sin llamadas a APIs externas).

    Devuelve un dict con p10, p50, p90, media, std, estado y tiempos.
    """
    cadena = obtener_cadena()
    if cadena is None or not MODULOS_SIMULACION_OK:
        return _resultado_fallback(corredor, hora, dia_idx)

    # Inferir estado inicial desde perfil histórico
    ratio = ratio_historico(hora, dia_idx)
    estado_inicial = ratio_a_estado(ratio)

    # Ajustar velocidades según congestión histórica (sin API climática)
    # Usamos un factor sintético basado en el ratio para simular el efecto
    # de condiciones adversas en horas pico
    factor_congestion = 1.0 + max(0, (0.6 - ratio)) * 0.8  # 1.0–1.48
    params_ajustados = {
        k: {
            "media": max(round(v["media"] / factor_congestion, 2), 1.0),
            "std":   max(round(v["std"]   / factor_congestion, 2), 0.5),
            "min":   max(round(v["min"]   / factor_congestion, 2), 1.0),
            "max":   v["max"],
        }
        for k, v in VELOCIDAD_PARAMS.items()
    }

    try:
        motor = MonteCarloEngine(
            cadena,
            n_simulaciones=n_simulaciones,
            velocidad_params=params_ajustados,
            rng=np.random.default_rng(42),
        )
        consulta = ConsultaViaje(
            distancia_km=corredor["distancia_km"],
            estado_inicial=estado_inicial,
        )
        resultado = motor.correr(consulta)
        return {
            "p10":            round(resultado.p10, 1),
            "p50":            round(resultado.p50, 1),
            "p90":            round(resultado.p90, 1),
            "media":          round(resultado.media, 1),
            "std":            round(resultado.std, 1),
            "estado_inicial": estado_inicial,
            "ratio":          ratio,
            "tiempos":        resultado.tiempos_minutos,
            "n_recortadas":   resultado.n_recortadas,
            "modo":           "demo",
        }
    except Exception as e:
        st.warning(f"Error en simulación: {e}. Usando estimación simplificada.")
        return _resultado_fallback(corredor, hora, dia_idx)


def _resultado_fallback(corredor: dict, hora: int, dia_idx: int) -> dict:
    """Estimación determinista de respaldo cuando la simulación falla."""
    ratio  = ratio_historico(hora, dia_idx)
    vel    = 40 * ratio + 7 * (1 - ratio)   # interpolación simple
    p50    = round(corredor["distancia_km"] / vel * 60, 1)
    spread = p50 * 0.3
    rng    = np.random.default_rng(hora + dia_idx * 24)
    tiempos = rng.normal(p50, spread * 0.4, 1000).clip(p50 * 0.5, p50 * 2.5)
    return {
        "p10":            round(p50 - spread * 0.6, 1),
        "p50":            p50,
        "p90":            round(p50 + spread, 1),
        "media":          p50,
        "std":            round(spread * 0.4, 1),
        "estado_inicial": ratio_a_estado(ratio),
        "ratio":          ratio,
        "tiempos":        tiempos,
        "n_recortadas":   0,
        "modo":           "fallback",
    }


def simular_modo_api(corredor: dict, hora: int, dia_idx: int,
                     n_simulaciones: int) -> dict:
    """
    Obtiene predicción usando las APIs de TomTom y OpenWeatherMap en tiempo real.
    Requiere TOMTOM_API_KEY y OPENWEATHERMAP_API_KEY en variables de entorno.
    """
    from dotenv import load_dotenv
    load_dotenv()
    tomtom_key = os.getenv("TOMTOM_API_KEY", "")
    owm_key    = os.getenv("OPENWEATHERMAP_API_KEY", "")

    if not tomtom_key or not owm_key:
        st.warning(
            "APIs en tiempo real requieren `TOMTOM_API_KEY` y "
            "`OPENWEATHERMAP_API_KEY` en el archivo `.env`.\n\n"
            "Usando modo DEMO con datos históricos calibrados."
        )
        return simular_modo_demo(corredor, hora, dia_idx, n_simulaciones)

    try:
        tomtom = TomTomTrafficClient(api_key=tomtom_key, pausa_entre_lotes=0.3)
        owm    = OpenWeatherMapClient(api_key=owm_key)
        pipeline = PipelineIntegrador(tomtom, owm)
        cadena   = obtener_cadena()

        with st.spinner("Consultando TomTom Traffic API..."):
            ctx, resultado = pipeline.predecir_tiempo_viaje(
                coordenadas_corredor = corredor["waypoints"],
                lat_clima            = corredor["lat_clima"],
                lon_clima            = corredor["lon_clima"],
                distancia_km         = corredor["distancia_km"],
                cadena               = cadena,
                n_simulaciones       = n_simulaciones,
                rng                  = np.random.default_rng(42),
            )

        return {
            "p10":            round(resultado.p10, 1),
            "p50":            round(resultado.p50, 1),
            "p90":            round(resultado.p90, 1),
            "media":          round(resultado.media, 1),
            "std":            round(resultado.std, 1),
            "estado_inicial": ctx.estado_inicial,
            "ratio":          ctx.ratio_congestion_promedio,
            "tiempos":        resultado.tiempos_minutos,
            "n_recortadas":   resultado.n_recortadas,
            "modo":           "api",
            "clima":          ctx.clima,
            "factor_clima":   ctx.factor_climatico,
        }
    except Exception as e:
        st.warning(f"Error con APIs en tiempo real: {e}. Usando modo DEMO.")
        return simular_modo_demo(corredor, hora, dia_idx, n_simulaciones)


# ══════════════════════════════════════════════════════════════════════
# FUNCIONES DE VISUALIZACIÓN
# ══════════════════════════════════════════════════════════════════════

def _nivel_riesgo(estado: int, p90: float, p50: float) -> tuple[str, str, str]:
    """
    Clasifica el nivel de riesgo de congestionamiento.

    Devuelve (nivel, color_hex, etiqueta_es).
    """
    banda = p90 - p50
    if estado == 0 and banda < 15:
        return "verde",    VERDE,     "Tráfico fluido"
    if estado == 2 or banda > 30:
        return "rojo",     ROJO,      "Congestión severa"
    return "amarillo", AMARILLO,  "Tráfico moderado"


def render_gauge(p50: float, p10: float, p90: float, distancia_km: float) -> go.Figure:
    """
    Gauge circular con el tiempo P50 como valor central.
    El arco de fondo está coloreado en zonas: verde/amarillo/rojo.
    """
    max_val = max(p90 * 1.3, 90)

    fig = go.Figure(go.Indicator(
        mode  = "gauge+number+delta",
        value = p50,
        delta = {
            "reference":  distancia_km / 40 * 60,   # referencia: velocidad libre 40 km/h
            "suffix":     " min",
            "increasing": {"color": ROJO},
            "decreasing": {"color": VERDE},
        },
        number = {
            "suffix":    " min",
            "font":      {"size": 52, "color": AZUL_MARINO, "family": "Arial Black"},
        },
        title = {
            "text":  "Tiempo estimado P50<br><span style='font-size:0.8em;color:#888'>mediana de 5 000 simulaciones</span>",
            "font":  {"size": 15, "color": "#444"},
        },
        gauge = {
            "axis": {
                "range":     [0, max_val],
                "tickwidth": 1,
                "tickcolor": "#CCC",
                "tickfont":  {"size": 10},
            },
            "bar":      {"color": AZUL_MARINO, "thickness": 0.28},
            "bgcolor":  "white",
            "borderwidth": 0,
            "steps": [
                {"range": [0,        max_val * 0.40], "color": "#D4EFE4"},
                {"range": [max_val * 0.40, max_val * 0.70], "color": "#FEF3CD"},
                {"range": [max_val * 0.70, max_val],        "color": "#FADBD8"},
            ],
            "threshold": {
                "line":  {"color": AZUL_MARINO, "width": 3},
                "thickness": 0.85,
                "value": p50,
            },
        },
    ))
    fig.update_layout(
        height=280,
        margin=dict(t=30, b=0, l=20, r=20),
        paper_bgcolor="white",
        font={"family": "Arial"},
    )
    return fig


def render_banda_incertidumbre(p10: float, p50: float, p90: float) -> go.Figure:
    """
    Diagrama de banda horizontal P10–P50–P90.
    """
    fig = go.Figure()

    # Banda total P10–P90
    fig.add_shape(
        type="rect",
        x0=p10, x1=p90, y0=0.2, y1=0.8,
        fillcolor=f"rgba(12,68,124,0.15)",
        line=dict(color=AZUL_MARINO, width=1.5, dash="dot"),
    )
    # Banda P10–P50 (optimista)
    fig.add_shape(
        type="rect",
        x0=p10, x1=p50, y0=0.2, y1=0.8,
        fillcolor=f"rgba(29,158,117,0.25)",
        line=dict(width=0),
    )
    # Línea P50
    fig.add_shape(
        type="line",
        x0=p50, x1=p50, y0=0.05, y1=0.95,
        line=dict(color=AZUL_MARINO, width=3),
    )
    # Marcadores P10, P50, P90
    for val, etiq, col in [(p10, "P10", VERDE), (p50, "P50", AZUL_MARINO), (p90, "P90", ROJO)]:
        fig.add_trace(go.Scatter(
            x=[val], y=[0.5],
            mode="markers+text",
            marker=dict(size=14, color=col, symbol="diamond"),
            text=[f"<b>{etiq}</b><br>{val:.0f} min"],
            textposition="top center",
            textfont=dict(size=11, color=col),
            showlegend=False,
        ))

    fig.update_layout(
        height=160,
        margin=dict(t=30, b=20, l=10, r=10),
        xaxis=dict(
            title="Tiempo de viaje (minutos)",
            range=[max(0, p10 - 10), p90 + 10],
            showgrid=True, gridcolor="#EEE",
        ),
        yaxis=dict(visible=False, range=[0, 1]),
        paper_bgcolor="white",
        plot_bgcolor="white",
        title=dict(
            text="Banda de incertidumbre P10 – P50 – P90",
            font=dict(size=13, color="#444"),
            x=0.5,
        ),
    )
    return fig


def render_histograma(tiempos: np.ndarray, p10: float,
                      p50: float, p90: float) -> go.Figure:
    """
    Histograma de la distribución completa de tiempos simulados.
    """
    fig = go.Figure()

    # Histograma principal
    fig.add_trace(go.Histogram(
        x=tiempos,
        nbinsx=60,
        marker_color=f"rgba(12,68,124,0.65)",
        marker_line=dict(color="white", width=0.3),
        name="Simulaciones",
        hovertemplate="Tiempo: %{x:.1f} min<br>Frecuencia: %{y}<extra></extra>",
    ))

    # Líneas de percentiles
    for val, etiq, col, dash in [
        (p10, "P10", VERDE,      "dash"),
        (p50, "P50", AZUL_MARINO, "solid"),
        (p90, "P90", ROJO,       "dash"),
    ]:
        fig.add_vline(
            x=val, line_color=col, line_width=2.5,
            line_dash=dash,
            annotation_text=f"<b>{etiq}: {val:.0f} min</b>",
            annotation_position="top",
            annotation_font=dict(size=11, color=col),
        )

    fig.update_layout(
        title=dict(
            text=f"Distribución de {len(tiempos):,} tiempos simulados",
            font=dict(size=13, color="#444"), x=0.5,
        ),
        xaxis_title="Tiempo de viaje (minutos)",
        yaxis_title="Frecuencia",
        paper_bgcolor="white",
        plot_bgcolor="white",
        height=280,
        margin=dict(t=40, b=40, l=40, r=20),
        bargap=0.05,
        showlegend=False,
    )
    fig.update_xaxes(showgrid=True, gridcolor="#EEE")
    fig.update_yaxes(showgrid=True, gridcolor="#EEE")
    return fig


def render_mapa(corredor: dict, nombre_corredor: str) -> None:
    """
    Mapa Folium del corredor con:
    - Polilínea del trayecto coloreada por corredor
    - Marcadores de inicio (A) y fin (B)
    - Popup con información del corredor
    """
    if not FOLIUM_OK:
        st.info("Instala `folium` y `streamlit-folium` para ver el mapa.")
        return

    waypoints = corredor["waypoints"]
    centro    = (
        np.mean([w[0] for w in waypoints]),
        np.mean([w[1] for w in waypoints]),
    )
    color_ruta = corredor["color_mapa"]

    m = folium.Map(
        location   = centro,
        zoom_start = 12,
        tiles      = "CartoDB positron",
    )

    # Polilínea del corredor
    folium.PolyLine(
        locations  = waypoints,
        color      = color_ruta,
        weight     = 6,
        opacity    = 0.85,
        tooltip    = nombre_corredor,
        popup      = folium.Popup(
            f"<b>{nombre_corredor}</b><br>"
            f"Distancia: {corredor['distancia_km']} km<br>"
            f"{corredor['descripcion']}",
            max_width=280,
        ),
    ).add_to(m)

    # Marcador de inicio
    folium.Marker(
        location  = waypoints[0],
        icon      = folium.DivIcon(html=f"""
            <div style="background:{VERDE};color:white;
                        border-radius:50%;width:28px;height:28px;
                        display:flex;align-items:center;justify-content:center;
                        font-weight:bold;font-size:13px;
                        box-shadow:0 2px 6px rgba(0,0,0,0.35);">A</div>
        """),
        tooltip   = "Punto de origen",
    ).add_to(m)

    # Marcador de destino
    folium.Marker(
        location  = waypoints[-1],
        icon      = folium.DivIcon(html=f"""
            <div style="background:{ROJO};color:white;
                        border-radius:50%;width:28px;height:28px;
                        display:flex;align-items:center;justify-content:center;
                        font-weight:bold;font-size:13px;
                        box-shadow:0 2px 6px rgba(0,0,0,0.35);">B</div>
        """),
        tooltip   = "Punto de destino",
    ).add_to(m)

    # Waypoints intermedios
    for i, wp in enumerate(waypoints[1:-1], start=1):
        folium.CircleMarker(
            location    = wp,
            radius      = 5,
            color       = color_ruta,
            fill        = True,
            fill_color  = "white",
            fill_opacity= 0.9,
            weight      = 2.5,
            tooltip     = f"Punto {i}",
        ).add_to(m)

    st_folium(m, width="100%", height=360, returned_objects=[])


def render_semaforo(nivel: str, etiqueta: str, ratio: float,
                    estado_nombre: str) -> None:
    """
    Semáforo de riesgo con tres luces y texto de estado.
    """
    activa_verde    = "activa" if nivel == "verde"    else ""
    activa_amarilla = "activa" if nivel == "amarillo" else ""
    activa_roja     = "activa" if nivel == "rojo"     else ""

    st.markdown(
        f"""
        <div class="semaforo-container">
            <div style="display:flex;flex-direction:column;gap:6px;">
                <div class="luz luz-roja {activa_roja}"></div>
                <div class="luz luz-amarilla {activa_amarilla}"></div>
                <div class="luz luz-verde {activa_verde}"></div>
            </div>
            <div style="margin-left:0.8rem;">
                <div style="font-size:1.15rem;font-weight:800;
                            color:{AZUL_MARINO};">{etiqueta}</div>
                <div style="font-size:0.85rem;color:#666;margin-top:2px;">
                    Estado de tráfico: <b>{estado_nombre}</b>
                </div>
                <div style="font-size:0.78rem;color:#999;margin-top:2px;">
                    Ratio de congestión: {ratio:.2f}
                    &nbsp;·&nbsp; 1.0 = flujo libre
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════
# ÁREA PRINCIPAL — estado inicial (antes de predecir)
# ══════════════════════════════════════════════════════════════════════

# Encabezado principal
st.markdown(
    f"""
    <h1 style="color:{AZUL_MARINO}; font-size:1.9rem;
               font-weight:900; margin-bottom:0.2rem;">
        🚦 VialAI
        <span style="font-size:1rem; font-weight:400;
                     color:#666; margin-left:0.5rem;">
            Predicción de tiempos de viaje · ZMVM
        </span>
    </h1>
    <p style="color:#888; font-size:0.9rem; margin-top:0;">
        Motor estocástico: <b>Monte Carlo + Cadenas de Markov</b> ·
        {n_sims:,} simulaciones por consulta ·
        Bandas de incertidumbre P10/P50/P90
    </p>
    <hr style="border-color:#E0E0E0; margin:0.5rem 0 1rem;">
    """,
    unsafe_allow_html=True,
)

# ── Vista previa del corredor (siempre visible) ───────────────────────
col_info, col_mapa = st.columns([1, 2], gap="large")

with col_info:
    st.markdown(f"#### {nombre_corredor}")
    st.markdown(
        f"""
        | Campo | Valor |
        |---|---|
        | Distancia | **{corredor['distancia_km']} km** |
        | Waypoints | **{len(corredor['waypoints'])} puntos** |
        | Hora seleccionada | **{hora_salida:02d}:00 h** |
        | Día | **{dia_nombre}** |
        | Modo | **{"API en tiempo real" if usar_api else "DEMO (datos históricos)"}** |
        """
    )
    ratio_prev = ratio_historico(hora_salida, dia_idx)
    estado_prev = ratio_a_estado(ratio_prev)
    nombres_estado = {0: "Fluido", 1: "Lento", 2: "Congestionado"}
    nivel_prev, color_prev, etiq_prev = _nivel_riesgo(estado_prev, 0, 0)
    st.markdown(
        f"""
        <div style="background:{color_prev}18; border-left:4px solid {color_prev};
                    border-radius:8px; padding:0.8rem 1rem; margin-top:0.5rem;">
            <b style="color:{color_prev};">{etiq_prev}</b><br>
            <span style="font-size:0.82rem;color:#555;">
                Ratio histórico {hora_salida:02d}h {dia_nombre}: <b>{ratio_prev:.2f}</b>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with col_mapa:
    render_mapa(corredor, nombre_corredor)


# ══════════════════════════════════════════════════════════════════════
# RESULTADOS — se muestran tras presionar el botón
# ══════════════════════════════════════════════════════════════════════

if predecir:

    # ── Ejecutar simulación ───────────────────────────────────────────
    with st.spinner("Ejecutando simulación Monte Carlo..."):
        if usar_api and MODULOS_PIPELINE_OK:
            res = simular_modo_api(corredor, hora_salida, dia_idx, n_sims)
        else:
            res = simular_modo_demo(corredor, hora_salida, dia_idx, n_sims)

    nombres_estado_map = {0: "Fluido", 1: "Lento", 2: "Congestionado"}
    estado_nombre = nombres_estado_map[res["estado_inicial"]]
    nivel, color_nivel, etiq_nivel = _nivel_riesgo(
        res["estado_inicial"], res["p90"], res["p50"]
    )

    st.markdown("---")
    st.markdown(
        f"### Resultados · {nombre_corredor}  "
        f"<span style='font-size:0.85rem;color:#888;font-weight:400;'>"
        f"{hora_salida:02d}:00 h · {dia_nombre}</span>",
        unsafe_allow_html=True,
    )

    # ── Fila de métricas resumen ──────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("P50 — Mediana", f"{res['p50']:.0f} min")
    with m2:
        st.metric("P10 — Optimista", f"{res['p10']:.0f} min",
                  delta=f"{res['p10'] - res['p50']:.0f} min",
                  delta_color="normal")
    with m3:
        st.metric("P90 — Pesimista", f"{res['p90']:.0f} min",
                  delta=f"+{res['p90'] - res['p50']:.0f} min",
                  delta_color="inverse")
    with m4:
        st.metric("Banda P10–P90", f"{res['p90'] - res['p10']:.0f} min")
    with m5:
        vel_media = corredor["distancia_km"] / (res["p50"] / 60)
        st.metric("Velocidad media", f"{vel_media:.1f} km/h")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Gauge + semáforo ──────────────────────────────────────────────
    col_gauge, col_sem = st.columns([1.6, 1], gap="large")

    with col_gauge:
        with st.container():
            st.plotly_chart(
                render_gauge(res["p50"], res["p10"], res["p90"],
                             corredor["distancia_km"]),
                use_container_width=True,
                config={"displayModeBar": False},
            )

    with col_sem:
        st.markdown("<br><br>", unsafe_allow_html=True)
        render_semaforo(nivel, etiq_nivel, res["ratio"], estado_nombre)
        st.markdown("<br>", unsafe_allow_html=True)

        # Información adicional de la simulación
        st.markdown(
            f"""
            <div style="background:#F0F4F8; border-radius:10px;
                        padding:0.9rem 1rem; font-size:0.82rem; color:#555;">
                <b>Detalles de la simulación</b><br>
                Simulaciones: <b>{n_sims:,}</b><br>
                Trayectorias completadas: <b>{n_sims - res['n_recortadas']:,}</b>
                ({(1 - res['n_recortadas']/n_sims)*100:.1f}%)<br>
                Estado inicial Markov: <b>{estado_nombre}</b><br>
                Modo: <b>{"API tiempo real" if res['modo']=='api' else "DEMO histórico"}</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Mostrar info climática si está disponible (modo API)
        if res.get("clima") and res.get("factor_clima"):
            clima = res["clima"]
            fclima = res["factor_clima"]
            st.markdown(
                f"""
                <div style="background:#E8F5F1; border-radius:10px;
                            padding:0.9rem 1rem; font-size:0.82rem;
                            color:#1D6B52; margin-top:0.5rem;">
                    <b>☁️ Factor climático OWM</b><br>
                    Condición: {clima.descripcion}<br>
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

    # ── Histograma de simulaciones ────────────────────────────────────
    st.plotly_chart(
        render_histograma(res["tiempos"], res["p10"], res["p50"], res["p90"]),
        use_container_width=True,
        config={"displayModeBar": False},
    )

    # ── Nota al pie ───────────────────────────────────────────────────
    st.caption(
        f"Predicción generada con {n_sims:,} trayectorias Monte Carlo sobre "
        f"la cadena de Markov calibrada con datos C5 CDMX 2023. "
        f"Bandas P10/P50/P90 representan el percentil 10, 50 y 90 de la "
        f"distribución simulada de tiempos de viaje."
    )

else:
    # ── Placeholder cuando aún no se ha predicho ─────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.info(
        "👈 **Selecciona un corredor, hora de salida y día de la semana "
        "en el panel izquierdo y presiona '🚀 Predecir trayecto'.**",
        icon="🚦",
    )
    st.markdown(
        f"""
        <div style="text-align:center; padding:2rem; color:#AAA;">
            <div style="font-size:4rem;">🗺️</div>
            <div style="font-size:1rem; margin-top:0.5rem;">
                VialAI predice el tiempo de viaje con bandas de incertidumbre<br>
                P10 · P50 · P90 usando simulación Monte Carlo
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
