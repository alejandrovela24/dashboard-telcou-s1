import pandas as pd
import streamlit as st

import api_client as api
from ui.styles import ESTADO_COLORS, badge, style_notas_df

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# Mantener en sync con AÑOS_DISPONIBLES de app.py — no se importa directo para
# evitar un ciclo de imports (app.py ya importa render_tab_colaboradores).
AÑOS_DISPONIBLES = [2026, 2025, 2024, 2023]

ESTADOS_INASISTENCIA = {"FALTA_INJUSTIFICADA", "FALTA_JUSTIFICADA", "VACACIONES"}
NECESITA_SUPLETORIO = {"REPROBADO", "FALTA_INJUSTIFICADA"}

ESTADO_TIPO_LABEL = {
    "FALTA_INJUSTIFICADA": "F · Falta injustificada",
    "FALTA_JUSTIFICADA":   "J · Falta justificada",
    "VACACIONES":          "V · Vacaciones",
}


def render_tab_colaboradores(anio: int) -> None:
    with st.spinner("Cargando empleados..."):
        # Sin filtro de año — primero eliges a la persona, el año se elige
        # despues (si se filtrara por año aca, alguien sin notas en el año
        # activo del sidebar ni siquiera aparecería para buscarlo).
        empleados = api.get_empleados()

    if not empleados:
        st.warning("No se encontraron empleados. Verifica que telcou-api esté corriendo.")
        return

    nombres = sorted({e["nombre"] for e in empleados if e.get("nombre")})

    with st.form("form_colab"):
        seleccion = st.multiselect(
            "Colaborador(es) — escribe para filtrar",
            options=nombres,
            default=[],
            placeholder="Empieza a escribir…",
        )
        c1, c2 = st.columns([1, 3])
        with c1:
            indice_default = AÑOS_DISPONIBLES.index(anio) if anio in AÑOS_DISPONIBLES else 0
            anio_sel = st.selectbox("Año", options=AÑOS_DISPONIBLES, index=indice_default)
        with c2:
            meses_sel = st.multiselect("Mes(es)", options=MESES, default=MESES)
        st.form_submit_button("Aplicar", use_container_width=True)

    if not seleccion:
        st.info("Selecciona uno o más colaboradores para ver su información.")
        return

    lookup = {e["nombre"]: e for e in empleados}

    for nombre in seleccion:
        emp = lookup.get(nombre)
        if not emp:
            st.warning(f"No encontrado: {nombre}")
            continue
        _render_empleado(emp, anio_sel, meses_sel)
        st.divider()


