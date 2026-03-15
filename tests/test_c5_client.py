"""
Tests para src/ingestion/c5_client.py

Cubre: normalización, filtrado, densidad temporal, descubrimiento CKAN,
descarga, pipeline completo y manejo de errores.
Sin llamadas reales a Internet — todo mockeado o con datos en memoria.
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest
import requests

from src.ingestion.c5_client import (
    C5IncidentesClient,
    C5DescargaError,
    C5FormatoError,
    RecursoC5,
    ResumenPipeline,
    ZMVM_LAT_MIN, ZMVM_LAT_MAX,
    ZMVM_LON_MIN, ZMVM_LON_MAX,
    MAPEO_COLUMNAS,
    normalizar_dataframe,
    filtrar_zmvm,
    enriquecer_columnas_temporales,
    calcular_densidad_temporal,
    _inferir_año,
    _parsear_fecha,
    _limpiar_coordenada,
)


# ──────────────────────────────────────────────────────────────────────
# Helpers y datos de prueba
# ──────────────────────────────────────────────────────────────────────

def _df_crudo_minimo(n: int = 5) -> pd.DataFrame:
    """DataFrame con nombres de columna tal como los publica el C5."""
    return pd.DataFrame({
        "fecha_creacion":   ["15/03/2023 08:30:00"] * n,
        "incidente_c4":     ["Accidente-Choque sin lesionados"] * n,
        "alcaldia_inicio":  ["CUAUHTEMOC"] * n,
        "latitud":          [19.4326] * n,
        "longitud":         [-99.1332] * n,
    })


def _df_canonico(n: int = 5) -> pd.DataFrame:
    """DataFrame ya normalizado para tests que no dependen de normalizar_dataframe."""
    return pd.DataFrame({
        "fecha_hora":     pd.to_datetime(["2023-03-15 08:30:00"] * n),
        "tipo_incidente": ["ACCIDENTE-CHOQUE SIN LESIONADOS"] * n,
        "alcaldia":       ["CUAUHTEMOC"] * n,
        "latitud":        [19.4326] * n,
        "longitud":       [-99.1332] * n,
    })


def _df_con_horas_variadas(base_date: str = "2023-03-15") -> pd.DataFrame:
    """DataFrame con 24 horas diferentes para tests de densidad."""
    filas = []
    for hora in range(24):
        # Más incidentes en horas pico (7-9, 17-19)
        repeticiones = 10 if hora in (7, 8, 9, 17, 18, 19) else 2
        for _ in range(repeticiones):
            filas.append({
                "fecha_hora": pd.Timestamp(f"{base_date} {hora:02d}:00:00"),
                "hora": hora,
                "tipo_incidente": "CHOQUE",
                "alcaldia": "CUAUHTEMOC",
                "latitud": 19.4326,
                "longitud": -99.1332,
            })
    return pd.DataFrame(filas)


PAYLOAD_CKAN_OK = {
    "success": True,
    "result": {
        "resources": [
            {
                "name": "Incidentes Viales 2022",
                "url":  "https://datos.cdmx.gob.mx/dataset/.../incidentes-2022.csv",
                "format": "CSV",
            },
            {
                "name": "Incidentes Viales 2023",
                "url":  "https://datos.cdmx.gob.mx/dataset/.../incidentes-2023.csv",
                "format": "CSV",
            },
            {
                "name": "Mapa interactivo",
                "url":  "https://datos.cdmx.gob.mx/map",
                "format": "HTML",   # debe ignorarse
            },
        ]
    },
}


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _mock_session_ckan(ckan_payload: dict, csv_df: pd.DataFrame) -> MagicMock:
    """Sesión mock: primera llamada devuelve CKAN, el resto devuelven el CSV."""
    session = MagicMock(spec=requests.Session)

    ckan_resp = MagicMock(spec=requests.Response)
    ckan_resp.status_code = 200
    ckan_resp.json.return_value = ckan_payload
    ckan_resp.raise_for_status.return_value = None

    csv_resp = MagicMock(spec=requests.Response)
    csv_resp.status_code = 200
    csv_resp.content = _csv_bytes(csv_df)

    session.get.side_effect = [ckan_resp, csv_resp, csv_resp, csv_resp]
    return session


# ──────────────────────────────────────────────────────────────────────
# Tests de normalizar_dataframe
# ──────────────────────────────────────────────────────────────────────

class TestNormalizarDataframe:
    def test_renombra_columnas_canonicas(self):
        df = normalizar_dataframe(_df_crudo_minimo())
        assert "fecha_hora"     in df.columns
        assert "tipo_incidente" in df.columns
        assert "alcaldia"       in df.columns
        assert "latitud"        in df.columns
        assert "longitud"       in df.columns

    def test_no_quedan_columnas_originales_renombradas(self):
        df = normalizar_dataframe(_df_crudo_minimo())
        assert "fecha_creacion"  not in df.columns
        assert "incidente_c4"    not in df.columns
        assert "alcaldia_inicio" not in df.columns

    def test_fecha_es_datetime(self):
        df = normalizar_dataframe(_df_crudo_minimo())
        assert pd.api.types.is_datetime64_any_dtype(df["fecha_hora"])

    def test_latitud_es_float(self):
        df = normalizar_dataframe(_df_crudo_minimo())
        assert pd.api.types.is_float_dtype(df["latitud"])

    def test_tipo_incidente_mayusculas(self):
        df = normalizar_dataframe(_df_crudo_minimo())
        assert df["tipo_incidente"].str.isupper().all()

    def test_alcaldia_mayusculas(self):
        df = normalizar_dataframe(_df_crudo_minimo())
        assert df["alcaldia"].str.isupper().all()

    def test_descarta_filas_con_fecha_nula(self):
        crudo = _df_crudo_minimo(3)
        crudo.loc[1, "fecha_creacion"] = "fecha_invalida_xxx"
        df = normalizar_dataframe(crudo)
        assert len(df) == 2

    def test_descarta_filas_con_latitud_nula(self):
        crudo = _df_crudo_minimo(3)
        crudo.loc[0, "latitud"] = "no_es_numero"
        df = normalizar_dataframe(crudo)
        assert len(df) == 2

    def test_maneja_separador_decimal_coma(self):
        crudo = _df_crudo_minimo(2)
        crudo["latitud"]  = ["19,4326", "19,3600"]
        crudo["longitud"] = ["-99,1332", "-99,1800"]
        df = normalizar_dataframe(crudo)
        assert df["latitud"].iloc[0] == pytest.approx(19.4326, abs=1e-4)

    def test_columna_tipo_ausente_se_rellena_desconocido(self):
        crudo = _df_crudo_minimo()
        crudo = crudo.drop(columns=["incidente_c4"])
        df = normalizar_dataframe(crudo)
        assert (df["tipo_incidente"] == "DESCONOCIDO").all()

    def test_columnas_minimas_faltantes_lanza_error(self):
        crudo = pd.DataFrame({"otra_col": [1, 2, 3]})
        with pytest.raises(C5FormatoError, match="requeridas"):
            normalizar_dataframe(crudo)

    def test_detecta_columnas_case_insensitive(self):
        crudo = _df_crudo_minimo()
        crudo.columns = [c.upper() for c in crudo.columns]
        df = normalizar_dataframe(crudo)
        assert "fecha_hora" in df.columns

    def test_corrige_lat_lon_intercambiados(self):
        """Si lat y lon están intercambiados (lat negativa, lon positiva) los corrige."""
        crudo = _df_crudo_minimo(5)
        crudo["latitud"]  = [-99.1332] * 5  # valores invertidos
        crudo["longitud"] = [ 19.4326] * 5
        df = normalizar_dataframe(crudo)
        # Tras corrección lat debe ser positiva
        assert (df["latitud"] > 0).all()

    def test_acepta_formato_fecha_iso(self):
        crudo = _df_crudo_minimo(2)
        crudo["fecha_creacion"] = ["2023-03-15 08:30:00", "2023-04-20 12:00:00"]
        df = normalizar_dataframe(crudo)
        assert len(df) == 2

    def test_acepta_nombre_delegacion_inicio(self):
        crudo = _df_crudo_minimo()
        crudo = crudo.rename(columns={"alcaldia_inicio": "delegacion_inicio"})
        df = normalizar_dataframe(crudo)
        assert "alcaldia" in df.columns

    def test_resultado_no_tiene_index_roto(self):
        df = normalizar_dataframe(_df_crudo_minimo(10))
        assert list(df.index) == list(range(len(df)))


# ──────────────────────────────────────────────────────────────────────
# Tests de filtrar_zmvm
# ──────────────────────────────────────────────────────────────────────

class TestFiltrarZMVM:
    def test_conserva_registros_dentro(self):
        df = _df_canonico(5)
        resultado = filtrar_zmvm(df)
        assert len(resultado) == 5

    def test_descarta_registros_fuera(self):
        df = _df_canonico(4)
        df.loc[0, "latitud"]  =  20.5   # Norte de ZMVM
        df.loc[1, "longitud"] = -97.0   # Este de ZMVM
        resultado = filtrar_zmvm(df)
        assert len(resultado) == 2

    def test_descarta_todos_si_ninguno_en_zmvm(self):
        df = pd.DataFrame({
            "latitud":  [18.0, 21.0],
            "longitud": [-99.0, -99.0],
        })
        assert filtrar_zmvm(df).empty

    def test_conserva_en_borde_exacto_del_bbox(self):
        df = pd.DataFrame({
            "latitud":  [ZMVM_LAT_MIN, ZMVM_LAT_MAX],
            "longitud": [ZMVM_LON_MIN, ZMVM_LON_MAX],
        })
        assert len(filtrar_zmvm(df)) == 2

    def test_sin_columna_latitud_lanza_error(self):
        df = pd.DataFrame({"longitud": [-99.1332]})
        with pytest.raises(KeyError, match="latitud"):
            filtrar_zmvm(df)

    def test_sin_columna_longitud_lanza_error(self):
        df = pd.DataFrame({"latitud": [19.4326]})
        with pytest.raises(KeyError, match="longitud"):
            filtrar_zmvm(df)

    def test_index_reiniciado(self):
        df = _df_canonico(5)
        df.loc[2, "latitud"] = 25.0   # fuera
        resultado = filtrar_zmvm(df)
        assert list(resultado.index) == list(range(len(resultado)))


# ──────────────────────────────────────────────────────────────────────
# Tests de enriquecer_columnas_temporales
# ──────────────────────────────────────────────────────────────────────

class TestEnriquecerColumnasTemporales:
    def test_agrega_todas_las_columnas(self):
        df = _df_canonico()
        resultado = enriquecer_columnas_temporales(df)
        for col in ("año", "mes", "dia", "hora", "dia_semana"):
            assert col in resultado.columns

    def test_valores_año_correctos(self):
        df = _df_canonico()
        resultado = enriquecer_columnas_temporales(df)
        assert (resultado["año"] == 2023).all()

    def test_valores_mes_correctos(self):
        df = _df_canonico()
        resultado = enriquecer_columnas_temporales(df)
        assert (resultado["mes"] == 3).all()

    def test_valores_hora_correctos(self):
        df = _df_canonico()
        resultado = enriquecer_columnas_temporales(df)
        assert (resultado["hora"] == 8).all()

    def test_dia_semana_rango_valido(self):
        df = _df_canonico()
        resultado = enriquecer_columnas_temporales(df)
        assert resultado["dia_semana"].between(0, 6).all()

    def test_latitud_convertida_a_float32(self):
        df = _df_canonico()
        resultado = enriquecer_columnas_temporales(df)
        assert resultado["latitud"].dtype == "float32"

    def test_no_modifica_df_original(self):
        df = _df_canonico()
        cols_originales = list(df.columns)
        enriquecer_columnas_temporales(df)
        assert list(df.columns) == cols_originales

    def test_sin_columna_fecha_hora_lanza_error(self):
        df = pd.DataFrame({"hora": [8]})
        with pytest.raises(KeyError, match="fecha_hora"):
            enriquecer_columnas_temporales(df)


# ──────────────────────────────────────────────────────────────────────
# Tests de calcular_densidad_temporal
# ──────────────────────────────────────────────────────────────────────

class TestCalcularDensidadTemporal:
    @pytest.fixture
    def df_horas(self):
        return _df_con_horas_variadas()

    def test_devuelve_24_filas(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        assert len(resultado) == 24

    def test_indice_es_0_a_23(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        assert list(resultado.index) == list(range(24))

    def test_columnas_presentes(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        for col in ("incidentes_por_dia", "densidad_relativa",
                    "p_fluido", "p_lento", "p_congestionado", "estado_dominante"):
            assert col in resultado.columns

    def test_probabilidades_suman_uno(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        sumas = resultado[["p_fluido", "p_lento", "p_congestionado"]].sum(axis=1)
        for s in sumas:
            assert s == pytest.approx(1.0, abs=1e-10)

    def test_probabilidades_no_negativas(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        for col in ("p_fluido", "p_lento", "p_congestionado"):
            assert (resultado[col] >= 0).all()

    def test_densidad_relativa_entre_0_y_1(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        assert resultado["densidad_relativa"].between(0, 1).all()

    def test_densidad_maxima_es_1(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        assert resultado["densidad_relativa"].max() == pytest.approx(1.0)

    def test_hora_pico_tiene_mas_congestion(self, df_horas):
        """La hora 8 (pico) debe tener mayor p_congestionado que la 3 (valle)."""
        resultado = calcular_densidad_temporal(df_horas)
        assert resultado.at[8, "p_congestionado"] >= resultado.at[3, "p_congestionado"]

    def test_estado_dominante_es_string_valido(self, df_horas):
        resultado = calcular_densidad_temporal(df_horas)
        estados_validos = {"fluido", "lento", "congestionado"}
        assert set(resultado["estado_dominante"].unique()).issubset(estados_validos)

    def test_horas_valle_son_fluido(self, df_horas):
        """Las horas de madrugada (3, 4, 5) con pocos incidentes deben ser fluido."""
        resultado = calcular_densidad_temporal(df_horas)
        for hora in (3, 4, 5):
            assert resultado.at[hora, "estado_dominante"] == "fluido"

    def test_sin_columna_hora_lanza_error(self):
        df = pd.DataFrame({"fecha_hora": pd.to_datetime(["2023-01-01"])})
        with pytest.raises(KeyError, match="hora"):
            calcular_densidad_temporal(df)

    def test_sin_columna_fecha_hora_lanza_error(self):
        df = pd.DataFrame({"hora": [8, 9, 10]})
        with pytest.raises(KeyError, match="fecha_hora"):
            calcular_densidad_temporal(df)


# ──────────────────────────────────────────────────────────────────────
# Tests de descubrimiento CKAN
# ──────────────────────────────────────────────────────────────────────

class TestDescubrirRecursos:
    def test_devuelve_lista_de_recursos(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = PAYLOAD_CKAN_OK
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        cliente = C5IncidentesClient(tmp_path, session=session)
        recursos = cliente.descubrir_recursos()
        assert isinstance(recursos, list)

    def test_filtra_recursos_no_csv(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = PAYLOAD_CKAN_OK
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        cliente = C5IncidentesClient(tmp_path, session=session)
        recursos = cliente.descubrir_recursos()
        # Debe excluir el recurso HTML
        assert all(r.formato in ("CSV", "") for r in recursos)
        assert len(recursos) == 2

    def test_infiere_año_correcto(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = PAYLOAD_CKAN_OK
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        cliente = C5IncidentesClient(tmp_path, session=session)
        recursos = cliente.descubrir_recursos()
        años = {r.año for r in recursos if r.año}
        assert 2022 in años
        assert 2023 in años

    def test_error_red_lanza_c5_descarga_error(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        session.get.side_effect = requests.ConnectionError("sin red")
        cliente = C5IncidentesClient(tmp_path, session=session)
        with pytest.raises(C5DescargaError, match="CKAN"):
            cliente.descubrir_recursos()

    def test_ckan_success_false_lanza_error(self, tmp_path):
        session = MagicMock(spec=requests.Session)
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.json.return_value = {"success": False, "error": {"message": "not found"}}
        resp.raise_for_status.return_value = None
        session.get.return_value = resp

        cliente = C5IncidentesClient(tmp_path, session=session)
        with pytest.raises(C5DescargaError, match="success=False"):
            cliente.descubrir_recursos()


# ──────────────────────────────────────────────────────────────────────
# Tests de cargar_csv (local)
# ──────────────────────────────────────────────────────────────────────

class TestCargarCSV:
    def test_carga_csv_utf8(self, tmp_path):
        df_orig = _df_crudo_minimo(5)
        ruta = tmp_path / "test.csv"
        df_orig.to_csv(ruta, index=False, encoding="utf-8")
        cliente = C5IncidentesClient(tmp_path)
        df = cliente.cargar_csv(ruta)
        assert len(df) == 5

    def test_carga_csv_latin1(self, tmp_path):
        df_orig = _df_crudo_minimo(3)
        ruta = tmp_path / "test_latin.csv"
        df_orig.to_csv(ruta, index=False, encoding="latin-1")
        cliente = C5IncidentesClient(tmp_path)
        df = cliente.cargar_csv(ruta)
        assert len(df) == 3

    def test_archivo_inexistente_lanza_error(self, tmp_path):
        cliente = C5IncidentesClient(tmp_path)
        with pytest.raises(C5DescargaError, match="no encontrado"):
            cliente.cargar_csv(tmp_path / "no_existe.csv")


# ──────────────────────────────────────────────────────────────────────
# Tests del pipeline completo
# ──────────────────────────────────────────────────────────────────────

class TestEjecutarPipeline:
    def _cliente_con_mocks(
        self,
        tmp_path: Path,
        años: list[int],
        df_csv: pd.DataFrame,
    ) -> C5IncidentesClient:
        """Construye un cliente con CKAN y descarga mockeados."""
        # Construir payload CKAN con recursos para cada año solicitado
        recursos_ckan = [
            {
                "name": f"Incidentes {año}",
                "url":  f"https://fake.url/{año}.csv",
                "format": "CSV",
            }
            for año in años
        ]
        ckan_payload = {"success": True, "result": {"resources": recursos_ckan}}

        ckan_resp = MagicMock(spec=requests.Response)
        ckan_resp.status_code = 200
        ckan_resp.json.return_value = ckan_payload
        ckan_resp.raise_for_status.return_value = None

        csv_resp = MagicMock(spec=requests.Response)
        csv_resp.status_code = 200
        csv_resp.content = _csv_bytes(df_csv)

        session = MagicMock(spec=requests.Session)
        session.get.side_effect = [ckan_resp] + [csv_resp] * len(años)

        return C5IncidentesClient(tmp_path, años=años, session=session)

    def test_devuelve_resumen_pipeline(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(10))
        resumen = cliente.ejecutar_pipeline()
        assert isinstance(resumen, ResumenPipeline)

    def test_años_procesados_en_resumen(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022, 2023], _df_crudo_minimo(5))
        resumen = cliente.ejecutar_pipeline()
        assert 2022 in resumen.años_procesados
        assert 2023 in resumen.años_procesados

    def test_registros_crudos_contabilizados(self, tmp_path):
        n = 8
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(n))
        resumen = cliente.ejecutar_pipeline()
        assert resumen.registros_crudos == n

    def test_crea_archivo_parquet(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(10))
        resumen = cliente.ejecutar_pipeline()
        assert Path(resumen.ruta_parquet).exists()

    def test_parquet_legible_con_pandas(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(10))
        resumen = cliente.ejecutar_pipeline()
        df_leido = pd.read_parquet(resumen.ruta_parquet)
        assert len(df_leido) > 0

    def test_parquet_contiene_columnas_temporales(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(5))
        resumen = cliente.ejecutar_pipeline()
        df_leido = pd.read_parquet(resumen.ruta_parquet)
        for col in ("año", "mes", "hora", "dia_semana"):
            assert col in df_leido.columns

    def test_filtra_registros_fuera_de_zmvm(self, tmp_path):
        df_mix = _df_crudo_minimo(6)
        df_mix.loc[0, "latitud"] = 25.0   # fuera
        df_mix.loc[1, "longitud"] = -85.0  # fuera
        cliente = self._cliente_con_mocks(tmp_path, [2022], df_mix)
        resumen = cliente.ejecutar_pipeline()
        assert resumen.registros_descartados >= 2

    def test_tasa_retencion_rango(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(10))
        resumen = cliente.ejecutar_pipeline()
        assert 0.0 <= resumen.tasa_retencion <= 1.0

    def test_crea_directorio_raw(self, tmp_path):
        cliente = self._cliente_con_mocks(tmp_path, [2022], _df_crudo_minimo(5))
        cliente.ejecutar_pipeline()
        assert (tmp_path / "data" / "raw" / "c5").is_dir()

    def test_sin_recursos_ckan_lanza_error(self, tmp_path):
        ckan_resp = MagicMock(spec=requests.Response)
        ckan_resp.status_code = 200
        ckan_resp.json.return_value = {"success": True, "result": {"resources": []}}
        ckan_resp.raise_for_status.return_value = None
        session = MagicMock(spec=requests.Session)
        session.get.return_value = ckan_resp
        cliente = C5IncidentesClient(tmp_path, años=[2022], session=session)
        with pytest.raises(C5DescargaError):
            cliente.ejecutar_pipeline()

    def test_csv_cacheado_no_se_re_descarga(self, tmp_path):
        """Si el CSV ya existe, no debe hacerse la petición HTTP de descarga."""
        df_csv = _df_crudo_minimo(5)
        # Pre-crear el archivo de caché
        dir_raw = tmp_path / "data" / "raw" / "c5"
        dir_raw.mkdir(parents=True)
        ruta_cache = dir_raw / "c5_incidentes_2022.csv"
        df_csv.to_csv(ruta_cache, index=False)

        ckan_resp = MagicMock(spec=requests.Response)
        ckan_resp.status_code = 200
        ckan_resp.json.return_value = {
            "success": True,
            "result": {"resources": [{
                "name": "Incidentes 2022",
                "url": "https://fake.url/2022.csv",
                "format": "CSV",
            }]}
        }
        ckan_resp.raise_for_status.return_value = None
        session = MagicMock(spec=requests.Session)
        session.get.return_value = ckan_resp  # solo devuelve CKAN, no CSV

        cliente = C5IncidentesClient(tmp_path, años=[2022], session=session)
        cliente.ejecutar_pipeline(forzar_descarga=False)
        # Solo una llamada (CKAN), sin descarga del CSV
        assert session.get.call_count == 1


# ──────────────────────────────────────────────────────────────────────
# Tests de ResumenPipeline
# ──────────────────────────────────────────────────────────────────────

class TestResumenPipeline:
    def test_tasa_retencion_calculo(self):
        r = ResumenPipeline(registros_crudos=100, registros_validos=80)
        assert r.tasa_retencion == pytest.approx(0.80)

    def test_tasa_retencion_cero_cuando_sin_registros(self):
        r = ResumenPipeline()
        assert r.tasa_retencion == 0.0

    def test_años_procesados_por_defecto_vacio(self):
        r = ResumenPipeline()
        assert r.años_procesados == []


# ──────────────────────────────────────────────────────────────────────
# Tests de funciones auxiliares
# ──────────────────────────────────────────────────────────────────────

class TestFuncionesAuxiliares:
    @pytest.mark.parametrize("texto,esperado", [
        ("Incidentes Viales 2022", 2022),
        ("c5_incidentes_2019.csv", 2019),
        ("datos-2023-viales", 2023),
        ("sin_año_aqui", None),
        ("Reporte 1999", None),   # año fuera de rango
    ])
    def test_inferir_año(self, texto, esperado):
        assert _inferir_año(texto, "") == esperado

    @pytest.mark.parametrize("valor,esperado", [
        ("19.4326",   19.4326),
        ("19,4326",   19.4326),
        ("-99.1332", -99.1332),
        ("-99,1332", -99.1332),
        ("  19.4326  ", 19.4326),
        ("no_numero",   float("nan")),
    ])
    def test_limpiar_coordenada(self, valor, esperado):
        serie = pd.Series([valor])
        resultado = _limpiar_coordenada(serie).iloc[0]
        if pd.isna(esperado):
            assert pd.isna(resultado)
        else:
            assert resultado == pytest.approx(esperado, abs=1e-4)

    @pytest.mark.parametrize("fecha_str,valida", [
        ("15/03/2023 08:30:00", True),
        ("2023-03-15 08:30:00", True),
        ("15/03/2023",         True),
        ("2023-03-15",         True),
        ("no_es_fecha",        False),
    ])
    def test_parsear_fecha(self, fecha_str, valida):
        serie  = pd.Series([fecha_str])
        resultado = _parsear_fecha(serie).iloc[0]
        if valida:
            assert pd.notna(resultado)
        else:
            assert pd.isna(resultado)

    def test_años_vacios_lanza_error(self, tmp_path):
        with pytest.raises(ValueError, match="vacía"):
            C5IncidentesClient(tmp_path, años=[])
