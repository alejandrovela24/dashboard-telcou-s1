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


def _get_bytes(path: str, params: dict = None) -> bytes | None:
    try:
        r = requests.get(f"{_base()}{path}", params=params, timeout=60)
        r.raise_for_status()
        return r.content
    except requests.exceptions.ConnectionError:
        st.error("No se puede conectar a la API. Verifica que telcou-api esté corriendo en " + _base())
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"Error de API ({e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al contactar la API: {e}")
        return None


def _get_bytes_admin(path: str, params: dict = None) -> bytes | None:
    headers = {"X-Admin-Token": st.secrets.get("ADMIN_TOKEN", "")}
    try:
        r = requests.get(f"{_base()}{path}", params=params, headers=headers, timeout=60)
        r.raise_for_status()
        return r.content
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


def _post_file(path: str, files: dict, params: dict = None) -> dict | list | None:
    headers = {"X-Admin-Token": st.secrets.get("ADMIN_TOKEN", "")}
    try:
        r = requests.post(f"{_base()}{path}", files=files, params=params, headers=headers, timeout=120)
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
def get_sucursales(anio: int, regional: str = "TS R2", nombre: Optional[str] = None) -> list[dict]:
    params = {"anio": anio, "regional": regional}
    if nombre: params["nombre"] = nombre
    return _get("/analitica/sucursales", params) or []


def get_convocatoria_preview(dia: str, regional: str, semana: str) -> list[dict]:
    return _get(
        "/analitica/convocatoria-preview",
        {"dia": dia, "regional": regional, "semana": semana},
    ) or []


def get_reporte_pendientes_excel(anio: int, dia: Optional[list[str]] = None) -> bytes | None:
    params = {"anio": anio}
    if dia:
        params["dia"] = dia  # requests repite el parametro por cada elemento de la lista
    return _get_bytes("/analitica/reporte-supletorios-pendientes", params)


def get_reporte_pendientes_html(anio: int, dia: Optional[list[str]] = None) -> bytes | None:
    params = {"anio": anio}
    if dia:
        params["dia"] = dia
    return _get_bytes("/analitica/reporte-supletorios-pendientes-html", params)


def get_reporte_asistencia_excel(anio: int, regional: Optional[str] = None) -> bytes | None:
    params = {"anio": anio}
    if regional:
        params["regional"] = regional
    return _get_bytes("/analitica/reporte-asistencia", params)


def get_reporte_asistencia_html(anio: int, regional: Optional[str] = None) -> bytes | None:
    params = {"anio": anio}
    if regional:
        params["regional"] = regional
    return _get_bytes("/analitica/reporte-asistencia-html", params)


def get_reporte_calificaciones_excel(anio: int, regional: Optional[str] = None) -> bytes | None:
    params = {"anio": anio}
    if regional:
        params["regional"] = regional
    return _get_bytes("/analitica/reporte-calificaciones", params)


def get_reporte_calificaciones_html(anio: int, regional: Optional[str] = None) -> bytes | None:
    params = {"anio": anio}
    if regional:
        params["regional"] = regional
    return _get_bytes("/analitica/reporte-calificaciones-html", params)


def get_reporte_calificaciones_macro_excel(
    anio: int, mes_desde: Optional[str] = None, mes_hasta: Optional[str] = None,
    combinado: bool = False,
) -> bytes | None:
    params = {"anio": anio, "combinado": combinado}
    if mes_desde:
        params["mes_desde"] = mes_desde
    if mes_hasta:
        params["mes_hasta"] = mes_hasta
    return _get_bytes("/analitica/reporte-calificaciones-macro", params)


def get_regional_dia_configurado(regional: str) -> bool:
    resultado = _get("/analitica/regional-dia-configurado", {"regional": regional})
    return bool(resultado and resultado.get("configurado"))


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
    enviar_resumen_ejecutivo: bool = True,
) -> dict | None:
    body = {
        "cedulas": cedulas, "semana": semana, "modo_prueba": modo_prueba,
        "enviar_resumen_ejecutivo": enviar_resumen_ejecutivo,
    }
    if correo_prueba:
        body["correo_prueba"] = correo_prueba
    if regional:
        body["regional"] = regional
    if dia:
        body["dia"] = dia
    return _post("/admin/enviar-convocatoria", body)


