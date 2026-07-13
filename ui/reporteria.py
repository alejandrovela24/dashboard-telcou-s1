import streamlit as st

import api_client as api


def render_tab_reporteria(anio: int) -> None:
    st.title("📥 Reportería")

    st.markdown("### Supletorios pendientes")
    st.caption(
        "Descarga un Excel con los colaboradores que tienen supletorio pendiente en el año "
        f"**{anio}** — una fila por colaborador y curso pendiente (cédula, nombre, área, sucursal, "
        "tema, fechas, link de Moodle y nota), con hojas separadas para Quito y TS R2."
    )

    with st.spinner("Generando reporte…"):
        contenido = api.get_reporte_pendientes_excel(anio)

    if not contenido:
        st.info("No se pudo generar el reporte. Verifica la conexión con telcou-api.")
        return

    st.download_button(
        label=f"⬇️ Descargar supletorios pendientes {anio} (.xlsx)",
        data=contenido,
        file_name=f"supletorios_pendientes_{anio}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
