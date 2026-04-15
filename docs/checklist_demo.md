# 🎯 Checklist Demo en Vivo — UrbanFlow CDMX / VialAI

**Duración:** 5 minutos exactos (rúbrica)
**Modalidad:** Compartir pantalla + hablar en vivo
**Peso en la rúbrica:** 25 puntos (el bloque más grande)
**Evaluador:** Prof. Fernando Barranco Rodríguez

> **Regla de oro:** la demo en vivo se evalúa sobre **usabilidad**. No es una clase de Markov, es una demostración de que *el sistema funciona y sirve para algo*. Habla poco, muestra mucho.

---

## 🧰 Setup técnico ANTES de conectarse

### 30 minutos antes

- [ ] **Reiniciar la laptop** (limpia memoria, procesos colgados)
- [ ] **Cargar batería al 100%** y dejar el cargador conectado
- [ ] **Cerrar todas las apps** excepto las necesarias (ver lista abajo)
- [ ] **Silenciar notificaciones** — Slack, Discord, Telegram, correo, iMessage, WhatsApp Web
- [ ] **Modo "No molestar"** activado en el sistema operativo
- [ ] **Verificar conexión a internet** — necesitas TomTom y OpenWeatherMap respondiendo
- [ ] **Hacer una corrida de prueba completa** del flujo que vas a demostrar

### Apps que deben estar abiertas (en este orden de alt+tab)

1. **Navegador Chrome/Edge** — pestaña única con `http://localhost:8501` (Streamlit)
2. **Terminal/PowerShell** — con el venv activado y listo por si Streamlit crashea
3. **VS Code o editor** — abierto en `src/agent/agent.py` por si necesitas mostrar código
4. **Este checklist** — en un segundo monitor o impreso

### Apps que deben estar CERRADAS

- Spotify, YouTube, Netflix, cualquier media player
- Steam, Discord, juegos
- Adobe Creative Cloud, OneDrive sync, Dropbox sync
- Docker Desktop (si no lo usas)
- Slack, Teams, Zoom no necesarios para la clase

### Verificación de VialAI antes de arrancar

- [ ] **Streamlit corriendo:** `python -m streamlit run app/streamlit_app.py` sin errores
- [ ] **Test de conexión Anthropic API:** mandar un mensaje de prueba al chat VialAI, debe responder en <5 seg
- [ ] **Test del motor Monte Carlo:** ejecutar una predicción Polanco → Santa Fe, debe devolver P10/P50/P90 en <1 seg
- [ ] **Verificar .env cargado:** en la consola de Streamlit no debe aparecer ningún warning sobre `ANTHROPIC_API_KEY`
- [ ] **Verificar TomTom:** que el mapa Folium se renderice correctamente con los tiles cargados
- [ ] **Verificar OpenWeatherMap:** que el widget de clima muestre la temperatura actual
- [ ] **720 tests pasando:** `pytest tests/ -q` debe mostrar `720 passed`

### Configuración de pantalla para compartir

- [ ] **Resolución de pantalla:** 1920×1080 (si tienes 4K, bájalo temporalmente)
- [ ] **Escalado:** 100% (no 125% ni 150%) — los elementos se ven más pequeños pero caben más
- [ ] **Tema claro** en Streamlit (no dark mode) — se ve mejor en compartir pantalla
- [ ] **Navegador en pantalla completa** (F11) para esconder tabs y barras
- [ ] **Zoom del navegador al 100%** (Ctrl+0)

---

## 🎬 Secuencia de la demo — 5 minutos exactos

```
┌────────────────────────────────────────────────────────────┐
│  0:00 — 0:30   Apertura: problema en 30 seg                │
│  0:30 — 1:30   Mostrar la UI y contexto                    │
│  1:30 — 3:00   Predicción en vivo + bandas + IC            │
│  3:00 — 4:00   Chat con VialAI (agente conversacional)     │
│  4:00 — 4:40   Mostrar perturbación en acción              │
│  4:40 — 5:00   Cierre y QnA                                │
└────────────────────────────────────────────────────────────┘
```

---

### 🟦 MINUTO 1 — Apertura y contexto (0:00 – 1:00)

#### 0:00 – 0:30 — Frase de apertura

**[Pantalla: Streamlit abierto en la página principal con el mapa de CDMX visible]**

