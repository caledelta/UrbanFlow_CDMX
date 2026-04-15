# 🎬 Guion del Video — UrbanFlow CDMX / VialAI

**Duración objetivo:** 4:45 – 5:00 minutos (máximo 5 min según rúbrica)
**Formato:** MP4, 1920×1080, 30 fps, audio mono 128 kbps
**Layout OBS:** cámara web en esquina inferior derecha (~20% del área), slides como fuente principal
**Tono:** TED talk en español. Rigor + emoción. Frases cortas. Pausas que respiren. Una idea por respiración.
**Presentación referenciada:** `UrbanFlow_CDMX_Presentacion.pptx` (22 slides — versión actualizada)

---

## 📋 Antes de grabar — Checklist técnico

### Setup de OBS Studio

- [ ] **Escena principal:** `VialAI_Video_Final`
- [ ] **Fuente 1 — Presentación:** PowerPoint en modo presentador o PDF full-screen (1920×1080 cubriendo todo el canvas)
- [ ] **Fuente 2 — Cámara web:** posicionada en esquina inferior derecha con marco redondo (filtro "Mask/Blend")
  - Tamaño: 360×360 px
  - Posición: `x=1540, y=700` (margen de 20 px al borde)
- [ ] **Fuente 3 — Micrófono:** monitoreado. Nivel pico entre -12 y -6 dB, nunca clipping
- [ ] **Filtros recomendados en el mic:** Noise Suppression (RNNoise), Compressor (threshold -18 dB, ratio 3:1), Limiter (-3 dB)
- [ ] **Resolución de salida:** 1920×1080 @ 30 fps, bitrate 6000 kbps, CBR
- [ ] **Formato:** MP4 (contenedor) con codec H.264 + AAC

### Checklist personal

- [ ] Agua al lado (no en cámara)
- [ ] Celular en silencio y lejos del micrófono
- [ ] Puerta cerrada, pedir silencio a quienes estén cerca
- [ ] Camisa/playera lisa (patrones causan moiré en cámara)
- [ ] Buena iluminación frontal (ventana al frente, NO detrás)
- [ ] Mirar a la cámara web, no al monitor
- [ ] Respirar antes de empezar y sonreír

### Checklist del contenido a mostrar

- [ ] `UrbanFlow_CDMX_Presentacion.pptx` (versión 22 slides) abierta en modo presentador
- [ ] Este guion abierto en un segundo monitor o impreso
- [ ] Cronómetro visible (puede ser el del celular en modo avión)

---

## 🎥 Estructura del video por bloques de tiempo

```
┌─────────────────────────────────────────────────────────────────┐
│  0:00 — 0:25   APERTURA — el gancho (Slide 1)                   │
│  0:25 — 0:55   EL DOLOR — 152 horas (Slides 2-3)                │
│  0:55 — 1:15   LA PROMESA — agenda (Slide 4)                    │
│  1:15 — 1:55   LA SOLUCIÓN — Markov + Monte Carlo (Slides 5-7)  │
│  1:55 — 2:25   LA INNOVACIÓN — perturbaciones + IC (Slides 8-9) │
│  2:25 — 3:25   COMO USARLO — los 5 pasos (Slides 13-18)         │
│  3:25 — 3:55   LA PRUEBA — validación 11.9% vs 19% (Slide 11)   │
│  3:55 — 4:30   EL NEGOCIO — última milla 15.6B (Slides 19-20)   │
│  4:30 — 5:00   EL CIERRE — el ciclo y el llamado (Slides 21-22) │
└─────────────────────────────────────────────────────────────────┘
```

> **Nota sobre slides omitidas:** las slides 10 (demo narrativa estática) y 12 (diagrama del agente) están cubiertas dentro del bloque "Cómo usarlo" (slides 13-18) que muestra el sistema funcionando paso a paso. Si te sobra tiempo, insértalas en el bloque correspondiente; si vas justo, sáltalas.

---

## 🎤 GUION LÍNEA POR LÍNEA — TONO TED TALK

