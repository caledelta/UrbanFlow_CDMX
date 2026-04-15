# 📬 UrbanFlow CDMX / VialAI — Paquete de Entrega Final

**Para:** Prof. Fernando Barranco Rodríguez
**De:** Carlos Armando López Encino
**Asunto:** Proyecto Integrador Final del Diplomado en Ciencia de Datos
**Fecha:** Abril 2026

---

## 🎯 ¿Qué es este paquete?

Este es el paquete completo del proyecto integrador final del Diplomado en Ciencia de Datos. El proyecto se llama **UrbanFlow CDMX** y el sistema se llama **VialAI**: un agente conversacional que predice tiempos de viaje en la Zona Metropolitana del Valle de México con bandas de incertidumbre probabilísticas, específicamente diseñado para el contexto mexicano.

Los archivos están organizados para que pueda navegar el proyecto en **15 minutos** si solo quiere una visión general, o en **90 minutos** si quiere una revisión técnica completa.

---

## 🚀 Acceso inmediato al sistema en vivo

Si solo tiene 5 minutos y quiere ver el sistema funcionando:

🔗 **https://urbanflow-cdmx.streamlit.app**
*(URL pública, sin requerir instalación)*

Le sugiero tres pruebas concretas:

1. **Predicción base** — Origen: Polanco, Destino: Santa Fe, Hora: 08:15. Observe la banda P10/P50/P90 y el Índice de Confiabilidad.

2. **Activar una perturbación** — En el panel lateral active "Marcha 9 de marzo" y recalcule. Note cómo la mediana sube y el IC pasa de amarillo a rojo.

3. **Chat con el agente** — Pregunte: *"¿Vale la pena salir ahora para Santa Fe, o espero 30 minutos?"*. Observe cómo VialAI razona y entrega una recomendación accionable.

🔗 **Código fuente completo:** https://github.com/caledelta/UrbanFlow_CDMX
*(720 tests automatizados, todos pasando al 100%)*

---

## 📂 Contenido del paquete

Los archivos están ordenados aproximadamente según el orden sugerido de lectura:

### 1️⃣ `proyecto_ZMCDMX_v3.pdf` (23 páginas) — **LEA PRIMERO**

Artículo técnico completo en formato académico. Contiene todo lo que necesita saber sobre el proyecto:

- Motivación y contexto (con datos reales de INEGI, DataMéxico y TomTom Traffic Index 2024)
- Arquitectura del sistema (diagrama de 5 capas)
- Marco teórico: cadenas de Markov y simulación Monte Carlo
- Implementación vectorizada del motor
- Catálogo de 11 perturbaciones contextuales específicas de la ZMVM
- Agente conversacional VialAI con structured outputs y function calling
- **Validación empírica sobre 30 rutas reales** con MAPE 11.9% (vs 19% de TomTom)
- Estrategia de negocio para B2B de última milla (mercado de USD 15.6B en México)
- Conclusiones y trabajo futuro

**Tiempo estimado de lectura:** 25-30 minutos.

### 2️⃣ `UrbanFlow_CDMX_Presentacion.pptx` (16 slides · 540 KB)

Presentación ejecutiva del proyecto con paleta "Midnight Executive". Sigue el hilo narrativo del artículo pero en formato visual. Incluye una demo narrativa paso a paso de la ruta Polanco → Santa Fe y cuatro KPIs de validación.

**Versión PDF alternativa:** `UrbanFlow_CDMX_Presentacion.pdf` (524 KB) por si prefiere no abrir PowerPoint.

**Tiempo estimado:** 10 minutos.

### 3️⃣ `UrbanFlow_CDMX_Colab.ipynb` (49 KB — versión limpia) + `UrbanFlow_CDMX_Colab_executed.ipynb` (964 KB — versión pre-ejecutada)

Notebook reproducible diseñado específicamente para Google Colab. **Corre end-to-end sin credenciales ni APIs externas** gracias a que los datos están cacheados inline. Reproduce exactamente los resultados de validación reportados en el artículo.

**Para verificar usted mismo la reproducibilidad:**