> "Buenas tardes, profesor. Soy Carlos y les voy a mostrar VialAI en vivo. El problema que resuelve es simple: Google Maps te dice *cuánto* vas a tardar, pero no te dice *qué tan confiable* es esa predicción. Y para logística de última milla en CDMX, esa diferencia vale dinero. Ya lo vamos a ver."

*(Una sola frase de pitch. Sin rodeos. El jurado ya leyó tu documento.)*

#### 0:30 – 1:00 — Tour rápido de la UI

**[Acción: mover el cursor para señalar cada elemento mientras lo mencionas]**

- [ ] **Señalar el mapa Folium:** "Este es el mapa interactivo de la ZMVM."
- [ ] **Señalar los selectores de origen/destino:** "Aquí selecciono el origen y el destino."
- [ ] **Señalar el chat en la sidebar:** "A la derecha está el agente VialAI, que es mi capa conversacional encima del motor estocástico."
- [ ] **Señalar el widget de clima:** "Arriba hay información climática en tiempo real de OpenWeatherMap."

> "El sistema integra cinco fuentes de datos: TomTom Traffic, TomTom Routing, OpenWeatherMap, datos históricos del C5 CDMX, y Google Maps para validación cruzada. Todo en tiempo real."

---

### 🟦 MINUTO 2-3 — Predicción estocástica en vivo (1:00 – 3:00)

#### 1:00 – 1:30 — Configurar la consulta

**[Acción: seleccionar Polanco como origen y Santa Fe como destino]**

> "Voy a correr una consulta real. Polanco a Santa Fe, mi ruta de ejemplo clásica. La hora actual, ahora mismo."

- [ ] Click en dropdown origen → seleccionar **Polanco**
- [ ] Click en dropdown destino → seleccionar **Santa Fe**
- [ ] Verificar que el mapa Folium dibuje la línea origen → destino
- [ ] Click en el botón **"Predecir tiempo de viaje"** (o como se llame en tu app)

#### 1:30 – 2:15 — Mostrar la banda estocástica

**[La UI debe mostrar los 3 percentiles después de ~1 segundo]**

> "Y aquí está el resultado. *(pausa, apuntar a los números)*"

- [ ] **Apuntar al P10:** "En el escenario optimista, llego en XX minutos."
- [ ] **Apuntar al P50:** "La mediana, lo más probable, son XX minutos."
- [ ] **Apuntar al P90:** "Y en el escenario pesimista, XX minutos."

> "Noten que esto no es un número, es **una distribución**. Debajo hay diez mil trayectorias Monte Carlo que se corrieron en menos de medio segundo."

#### 2:15 – 3:00 — Mostrar el Índice de Confiabilidad

**[Acción: apuntar al gauge del IC con el semáforo]**

- [ ] **Apuntar al número del IC:** "El Índice de Confiabilidad es X.XX."
- [ ] **Apuntar al color del semáforo:** "Y eso me da semáforo [verde/amarillo/rojo]."

> "Este es el número que inventé para el proyecto. Para un dispatcher de logística, no le importan los percentiles — le importa si la ruta es confiable o no. Verde significa que promete la ventana con tranquilidad, amarillo significa que debe agregar un buffer, y rojo significa que esa ruta no debe ser asignada a un conductor nuevo."

---

### 🟦 MINUTO 4 — Agente conversacional VialAI (3:00 – 4:00)

#### 3:00 – 3:15 — Introducción al chat

**[Acción: mover el cursor al chat de la sidebar]**

> "Ahora viene la parte conversacional. Todo lo que acabamos de ver puede preguntarse en lenguaje natural. Voy a escribirle a VialAI."

#### 3:15 – 3:45 — Pregunta en vivo al agente

**[Acción: escribir literalmente en el input del chat]**

> **Texto a escribir:** `¿Vale la pena salir ahora para Santa Fe, o espero 30 minutos?`

- [ ] **Enviar el mensaje** (Enter)
- [ ] **Esperar la respuesta del agente** (2-5 seg típicamente)

**[Mientras Claude piensa, narra:]**

> "Internamente, VialAI está invocando tres herramientas: una para consultar el tráfico actual, otra para predecir el tiempo de viaje, y una tercera para verificar perturbaciones activas. Esto es function calling con la API de Anthropic."

