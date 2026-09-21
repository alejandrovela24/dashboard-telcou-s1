import altair as alt
import pandas as pd
import streamlit as st

import api_client as api

ORDEN_MES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
}


def _pct_color(val):
    if val is None:
        return ""
    if val >= 70:
        return "background-color:#1a4731; color:#86efac;"
    if val >= 50:
        return "background-color:#713f12; color:#fde68a;"
    return "background-color:#4c0519; color:#fca5a5;"


def render_tab_analitica(anio: int) -> None:

    # ── Carga inicial de todos los cursos ────────────────────────────────
    with st.spinner("Cargando capacitaciones…"):
        todos = api.get_listado_cursos(anio=anio)

    if not todos:
        st.warning("Sin datos. Verifica que la API esté corriendo en localhost:8000")
        return

    # ── Filtros en tiempo real ───────────────────────────────────────────
    nombres_disp = sorted({d["nombre"] for d in todos})
    meses_disp   = sorted(
        {d["mes"] for d in todos if d.get("mes")},
        key=lambda m: ORDEN_MES.get(m.upper(), 99),
    )

    fc1, fc2 = st.columns([3, 1])
    with fc1:
        sel_cursos = st.multiselect(
            "Capacitaciones",
            options=nombres_disp,
            default=[],
            placeholder="Todas — escribe para buscar",
        )
    with fc2:
        sel_mes = st.selectbox("Mes", ["Todos"] + meses_disp)

    # Aplicar filtros
    data = todos
    if sel_cursos:
        data = [d for d in data if d["nombre"] in sel_cursos]
    if sel_mes != "Todos":
        data = [d for d in data if (d.get("mes") or "").upper() == sel_mes.upper()]

    if not data:
        st.info("Sin resultados para los filtros seleccionados.")
        return

    # ── Métricas globales ────────────────────────────────────────────────
    tp  = sum(d["total"]["total"]                for d in data)
    ta  = sum(d["total"]["aprobados"]            for d in data)
    tr  = sum(d["total"]["reprobados"]           for d in data)
    tfi = sum(d["total"]["faltas_injustificadas"] for d in data)
    tfj = sum(d["total"]["faltas_justificadas"]   for d in data)
    tv  = sum(d["total"]["vacaciones"]            for d in data)
    tna = sum(d["total"]["na"]                    for d in data)
    tconv = tp - tna
    pct_gbl = round(ta / tconv * 100, 1) if tconv else 0

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Capacitaciones",    len(data))
    m2.metric("Convocados",        tconv)
    m3.metric("Aprobados",         f"{ta}  ({pct_gbl}%)")
    m4.metric("Reprobados",        tr)
    m5.metric("Faltas",            tfi + tfj)
    m6.metric("Vacaciones / N/A",  f"{tv} / {tna}")

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # SECCIÓN 1 — Tabla por capacitación
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### 📋 Tabla por Capacitación")
    st.caption(
        "% Apr. = % Aprobados combinado Quito+R2 · % Apr. Q y % Apr. R2 = mismo cálculo, "
        "por regional (aprobados / convocados, sin contar NUEVO+CAMBIO+SALIO) · "
        "Inactivos = empleados con flag inactivo hoy · "
        "% Apr. muestra '—' en cursos de solo Asistencia (sin calificación numérica)"
    )

    rows_t = []
    for d in data:
        t = d["total"]
        q = d.get("quito")
        r = d.get("r2")
        rows_t.append({
            "Capacitación": d["nombre"],
            "Mes":          d["mes"] or "—",
            "Total":        t["total"],
            "Aprobados":    t["aprobados"],
            "% Apr.":       t["pct_aprobados"],
            "% Apr. Q":     q["pct_aprobados"] if q else None,
            "% Apr. R2":    r["pct_aprobados"] if r else None,
            "Reprobados":   t["reprobados"],
            "F. Injust.":   t["faltas_injustificadas"],
            "F. Just.":     t["faltas_justificadas"],
            "Vacaciones":   t["vacaciones"],
            "Asistencia":   t["asistencia"],
            "N/A":          t["na"],
            "Exonerados":   t["exonerados"],
            "Inactivos":    t["inactivos"],
            "Promedio":     t["promedio"],
        })

    df_t = pd.DataFrame(rows_t)

    def _style_t(df):
        out = pd.DataFrame("", index=df.index, columns=df.columns)
        for i in df.index:
            out.loc[i, "% Apr."]    = _pct_color(df.loc[i, "% Apr."])
            out.loc[i, "% Apr. Q"]  = _pct_color(df.loc[i, "% Apr. Q"])
            out.loc[i, "% Apr. R2"] = _pct_color(df.loc[i, "% Apr. R2"])
        return out

    st.dataframe(
        df_t.style.apply(_style_t, axis=None).format({
            "% Apr.":    lambda x: f"{x:.1f}%" if x is not None else "—",
            "% Apr. Q":  lambda x: f"{x:.1f}%" if x is not None else "—",
            "% Apr. R2": lambda x: f"{x:.1f}%" if x is not None else "—",
            "Promedio":  lambda x: f"{x:.2f}"  if x is not None else "—",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # ── Gráfico 1: % Aprobados por capacitación ──────────────────────────
    st.markdown("#### % Aprobados por capacitación (nota original)")

    vista = st.radio(
        "Vista", ["Peores 15", "Mejores 15", "Todas"],
        horizontal=True, key="vista_pct_curso",
    )
    data_con_pct = [d for d in data if d["total"]["pct_aprobados"] is not None]
    df_g1 = pd.DataFrame({
        "Capacitación": [d["nombre"] for d in data_con_pct],
        "% Aprobados": [d["total"]["pct_aprobados"] for d in data_con_pct],
    }).sort_values("% Aprobados")

    if vista == "Peores 15":
        df_plot = df_g1.head(15)
    elif vista == "Mejores 15":
        df_plot = df_g1.tail(15).sort_values("% Aprobados")
    else:
        df_plot = df_g1

    chart = alt.Chart(df_plot).mark_bar(color="#00A8A8").encode(
        x=alt.X("% Aprobados:Q"),
        y=alt.Y("Capacitación:N", sort="-x", title=None),
        tooltip=["Capacitación", "% Aprobados"],
    ).properties(height=max(28 * len(df_plot), 200))
    st.altair_chart(chart, use_container_width=True)

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # SECCIÓN 2 — Comparativa Quito vs TS R2
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### 🔄 Comparativa Quito vs TS R2")

    data_q = [d for d in data if d.get("quito")]
    data_r = [d for d in data if d.get("r2")]
    data_ambos = [d for d in data if d.get("quito") and d.get("r2")]

    # Totales por regional
    def _sum(lst, key):
        return sum(d[key] for d in lst if d is not None)

    if data_q or data_r:
        q_tot  = sum(d["quito"]["total"]    for d in data_q)
        q_apr  = sum(d["quito"]["aprobados"] for d in data_q)
        q_fal  = sum(d["quito"]["faltas_injustificadas"] + d["quito"]["faltas_justificadas"] for d in data_q)
        q_vac  = sum(d["quito"]["vacaciones"] for d in data_q)
        q_na   = sum(d["quito"]["na"]         for d in data_q)
        q_conv = q_tot - q_na
        q_pct  = round(q_apr / q_conv * 100, 1) if q_conv else 0

        r_tot  = sum(d["r2"]["total"]    for d in data_r)
        r_apr  = sum(d["r2"]["aprobados"] for d in data_r)
        r_fal  = sum(d["r2"]["faltas_injustificadas"] + d["r2"]["faltas_justificadas"] for d in data_r)
        r_vac  = sum(d["r2"]["vacaciones"] for d in data_r)
        r_na   = sum(d["r2"]["na"]         for d in data_r)
        r_conv = r_tot - r_na
        r_pct  = round(r_apr / r_conv * 100, 1) if r_conv else 0

        ka, kb, kc, kd, ke = st.columns(5)
        ka.metric("Quito % Aprobados",  f"{q_pct}%",  delta=f"{q_pct - r_pct:+.1f}% vs R2")
        kb.metric("R2 % Aprobados",     f"{r_pct}%")
        kc.metric("Faltas  Q / R2",     f"{q_fal} / {r_fal}")
        kd.metric("Vacac.  Q / R2",     f"{q_vac} / {r_vac}")
        ke.metric("N/A     Q / R2",     f"{q_na}  / {r_na}")

    # Gráficos comparativos (solo cursos que tienen ambas regionales)
    if data_ambos:
        labels = [d["nombre"][:28] for d in data_ambos]

        g1, g2 = st.columns(2)

        with g1:
            st.markdown("**% Aprobados — Quito vs R2**")
            st.bar_chart(pd.DataFrame({
                "Quito": [d["quito"]["pct_aprobados"] or 0 for d in data_ambos],
                "TS R2": [d["r2"]["pct_aprobados"]    or 0 for d in data_ambos],
            }, index=labels))

        with g2:
            st.markdown("**Faltas totales — Quito vs R2**")
            st.bar_chart(pd.DataFrame({
                "Quito": [d["quito"]["faltas_injustificadas"] + d["quito"]["faltas_justificadas"] for d in data_ambos],
                "TS R2": [d["r2"]["faltas_injustificadas"]   + d["r2"]["faltas_justificadas"]    for d in data_ambos],
            }, index=labels))

        g3, g4 = st.columns(2)

        with g3:
            st.markdown("**Vacaciones — Quito vs R2**")
            st.bar_chart(pd.DataFrame({
                "Quito": [d["quito"]["vacaciones"] for d in data_ambos],
                "TS R2": [d["r2"]["vacaciones"]    for d in data_ambos],
            }, index=labels))

        with g4:
            st.markdown("**N/A (no convocados) — Quito vs R2**")
            st.bar_chart(pd.DataFrame({
                "Quito": [d["quito"]["na"] for d in data_ambos],
                "TS R2": [d["r2"]["na"]    for d in data_ambos],
            }, index=labels))

        # Tabla comparativa
        with st.expander("Ver tabla comparativa completa", expanded=False):
            comp_rows = []
            for d in data_ambos:
                q, r = d["quito"], d["r2"]
                comp_rows.append({
                    "Capacitación":  d["nombre"],
                    "Q · Total":     q["total"],
                    "Q · % Apr.":    q["pct_aprobados"],
                    "Q · F.Inj.":    q["faltas_injustificadas"],
                    "Q · F.Just.":   q["faltas_justificadas"],
                    "Q · Vacac.":    q["vacaciones"],
                    "Q · N/A":       q["na"],
                    "R2 · Total":    r["total"],
                    "R2 · % Apr.":   r["pct_aprobados"],
                    "R2 · F.Inj.":   r["faltas_injustificadas"],
                    "R2 · F.Just.":  r["faltas_justificadas"],
                    "R2 · Vacac.":   r["vacaciones"],
                    "R2 · N/A":      r["na"],
                })
            st.dataframe(
                pd.DataFrame(comp_rows).style.format({
                    "Q · % Apr.":  lambda x: f"{x:.1f}%" if x is not None else "—",
                    "R2 · % Apr.": lambda x: f"{x:.1f}%" if x is not None else "—",
                }),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("Selecciona capacitaciones que existan en ambas regionales para ver la comparativa.")

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # SECCIÓN 3 — Resultados por ciudad (TS R2)
    # ════════════════════════════════════════════════════════════════════
    filtro_curso_ciudad = sel_cursos[0] if len(sel_cursos) == 1 else None
    if filtro_curso_ciudad:
        st.markdown(f"### 🏙️ Resultados por Ciudad — TS R2 · *{filtro_curso_ciudad}*")
        st.caption("Capacitaciones = colaboradores de esa ciudad con nota registrada en esta capacitación.")
    else:
        st.markdown("### 🏙️ Resultados por Ciudad — TS R2")
        st.caption(
            "Selecciona una sola capacitación arriba para filtrar esta sección · "
            "sin filtro, Capacitaciones = total de registros de notas de TODO el año (no empleados distintos)."
        )

    with st.spinner("Cargando ciudades…"):
        suc_data = api.get_sucursales(anio=anio, regional="TS R2", nombre=filtro_curso_ciudad)

    if suc_data:
        rows_s = []
        for s in suc_data:
            tot_s = s.get("total_capacitaciones") or 0
            apr_s = s.get("aprobados") or 0
            pct_s = round(apr_s / tot_s * 100, 1) if tot_s else None
            rows_s.append({
                "Ciudad":         s["sucursal"],
                "Empleados":      s["total_empleados"],
                "Capacitaciones": tot_s,
                "Aprobados":      apr_s,
                "% Aprobados":    pct_s,
                "Reprobados":     s.get("reprobados", 0),
                "Faltas":         s.get("faltas", 0),
                "Promedio":       s.get("promedio"),
            })

        # Gráfico
        st.bar_chart(pd.DataFrame(
            {"% Aprobados": [r["% Aprobados"] or 0 for r in rows_s]},
            index=[r["Ciudad"] for r in rows_s],
        ).sort_values("% Aprobados"), color="#00A8A8")

        # Tabla
        st.dataframe(
            pd.DataFrame(rows_s).style.format({
                "% Aprobados": lambda x: f"{x:.1f}%" if x is not None else "—",
                "Promedio":    lambda x: f"{x:.2f}"  if x is not None else "—",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin datos de ciudades para TS R2.")

    st.divider()

    # ════════════════════════════════════════════════════════════════════
    # SECCIÓN 4 — Supletorios
    # ════════════════════════════════════════════════════════════════════
    st.markdown("### 🎯 Supletorios")
    st.caption(
        "Aprobados Intento 1/2 = resultado de cada convocatoria de supletorio · "
        "Pendientes = reprobados en su último intento registrado, solo si el colaborador "
        "sigue activo hoy (si ya salió, no se cuenta como pendiente)"
    )

    q_all = [d["quito"]["supletorios"] for d in data if d.get("quito")]
    r_all = [d["r2"]["supletorios"]    for d in data if d.get("r2")]

    qs1 = sum(s["aprobados_intento1"] for s in q_all)
    qs2 = sum(s["aprobados_intento2"] for s in q_all)
    qsp = sum(s["pendientes"]         for s in q_all)
    rs1 = sum(s["aprobados_intento1"] for s in r_all)
    rs2 = sum(s["aprobados_intento2"] for s in r_all)
    rsp = sum(s["pendientes"]         for s in r_all)

    st.markdown("**Quito**")
    q1, q2, q3 = st.columns(3)
    q1.metric("Aprobados Intento 1", qs1)
    q2.metric("Aprobados Intento 2", qs2)
    q3.metric("Pendientes",          qsp)

    st.markdown("**TS R2**")
    r1, r2, r3 = st.columns(3)
    r1.metric("Aprobados Intento 1", rs1)
    r2.metric("Aprobados Intento 2", rs2)
    r3.metric("Pendientes",          rsp)

    def _sup_o_cero(bloque):
        s = (bloque or {}).get("supletorios") or {}
        return {
            "Aprobados Intento 1": s.get("aprobados_intento1", 0),
            "Aprobados Intento 2": s.get("aprobados_intento2", 0),
            "Pendientes":          s.get("pendientes", 0),
        }

    rows_sup = []
    for d in data:
        q_sup = _sup_o_cero(d.get("quito"))
        r_sup = _sup_o_cero(d.get("r2"))
        if sum(q_sup.values()) + sum(r_sup.values()) == 0:
            continue
        rows_sup.append({
            "Capacitación":     d["nombre"],
            "Mes":              d["mes"] or "—",
            "Q · Aprob. Int.1": q_sup["Aprobados Intento 1"],
            "Q · Aprob. Int.2": q_sup["Aprobados Intento 2"],
            "Q · Pendientes":   q_sup["Pendientes"],
            "R2 · Aprob. Int.1": r_sup["Aprobados Intento 1"],
            "R2 · Aprob. Int.2": r_sup["Aprobados Intento 2"],
            "R2 · Pendientes":   r_sup["Pendientes"],
        })

    if rows_sup:
        st.dataframe(
            pd.DataFrame(rows_sup),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Sin supletorios registrados para los filtros seleccionados.")

    # ── Detalle de pendientes por empleado ───────────────────────────────
    st.markdown("#### 🔍 Detalle de Pendientes por Colaborador")
    st.caption(
        "Listado individual (no solo conteos) de colaboradores activos con supletorio pendiente · "
        "usa el filtro de Capacitaciones de arriba para acotar a un solo curso"
    )

    regional_sel = st.selectbox("Regional", ["Todas", "Quito", "TS R2"], key="pend_regional")

    with st.spinner("Cargando detalle de pendientes…"):
        pendientes = api.get_supletorios_pendientes(
            anio=anio,
            regional=None if regional_sel == "Todas" else regional_sel,
            curso=filtro_curso_ciudad,
        )

    if pendientes:
        # "0" solo significa que no hay ningún supletorio registrado para ese
        # curso — no prueba que la persona nunca lo haya rendido, solo que no
        # está registrado en el sistema.
        INTENTO_LABEL = {
            0: "Pendiente (sin intento registrado)",
            1: "Pendiente (reprobó Intento 1)",
            2: "Pendiente (reprobó Intento 2)",
        }
        rows_det = [{
            "Cédula":        p["cedula"],
            "Nombre":        p["nombre"],
            "Regional":      p["regional"],
            "Sucursal":      p.get("sucursal") or "—",
            "Área":          p.get("area") or "—",
            "Curso":         p["curso"],
            "Mes":           p.get("mes") or "—",
            "Situación":     INTENTO_LABEL.get(p.get("ultimo_intento", 0), str(p.get("ultimo_intento"))),
            "Última Nota":   p.get("ultima_nota"),
            "Último Estado": p.get("ultimo_estado"),
        } for p in pendientes]

        df_det = pd.DataFrame(rows_det)
        st.caption(f"{len(df_det)} pendientes")

        def _style_det(df):
            def row(r):
                color = (
                    "rgba(239,68,68,0.10)" if r["Último Estado"] == "REPROBADO" else
                    "rgba(234,179,8,0.10)" if r["Último Estado"] == "FALTA_INJUSTIFICADA" else ""
                )
                return [f"background-color:{color};" if color else ""] * len(r)
            return df.style.apply(row, axis=1)

        st.dataframe(
            _style_det(df_det).format({"Última Nota": lambda x: f"{x:.2f}" if x is not None else "—"}),
            use_container_width=True,
            hide_index=True,
            height=min(35 * (len(df_det) + 1), 500),
        )
    else:
        st.info("Sin pendientes para los filtros seleccionados.")
