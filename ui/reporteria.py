import streamlit as st

import api_client as api


def render_tab_reporteria(anio: int) -> None:
    st.title("📥 Reportería")

    st.markdown("### Supletorios pendientes")

    st.markdown("#### 📊 Excel (lista)")
    st.caption(
        "Un Excel con los colaboradores que tienen supletorio pendiente en el año "
        f"**{anio}** — una fila por colaborador y curso pendiente (cédula, nombre, área, sucursal, "
        "tema, fechas, link de Moodle y nota), con hojas separadas para Quito y TS R2."
    )
    with st.spinner("Generando Excel…"):
        excel_contenido = api.get_reporte_pendientes_excel(anio)
    if excel_contenido:
        st.download_button(
            label=f"⬇️ Descargar supletorios pendientes {anio} (.xlsx)",
            data=excel_contenido,
            file_name=f"supletorios_pendientes_{anio}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.info("No se pudo generar el Excel. Verifica la conexión con telcou-api.")

    st.divider()

    st.markdown("#### 🔎 Vista interactiva (HTML)")
    st.caption(
        "Una página HTML descargable (funciona sin conexión, se abre en cualquier navegador) para "
        "buscar un colaborador por nombre o cédula y ver sus supletorios pendientes — solo aparecen "
        "quienes tienen al menos uno."
    )
    with st.spinner("Generando página HTML…"):
        html_contenido = api.get_reporte_pendientes_html(anio)
    if html_contenido:
        st.download_button(
            label=f"⬇️ Descargar vista interactiva {anio} (.html)",
            data=html_contenido,
            file_name=f"supletorios_pendientes_{anio}.html",
            mime="text/html",
        )
    else:
        st.info("No se pudo generar la página HTML. Verifica la conexión con telcou-api.")
