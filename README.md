# 🚦 UrbanFlow CDMX / VialAI

**Sistema de Predicción Estocástica de Tiempos de Viaje en la ZMVM**

[![Tests](https://img.shields.io/badge/tests-720%20passing-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.14-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

Proyecto Integrador Final del **Diplomado en Ciencia de Datos**
FES Acatlán · UNAM · Abril 2026

**Autor:** Carlos Armando López Encino

---

## 📖 ¿Qué es UrbanFlow CDMX?

UrbanFlow CDMX es un sistema de **predicción probabilística** de tiempos de viaje para la Zona Metropolitana del Valle de México que combina:

- **Cadenas de Markov** de 3 estados (Fluido / Lento / Congestionado) para modelar la dinámica del tráfico
- **Simulación Monte Carlo** vectorizada de 10,000 trayectorias por consulta
- **Catálogo de 11 perturbaciones contextuales** específicas de la ZMVM (cierres del Metro, manifestaciones, eventos masivos, festivos patrios)
- **Agente conversacional VialAI** basado en la API de Anthropic que traduce los resultados numéricos a recomendaciones accionables en lenguaje natural

A diferencia de Google Maps, Waze o TomTom, que entregan una **estimación puntual** del tiempo de viaje, VialAI entrega una **distribución completa de probabilidad** con bandas $P_{10}$, $P_{50}$, $P_{90}$ y un **Índice de Confiabilidad (IC)** que resume la volatilidad de cada ruta en un semáforo verde/amarillo/rojo.

---

## 🎯 Resultados de validación

Validado contra la API de TomTom Routing como *ground truth* sobre 30 rutas representativas de la ZMVM en horario pico matutino:

| Métrica | Valor |
|---|---|
| **MAPE del $P_{50}$ (VialAI)** | **11.9 %** |
| MAPE del ETA (TomTom Routing) | 19.0 % |
| **Ventaja de VialAI sobre TomTom** | **+7.1 puntos porcentuales** |
| **Cobertura empírica banda $P_{10}$-$P_{90}$** | **93.3 %** |
| Cobertura nominal esperada | 80.0 % |
| MAE del $P_{50}$ | 4.8 min |
| Latencia por consulta | < 500 ms |

**VialAI no solo cuantifica la incertidumbre (algo que TomTom no hace): también es más preciso en su estimación central que el líder comercial del mercado.**

---

## 🏗️ Arquitectura

```
UrbanFlow_CDMX/
├── src/
│   ├── simulation/
│   │   ├── markov_chain.py       # MarkovTrafficChain
│   │   ├── monte_carlo.py        # MonteCarloEngine vectorizado
│   │   └── evaluador_rutas.py    # Comparación de rutas alternativas
│   ├── ingestion/
│   │   ├── tomtom_client.py      # TomTom Traffic Stats
│   │   ├── tomtom_routing.py     # TomTom Routing API
│   │   ├── weather_client.py     # OpenWeatherMap
│   │   ├── c5_client.py          # Portal de datos abiertos CDMX
│   │   └── pipeline.py           # Orquestador ETL
│   ├── agent/
│   │   ├── agent.py              # VialAIAgent (tool use loop)
│   │   ├── perturbaciones.py     # Catálogo de 11 eventos contextuales
│   │   ├── tools.py              # Herramientas expuestas al LLM
│   │   ├── prompts.py            # System prompts
│   │   └── voice_io.py           # Síntesis de voz (TTS)
│   ├── core/
│   │   ├── rutas_personalizadas.py  # Gestión de rutas del usuario
│   │   ├── recompensa.py            # Sistema de recompensa silenciosa
│   │   ├── telemetria.py            # Analytics y feedback
│   │   └── iconos_mapa.py           # Iconos contextuales de mapa
│   └── models/
│       └── schemas.py            # Modelos Pydantic
├── app/
│   └── streamlit_app.py          # Dashboard interactivo
├── tests/                        # 720 tests con pytest
├── notebooks/
│   ├── UrbanFlow_CDMX_Colab.ipynb     # Notebook reproducible (entregable)
│   └── archive/                       # EDA de desarrollo (v1, v2, v3)
├── docs/
│   ├── proyecto_ZMCDMX_v3.pdf                # Artículo técnico (23 pp)
│   ├── UrbanFlow_CDMX_Presentacion.pptx      # Presentación (16 slides)
│   ├── VialAI_Pitch_B2B.pdf                  # Pitch comercial B2B (4 pp)
│   └── Inventario_Proyecto.pdf               # Inventario del proyecto
├── data/                         # Caches locales (ignorado por git)
├── requirements.txt
├── .env.example                  # Plantilla de variables de entorno
└── README.md
```

---

## 🚀 Quick Start

### Opción A: Acceder al sistema en vivo (recomendado)

Si solo quieres probar VialAI, visita el sistema en Streamlit Community Cloud:

🔗 **https://urbanflow-cdmx.streamlit.app**

No necesitas instalar nada.

### Opción B: Correr el notebook reproducible en Google Colab

Si quieres ver el motor estocástico funcionando sin instalar nada:

1. Abre [Google Colab](https://colab.research.google.com)
2. File → Upload notebook → selecciona `notebooks/UrbanFlow_CDMX_Colab.ipynb`
3. Runtime → Run all

El notebook tiene **todos los datos cacheados inline** y corre sin APIs ni credenciales.

### Opción C: Correr el sistema completo en local

```bash
# 1. Clonar el repo
git clone https://github.com/caledelta/UrbanFlow_CDMX.git
cd UrbanFlow_CDMX

# 2. Crear entorno virtual
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate            # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar API keys
cp .env.example .env
# Editar .env y agregar tus keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   TOMTOM_API_KEY=...
#   OPENWEATHERMAP_API_KEY=...
#   GOOGLE_MAPS_API_KEY=...

# 5. Correr tests (opcional pero recomendado)
pytest tests/ -q

# 6. Lanzar la app
python -m streamlit run app/streamlit_app.py
```

La app estará disponible en `http://localhost:8501`.

---

## 📚 Documentación

Toda la documentación del proyecto está en la carpeta `docs/`:

| Documento | Descripción |
|---|---|
| [Artículo técnico](docs/proyecto_ZMCDMX_v3.pdf) | Paper académico de 23 páginas con metodología completa, validación y estrategia B2B |
| [Presentación](docs/UrbanFlow_CDMX_Presentacion.pptx) | Slides ejecutivos (16 slides) para exposición del proyecto |
| [Pitch B2B](docs/VialAI_Pitch_B2B.pdf) | Propuesta comercial para logística de última milla (4 páginas) |
| [Inventario](docs/Inventario_Proyecto.pdf) | Listado completo de herramientas, bibliotecas y recursos utilizados |
| [Notebook Colab](notebooks/UrbanFlow_CDMX_Colab.ipynb) | Notebook reproducible con el motor estocástico (38 celdas) |

---

## 🧪 Tests

El proyecto tiene **720 tests automatizados** con cobertura del motor estocástico, pipeline de datos y agente conversacional:

```bash
pytest tests/ -q                 # Ejecutar todos los tests
pytest tests/ -v                 # Modo verbose
pytest tests/ --cov=src          # Reporte de cobertura
```

---

## 🔌 Stack tecnológico

**Backend:**
- Python 3.14
- NumPy, Pandas, SciPy (cómputo numérico)
- Pydantic 2.x (validación de esquemas)
- Anthropic SDK (agente conversacional)
- pytest (testing)

**Frontend:**
- Streamlit 1.56
- Folium (mapas interactivos)
- Plotly (gauges y charts)

**APIs externas integradas:**
- TomTom Traffic Stats + Routing
- OpenWeatherMap
- Google Maps Distance Matrix
- Portal de datos abiertos CDMX (C5)

---

## 📊 Fuentes de datos

1. **TomTom Traffic Stats API** — Velocidades en tiempo real, inferencia del estado inicial
2. **TomTom Routing API** — Distancia real por carretera y geometría de ruta
3. **OpenWeatherMap API** — Condición climática, factor de ajuste de velocidades
4. **C5 CDMX Histórico** — Dataset de incidentes viales (2018-2024, ~1M registros) para calibración Markov
5. **Google Maps Distance Matrix** — Validación cruzada del ETA y geocodificación

---

## 🎓 Contexto académico

Este proyecto fue desarrollado como **proyecto integrador final** del Diplomado en Ciencia de Datos de la FES Acatlán (UNAM), bajo la dirección del profesor Fernando Barranco Rodríguez.

El proyecto integra múltiples áreas del diplomado:
- **Procesos estocásticos** (cadenas de Markov)
- **Métodos de simulación** (Monte Carlo)
- **Ingeniería de datos** (5 fuentes, pipelines ETL)
- **Modelos de lenguaje** (agentes con Claude API)
- **Desarrollo de productos de datos** (Streamlit, testing, documentación)

---

## 📄 Licencia

MIT License. Ver `LICENSE` para más detalles.

---

## 👤 Autor

**Carlos Armando López Encino**
Diplomado en Ciencia de Datos · FES Acatlán · UNAM

- GitHub: [@caledelta](https://github.com/caledelta)
- Proyecto: [github.com/caledelta/UrbanFlow_CDMX](https://github.com/caledelta/UrbanFlow_CDMX)

---

## 🙏 Agradecimientos

- Profesor Fernando Barranco Rodríguez por la dirección académica del diplomado
- La FES Acatlán y la UNAM por el programa del diplomado
- TomTom, OpenWeatherMap y el Gobierno de la CDMX por las APIs públicas
- Anthropic por la API de Claude que hace posible el agente VialAI
