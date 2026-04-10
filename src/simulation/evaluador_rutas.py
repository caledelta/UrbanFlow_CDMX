"""
src/simulation/evaluador_rutas.py — Evaluador multi-ruta con Monte Carlo.

Corre el motor Monte Carlo sobre múltiples rutas alternativas y las rankea
por P50 e IC (índice de confiabilidad = banda P10-P90 / P50) para seleccionar
la ruta óptima.

Este módulo NO modifica el motor Monte Carlo. Lo invoca N veces (una por ruta)
y compara los resultados. Si falla alguna ruta, se omite sin romper el flujo.

Uso rápido
----------
>>> from src.simulation.evaluador_rutas import evaluar_rutas
>>> resultados = evaluar_rutas(rutas_viales, motor_mc, cadena, estado_inicial=0)
>>> mejor = resultados[0]          # ya ordenada: primero la recomendada
>>> print(mejor.nombre, mejor.p50)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

VELOCIDAD_FLUJO_LIBRE_DEFAULT: float = 35.0   # km/h referencia ZMVM


# ═══════════════════════════════════════════════════════════════════════════
# Estructuras de datos
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ResultadoRuta:
    """
    Resultado de simulación Monte Carlo para una ruta específica.

    Atributos
    ---------
    indice : int
        Posición de la ruta en la respuesta del router (0 = principal).
    nombre : str
        Etiqueta legible: "Ruta principal", "Alternativa 1", etc.
    distancia_km : float
        Distancia real de esta ruta en kilómetros.
    p10, p50, p90 : float
        Percentiles de la distribución de tiempos simulados (minutos).
    ic : float
        Índice de confiabilidad = (p90 − p10) / p50.  0 = perfectamente
        predecible; mayor = más incertidumbre.
    semaforo : str
        ``"verde"`` (IC ≤ 0.30), ``"amarillo"`` (IC ≤ 0.60), ``"rojo"``.
    es_recomendada : bool
        ``True`` si esta ruta es la seleccionada como óptima.
    razon_recomendacion : str
        Texto explicando por qué se recomienda (o no) esta ruta.
    waypoints : list
        Geometría de la ruta (lista de tuplas (lat, lon)).
    tiempo_fluido_min : float
        Tiempo estimado en condiciones de flujo libre.
    ratio_compromiso : float
        p50 / tiempo_fluido_min.  > 1.8 indica ruta muy comprometida.
    """
    indice:               int
    nombre:               str
    distancia_km:         float
    p10:                  float
    p50:                  float
    p90:                  float
    ic:                   float
    semaforo:             str
    es_recomendada:       bool = False
    razon_recomendacion:  str = ""
    waypoints:            list = field(default_factory=list)
    tiempo_fluido_min:    float = 0.0
    ratio_compromiso:     float = 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Función principal
# ═══════════════════════════════════════════════════════════════════════════

def evaluar_rutas(
    rutas_viales: list,
    motor_mc: Any,
    cadena_markov: Any,        # No se usa directamente; el motor ya está configurado
    estado_inicial: int,
    velocidad_flujo_libre: float = VELOCIDAD_FLUJO_LIBRE_DEFAULT,
) -> list[ResultadoRuta]:
    """
    Evalúa múltiples rutas con Monte Carlo y las rankea por P50 e IC.

    El motor Monte Carlo debe estar ya configurado con los parámetros de
    velocidad y vehículo correctos.  Esta función solo llama a
    ``motor_mc.correr(ConsultaViaje(...))`` por cada ruta.

    Parámetros
    ----------
    rutas_viales : list[RutaVial]
        Lista de rutas del router externo (TomTom o fallback Haversine).
    motor_mc : MonteCarloEngine
        Motor ya instanciado con ``cadena``, ``velocidad_params`` y ``rng``.
    cadena_markov : MarkovTrafficChain
        No se usa (el motor ya la contiene). Se acepta para compatibilidad
        con la firma esperada por los tests con mocks.
    estado_inicial : int
        Estado de tráfico inicial (0=Fluido, 1=Lento, 2=Congestionado).
    velocidad_flujo_libre : float
        Velocidad de referencia en flujo libre (km/h). Default: 35.0.

    Devuelve
    --------
    list[ResultadoRuta]
        Lista ordenada por P50 ascendente (el índice 0 es la recomendada).
        Lista vacía si ninguna ruta se pudo simular.
    """
    from src.simulation.monte_carlo import ConsultaViaje  # import tardío para evitar ciclos

    resultados: list[ResultadoRuta] = []

    for i, ruta in enumerate(rutas_viales):
        nombre = "Ruta principal" if i == 0 else f"Alternativa {i}"
        try:
            consulta    = ConsultaViaje(
                distancia_km  = ruta.distancia_km,
                estado_inicial = estado_inicial,
            )
            resultado_mc = motor_mc.correr(consulta)

            tiempo_fluido = (ruta.distancia_km / velocidad_flujo_libre) * 60
            ratio = resultado_mc.p50 / tiempo_fluido if tiempo_fluido > 0 else 1.0
            ic    = resultado_mc.banda_incertidumbre / resultado_mc.p50 \
                    if resultado_mc.p50 > 0 else 0.0

            if ic <= 0.30:
                semaforo = "verde"
            elif ic <= 0.60:
                semaforo = "amarillo"
            else:
                semaforo = "rojo"

            resultados.append(ResultadoRuta(
                indice            = i,
                nombre            = nombre,
                distancia_km      = ruta.distancia_km,
                p10               = round(resultado_mc.p10, 1),
                p50               = round(resultado_mc.p50, 1),
                p90               = round(resultado_mc.p90, 1),
                ic                = round(ic, 3),
                semaforo          = semaforo,
                waypoints         = list(getattr(ruta, "waypoints", [])),
                tiempo_fluido_min = round(tiempo_fluido, 1),
                ratio_compromiso  = round(ratio, 2),
            ))

        except Exception as exc:
            logger.warning("Error evaluando %s: %s", nombre, exc)
            continue

    if not resultados:
        return []

    # ── Rankear: menor P50 primero; desempate por menor IC ──────────────────
    resultados.sort(key=lambda r: (r.p50, r.ic))

    mejor = resultados[0]
    mejor.es_recomendada = True
    mejor.razon_recomendacion = _generar_razon(mejor, resultados)

    return resultados


# ═══════════════════════════════════════════════════════════════════════════
# Explicación en lenguaje natural
# ═══════════════════════════════════════════════════════════════════════════

def generar_explicacion_cambio_ruta(
    recomendada: ResultadoRuta,
    principal: ResultadoRuta,
    eventos_activos: list | None = None,
    condicion_clima: str = "",
) -> str:
    """
    Genera un mensaje en español explicando por qué se recomienda
    una ruta diferente a la principal.

    Parámetros
    ----------
    recomendada : ResultadoRuta
        La ruta seleccionada como óptima.
    principal : ResultadoRuta
        La ruta principal (índice 0) para comparación.
    eventos_activos : list, opcional
        Lista de eventos detectados (dicts o strings).
    condicion_clima : str
        Descripción breve de la condición climática.

    Devuelve
    --------
    str
        Mensaje multi-línea listo para mostrar o enviar.
    """
    if recomendada.indice == 0:
        return "✅ La ruta principal es la óptima. Sin cambios necesarios."

    partes: list[str] = []
    partes.append(
        f"📍 Se recomienda tomar {recomendada.nombre} "
        f"({recomendada.distancia_km:.1f} km) en lugar de la ruta habitual "
        f"({principal.distancia_km:.1f} km)."
    )

    ahorro = principal.p50 - recomendada.p50
    partes.append(
        f"⏱️ Ahorro estimado: {ahorro:.0f} minutos "
        f"(~{recomendada.p50:.0f} min vs {principal.p50:.0f} min en P50)."
    )

    razones: list[str] = []
    if principal.ratio_compromiso > 1.8:
        razones.append("congestión severa en el corredor principal")
    elif principal.ratio_compromiso > 1.3:
        razones.append("tráfico lento en el corredor principal")
    for ev in (eventos_activos or [])[:2]:
        desc = ev.get("descripcion", ev) if isinstance(ev, dict) else str(ev)
        razones.append(str(desc))
    if condicion_clima and condicion_clima.lower() not in ("despejado", "clear", ""):
        razones.append(f"condiciones climáticas: {condicion_clima}")

    if razones:
        partes.append(f"📋 Motivo: {'; '.join(razones)}.")

    partes.append(
        f"🕐 Ventana de llegada: entre {recomendada.p10:.0f} "
        f"y {recomendada.p90:.0f} minutos."
    )

    return "\n".join(partes)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers privados
# ═══════════════════════════════════════════════════════════════════════════

def _generar_razon(mejor: ResultadoRuta, todos: list[ResultadoRuta]) -> str:
    """Genera la razón de recomendación para la ruta seleccionada."""
    if len(todos) == 1:
        return "Ruta única disponible."

    if mejor.indice == 0:
        segunda = todos[1]
        ahorro = segunda.p50 - mejor.p50
        return (
            f"La ruta principal es la más rápida "
            f"({ahorro:.0f} min menos que la alternativa más cercana)."
        )

    # Una alternativa es mejor
    principal = next((r for r in todos if r.indice == 0), None)
    if principal:
        ahorro = principal.p50 - mejor.p50
        return (
            f"⚠️ Se recomienda {mejor.nombre} en lugar de la ruta principal. "
            f"Ahorro estimado: {ahorro:.0f} min (P50). "
            f"La ruta principal está comprometida "
            f"(ratio {principal.ratio_compromiso:.1f}× flujo libre)."
        )
    return f"{mejor.nombre} tiene el menor tiempo estimado."
