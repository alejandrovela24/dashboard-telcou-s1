# ui/convocatoria.py
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import api_client as api

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
# Solo para el selector de Convocatoria: "Virtual" no es un dia (sede=Virtual
# siempre tiene dia=None, disponible toda la semana) — se agrega aca nada mas
# porque es la unica forma de que esa gente aparezca en el preview/envio.
DIAS_CONVOCATORIA = DIAS + ["VIRTUAL"]


def _lunes_de_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _form_cambiar_dia(cedula: str, nombre: str, dia_sugerido: str, key_prefix: str) -> None:
    with st.form(f"form_dia_{key_prefix}_{cedula}"):
        st.write(f"**Cambiar día de {nombre}**")
        dia_nuevo = st.selectbox("Día nuevo", DIAS, index=DIAS.index(dia_sugerido) if dia_sugerido in DIAS else 0)
        tipo = st.radio("Tipo de cambio", ["SEMANAL", "PERMANENTE"], horizontal=True,
                         help="SEMANAL = solo esta semana, vuelve a su día normal después. PERMANENTE = cambia su día de base.")
        semana_inicio = None
        if tipo == "SEMANAL":
            semana_sel = st.date_input("Semana (cualquier día de esa semana)", value=date.today())
            semana_inicio = _lunes_de_semana(semana_sel).isoformat()
        motivo = st.text_area("Motivo", placeholder="Ej: no pudo asistir el lunes por...")
        editado_por = st.text_input("Editado por (opcional)")
        guardar = st.form_submit_button("Guardar cambio")

        if guardar:
            if not motivo.strip():
                st.error("El motivo es obligatorio.")
                return
            resultado = api.cambiar_dia_empleado(
                cedula=cedula, dia_nuevo=dia_nuevo, tipo=tipo, motivo=motivo,
                semana_inicio=semana_inicio, editado_por=editado_por or None,
            )
            if resultado:
                st.success(f"Día actualizado a {dia_nuevo} ({tipo}).")
                st.rerun()


def render_tab_convocatoria(anio: int) -> None:
    # Convocatoria es un flujo semanal, no anual: el año efectivo sale de la
    # "Semana" seleccionada abajo, no del selector de Año global (ese solo
    # tiene sentido para Colaboradores/Analítica). El parámetro `anio` se
    # ignora a propósito para mantener la firma uniforme con las otras
    # secciones en app.py.
    st.title("📧 Convocatoria a Supletorios")

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        regional = st.selectbox("Regional", ["TS R2", "Quito"], key="conv_regional")
    with fc2:
        dia = st.selectbox(
            "Día", DIAS_CONVOCATORIA, key="conv_dia",
            help="'Virtual' agrupa a quienes tienen esa modalidad — están disponibles toda la "
                 "semana, no un día fijo.",
        )
    with fc3:
        # default = lunes de LA PROXIMA semana, nunca "hoy" — un default de
        # "hoy" hace que si nadie toca este campo, la convocatoria salga con
        # fechas de la semana actual (o incluso de hoy mismo) en vez de una
        # fecha futura para que la gente se prepare. Bug real: paso una vez.
        semana_sel = st.date_input(
            "Semana", value=_lunes_de_semana(date.today()) + timedelta(days=7), key="conv_semana",
            help="Por defecto es la PRÓXIMA semana, no la actual — revisa la fecha antes de enviar.",
        )

    semana_inicio = _lunes_de_semana(semana_sel)
    anio_efectivo = semana_inicio.year

    if st.button("Cargar convocatoria del día", type="primary"):
        st.session_state["conv_cargado"] = True

    if not st.session_state.get("conv_cargado"):
        st.info("Selecciona los filtros y presiona 'Cargar convocatoria del día'.")
        return

    with st.spinner("Cargando convocatoria…"):
        preview = api.get_convocatoria_preview(dia=dia, regional=regional, semana=semana_inicio.isoformat())

    st.markdown(f"### Convocados — {dia}, semana del {semana_inicio.strftime('%d/%m/%Y')}")

    if not preview:
        if api.get_regional_dia_configurado(regional):
            st.info("Nadie tiene día efectivo = " + dia + " en " + regional + " para esta semana.")
        else:
            st.warning(
                f"⚠️ **{regional}** todavía no tiene cargado el día de capacitación por colaborador "
                "— por eso no aparece nadie convocado en ningún día para esta regional. No es que "
                "no haya pendientes (si los hay, se pueden agregar manualmente con el buscador "
                "'Agregar por nombre' de abajo)."
            )
        seleccionados: list[str] = []
    else:
        seleccionados = _seccion_tabla_convocados(preview, dia)

    st.divider()
    _seccion_agregar_por_nombre(anio_efectivo, regional, dia)
    st.divider()
    _seccion_envio(preview, semana_inicio, seleccionados, regional, dia)
    st.divider()
    _seccion_resumen_consolidado(semana_inicio, dia)
    st.divider()
    _seccion_historial_envios(anio_efectivo, regional)
    st.divider()
    _seccion_emails_archivados()


