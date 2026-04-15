# 🎬 Guion del Video — UrbanFlow CDMX / VialAI

**Duración objetivo:** 4:45 – 5:00 minutos (máximo 5 min según rúbrica)
**Formato:** MP4, 1920×1080, 30 fps, audio mono 128 kbps
**Layout OBS:** Cámara web en esquina inferior derecha (≈20% del área), slides como fuente principal

---

## 📋 Antes de grabar — Checklist técnico

### Setup de OBS Studio

- [ ] **Escena principal:** `VialAI_Video_Final`
- [ ] **Fuente 1 — Presentación:** Ventana de PowerPoint en modo presentador o PDF full-screen (1920×1080 cubriendo todo el canvas)
- [ ] **Fuente 2 — Cámara web:** Dispositivo de captura de video, posicionado en esquina inferior derecha con marco redondo (filtro "Mask/Blend")
  - Tamaño: 360×360 px aproximadamente
  - Posición: `x=1540, y=700` (deja margen de 20 px al borde)
- [ ] **Fuente 3 — Micrófono:** Audio input device, monitoreado. Nivel pico entre -12 y -6 dB, nunca clipping
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

- [ ] `UrbanFlow_CDMX_Presentacion.pptx` abierta en modo presentador
- [ ] Este guion abierto en un segundo monitor o impreso
- [ ] Contador/cronómetro visible (puede ser el del celular en modo avión)

---

## 🎥 Estructura del video por bloques de tiempo

```
┌──────────────────────────────────────────────────────────┐
│  0:00 — 0:20   Apertura y hook (20 seg)                  │
│  0:20 — 1:00   Problema y magnitud (40 seg)              │
│  1:00 — 1:50   Solución técnica: Markov + Monte Carlo    │
│  1:50 — 2:40   Innovación: perturbaciones + IC (50 seg)  │
│  2:40 — 3:30   Demo narrativa Polanco → Santa Fe         │
│  3:30 — 4:10   Validación empírica (40 seg)              │
│  4:10 — 4:50   Estrategia B2B última milla (40 seg)      │
│  4:50 — 5:00   Cierre (10 seg)                           │
└──────────────────────────────────────────────────────────┘
```

---

## 🎤 GUION LÍNEA POR LÍNEA

> **Cómo leer este guion:**
> - **[NEGRITAS]** = acción que haces con las slides o la cámara
> - *Cursivas* = dirección de tono (entusiasta, pausa, énfasis)
> - Las líneas sin marca son lo que dices literalmente
> - Los tiempos entre paréntesis son objetivos, no obligatorios

---

### 🟦 BLOQUE 1 — Apertura (0:00 – 0:20)

**[SLIDE 1 – Portada. Tú a cámara, sonriente]**

> (0:00) Hola, soy **Carlos López Encino**, estudiante del Diplomado en Ciencia de Datos de la FES Acatlán.

> (0:06) En los próximos cinco minutos les voy a presentar **UrbanFlow CDMX**, un sistema que cambia la forma en que predecimos tiempos de viaje en la Ciudad de México.

> (0:14) Y lo hace respondiendo una pregunta que Google Maps no puede responder: ***¿qué tan confiable es mi ruta?***

**[Pausa breve, cambio de slide]**

---

### 🟦 BLOQUE 2 — El problema (0:20 – 1:00)

**[SLIDE 3 – Número gigante 152]**

> (0:20) La CDMX es la ciudad **número uno del mundo en congestión vehicular** según el TomTom Traffic Index 2024.

> (0:27) Cada conductor pierde **152 horas al año** atrapado en tráfico. Son seis días completos de su vida, cada año.

> (0:34) Pero el problema real no es la lentitud. Es la **impredecibilidad**.

**[Apuntar con el cursor al texto del panel derecho]**

> (0:40) El mismo viaje, a la misma hora, puede variar entre 20 y 40 minutos dependiendo de una manifestación, una lluvia o un cierre del Metro.

> (0:50) Los sistemas actuales te dan **un solo número**. Y ese número oculta la varianza. El tráfico no es un número: es una distribución.

---

### 🟦 BLOQUE 3 — Solución técnica (1:00 – 1:50)

**[SLIDE 6 – Cadenas de Markov + matriz]**

> (1:00) Mi solución combina **dos herramientas clásicas** de la estadística.

> (1:04) Primero, modelo la dinámica del tráfico como una **cadena de Markov de tres estados**: Fluido, Lento y Congestionado.

**[Apuntar a la matriz de la derecha]**

> (1:12) Estimé la matriz de transición a partir de datos históricos del C5 CDMX. Los elementos diagonales dominan cada fila, y eso captura algo que cualquier conductor de CDMX intuye: **el tráfico tiene inercia**. Si estás atorado, lo más probable es que sigas atorado.

