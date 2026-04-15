# Guion narrativo — Demo en vivo de VialAI
## 5 minutos · Proyecto Integrador Final · 18 de abril de 2026

> **Propósito:** Este documento es el guion de la demostración en vivo
> (25 pts de 110 en la rúbrica). Es un guion de palabras, no una checklist.
> La checklist de preparación técnica está en `checklist_demo.md`.
>
> **Ritmo:** 5 bloques de ~1 minuto cada uno. Practicar en voz alta.
> El tono es el de alguien que **usa** la herramienta, no que la explica.

---

## Preparación (30 minutos antes, en silencio)

Revisar `checklist_demo.md` completo. El guion asume que:
- La app ya está corriendo en `http://localhost:8501`
- La ventana del navegador está maximizada
- El origen/destino está limpio (sin selección previa)
- El `.env` tiene las cuatro API keys cargadas

---

## BLOQUE 0 — Apertura (0:00–0:30)

*[Pantalla: la app abierta, mapa vacío de la ZMVM]*

> "Buenos días. Voy a mostrarles VialAI en funcionamiento.
> El problema que resuelve es simple: cuando un conductor de
> entrega en la CDMX acepta un pedido, las apps le dicen
> 'llegarás en 23 minutos'. Pero no le dicen si ese 23 puede
> convertirse en 47 por un evento que no estaba en el radar.
> Eso le cuesta dinero real: bonos de SLA perdidos, re-entregas,
> sobretiempo.
>
> VialAI no entrega un número. Entrega una distribución:
> el mejor caso, el más probable y el caso adverso.
> Y un agente que traduce eso a una recomendación concreta.
> Vamos a verlo."

*[Timing check: ~30 segundos]*

---

## BLOQUE 1 — Predicción base (0:30–1:30)

*[Acción: seleccionar Polanco como origen, Santa Fe como destino]*

> "Tengo a Miguel, repartidor, en Polanco a las 8:15 de la mañana.
> Necesita saber si llega a Santa Fe antes de las 9."

*[Acción: fijar hora 08:15, pulsar 'Predecir trayecto']*

> "El motor ejecuta 10,000 trayectorias en menos de 500
> milisegundos sobre la cadena de Markov calibrada con un millón
> de registros históricos del C5 CDMX."

*[Esperar resultados. Señalar los tres números en pantalla]*

> "Aquí tenemos:
> - P10: 19 minutos — si el tráfico fluye bien.
> - P50: 27 minutos — lo más probable. Llega a las 8:42.
> - P90: 44 minutos — si hay congestión fuerte. Llega casi a las 9.
>
> Y este número en amarillo: el Índice de Confiabilidad de 0.93.
> Le dice al conductor que esta ruta, a esta hora, tiene variabilidad
> alta. No es una ruta confiable, pero tampoco es roja.
> Miguel puede salir, pero con los ojos abiertos."

*[Timing check: ~1:30 desde inicio]*

---

## BLOQUE 2 — Perturbación (1:30–2:30)

*[Acción: activar 'Marcha 9 de marzo' en el selector lateral]*

> "Ahora activamos una perturbación contextual.
> El 8 de marzo hay una marcha que cierra Reforma y avenidas
> aledañas. VialAI tiene un catálogo de 11 eventos típicos de la
> ZMVM. Vean qué pasa."

*[Acción: pulsar 'Predecir trayecto' con perturbación activa]*

*[Señalar los números actualizados]*

> "La mediana sube de 27 a 43 minutos.
> El P90 sube de 44 a 71 minutos.
> El IC se dispara a 1.3: rojo.
>
> Esto es lo que Google Maps no calcula. No porque no quiera,
> sino porque no tiene el modelo para hacerlo.
> VialAI aplica un factor multiplicador sobre la probabilidad
> de transitar a estado Congestionado en la cadena de Markov.
> La matemática es simple; el dato es el que importa."

*[Timing check: ~2:30]*

---

## BLOQUE 3 — Chat con el agente (2:30–3:45)

*[Acción: expandir el panel 'Chat con VialAI' en la barra lateral]*