def _seccion_tabla_convocados(preview: list[dict], dia: str) -> list[str]:
    """Tabla única de convocados con checkbox 'Enviar' integrado — reemplaza
    la lista de solo-lectura + la lista separada de checkboxes que había antes.
    Devuelve las cédulas marcadas para enviar."""
    st.session_state.setdefault("conv_select_default", True)
    st.session_state.setdefault("conv_editor_version", 0)

    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("☑️ Seleccionar todos"):
        st.session_state["conv_select_default"] = True
        st.session_state["conv_editor_version"] += 1
    if b2.button("☐ Ninguno"):
        st.session_state["conv_select_default"] = False
        st.session_state["conv_editor_version"] += 1

    default_marcado = st.session_state["conv_select_default"]

    rows = []
    for p in preview:
        cursos_txt = ", ".join(
            f"{c['curso']} (nota: {c['nota'] if c['nota'] is not None else '—'})"
            for c in p["cursos_pendientes"]
        )
        rows.append({
            "Enviar":             default_marcado and p["tiene_correo"],
            "Nombre":             p["nombre"],
            "Cursos pendientes":  cursos_txt,
            "Correo":             "✅" if p["tiene_correo"] else "❌ sin correo",
            "Ya enviado":         "📨" if p["ya_enviado"] else "—",
            "Cédula":             p["cedula"],
        })
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        key=f"conv_editor_{st.session_state['conv_editor_version']}",
        use_container_width=True,
        hide_index=True,
        disabled=["Nombre", "Cursos pendientes", "Correo", "Ya enviado", "Cédula"],
        column_config={
            "Enviar": st.column_config.CheckboxColumn("Enviar", help="Desmarca para excluir del envío"),
        },
    )

    st.markdown("#### Cambiar día de un convocado")
    nombres_map = {p["nombre"]: p["cedula"] for p in preview}
    nombre_sel = st.selectbox("Convocado", ["—"] + sorted(nombres_map.keys()), key="conv_cambiar_dia_select")
    if nombre_sel != "—":
        _form_cambiar_dia(nombres_map[nombre_sel], nombre_sel, dia, "principal")

    return edited[edited["Enviar"]]["Cédula"].tolist()


def _seccion_agregar_por_nombre(anio: int, regional: str, dia: str) -> None:
    st.markdown("### 🔎 Agregar por nombre")
    st.caption("Busca solo entre empleados con supletorio pendiente, de cualquier día actual. "
               "Al cambiar su día a este, vuelve a cargar la convocatoria arriba para verlo en la tabla.")
    nombre_busqueda = st.text_input("Nombre", key="conv_buscar_nombre", placeholder="Escribe al menos 2 letras…")

    if len(nombre_busqueda.strip()) < 2:
        return

    with st.spinner("Buscando…"):
        resultados = api.buscar_supletorios_pendientes(nombre=nombre_busqueda, anio=anio, regional=regional)

    if not resultados:
        st.info("Sin resultados.")
        return

    vistos = set()
    for r in resultados:
        if r["cedula"] in vistos:
            continue
        vistos.add(r["cedula"])
        with st.expander(f"{r['nombre']} — {r['cedula']}"):
            _form_cambiar_dia(r["cedula"], r["nombre"], dia, "buscar")


