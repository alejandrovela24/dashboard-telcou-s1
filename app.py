import streamlit as st

from ui.styles import inject_styles
from ui.colaboradores import render_tab_colaboradores
from ui.analitica import render_tab_analitica
from ui.convocatoria import render_tab_convocatoria

st.set_page_config(
    page_title="Dashboard Capacitación TELCOU",
    page_icon="📊",
    layout="wide",
)

inject_styles()

SECCIONES = {
    "👥 Colaboradores": render_tab_colaboradores,
    "📈 Analítica": render_tab_analitica,
    "📧 Convocatoria": render_tab_convocatoria,
}

# ── Sidebar: navegación ──
with st.sidebar:
    st.markdown("# TELCOU")
    st.markdown("### Dashboard Capacitación")
    st.divider()

    seccion = st.radio("Navegación", options=list(SECCIONES.keys()), label_visibility="collapsed")

    st.divider()
    st.caption("Fuente: telcou-api · PostgreSQL")

    if st.button("🔄 Limpiar caché", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Header ──
st.title("📊 Dashboard Capacitación Técnica TELCOU")

# ── Selector de año (arriba del contenido) ──
AÑOS_DISPONIBLES = [2026, 2025, 2024, 2023]
anio = st.radio(
    "Año", options=AÑOS_DISPONIBLES, horizontal=True, label_visibility="collapsed",
)
st.caption(f"Año **{anio}** · Datos en tiempo real desde telcou-api")

st.divider()

SECCIONES[seccion](anio)
