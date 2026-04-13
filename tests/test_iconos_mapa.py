from src.core.iconos_mapa import icono_para_lugar


def test_icono_casa():
    r = icono_para_lugar("Casa de mi abuela", "Coyoacán")
    assert r["emoji"] == "🏠"
    assert r["folium_icon"] == "home"


def test_icono_trabajo():
    r = icono_para_lugar("Mi oficina", "Reforma 222")
    assert r["emoji"] == "💼"


def test_icono_aeropuerto():
    r = icono_para_lugar("AICM", "Terminal 2")
    assert r["emoji"] == "✈️"


def test_icono_default():
    r = icono_para_lugar("Lugar raro XYZ", "")
    assert r["emoji"] == "📍"
    assert r["folium_color"] == "yellow"


def test_case_insensitive():
    r = icono_para_lugar("CASA", "")
    assert r["emoji"] == "🏠"


def test_nombre_vacio_no_crashea():
    r = icono_para_lugar("", "")
    assert r["emoji"] == "📍"


def test_keyword_en_direccion_tambien_matchea():
    r = icono_para_lugar("Sucursal", "Hospital General")
    assert r["emoji"] == "🏥"