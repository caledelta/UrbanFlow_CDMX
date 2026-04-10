"""Tests para el evaluador multi-ruta con Monte Carlo."""
import pytest
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════
# Mocks (no tocan la red ni el motor real)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MockRutaVial:
    distancia_km:        float
    tiempo_base_min:     int = 0
    waypoints:           list = field(default_factory=list)
    fuente:              str = "mock"
    es_alternativa:      bool = False
    indice_ruta:         int = 0


@dataclass
class MockResultadoMC:
    p10:   float
    p50:   float
    p90:   float
    media: float = 0.0
    std:   float = 0.0

    @property
    def banda_incertidumbre(self) -> float:
        return self.p90 - self.p10


class MockMotorMC:
    """Motor Monte Carlo que devuelve respuestas predefinidas en orden."""

    def __init__(self, resultados: list[MockResultadoMC]):
        self._resultados  = resultados
        self._call_count  = 0

    def correr(self, consulta) -> MockResultadoMC:
        r = self._resultados[self._call_count % len(self._resultados)]
        self._call_count += 1
        return r


# ═══════════════════════════════════════════════════════════════════════════
# Importación del módulo a testear
# ═══════════════════════════════════════════════════════════════════════════

from src.simulation.evaluador_rutas import (
    evaluar_rutas,
    generar_explicacion_cambio_ruta,
    ResultadoRuta,
)


# ═══════════════════════════════════════════════════════════════════════════
# Tests de evaluar_rutas
# ═══════════════════════════════════════════════════════════════════════════

class TestEvaluarRutas:

    def test_lista_vacia_devuelve_vacio(self):
        resultado = evaluar_rutas([], None, None, estado_inicial=0)
        assert resultado == []

    def test_ruta_unica_es_recomendada(self):
        rutas  = [MockRutaVial(distancia_km=15.0)]
        motor  = MockMotorMC([MockResultadoMC(p10=22, p50=28, p90=38)])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=0)
        assert len(result) == 1
        assert result[0].es_recomendada
        assert result[0].p50 == pytest.approx(28.0)

    def test_alternativa_mejor_que_principal(self):
        rutas = [
            MockRutaVial(distancia_km=15.0, indice_ruta=0),
            MockRutaVial(distancia_km=18.0, indice_ruta=1, es_alternativa=True),
        ]
        motor = MockMotorMC([
            MockResultadoMC(p10=35, p50=55, p90=80),   # Principal: lenta
            MockResultadoMC(p10=25, p50=35, p90=48),   # Alternativa: rápida
        ])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=1)
        assert result[0].indice == 1        # La alternativa queda primera
        assert result[0].es_recomendada
        assert not result[1].es_recomendada

    def test_tres_rutas_ordenadas_por_p50(self):
        rutas = [
            MockRutaVial(distancia_km=15.0, indice_ruta=0),
            MockRutaVial(distancia_km=18.0, indice_ruta=1, es_alternativa=True),
            MockRutaVial(distancia_km=20.0, indice_ruta=2, es_alternativa=True),
        ]
        motor = MockMotorMC([
            MockResultadoMC(p10=30, p50=50, p90=70),
            MockResultadoMC(p10=25, p50=35, p90=45),   # La más rápida
            MockResultadoMC(p10=28, p50=40, p90=55),
        ])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=0)
        assert result[0].p50 <= result[1].p50 <= result[2].p50
        assert result[0].es_recomendada

    def test_empate_p50_desempate_por_ic(self):
        rutas = [
            MockRutaVial(distancia_km=12.0, indice_ruta=0),
            MockRutaVial(distancia_km=12.0, indice_ruta=1, es_alternativa=True),
        ]
        # Mismo P50 pero la segunda tiene menor IC (más predecible)
        motor = MockMotorMC([
            MockResultadoMC(p10=20, p50=35, p90=60),  # IC = 40/35 ≈ 1.14
            MockResultadoMC(p10=28, p50=35, p90=44),  # IC = 16/35 ≈ 0.46
        ])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=0)
        assert result[0].ic < result[1].ic

    def test_semaforo_verde_para_ic_bajo(self):
        rutas  = [MockRutaVial(distancia_km=10.0)]
        motor  = MockMotorMC([MockResultadoMC(p10=18, p50=20, p90=24)])  # IC=0.30
        result = evaluar_rutas(rutas, motor, None, estado_inicial=0)
        assert result[0].semaforo == "verde"

    def test_semaforo_rojo_para_ic_alto(self):
        rutas  = [MockRutaVial(distancia_km=10.0)]
        motor  = MockMotorMC([MockResultadoMC(p10=10, p50=20, p90=50)])  # IC=2.0
        result = evaluar_rutas(rutas, motor, None, estado_inicial=0)
        assert result[0].semaforo == "rojo"

    def test_ratio_compromiso_calculado(self):
        rutas  = [MockRutaVial(distancia_km=17.5)]  # 17.5/35*60 = 30 min fluido
        motor  = MockMotorMC([MockResultadoMC(p10=28, p50=60, p90=80)])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=2)
        assert result[0].ratio_compromiso == pytest.approx(2.0, rel=0.01)

    def test_error_en_una_ruta_no_rompe_el_resto(self):
        """Si una ruta falla en el motor, las demás siguen procesándose."""

        class MotorConFallo:
            def __init__(self):
                self._llamadas = 0
            def correr(self, consulta):
                self._llamadas += 1
                if self._llamadas == 1:
                    raise RuntimeError("Error de prueba")
                return MockResultadoMC(p10=20, p50=30, p90=42)

        rutas = [
            MockRutaVial(distancia_km=12.0, indice_ruta=0),
            MockRutaVial(distancia_km=15.0, indice_ruta=1, es_alternativa=True),
        ]
        result = evaluar_rutas(rutas, MotorConFallo(), None, estado_inicial=0)
        assert len(result) == 1    # Solo la segunda ruta se procesó con éxito
        assert result[0].indice == 1

    def test_razon_recomendacion_ruta_principal(self):
        rutas = [
            MockRutaVial(distancia_km=12.0, indice_ruta=0),
            MockRutaVial(distancia_km=15.0, indice_ruta=1, es_alternativa=True),
        ]
        motor = MockMotorMC([
            MockResultadoMC(p10=20, p50=30, p90=42),
            MockResultadoMC(p10=25, p50=40, p90=55),
        ])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=0)
        assert "ruta principal" in result[0].razon_recomendacion.lower()

    def test_razon_recomendacion_alternativa(self):
        rutas = [
            MockRutaVial(distancia_km=12.0, indice_ruta=0),
            MockRutaVial(distancia_km=15.0, indice_ruta=1, es_alternativa=True),
        ]
        motor = MockMotorMC([
            MockResultadoMC(p10=35, p50=60, p90=85),   # Principal: lenta
            MockResultadoMC(p10=20, p50=30, p90=42),   # Alternativa: mejor
        ])
        result = evaluar_rutas(rutas, motor, None, estado_inicial=2)
        mejor = result[0]
        assert mejor.indice == 1
        assert "alternativa" in mejor.razon_recomendacion.lower() or \
               "Alternativa" in mejor.razon_recomendacion