def _seccion_envio(
    preview: list[dict], semana_inicio, cedulas_seleccionadas: list[str],
    regional: str, dia: str,
) -> None:
    st.markdown("### ✉️ Envío de convocatoria")

    if not preview:
        st.info("No hay convocados cargados para enviar.")
        return

    semana_fin = semana_inicio + timedelta(days=4)
    st.warning(
        f"📅 Esta convocatoria se enviará con fecha de la semana del "
        f"**{semana_inicio.strftime('%d/%m/%Y')} al {semana_fin.strftime('%d/%m/%Y')}** "
        f"— verifica que sea la semana correcta antes de confirmar el envío."
    )

    st.caption(f"{len(cedulas_seleccionadas)} seleccionados en la columna 'Enviar' de la tabla de arriba.")

    modo_prueba = st.toggle("Modo prueba", value=True,
                             help="Mientras esté activo, TODOS los correos de esta tanda se redirigen al correo de prueba.")
    correo_prueba = None
    if modo_prueba:
        correo_prueba = st.text_input("Correo de prueba", placeholder="tu_correo@telconet.ec")

    enviar_resumen_ejecutivo = st.checkbox(
        "Enviar resumen ejecutivo individual a coordinadores",
        value=False,
        help="Déjalo desactivado si vas a usar 'Enviar resumen consolidado' (recomendado) más "
             "abajo después de enviar Quito y TS R2 — activarlo aquí también duplica el aviso "
             "a la jefatura.",
    )

    if st.button(f"Confirmar y enviar a los {len(cedulas_seleccionadas)} seleccionados", type="primary"):
        if not cedulas_seleccionadas:
            st.error("Selecciona al menos un destinatario en la tabla de arriba.")
            return
        if modo_prueba and not correo_prueba:
            st.error("Ingresa un correo de prueba mientras el modo prueba esté activo.")
            return

        with st.spinner("Enviando…"):
            resultado = api.enviar_convocatoria(
                cedulas=cedulas_seleccionadas,
                semana=semana_inicio.isoformat(),
                modo_prueba=modo_prueba,
                correo_prueba=correo_prueba,
                regional=regional,
                dia=dia,
                enviar_resumen_ejecutivo=enviar_resumen_ejecutivo,
            )

        if resultado:
            sufijo = " (modo prueba — redirigido a correo de prueba)" if modo_prueba else ""
            st.success(f"✅ Enviados: {len(resultado['enviados'])}{sufijo}")
            if resultado["fallidos"]:
                st.error("❌ Fallidos:")
                for f in resultado["fallidos"]:
                    st.write(f"- {f['nombre'] or f['cedula']}: {f['detalle']}")
            if resultado.get("recopilatorios_enviados"):
                st.caption(f"📋 Recopilatorio enviado a {len(resultado['recopilatorios_enviados'])} jefe(s) inmediato(s).")
            if resultado.get("resumen_ejecutivo_enviado"):
                st.caption("📊 Resumen ejecutivo enviado a los coordinadores.")


def _seccion_resumen_consolidado(semana_inicio: date, dia: str) -> None:
    st.markdown("### 📊 Enviar resumen consolidado a la jefatura")
    st.caption(
        "Un solo correo a la jefatura con dos secciones — UIO (Quito) y TS R2 — agregando "
        "los envíos ya hechos esa semana. Úsalo una sola vez, después de haber enviado Quito "
        "y TS R2 por separado (con 'Enviar resumen ejecutivo individual' desactivado arriba)."
    )
    semana_fin_c = semana_inicio + timedelta(days=4)
    st.caption(
        f"📅 Semana: **{semana_inicio.strftime('%d/%m/%Y')} al {semana_fin_c.strftime('%d/%m/%Y')}** "
        "— debe ser la misma semana que usaste en los envíos de arriba."
    )

    modo_prueba_c = st.toggle(
        "Modo prueba", value=True, key="conv_consolidado_modo_prueba",
        help="Mientras esté activo, el correo se redirige al correo de prueba.",
    )
    correo_prueba_c = None
    if modo_prueba_c:
        correo_prueba_c = st.text_input(
            "Correo de prueba", key="conv_consolidado_correo_prueba",
            placeholder="tu_correo@telconet.ec",
        )

    if st.button("Enviar resumen consolidado", key="conv_consolidado_btn"):
        if modo_prueba_c and not correo_prueba_c:
            st.error("Ingresa un correo de prueba mientras el modo prueba esté activo.")
            return

        with st.spinner("Enviando resumen consolidado…"):
            resultado = api.enviar_resumen_consolidado(
                semana=semana_inicio.isoformat(),
                dia=dia,
                modo_prueba=modo_prueba_c,
                correo_prueba=correo_prueba_c,
            )

        if resultado:
            sufijo = " (modo prueba — redirigido a correo de prueba)" if modo_prueba_c else ""
            st.success(
                f"✅ Resumen consolidado enviado{sufijo}: "
                f"{resultado['quito_count']} de Quito, {resultado['ts_r2_count']} de TS R2."
            )


