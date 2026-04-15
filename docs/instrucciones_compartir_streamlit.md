# 🌐 Cómo compartir VialAI con el profesor

**Documento de instrucciones para hacer accesible la interfaz Streamlit del proyecto UrbanFlow CDMX**

Este documento explica las cuatro opciones disponibles para que el profesor Fernando Barranco pueda navegar y probar VialAI desde su propia computadora. Cada opción tiene ventajas y desventajas; al final hay una recomendación clara según el escenario.

---

## 📊 Comparativa rápida de las 4 opciones

| Opción | Costo | Setup | El profesor necesita | Persistencia |
|---|---|---|---|---|
| **A. Streamlit Community Cloud** | Gratis | 30 min | Solo un navegador | Siempre disponible |
| **B. ngrok (túnel temporal)** | Gratis | 5 min | Solo un navegador | Solo mientras tu laptop esté encendida |
| **C. Screen share en vivo** | Gratis | 0 min | Zoom/Meet | Solo durante la llamada |
| **D. Repo clonable + instrucciones** | Gratis | 0 min | Python + Git + API keys | El profesor lo corre cuando quiera |

---

## 🟢 Opción A — Streamlit Community Cloud (RECOMENDADA)

**Lo que es:** plataforma gratuita oficial de Streamlit que aloja tu app directamente desde tu repo de GitHub. Una vez configurada, tienes una URL pública permanente del estilo `http://localhost:8501 (correr localmente con: streamlit run app/streamlit_app.py)`.

### Ventajas

- ✅ **Profesional**: URL pública permanente, sin depender de tu laptop
- ✅ **Cero fricción para el profesor**: solo abre el link en su navegador
- ✅ **Gratis para proyectos públicos** sin límite de tiempo
- ✅ **Auto-deploy** desde tu repo: cada vez que hagas `git push`, la app se actualiza sola
- ✅ **Permite compartir el link en el video y en la demo en vivo** sin riesgo de que se caiga

### Desventajas

- ⚠️ Requiere que el repo sea **público en GitHub** (lo cual ya es)
- ⚠️ Las **API keys** (Anthropic, TomTom, OpenWeatherMap) deben configurarse como **secrets** en el dashboard de Streamlit, no en el `.env` del repo
- ⚠️ Cuotas: hasta 1 GB de RAM, lo cual es **suficiente** para VialAI pero no para datasets gigantes
- ⚠️ Setup inicial de ~30 min la primera vez

### Pasos para configurarlo

