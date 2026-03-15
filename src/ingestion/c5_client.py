"""
Cliente para los datos históricos de incidentes viales del C5 CDMX.

Fuente: Portal de Datos Abiertos de la CDMX
    https://datos.cdmx.gob.mx/dataset/incidentes-viales-c5

El C5 publica CSVs anuales de incidentes viales (choques, atropellados,
derrumbes, etc.) reportados al 911 desde 2014. Este módulo descarga,
normaliza y procesa esos registros para alimentar el modelo estocástico
de UrbanFlow con información histórica de densidad de incidentes.

Pipeline principal
------------------
1. **Descubrimiento**: consulta la API CKAN de datos.cdmx.gob.mx para
   obtener las URLs de los CSVs disponibles por año.
2. **Descarga**: guarda cada CSV en ``data/raw/c5/`` (caché local).
3. **Normalización**: estandariza nombres de columnas, parsea fechas,
   corrige separadores decimales y codificación (UTF-8 / Latin-1).
4. **Filtrado geográfico**: descarta registros fuera del bounding box
   de la ZMVM.
5. **Densidad temporal**: agrega los incidentes por hora, día de la
   semana y mes para calcular distribuciones de probabilidad de
   congestión inducida por incidentes.
6. **Exportación**: guarda el dataset limpio en
   ``data/processed/c5_incidentes.parquet``.

Esquema de salida (parquet)
---------------------------
| Columna          | Tipo       | Descripción                         |
|------------------|------------|-------------------------------------|
| fecha_hora       | datetime64 | Fecha y hora del incidente (UTC-6)  |
| año              | int16      | Año del incidente                   |
| mes              | int8       | Mes (1–12)                          |
| dia              | int8       | Día del mes (1–31)                  |
| hora             | int8       | Hora del día (0–23)                 |
| dia_semana       | int8       | Día de la semana (0=lunes…6=domingo)|
| latitud          | float32    | Latitud WGS84                       |
| longitud         | float32    | Longitud WGS84                      |
| tipo_incidente   | str        | Categoría del incidente             |
| alcaldia         | str        | Alcaldía donde ocurrió              |
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────

CKAN_API_URL  = "https://datos.cdmx.gob.mx/api/3/action/package_show"
DATASET_ID    = "incidentes-viales-c5"
AÑOS_DEFAULT  = list(range(2018, 2026))

# Bounding box ZMVM (misma que en TomTom y OWM)
ZMVM_LAT_MIN, ZMVM_LAT_MAX =  19.05, 19.85
ZMVM_LON_MIN, ZMVM_LON_MAX = -99.45, -98.85

# Columnas canónicas del esquema de salida
COLUMNAS_SALIDA = [
    "fecha_hora", "año", "mes", "dia", "hora", "dia_semana",
    "latitud", "longitud", "tipo_incidente", "alcaldia",
]

# Mapeo de nombres de columna reales (varían por año) → nombre canónico
# Se aplica en orden: primera coincidencia gana.
MAPEO_COLUMNAS: dict[str, str] = {
    # Fecha / hora
    "fecha_creacion":        "fecha_hora",
    "fecha_hora_inicio":     "fecha_hora",
    "fecha_inicio":          "fecha_hora",
    "date":                  "fecha_hora",
    # Tipo de incidente
    "incidente_c4":          "tipo_incidente",
    "tipo_incidente":        "tipo_incidente",
    "tipo_entrada":          "tipo_incidente",
    "clasificacion_del_llamado": "tipo_incidente",
    # Alcaldía / delegación
    "alcaldia_inicio":       "alcaldia",
    "alcaldía_inicio":       "alcaldia",
    "delegacion_inicio":     "alcaldia",
    "delegación_inicio":     "alcaldia",
    "municipio_delegacion":  "alcaldia",
    # Coordenadas
    "latitud":               "latitud",
    "longitud":              "longitud",
    "longitud_inicio":       "longitud",
    "latitud_inicio":        "latitud",
}

# Encodings a probar en orden (los CSVs del C5 no son consistentes)
ENCODINGS = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]

# Umbrales de percentil para clasificar densidad → estado de tráfico
# (usado en calcular_densidad_temporal)
PERCENTIL_FLUIDO      = 40   # p0–p40  → FLUIDO
PERCENTIL_LENTO       = 75   # p40–p75 → LENTO
# p75–p100 → CONGESTIONADO


# ──────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ──────────────────────────────────────────────────────────────────────

@dataclass
class RecursoC5:
    """Metadatos de un recurso CSV del dataset C5 en el portal CKAN."""
    nombre:  str
    url:     str
    formato: str
    año:     int | None = None


@dataclass
class ResumenPipeline:
    """Estadísticas del pipeline de ingesta tras su ejecución."""
    años_procesados:      list[int]   = field(default_factory=list)
    registros_crudos:     int         = 0
    registros_validos:    int         = 0
    registros_descartados: int        = 0
    ruta_parquet:         str         = ""
    columnas_faltantes:   list[str]   = field(default_factory=list)

    @property
    def tasa_retencion(self) -> float:
        if self.registros_crudos == 0:
            return 0.0
        return round(self.registros_validos / self.registros_crudos, 4)


# ──────────────────────────────────────────────────────────────────────
# Excepciones
# ──────────────────────────────────────────────────────────────────────

class C5DescargaError(Exception):
    """Error al descargar o acceder a los datos del C5."""


class C5FormatoError(Exception):
    """El CSV descargado no tiene las columnas esperadas."""


# ──────────────────────────────────────────────────────────────────────
# Cliente principal
# ──────────────────────────────────────────────────────────────────────

class C5IncidentesClient:
    """
    Descarga, normaliza y procesa los incidentes viales históricos del C5 CDMX.

    Parámetros
    ----------
    directorio_datos : str o Path
        Raíz del proyecto; los subdirectorios ``data/raw/c5/`` y
        ``data/processed/`` se crean automáticamente si no existen.
    años : list[int], opcional
        Años a descargar. Por defecto 2018–2025.
    timeout : int, opcional
        Timeout HTTP en segundos. Por defecto 60 (los CSVs son grandes).
    max_reintentos : int, opcional
        Reintentos ante errores de red. Por defecto 3.
    session : requests.Session o None, opcional
        Sesión HTTP inyectable para tests.

    Ejemplo
    -------
    >>> cliente = C5IncidentesClient(".")
    >>> resumen = cliente.ejecutar_pipeline()
    >>> print(resumen.registros_validos)
    """

    def __init__(
        self,
        directorio_datos: str | Path = ".",
        años:             list[int] | None = None,
        timeout:          int = 60,
        max_reintentos:   int = 3,
        session:          requests.Session | None = None,
    ) -> None:
        self.dir_datos     = Path(directorio_datos)
        self.dir_raw       = self.dir_datos / "data" / "raw"  / "c5"
        self.dir_processed = self.dir_datos / "data" / "processed"
        if años is not None and not años:
            raise ValueError("'años' no puede ser una lista vacía.")
        self.años          = años if años is not None else AÑOS_DEFAULT
        self.timeout       = timeout
        self.max_reintentos = max_reintentos
        self._session      = session or requests.Session()

    # ------------------------------------------------------------------
    # Pipeline completo
    # ------------------------------------------------------------------

    def ejecutar_pipeline(
        self,
        forzar_descarga: bool = False,
    ) -> ResumenPipeline:
        """
        Ejecuta el pipeline completo de ingesta.

        Pasos: descubrimiento → descarga → normalización → filtrado
        geográfico → enriquecimiento temporal → exportación parquet.

        Parámetros
        ----------
        forzar_descarga : bool
            Si ``True``, re-descarga aunque el CSV ya exista en caché.

        Devuelve
        --------
        ResumenPipeline
        """
        self.dir_raw.mkdir(parents=True, exist_ok=True)
        self.dir_processed.mkdir(parents=True, exist_ok=True)

        recursos = self.descubrir_recursos()
        recursos_año = {r.año: r for r in recursos if r.año in self.años}

        frames: list[pd.DataFrame] = []
        resumen = ResumenPipeline()

        for año in sorted(self.años):
            try:
                if año in recursos_año:
                    ruta = self._descargar_si_necesario(
                        recursos_año[año], forzar=forzar_descarga
                    )
                else:
                    logger.warning("No se encontró recurso para el año %d.", año)
                    continue

                df_año = self.cargar_csv(ruta)
                resumen.registros_crudos += len(df_año)

                df_norm = normalizar_dataframe(df_año)
                df_filt = filtrar_zmvm(df_norm)

                resumen.registros_validos    += len(df_filt)
                resumen.registros_descartados += len(df_año) - len(df_filt)
                resumen.años_procesados.append(año)
                frames.append(df_filt)

            except C5FormatoError as exc:
                logger.warning("Año %d omitido por error de formato: %s", año, exc)
            except C5DescargaError as exc:
                logger.warning("Año %d omitido por error de descarga: %s", año, exc)

        if not frames:
            raise C5DescargaError(
                "No se pudo procesar ningún año. "
                "Verifica la conectividad o los CSVs locales."
            )

        df_total = pd.concat(frames, ignore_index=True)
        df_total = enriquecer_columnas_temporales(df_total)

        ruta_parquet = self.dir_processed / "c5_incidentes.parquet"
        df_total.to_parquet(ruta_parquet, index=False)
        resumen.ruta_parquet = str(ruta_parquet)

        logger.info(
            "Pipeline C5 completado: %d registros válidos → %s",
            resumen.registros_validos, ruta_parquet,
        )
        return resumen

    # ------------------------------------------------------------------
    # Descubrimiento de recursos en CKAN
    # ------------------------------------------------------------------

    def descubrir_recursos(self) -> list[RecursoC5]:
        """
        Consulta la API CKAN de datos.cdmx.gob.mx para obtener la lista
        de recursos CSV disponibles del dataset de incidentes C5.

        Devuelve
        --------
        list[RecursoC5]
            Lista de recursos con URL, nombre y año inferido.

        Raises
        ------
        C5DescargaError
            Si la API no responde o no devuelve recursos CSV.
        """
        try:
            resp = self._session.get(
                CKAN_API_URL,
                params={"id": DATASET_ID},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            datos = resp.json()
        except requests.RequestException as exc:
            raise C5DescargaError(
                f"Error al consultar la API CKAN: {exc}"
            ) from exc

        if not datos.get("success"):
            raise C5DescargaError(
                f"La API CKAN devolvió success=False: {str(datos)[:300]}"
            )

        recursos = []
        for rec in datos.get("result", {}).get("resources", []):
            fmt = str(rec.get("format", "")).upper()
            if fmt not in ("CSV", ""):
                continue
            nombre = rec.get("name", rec.get("description", ""))
            url    = rec.get("url", "")
            año    = _inferir_año(nombre, url)
            recursos.append(RecursoC5(nombre=nombre, url=url, formato=fmt, año=año))

        logger.info("CKAN: %d recursos CSV encontrados.", len(recursos))
        return recursos

    # ------------------------------------------------------------------
    # Descarga
    # ------------------------------------------------------------------

    def cargar_csv_desde_url(self, url: str) -> pd.DataFrame:
        """
        Descarga un CSV desde ``url`` y lo devuelve como DataFrame,
        manejando encodings y separadores decimales.
        """
        contenido = self._descargar_bytes(url)
        return _leer_csv_bytes(contenido)

    def cargar_csv(self, ruta: str | Path) -> pd.DataFrame:
        """
        Carga un CSV local, probando múltiples encodings y manejando
        separadores decimales en español.
        """
        ruta = Path(ruta)
        if not ruta.exists():
            raise C5DescargaError(f"Archivo no encontrado: {ruta}")
        return _leer_csv_local(ruta)

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _descargar_si_necesario(
        self,
        recurso: RecursoC5,
        forzar: bool = False,
    ) -> Path:
        """Descarga el CSV al caché local si no existe (o si forzar=True)."""
        nombre_archivo = f"c5_incidentes_{recurso.año}.csv"
        ruta_destino   = self.dir_raw / nombre_archivo

        if ruta_destino.exists() and not forzar:
            logger.info("Caché encontrado para %d: %s", recurso.año, ruta_destino)
            return ruta_destino

        logger.info("Descargando año %d desde %s …", recurso.año, recurso.url)
        contenido = self._descargar_bytes(recurso.url)
        ruta_destino.write_bytes(contenido)
        logger.info("Guardado en %s (%.1f MB)", ruta_destino, len(contenido) / 1e6)
        return ruta_destino

    @retry(
        retry=retry_if_exception_type(
            (requests.Timeout, requests.ConnectionError)
        ),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _descargar_bytes(self, url: str) -> bytes:
        """Descarga bytes con reintentos. Lanza C5DescargaError en HTTP ≥ 400."""
        try:
            resp = self._session.get(url, timeout=self.timeout, stream=True)
        except requests.Timeout as exc:
            raise requests.Timeout(
                f"Timeout ({self.timeout}s) descargando {url}"
            ) from exc

        if resp.status_code >= 400:
            raise C5DescargaError(
                f"HTTP {resp.status_code} al descargar {url}: {resp.text[:200]}"
            )
        return resp.content


# ──────────────────────────────────────────────────────────────────────
# Funciones de transformación (públicas para testabilidad directa)
# ──────────────────────────────────────────────────────────────────────

def normalizar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza un DataFrame crudo del C5 al esquema canónico.

    Operaciones:
    - Renombra columnas según ``MAPEO_COLUMNAS`` (case-insensitive).
    - Parsea ``fecha_hora`` a datetime con inferencia de formato.
    - Convierte latitud/longitud a float, manejando separador decimal coma.
    - Normaliza ``tipo_incidente`` y ``alcaldia`` a mayúsculas sin espacios extras.
    - Descarta filas con fecha, latitud o longitud nulos.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame con columnas en bruto tal como viene del CSV.

    Devuelve
    --------
    pd.DataFrame
        DataFrame con columnas canónicas. Puede estar vacío si ninguna
        columna necesaria fue encontrada.

    Raises
    ------
    C5FormatoError
        Si el DataFrame no contiene ninguna columna reconocible para
        latitud, longitud o fecha.
    """
    df = df.copy()

    # ── 1. Renombrar columnas ─────────────────────────────────────────
    df.columns = [c.strip().lower() for c in df.columns]
    renombres  = {col: canon for col, canon in MAPEO_COLUMNAS.items()
                  if col in df.columns}
    df = df.rename(columns=renombres)

    # ── 2. Verificar columnas mínimas ─────────────────────────────────
    faltantes = [c for c in ("fecha_hora", "latitud", "longitud")
                 if c not in df.columns]
    if faltantes:
        raise C5FormatoError(
            f"El DataFrame no contiene columnas requeridas: {faltantes}. "
            f"Columnas disponibles: {list(df.columns)}"
        )

    # ── 3. Parsear fecha ──────────────────────────────────────────────
    df["fecha_hora"] = _parsear_fecha(df["fecha_hora"])
    df = df.dropna(subset=["fecha_hora"])

    # ── 4. Limpiar coordenadas ────────────────────────────────────────
    df["latitud"]  = _limpiar_coordenada(df["latitud"])
    df["longitud"] = _limpiar_coordenada(df["longitud"])
    df = df.dropna(subset=["latitud", "longitud"])

    # Algunos CSVs tienen lat/lon intercambiados (longitud > 0 para CDMX es error)
    # CDMX: latitud ≈ +19, longitud ≈ -99
    mask_swap = (df["latitud"] < 0) & (df["longitud"] > 0)
    if mask_swap.sum() > len(df) * 0.5:   # más de la mitad invertida → corregir
        df.loc[:, ["latitud", "longitud"]] = df[["longitud", "latitud"]].values
        logger.info("Columnas lat/lon detectadas intercambiadas y corregidas.")

    # ── 5. Normalizar texto ───────────────────────────────────────────
    for col in ("tipo_incidente", "alcaldia"):
        if col in df.columns:
            df[col] = (
                df[col].astype(str)
                       .str.strip()
                       .str.upper()
                       .str.replace(r"\s+", " ", regex=True)
            )
        else:
            df[col] = "DESCONOCIDO"

    # ── 6. Retener solo columnas base (latitud/longitud incluidas).
    #       Las columnas temporales derivadas (año, mes…) se agregan
    #       después en enriquecer_columnas_temporales().
    columnas_base = ["fecha_hora", "latitud", "longitud", "tipo_incidente", "alcaldia"]
    columnas_presentes = [c for c in columnas_base if c in df.columns]
    return df[columnas_presentes].reset_index(drop=True)