def enviar_resumen_consolidado(
    semana: str,
    modo_prueba: bool,
    dia: Optional[str] = None,
    correo_prueba: Optional[str] = None,
) -> dict | None:
    body = {"semana": semana, "modo_prueba": modo_prueba}
    if dia:
        body["dia"] = dia
    if correo_prueba:
        body["correo_prueba"] = correo_prueba
    return _post("/admin/enviar-resumen-consolidado", body)


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


def get_emails_enviados(
    tipo: Optional[str] = None,
    cedula: Optional[str] = None,
    modo_prueba: Optional[bool] = None,
    dia: Optional[str] = None,
) -> list[dict]:
    params: dict = {}
    if tipo:
        params["tipo"] = tipo
    if cedula:
        params["cedula"] = cedula
    if modo_prueba is not None:
        params["modo_prueba"] = modo_prueba
    if dia:
        params["dia"] = dia
    return _get_admin("/analitica/emails-enviados", params) or []


def get_email_enviado_html(email_id: int) -> bytes | None:
    return _get_bytes_admin(f"/analitica/emails-enviados/{email_id}/html")


def get_emails_enviados_zip(
    ids: Optional[list[int]] = None,
    tipo: Optional[str] = None,
    cedula: Optional[str] = None,
    modo_prueba: Optional[bool] = None,
    dia: Optional[str] = None,
) -> bytes | None:
    params: dict = {}
    if ids:
        params["ids"] = ids  # requests repite el parametro por cada elemento de la lista
    else:
        if tipo:
            params["tipo"] = tipo
        if cedula:
            params["cedula"] = cedula
        if modo_prueba is not None:
            params["modo_prueba"] = modo_prueba
        if dia:
            params["dia"] = dia
    return _get_bytes_admin("/analitica/emails-enviados/zip", params)


def get_cursos(anio: Optional[int] = None, regional: Optional[str] = None) -> list[dict]:
    params = {}
    if anio:     params["anio"] = anio
    if regional: params["regional"] = regional
    return _get("/cursos/", params) or []


def cargar_curso(
    archivo_bytes: bytes,
    nombre_archivo: str,
    modo: str,
    *,
    codigo: Optional[str] = None,
    nombre: Optional[str] = None,
    tipo: Optional[str] = None,
    mes: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    anio: Optional[int] = None,
    regional: Optional[str] = None,
    curso_id: Optional[int] = None,
    convocatoria: Optional[int] = None,
    url_telcou: Optional[str] = None,
) -> dict | None:
    params: dict = {"modo": modo}
    if modo == "nuevo":
        params.update({
            "codigo": codigo, "nombre": nombre, "tipo": tipo, "mes": mes,
            "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
            "anio": anio, "regional": regional,
        })
        if url_telcou:
            params["url_telcou"] = url_telcou
    else:
        params.update({"curso_id": curso_id, "convocatoria": convocatoria})
    files = {"archivo": (nombre_archivo, archivo_bytes, "text/csv")}
    return _post_file("/admin/cargar-curso", files=files, params=params)


def crear_empleado(payload: dict) -> dict | None:
    return _post("/admin/empleados", payload)


def get_no_rindieron(curso_id: int) -> dict | None:
    return _get_admin(f"/analitica/curso/{curso_id}/no-rindieron")


def enviar_novedad(
    curso_id: int,
    cedulas: list[str],
    modo_prueba: bool,
    correo_prueba: Optional[str] = None,
) -> dict | None:
    body = {"cedulas": cedulas, "modo_prueba": modo_prueba}
    if correo_prueba:
        body["correo_prueba"] = correo_prueba
    return _post(f"/admin/curso/{curso_id}/enviar-novedad", body)


def resolver_nota(nota_id: int, estado: str) -> dict | None:
    return _patch(f"/admin/notas/{nota_id}/resolver", {"estado": estado})


def actualizar_observacion_nota(nota_id: int, observacion: str) -> dict | None:
    return _patch(f"/admin/notas/{nota_id}/observacion", {"observacion": observacion})


def set_convocatoria_habilitada(curso_id: int, habilitada: bool) -> dict | None:
    return _patch(f"/admin/curso/{curso_id}/convocatoria-habilitada", {"habilitada": habilitada})


def set_evaluado(curso_id: int, evaluado: bool) -> dict | None:
    return _patch(f"/admin/curso/{curso_id}/evaluado", {"evaluado": evaluado})


def marcar_na(curso_id: int, cedulas: list[str]) -> dict | None:
    return _post(f"/admin/curso/{curso_id}/marcar-na", {"cedulas": cedulas})
