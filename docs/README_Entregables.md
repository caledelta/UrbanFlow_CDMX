# 📦 UrbanFlow CDMX — Paquete de Entregables Finales

**Proyecto Integrador del Diplomado en Ciencia de Datos**
FES Acatlán · UNAM · Abril 2026

**Autor:** Carlos Armando López Encino
**Repositorio:** [github.com/caledelta/UrbanFlow_CDMX](https://github.com/caledelta/UrbanFlow_CDMX)

---

## 🎯 ¿Qué es este paquete?

Este es el paquete completo de entregables para la evaluación final del proyecto **UrbanFlow CDMX / VialAI**, un sistema de predicción estocástica de tiempos de viaje en la Zona Metropolitana del Valle de México que combina cadenas de Markov, simulación Monte Carlo e inteligencia artificial conversacional.

Los siete archivos listados abajo cubren los seis criterios de la rúbrica de evaluación del diplomado (Documento, Estrategia, Notebook, Presentación, Video y Demo en vivo), sumando los 110 puntos totales del proyecto.

---

## 📁 Contenido del paquete

### 1. `proyecto_ZMCDMX_v3.pdf` (artículo técnico completo)

**Peso en rúbrica:** 15 pts (Documento) + 15 pts (Estrategia) = **30 pts**

Artículo técnico de 22 páginas en formato académico con las 12 secciones estándar de un paper de ciencia de datos:

1. Motivación y contexto (con datos reales de INEGI, DataMéxico y TomTom Traffic Index 2024)
2. Arquitectura general del sistema (con diagrama TikZ de 5 capas)
3. Fuentes de datos (5 APIs integradas)
4. Marco teórico: Cadenas de Markov
5. Implementación de la cadena (`MarkovTrafficChain`)
6. Marco teórico: Simulación Monte Carlo
7. Implementación del motor (`MonteCarloEngine` vectorizado)
8. Pipeline integrador en tiempo real, **incluyendo §8.4 Perturbaciones contextuales**
9. Agente VialAI (structured outputs, function calling, loop tool use)
10. Resultados y validación empírica (MAPE 12.8% sobre 30 rutas reales)
11. **Estrategia de negocio para B2B logística de última milla** (USD 15.6B mercado, 3 perfiles de usuario, 4 accionables, modelo SaaS freemium)
12. Conclusiones y trabajo futuro

**Distintivos del artículo:**
- 4 `challengebox` documentando retos reales y cómo se abordaron
- 4 `insightbox` con hallazgos vendibles para el jurado
- 17 referencias bibliográficas reales
- Código vectorizado incluido en listings LaTeX
- Glosario y apéndice de parámetros

**También se incluye** `proyecto_ZMCDMX_v3.tex` con el fuente LaTeX completo por si el evaluador quiere recompilar.

---

### 2. `UrbanFlow_CDMX_Colab.ipynb` (notebook Colab reproducible)

**Peso en rúbrica:** 15 pts (Notebook) = **15 pts**

Notebook de 33 celdas (11 markdown + 22 código) **totalmente autocontenido** que reproduce el motor estocástico del sistema sin necesidad de APIs externas ni credenciales.

**Características:**
- **Datos cacheados inline**: matriz de transición histórica del corredor Insurgentes Sur pico AM + 30 rutas de validación con sus ETA de TomTom y tiempos reales observados
- **Corre en Google Colab sin configuración previa** (solo numpy, pandas, matplotlib, scipy — todos preinstalados en Colab)
- **Implementa desde cero** la clase `MarkovTrafficChain` con fit/predict_distribution/steady_state/simulate
- **Implementa desde cero** la clase `MonteCarloEngine` con vectorización por transformada inversa
- **Incluye las perturbaciones contextuales** con ejemplo numérico de antes/después
- **Ejecuta la validación empírica completa** sobre las 30 rutas y reporta:
  - **MAPE del P50: 11.87%** (< 15% objetivo)
  - **Cobertura empírica de la banda P10-P90: 93.3%** (nominal 80%)
  - **MAPE de TomTom ETA: 18.99%** — VialAI es 7 puntos porcentuales más preciso
- **7 visualizaciones** incluidas (histograma de distancias, heatmap de la matriz, convergencia a estacionaria, histograma de la distribución, comparación VialAI vs TomTom, cobertura de banda, distribución del IC con semáforo)

**Archivos incluidos:**
- `UrbanFlow_CDMX_Colab.ipynb` — versión limpia para que el evaluador la corra
- `UrbanFlow_CDMX_Colab_executed.ipynb` — versión pre-ejecutada con todos los outputs visibles (por si hay problemas de red)

---

### 3. `UrbanFlow_CDMX_Presentacion.pptx` (presentación ejecutiva)

**Peso en rúbrica:** 10 pts (Presentación) = **10 pts**

Presentación de **16 slides** en formato 16:9 widescreen (13.33 × 7.5 pulgadas) con paleta ejecutiva "Midnight Executive" (navy profundo + ámbar).

**Estructura narrativa:**

| # | Slide | Propósito |
|---|---|---|
| 1 | Portada | Identidad visual del proyecto |
| 2 | ¿Qué es la ZMVM? | Contexto geográfico y demográfico |
| 3 | El problema | Número gigante 152 horas/año |
| 4 | Agenda | Regla del 3 (datos, VialAI, estrategia) |
| 5 | Los datos | 6 KPI cards (5 fuentes, 10K, 3 estados, 11 perturbaciones, 720 tests, <500 ms) |
| 6 | Cadenas de Markov | Matriz de transición como heatmap |
| 7 | Monte Carlo | Histograma conceptual con P10/P50/P90 |
| 8 | Perturbaciones contextuales | 4 cards (Metro, eventos, marchas, festivos) |
| 9 | Índice de Confiabilidad | Fórmula + semáforo verde/amarillo/rojo |
| 10 | Demo narrativa | Polanco → Santa Fe con inputs y outputs |
| 11 | Validación empírica | 4 KPIs: MAPE 11.9%, cobertura 93%, MAE 4.8, TomTom 19% |
| 12 | Agente VialAI | Diagrama del loop tool_use + 3 herramientas |
| 13 | Estrategia B2B | USD 15.6B + 3 perfiles de usuario |
| 14 | 4 accionables | Quoting, priorización, alertas, post-mortem |
| 15 | Ciclo operativo | Diagrama circular de 8 pasos estilo rueda |
| 16 | Gracias | Cierre con URL de GitHub |

**Distintivos:**
- Cada slide tiene al menos un elemento visual (iconos FontAwesome, cards, heatmaps, diagramas)
- Números grandes destacados (60-96 pt) para impacto inmediato
- Paleta consistente con el artículo LaTeX
- Usable tanto para la grabación del video como para la demo en vivo

**Archivos incluidos:**
- `UrbanFlow_CDMX_Presentacion.pptx` — versión editable
- `UrbanFlow_CDMX_Presentacion.pdf` — versión PDF por si el equipo del evaluador no tiene PowerPoint

---

### 4. `guion_video.md` (guion del video de 5 minutos)

**Peso en rúbrica:** 20 pts (Video) = **20 pts**

Guion completo, línea por línea, con timestamps exactos para grabar el video de 5 minutos que exige la rúbrica.

**Contenido:**
- Checklist técnico de OBS Studio (resolución, filtros de audio, layout con cámara web)
- Estructura de 8 bloques de tiempo con objetivos claros:
  - Apertura (0:00-0:20)
  - Problema (0:20-1:00)
  - Solución técnica (1:00-1:50)
  - Innovación: perturbaciones + IC (1:50-2:40)
  - Demo narrativa (2:40-3:30)
  - Validación (3:30-4:10)
  - Estrategia (4:10-4:50)
  - Cierre (4:50-5:00)
- Texto literal para leer/memorizar con cues de slide en cada punto
- Notas de edición si el video se pasa de tiempo (qué cortar en orden de prioridad)
- Errores comunes a evitar
- Cheatsheet de números clave para memorizar
- Plan de práctica recomendado (hora y media antes de la grabación final)

---

### 5. `checklist_demo.md` (checklist operativo de la demo en vivo)

**Peso en rúbrica:** 25 pts (Demo en vivo) = **25 pts** ← *El bloque más grande*

Checklist de 5 minutos exactos para la presentación en vivo del proyecto frente al profesor Fernando Barranco.

**Contenido:**
- Setup técnico (30 minutos antes): apps abiertas, apps cerradas, resolución de pantalla, verificación de APIs, tests pasando
- Secuencia minuto a minuto con acciones concretas:
  - Minuto 1: apertura + tour rápido de la UI
  - Minutos 2-3: predicción en vivo Polanco → Santa Fe con bandas e IC
  - Minuto 4: pregunta al agente VialAI en el chat
  - Minuto 5: activar perturbación y mostrar cambio en las bandas
  - Cierre con QnA
- **Plan de contingencia** para 6 escenarios de falla posibles:
  - Streamlit se cae
  - API de TomTom no responde
  - Agente VialAI no responde
  - Se cae el internet completamente
  - Se te olvida qué decir
  - El profesor interrumpe con una pregunta
- Checklist final de 5 minutos antes del turno
- Tabla de criterios de la rúbrica con el mapeo de cómo los cumples
- Frases poderosas para cerrar si sobra tiempo

---

## ✅ Mapeo de entregables → rúbrica

| Criterio | Peso | Archivo que lo cubre | Estado |
|---|---|---|---|
| **Documento técnico** | 15 pts | `proyecto_ZMCDMX_v3.pdf` | ✅ Completo |
| **Estrategia de negocio** | 15 pts | §11 del artículo + slide 13-14 | ✅ Completo (B2B última milla con datos reales) |
| **Notebook reproducible** | 15 pts | `UrbanFlow_CDMX_Colab.ipynb` | ✅ Completo (corre en Colab sin credenciales) |
| **Presentación** | 10 pts | `UrbanFlow_CDMX_Presentacion.pptx` | ✅ Completo (16 slides) |
| **Interfaz de uso** | 10 pts | Streamlit + agente VialAI (en el repo) | ⚠️ Depende del bug del `.env` |
| **Video 5 min** | 20 pts | `guion_video.md` — guion listo para grabar | 🎬 Por grabar |
| **Demo en vivo** | 25 pts | `checklist_demo.md` — checklist listo para ejecutar | 🎯 Por presentar |
| **TOTAL** | **110 pts** | | |

---

## 🎯 Orden sugerido de preparación (desde ahora hasta la entrega)

### Fase 1 — Técnica (ya resuelta)

- [x] Motor Markov + Monte Carlo funcionando (720 tests pasando)
- [x] Pipeline de datos con 5 fuentes
- [x] Agente VialAI con Anthropic API
- [x] Streamlit con mapa Folium y chat integrado
- [x] Perturbaciones contextuales implementadas

### Fase 2 — Bug del `.env`

**Prompt para Claude Code** (ejecutar ANTES de grabar el video o hacer la demo):

```
Contexto: proyecto UrbanFlow_CDMX. Tenemos un bug donde ANTHROPIC_API_KEY
no se carga cuando el VialAIAgent se instancia desde Streamlit, aunque
sí está en el archivo .env en la raíz del proyecto. Causa: load_dotenv()
usa ruta relativa al cwd, pero Streamlit corre desde un directorio distinto
al módulo src/agent/agent.py.

Arregla con estos pasos:

1. En src/agent/agent.py, al inicio del archivo:

   from pathlib import Path
   from dotenv import load_dotenv
   import os

   PROJECT_ROOT = Path(__file__).resolve().parents[2]
   ENV_PATH = PROJECT_ROOT / ".env"
   load_dotenv(dotenv_path=ENV_PATH, override=False)

   ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
   if not ANTHROPIC_API_KEY:
       raise RuntimeError(
           f"ANTHROPIC_API_KEY no encontrada. Verificado en: {ENV_PATH}. "
           f"Existe: {ENV_PATH.exists()}"
       )

2. En app/streamlit_app.py, antes de cualquier import de src.*:

   from pathlib import Path
   from dotenv import load_dotenv
   ROOT = Path(__file__).resolve().parent.parent
   load_dotenv(ROOT / ".env")

3. Verifica con:
   python -c "from src.agent.agent import VialAIAgent; print('OK')"
   pytest tests/ -k agent -v

Muestrame el diff completo de los 2 archivos modificados. No toques nada más.
```

### Fase 3 — Documentación (ya resuelta)

- [x] Artículo LaTeX con todas las secciones
- [x] Notebook Colab reproducible
- [x] Presentación ejecutiva
- [x] Guion de video
- [x] Checklist de demo

### Fase 4 — Grabación del video (pendiente)

**Tiempo estimado: 1.5 horas**

1. Leer el guion en voz alta 2 veces (cronometrar)
2. Hacer setup de OBS (30 min)
3. Ensayar sin grabar (15 min)
4. Grabar toma 1 (5 min + tiempo de resetear)
5. Grabar toma 2 (corrigiendo lo que falló)
6. Grabar toma 3 solo si es necesario
7. Edición mínima en DaVinci Resolve o Shotcut (30 min)
8. Exportar en MP4 1080p 30fps

### Fase 5 — Demo en vivo (pendiente)

**Tiempo estimado: 2 horas de preparación**

1. Ensayar la demo completa 3 veces con cronómetro
2. Ejecutar el plan de contingencia como simulacro (forzar un error y recuperarse)
3. El día de la presentación: llegar 30 minutos antes con el setup completo

---

## 🧪 Para el evaluador: cómo verificar cada entregable

### Verificar el artículo

```bash
# Si quieres recompilar el LaTeX tú mismo
pdflatex proyecto_ZMCDMX_v3.tex
pdflatex proyecto_ZMCDMX_v3.tex  # segunda pasada para TOC y refs
```

### Verificar el notebook Colab

1. Subir `UrbanFlow_CDMX_Colab.ipynb` a [colab.research.google.com](https://colab.research.google.com)
2. `Runtime → Run all`
3. Verificar que la celda final reporte `MAPE del P50 (VialAI): ~11-12%` y `Cobertura banda P10-P90: ~90-95%`
4. **Debe correr sin errores, sin warnings y sin pedir credenciales**

Alternativamente, abrir `UrbanFlow_CDMX_Colab_executed.ipynb` que ya tiene todos los outputs visibles.

### Verificar la presentación

Abrir `UrbanFlow_CDMX_Presentacion.pptx` en PowerPoint, LibreOffice Impress, Keynote o Google Slides. También se incluye `UrbanFlow_CDMX_Presentacion.pdf` como respaldo.

### Verificar el sistema completo

El repositorio GitHub contiene el código ejecutable:

```bash
git clone https://github.com/caledelta/UrbanFlow_CDMX.git
cd UrbanFlow_CDMX
python -m venv .venv
source .venv/bin/activate  # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
# Configurar las API keys en .env (ver .env.example)
pytest tests/ -q  # debe reportar 720 passed
python -m streamlit run app/streamlit_app.py
```

---

## 📊 Resumen ejecutivo del proyecto

**Problema:** CDMX es la ciudad #1 del mundo en congestión vehicular (TomTom 2024). Los conductores pierden 152 horas al año en tráfico. Los sistemas de navegación actuales entregan estimaciones puntuales que ocultan la varianza del tráfico urbano.

**Solución:** UrbanFlow CDMX / VialAI, un sistema de predicción **probabilística** que entrega bandas P10/P50/P90 + Índice de Confiabilidad con semáforo operativo.

**Tecnología:**
- Cadenas de Markov de 3 estados (Fluido / Lento / Congestionado)
- Simulación Monte Carlo vectorizada de 10,000 trayectorias (<500 ms latencia)
- Perturbaciones contextuales para eventos no capturados por sensores
- Agente conversacional con Anthropic API (structured outputs + function calling)
- Streamlit con mapa Folium interactivo

**Fuentes de datos (5):** TomTom Traffic Stats, TomTom Routing, OpenWeatherMap, C5 CDMX, Google Maps

**Validación:** MAPE 11.9% sobre 30 rutas (mejor que TomTom ETA con 19%), cobertura empírica de banda 93% (nominal 80%)

**Nicho objetivo:** B2B logística de última milla en ZMVM — mercado de USD 15.6B en 2025, proyectado a USD 27.3B en 2030 (CAGR 11.8%)

**Estado técnico:** Funcional, 720 tests automatizados al 100%, código en GitHub

---

## 📬 Contacto

**Carlos Armando López Encino**
Estudiante del Diplomado en Ciencia de Datos
FES Acatlán · UNAM

**GitHub del proyecto:** [github.com/caledelta/UrbanFlow_CDMX](https://github.com/caledelta/UrbanFlow_CDMX)

---

*Documento generado: Abril 2026*
