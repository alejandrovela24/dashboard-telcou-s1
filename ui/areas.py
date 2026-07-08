import pandas as pd
import streamlit as st

import api_client as api


def render_tab_areas(anio: int) -> None:
    # ── Filtros ──
    with st.form("form_area"):
        c1, c2 = st.columns([2, 1])
        with c1:
            regional_filtro = st.text_input(
                "Filtrar por regional (opcional)",
                placeholder="Ej: Quito, TS R2 — vacío = todas",
            )
        with c2:
            regional_suc = st.text_input(
                "Regional para Sucursales",
                value="TS R2",
            )
        st.form_submit_button("Aplicar", use_container_width=True)

    # ── Por Área ──
    st.markdown("### 🏢 Estadísticas por Área")
    with st.spinner("Cargando áreas..."):
        areas_data = api.get_areas(anio=anio, regional=regional_filtro or None)

    if areas_data:
        df_areas = pd.DataFrame(areas_data)
        total_emp  = int(df_areas["total_empleados"].sum())
        total_caps = int(df_areas["total_capacitaciones"].sum())
        prom_gl    = df_areas["promedio"].mean(skipna=True)

        k1, k2, k3 = st.columns(3)
        k1.metric("Total Empleados", total_emp)
        k2.metric("Total Capacitaciones", total_caps)
        k3.metric("Promedio Global", f"{prom_gl:.2f}" if pd.notna(prom_gl) else "—")

        df_show = df_areas.rename(columns={
            "area":                "Área",
            "promedio":            "Promedio",
            "total_empleados":     "Empleados",
            "total_capacitaciones":"Capacitaciones",
        })[["Área", "Empleados", "Capacitaciones", "Promedio"]]
        df_show["Promedio"] = df_show["Promedio"].apply(
            lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
        )
        st.dataframe(df_show.sort_values("Área").reset_index(drop=True), use_container_width=True)
    else:
        st.info("Sin datos de áreas para los filtros seleccionados.")

    st.divider()

    # ── Por Regional ──
    st.markdown("### 🗺️ Estadísticas por Regional")
    with st.spinner("Cargando regionales..."):
        reg_data = api.get_regionales(anio=anio)

    if reg_data:
        df_reg = pd.DataFrame(reg_data).rename(columns={
            "regional":            "Regional",
            "promedio":            "Promedio",
            "total_empleados":     "Empleados",
            "total_capacitaciones":"Capacitaciones",
        })[["Regional", "Empleados", "Capacitaciones", "Promedio"]]
        df_reg["Promedio"] = df_reg["Promedio"].apply(
            lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
        )
        st.dataframe(df_reg.reset_index(drop=True), use_container_width=True)
    else:
        st.info("Sin datos de regionales.")

    st.divider()

    # ── Por Sucursal ──
    st.markdown(f"### 🏗️ Estadísticas por Sucursal — *{regional_suc or 'TS R2'}*")
    with st.spinner("Cargando sucursales..."):
        suc_data = api.get_sucursales(anio=anio, regional=regional_suc or "TS R2")

    if suc_data:
        df_suc = pd.DataFrame(suc_data).rename(columns={
            "sucursal":            "Sucursal",
            "total_empleados":     "Empleados",
            "total_capacitaciones":"Capacitaciones",
            "promedio":            "Promedio",
            "aprobados":           "Aprobados",
            "reprobados":          "Reprobados",
            "faltas":              "Faltas",
        })[["Sucursal", "Empleados", "Capacitaciones", "Promedio", "Aprobados", "Reprobados", "Faltas"]]
        df_suc["Promedio"] = df_suc["Promedio"].apply(
            lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
        )

        t1, t2, t3 = st.columns(3)
        t1.metric("Total Sucursales", len(df_suc))
        t2.metric("Total Aprobados", int(df_suc["Aprobados"].sum()) if "Aprobados" in df_suc else "—")
        t3.metric("Total Faltas", int(df_suc["Faltas"].sum()) if "Faltas" in df_suc else "—")

        st.dataframe(df_suc.reset_index(drop=True), use_container_width=True)
    else:
        st.info(f"Sin datos de sucursales para la regional '{regional_suc or 'TS R2'}'.")