**[Cambio a SLIDE 7 – Monte Carlo + histograma]**

> (1:26) Segundo, sobre esa cadena ejecuto una **simulación Monte Carlo con diez mil trayectorias** por cada consulta.

> (1:34) Cada trayectoria es un posible viaje, con sus velocidades muestreadas desde una distribución normal truncada.

> (1:40) El resultado no es un número, son **tres percentiles**: P10, P50 y P90. Una banda de incertidumbre completa, calculada en menos de medio segundo en una laptop sin GPU.

---

### 🟦 BLOQUE 4 — Innovación propia (1:50 – 2:40)

**[SLIDE 8 – Perturbaciones contextuales]**

> (1:50) Ahora, aquí viene la parte que me parece más interesante del proyecto.

> (1:55) TomTom y Google Maps miden velocidades con GPS, pero **no pueden ver** cierres del Metro, manifestaciones o eventos masivos hasta que ya pasaron.

> (2:04) Yo construí un catálogo de **perturbaciones contextuales** que modifican la matriz de Markov *antes* de ejecutar la simulación.

**[Apuntar a los 4 cuadros de perturbaciones]**

> (2:12) Cada evento tiene un factor multiplicativo calibrado. Una marcha del 9 de marzo, por ejemplo, **aumenta la mediana del tiempo de viaje en 16 minutos** sobre una ruta de 15 km, y el Índice de Confiabilidad pasa de 0.53 a 0.70, es decir, de amarillo a rojo.

**[Cambio a SLIDE 9 – Índice de Confiabilidad con semáforo]**

> (2:22) Y todo esto se resume en una sola métrica que inventé para este proyecto: el **Índice de Confiabilidad** o IC.

> (2:29) Es la amplitud relativa de la banda. Un número adimensional que convierto en un semáforo verde, amarillo o rojo. **Un dispatcher lo interpreta en dos segundos.**

---

### 🟦 BLOQUE 5 — Demo narrativa (2:40 – 3:30)

**[SLIDE 10 – Polanco → Santa Fe]**

> (2:40) Veamos un ejemplo concreto. Polanco a Santa Fe, ocho quince de la mañana.

**[Apuntar al panel izquierdo]**

> (2:46) El sistema ingiere la distancia real por carretera de TomTom Routing: 12.8 km. El ratio de congestión de TomTom Traffic indica estado Lento. OpenWeatherMap reporta llovizna, así que aplicamos un factor climático de 0.88.

**[Apuntar al panel derecho, en orden P10 → P50 → P90 → IC]**

> (3:00) La simulación devuelve: P10 de 28 minutos en el mejor escenario, mediana de 37 minutos, y P90 de 53 minutos en el pesimista.

> (3:10) El Índice de Confiabilidad da 0.68, **ruta roja**. Esto significa que esta ruta es **impredecible**.

> (3:17) Y la recomendación operativa de VialAI es clara: **sal con 16 minutos extra** sobre la mediana para tener 90% de probabilidad de llegar a tiempo.

> (3:25) Este tipo de recomendación es literalmente la diferencia entre cumplir o romper un SLA de entrega.

---

### 🟦 BLOQUE 6 — Validación (3:30 – 4:10)

**[SLIDE 11 – Validación empírica 4 KPIs]**

> (3:30) ¿Pero cómo sé que esto realmente funciona? Corrí una validación empírica sobre **30 rutas reales** de la ZMVM, comparando contra el ETA de TomTom Routing como ground truth.

**[Apuntar a los 4 cuadros]**

> (3:38) El MAPE del P50 fue de **11.9%**, por debajo del umbral del 15% que me puse como objetivo.

> (3:46) La cobertura empírica de la banda P10-P90 fue del **93%**, consistente con la cobertura nominal del 80% — las bandas están bien calibradas.

> (3:55) Y el MAPE de TomTom ETA sobre las mismas rutas fue de **19%**. Mi sistema es **siete puntos porcentuales más preciso** que TomTom.

> (4:05) No solo eso: VialAI además cuantifica la incertidumbre, que TomTom no hace.

---

### 🟦 BLOQUE 7 — Estrategia (4:10 – 4:50)

**[SLIDE 13 – Estrategia B2B última milla]**

> (4:10) ¿Para quién es esto? El nicho que identifiqué es la **logística B2B de última milla en la ZMVM**.

> (4:16) Es un mercado de **quince mil seiscientos millones de dólares** en México en 2025, que crece al 11.8% anual según Mordor Intelligence.

