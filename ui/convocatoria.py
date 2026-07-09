# ui/convocatoria.py
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import api_client as api

DIAS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]


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
    st.title("📧 Convocatoria a Supletorios")

    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        regional = st.selectbox("Regional", ["TS R2", "Quito"], key="conv_regional")
    with fc2:
        dia = st.selectbox("Día", DIAS, key="conv_dia")
    with fc3:
        semana_sel = st.date_input("Semana", value=date.today(), key="conv_semana")

    semana_inicio = _lunes_de_semana(semana_sel)

    if st.button("Cargar convocatoria del día", type="primary"):
        st.session_state["conv_cargado"] = True

    if not st.session_state.get("conv_cargado"):
        st.info("Selecciona los filtros y presiona 'Cargar convocatoria del día'.")
        return

    with st.spinner("Cargando convocatoria…"):
        preview = api.get_convocatoria_preview(dia=dia, regional=regional, semana=semana_inicio.isoformat())

    st.markdown(f"### Convocados — {dia}, semana del {semana_inicio.strftime('%d/%m/%Y')}")

    if not preview:
        st.info("Nadie tiene día efectivo = " + dia + " en " + regional + " para esta semana.")
    else:
        for persona in preview:
            cols = st.columns([3, 4, 1, 1, 2])
            cols[0].write(f"**{persona['nombre']}**")
            cursos_txt = ", ".join(
                f"{c['curso']} (nota: {c['nota'] if c['nota'] is not None else '—'})"
                for c in persona["cursos_pendientes"]
            )
            cols[1].write(cursos_txt)
            cols[2].write("✅" if persona["tiene_correo"] else "❌ sin correo")
            cols[3].write("📨 ya enviado" if persona["ya_enviado"] else "—")
            with cols[4].popover("Cambiar día"):
                _form_cambiar_dia(persona["cedula"], persona["nombre"], dia, "principal")

    st.divider()
    _seccion_agregar_por_nombre(anio, regional, dia)
    st.divider()
    _seccion_envio(preview, semana_inicio)


def _seccion_agregar_por_nombre(anio: int, regional: str, dia: str) -> None:
    st.markdown("### 🔎 Agregar por nombre")
    st.caption("Busca solo entre empleados con supletorio pendiente, de cualquier día actual.")
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


def _seccion_envio(preview: list[dict], semana_inicio) -> None:
    st.markdown("### ✉️ Envío de convocatoria")

    if not preview:
        st.info("No hay convocados cargados para enviar.")
        return

    seleccionables = [p for p in preview if p["tiene_correo"]]
    if not seleccionables:
        st.warning("Ninguno de los convocados tiene correo registrado.")
        return

    seleccion = {}
    for p in seleccionables:
        etiqueta = f"{p['nombre']}" + (" (ya enviado antes)" if p["ya_enviado"] else "")
        seleccion[p["cedula"]] = st.checkbox(etiqueta, value=True, key=f"chk_envio_{p['cedula']}")

    modo_prueba = st.toggle("Modo prueba", value=True,
                             help="Mientras esté activo, TODOS los correos de esta tanda se redirigen al correo de prueba.")
    correo_prueba = None
    if modo_prueba:
        correo_prueba = st.text_input("Correo de prueba", placeholder="tu_correo@telconet.ec")

    cedulas_seleccionadas = [c for c, marcado in seleccion.items() if marcado]

    if st.button(f"Confirmar y enviar a los {len(cedulas_seleccionadas)} seleccionados", type="primary"):
        if not cedulas_seleccionadas:
            st.error("Selecciona al menos un destinatario.")
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
            )

        if resultado:
            sufijo = " (modo prueba — redirigido a correo de prueba)" if modo_prueba else ""
            st.success(f"✅ Enviados: {len(resultado['enviados'])}{sufijo}")
            if resultado["fallidos"]:
                st.error("❌ Fallidos:")
                for f in resultado["fallidos"]:
                    st.write(f"- {f['nombre'] or f['cedula']}: {f['detalle']}")