def filtrar_zmvm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra el DataFrame conservando solo registros dentro del bounding
    box de la ZMVM.

    Parámetros
    ----------
    df : pd.DataFrame
        DataFrame con columnas ``latitud`` y ``longitud`` (float).

    Devuelve
    --------
    pd.DataFrame
        Subconjunto de filas dentro de la ZMVM.

    Raises
    ------
    KeyError
        Si faltan las columnas ``latitud`` o ``longitud``.
    """
    if "latitud" not in df.columns or "longitud" not in df.columns:
        raise KeyError("El DataFrame debe contener columnas 'latitud' y 'longitud'.")

    mask = (
        df["latitud"].between(ZMVM_LAT_MIN, ZMVM_LAT_MAX) &
        df["longitud"].between(ZMVM_LON_MIN, ZMVM_LON_MAX)
    )
    descartados = (~mask).sum()
    if descartados:
        logger.debug("filtrar_zmvm: %d registros fuera del bounding box descartados.", descartados)
    return df[mask].reset_index(drop=True)


def enriquecer_columnas_temporales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega columnas derivadas de ``fecha_hora``:
    ``año``, ``mes``, ``dia``, ``hora``, ``dia_semana``.

    Parámetros
    ----------
    df : pd.DataFrame
        Debe contener la columna ``fecha_hora`` (datetime).

    Devuelve
    --------
    pd.DataFrame con las nuevas columnas añadidas.
    """
    if "fecha_hora" not in df.columns:
        raise KeyError("El DataFrame debe contener la columna 'fecha_hora'.")

    fh = pd.to_datetime(df["fecha_hora"])
    df = df.copy()
    df["año"]        = fh.dt.year.astype("int16")
    df["mes"]        = fh.dt.month.astype("int8")
    df["dia"]        = fh.dt.day.astype("int8")
    df["hora"]       = fh.dt.hour.astype("int8")
    df["dia_semana"] = fh.dt.dayofweek.astype("int8")  # 0=lunes…6=domingo

    # Optimizar tipos de columnas flotantes
    for col in ("latitud", "longitud"):
        if col in df.columns:
            df[col] = df[col].astype("float32")

    return df