1. **Ir a** [share.streamlit.io](https://share.streamlit.io) y entrar con tu cuenta de GitHub.
2. Click en **"New app"** y seleccionar tu repo `caledelta/UrbanFlow_CDMX`.
3. **Branch:** `main`. **Main file path:** `app/streamlit_app.py`.
4. Click en **"Advanced settings"** → **"Secrets"** y pegar las API keys con este formato TOML:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-api03-..."
   TOMTOM_API_KEY = "..."
   OPENWEATHERMAP_API_KEY = "..."
   GOOGLE_MAPS_API_KEY = "..."
   ```
5. Click en **"Deploy!"**. La primera build toma 2-5 minutos.
6. Una vez desplegada, copia la URL (algo como `https://palermo01-urbanflow-cdmx-app-streamlit-app-xyz.streamlit.app`).
7. **Acortar la URL** con [bit.ly](https://bit.ly) o configurar un nombre custom desde el dashboard de Streamlit (opcional).

### Cambio de código necesario en el repo

Para que la app lea los secrets de Streamlit Cloud Y del `.env` local indistintamente, agrega esto al inicio de `app/streamlit_app.py`:

```python
import os
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# Carga local desde .env (cuando corres en tu laptop)
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# Carga desde Streamlit secrets (cuando corre en Streamlit Cloud)
if hasattr(st, "secrets"):
    for key in ["ANTHROPIC_API_KEY", "TOMTOM_API_KEY",
                "OPENWEATHERMAP_API_KEY", "GOOGLE_MAPS_API_KEY"]:
        if key in st.secrets and not os.getenv(key):
            os.environ[key] = st.secrets[key]
```

Este patrón es robusto: funciona en local (lee `.env`) Y en la nube (lee `st.secrets`) sin tocar nada más.

### Mensaje sugerido para el profesor

> *"Profesor Barranco, le comparto el link de VialAI para que pueda navegar y probarlo cuando guste:*
>
> *🔗 http://localhost:8501 (correr localmente con: streamlit run app/streamlit_app.py)*
>
> *Le sugiero probar primero la ruta Polanco → Santa Fe en horario matutino, después activar la perturbación 'Manifestación' y ver cómo cambia el Índice de Confiabilidad. También puede preguntarle directamente al chat de VialAI cualquier cosa sobre rutas en la ZMVM. Cualquier comentario o sugerencia, aquí estoy."*

---

## 🟡 Opción B — ngrok (túnel temporal)

**Lo que es:** una herramienta que crea un túnel HTTPS público desde tu laptop hacia Internet. Mientras tu laptop esté encendida con Streamlit corriendo, el profesor puede acceder desde cualquier navegador.

### Ventajas

- ✅ **Setup en 5 minutos** sin tocar nada del código
- ✅ **No requiere desplegar nada** ni configurar secrets
- ✅ **Las API keys siguen en tu `.env` local** (más privadas)
- ✅ Útil si tienes datos locales que no quieres subir a la nube

### Desventajas

- ❌ **Solo funciona mientras tu laptop esté encendida** y Streamlit corriendo
- ❌ La URL **cambia cada vez** que reinicias ngrok (en el plan gratuito)
- ❌ Hay un **límite de conexiones simultáneas** en el plan gratuito
- ❌ ngrok añade un **banner de advertencia** que el profesor ve la primera vez (puede confundirlo)

### Pasos para configurarlo

1. **Crear cuenta gratuita en** [ngrok.com](https://ngrok.com) y descargar el binario.
2. Autenticar con tu token: `ngrok config add-authtoken <tu_token>`
3. **En una terminal**, lanzar Streamlit normalmente:
   ```bash
   cd C:\Users\Carlos\UrbanFlow_CDMX
   .venv\Scripts\activate
   python -m streamlit run app/streamlit_app.py
   ```
4. **En otra terminal**, lanzar ngrok apuntando al puerto de Streamlit (8501 por defecto):
   ```bash
   ngrok http 8501
   ```
5. Copiar la URL `https://xxxx-xxxx.ngrok.io` que ngrok te muestra.
6. Compartir esa URL con el profesor.

### Cuándo usar esta opción

- Como **plan B** si Streamlit Community Cloud falla o tarda en desplegar.
- Para **demos puntuales** de horas o un día específico.
- Si necesitas mostrar una versión que **todavía no quieres subir al repo**.

---

## 🟠 Opción C — Screen share en vivo (Zoom/Meet)

**Lo que es:** durante la demo en vivo del proyecto, simplemente compartes tu pantalla con Streamlit corriendo en local.

### Ventajas

- ✅ **Cero setup**: solo abres Streamlit en tu laptop
- ✅ **Tú controlas el flujo**: puedes guiar al profesor por el sistema
- ✅ **Es exactamente lo que la rúbrica pide para la demo en vivo** (5 minutos compartiendo pantalla)

### Desventajas

- ❌ **El profesor no puede tocar nada**: solo ve lo que tú haces
- ❌ **Solo funciona durante la llamada**: el profesor no puede explorar después
- ❌ **No deja una URL permanente** que pueda revisitar

### Cuándo usar esta opción

- **Es la opción obligatoria para la demo en vivo de los 5 minutos** según la rúbrica.
- Pero **NO debe ser la única manera** que el profesor tiene de acceder al sistema; idealmente combínala con la Opción A o D para que también pueda probarla por su cuenta después.

---

## 🔵 Opción D — Repositorio clonable + instrucciones

**Lo que es:** el profesor clona tu repo público de GitHub, configura sus propias API keys en un `.env` local, y corre Streamlit en su propia computadora.

### Ventajas

- ✅ **Total transparencia**: el profesor ve todo el código
- ✅ **No depende de servicios externos** (Streamlit Cloud, ngrok)
- ✅ **El profesor puede modificar y experimentar** con el código
- ✅ **Es lo más cercano a "código de producción"** que puedes entregar
- ✅ Refuerza la idea de que tu proyecto es **reproducible y bien documentado**

### Desventajas

- ❌ **El profesor debe tener Python instalado** y saber usar Git
- ❌ **El profesor debe obtener sus propias API keys** (TomTom y OpenWeatherMap son gratuitas pero requieren registro)
- ❌ **Requiere ~20-30 minutos de setup** del lado del profesor
- ❌ **Si hay un bug en su entorno**, no puedes ayudarlo directamente

### Pasos que el profesor debe seguir

1. Clonar el repo:
   ```bash
   git clone https://github.com/caledelta/UrbanFlow_CDMX.git
   cd UrbanFlow_CDMX
   ```
2. Crear y activar entorno virtual:
   ```bash
   python -m venv .venv
   source .venv/bin/activate    # Linux/Mac
   .venv\Scripts\activate        # Windows
   ```
3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4. Crear archivo `.env` en la raíz del proyecto con sus propias keys:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-...
   TOMTOM_API_KEY=...
   OPENWEATHERMAP_API_KEY=...
   GOOGLE_MAPS_API_KEY=...
   ```
5. Correr Streamlit:
   ```bash
   python -m streamlit run app/streamlit_app.py
   ```

### Cuándo usar esta opción

- **Como complemento** a la Opción A o C, no como única opción.
- Si quieres demostrar **rigor metodológico** y reproducibilidad total.
- Para que el evaluador tenga **acceso al código fuente completo** sin intermediarios.

---

## 🎯 Recomendación final

**La estrategia óptima combina TRES de las cuatro opciones:**

| Para | Usa esta opción | Por qué |
|---|---|---|
| **Demo en vivo de 5 min** | C (Screen share) | Es lo que la rúbrica pide |
| **Acceso permanente del profesor** | A (Streamlit Community Cloud) | URL pública, cero fricción |
| **Verificación de reproducibilidad** | D (Repo clonable) | El evaluador ve el código real |

**No uses la Opción B (ngrok)** salvo como plan de contingencia si Streamlit Community Cloud falla.

### Plan de acción concreto

1. **Hoy mismo (30 min):** Configura Streamlit Community Cloud (Opción A) siguiendo los pasos descritos arriba. Esto te da una URL permanente.

2. **Verifica que funcione** abriendo la URL en una ventana de incógnito de tu navegador y probando la ruta Polanco → Santa Fe.

3. **Acorta la URL** con bit.ly para que sea fácil de compartir y memorizar.

4. **Manda un email al profesor** con:
   - El link de Streamlit Community Cloud (acceso inmediato)
   - El link al repo de GitHub (para verificación de código)
   - 3-4 ejemplos concretos de qué probar (Polanco→Santa Fe, activar perturbación de manifestación, hacer una pregunta al chat)
   - El PDF del artículo y el pitch B2B como adjuntos

5. **Durante la demo en vivo de 5 minutos**, comparte tu pantalla local (Opción C) corriendo Streamlit desde tu laptop. Si por alguna razón falla, **el plan B es abrir la URL de Streamlit Cloud** (Opción A) en el navegador y demostrar desde ahí.

---

## 📧 Email de muestra para el profesor

```
Asunto: UrbanFlow CDMX / VialAI — Acceso al sistema y entregables del proyecto integrador

Estimado profesor Fernando Barranco,

Le envío los entregables finales del proyecto integrador del Diplomado en
Ciencia de Datos. El sistema se llama "UrbanFlow CDMX" y construye un
agente conversacional ("VialAI") que predice tiempos de viaje en la ZMVM
con bandas de incertidumbre P10/P50/P90 y un Índice de Confiabilidad.

🔗 ACCESO AL SISTEMA EN VIVO:
   http://localhost:8501 (correr localmente con: streamlit run app/streamlit_app.py)
   (URL pública, no requiere instalación)

📂 CÓDIGO FUENTE COMPLETO:
   https://github.com/caledelta/UrbanFlow_CDMX
   (720 tests automatizados, todos pasando)

📎 ADJUNTOS:
   1. proyecto_ZMCDMX_v3.pdf — Artículo técnico (23 páginas)
   2. UrbanFlow_CDMX_Colab.ipynb — Notebook reproducible en Google Colab
   3. UrbanFlow_CDMX_Presentacion.pptx — Presentación ejecutiva (16 slides)
   4. VialAI_Pitch_B2B.pdf — Propuesta para nicho B2B última milla
   5. Inventario_Proyecto.pdf — Inventario completo del trabajo realizado

🧪 SUGERENCIAS DE PRUEBAS PARA EL SISTEMA EN VIVO:

   1. Predicción base:
      - Origen: Polanco
      - Destino: Santa Fe
      - Hora: 08:15 AM
      - Observe la banda P10/P50/P90 y el Índice de Confiabilidad

   2. Activar una perturbación:
      - En el panel lateral, active "Marcha 9 de marzo"
      - Vuelva a calcular la misma ruta
      - Note cómo la mediana sube y el IC pasa de amarillo a rojo

   3. Probar el chat conversacional:
      - Pregunte: "¿Vale la pena salir ahora para Santa Fe, o espero 30 minutos?"
      - Observe cómo VialAI razona y entrega una recomendación accionable

Quedo a sus órdenes para cualquier pregunta o aclaración.

Saludos cordiales,
Carlos Armando López Encino
Diplomado en Ciencia de Datos · FES Acatlán · UNAM
```

---

**Carlos Armando López Encino**
Diplomado en Ciencia de Datos · FES Acatlán · UNAM
Abril 2026
