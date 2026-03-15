# UrbanFlow CDMX — CLAUDE.md

## Descripción del Proyecto

Sistema de predicción de tiempos de viaje en la Zona Metropolitana del Valle de México (ZMVM) mediante simulación Monte Carlo y cadenas de Markov. Proyecto de diplomado en Ciencia de Datos.

**Entregables principales:**
- Motor de simulación estocástica (Monte Carlo + Markov) con bandas de incertidumbre P10/P50/P90
- Pipeline de ingesta de +1M registros históricos de tráfico
- API REST para consultas de predicción
- Dashboard en tiempo real de congestión vial

---

## Stack Tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11 |
| Cómputo numérico | NumPy, SciPy |
| Datos tabulares | Pandas |
| Datos geoespaciales | GeoPandas, Shapely |
| ML / Forecasting | XGBoost, Prophet |
| API REST | FastAPI + Uvicorn |
| Frontend / Dashboard | Streamlit |
| Base de datos | PostgreSQL 15 + PostGIS |
| Caché / Broker | Redis |
| Tareas asíncronas | Celery |
| Contenerización | Docker + Docker Compose |

---

## Fuentes de Datos

| Fuente | Datos | Frecuencia |
|---|---|---|
| C5 CDMX (`datos.cdmx.gob.mx`) | Incidentes viales históricos | Batch histórico |
| Metrobús GTFS-RT | Posición de autobuses | Cada 30 seg |
| TomTom Traffic Stats API | Velocidades históricas por segmento | Diario |
| OpenWeatherMap API | Clima histórico CDMX | Horario |
| SEMOVI datos abiertos | Aforos vehiculares | Batch histórico |

---

## Arquitectura de Directorios

```
UrbanFlow_CDMX/
├── data/
│   ├── raw/            # Datos crudos descargados, nunca modificar
│   ├── processed/      # Datos limpios y transformados
│   └── external/       # Shapefiles, GTFS estáticos, catálogos
├── src/
│   ├── ingestion/      # Conectores a cada fuente de datos
│   ├── simulation/     # Motor Monte Carlo + cadenas de Markov
│   ├── models/         # XGBoost, Prophet, modelos de predicción
│   ├── api/            # FastAPI routers, schemas, dependencies
│   └── dashboard/      # Streamlit app
├── tests/
├── notebooks/          # Exploración y prototipado (no producción)
├── docker/
├── .env.example
├── requirements.txt
├── requirements-dev.txt
└── docker-compose.yml
```

---

## Módulos Clave

### `src/simulation/`
- `monte_carlo.py` — simulación de N iteraciones sobre distribuciones de velocidad/tiempo
- `markov_chains.py` — matrices de transición de estado de tráfico (fluido / lento / congestionado)
- `uncertainty_bands.py` — cálculo de percentiles P10/P50/P90 sobre resultados de simulación

### `src/ingestion/`
- Un módulo por fuente: `c5_cdmx.py`, `metrobus_gtfs.py`, `tomtom.py`, `openweathermap.py`, `semovi.py`
- Todos exponen la misma interfaz: `fetch() -> pd.DataFrame` y `load_to_db(df)`

### `src/api/`
- `POST /predict/travel-time` — retorna P10/P50/P90 para un origen–destino dado
- `GET /traffic/realtime` — estado actual de congestión por zona
- `GET /health` — liveness check

---

## Convenciones de Código

- **Coordenadas:** siempre en WGS84 (EPSG:4326) para ingesta; reproyectar a EPSG:6372 (México) para cálculos de distancia
- **Timestamps:** siempre UTC en base de datos; convertir a `America/Mexico_City` solo en capa de presentación
- **Tipos:** usar type hints en todas las funciones públicas
- **Tests:** pytest; los tests de integración deben usar una base de datos real (no mocks de DB)
- **Secrets:** nunca hardcodear API keys; usar `.env` + `python-dotenv`

---

## Variables de Entorno Requeridas

```
DATABASE_URL=postgresql://user:password@localhost:5432/urbanflow
REDIS_URL=redis://localhost:6379/0
TOMTOM_API_KEY=
OPENWEATHERMAP_API_KEY=
METROBUS_GTFS_RT_URL=
```

---

## Comandos Frecuentes

```bash
# Levantar servicios locales
docker-compose up -d postgres redis

# Instalar dependencias
pip install -r requirements.txt

# Correr API en desarrollo
uvicorn src.api.main:app --reload --port 8000

# Correr dashboard
streamlit run src/dashboard/app.py

# Correr tests
pytest tests/ -v

# Ejecutar worker Celery
celery -A src.tasks worker --loglevel=info
```

---

## Notas del Proyecto

- **Diplomado:** Ciencia de Datos — proyecto final integrador
- **Alcance geográfico:** ZMVM (CDMX + municipios conurbados del Edomex)
- **Volumen objetivo:** +1 millón de registros históricos de tráfico
- **Métrica de éxito:** MAPE < 15% en predicción de tiempo de viaje para horizonte de 30 min
