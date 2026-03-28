"""
Tests para src/models/schemas.py — Fase 1 Structured Outputs.

Cubre: RespuestaTomTom, RespuestaClima, PrediccionViaje, PerturbacionActiva.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.schemas import (
    RespuestaTomTom,
    RespuestaClima,
    PrediccionViaje,
    PerturbacionActiva,
    NIVEL_INTERNO_A_COLOR,
)


# ──────────────────────────────────────────────────────────────────────
# RespuestaTomTom
# ──────────────────────────────────────────────────────────────────────

class TestRespuestaTomTom:

    def _valido(self, **kwargs) -> dict:
        base = {
            "velocidad_actual_kmh": 35.0,
            "velocidad_libre_kmh": 60.0,
            "confianza": 0.92,
            "ratio_flujo": 0.583,
        }
        base.update(kwargs)
        return base

    def test_construccion_valida(self):
        r = RespuestaTomTom(**self._valido())
        assert r.velocidad_actual_kmh == 35.0

    def test_todos_los_campos_presentes(self):
        r = RespuestaTomTom(**self._valido())
        assert hasattr(r, "velocidad_actual_kmh")
        assert hasattr(r, "velocidad_libre_kmh")
        assert hasattr(r, "confianza")
        assert hasattr(r, "ratio_flujo")

    def test_velocidad_actual_cero_valida(self):
        r = RespuestaTomTom(**self._valido(velocidad_actual_kmh=0.0))
        assert r.velocidad_actual_kmh == 0.0

    def test_velocidad_libre_maxima(self):
        r = RespuestaTomTom(**self._valido(velocidad_libre_kmh=300.0))
        assert r.velocidad_libre_kmh == 300.0

    def test_confianza_uno(self):
        r = RespuestaTomTom(**self._valido(confianza=1.0))
        assert r.confianza == 1.0

    def test_confianza_cero(self):
        r = RespuestaTomTom(**self._valido(confianza=0.0))
        assert r.confianza == 0.0

    def test_ratio_flujo_limite_inferior(self):
        r = RespuestaTomTom(**self._valido(ratio_flujo=0.0))
        assert r.ratio_flujo == 0.0

    def test_ratio_flujo_limite_superior(self):
        r = RespuestaTomTom(**self._valido(ratio_flujo=1.0))
        assert r.ratio_flujo == 1.0

    def test_velocidad_negativa_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(**self._valido(velocidad_actual_kmh=-1.0))

    def test_velocidad_sobre_300_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(**self._valido(velocidad_libre_kmh=301.0))

    def test_confianza_negativa_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(**self._valido(confianza=-0.1))

    def test_confianza_mayor_a_uno_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(**self._valido(confianza=1.01))

    def test_ratio_negativo_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(**self._valido(ratio_flujo=-0.01))

    def test_ratio_mayor_a_uno_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(**self._valido(ratio_flujo=1.01))

    def test_campo_faltante_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaTomTom(velocidad_actual_kmh=35.0)

    def test_serializable_a_dict(self):
        r = RespuestaTomTom(**self._valido())
        d = r.model_dump()
        assert isinstance(d, dict)
        assert set(d.keys()) == {
            "velocidad_actual_kmh", "velocidad_libre_kmh",
            "confianza", "ratio_flujo",
        }


# ──────────────────────────────────────────────────────────────────────
# RespuestaClima
# ──────────────────────────────────────────────────────────────────────

class TestRespuestaClima:

    def _valido(self, **kwargs) -> dict:
        base = {
            "descripcion": "lluvia ligera",
            "lluvia_mm_h": 3.5,
            "visibilidad_km": 6.0,
            "factor_velocidad": 1.4,
            "nivel_alerta": "AMARILLA",
        }
        base.update(kwargs)
        return base

    def test_construccion_valida(self):
        r = RespuestaClima(**self._valido())
        assert r.nivel_alerta == "AMARILLA"

    def test_nivel_verde(self):
        r = RespuestaClima(**self._valido(nivel_alerta="VERDE", factor_velocidad=1.0))
        assert r.nivel_alerta == "VERDE"

    def test_nivel_naranja(self):
        r = RespuestaClima(**self._valido(nivel_alerta="NARANJA", factor_velocidad=1.7))
        assert r.nivel_alerta == "NARANJA"

    def test_nivel_roja(self):
        r = RespuestaClima(**self._valido(nivel_alerta="ROJA", factor_velocidad=2.0))
        assert r.nivel_alerta == "ROJA"

    def test_lluvia_cero_valida(self):
        r = RespuestaClima(**self._valido(lluvia_mm_h=0.0, nivel_alerta="VERDE", factor_velocidad=1.0))
        assert r.lluvia_mm_h == 0.0

    def test_factor_minimo_valido(self):
        r = RespuestaClima(**self._valido(factor_velocidad=1.0, nivel_alerta="VERDE"))
        assert r.factor_velocidad == 1.0

    def test_factor_maximo_valido(self):
        r = RespuestaClima(**self._valido(factor_velocidad=2.5, nivel_alerta="ROJA"))
        assert r.factor_velocidad == 2.5

    def test_nivel_invalido_lanza_error(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(nivel_alerta="AZUL"))

    def test_nivel_en_minusculas_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(nivel_alerta="verde"))

    def test_lluvia_negativa_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(lluvia_mm_h=-1.0))

    def test_visibilidad_negativa_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(visibilidad_km=-0.1))

    def test_visibilidad_sobre_100_invalida(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(visibilidad_km=100.1))

    def test_factor_menor_a_uno_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(factor_velocidad=0.9))

    def test_factor_mayor_a_25_invalido(self):
        with pytest.raises(ValidationError):
            RespuestaClima(**self._valido(factor_velocidad=2.51))

    def test_serializable_a_dict(self):
        r = RespuestaClima(**self._valido())
        d = r.model_dump()
        assert "nivel_alerta" in d
        assert "factor_velocidad" in d


# ──────────────────────────────────────────────────────────────────────
# PrediccionViaje
# ──────────────────────────────────────────────────────────────────────

class TestPrediccionViaje:

    def _valido(self, **kwargs) -> dict:
        base = {
            "origen": "Insurgentes Sur · Perisur",
            "destino": "Indios Verdes",
            "p10_min": 18.0,
            "p50_min": 25.0,
            "p90_min": 38.0,
            "nivel_alerta": "AMARILLA",
            "resumen": "Tráfico moderado en Insurgentes",
        }
        base.update(kwargs)
        return base

    def test_construccion_valida(self):
        p = PrediccionViaje(**self._valido())
        assert p.p50_min == 25.0

    def test_todos_los_campos_presentes(self):
        p = PrediccionViaje(**self._valido())
        assert p.origen
        assert p.destino
        assert p.resumen

    def test_percentiles_iguales_validos(self):
        """p10 = p50 = p90 es válido (caso determinista)."""
        p = PrediccionViaje(**self._valido(p10_min=20.0, p50_min=20.0, p90_min=20.0))
        assert p.p10_min == p.p50_min == p.p90_min

    def test_p10_mayor_p50_invalido(self):
        with pytest.raises(ValidationError, match="percentiles"):
            PrediccionViaje(**self._valido(p10_min=30.0, p50_min=25.0, p90_min=38.0))

    def test_p50_mayor_p90_invalido(self):
        with pytest.raises(ValidationError, match="percentiles"):
            PrediccionViaje(**self._valido(p10_min=18.0, p50_min=40.0, p90_min=35.0))

    def test_p10_negativo_invalido(self):
        with pytest.raises(ValidationError):
            PrediccionViaje(**self._valido(p10_min=-1.0))

    def test_nivel_invalido_lanza_error(self):
        with pytest.raises(ValidationError):
            PrediccionViaje(**self._valido(nivel_alerta="MORADO"))

    @pytest.mark.parametrize("nivel", ["VERDE", "AMARILLA", "NARANJA", "ROJA"])
    def test_todos_los_niveles_validos(self, nivel):
        p = PrediccionViaje(**self._valido(nivel_alerta=nivel))
        assert p.nivel_alerta == nivel

    def test_serializable_a_dict(self):
        p = PrediccionViaje(**self._valido())
        d = p.model_dump()
        assert set(d.keys()) == {
            "origen", "destino",
            "p10_min", "p50_min", "p90_min",
            "nivel_alerta", "resumen",
        }


# ──────────────────────────────────────────────────────────────────────
# PerturbacionActiva
# ──────────────────────────────────────────────────────────────────────

class TestPerturbacionActiva:

    def _valido(self, **kwargs) -> dict:
        base = {
            "tipo": "marcha",
            "descripcion": "9 de marzo — marcha feminista",
            "factor": 1.70,
            "alcaldias": ["Cuauhtémoc", "Miguel Hidalgo"],
            "horas": (16, 22),
        }
        base.update(kwargs)
        return base

    def test_construccion_valida(self):
        p = PerturbacionActiva(**self._valido())
        assert p.factor == pytest.approx(1.70)

    def test_alcaldias_vacia_valida(self):
        """Lista vacía = afecta toda la ZMVM."""
        p = PerturbacionActiva(**self._valido(alcaldias=[]))
        assert p.alcaldias == []

    def test_factor_minimo_valido(self):
        p = PerturbacionActiva(**self._valido(factor=0.1))
        assert p.factor == pytest.approx(0.1)

    def test_factor_maximo_valido(self):
        p = PerturbacionActiva(**self._valido(factor=5.0))
        assert p.factor == pytest.approx(5.0)

    def test_factor_temporada_baja(self):
        """Valores < 1 son válidos (reducen congestión)."""
        p = PerturbacionActiva(**self._valido(factor=0.6))
        assert p.factor == pytest.approx(0.6)

    def test_horas_inicio_iguales_validas(self):
        p = PerturbacionActiva(**self._valido(horas=(10, 10)))
        assert p.horas == (10, 10)

    def test_horas_medianoche_validas(self):
        p = PerturbacionActiva(**self._valido(horas=(0, 23)))
        assert p.horas[0] == 0
        assert p.horas[1] == 23

    def test_factor_menor_a_minimo_invalido(self):
        with pytest.raises(ValidationError):
            PerturbacionActiva(**self._valido(factor=0.09))

    def test_factor_mayor_a_maximo_invalido(self):
        with pytest.raises(ValidationError):
            PerturbacionActiva(**self._valido(factor=5.01))

    def test_hora_inicio_negativa_invalida(self):
        with pytest.raises(ValidationError, match="hora_inicio"):
            PerturbacionActiva(**self._valido(horas=(-1, 22)))

    def test_hora_fin_mayor_23_invalida(self):
        with pytest.raises(ValidationError, match="hora_fin"):
            PerturbacionActiva(**self._valido(horas=(0, 24)))

    def test_inicio_mayor_que_fin_invalido(self):
        with pytest.raises(ValidationError, match="hora_inicio"):
            PerturbacionActiva(**self._valido(horas=(20, 15)))

    def test_serializable_a_dict(self):
        p = PerturbacionActiva(**self._valido())
        d = p.model_dump()
        assert "factor" in d
        assert "alcaldias" in d
        assert "horas" in d


# ──────────────────────────────────────────────────────────────────────
# NIVEL_INTERNO_A_COLOR — mapeo de niveles internos a semáforo
# ──────────────────────────────────────────────────────────────────────

class TestNivelInternoAColor:

    def test_normal_es_verde(self):
        assert NIVEL_INTERNO_A_COLOR["normal"] == "VERDE"

    def test_moderado_es_amarilla(self):
        assert NIVEL_INTERNO_A_COLOR["moderado"] == "AMARILLA"

    def test_severo_es_naranja(self):
        assert NIVEL_INTERNO_A_COLOR["severo"] == "NARANJA"

    def test_extremo_es_roja(self):
        assert NIVEL_INTERNO_A_COLOR["extremo"] == "ROJA"

    def test_todos_los_niveles_mapeados(self):
        assert set(NIVEL_INTERNO_A_COLOR.keys()) == {
            "normal", "moderado", "severo", "extremo"
        }

    def test_todos_los_colores_son_literales_validos(self):
        colores_validos = {"VERDE", "AMARILLA", "NARANJA", "ROJA"}
        assert set(NIVEL_INTERNO_A_COLOR.values()) == colores_validos
