import streamlit as st

import api_client as api

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]

TIPOS_REPORTE = ["Supletorios pendientes", "Asistencia", "Calificaciones generales", "Calificaciones (formato macro)"]


def render_tab_reporteria(anio: int) -> None:
    st.title("📥 Reportería")

    tipo = st.radio("Tipo de reporte", TIPOS_REPORTE, key="rep_tipo", horizontal=True)
    st.divider()

    if tipo == "Supletorios pendientes":
        _seccion_supletorios(anio)
    elif tipo == "Asistencia":
        _seccion_asistencia(anio)
    elif tipo == "Calificaciones generales":
        _seccion_calificaciones(anio)
    else:
        _seccion_calificaciones_macro(anio)


def _seccion_supletorios(anio: int) -> None:
    st.markdown("### Supletorios pendientes")

    dias_sel = st.multiselect(
        "Día de capacitación",
        DIAS,
        key="rep_dia",
        help="Filtra a quienes tienen alguno de estos días efectivos de capacitación asignado "
             "(elige uno o varios — vacío = todos). Guamaní/Mariana de Jesús (Quito) y TS R2 se "
             "muestran cada una por separado; Virtual aparece siempre, ya que está disponible "
             "toda la semana.",
    )
    dia = dias_sel or None
    sufijo_archivo = f"_{'-'.join(d.lower() for d in dias_sel)}" if dia else ""
    sufijo_caption = f" para el día **{', '.join(dias_sel)}**" if dia else ""

    st.markdown("#### 📊 Excel (lista)")
    st.caption(
        "Un Excel con los colaboradores que tienen supletorio pendiente en el año "
        f"**{anio}**{sufijo_caption} — una fila por colaborador y curso pendiente (cédula, nombre, "
        "área, sucursal, tema, fechas, link de Moodle y nota), con hojas separadas por sede/regional. "
        "Las hojas de Guamaní y Mariana de Jesús agregan Jefe Inmediato, Aula y Código de curso."
    )
    with st.spinner("Generando Excel…"):
        excel_contenido = api.get_reporte_pendientes_excel(anio, dia=dia)
    if excel_contenido:
        st.download_button(
            label=f"⬇️ Descargar supletorios pendientes {anio}{sufijo_archivo} (.xlsx)",
            data=excel_contenido,
            file_name=f"supletorios_pendientes_{anio}{sufijo_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("No se pudo generar el Excel. Verifica la conexión con telcou-api.")

    st.divider()

    st.markdown("#### 🔎 Vista interactiva (HTML)")
    st.caption(
        "Una página HTML descargable (funciona sin conexión, se abre en cualquier navegador) para "
        "buscar un colaborador por nombre o cédula y ver sus supletorios pendientes — solo aparecen "
        f"quienes tienen al menos uno{sufijo_caption}."
    )
    with st.spinner("Generando página HTML…"):
        html_contenido = api.get_reporte_pendientes_html(anio, dia=dia)
    if html_contenido:
        st.download_button(
            label=f"⬇️ Descargar vista interactiva {anio}{sufijo_archivo} (.html)",
            data=html_contenido,
            file_name=f"supletorios_pendientes_{anio}{sufijo_archivo}.html",
            mime="text/html",
        )
    else:
        st.info("No se pudo generar la página HTML. Verifica la conexión con telcou-api.")


def _seccion_reporte_general(
    anio: int, titulo: str, descripcion: str, key_prefix: str,
    get_excel, get_html, nombre_archivo: str,
) -> None:
    st.markdown(f"### {titulo}")
    st.caption(descripcion)

    regional_sel = st.selectbox(
        "Regional", ["Todas", "Quito", "TS R2"], key=f"{key_prefix}_regional",
        help="'Todas' genera una hoja por regional en el mismo archivo.",
    )
    regional = None if regional_sel == "Todas" else regional_sel
    sufijo_archivo = f"_{regional}" if regional else ""

    st.markdown("#### 📊 Excel")
    with st.spinner("Generando Excel…"):
        excel_contenido = get_excel(anio, regional=regional)
    if excel_contenido:
        st.download_button(
            label=f"⬇️ Descargar {nombre_archivo} {anio}{sufijo_archivo} (.xlsx)",
            data=excel_contenido,
            file_name=f"{nombre_archivo}_{anio}{sufijo_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key_prefix}_dl_excel",
        )
    else:
        st.info("No se pudo generar el Excel. Verifica la conexión con telcou-api.")

    st.divider()

    st.markdown("#### 🔎 Vista interactiva (HTML)")
    st.caption(
        "Una página HTML descargable (funciona sin conexión, se abre en cualquier navegador) para "
        "buscar un colaborador por nombre o cédula."
    )
    with st.spinner("Generando página HTML…"):
        html_contenido = get_html(anio, regional=regional)
    if html_contenido:
        st.download_button(
            label=f"⬇️ Descargar vista interactiva {anio}{sufijo_archivo} (.html)",
            data=html_contenido,
            file_name=f"{nombre_archivo}_{anio}{sufijo_archivo}.html",
            mime="text/html",
            key=f"{key_prefix}_dl_html",
        )
    else:
        st.info("No se pudo generar la página HTML. Verifica la conexión con telcou-api.")


def _seccion_asistencia(anio: int) -> None:
    _seccion_reporte_general(
        anio,
        titulo="Asistencia",
        descripcion=(
            "Todos los estados sin nota numérica: ASISTENCIA, FALTA_INJUSTIFICADA, "
            "FALTA_JUSTIFICADA, VACACIONES, NO_APLICA, EXONERADO, CAMBIO, SALIO y NUEVO. "
            "Incluye si el estado se resolvió vía Novedades y su observación."
        ),
        key_prefix="rep_asist",
        get_excel=api.get_reporte_asistencia_excel,
        get_html=api.get_reporte_asistencia_html,
        nombre_archivo="asistencia",
    )


def _seccion_calificaciones(anio: int) -> None:
    _seccion_reporte_general(
        anio,
        titulo="Calificaciones generales",
        descripcion=(
            "El libro de calificaciones completo del año: todas las notas regulares "
            "(aprobados, reprobados, y todo lo demás), con si el estado se resolvió vía "
            "Novedades y su observación."
        ),
        key_prefix="rep_calif",
        get_excel=api.get_reporte_calificaciones_excel,
        get_html=api.get_reporte_calificaciones_html,
        nombre_archivo="calificaciones",
    )


MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


def _seccion_calificaciones_macro(anio: int) -> None:
    st.markdown("### Calificaciones (formato macro)")
    st.caption(
        "Replica el formato exacto del macro manual: una fila por colaborador, una columna "
        "por curso, con las mismas fórmulas de resumen (0 por copia, faltas, supletorios, "
        "promedio). Dos hojas en el mismo archivo: Quito y TS R2."
    )

    col1, col2 = st.columns(2)
    opciones_mes = ["Todo el año"] + MESES
    mes_desde_sel = col1.selectbox("Desde", opciones_mes, key="rep_macro_desde")
    mes_hasta_sel = col2.selectbox("Hasta", opciones_mes, key="rep_macro_hasta")
    mes_desde = None if mes_desde_sel == "Todo el año" else mes_desde_sel
    mes_hasta = None if mes_hasta_sel == "Todo el año" else mes_hasta_sel

    combinado = st.checkbox(
        "Incluir supletorios", key="rep_macro_combinado",
        help="Agrega una columna extra por cada curso con supletorio pendiente o rendido, "
             "mostrando su propio resultado.",
    )

    sufijo_archivo = ""
    if mes_desde or mes_hasta:
        sufijo_archivo = f"_{mes_desde or 'inicio'}-{mes_hasta or 'fin'}"

    with st.spinner("Generando Excel…"):
        excel_contenido = api.get_reporte_calificaciones_macro_excel(
            anio, mes_desde=mes_desde, mes_hasta=mes_hasta, combinado=combinado,
        )
    if excel_contenido:
        st.download_button(
            label=f"⬇️ Descargar calificaciones (formato macro) {anio}{sufijo_archivo} (.xlsx)",
            data=excel_contenido,
            file_name=f"calificaciones_macro_{anio}{sufijo_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="rep_macro_dl_excel",
        )
    else:
        st.info("No se pudo generar el Excel. Verifica la conexión con telcou-api.")