> **Cómo leer este guion:**
> - **[NEGRITAS EN CORCHETES]** = acción que haces con las slides o la cámara
> - *Cursivas* = dirección de tono (énfasis, pausa, suavizar)
> - **(0:XX)** = tiempo objetivo de inicio del bloque
> - Las líneas sin marca son lo que dices literalmente
> - Las **palabras en negrita dentro del diálogo** son énfasis al hablar (subir un poco la voz, no gritar)
> - Las pausas marcadas como `…` duran 1 segundo. `——` duran 2 segundos.

---

### 🟦 BLOQUE 1 — APERTURA: el gancho (0:00 – 0:25)

**[SLIDE 1 — Portada. Tú a cámara, sonriente, mirando al lente]**

> (0:00) Si vives en la Ciudad de México, te voy a hacer una pregunta incómoda…

*[Pausa corta — 1 segundo, sostener la mirada]*

> (0:05) ¿Sabes cuántas horas de tu vida pierdes cada año atrapado en el tráfico? *…* No lo adivines. Te lo voy a decir en treinta segundos. Y te voy a decir algo más: **Google Maps no puede ayudarte con esto.** Yo construí algo que sí.

*[Sonrisa breve]*

> (0:18) Soy **Carlos López Encino**, del Diplomado en Ciencia de Datos de la FES Acatlán, y esto es **UrbanFlow CDMX**.

**[Cambio a SLIDE 2 — ZMVM contexto]**

---

### 🟦 BLOQUE 2 — EL DOLOR: 152 horas (0:25 – 0:55)

**[SLIDE 2 — Datos de la ZMVM: 21.8M habitantes, 75 municipios, 52% congestión, 5.5M vehículos]**

> (0:25) Vivimos en una de las megaciudades más grandes del continente. **Veintiuno punto ocho millones** de personas. Cinco millones y medio de vehículos. Y un nivel de congestión del **cincuenta y dos por ciento**, el más alto del planeta según TomTom.

*[Pausa breve, 1 segundo]*

**[Cambio a SLIDE 3 — el "152" gigante]**

> (0:42) Aquí está la cifra que importa. *…* **Ciento cincuenta y dos.** Horas. Al año. Eso es lo que pierde, en promedio, cada conductor de esta ciudad. *…* Seis días completos. Diecinueve jornadas laborales. **Una semana y media de tu vida — cada año — sentado, sin moverte.**

**[Cambio a SLIDE 4 — agenda]**

---

### 🟦 BLOQUE 3 — LA PROMESA: agenda (0:55 – 1:15)

**[SLIDE 4 — Agenda con 3 bloques: Datos y metodología, VialAI en acción, Estrategia]**

> (0:55) En los próximos cuatro minutos te voy a contar tres cosas. *…* Primero: por qué los modelos actuales fallan, y cómo las cadenas de Markov y Monte Carlo resuelven el problema. Segundo: cómo se usa VialAI, paso a paso. Y tercero: por qué esto vale **quince mil seiscientos millones de dólares** al año.

*[Pausa breve, 1 segundo, sonrisa cómplice]*

> (1:12) Empecemos por los datos.

**[Cambio a SLIDE 5 — 5 fuentes]**

---

### 🟦 BLOQUE 4 — LA SOLUCIÓN: Markov + Monte Carlo (1:15 – 1:55)

**[SLIDE 5 — KPIs: 5 fuentes, 10K trayectorias, 3 estados, 11 perturbaciones, 720 tests, <500ms]**

> (1:15) VialAI integra **cinco fuentes de datos en vivo**: TomTom para el tráfico actual, OpenWeatherMap para el clima, Google Maps para distancia, y el portal del C5 de la CDMX para histórico de incidentes. Todo esto alimenta un motor que hice desde cero, **vectorizado**, que responde en menos de medio segundo. Más de **setecientos veinte tests automatizados** lo respaldan.

**[Cambio a SLIDE 6 — Markov + matriz de transición]**

> (1:30) El motor usa una **cadena de Markov de tres estados**: Fluido, Lento, Congestionado. Y la regla es simple: el estado del próximo minuto solo depende del estado de este minuto. *…* Lo bonito es la diagonal. **Empeorar es siempre más probable que mejorar.** Eso es lo que tu intuición ya sabía. Ahora es matemática.

**[Cambio a SLIDE 7 — Monte Carlo histograma]**

> (1:45) Y sobre esa cadena, simulo **diez mil trayectorias posibles** de tu viaje. Eso me da una distribución completa, no un número solo. Tres percentiles: P10, P50, P90. Ahí nace lo nuevo.

