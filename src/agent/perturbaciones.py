"""
src/agent/perturbaciones.py — Utilidades de combinación de perturbaciones.

El catálogo de 11 perturbaciones estáticas y la función seleccionar_perturbacion
viven en src/agent/tools.py. Este módulo agrega la capa de merge entre
el catálogo estático y los factores dinámicos detectados en cuasi-tiempo-real.
"""
from __future__ import annotations


def merge_perturbaciones(
    factor_estatico: float,
    factor_dinamico: float,
) -> float:
    """
    Combina el factor de una perturbación estática (catálogo de 11 eventos)
    con el factor dinámico (eventos detectados en cuasi-tiempo-real).

    Usa el máximo de ambos para evitar doble conteo cuando un evento
    del catálogo ya está activo y también se detecta dinámicamente.

    Args:
        factor_estatico: Factor f del catálogo (e.g., 1.25 para Línea 1 Metro).
        factor_dinamico: Factor f de eventos detectados.

    Returns:
        Factor f combinado = max(f_estatico, f_dinamico).
    """
    return max(factor_estatico, factor_dinamico)
