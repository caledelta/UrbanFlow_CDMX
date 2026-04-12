"""
tests/test_recompensa.py — Tests unitarios para src/core/recompensa.py
"""

from __future__ import annotations

import pytest

from src.core.recompensa import (
    perfil_completo,
    get_company_config,
    sugerir_ventana_optima,
    generar_analisis,
    COMPANY_CONFIG,
)


# ─────────────────────────────────────────────────────────────────────────────
# perfil_completo
# ─────────────────────────────────────────────────────────────────────────────

class TestPerfilCompleto:
    def test_completo(self):
        assert perfil_completo({"tipo": "Uber", "genero": "M", "edad": 30}) is True

    def test_falta_tipo(self):
        assert perfil_completo({"genero": "M", "edad": 30}) is False

    def test_falta_genero(self):
        assert perfil_completo({"tipo": "Uber", "edad": 30}) is False

    def test_falta_edad(self):
        assert perfil_completo({"tipo": "Uber", "genero": "M"}) is False

    def test_vacio(self):
        assert perfil_completo({}) is False

    def test_tipo_vacio_string(self):
        assert perfil_completo({"tipo": "", "genero": "M", "edad": 30}) is False

    def test_none_values(self):
        assert perfil_completo({"tipo": None, "genero": "M", "edad": 30}) is False


# ─────────────────────────────────────────────────────────────────────────────
# get_company_config
# ─────────────────────────────────────────────────────────────────────────────

class TestGetCompanyConfig:
    def test_uber_eats(self):
        cfg = get_company_config("Uber Eats")
        assert cfg is not None
        assert cfg["emoji"] == "🟢"
        assert "color" in cfg
        assert "tip" in cfg

    def test_empresa_desconocida_retorna_none(self):
        assert get_company_config("EmpresaFantasma") is None

    def test_particular(self):
        cfg = get_company_config("Particular")
        assert cfg is not None
        assert "Hoy No Circula" in cfg["tip"]

    def test_todas_las_empresas_tienen_campos(self):
        for nombre, cfg in COMPANY_CONFIG.items():
            assert "emoji" in cfg,  f"{nombre}: falta emoji"
            assert "color" in cfg,  f"{nombre}: falta color"
            assert "bg"    in cfg,  f"{nombre}: falta bg"
            assert "tip"   in cfg,  f"{nombre}: falta tip"


# ─────────────────────────────────────────────────────────────────────────────
# sugerir_ventana_optima
# ─────────────────────────────────────────────────────────────────────────────

class TestSugerirVentanaOptima:
    def test_hora_pico_manana(self):
        result = sugerir_ventana_optima(8)
        assert "pico" in result["estado"].lower() or "⚠️" in result["estado"]
        assert "8" in result["consejo"] or "08" in result["consejo"]

    def test_hora_pico_tarde(self):
        result = sugerir_ventana_optima(18)
        assert "⚠️" in result["estado"]

    def test_hora_favorable(self):
        result = sugerir_ventana_optima(15)
        assert "✅" in result["estado"]

    def test_sin_hora(self):
        result = sugerir_ventana_optima(None)
        assert "estado" in result
        assert "mejor" in result
        assert "peor" in result

    def test_hora_fuera_de_rango(self):
        # hora 12 no es pico ni valle definido → devuelve genérico
        result = sugerir_ventana_optima(12)
        assert "estado" in result
        assert "mejor" in result

    def test_claves_presentes(self):
        for h in [6, 7, 8, 14, 17, 21, None]:
            r = sugerir_ventana_optima(h)
            assert all(k in r for k in ("estado", "consejo", "mejor", "peor")), \
                f"Faltan claves para hora={h}"


# ─────────────────────────────────────────────────────────────────────────────
# generar_analisis
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerarAnalisis:
    def _perfil(self, tipo="Uber Eats", genero="M", edad=28):
        return {"tipo": tipo, "genero": genero, "edad": edad}

    def _stats(self, rutas=None, n=5):
        return {
            "total_consultas": n,
            "rutas_unicas": len(rutas) if rutas else 0,
            "top_5_rutas": rutas or [],
        }

    def test_estructura_resultado(self):
        resultado = generar_analisis(self._perfil(), self._stats(), [])
        assert "tipo" in resultado
        assert "company" in resultado
        assert "ruta_principal" in resultado
        assert "total_consultas" in resultado
        assert "avg_real_min" in resultado
        assert "n_viajes_reales" in resultado
        assert "ventana" in resultado
        assert "tip" in resultado

    def test_company_config_incluido(self):
        resultado = generar_analisis(self._perfil("Uber Eats"), self._stats(), [])
        assert resultado["company"] is not None
        assert resultado["company"]["emoji"] == "🟢"

    def test_empresa_desconocida_usa_tip_generico(self):
        resultado = generar_analisis(self._perfil("EmpresaX"), self._stats(), [])
        assert resultado["company"] is None
        assert "VialAI" in resultado["tip"]

    def test_ruta_principal_top1(self):
        stats = self._stats(rutas=[("Polanco → AICM", 5), ("Roma → Satélite", 2)])
        resultado = generar_analisis(self._perfil(), stats, [])
        assert resultado["ruta_principal"] == ("Polanco → AICM", 5)

    def test_ruta_principal_none_si_sin_rutas(self):
        resultado = generar_analisis(self._perfil(), self._stats(), [])
        assert resultado["ruta_principal"] is None

    def test_avg_real_min_calculado(self):
        fb = [{"real_min": 10}, {"real_min": 20}, {"real_min": 15}]
        resultado = generar_analisis(self._perfil(), self._stats(), fb)
        assert resultado["avg_real_min"] == 15.0
        assert resultado["n_viajes_reales"] == 3

    def test_avg_real_min_none_si_sin_feedback(self):
        resultado = generar_analisis(self._perfil(), self._stats(), [])
        assert resultado["avg_real_min"] is None
        assert resultado["n_viajes_reales"] == 0

    def test_ignora_feedback_sin_real_min(self):
        fb = [{"real_min": 10}, {"comentario": "tarde"}, {"real_min": None}]
        resultado = generar_analisis(self._perfil(), self._stats(), fb)
        assert resultado["n_viajes_reales"] == 1

    def test_ventana_incluida(self):
        resultado = generar_analisis(self._perfil(), self._stats(), [], hora_habitual=8)
        assert "estado" in resultado["ventana"]

    def test_no_lanza_excepcion_perfil_vacio(self):
        resultado = generar_analisis({}, {}, [])
        assert resultado is not None
        assert resultado["company"] is None
