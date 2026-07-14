import streamlit as st

import api_client as api

TIPOS_CURSO = ["PRESENCIAL", "VIRTUAL", "ZOOM"]
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
         "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]


def render_tab_administracion(anio: int) -> None:
    st.title("🛠️ Administración")

    _seccion_carga_curso(anio)
    st.divider()
    _seccion_convocatoria_por_curso(anio)
    st.divider()
    _seccion_novedades(anio)


def _seccion_carga_curso(anio: int) -> None:
    st.markdown("### 📤 Carga de curso desde CSV")
    st.caption(
        "Sube el export crudo de Moodle (calificaciones) de un curso. Puede ser un curso "
        "completamente nuevo, o un supletorio de uno ya cargado."
    )

    archivo = st.file_uploader("Archivo CSV", type=["csv", "xls"], key="admin_csv_uploader")
    modo_label = st.radio("Tipo de carga", ["Curso nuevo", "Supletorio de curso existente"], key="admin_modo")
    modo = "nuevo" if modo_label == "Curso nuevo" else "supletorio"

    metadata: dict = {}
    if modo == "nuevo":
        c1, c2, c3 = st.columns(3)
        with c1:
            metadata["codigo"] = st.text_input("Código", key="admin_codigo")
            metadata["regional"] = st.selectbox("Regional", ["TS R2", "Quito"], key="admin_regional")
        with c2:
            metadata["nombre"] = st.text_input("Nombre del curso", key="admin_nombre_curso")
            metadata["tipo"] = st.selectbox("Tipo", TIPOS_CURSO, key="admin_tipo_curso")
        with c3:
            metadata["mes"] = st.selectbox("Mes", MESES, key="admin_mes_curso")
            metadata["anio"] = st.number_input("Año", value=anio, step=1, key="admin_anio_curso")
        c4, c5 = st.columns(2)
        with c4:
            metadata["fecha_inicio"] = st.date_input("Fecha inicio", key="admin_fecha_inicio")
        with c5:
            metadata["fecha_fin"] = st.date_input("Fecha fin", key="admin_fecha_fin")
    else:
        cursos = api.get_cursos(anio=anio)
        opciones = {f"{c['nombre']} — {c['regional_nombre']} ({c['codigo']})": c["id"] for c in cursos}
        if not opciones:
            st.info(f"No hay cursos cargados para el año {anio} todavía.")
            return
        seleccionado = st.selectbox("Curso existente", list(opciones.keys()), key="admin_curso_existente")
        curso_elegido = next(c for c in cursos if c["id"] == opciones[seleccionado])
        metadata["curso_id"] = curso_elegido["id"]
        metadata["regional"] = curso_elegido["regional_nombre"]
        metadata["convocatoria"] = st.number_input("Número de convocatoria (supletorio)", min_value=2, value=2, step=1, key="admin_convocatoria")

    if st.button("Cargar CSV", type="primary", disabled=archivo is None):
        if archivo is None:
            st.error("Selecciona un archivo CSV primero.")
            return

        with st.spinner("Procesando…"):
            kwargs = dict(modo=modo)
            if modo == "nuevo":
                kwargs.update(
                    codigo=metadata["codigo"], nombre=metadata["nombre"], tipo=metadata["tipo"],
                    mes=metadata["mes"], fecha_inicio=metadata["fecha_inicio"].isoformat(),
                    fecha_fin=metadata["fecha_fin"].isoformat(), anio=int(metadata["anio"]),
                    regional=metadata["regional"],
                )
            else:
                kwargs.update(curso_id=metadata["curso_id"], convocatoria=int(metadata["convocatoria"]))

            resultado = api.cargar_curso(archivo.getvalue(), archivo.name, **kwargs)

        if resultado:
            st.session_state["admin_ultimo_resultado"] = resultado

    resultado = st.session_state.get("admin_ultimo_resultado")
    if resultado:
        col_msg, col_clear = st.columns([5, 1])
        with col_msg:
            st.success(f"✅ Nuevos: {resultado['nuevos']} · Actualizados: {resultado['actualizados']}")
        with col_clear:
            if st.button("Limpiar", key="admin_limpiar_resultado"):
                st.session_state.pop("admin_ultimo_resultado", None)
                st.rerun()
        if resultado.get("sin_regular"):
            st.warning(
                f"⚠️ {len(resultado['sin_regular'])} persona(s) no tienen nota REGULAR previa en este curso "
                "— no se les pudo cargar el supletorio: "
                + ", ".join(p["nombre"] for p in resultado["sin_regular"])
            )
        if resultado.get("sin_match"):
            st.markdown(f"#### 🧑‍💼 {len(resultado['sin_match'])} colaborador(es) sin registrar — dar de alta")
            for persona in resultado["sin_match"]:
                _form_alta_empleado(persona, metadata.get("regional", "TS R2"))