> (4:25) En este sector, los costos de última milla representan hasta el 53% del gasto logístico total. Y el problema estructural no es la velocidad promedio, es la **varianza**.

**[Apuntar a los 3 usuarios del panel derecho]**

> (4:34) VialAI sirve a tres perfiles concretos: el dispatcher que promete ventanas de entrega, el operations manager que planea flotillas, y el conductor que decide si seguir o desviar en ruta.

> (4:45) Todos ellos toman mejores decisiones cuando conocen la banda completa, no solo un promedio.

---

### 🟦 BLOQUE 8 — Cierre (4:50 – 5:00)

**[SLIDE 16 – Gracias]**

> (4:50) El código completo, los 720 tests que pasa el motor y el agente conversacional están en **GitHub, caledelta / UrbanFlow_CDMX**.

> (4:56) Muchas gracias por su atención. *(sonrisa, pausa)*

**[Dejar el último frame 2 segundos y cortar grabación en OBS]**

---

## 🛠️ Notas de edición post-grabación

### Si te pasas de los 5 minutos

Corta **en este orden** (del menos crítico al más crítico):

1. Bloque 1 — puedes comprimir la intro a 12 segundos diciendo solo "Soy Carlos López, estudiante del Diplomado. Les presento UrbanFlow CDMX."
2. Bloque 4 — puedes quitar la frase sobre el cierre del Metro y dejar solo el ejemplo de la manifestación.
3. Bloque 6 — puedes fundir el punto del MAPE con el de cobertura en una sola frase.

**No cortes** bajo ningún concepto:
- La demo narrativa (Bloque 5) — es la parte donde el jurado "ve" que el sistema funciona
- La mención del MAPE 11.9% vs TomTom 19% — es el diferenciador más fuerte
- La estrategia B2B con el número de USD 15.6B — es el pitch de negocio

### Si te sobran más de 10 segundos al final

Agrega al Bloque 7 esta línea justo antes del cierre:

> "El modelo SaaS freemium permite a una PyME probar el sistema sin fricciones, y escalar a tiers de pago cuando ya lo tiene integrado en su operación."

### Errores comunes a evitar

- **No leer el guion robóticamente.** Es mejor recordar los puntos clave y hablar natural.
- **No taparse la boca** con las manos ni tocarse el cabello frente a cámara.
- **No decir "emmm" o "este"** entre frases. Es mejor una pausa limpia.
- **No mirar al teléfono** durante la grabación. Si pierdes el hilo, pausa OBS y re-graba ese bloque.
- **Grabar por bloques si es necesario.** OBS permite pausar grabación; puedes ensamblar en DaVinci Resolve gratis.
- **Revisar el audio después de cada toma.** Un video perfecto con audio malo se descalifica automáticamente.

---

## 🎯 Práctica recomendada antes de grabar

1. **Lectura en voz alta** del guion completo, cronometrando. Objetivo: 4:45.
2. **Ensayo frente al espejo** sin cámara. Fíjate en gestos y postura.
3. **Ensayo con cámara pero sin grabar**, revisando que las slides aparezcan correctamente.
4. **Primera grabación** completa. Probablemente sale mal y es normal.
5. **Segunda grabación** corrigiendo lo detectado. Normalmente esta ya es usable.
6. **Tercera grabación** solo si las dos anteriores tuvieron errores mayores.

> **Mi recomendación:** reserva **una hora y media** para grabar el video. La primera hora es para ensayar y las grabaciones fallidas; los últimos 30 minutos son para las tomas finales.

---

## 📊 Cheatsheet de números clave para memorizar

Si olvidas algo durante la grabación, estos son **los números no negociables** que deben aparecer:

| Número | Qué es | Dónde va |
|---|---|---|
| **152 horas/año** | Horas perdidas en tráfico CDMX (TomTom 2024) | Bloque 2 |
| **10,000 trayectorias** | Simulaciones Monte Carlo por consulta | Bloque 3 |
| **3 estados** | Fluido, Lento, Congestionado | Bloque 3 |
| **500 ms** | Latencia del motor (opcional, solo si hay tiempo) | Bloque 3 |
| **+16 min** | Impacto de marcha 9 marzo sobre ruta 15 km | Bloque 4 |
| **0.53 → 0.70** | IC pasa de amarillo a rojo con la marcha | Bloque 4 |
| **11.9%** | MAPE de VialAI | Bloque 6 |
| **93%** | Cobertura empírica de banda | Bloque 6 |
| **19%** | MAPE de TomTom ETA | Bloque 6 |
| **USD 15.6B** | Mercado última milla México 2025 | Bloque 7 |

---

**Carlos Armando López Encino**
Diplomado en Ciencia de Datos · FES Acatlán · UNAM
Abril 2026