# ═══════════════════════════════════════════════════════════════════════════
# Tests de generar_explicacion_cambio_ruta
# ═══════════════════════════════════════════════════════════════════════════

class TestExplicacionCambioRuta:

    def _rr(self, indice: int, nombre: str, dist: float, p50: float,
            ratio: float = 1.0) -> ResultadoRuta:
        return ResultadoRuta(
            indice=indice, nombre=nombre, distancia_km=dist,
            p10=round(p50 * 0.8, 1), p50=p50, p90=round(p50 * 1.3, 1),
            ic=0.5, semaforo="amarillo",
            ratio_compromiso=ratio,
        )

    def test_sin_cambio_devuelve_mensaje_positivo(self):
        r = self._rr(0, "Ruta principal", 15, 28)
        msg = generar_explicacion_cambio_ruta(r, r)
        assert "óptima" in msg.lower() or "sin cambios" in msg.lower()

    def test_con_cambio_menciona_nombre_alternativa(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35, ratio=1.0)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=2.1)
        msg = generar_explicacion_cambio_ruta(mejor, principal)
        assert "Alternativa 1" in msg

    def test_con_cambio_menciona_ahorro(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=2.1)
        msg = generar_explicacion_cambio_ruta(mejor, principal)
        assert "20" in msg or "Ahorro" in msg or "ahorro" in msg

    def test_incluye_motivo_congestion_severa(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=2.5)
        msg = generar_explicacion_cambio_ruta(mejor, principal)
        assert "congest" in msg.lower()

    def test_incluye_eventos_activos(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=1.5)
        eventos  = [{"descripcion": "Manifestación en Reforma"}]
        msg = generar_explicacion_cambio_ruta(mejor, principal, eventos_activos=eventos)
        assert "Manifestación" in msg or "manifestaci" in msg.lower()

    def test_incluye_ventana_de_llegada(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=1.5)
        msg = generar_explicacion_cambio_ruta(mejor, principal)
        assert "Ventana" in msg or "ventana" in msg or "llegada" in msg.lower()

    def test_clima_incluido_si_no_despejado(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=1.5)
        msg = generar_explicacion_cambio_ruta(
            mejor, principal, condicion_clima="Lluvia moderada"
        )
        assert "Lluvia" in msg or "lluvia" in msg

    def test_clima_despejado_no_incluido(self):
        mejor    = self._rr(1, "Alternativa 1", 18, 35)
        principal = self._rr(0, "Ruta principal", 15, 55, ratio=1.5)
        msg = generar_explicacion_cambio_ruta(
            mejor, principal, condicion_clima="despejado"
        )
        assert "despejado" not in msg