**[Cambio a SLIDE 8 — perturbaciones]**

---

### 🟦 BLOQUE 5 — LA INNOVACIÓN: perturbaciones + IC (1:55 – 2:25)

**[SLIDE 8 — Perturbaciones: Metro L1, Estadio Azteca, marcha 9 marzo, Navidad]**

> (1:55) Aquí viene lo que **TomTom no puede ver**. *…* Cuando cierran la Línea 1 del Metro, miles de personas se suben al auto. Cuando hay partido en el Azteca, tres kilómetros a la redonda colapsan. Cuando es la marcha del 9 de marzo, Reforma se bloquea. *…* VialAI tiene **once perturbaciones contextuales** calibradas con datos del C5. Tú las activas con un clic, y la matriz de Markov se ajusta antes de simular.

**[Cambio a SLIDE 9 — Índice de Confiabilidad]**

> (2:13) Y aquí está la métrica que cambia todo. *…* El **Índice de Confiabilidad**. Un solo número, en formato semáforo. **Verde**: la ruta es predecible, prométela sin miedo. **Amarillo**: agrega buffer. **Rojo**: no prometas hora exacta. Ningún sistema de navegación en el mercado entrega esto.

**[Cambio a SLIDE 13 — divisor "Cómo usar VialAI"]**

---

### 🟦 BLOQUE 6 — CÓMO USARLO: los 5 pasos (2:25 – 3:25) ⭐ BLOQUE CLAVE

> *[Este bloque es el corazón de la rúbrica del profesor: "usabilidad". Dale energía y velocidad. Cada slide es 10 segundos.]*

**[SLIDE 13 — divisor]**

> (2:25) Pero todo esto es teoría hasta que se usa. Te muestro **cómo se usa VialAI en cinco pasos**.

**[Cambio a SLIDE 14 — Paso 1: Definir el viaje]**

> (2:32) **Paso uno**: defines el viaje. Origen, destino. VialAI calcula la distancia real por carretera y detecta el estado inicial del tráfico desde TomTom.

**[Cambio a SLIDE 15 — Paso 2: Añadir el contexto]**

> (2:42) **Paso dos**: añades el contexto. La hora, el clima — automático — y activas cualquier evento conocido. ¿Hay cierre del Metro? Lo activas.

**[Cambio a SLIDE 16 — Paso 3: Leer las bandas]**

> (2:52) **Paso tres**: lees las bandas. *…* No te entrego un número. Te entrego **tres**. Y un veredicto. *…* Veintiocho minutos en el mejor caso. Treinta y siete en el típico. **Cincuenta y tres en el peor.** Y un IC en rojo: la ruta es impredecible.

**[Cambio a SLIDE 17 — Paso 4: Conversar con el agente]**

> (3:05) **Paso cuatro**: conversas con el agente. *…* Le preguntas en lenguaje natural: «¿salgo ahora o espero?» Y el agente, que tiene seis herramientas conectadas al motor, te responde con una recomendación. *No con un cálculo más — con un consejo.*

**[Cambio a SLIDE 18 — Paso 5: Tomar la decisión]**

> (3:18) **Paso cinco**: decides. Salir ahora con IC rojo, o esperar treinta minutos hasta que el IC pase a amarillo. VialAI te dice exactamente cuánto buffer agregar para llegar a tu reunión de las nueve y media. *…* Cinco minutos antes de salir, ya sabes qué hacer.

**[Cambio a SLIDE 11 — validación empírica]**

---

### 🟦 BLOQUE 7 — LA PRUEBA: validación (3:25 – 3:55)

**[SLIDE 11 — KPIs validación: 11.9% MAPE, 93% cobertura, 4.8 min MAE, 19% TomTom]**

> (3:25) Pero, ¿esto **funciona**? *…* Lo validé sobre **treinta rutas reales** de la ZMVM, en hora pico, contra los tiempos observados.

*[Pausa breve, 1 segundo]*

> (3:35) **Once punto nueve por ciento de error.** *…* TomTom, el líder del mercado, falla por **diecinueve por ciento**. Soy **siete puntos porcentuales más preciso** que la herramienta que usan los repartidores hoy. *…* Y mi banda P10-P90 captura el resultado real el **noventa y tres por ciento** de las veces, cuando lo nominal era ochenta. *Esto no es un proyecto académico. Es algo que funciona mejor que lo que ya existe.*