#### 3:45 – 4:00 — Leer la respuesta del agente

**[El agente debe responder con una recomendación explicada]**

- [ ] **Apuntar a la respuesta del agente** con el cursor
- [ ] **No leer toda la respuesta en voz alta** — solo resaltar el insight clave

> "Como ven, el agente no solo da los números. Los **explica** en lenguaje natural y da una recomendación concreta. Esto es lo que un dispatcher necesita para tomar decisiones rápido."

---

### 🟦 MINUTO 5 — Perturbación en acción (4:00 – 4:40)

#### 4:00 – 4:20 — Aplicar una perturbación

**[Acción: ir a la sección de perturbaciones en la sidebar o donde la tengas]**

> "Y esta es la contribución más novedosa del proyecto: las perturbaciones contextuales. Imaginen que en este momento hay una manifestación activa en Reforma."

- [ ] **Activar el toggle de "Manifestación activa"** (o como se llame)
- [ ] **Re-correr la predicción** con el mismo origen/destino
- [ ] **Esperar el resultado** (~1 seg)

#### 4:20 – 4:40 — Comparar resultados

**[La UI debe mostrar cómo cambió la banda]**

- [ ] **Apuntar al nuevo P50 vs el anterior:** "La mediana pasó de XX a XX minutos."
- [ ] **Apuntar al nuevo IC:** "El IC saltó de X.XX a X.XX."
- [ ] **Apuntar al semáforo:** "Y la ruta pasó de [color] a [color peor]."

> "Esto es lo que TomTom y Google Maps no pueden hacer. Ellos miden velocidades con GPS, pero una manifestación recién convocada no aparece en sus datos hasta que ya pasó. Yo inyecto ese conocimiento contextual al vuelo."

---

### 🟦 CIERRE (4:40 – 5:00)

**[Acción: volver al estado inicial del mapa, cursor quieto]**

> "Con eso cierro la demo. En resumen: UrbanFlow CDMX entrega bandas probabilísticas P10-P90 con un Índice de Confiabilidad interpretable, integra cinco fuentes de datos en tiempo real, incorpora perturbaciones contextuales que ningún sistema comercial tiene, y todo está envuelto en un agente conversacional que cualquier dispatcher puede usar."

> "El código completo con 720 tests está en mi GitHub. Gracias, profesor. *(pausa)* ¿Tiene alguna pregunta?"

---

## 🆘 Plan de contingencia — Qué hacer si algo falla

### Escenario 1: Streamlit se cae durante la demo

- [ ] **Respirar** (3 segundos)
- [ ] Cambiar al terminal con **Alt+Tab**
- [ ] Presionar **Ctrl+C** si todavía está corriendo
- [ ] Ejecutar `python -m streamlit run app/streamlit_app.py`
- [ ] **Mientras arranca**, narra: *"Permítame un segundo, voy a reiniciar el servidor. Esto me da la oportunidad de mostrar que el sistema corre en local y no depende de ningún servicio externo."*
- [ ] Cuando reinicia (≈10 seg), continúa la demo donde la dejaste

### Escenario 2: La API de TomTom no responde

- [ ] **No entrar en pánico**
- [ ] Narrar: *"Parece que TomTom está tardando. Mi sistema tiene un fallback automático que usa el factor empírico de tortuosidad kappa = 1.4 cuando la API no responde. Esto lo documenté en la sección 3.2 del artículo."*
- [ ] Continuar con una predicción que use el fallback (si tu UI lo expone)

### Escenario 3: El agente VialAI no responde o da un error

- [ ] **Narrar mientras ocurre**: *"Mientras el agente procesa, les explico qué está haciendo internamente..."*
- [ ] Si después de 15 segundos sigue sin responder, cancelar con "Voy a saltarme esta parte del chat y les muestro directamente el resultado del motor, que es el mismo sistema pero sin la capa conversacional."
- [ ] Mostrar directamente los P10/P50/P90 en la UI

### Escenario 4: Se cae internet completamente

- [ ] **Mantener la calma**
- [ ] Narrar: *"Parece que perdí conexión. Afortunadamente el motor Monte Carlo no necesita internet — los datos de tráfico y clima están cacheados de la última consulta. Puedo mostrar el motor corriendo en modo offline."*
- [ ] Ir al notebook `UrbanFlow_CDMX_Colab.ipynb` que tiene datos cacheados y corre sin APIs live
- [ ] Mostrar la celda de validación que reporta el MAPE 11.9%

