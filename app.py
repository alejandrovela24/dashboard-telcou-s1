import streamlit as st

from ui.styles import inject_styles
from ui.colaboradores import render_tab_colaboradores
from ui.areas import render_tab_areas
from ui.analitica import render_tab_analitica
from ui.convocatoria import render_tab_convocatoria

st.set_page_config(
    page_title="Dashboard Capacitación TELCOU",
    page_icon="📊",
    layout="wide",
)

inject_styles()

# ── Sidebar ──
with st.sidebar:
    st.markdown("# TELCOU")
    st.markdown("### Dashboard Capacitación")
    st.divider()

    anio = st.selectbox("Año", options=[2026, 2025, 2024, 2023], index=0)

    st.divider()
    st.caption("Fuente: telcou-api · PostgreSQL")

    if st.button("🔄 Limpiar caché", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Header ──
st.title("📊 Dashboard Capacitación Técnica TELCOU")
st.caption(f"Año **{anio}** · Datos en tiempo real desde telcou-api")

# ── Tabs ──
tab_colab, tab_area, tab_analitica, tab_convocatoria = st.tabs(
    ["👥 Colaboradores", "🏢 Áreas", "📈 Analítica", "📧 Convocatoria"]
)

with tab_colab:
    render_tab_colaboradores(anio)

with tab_area:
    render_tab_areas(anio)

with tab_analitica:
    render_tab_analitica(anio)

with tab_convocatoria:
    render_tab_convocatoria(anio)