def _seccion_historial_envios(anio: int, regional: str) -> None:
    st.markdown("### 🗂️ Historial de envíos")
    st.caption("Auditoría de convocatorias ya enviadas (incluye envíos en modo prueba).")

    hf1, hf2 = st.columns(2)
    with hf1:
        filtro_regional = st.selectbox(
            "Regional", ["Todas", "TS R2", "Quito"], key="conv_hist_regional",
        )
    with hf2:
        filtro_modo = st.selectbox(
            "Modo", ["Todos", "Solo reales", "Solo prueba"], key="conv_hist_modo",
        )

    if not st.checkbox("Mostrar historial", key="conv_hist_mostrar"):
        return

    modo_prueba_filtro = None
    if filtro_modo == "Solo reales":
        modo_prueba_filtro = False
    elif filtro_modo == "Solo prueba":
        modo_prueba_filtro = True

    with st.spinner("Cargando historial…"):
        historial = api.get_envios_convocatoria(
            anio=anio,
            regional=None if filtro_regional == "Todas" else filtro_regional,
            modo_prueba=modo_prueba_filtro,
        )

    if not historial:
        st.info("Sin envíos registrados para estos filtros.")
        return

    df = pd.DataFrame([{
        "Fecha":      h["fecha_envio"],
        "Nombre":     h["nombre"],
        "Cédula":     h["cedula"],
        "Regional":   h["regional"],
        "Curso":      h["curso"],
        "Modo":       "🧪 Prueba" if h["modo_prueba"] else "✅ Real",
        "Enviado por": h["enviado_por"] or "—",
    } for h in historial])
    st.dataframe(df, use_container_width=True, hide_index=True)


_TIPOS_EMAIL = ["INDIVIDUAL", "RECOPILATORIO", "RESUMEN_EJECUTIVO", "RESUMEN_CONSOLIDADO"]


def _nombre_archivo_email(email: dict) -> str:
    """Espeja el nombre que arma el backend (apellidos y nombres del
    colaborador cuando el correo esta ligado a uno; si no, el tipo)."""
    import re
    base = email["empleado_nombre"] or email["tipo"]
    limpio = re.sub(r'[\\/:*?"<>|]', "", base).strip()
    slug = re.sub(r"\s+", "_", limpio)
    return f"{slug}_{email['tipo']}_{email['id']}.html"