### Escenario 5: Se te olvida qué decir

- [ ] **Hacer una pausa deliberada** (1-2 segundos, no más)
- [ ] Mirar discretamente este checklist
- [ ] Recuperar diciendo: *"Lo más importante de esta sección es..."*
- [ ] Continuar

### Escenario 6: El profesor te interrumpe con una pregunta a la mitad

- [ ] **Responderla brevemente** (máximo 20 segundos)
- [ ] Regresar al checkpoint donde estabas
- [ ] Decir: *"Volviendo a la demo, estaba mostrando..."*

---

## 🎯 Checklist FINAL inmediatamente antes de empezar

**5 minutos antes de tu turno:**

- [ ] Streamlit corriendo y respondiendo (última verificación)
- [ ] Chrome en pantalla completa, zoom 100%
- [ ] Mapa visible, todo cargado
- [ ] Chat VialAI con historial limpio (sin mensajes previos)
- [ ] Volumen del micrófono a nivel audible
- [ ] Cámara web funcionando si la clase lo requiere
- [ ] Este checklist abierto en el segundo monitor o impreso
- [ ] Agua al lado
- [ ] Celular en silencio, lejos del mic
- [ ] Respirar profundo 3 veces
- [ ] Sonreír antes de empezar

---

## 📊 Lo que el profesor está evaluando (según rúbrica)

| Criterio | Qué significa | Cómo lo cumples en esta demo |
|---|---|---|
| **Explicación clara** | Que el público entienda cómo usar el modelo, paso a paso | Sigues la secuencia del 1 al 5 sin saltar pasos |
| **Demostración convincente** | Que el sistema funcione de verdad en vivo | Los 4 momentos clave: mapa, bandas, chat, perturbación |
| **Usabilidad** | Que sea intuitivo y fácil de usar | Menos explicación técnica, más "hacer clic y ver qué pasa" |
| **Herramientas** | Streamlit/Gradio/BI | Streamlit (ya está en tu stack) |

**La única cosa que NO debes hacer:** explicar teoría de Markov en la demo. Eso ya está en el artículo. Aquí solo muestras el sistema funcionando.

---

## 🎓 Frases poderosas para cerrar si te sobra tiempo

Si terminas antes de los 5 minutos y tienes 20-30 segundos libres, agrega UNA de estas:

1. **"Este motor estocástico está cubierto por 720 tests automatizados que pasan al 100%. No es un prototipo de diplomado, es código que puede ir a producción mañana."**

2. **"El código está publicado bajo licencia abierta en GitHub para que cualquier estudiante de la FES Acatlán pueda clonarlo, correrlo y aprender de él. Esa es la mejor devolución que puedo hacer al programa."**

3. **"El MAPE de 11.9% sobre 30 rutas es mejor que el de TomTom sobre las mismas rutas. Y VialAI además cuantifica la incertidumbre, que es algo que ningún sistema comercial hace."**

---

## ⏱️ Resumen de tiempos (tabla de referencia rápida)

| Tiempo | Acción | Lo esencial |
|---|---|---|
| 0:00 | Frase de apertura | Pitch en una frase |
| 0:30 | Tour de la UI | Mapa, selectores, chat, clima |
| 1:00 | Configurar Polanco → Santa Fe | Click, click, click |
| 1:30 | Mostrar P10/P50/P90 | Apuntar, no leer |
| 2:15 | Mostrar IC con semáforo | "Verde/amarillo/rojo" |
| 3:00 | Escribir pregunta al chat | Literal: "¿Vale la pena salir ahora...?" |
| 3:45 | Leer respuesta del agente | Resaltar el insight, no leer todo |
| 4:00 | Activar perturbación | Toggle "Manifestación" |
| 4:20 | Comparar bandas antes/después | Narrar el cambio del IC |
| 4:40 | Cierre con resumen | "5 fuentes, bandas, IC, perturbaciones, agente" |
| 5:00 | QnA | "¿Preguntas, profesor?" |

---

**Carlos Armando López Encino**
Diplomado en Ciencia de Datos · FES Acatlán · UNAM
Abril 2026
