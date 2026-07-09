from urllib.parse import quote

import requests
import streamlit as st
from typing import Optional


def _base() -> str:
    return st.secrets.get("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _get(path: str, params: dict = None) -> list | dict | None:
    try:
        r = requests.get(f"{_base()}{path}", params=params, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("No se puede conectar a la API. Verifica que telcou-api esté corriendo en " + _base())
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None
        st.error(f"Error de API ({e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al contactar la API: {e}")
        return None


def _get_admin(path: str, params: dict = None) -> list | dict | None:
    headers = {"X-Admin-Token": st.secrets.get("ADMIN_TOKEN", "")}
    try:
        r = requests.get(f"{_base()}{path}", params=params, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("No se puede conectar a la API. Verifica que telcou-api esté corriendo en " + _base())
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"Error de API ({e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al contactar la API: {e}")
        return None


def _write(method: str, path: str, json: dict = None, params: dict = None) -> dict | list | None:
    headers = {"X-Admin-Token": st.secrets.get("ADMIN_TOKEN", "")}
    try:
        r = requests.request(
            method, f"{_base()}{path}", json=json, params=params, headers=headers, timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("No se puede conectar a la API. Verifica que telcou-api esté corriendo en " + _base())
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"Error de API ({e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al contactar la API: {e}")
        return None


def _patch(path: str, json: dict) -> dict | None:
    return _write("PATCH", path, json=json)


def _post(path: str, json: dict) -> dict | None:
    return _write("POST", path, json=json)


@st.cache_data(ttl=900, show_spinner=False)
def get_empleados(
    area: Optional[str] = None,
    regional: Optional[str] = None,
    anio: Optional[int] = None,
    inactivo: Optional[bool] = None,
) -> list[dict]:
    params = {}
    if area:                 params["area"] = area
    if regional:             params["regional"] = regional
    if anio:                 params["anio"] = anio
    if inactivo is not None: params["inactivo"] = inactivo
    return _get("/empleados/", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_notas_empleado(
    cedula: str,
    anio: Optional[int] = None,
    mes: Optional[str] = None,
    regional: Optional[str] = None,
) -> list[dict]:
    params = {}
    if anio:     params["anio"] = anio
    if mes:      params["mes"] = mes
    if regional: params["regional"] = regional
    return _get(f"/empleados/{quote(cedula, safe='')}/notas", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_resumen_empleado(cedula: str, anio: int) -> dict | None:
    return _get(f"/empleados/{quote(cedula, safe='')}/resumen", {"anio": anio})


@st.cache_data(ttl=900, show_spinner=False)
def get_trazabilidad_empleado(cedula: str, anio: Optional[int] = None) -> list[dict]:
    params = {}
    if anio: params["anio"] = anio
    return _get(f"/empleados/{quote(cedula, safe='')}/trazabilidad", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_listado_cursos(
    anio: int,
    mes: Optional[str] = None,
    nombre: Optional[str] = None,
) -> list[dict]:
    params: dict = {"anio": anio}
    if mes:    params["mes"] = mes
    if nombre: params["nombre"] = nombre
    return _get("/analitica/listado-cursos", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_supletorios_pendientes(
    anio: int,
    regional: Optional[str] = None,
    curso: Optional[str] = None,
    sucursal: Optional[str] = None,
) -> list[dict]:
    params: dict = {"anio": anio}
    if regional: params["regional"] = regional
    if curso:    params["curso"] = curso
    if sucursal: params["sucursal"] = sucursal
    return _get("/analitica/supletorios-pendientes", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_areas(anio: int, regional: Optional[str] = None) -> list[dict]:
    params = {"anio": anio}
    if regional: params["regional"] = regional
    return _get("/analitica/areas", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_regionales(anio: int) -> list[dict]:
    return _get("/analitica/regionales", {"anio": anio}) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_sucursales(anio: int, regional: str = "TS R2", nombre: Optional[str] = None) -> list[dict]:
    params = {"anio": anio, "regional": regional}
    if nombre: params["nombre"] = nombre
    return _get("/analitica/sucursales", params) or []


def get_convocatoria_preview(dia: str, regional: str, semana: str) -> list[dict]:
    return _get(
        "/analitica/convocatoria-preview",
        {"dia": dia, "regional": regional, "semana": semana},
    ) or []


def buscar_supletorios_pendientes(nombre: str, anio: int, regional: Optional[str] = None) -> list[dict]:
    params = {"nombre": nombre, "anio": anio}
    if regional:
        params["regional"] = regional
    return _get("/analitica/supletorios-pendientes/buscar", params) or []


def get_dia_historial(cedula: str) -> list[dict]:
    return _get(f"/empleados/{quote(cedula, safe='')}/dia-historial") or []


def cambiar_dia_empleado(
    cedula: str,
    dia_nuevo: str,
    tipo: str,
    motivo: str,
    semana_inicio: Optional[str] = None,
    editado_por: Optional[str] = None,
) -> dict | None:
    body = {"dia_nuevo": dia_nuevo, "tipo": tipo, "motivo": motivo}
    if semana_inicio:
        body["semana_inicio"] = semana_inicio
    if editado_por:
        body["editado_por"] = editado_por
    return _patch(f"/empleados/{quote(cedula, safe='')}/dia", body)


def enviar_convocatoria(
    cedulas: list[str],
    semana: str,
    modo_prueba: bool,
    correo_prueba: Optional[str] = None,
    regional: Optional[str] = None,
    dia: Optional[str] = None,
) -> dict | None:
    body = {"cedulas": cedulas, "semana": semana, "modo_prueba": modo_prueba}
    if correo_prueba:
        body["correo_prueba"] = correo_prueba
    if regional:
        body["regional"] = regional
    if dia:
        body["dia"] = dia
    return _post("/admin/enviar-convocatoria", body)


def get_envios_convocatoria(
    anio: Optional[int] = None,
    regional: Optional[str] = None,
    modo_prueba: Optional[bool] = None,
) -> list[dict]:
    params: dict = {}
    if anio is not None:
        params["anio"] = anio
    if regional:
        params["regional"] = regional
    if modo_prueba is not None:
        params["modo_prueba"] = modo_prueba
    return _get_admin("/analitica/envios-convocatoria", params) or []