1. Suba `UrbanFlow_CDMX_Colab.ipynb` a [colab.research.google.com](https://colab.research.google.com)
2. Runtime → Run all
3. Debería reportar `MAPE del P50: ~11.9%` y `Cobertura banda P10-P90: ~93.3%`

**O bien**, si prefiere no ejecutarlo, abra `UrbanFlow_CDMX_Colab_executed.ipynb` que ya tiene todos los outputs visibles.

### 4️⃣ `VialAI_Pitch_B2B.pdf` (4 páginas · 224 KB)

Propuesta ejecutiva comercial del sistema para el nicho de logística B2B de última milla. Contiene:

- Diagnóstico del mercado (datos de Mordor Intelligence, TomTom Index, AMVO)
- Fórmula del Índice de Confiabilidad destacada con justificación matemática
- Caso de negocio con cálculo concreto (\$650K MXN/año de sobrecosto para una PyME típica)
- Cuatro accionables habilitados por VialAI
- Tabla comparativa VialAI vs Google/Waze vs TomTom
- Modelo SaaS freemium con tiers en pesos mexicanos

Este documento está pensado como material de venta que el autor podría usar en reuniones reales con operadores de última milla. **Es opcional para la evaluación académica**, pero muestra cómo el proyecto tiene aplicación práctica fuera del aula.

**Tiempo estimado:** 10 minutos.

### 5️⃣ `Inventario_Proyecto.pdf` (12 páginas · 265 KB)

Inventario exhaustivo de **todo** lo que se construyó durante el proyecto, organizado cronológicamente por fase de trabajo (concepción → arquitectura → datos → EDA → motor → perturbaciones → agente → UI → validación → documentación). Incluye:

- Todas las herramientas y bibliotecas utilizadas
- Todas las APIs externas consumidas
- Todas las fuentes de datos públicos
- Todos los recursos académicos y bibliográficos consultados
- Retos técnicos reales encontrados y cómo se resolvieron
- Métricas finales del proyecto (720 tests, 5 fuentes, 11 perturbaciones, etc.)

Útil si quiere entender el alcance total del trabajo o verificar que el proyecto es reproducible.

**Tiempo estimado:** 10 minutos (lectura rápida).

---

## 🎓 Cobertura de la rúbrica de evaluación

| Criterio de la rúbrica | Peso | Archivo que lo cubre |
|---|---|---|
| Documento técnico | 15 pts | `proyecto_ZMCDMX_v3.pdf` |
| Estrategia de negocio | 15 pts | §11 del artículo + `VialAI_Pitch_B2B.pdf` |
| Notebook reproducible | 15 pts | `UrbanFlow_CDMX_Colab.ipynb` |
| Presentación | 10 pts | `UrbanFlow_CDMX_Presentacion.pptx` |
| Interfaz de uso | 10 pts | https://urbanflow-cdmx.streamlit.app |
| Video demostrativo (5 min) | 20 pts | Se entrega por separado |
| Demo en vivo (5 min) | 25 pts | Presentación sincrónica |
| **TOTAL** | **110 pts** | |

---

## 🔍 Ruta de lectura sugerida según tiempo disponible

### Si tiene 15 minutos:

1. Leer el **resumen** del artículo (página 2) — 3 min
2. Abrir la URL de Streamlit y hacer **una predicción** Polanco → Santa Fe — 5 min
3. Hojear la **presentación** saltando a los slides 10 (demo narrativa) y 11 (validación) — 5 min
4. Cerrar con el **slide 13** (estrategia B2B) — 2 min

### Si tiene 45 minutos:

1. Lectura completa del **artículo técnico** — 25 min
2. Navegación del **sistema en vivo** con las 3 pruebas sugeridas arriba — 15 min
3. Hojear el **pitch B2B** — 5 min

### Si tiene 90 minutos (revisión completa):

1. Lectura detallada del **artículo técnico** prestando atención a §8.4 (perturbaciones) y §10 (validación) — 35 min
2. **Ejecutar el notebook** en Google Colab y verificar los números de validación — 20 min
3. **Navegar el sistema en vivo** explorando todas las perturbaciones del catálogo — 15 min
4. Revisar la **presentación** y el **pitch B2B** — 10 min
5. Hojear el **inventario del proyecto** — 10 min

---

## 💬 Contacto

Para cualquier pregunta, aclaración o sugerencia sobre el proyecto:

**Carlos Armando López Encino**
Diplomado en Ciencia de Datos · FES Acatlán · UNAM

- 📂 GitHub: https://github.com/caledelta/UrbanFlow_CDMX
- 🌐 Sistema en vivo: https://urbanflow-cdmx.streamlit.app

---

## 🙏 Agradecimientos

Gracias profesor Barranco por el seguimiento durante el diplomado y por el rigor metodológico que transmitió en sus clases. Este proyecto integra múltiples áreas del programa (procesos estocásticos, métodos de simulación, ingeniería de datos, modelos de lenguaje y desarrollo de productos de datos) y no habría sido posible sin ese bagaje.

Quedo a sus órdenes para la defensa en vivo del proyecto.

---

*Documento preparado por Carlos Armando López Encino · Abril 2026*