**[Cambio a SLIDE 19 — estrategia mercado]**

---

### 🟦 BLOQUE 8 — EL NEGOCIO: última milla (3:55 – 4:30)

**[SLIDE 19 — Estrategia B2B: USD 15.6B + 3 perfiles]**

> (3:55) ¿Y para quién es esto? *…* No para ti, conductor individual. Es para el **negocio que vive de prometer ventanas de entrega**: la última milla. *…* En México este mercado vale **quince mil seiscientos millones de dólares** este año, y crece al doce por ciento anual. Tres usuarios objetivo: el dispatcher que promete SLAs, el operations manager de la PyME, y el conductor en ruta.

**[Cambio a SLIDE 20 — 4 accionables]**

> (4:13) Y VialAI habilita cuatro acciones concretas: prometer ventanas de **cuarenta minutos** en lugar de cuatro horas. Asignar rutas verdes a conductores nuevos, rojas a los expertos. Alertar al dispatcher antes de que ocurra el retraso. Y comparar predicho contra real al final del día para recalibrar.

**[Cambio a SLIDE 21 — ciclo operativo]**

---

### 🟦 BLOQUE 9 — EL CIERRE: el ciclo y el llamado (4:30 – 5:00)

**[SLIDE 21 — Ciclo operativo de 8 pasos]**

> (4:30) Todo esto vive en un **ciclo que se repite cada hora**. *…* Ingesta, discretización, matriz, perturbaciones, Monte Carlo, bandas, agente, decisión. *…* Cada día el modelo se recalibra. Cada hora aprende.

**[Cambio a SLIDE 22 — Gracias / preguntas]**

> (4:43) En CDMX perdemos ciento cincuenta y dos horas al año. *…* No las vamos a recuperar todas. Pero podemos dejar de sorprendernos. Podemos dejar de prometer cosas que no podemos cumplir. Podemos dejar de tratar al tráfico como un misterio, **cuando en realidad es una distribución**.

*[Pausa, 2 segundos. Mirar a la cámara directo.]*

> (4:54) Soy Carlos López Encino. Esto fue UrbanFlow CDMX. *…* Gracias.

*[Sonrisa breve, sostener mirada 2 segundos antes de cortar la grabación.]*

---

## 📊 Cheatsheet de números clave (memorizar)

| Concepto | Número exacto | Cómo decirlo en voz alta |
|---|---|---|
| Habitantes ZMVM | 21.8M | "veintiuno punto ocho millones" |
| Municipios ZMVM | 75 | "setenta y cinco" |
| Vehículos en circulación | 5.5M | "cinco millones y medio" |
| Nivel de congestión | 52% | "cincuenta y dos por ciento" |
| Horas perdidas/año/conductor | 152 | "ciento cincuenta y dos" |
| Trayectorias Monte Carlo | 10,000 | "diez mil" |
| Estados de Markov | 3 | "tres" |
| Perturbaciones del catálogo | 11 | "once" |
| Tests automatizados | 720+ | "más de setecientos veinte" |
| Latencia por consulta | <500 ms | "menos de medio segundo" |
| MAPE de VialAI | 11.9% | "once punto nueve por ciento" |
| MAPE de TomTom | 19.0% | "diecinueve por ciento" |
| Ventaja sobre TomTom | 7.1 pp | "siete puntos porcentuales" |
| Cobertura empírica P10-P90 | 93% | "noventa y tres por ciento" |
| Cobertura nominal | 80% | "ochenta por ciento" |
| Mercado última milla México 2025 | USD 15.6B | "quince mil seiscientos millones de dólares" |
| Proyección 2030 | USD 27.3B | "veintisiete mil trescientos millones" |
| CAGR | 11.81% | "doce por ciento anual" |

---

## 🚨 Frases poderosas que NO debes cambiar

Estas son los anclajes emocionales del guion. Memorízalas exactas:

1. **"Si vives en la Ciudad de México, te voy a hacer una pregunta incómoda."** ← apertura
2. **"Una semana y media de tu vida — cada año — sentado, sin moverte."** ← golpe del 152
3. **"Empeorar es siempre más probable que mejorar."** ← matriz de Markov
4. **"Aquí viene lo que TomTom no puede ver."** ← entrada a perturbaciones
5. **"No te entrego un número. Te entrego tres. Y un veredicto."** ← bandas
6. **"No con un cálculo más — con un consejo."** ← agente VialAI
7. **"Esto no es un proyecto académico. Es algo que funciona mejor que lo que ya existe."** ← validación
8. **"Cuando en realidad es una distribución."** ← cierre

---

## ⚠️ Errores comunes a evitar

- **No leas el guion mirando abajo.** Memoriza bloques de 15 segundos máximo. Mira a la cámara.
- **No corras.** El TED talk respira. Si vas más rápido de 165 palabras por minuto, suenas a vendedor.
- **No subas la voz al final de cada frase.** El upspeak debilita la autoridad. Termina las frases bajando.
- **No digas "este proyecto"**. Di "UrbanFlow", "VialAI", "lo que construí". El producto tiene nombre.
- **No te disculpes** ("perdón si no se ve bien", "espero que se entienda"). Asume que se entiende.
- **No leas los KPIs en voz pasiva.** "El sistema obtuvo un MAPE de..." → "Soy siete puntos más preciso que TomTom."
- **No rías nervioso.** Si necesitas pausar, **pausa en silencio**. El silencio comunica seguridad.

---

## 📝 Notas de edición si te pasas de tiempo

Si el primer take dura más de 5 minutos, recortar **en este orden estricto**:

1. Cortar la frase de los 5.5M de vehículos en bloque 2 (slide 2). Ahorra 4 segundos.
2. Acortar bloque de Markov: omitir "Lo bonito es la diagonal." y siguiente. Ahorra 6 segundos.
3. En el bloque de los 5 pasos, comprimir paso 1 y paso 2 juntos en una frase única ("Defines el viaje y el contexto en dos pasos rápidos: origen-destino, hora-clima-perturbaciones."). Ahorra 8 segundos.
4. En estrategia, omitir los 3 perfiles de usuario y dejar solo el mercado. Ahorra 10 segundos.

**No cortes** en este orden:
- La apertura ("pregunta incómoda") — es el gancho
- El número 152 — es el dolor
- La validación 11.9% vs 19% — es la prueba
- El cierre "una distribución" — es el ancla emocional

---

## 🎬 Plan de práctica (1.5 horas antes de grabación final)

1. **00:00 – 00:15** — Leer todo el guion en voz alta, sin slides, sin cámara, solo cronómetro. Anotar dónde te trabas.
2. **00:15 – 00:30** — Releer los 8 bloques uno por uno, cada uno cronometrado. Si un bloque excede su tiempo objetivo por más de 5 segundos, simplificar.
3. **00:30 – 00:45** — Setup OBS según checklist arriba. Audio test, video test, layout test.
4. **00:45 – 01:00** — Ensayo completo CON slides pero SIN grabar. Mirar a la cámara, no al monitor.
5. **01:00 – 01:20** — Toma 1. Grabar de corrido. Si te equivocas en una palabra, sigue. Si te equivocas dos veces seguidas, corta y rehaz solo ese bloque.
6. **01:20 – 01:30** — Toma 2 si Toma 1 tuvo más de 2 fallos.
7. **Edición posterior** — Cortar inicio y fin (pre-roll/post-roll). Normalizar audio a -16 LUFS. Exportar MP4 H.264 + AAC, 1920×1080 @ 30fps, bitrate 6000 kbps.

---

## ✅ Checklist final antes de subir el video al repo

- [ ] Duración entre **4:45 y 5:00 minutos** (rúbrica máximo 5)
- [ ] Tu cara visible **en todo momento** (rúbrica explícita)
- [ ] Audio claro, sin ruido de fondo perceptible
- [ ] Slides legibles (sin estiramientos ni recortes)
- [ ] Formato **MP4** (rúbrica explícita)
- [ ] Resolución **1920×1080** mínimo
- [ ] Subido al repo en `docs/UrbanFlow_CDMX_Video.mp4`
- [ ] Mencionado en `README_PROFESOR.md` y `README_Entregables.md`

---

*Guion v2 · Mapeado a presentación de 22 slides · Tono TED talk · Abril 2026*
