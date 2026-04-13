"""
src/core/rutas_personalizadas.py — Gestión de rutas personalizadas del usuario.

Permite guardar, listar, eliminar y cargar puntos (origen/destino) con nombre,
persistidos en session_state de Streamlit o como lista en memoria.

Esquema de un punto:
    {"lat": float, "lon": float, "nombre": str}

Uso rápido
----------
>>> from src.core.rutas_personalizadas import (
...     agregar_ruta, listar_rutas, eliminar_ruta, cargar_ruta
... )
>>> agregar_ruta("Casa", 19.4326, -99.1332, store=[])
>>> listar_rutas(store=[...])
"""

from __future__ import annotations

from typing import TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# Tipos
# ─────────────────────────────────────────────────────────────────────────────

class PuntoRuta(TypedDict, total=False):
    lat: float
    lon: float
    nombre: str
    direccion: str
    tipo: str  # "origen" | "destino" | "ambos"


# ─────────────────────────────────────────────────────────────────────────────
# Funciones CRUD
# ─────────────────────────────────────────────────────────────────────────────

def agregar_ruta(
    nombre: str,
    lat: float,
    lon: float,
    store: list[PuntoRuta],
    direccion: str = "",
    tipo: str = "ambos",
) -> PuntoRuta:
    """
    Agrega un punto con nombre a la lista ``store`` y lo devuelve.
    Si ya existe un punto con el mismo nombre (case-insensitive), lo sobreescribe.

    Parámetros
    ----------
    nombre : str
        Etiqueta legible para el punto (e.g. "Casa", "Trabajo").
    lat : float
        Latitud en grados decimales (WGS84).
    lon : float
        Longitud en grados decimales (WGS84).
    store : list
        Lista mutable donde se almacena el punto (normalmente
        ``st.session_state.rutas_guardadas``).
    direccion : str, opcional
        Dirección o referencia textual. Default cadena vacía.
    tipo : str, opcional
        Clasificación de uso del lugar: ``"origen"``, ``"destino"`` o
        ``"ambos"``. Default ``"ambos"``.

    Devuelve
    --------
    PuntoRuta
        El punto creado/actualizado.

    Lanza
    -----
    ValueError
        Si ``tipo`` no es uno de los valores válidos.
    """
    tipo_norm = tipo.lower().strip()
    if tipo_norm not in ("origen", "destino", "ambos"):
        raise ValueError(
            f"Tipo inválido: {tipo!r}. Usa 'origen', 'destino' o 'ambos'."
        )
    punto: PuntoRuta = {
        "lat": lat,
        "lon": lon,
        "nombre": nombre.strip(),
        "direccion": (direccion or "").strip(),
        "tipo": tipo_norm,
    }
    for i, p in enumerate(store):
        if p["nombre"].lower() == nombre.strip().lower():
            store[i] = punto
            return punto
    store.append(punto)
    return punto


def listar_rutas(store: list[PuntoRuta]) -> list[PuntoRuta]:
    """
    Devuelve una copia de todos los puntos guardados.

    Parámetros
    ----------
    store : list
        Lista fuente (normalmente ``st.session_state.rutas_guardadas``).

    Devuelve
    --------
    list[PuntoRuta]
        Lista con todos los puntos.
    """
    return list(store)


def eliminar_ruta(nombre: str, store: list[PuntoRuta]) -> bool:
    """
    Elimina el primer punto cuyo nombre coincida (case-insensitive).

    Parámetros
    ----------
    nombre : str
        Nombre del punto a eliminar.
    store : list
        Lista mutable de puntos.

    Devuelve
    --------
    bool
        ``True`` si se encontró y eliminó, ``False`` si no existía.
    """
    nombre_lower = nombre.strip().lower()
    for i, p in enumerate(store):
        if p["nombre"].lower() == nombre_lower:
            store.pop(i)
            return True
    return False


def cargar_ruta(nombre: str, store: list[PuntoRuta]) -> PuntoRuta | None:
    """
    Busca y devuelve el punto con el nombre indicado.

    Parámetros
    ----------
    nombre : str
        Nombre del punto buscado (case-insensitive).
    store : list
        Lista de puntos donde buscar.

    Devuelve
    --------
    PuntoRuta | None
        El punto si existe, ``None`` si no se encontró.
    """
    nombre_lower = nombre.strip().lower()
    for p in store:
        if p["nombre"].lower() == nombre_lower:
            return p
    return None