> "Ahora el agente conversacional. La demo anterior fue visual.
> Esta es la experiencia del conductor que no puede tocar la pantalla."

*[Acción: escribir en el chat: "¿Vale la pena salir ahora para
Santa Fe, o espero 30 minutos?" — con perturbación aún activa]*

*[Esperar respuesta del agente. Leer en voz alta lo que aparece.]*

> "El agente no solo recita los números. Razona sobre ellos.
> Llamó internamente a tres herramientas: motor de predicción,
> tráfico actual de TomTom, y clima de OpenWeatherMap.
> Integró todo y entregó una recomendación: qué hacer ahora.
>
> Eso es lo que diferencia un sistema de predicción de un agente.
> La diferencia entre un semáforo y un copiloto."

*[Timing check: ~3:45]*

---

## BLOQUE 4 — Validación (3:45–4:30)

*[Acción: minimizar el chat. Señalar en pantalla o abrir la
sección de métricas del artículo si el profesor lo pide]*

> "Antes de cerrar, los números de validación.
>
> Validamos el sistema contra 30 rutas reales de la ZMVM,
> comparando nuestra predicción con la de TomTom Routing como
> ground truth.
>
> Resultado: MAPE del P50 de 11.9%.
> TomTom Routing, el líder comercial, tiene 19% en las mismas rutas.
> Somos 7 puntos porcentuales más precisos.
>
> Y la cobertura empírica de la banda P10-P90: 93.3%.
> La banda nominal debería cubrir el 80%.
> Cubrimos más, lo que significa que el sistema es conservadoramente
> calibrado — preferible a ser optimista y mentir.
>
> 720 tests automatizados, todos en verde, verificables en el repo."

*[Timing check: ~4:30]*

---

## BLOQUE 5 — Cierre (4:30–5:00)

*[Pantalla: dejar la app visible, no cerrar]*

> "VialAI es un prototipo funcional, no un producto terminado.
> Pero demuestra que es posible construir un sistema de predicción
> probabilística de tiempos de viaje para la ZMVM, con incertidumbre
> cuantificada, que supera al líder comercial en precisión,
> con datos abiertos, y con una interfaz que un conductor puede
> usar mientras maneja.
>
> El siguiente paso es llevarlo a campo: 500 viajes etiquetados
> con conductores reales. El modelo ya está listo para aprender de ellos.
>
> Eso es todo. Quedo a sus órdenes para preguntas."

*[Timing: exactamente 5:00]*

---

## Plan de contingencia

| Problema | Acción inmediata |
|---|---|
| API TomTom no responde | La app usa el caché local. No se nota. Continuar. |
| API Anthropic falla | Mostrar la predicción manual (BLOQUE 1 y 2) sin chat. Decir: "El agente requiere conectividad; les muestro la predicción base que funciona offline." |
| La app no cargó | Abrir `docs/proyecto_ZMCDMX_v3.pdf` en la pantalla y narrar la demo usando las figuras del paper. |
| El profesor interrumpe con preguntas | Responder brevemente y retomar. No perder el hilo del timing. |

---

## Números clave para memorizar

| Dato | Valor |
|---|---|
| Trayectorias Monte Carlo | 10,000 |
| Registros históricos C5 | +1 millón |
| Perturbaciones en el catálogo | 11 |
| Tests automatizados | 720 |
| MAPE VialAI (P50) | 11.9% |
| MAPE TomTom Routing | 19.0% |
| Ventaja VialAI | +7.1 pp |
| Cobertura empírica P10-P90 | 93.3% |
| Latencia por consulta | < 500 ms |
| Conductores Tier 1 ZMVM | ~180,000 |
| Precio Tier 2 | $199 MXN/mes/conductor |
| Punto de equilibrio | 800 usuarios pagos |

---

## Diferencias clave respecto a `checklist_demo.md`

Este documento es el **guion de palabras** para practicar en voz alta.
`checklist_demo.md` es la **lista de verificación técnica** para la
preparación (qué hacer 30 minutos antes, qué tener abierto, qué
verificar). Ambos documentos son complementarios.