def _seccion_emails_archivados() -> None:
    st.markdown("### 📬 Correos archivados")
    st.caption(
        "El contenido HTML real de cada correo que el sistema ya envió — individual a "
        "colaborador, recopilatorio a jefe, y resúmenes ejecutivo/consolidado. Búscalo y "
        "descárgalo (uno o varios a la vez) para ver exactamente qué se mandó."
    )

    ef1, ef2, ef3, ef4 = st.columns(4)
    with ef1:
        filtro_tipo = st.selectbox("Tipo", ["Todos"] + _TIPOS_EMAIL, key="conv_email_tipo")
    with ef2:
        filtro_dia = st.selectbox("Día", ["Todos"] + DIAS, key="conv_email_dia")
    with ef3:
        filtro_cedula = st.text_input(
            "Cédula (opcional)", key="conv_email_cedula",
            placeholder="Solo aplica a tipo Individual",
        )
    with ef4:
        filtro_modo = st.selectbox(
            "Modo", ["Todos", "Solo reales", "Solo prueba"], key="conv_email_modo",
        )

    if not st.checkbox("Mostrar correos archivados", key="conv_email_mostrar"):
        return

    modo_prueba_filtro = None
    if filtro_modo == "Solo reales":
        modo_prueba_filtro = False
    elif filtro_modo == "Solo prueba":
        modo_prueba_filtro = True
    tipo_filtro = None if filtro_tipo == "Todos" else filtro_tipo
    dia_filtro = None if filtro_dia == "Todos" else filtro_dia
    cedula_filtro = filtro_cedula.strip() or None

    with st.spinner("Cargando correos archivados…"):
        emails = api.get_emails_enviados(
            tipo=tipo_filtro, cedula=cedula_filtro, modo_prueba=modo_prueba_filtro, dia=dia_filtro,
        )

    if not emails:
        st.info("Sin correos archivados para estos filtros.")
        return

    st.caption(f"{len(emails)} correo(s) encontrados.")
    df = pd.DataFrame([{
        "Seleccionar": False,
        "Fecha":      e["fecha_envio"],
        "Tipo":       e["tipo"],
        "Día":        e["dia"] or "—",
        "Nombre":     e["empleado_nombre"] or "—",
        "Cédula":     e["empleado_cedula"] or "—",
        "Destino":    e["destino"],
        "Asunto":     e["asunto"],
        "Modo":       "🧪 Prueba" if e["modo_prueba"] else "✅ Real",
        "id":         e["id"],
    } for e in emails])

    edited = st.data_editor(
        df,
        key="conv_email_editor",
        use_container_width=True,
        hide_index=True,
        disabled=["Fecha", "Tipo", "Día", "Nombre", "Cédula", "Destino", "Asunto", "Modo"],
        column_config={
            "Seleccionar": st.column_config.CheckboxColumn("Seleccionar"),
            "id": None,  # oculta la columna id, solo se usa internamente
        },
    )
    ids_seleccionados = edited[edited["Seleccionar"]]["id"].tolist()

    bd1, bd2 = st.columns(2)
    with bd1:
        if st.button(f"⬇️ Descargar seleccionados ({len(ids_seleccionados)})", disabled=not ids_seleccionados):
            if len(ids_seleccionados) == 1:
                with st.spinner("Preparando descarga…"):
                    html_contenido = api.get_email_enviado_html(ids_seleccionados[0])
                if html_contenido:
                    email_sel = next(e for e in emails if e["id"] == ids_seleccionados[0])
                    st.download_button(
                        label=f"⬇️ Descargar correo de {email_sel['empleado_nombre'] or email_sel['tipo']} (.html)",
                        data=html_contenido, file_name=_nombre_archivo_email(email_sel),
                        mime="text/html", key="conv_email_download_individual",
                    )
                else:
                    st.info("No se pudo descargar ese correo.")
            else:
                with st.spinner("Preparando descarga…"):
                    zip_contenido = api.get_emails_enviados_zip(ids=ids_seleccionados)
                if zip_contenido:
                    st.download_button(
                        label=f"⬇️ Descargar {len(ids_seleccionados)} correos (.zip)",
                        data=zip_contenido, file_name="correos_seleccionados.zip",
                        mime="application/zip", key="conv_email_download_zip_seleccionados",
                    )
                else:
                    st.info("No se pudo generar la descarga.")
    with bd2:
        if st.button(f"⬇️ Descargar todos los filtrados ({len(emails)})"):
            with st.spinner("Preparando descarga…"):
                zip_contenido = api.get_emails_enviados_zip(
                    tipo=tipo_filtro, cedula=cedula_filtro, modo_prueba=modo_prueba_filtro, dia=dia_filtro,
                )
            if zip_contenido:
                st.download_button(
                    label=f"⬇️ Descargar {len(emails)} correos filtrados (.zip)",
                    data=zip_contenido, file_name="correos_archivados_filtrados.zip",
                    mime="application/zip", key="conv_email_download_zip_filtrados",
                )
            else:
                st.info("No se pudo generar la descarga.")