def _form_alta_empleado(persona: dict, regional_sugerida: str) -> None:
    with st.expander(f"{persona['nombre']} — {persona['cedula']}"):
        with st.form(f"form_alta_{persona['cedula']}"):
            regional = st.selectbox("Regional", ["TS R2", "Quito"],
                                     index=0 if regional_sugerida == "TS R2" else 1,
                                     key=f"alta_regional_{persona['cedula']}")
            jefe_inmediato = st.text_input("Jefe inmediato", key=f"alta_jefe_{persona['cedula']}")
            jefe_correo = st.text_input("Correo del jefe", key=f"alta_jefe_correo_{persona['cedula']}")
            sucursal = None
            if regional == "TS R2":
                sucursal = st.text_input("Sucursal", key=f"alta_sucursal_{persona['cedula']}")
            genero = st.selectbox("Género (opcional)", ["", "M", "F"], key=f"alta_genero_{persona['cedula']}")

            if st.form_submit_button("Dar de alta"):
                if not jefe_inmediato or not jefe_correo:
                    st.error("Jefe inmediato y su correo son obligatorios.")
                    return
                payload = {
                    "cedula": persona["cedula"], "nombre": persona["nombre"],
                    "regional": regional, "area": persona.get("area"), "correo": persona.get("correo"),
                    "jefe_inmediato": jefe_inmediato, "jefe_correo": jefe_correo,
                    "genero": genero or None, "sucursal": sucursal or None,
                }
                resultado = api.crear_empleado(payload)
                if resultado:
                    st.success(f"Empleado {resultado['nombre']} creado. Vuelve a cargar el mismo CSV para registrar su nota.")
                    ultimo = st.session_state.get("admin_ultimo_resultado")
                    if ultimo and ultimo.get("sin_match"):
                        ultimo["sin_match"] = [
                            p for p in ultimo["sin_match"] if p["cedula"] != persona["cedula"]
                        ]
                    st.rerun()


def _seccion_convocatoria_por_curso(anio: int) -> None:
    st.markdown("### 📅 Convocatoria por curso")
    st.caption(
        "Un curso recién cargado no cuenta para Convocatoria hasta que lo actives aquí. "
        "Los cursos ya cargados antes de esta funcionalidad quedaron activos por defecto."
    )

    cursos = api.get_cursos(anio=anio)
    if not cursos:
        st.info(f"No hay cursos cargados para el año {anio} todavía.")
        return

    for c in sorted(cursos, key=lambda c: c["nombre"]):
        col_nombre, col_toggle = st.columns([4, 1])
        with col_nombre:
            st.write(f"**{c['nombre']}** — {c['regional_nombre']} ({c['codigo']})")
        with col_toggle:
            st.toggle(
                "Convocatoria", value=c["convocatoria_habilitada"],
                key=f"conv_hab_{c['id']}", label_visibility="collapsed",
                on_change=_on_toggle_convocatoria_habilitada, args=(c["id"],),
            )


def _on_toggle_convocatoria_habilitada(curso_id: int) -> None:
    habilitada = st.session_state[f"conv_hab_{curso_id}"]
    resultado = api.set_convocatoria_habilitada(curso_id, habilitada)
    if not resultado:
        st.error("No se pudo actualizar el estado de convocatoria. Intenta de nuevo.")


