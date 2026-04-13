"""
iconos_mapa.py — Mapeo de nombres/descripciones de lugares
guardados a iconos contextuales para marcadores del mapa Folium.
Case-insensitive, acepta coincidencias parciales.
"""
from typing import Dict

# Cada tupla: (keywords, folium_icon, folium_color, emoji)
ICONOS = [
    (("casa", "hogar", "home"), "home", "green", "🏠"),
    (("trabajo", "oficina", "office", "chamba"), "briefcase", "blue", "💼"),
    (("escuela", "universidad", "unam", "ipn", "tec", "colegio", "prepa", "fes"),
        "graduation-cap", "purple", "🎓"),
    (("gym", "gimnasio", "crossfit", "sport city"),
        "dumbbell", "darkred", "🏋️"),
    (("hospital", "clínica", "clinica", "imss", "issste"),
        "hospital", "red", "🏥"),
    (("aeropuerto", "aicm", "aifa", "terminal"),
        "plane", "darkblue", "✈️"),
    (("iglesia", "catedral", "parroquia", "templo"),
        "place-of-worship", "gray", "⛪"),
    (("metro", "estación", "estacion"),
        "train", "orange", "🚇"),
    (("restaurante", "restaurant", "comida", "taquería", "taqueria"),
        "utensils", "orange", "🍽️"),
    (("banco", "bbva", "santander", "banamex", "hsbc", "scotia"),
        "landmark", "cadetblue", "🏦"),
    (("super", "súper", "walmart", "chedraui", "soriana", "bodega"),
        "shopping-cart", "lightgreen", "🛒"),
    (("centro comercial", "plaza", "mall", "antara", "perisur", "santa fe"),
        "shopping-bag", "pink", "🏬"),
    (("parque", "bosque", "chapultepec"),
        "tree", "green", "🌳"),
    (("farmacia",), "briefcase-medical", "red", "💊"),
    (("café", "cafe", "starbucks", "cielito"),
        "coffee", "beige", "☕"),
]

ICONO_DEFAULT = ("map-marker", "yellow", "📍")


def icono_para_lugar(nombre: str, direccion: str = "") -> Dict[str, str]:
    """
    Retorna {'folium_icon', 'folium_color', 'emoji'} según keywords
    encontradas en nombre + dirección. Default: punto amarillo.
    """
    texto = f"{nombre or ''} {direccion or ''}".lower()
    for keywords, folium_icon, color, emoji in ICONOS:
        if any(kw in texto for kw in keywords):
            return {
                "folium_icon": folium_icon,
                "folium_color": color,
                "emoji": emoji,
            }
    return {
        "folium_icon": ICONO_DEFAULT[0],
        "folium_color": ICONO_DEFAULT[1],
        "emoji": ICONO_DEFAULT[2],
    }