def _render_empleado(emp: dict, anio: int, meses_sel: list[str]) -> None:
    cedula = emp["cedula"]
    estado_texto = "INACTIVO" if emp.get("inactivo") else "ACTIVO"
    regional = emp.get("regional", {}).get("nombre", "—")
    color_estado = "#ef4444" if emp.get("inactivo") else "#10b981"

    # ── Encabezado ──
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader(f"👤 {emp['nombre']}")
        st.markdown(
            f'Estado: {badge(estado_texto if not emp.get("inactivo") else "INACTIVO")} '
            f'&nbsp; Regional: **{regional}**',
            unsafe_allow_html=True,
        )
        st.write(f"Área: **{emp.get('area') or '—'}**")
        if emp.get("tipo_movimiento"):
            st.caption(f"Tipo de movimiento: {emp['tipo_movimiento']}")
    with c2:
        st.write(f"Cédula: **{cedula}**")
        st.write(f"Jefe: **{emp.get('jefe_inmediato') or '—'}**")

    # ── Resumen ──
    with st.spinner("Cargando resumen..."):
        resumen = api.get_resumen_empleado(cedula, anio)

    if resumen:
        m1, m2, m3, m4, m5 = st.columns(5)
        prom = resumen.get("promedio")
        m1.metric("Total Capacitaciones", resumen.get("total_capacitaciones", 0))
        m2.metric("Promedio", f"{float(prom):.2f}" if prom is not None else "—")
        m3.metric("Faltas (F)", resumen.get("faltas_injustificadas", 0))
        m4.metric("Justificadas (J)", resumen.get("faltas_justificadas", 0))
        m5.metric("Supletorios Rendidos", resumen.get("supletorios", 0))

    # ── Notas del período ──
    with st.spinner("Cargando notas..."):
        notas = api.get_notas_empleado(cedula, anio=anio)

    if meses_sel:
        notas = [n for n in notas if (n.get("mes") or "").capitalize() in meses_sel or n.get("mes") is None]

    notas_reg = [n for n in notas if n.get("tipo") == "REGULAR"]

    # ── Inasistencias / Vacaciones ──
    st.markdown("### 📌 Inasistencias y Vacaciones")
    inasis = [n for n in notas_reg if n.get("estado") in ESTADOS_INASISTENCIA]

    if inasis:
        rows = []
        for n in inasis:
            rows.append({
                "Código":      n["curso_codigo"],
                "Curso":       n["curso_nombre"],
                "Mes":         n.get("mes") or "—",
                "Tipo":        ESTADO_TIPO_LABEL.get(n["estado"], n["estado"]),
                "Estado":      n["estado"],
                "Observación": n.get("observacion") or "—",
            })
        df_inasis = pd.DataFrame(rows)

        def _style_inasis(df):
            def row(r):
                est = r["Estado"]
                bg, _ = ESTADO_COLORS.get(est, ("", ""))
                return [f"background-color:{bg};" if bg else ""] * len(r)
            return df.style.apply(row, axis=1)

        f_cols = ["Código", "Curso", "Mes", "Tipo", "Observación"]
        st.dataframe(_style_inasis(df_inasis[f_cols + ["Estado"]]).hide(axis="columns", subset=["Estado"]),
                     use_container_width=True)
    else:
        st.info("Sin inasistencias ni vacaciones registradas para los filtros seleccionados.")

    # ── Trazabilidad Supletorios ──
    st.markdown("### 🎯 Trazabilidad de Supletorios")
    with st.spinner("Cargando trazabilidad..."):
        trazabilidad = api.get_trazabilidad_empleado(cedula, anio=anio)

    if trazabilidad:
        originales_map = {n["id"]: n for n in trazabilidad if n.get("tipo") == "REGULAR"}
        suples_por_original: dict[int, list[dict]] = {}
        for n in trazabilidad:
            if n.get("tipo") == "SUPLETORIO":
                oid = n.get("nota_original_id")
                if oid is not None:
                    suples_por_original.setdefault(oid, []).append(n)
        for lst in suples_por_original.values():
            lst.sort(key=lambda n: n.get("convocatoria", 1))

        def _fmt(nota_dict: dict | None) -> str:
            if nota_dict is None:
                return "—"
            v = nota_dict.get("valor")
            return f"{float(v):.2f}" if v is not None else nota_dict.get("estado", "—")

        rows = []
        for orig_id, orig_nota in sorted(
            originales_map.items(),
            key=lambda x: x[1].get("curso_nombre", ""),
        ):
            suples = suples_por_original.get(orig_id, [])
            if not suples:
                continue
            s1 = suples[0] if len(suples) > 0 else None
            s2 = suples[1] if len(suples) > 1 else None
            final = suples[-1]
            rows.append({
                "Curso":        orig_nota.get("curso_nombre", "—"),
                "Nota":         _fmt(orig_nota),
                "Supletorio 1": _fmt(s1),
                "Supletorio 2": _fmt(s2),
                "Resultado":    final.get("estado", "—"),
                # hidden: estados para colorear cada celda
                "_e_reg":  orig_nota.get("estado", ""),
                "_e_s1":   s1.get("estado", "") if s1 else "",
                "_e_s2":   s2.get("estado", "") if s2 else "",
                "_e_fin":  final.get("estado", ""),
            })

        if rows:
            aprobados = sum(1 for r in rows if r["_e_fin"] == "APROBADO")
            k1, k2, k3 = st.columns(3)
            k1.metric("Cursos con Supletorio", len(rows))
            k2.metric("Aprobados (resultado final)", aprobados)
            k3.metric("No aprobados", len(rows) - aprobados)

            df_t = pd.DataFrame(rows).reset_index(drop=True)
            # Separate: visible cols vs estado cols (for styling only)
            VIS_COLS = ["Curso", "Nota", "Supletorio 1", "Supletorio 2", "Resultado"]
            df_vis = df_t[VIS_COLS]
            estados = df_t[["_e_reg", "_e_s1", "_e_s2", "_e_fin"]]

            _COL_EST = [
                ("Nota",         "_e_reg"),
                ("Supletorio 1", "_e_s1"),
                ("Supletorio 2", "_e_s2"),
                ("Resultado",    "_e_fin"),
            ]

            def _style_traza(df):
                result = pd.DataFrame("", index=df.index, columns=df.columns)
                for col, est_key in _COL_EST:
                    for i in df.index:
                        bg, _ = ESTADO_COLORS.get(estados.loc[i, est_key], ("", ""))
                        if bg:
                            result.loc[i, col] = f"background-color:{bg};"
                return result

            st.dataframe(
                df_vis.style.apply(_style_traza, axis=None),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Sin supletorios registrados.")
    else:
        st.info("Sin supletorios registrados.")

    # ── Pendientes de Supletorio ──
    st.markdown("### ⏳ Pendientes de Supletorio")
    st.caption(
        "Cursos reprobados o con falta injustificada donde el empleado **todavía no ha rendido "
        "ningún supletorio** — a diferencia de Trazabilidad (que solo muestra intentos ya hechos)."
    )
    if emp.get("inactivo"):
        st.info("Empleado inactivo — no aplica.")
    else:
        ids_con_supletorio = {
            n["nota_original_id"] for n in notas
            if n.get("tipo") == "SUPLETORIO" and n.get("nota_original_id") is not None
        }
        pendientes = [
            n for n in notas_reg
            if n.get("estado") in NECESITA_SUPLETORIO and n["id"] not in ids_con_supletorio
        ]
        if pendientes:
            rows = []
            for n in pendientes:
                rows.append({
                    "Código": n["curso_codigo"],
                    "Curso":  n["curso_nombre"],
                    "Mes":    n.get("mes") or "—",
                    "Nota":   float(n["valor"]) if n.get("valor") is not None else None,
                    "Estado": n.get("estado", ""),
                })
            df_pend = pd.DataFrame(rows)
            st.dataframe(
                style_notas_df(df_pend).format({"Nota": lambda x: f"{x:.2f}" if x is not None else "—"}),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Sin supletorios pendientes por rendir.")

    # ── Todas las notas regulares ──
    with st.expander("📋 Ver todas las notas del período"):
        if notas_reg:
            rows = []
            for n in notas_reg:
                rows.append({
                    "Código":  n["curso_codigo"],
                    "Curso":   n["curso_nombre"],
                    "Mes":     n.get("mes") or "—",
                    "Nota":    float(n["valor"]) if n.get("valor") is not None else None,
                    "Estado":  n.get("estado", ""),
                    "Obs":     n.get("observacion") or "—",
                })
            df_notas = pd.DataFrame(rows)
            st.dataframe(
                style_notas_df(df_notas).format({"Nota": lambda x: f"{x:.2f}" if x is not None else "—"}),
                use_container_width=True,
            )
        else:
            st.info("Sin notas regulares para este período.")