def calcular_densidad_temporal(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula la densidad de incidentes por franja horaria y estima la
    probabilidad de cada estado de tráfico (FLUIDO / LENTO / CONGESTIONADO).

    La densidad se normaliza por el número de días del período para
    obtener incidentes promedio por hora del día.  El percentil 40 y 75
    de esa distribución se usan como umbrales de clasificación.

    Parámetros
    ----------
    df : pd.DataFrame
        Debe contener columnas ``hora`` (int 0–23) y ``fecha_hora``
        (datetime o date).

    Devuelve
    --------
    pd.DataFrame con índice = hora (0–23) y columnas:
        - ``incidentes_por_dia``: promedio diario de incidentes en esa hora
        - ``densidad_relativa``: densidad normalizada [0, 1]
        - ``p_fluido``, ``p_lento``, ``p_congestionado``: probabilidades estimadas
          del estado de tráfico en esa hora (suman 1.0 por fila)
        - ``estado_dominante``: estado con mayor probabilidad (str)
    """
    for col in ("hora", "fecha_hora"):
        if col not in df.columns:
            raise KeyError(f"El DataFrame debe contener la columna '{col}'.")

    n_dias = max(
        df["fecha_hora"].apply(
            lambda x: x.date() if hasattr(x, "date") else x
        ).nunique(),
        1,
    )

    conteo_horario = (
        df.groupby("hora")
          .size()
          .reindex(range(24), fill_value=0)
          .rename("total_incidentes")
    )

    resultado = conteo_horario.to_frame()
    resultado["incidentes_por_dia"] = resultado["total_incidentes"] / n_dias

    max_val = resultado["incidentes_por_dia"].max()
    resultado["densidad_relativa"] = (
        resultado["incidentes_por_dia"] / max_val if max_val > 0 else 0.0
    )

    # Umbrales sobre la distribución de incidentes_por_dia
    p40 = resultado["incidentes_por_dia"].quantile(PERCENTIL_FLUIDO / 100)
    p75 = resultado["incidentes_por_dia"].quantile(PERCENTIL_LENTO  / 100)

    resultado["p_fluido"]       = 0.0
    resultado["p_lento"]        = 0.0
    resultado["p_congestionado"]= 0.0

    for hora in resultado.index:
        ipd = resultado.at[hora, "incidentes_por_dia"]
        if ipd <= p40:
            resultado.at[hora, "p_fluido"]        = 0.70
            resultado.at[hora, "p_lento"]         = 0.20
            resultado.at[hora, "p_congestionado"] = 0.10
        elif ipd <= p75:
            resultado.at[hora, "p_fluido"]        = 0.25
            resultado.at[hora, "p_lento"]         = 0.55
            resultado.at[hora, "p_congestionado"] = 0.20
        else:
            resultado.at[hora, "p_fluido"]        = 0.10
            resultado.at[hora, "p_lento"]         = 0.30
            resultado.at[hora, "p_congestionado"] = 0.60

    resultado["estado_dominante"] = resultado[
        ["p_fluido", "p_lento", "p_congestionado"]
    ].idxmax(axis=1).str.replace("p_", "")

    return resultado.drop(columns=["total_incidentes"])


# ──────────────────────────────────────────────────────────────────────
# Funciones auxiliares privadas
# ──────────────────────────────────────────────────────────────────────

def _inferir_año(nombre: str, url: str) -> int | None:
    """Extrae el año de 4 dígitos del nombre o URL del recurso CKAN."""
    import re
    texto = f"{nombre} {url}"
    # Usar lookaround para evitar que _ (también \w) bloquee \b
    coincidencias = re.findall(r"(?<!\d)(201[4-9]|202[0-9])(?!\d)", texto)
    return int(coincidencias[0]) if coincidencias else None


def _parsear_fecha(serie: pd.Series) -> pd.Series:
    """
    Parsea una serie de strings de fecha al tipo datetime.
    Prueba múltiples formatos comunes en los CSV del C5.
    """
    formatos = [
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%d/%m/%Y",
        "%Y-%m-%d",
    ]
    for fmt in formatos:
        try:
            parsed = pd.to_datetime(serie, format=fmt, errors="coerce")
            tasa_ok = parsed.notna().mean()
            if tasa_ok >= 0.80:  # al menos 80 % parseados correctamente
                return parsed
        except Exception:
            continue

    # Último recurso: inferencia automática (sin argumento deprecado)
    return pd.to_datetime(serie, errors="coerce")


def _limpiar_coordenada(serie: pd.Series) -> pd.Series:
    """
    Convierte una serie de coordenadas a float.
    Maneja separadores decimales en español (coma) y valores no numéricos.
    """
    return (
        serie.astype(str)
             .str.strip()
             .str.replace(",", ".", regex=False)
             .str.replace(r"[^\d.\-]", "", regex=True)
             .replace("", float("nan"))
             .infer_objects(copy=False)
             .pipe(pd.to_numeric, errors="coerce")
    )


def _leer_csv_bytes(contenido: bytes) -> pd.DataFrame:
    """Carga un CSV desde bytes probando múltiples encodings."""
    for enc in ENCODINGS:
        try:
            return pd.read_csv(
                io.BytesIO(contenido),
                encoding=enc,
                low_memory=False,
                on_bad_lines="skip",
            )
        except (UnicodeDecodeError, Exception):
            continue
    raise C5FormatoError("No se pudo decodificar el CSV con ningún encoding conocido.")


def _leer_csv_local(ruta: Path) -> pd.DataFrame:
    """Carga un CSV local probando múltiples encodings."""
    for enc in ENCODINGS:
        try:
            return pd.read_csv(
                ruta,
                encoding=enc,
                low_memory=False,
                on_bad_lines="skip",
            )
        except (UnicodeDecodeError, Exception):
            continue
    raise C5FormatoError(
        f"No se pudo leer '{ruta}' con ningún encoding conocido."
    )