_ESTADOS_RESOLUCION = {
    "Falta injustificada (F)": "FALTA_INJUSTIFICADA",
    "Falta justificada (J)": "FALTA_JUSTIFICADA",
    "No aplica (NA)": "NO_APLICA",
    "Vacaciones (V)": "VACACIONES",
    "Exonerado": "EXONERADO",
    "Asistencia": "ASISTENCIA",
}


def _seccion_novedades(anio: int) -> None:
    st.markdown("### 📋 Novedades — quiénes no han rendido")
    st.caption(
        "Activos que no tienen ninguna nota en un curso ya cargado. Se puede notificar a su "
        "jefe directo, y luego resolver el estado final cuando se sepa qué pasó."
    )

    cursos = api.get_cursos(anio=anio)
    if not cursos:
        st.info(f"No hay cursos cargados para el año {anio} todavía.")
        return

    opciones = {f"{c['nombre']} — {c['regional_nombre']} ({c['codigo']})": c["id"] for c in cursos}
    seleccionado = st.selectbox("Curso", list(opciones.keys()), key="novedad_curso_select")
    curso_id = opciones[seleccionado]

    with st.spinner("Cargando…"):
        datos = api.get_no_rindieron(curso_id)

    if not datos:
        st.info("No se pudo cargar la información de este curso.")
        return

    _tabla_sin_notificar(curso_id, datos["sin_notificar"])
    st.divider()
    _tabla_pendientes_resolver(datos["pendientes_resolver"])


def _tabla_sin_notificar(curso_id: int, personas: list[dict]) -> None:
    st.markdown(f"#### Sin notificar ({len(personas)})")
    if not personas:
        st.info("Todos los activos de esta regional tienen alguna nota en este curso.")
        return

    seleccionadas = []
    for p in personas:
        marcado = st.checkbox(f"{p['nombre']} — {p['cedula']}", value=True, key=f"chk_{curso_id}_{p['cedula']}")
        if marcado:
            seleccionadas.append(p["cedula"])

    modo_prueba = st.toggle("Modo prueba", value=True, key=f"novedad_modo_prueba_{curso_id}",
                             help="Mientras esté activo, TODOS los correos de esta tanda se redirigen al correo de prueba.")
    correo_prueba = None
    if modo_prueba:
        correo_prueba = st.text_input("Correo de prueba", placeholder="tu_correo@telconet.ec", key=f"novedad_correo_prueba_{curso_id}")

    if st.button(f"Enviar novedad a jefes ({len(seleccionadas)} seleccionados)", type="primary", key=f"btn_novedad_{curso_id}"):
        if not seleccionadas:
            st.error("Selecciona al menos una persona.")
            return
        if modo_prueba and not correo_prueba:
            st.error("Ingresa un correo de prueba mientras el modo prueba esté activo.")
            return

        with st.spinner("Enviando…"):
            resultado = api.enviar_novedad(curso_id, seleccionadas, modo_prueba, correo_prueba)

        if resultado:
            sufijo = " (modo prueba)" if modo_prueba else ""
            st.success(f"✅ Notificados: {len(resultado['notificados'])}{sufijo} · Correos a jefes: {len(resultado['recopilatorios_enviados'])}")
            st.rerun()


def _tabla_pendientes_resolver(personas: list[dict]) -> None:
    st.markdown(f"#### Pendientes de resolver ({len(personas)})")
    if not personas:
        st.info("No hay novedades pendientes de resolver para este curso.")
        return

    for p in personas:
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            st.write(f"**{p['nombre']}** — {p['cedula']}")
        with col2:
            etiqueta = st.selectbox(
                "Estado final", list(_ESTADOS_RESOLUCION.keys()),
                key=f"resolver_estado_{p['nota_id']}", label_visibility="collapsed",
            )
        with col3:
            if st.button("Guardar", key=f"resolver_btn_{p['nota_id']}"):
                estado = _ESTADOS_RESOLUCION[etiqueta]
                resultado = api.resolver_nota(p["nota_id"], estado)
                if resultado:
                    st.success(f"{p['nombre']} → {etiqueta}")
                    st.rerun()
