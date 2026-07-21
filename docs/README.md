# Dashboard Capacitación TELCOU — Documentación

**Ruta:** `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1`  
**Stack:** Python · Streamlit 1.57 · pandas  
**API:** `telcou-api` en `http://localhost:8000` (FastAPI + PostgreSQL 15)  
**Puerto Streamlit:** `8501`

---

## Iniciar

```powershell
# 1. Primero levantar la API (en otra terminal)
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Luego el dashboard
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
streamlit run app.py
```

Abre `http://localhost:8501` en el navegador.

---

## Estructura de archivos

```
dashboard-telcou-s1/
├── app.py                    # Entry point — configura página, navegación en sidebar y selector de año
├── api_client.py             # Todas las llamadas a la API con caché
├── ui/
│   ├── styles.py             # CSS global, colores por estado, función badge()
│   ├── colaboradores.py      # Sección "Colaboradores"
│   ├── analitica.py          # Sección "Analítica"
│   ├── convocatoria.py       # Sección "Convocatoria" (nuevo — 2026-07-09)
│   ├── reporteria.py         # Sección "Reportería" (nuevo — 2026-07-13)
│   └── administracion.py     # Sección "Administración" (nuevo — 2026-07-13)
├── .streamlit/
│   ├── config.toml           # Tema visual (azul oscuro #0F1623 + teal #00A8A8)
│   └── secrets.toml          # API_BASE_URL, ADMIN_TOKEN (no commitear)
└── docs/
    ├── README.md             # Este archivo
    └── superpowers/plans/    # Planes de implementación
```

---

## Navegación (rediseñado — 2026-07-10)

La navegación entre secciones vive en el **sidebar** (antes eran tabs horizontales arriba del contenido) — `st.radio` con las 5 secciones: Colaboradores, Analítica, Convocatoria, Reportería, Administración (esta última agregada 2026-07-13). La tab **"Áreas" se eliminó** (`ui/areas.py` y las funciones `api_client.get_areas()`/`get_regionales()` fueron borradas, no solo ocultadas — no aportaba valor sobre lo que ya cubre Analítica).

Donde antes estaban las tabs (arriba del título) ahora está el **selector de Año** (`st.radio` horizontal: 2026 / 2025 / 2024 / 2023). Hoy solo hay datos reales cargados para 2025 (completo) y 2026 (parcial); 2024 y años anteriores se cargarán más adelante.

## Secciones del dashboard

### 👥 Colaboradores
Busca empleados por nombre. Para cada uno muestra:
- Datos personales (área, jefe, regional, estado activo/inactivo)
- Métricas: total capacitaciones, promedio, faltas, **Supletorios Rendidos** (renombrado 2026-07-09 — antes decía solo "Supletorios" y se prestaba a confusión con los pendientes)
- Inasistencias y vacaciones (tabla coloreada)
- **Trazabilidad de supletorios** (tabla horizontal) — solo muestra cursos donde **ya se intentó** un supletorio
- **Pendientes de Supletorio** (nuevo — 2026-07-09) — cursos reprobados/falta injustificada donde **todavía no se ha rendido ningún** supletorio (calculado en el cliente a partir de las notas ya cargadas, sin llamada extra a la API). Antes esto no se mostraba en ningún lado de esta tab, dando la falsa impresión de que el empleado no tenía nada pendiente
- Todas las notas regulares del período (expander)

### 📈 Analítica
- **% Aprobados global (fix 2026-07-01):** el header mostraba 68.5% vs el 85.7% real de la tabla principal, porque el denominador incluía NUEVO/CAMBIO/SALIO (empleados no convocados a ese curso). Ahora `convocados = total - na` en ambos lados y coinciden
- **Tabla por capacitación:** Total, Aprobados, % Apr. (coloreado, "—" si el curso es de solo Asistencia), **% Apr. Q / % Apr. R2** (mismo cálculo, desglosado por regional — nuevas columnas), Reprobados, Faltas injust./just., Vacaciones, **Asistencia** (columna nueva), N/A, Exonerados, Inactivos, Promedio
- **Gráfico % Aprobados:** cambiado de una sola barra vertical con ~70 cursos (ilegible) a barras horizontales (Altair) con selector Peores 15 / Mejores 15 / Todas — excluye cursos de solo Asistencia
- **Comparativa Quito vs TS R2:** mismas métricas lado a lado para cada regional
- **Resultados por ciudad (TS R2):** desglose por sucursal con % aprobados — ahora respeta el filtro de capacitación seleccionado arriba (si se elige exactamente 1 curso, tabla y gráfico se limitan a ese curso; antes ignoraba el filtro y siempre mostraba el total del año)
- **Supletorios:** Aprobados Intento 1/2 y Pendientes, segmentado por Quito y TS R2. Pendientes excluye a quienes ya están inactivos hoy
- **Detalle de Pendientes por Colaborador (nuevo — 2026-07-07):** listado individual (cédula, nombre, regional, sucursal, área, curso, situación, última nota/estado) consumiendo `GET /analitica/supletorios-pendientes`. Filtro por Regional (Todas/Quito/TS R2); reutiliza el filtro de Capacitaciones de arriba para acotar a un solo curso

> Año 2026 agregado al selector del sidebar (antes solo 2025/2024/2023). Con datos reales ya cargados (empleados, notas y supletorios pendientes para TS R2; Quito aún sin supletorios pendientes 2026 registrados).

### 📧 Convocatoria (nuevo — 2026-07-09)

Ventana para gestionar el día de capacitación de cada empleado y para enviar convocatorias de supletorio por correo. TS R2 tiene `día`/`correo` cargados (`variables_adicionales`, desde el Excel de Israel). **Quito (cargado 2026-07-10, 1012 colaboradores, 1724 supletorios pendientes) todavía NO tiene `día` cargado** — sí tiene `jefe_correo`/`jefe_inmediato` — ver aviso más abajo.

- **Filtros:** Regional (TS R2 / Quito) · Día (LUNES-VIERNES) · Semana → botón "Cargar convocatoria del día"
- **Tabla principal (nuevo — 2026-07-09, `st.data_editor`):** convocados de ese día (día efectivo — ver más abajo), con columna **"Enviar"** (checkbox editable, integrado en la misma tabla — antes era una lista aparte de 60-100 checkboxes, ilegible), cursos pendientes (nombre, nota), correo registrado, y si ya se les envió antes. Botones **"Seleccionar todos"** / **"Ninguno"** arriba de la tabla.
- **Cambiar día:** ya no es un botón por fila (con 60-100 filas era inmanejable) — un selector único **"Cambiar día de un convocado"** debajo de la tabla, o desde el buscador. Formulario: día nuevo, tipo (`SEMANAL` = solo esa semana, vuelve a su día normal después; `PERMANENTE` = cambia su día de base), motivo, editado por (opcional). Con trazabilidad completa (`GET /empleados/{cedula}/dia-historial`).
- **"Día efectivo"**: si el empleado tiene una excepción `SEMANAL` vigente para la semana consultada, se usa ese día; si no, se usa su día base (`variables_adicionales.dia`).
- **Buscador "Agregar por nombre":** busca solo entre empleados con supletorio pendiente (de cualquier día), para agregarlos al día que se está armando.
- **Envío:** lee la selección directo de la columna "Enviar" de la tabla de arriba (ya no duplica la lista) · toggle **"Modo prueba"** (por defecto ON — hay que apagarlo conscientemente para un envío real; en modo prueba todos los correos de la tanda se redirigen al correo de prueba, con el nombre real del destinatario visible en el cuerpo) · botón "Confirmar y enviar" → resumen final (enviados/fallidos).
- **Plantilla de correo rediseñada (2026-07-09):** los 3 tipos de correo (individual, recopilatorio, resumen ejecutivo) usan un layout de tabla con inline styles compatible con Outlook/Zimbra (sin CSS moderno tipo flexbox/grid), con cabecera de marca TELCOU. Antes era texto plano sin estilo.
- **Recopilatorio al jefe inmediato (nuevo — 2026-07-09):** por cada envío, si el empleado tiene `jefe_correo` registrado en `variables_adicionales`, se agrupan todos sus colaboradores convocados en esa tanda y se le manda **un solo correo** (no uno por empleado) con el listado de quién fue convocado y a qué cursos. La UI muestra un caption "📋 Recopilatorio enviado a N jefe(s)" tras el envío.
- **Resumen ejecutivo a coordinación (nuevo — 2026-07-09):** al final de cada tanda de envío (si hubo al menos un enviado o un fallido) se manda un resumen ejecutivo (regional, día, semana, total enviados/fallidos, detalle de fallidos) a una lista fija de coordinadores, configurada en `telcou-api/.env` como `COORDINADOR_EMAILS` (hoy: `mharo@telconet.ec, telcou_uio@telconet.ec`). La UI muestra "📊 Resumen ejecutivo enviado a los coordinadores".
- **Modo prueba cubre los 3 correos:** individual, recopilatorio y resumen ejecutivo se redirigen todos al correo de prueba cuando el toggle está activo — ninguno de los tres llega a un destinatario real durante pruebas.
- **Historial de envíos (nuevo — 2026-07-09):** sección de auditoría de solo lectura al final de la tab, con filtros por Regional y Modo (reales/prueba/todos) tras marcar "Mostrar historial". Consume `GET /analitica/envios-convocatoria` (protegido por `X-Admin-Token`, nunca expuesto sin token) — el dashboard no tiene ni necesita acceso directo a la base de datos, todo pasa por la API.
- **Año efectivo = año de la Semana, no el selector global (fix 2026-07-10):** el selector de Año de arriba (ver sección "Navegación") no controla la tabla principal — esa siempre se filtra por la fecha "Semana" del formulario. Antes el buscador "Agregar por nombre" y el "Historial de envíos" sí usaban el selector global, lo que podía desincronizarse en cuanto hubiera datos de más de un año. Ahora los tres derivan el año de `semana_inicio.year`.
- **Aviso cuando la regional no tiene `día` cargado (nuevo — 2026-07-10):** si al cargar la convocatoria no aparece nadie, el dashboard distingue dos casos usando `GET /analitica/regional-dia-configurado`: si la regional sí tiene el dato de día para al menos un colaborador, muestra el mensaje normal ("Nadie tiene día efectivo = X"); si la regional entera no tiene `día` cargado (caso Quito hoy), muestra una advertencia explícita en vez del mensaje genérico y engañoso que había antes. El buscador "Agregar por nombre" y el formulario "Cambiar día" sí funcionan para Quito mientras tanto (permiten ir estableciendo el día colaborador por colaborador).

> **Verificado en producción (2026-07-09):** un envío real en modo prueba a un empleado real de TS R2 llegó correctamente redirigido a `telcou_aut@telconet.ec` (no al correo real del empleado), registrando 4 filas en `envios_convocatoria` con `modo_prueba=True` sin marcar al empleado como "ya enviado" (los envíos de prueba no cuentan como notificación real). Verificado también el flujo completo de recopilatorio + resumen ejecutivo (envío real en modo prueba con jefe_correo poblado): 3 correos SMTP reales enviados, todos redirigidos correctamente al correo de prueba.

**Fecha puntual por día en el correo individual (fix 2026-07-17).** El correo a cada colaborador mostraba el nombre del día ("LUNES") sin fecha, o — en un intento intermedio — un rango de la semana completa ("semana del 20 al 24 de julio"). Ambos formatos generaron confusión real el día del envío. Ahora muestra la fecha exacta de su día convocado como frase natural ("lunes 20 de julio de 2026"), calculada por offset desde el lunes de la semana (`fecha_inicio_semana` + días hasta el día del empleado). **Virtual es la única excepción a propósito:** como no tiene un día fijo (disponible toda la semana), su mensaje quedó como *"Las evaluaciones se encuentran habilitadas de forma virtual toda la semana (27 al 31 de julio de 2026)"* — rango, no fecha puntual.

**Fecha única en el resumen ejecutivo y el consolidado (fix 2026-07-17).** Ambos correos mostraban "Día: LUNES" y "Semana: 2026-07-20" como dos filas separadas y redundantes. Se colapsaron en una sola fila "Fecha" con el mismo formato natural que el correo individual (fecha puntual si hay un día, rango si no). El resumen ejecutivo ahora también lista **a quién se le envió** (nombre + cédula), no solo el conteo — antes solo mostraba el detalle de fallidos.

**Envío real de convocatoria — validado en producción el 2026-07-20 (semana del 27 al 31 de julio):** durante el envío real del día se encontraron y corrigieron en vivo 3 bugs — (1) el selector de Semana tenía como valor por defecto `date.today()`, así que un envío sin tocar ese campo salía con fecha de la semana actual/pasada en vez de la semana futura correcta (ahora el default es el lunes de **la próxima semana**, y hay un aviso `st.warning` visible con el rango exacto justo antes del botón de enviar, tanto en el envío individual como en el consolidado); (2) la asignación de aula en el envío real dependía del orden en que llegaban las cédulas en el body (no del orden alfabético que usa el preview de Reportería), así que la misma persona podía terminar en un aula distinta según el orden de selección en el frontend — ahora ambos ordenan por nombre antes de asignar; (3) los colaboradores con `sede=Virtual` (siempre `dia=None` en la base — no aplica un día fijo) nunca podían aparecer en el preview de Convocatoria para ningún día (`None` nunca coincide con LUNES-VIERNES) y, aunque se les mandara el correo por cédula directa, el bloque de asistencia se omitía por completo por no tener día — se agregó la opción **"VIRTUAL"** al selector de Día (filtra por `sede="Virtual"` en vez de por día efectivo) y se corrigió el bloque de asistencia para armarse con solo `sede="Virtual"`, sin depender de que haya un día.

**Correos archivados (nuevo — 2026-07-20).** Nueva sección al final de la tab: bitácora con el HTML real de cada correo que el sistema ya envió (individual, recopilatorio, resumen ejecutivo, resumen consolidado) — antes solo quedaba registro de que "se envió", nunca de qué decía el correo exactamente. Filtros por Tipo, Día, Cédula y Modo (real/prueba). Tabla con columna de selección (checkbox) + dos botones de descarga: **"Descargar seleccionados"** (uno → `.html` directo; varios → `.zip`) y **"Descargar todos los filtrados"** (siempre `.zip`, sin necesidad de marcar nada). Cada archivo dentro del zip (y el nombre del `.html` individual) usa el nombre y apellidos reales del colaborador, no un ID genérico.

**Resumen consolidado + toggle de resumen ejecutivo (nuevo — 2026-07-17).** Nueva sección "Enviar resumen consolidado a la jefatura" (un solo correo con dos secciones — UIO/Quito y TS R2 — agregando los envíos ya hechos esa semana, pensado para usarse una sola vez después de enviar Quito y TS R2 por separado) y un checkbox **"Enviar resumen ejecutivo individual a coordinadores"** (desactivado por defecto) en la sección de envío existente — antes el resumen ejecutivo se mandaba siempre, duplicando el aviso a la jefatura si además se usaba el consolidado.

---

### 📥 Reportería (nuevo — 2026-07-13)

Sección para descargar reportes de supletorios pendientes en dos formatos, ambos generados en el backend (`app/services/reportes.py`) reutilizando la misma lógica de "quién se quedó" que ya usa Convocatoria y Analítica (`supletorios_pendientes_data()`) — sin duplicar reglas de negocio.

- **Excel (lista) — `GET /analitica/reporte-supletorios-pendientes?anio=`:** `.xlsx` con dos hojas fijas (Quito, TS R2), formato lista (una fila por colaborador + curso pendiente): Cédula, Nombre, Área, Sucursal, Tema, Fecha Inicio, Fecha Fin, Link Moodle, Nota. Sin código de curso. La columna Nota trae solo el valor numérico, o **"F"** si el pendiente es por falta injustificada (nunca rindió el examen, no hay nota que mostrar — antes esa celda quedaba vacía y se confundía con un error de datos).
- **Vista interactiva (HTML) — `GET /analitica/reporte-supletorios-pendientes-html?anio=`:** página `.html` autocontenida (sin dependencias externas salvo Google Charts para la gráfica — ver abajo), descargable y navegable por colaborador: tarjetas colapsadas por defecto (nombre + cantidad de pendientes, clic para expandir), buscador por nombre/cédula (mínimo 2 letras), y filtros por Regional y Capacitación. Solo aparecen colaboradores con al menos un pendiente.
- **Resumen con gráfica 3D (nuevo — 2026-07-13, misma tarde):** al final de la vista interactiva, un contador de "Supletorios pendientes en la selección actual" + una gráfica de pastel 3D real (Google Charts, `is3D: true`) comparando Aprobados vs. Supletorio pendiente con porcentaje, reactiva a los filtros de Regional y Capacitación (no a la búsqueda por nombre). Requiere internet la primera vez que se abre (CDN de `gstatic.com`) — si no carga en 4 segundos, muestra un resumen de solo texto en vez de un recuadro roto.
- **Ambos botones de descarga** (`api_client.get_reporte_pendientes_excel(anio)` / `get_reporte_pendientes_html(anio)`) usan un nuevo helper `_get_bytes()` en `api_client.py`, ya que los helpers existentes (`_get`, `_get_admin`) asumen respuesta JSON — estos dos endpoints devuelven binario.

**Homologación de nombres de capacitación entre Quito y TS R2 (2026-07-13):** Quito y TS R2 cargan sus propias planillas de forma independiente para el mismo año, y los nombres de curso casi nunca coinciden exacto (tildes, sufijos de sede, typos como "TRUBLESHOOTING"/"MANTENIMINETO"). Sin esto, el mismo curso aparecía como dos capacitaciones distintas en el filtro de Reportería, y además `GET /analitica/listado-cursos` (en Analítica) agrupaba mal — mostraba dos filas separadas por regional en vez de una fila comparable. Se agregó `app/services/homologacion_cursos.py` (backend) con un mapeo verificado y confirmado manualmente con el usuario: **46/46 cursos de 2026 homologados**, cero cursos exclusivos de una sola regional. Es una capa de presentación en código puro — no toca la base de datos ni requiere migraciones (decisión explícita para no arriesgar la carga de datos en curso).

> **Verificado con datos reales (2026-07-13):** `GET /analitica/listado-cursos?anio=2026` pasó de 56 filas (20 mal separadas) a exactamente 46 filas, todas con Quito y TS R2 poblados. El filtro de Capacitación en Reportería bajó de 71 a 45 opciones únicas (solo cursos con al menos un pendiente). "MANTENIMIENTO DE CAJAS" (Quito) y "MANTENIMINETO DE CAJAS" (TS R2, con typo) ahora se homologan al mismo nombre en ambos reportes.

**Segmentación por día + columnas de convocatoria (2026-07-17).** El reporte de Supletorios ganó un filtro **multiselect de Día** (LUNES-VIERNES, elegís uno o varios — Streamlit agrega automáticamente un "Select all"): sin día seleccionado, comportamiento clásico de 2 hojas (Quito, TS R2); con día(s), se desglosa en 4 hojas — Guamaní, Mariana de Jesús (filtradas a esos días), Virtual (sin filtrar, disponible toda la semana) y TS R2. Las hojas de Guamaní y Mariana de Jesús agregan 3 columnas exclusivas — **Jefe Inmediato, Aula, Código de curso** — porque son las únicas sedes con asignación de aula; un colaborador con varios cursos pendientes ocupa un solo cupo de aula, no uno por curso.

**Selector "Tipo de reporte" (nuevo — 2026-07-20).** Reportería dejó de ser solo "supletorios pendientes": ahora abre con un selector (`Supletorios pendientes` / `Asistencia` / `Calificaciones generales`) que cambia los filtros y las descargas disponibles.
- **Asistencia:** todos los estados sin nota numérica del año — ASISTENCIA, FALTA_INJUSTIFICADA, FALTA_JUSTIFICADA, VACACIONES, NO_APLICA, EXONERADO, CAMBIO, SALIO, NUEVO. No es "quién necesita supletorio" (eso sigue siendo el reporte de Supletorios) — es el universo completo de gente sin calificación numérica, para revisión general.
- **Calificaciones generales:** el libro de calificaciones completo del año — todas las notas REGULAR, aprobadas o no, sin filtrar por pendiente/resuelto.
- Ambos se segmentan solo por **Regional** (Quito/TS R2, sin desglose por día/sede — más simple que Supletorios a propósito), en Excel y HTML, y agregan columnas **"Resuelto por Novedad"** (Sí/No) y **Observación** por fila — para saber si ese estado llegó así desde la carga original o se resolvió manualmente vía Novedades (ver sección Administración).
- **Fix de rendimiento (2026-07-20):** el reporte de Calificaciones generales (~68.000 filas en 2026) tardaba **41 segundos** en generarse — peligrosamente cerca del timeout de 60s del dashboard, y la causa directa del incidente de "Semana" documentado arriba. Se cambió `openpyxl.Workbook(write_only=True)` (streaming de celdas, sin construir el árbol completo en memoria) solo para estos dos reportes nuevos — bajó a **11 segundos**.

**Calificaciones (formato macro) — 4º tipo de reporte (nuevo — 2026-07-21).** A diferencia de los otros tres (formato lista), este replica **exactamente** la disposición del macro manual real que el usuario mantiene a mano (`ejemplo formatos.xlsx`): una fila por colaborador, una columna por curso, dos hojas fijas ("PERSONAL TECNICO - QUITO" / "PERSONAL TECNICO - TS R2") con el mismo bloque de cabecera de 5 filas (código, link, mes, nombre, tipo) y columnas de resumen con **fórmulas Excel reales** (`COUNTIF`/`COUNT`/`SUM`, no valores precalculados) — 0 por copia, faltas, supletorios pendientes, conteo y promedio. Filtro de rango de meses (`mes_desde`/`mes_hasta`, ambos opcionales) y toggle **"Incluir supletorios"** (`combinado=True`) que agrega, junto a cada curso con actividad de supletorio, una columna compañera " (SUPLETORIO)" con el resultado del intento más reciente. Backend nuevo: `app/services/reporte_matriz.py`, endpoint `GET /analitica/reporte-calificaciones-macro?anio=&mes_desde=&mes_hasta=&combinado=`. Sin migración (reporte de solo lectura sobre tablas existentes).

> **Verificado con datos reales (2026-07-21):** generado para `anio=2026`, ENERO-FEBRERO, Quito, y comparado celda por celda contra `ejemplo formatos.xlsx` — 3 colaboradores (incluyendo el caso especial "A"=ASISTENCIA de CAGUA OVANDO KLEVER ANTONIO, que motivó el diseño del mapeo estado→código) coincidieron exacto, igual que las 5 fórmulas de resumen. **Hallazgo real, no defecto de esta feature:** una comparación más allá del spot-check encontró que 190/1011 filas (19%) muestran un "NA" tipeado a mano en el original donde el reporte generado muestra celda vacía, y 1 colaborador (ANGAMARCA MORA HECTOR ROBERTO, 1717138513) está ausente del reporte generado. Causa raíz confirmada por consulta directa a la BD: faltan registros `Nota` con estado `NO_APLICA` para esas combinaciones empleado/curso (cero notas de ningún tipo, no solo con estado incorrecto) — un hueco de completitud de datos preexistente en la BD, no un bug del mapeo (que coincidió exacto en todo el resto del dataset). Buen candidato para el atajo "Marcar NA" de Administración.

---

### 🛠️ Administración (nuevo — 2026-07-13)

Nueva `ui/administracion.py`, 5ª entrada del sidebar. Tres flujos conectados entre sí, pensados para que el admin cargue un curso completo (carga → altas de empleados nuevos → aviso de novedades) sin salir de la pantalla.

**1. Carga de curso desde CSV.** `st.file_uploader` para el export crudo de Moodle (extensión `.xls` engañosa — es CSV, UTF-8 con BOM) + radio **Curso nuevo** / **Supletorio de curso existente**:
- **Curso nuevo (Modo A):** el admin llena código, nombre, tipo (`PRESENCIAL`/`VIRTUAL`/`ZOOM`), mes, fechas y regional. Cada fila del CSV se guarda como `Nota(tipo="REGULAR", convocatoria=1)`.
- **Supletorio (Modo B):** el admin elige un curso ya cargado (selector filtrable por año) y un número de convocatoria (2, 3…). Cada fila se guarda como `Nota(tipo="SUPLETORIO")` enlazada vía `nota_original_id` a la nota REGULAR de esa misma persona en ese curso — si no existe una REGULAR previa, la fila se reporta como error (`sin_regular`), nunca se crea un supletorio huérfano.
- Recargar el mismo CSV corrige/completa sin duplicar (upsert por `empleado_id, curso_id, tipo, convocatoria`). Cédulas sin match no bloquean el resto de la carga — se acumulan y disparan el Flujo 2.

**Formato del CSV de Moodle:** columnas `Nombre`, `Departamento` (→ área), `Dirección de correo`, `Número de ID` (cédula, normalizada con `.zfill(10)`), `Calificación/10,00` (coma decimal, formato Ecuador). La última fila ("Promedio general", `Nombre` vacío) se descarta. Umbral de aprobación **7.5** (mismo valor que los importadores existentes).

**2. Alta de empleado nuevo.** Por cada cédula del CSV sin match en la BD, un formulario pre-llenado (`cedula`, `nombre`, `area`, `correo` ya vienen del CSV) donde el admin completa lo que falta: **jefe inmediato** y **su correo** (obligatorios — sin esto Convocatoria no puede notificarlo), **sucursal** (solo si la regional es TS R2), **género** (opcional). Al guardar se crea `Empleado` + `VariableAdicional`; el admin debe volver a cargar el mismo CSV para que esa fila, ya con match, se registre como nota.

**3. Novedades.** Para cualquier curso ya cargado: activos de esa regional sin ninguna nota en el curso, separados en dos tablas alimentadas por la misma consulta:
- **Sin notificar** — checkboxes (todos marcados por defecto) + botón "Enviar novedad a jefes", con **modo prueba obligatorio y ON por defecto** (igual que Convocatoria). Agrupa por `jefe_correo` — un correo por jefe, no uno por persona. Cada envío real crea `Nota(estado="PENDIENTE_JUSTIFICACION")` para esa persona, que pasa a la otra tabla.
- **Pendientes de resolver** — quienes ya tienen esa nota `PENDIENTE_JUSTIFICACION`; un selector de estado final (F/J/NA/V/Exonerado/Asistencia) por fila con botón "Guardar", que actualiza la nota existente in place (mismo `id`).

Esta separación deja que el admin vuelva días después a la misma pantalla y siga viendo, sin recordar nada, tanto a quién falta notificar como a quién falta resolver.

**Nuevo estado `PENDIENTE_JUSTIFICACION`:** creado al enviar una novedad real, significa "se avisó al jefe, todavía sin resolver". Cuenta como pendiente de supletorio mientras no se resuelve — se agregó a `NECESITA_SUPLETORIO` en el backend (`app/services/convocatoria.py`), junto a `REPROBADO`/`FALTA_INJUSTIFICADA`. No requirió ninguna migración — `Nota.estado` es texto libre sin `CHECK`.

**Convocatoria por curso (nuevo — 2026-07-14).** Nueva subsección entre "Carga de curso" y "Novedades": lista los cursos del año seleccionado con un `st.toggle` por curso para activar/desactivar si cuenta para Convocatoria (backend: `Curso.convocatoria_habilitada`, expuesto ahora en `CursoOut`/`GET /cursos/`). Existe porque un curso recién cargado no debe aparecer en la vista previa ni en el envío real de Convocatoria hasta que el admin decida explícitamente que ya le toca su ronda de supletorio — los cursos cargados antes de esta funcionalidad quedaron `convocatoria_habilitada=True` por defecto vía migración retroactiva, pero todo curso nuevo nace en `False`. El toggle usa el patrón `on_change` de Streamlit (no comparar valor-guardado-vs-API en cada render) para evitar un retry-storm: si el `PATCH` falla de forma transitoria, comparar en cada rerender reintentaría la llamada en cualquier interacción no relacionada de la página.

**Atajo "Marcar NA" (nuevo — 2026-07-14).** Solo tras una carga exitosa en Modo A ("Curso nuevo"): muestra los activos de esa regional sin ninguna nota en el curso recién cargado (reutiliza `GET /analitica/curso/{curso_id}/no-rindieron`, el mismo dato que ya alimenta Novedades) con checkboxes sin marcar por defecto y un botón "Marcar NA". Crea `Nota(estado="NO_APLICA")` directo para cada cédula marcada, sin pasar por el ciclo completo de Novedades (notificar al jefe → esperar → resolver). Quien no se marca aquí sigue su camino normal y aparecerá después en Novedades.

**Fixes de la revisión final de rama (2026-07-14):** una revisión holística tras completar los 16 tasks encontró y corrigió 6 gaps que solo eran visibles al ver las piezas compuestas juntas:
- *Backend* — `cargar_supletorio` ya no enlaza un supletorio contra una nota `PENDIENTE_JUSTIFICACION` (placeholder, no una nota REGULAR real); esas cédulas ahora se reportan en `sin_regular` igual que si no existiera nota previa.
- *Backend* — `parsear_csv_moodle` valida el encoding UTF-8 y el endpoint `/admin/cargar-curso` retorna **400** (antes: 500 sin manejar) si el CSV viene en otro encoding (p.ej. Windows-1252/Latin-1, común en exports de Excel/Moodle con tildes).
- *Backend* — `enviar_novedad` solo reporta una cédula en `notificados` cuando la nota `PENDIENTE_JUSTIFICACION` realmente se creó (antes podía reportar como "notificado" a alguien que ya tenía otra nota para ese curso, sin que el `ON CONFLICT DO NOTHING` insertara nada).
- *Frontend* — la lista de "sin registrar" ahora se refresca tras dar de alta a un empleado (antes seguía mostrándolo indefinidamente aunque ya estuviera creado).
- *Frontend* — botón **"Limpiar"** junto al resumen de carga, para descartar el panel manualmente.
- *Frontend* — Modo B (supletorio) ahora sugiere la regional real del curso seleccionado en el formulario de alta (antes siempre asumía TS R2).

**Excepción "Evaluado" por curso (nuevo — 2026-07-20).** Se detectó (a pedido del usuario, analizando notas sin valor numérico) que 4 capacitaciones de 2026 (RIESGOS ELÉCTRICOS y EFICIENCIA ENERGÉTICA, Quito + su versión CNEL en TS R2 — todas ZOOM, marzo) son de **solo-asistencia, sin examen**: el 100% de sus notas son ASISTENCIA/FALTA/VACACIONES/etc., nunca un número. La regla general (FALTA_INJUSTIFICADA cuenta como pendiente de supletorio) no debía aplicar ahí, porque no hay nada que evaluar. Nuevo campo `Curso.evaluado` (default `True`, igual patrón que `convocatoria_habilitada`) con un segundo toggle **"Evaluado"** junto al de "Convocatoria" en la subsección "Convocatoria por curso" — al desactivarlo, ese curso queda excluido por completo de `supletorios_pendientes_data()`, sin importar el estado de la nota. Aplicado ya a los 4 cursos reales.

**Observaciones de notas (nuevo — 2026-07-20).** Nueva sección al final de la tab: busca por cédula, lista todas las notas de esa persona en el año (una por curso, en un expander con estado/nota) y cada una tiene su propio campo de texto libre + botón "Guardar" — para dejar contexto sobre un caso puntual sin tocar el estado ni la nota. `get_notas_empleado()` tiene caché de 15 min (`@st.cache_data(ttl=900)`); tras guardar se limpia explícitamente (`api.get_notas_empleado.clear()`) para no mostrar la observación vieja hasta que expire el caché.

**Auditoría de resoluciones de Novedades (nuevo — 2026-07-20).** Cuando `resolver_nota()` transiciona una nota de `PENDIENTE_JUSTIFICACION` a su estado final, ahora queda registrado si vino de ese flujo (`resuelto_via_novedad`, `resuelto_en`, `resuelto_por` — este último opcional, no hay login de usuarios en el dashboard todavía). Antes no había forma de distinguir, viendo solo el estado final, si una FALTA_JUSTIFICADA llegó así desde la carga original del CSV o fue una resolución manual posterior. Se refleja en los reportes de Asistencia/Calificaciones generales (columna "Resuelto por Novedad").

---

## Colores de estado

| Estado | Color |
|--------|-------|
| APROBADO | Verde `#166534` |
| REPROBADO | Rojo `#991b1b` |
| FALTA_INJUSTIFICADA | Naranja `#92400e` |
| FALTA_JUSTIFICADA | Amarillo `#854d0e` |
| VACACIONES | Azul `#1e3a5f` |
| EXONERADO | Púrpura `#4c1d95` |
| ASISTENCIA | Gris `#374151` |
| COPIA | Rosa `#9d174d` |
| NUEVO / CAMBIO / SALIO | Gris oscuro |

---

## api_client.py — Funciones disponibles

| Función | Endpoint | Descripción |
|---------|----------|-------------|
| `get_empleados(area, regional, anio, inactivo)` | `GET /empleados/` | Lista empleados con filtros |
| `get_notas_empleado(cedula, anio, mes, regional)` | `GET /empleados/{cedula}/notas` | Notas del empleado |
| `get_resumen_empleado(cedula, anio)` | `GET /empleados/{cedula}/resumen` | Métricas del empleado |
| `get_trazabilidad_empleado(cedula, anio)` | `GET /empleados/{cedula}/trazabilidad` | Cadena REGULAR→SUPLE1→SUPLE2 por curso |
| `get_sucursales(anio, regional, nombre)` | `GET /analitica/sucursales` | Stats por ciudad dentro de una regional — `nombre` (2026-07-01) filtra por capacitación seleccionada |
| `get_listado_cursos(anio, mes, nombre)` | `GET /analitica/listado-cursos` | Stats por capacitación con desglose Quito/R2 |
| `get_supletorios_pendientes(anio, regional, curso, sucursal)` | `GET /analitica/supletorios-pendientes` | Listado detallado por empleado de supletorios pendientes (2026-07-07) |
| `get_convocatoria_preview(dia, regional, semana)` | `GET /analitica/convocatoria-preview` | Convocados de un día/regional/semana, con cursos pendientes, correo y estado de envío (2026-07-09) |
| `buscar_supletorios_pendientes(nombre, anio, regional)` | `GET /analitica/supletorios-pendientes/buscar` | Búsqueda por nombre entre pendientes, para el buscador "Agregar por nombre" (2026-07-09) |
| `get_dia_historial(cedula)` | `GET /empleados/{cedula}/dia-historial` | Trazabilidad de cambios de día de un empleado (2026-07-09) |
| `cambiar_dia_empleado(cedula, dia_nuevo, tipo, motivo, semana_inicio, editado_por)` | `PATCH /empleados/{cedula}/dia` | Cambia el día de capacitación (permanente o solo-una-semana) (2026-07-09) |
| `enviar_convocatoria(cedulas, semana, modo_prueba, correo_prueba, regional, dia)` | `POST /admin/enviar-convocatoria` | Envía correos de convocatoria a supletorio, con modo prueba, recopilatorio al jefe y resumen ejecutivo a coordinación (2026-07-09) |
| `get_envios_convocatoria(anio, regional, modo_prueba)` | `GET /analitica/envios-convocatoria` | Historial/auditoría de convocatorias ya enviadas, protegido por `X-Admin-Token` (2026-07-09) |
| `get_regional_dia_configurado(regional)` | `GET /analitica/regional-dia-configurado` | `bool` — si la regional tiene `día` cargado para al menos un colaborador (2026-07-10) |
| `get_reporte_pendientes_excel(anio)` | `GET /analitica/reporte-supletorios-pendientes` | Descarga el reporte Excel de supletorios pendientes (bytes), sección Reportería (2026-07-13) |
| `get_reporte_pendientes_html(anio)` | `GET /analitica/reporte-supletorios-pendientes-html` | Descarga la vista interactiva HTML de supletorios pendientes (bytes), sección Reportería (2026-07-13) |
| `get_cursos(anio, regional)` | `GET /cursos/` | Lista cursos ya cargados, para los selectores de "Supletorio existente" y "Novedades" en Administración (2026-07-13) |
| `cargar_curso(archivo_bytes, nombre_archivo, modo, ...)` | `POST /admin/cargar-curso` | Sube el CSV de Moodle (multipart), modo `nuevo`/`supletorio` con sus parámetros específicos — sección Administración (2026-07-13) |
| `crear_empleado(payload)` | `POST /admin/empleados` | Alta de un empleado nuevo (Flujo 2 de Administración) a partir del formulario de una cédula sin match (2026-07-13) |
| `get_no_rindieron(curso_id)` | `GET /analitica/curso/{curso_id}/no-rindieron` | Activos de la regional del curso sin ninguna nota, separados en `sin_notificar`/`pendientes_resolver` — sección Novedades (2026-07-13) |
| `enviar_novedad(curso_id, cedulas, modo_prueba, correo_prueba)` | `POST /admin/curso/{curso_id}/enviar-novedad` | Envía la novedad agrupada por jefe, con modo prueba obligatorio; crea las notas `PENDIENTE_JUSTIFICACION` en envío real (2026-07-13) |
| `resolver_nota(nota_id, estado)` | `PATCH /admin/notas/{nota_id}/resolver` | Resuelve una nota `PENDIENTE_JUSTIFICACION` in place hacia F/J/NA/V/Exonerado/Asistencia (2026-07-13) |
| `set_convocatoria_habilitada(curso_id, habilitada)` | `PATCH /admin/curso/{curso_id}/convocatoria-habilitada` | Activa/desactiva si un curso cuenta para Convocatoria — panel "Convocatoria por curso" en Administración (2026-07-14) |
| `marcar_na(curso_id, cedulas)` | `POST /admin/curso/{curso_id}/marcar-na` | Marca `NO_APLICA` directo para las cédulas seleccionadas, sin pasar por Novedades — atajo tras cargar un curso nuevo (2026-07-14) |
| `enviar_resumen_consolidado(semana, modo_prueba, dia, correo_prueba)` | `POST /admin/enviar-resumen-consolidado` | Un solo correo a la jefatura con Quito y TS R2 en dos secciones, agregando los envíos ya hechos esa semana (2026-07-17) |
| `set_evaluado(curso_id, evaluado)` | `PATCH /admin/curso/{curso_id}/evaluado` | Excluye/incluye un curso de "pendiente de supletorio" — cursos de solo-asistencia sin examen (2026-07-20) |
| `actualizar_observacion_nota(nota_id, observacion)` | `PATCH /admin/notas/{nota_id}/observacion` | Edita la observación libre de cualquier nota, sin restricción de estado — sección "Observaciones de notas" (2026-07-20) |
| `get_emails_enviados(tipo, cedula, modo_prueba, dia)` | `GET /analitica/emails-enviados` | Lista (metadatos) de correos ya enviados por el sistema — sección "Correos archivados" en Convocatoria (2026-07-20) |
| `get_email_enviado_html(email_id)` | `GET /analitica/emails-enviados/{id}/html` | Descarga el HTML real archivado de un correo puntual (2026-07-20) |
| `get_emails_enviados_zip(ids, tipo, cedula, modo_prueba, dia)` | `GET /analitica/emails-enviados/zip` | Descarga masiva en `.zip` — por `ids` específicos (seleccionados) o por los mismos filtros de la lista (todos los filtrados) (2026-07-20) |
| `get_reporte_asistencia_excel(anio, regional)` / `get_reporte_asistencia_html(anio, regional)` | `GET /analitica/reporte-asistencia[-html]` | Reporte de todos los estados sin nota numérica, segmentado por regional (2026-07-20) |
| `get_reporte_calificaciones_excel(anio, regional)` / `get_reporte_calificaciones_html(anio, regional)` | `GET /analitica/reporte-calificaciones[-html]` | Libro de calificaciones completo del año, segmentado por regional (2026-07-20) |
| `get_reporte_calificaciones_macro_excel(anio, mes_desde, mes_hasta, combinado)` | `GET /analitica/reporte-calificaciones-macro` | Descarga el reporte Excel en formato matriz idéntico al macro manual real, con fórmulas de resumen (COUNTIF/COUNT/SUM) y toggle de supletorios combinados — 4º tipo de reporte en Reportería (2026-07-21) |

Todas las funciones usan `@st.cache_data(ttl=900)`, **excepto** las 17 de arriba (`get_convocatoria_preview` en adelante, incluyendo las 8 de Administración) — son escrituras o lecturas sensibles a cambios recientes, no se cachean. Para refrescar manualmente las que sí cachean: botón "Limpiar caché" en el sidebar.

Las 6 funciones de Administración usan un nuevo helper, `_post_file()` en `api_client.py` — igual que `_post()` pero manda `multipart/form-data` (vía el parámetro `files` de `requests`) en vez de JSON, con `X-Admin-Token` y timeout 120s (más alto que el resto porque sube un archivo), usado solo por `cargar_curso()`.

`get_envios_convocatoria` usa un helper nuevo, `_get_admin()` en `api_client.py` — igual que `_get()` pero manda `X-Admin-Token`, porque el endpoint de auditoría es de lectura pero sigue protegido (no se expone historial de envíos sin token).

`get_reporte_pendientes_excel`/`_html` usan otro helper nuevo, `_get_bytes()` — igual que `_get()` pero devuelve `r.content` (bytes) en vez de `r.json()`, porque estos dos endpoints no devuelven JSON sino un archivo binario/texto para descargar directo con `st.download_button`.

`get_email_enviado_html`/`get_emails_enviados_zip` usan `_get_bytes_admin()` (2026-07-20) — combina los dos anteriores: bytes en vez de JSON, **y** manda `X-Admin-Token`, porque el contenido de los correos archivados es sensible (direcciones reales, nombres) y no debe quedar expuesto sin token como sí lo están los reportes de Reportería.

Timeout de requests: 30s en lecturas (`_get`), 60s en escrituras (`_patch`/`_post`, usadas por la tab Convocatoria — el envío de correos puede tardar más).

Las escrituras (`PATCH`/`POST`) requieren `ADMIN_TOKEN` en `.streamlit/secrets.toml`, enviado como header `X-Admin-Token` — debe coincidir con `ADMIN_TOKEN` en el `.env` de `telcou-api`.

---

## Seguridad (fixes 2026-07-01)

- **XSS:** `badge()` en `ui/styles.py` aplica `html.escape()` al label antes de insertarlo en el `<span>` (el HTML se renderiza con `unsafe_allow_html=True`, así que cualquier valor de `estado` no confiable debía escaparse)
- **Path/query injection:** la cédula se URL-encodea con `urllib.parse.quote(cedula, safe='')` en `api_client.py` antes de interpolarla en la ruta (`/empleados/{cedula}/...`)
- **Timeout:** subido de 10s a 30s en `_get()` para evitar cortes prematuros en `listado-cursos`
- **`enableXsrfProtection`**: en `false` en `.streamlit/config.toml` — alineado intencionalmente así porque Streamlit Cloud maneja su propio proxy/CSRF; no reactivar sin probar en producción primero

### Seguridad (feature Convocatoria, 2026-07-09)

- Las escrituras (`PATCH /empleados/{cedula}/dia`, `POST /admin/enviar-convocatoria`) y el nuevo endpoint de auditoría (`GET /analitica/envios-convocatoria`) requieren `X-Admin-Token` en la API — el dashboard lo manda desde `.streamlit/secrets.toml`, nunca queda expuesto al navegador (Streamlit lo mantiene server-side)
- El envío real de correo usa credenciales SMTP reales (`smtp.telconet.ec`) que viven solo en `.env` de `telcou-api` (gitignoreado) — la contraseña se reutilizó de una cuenta ya validada en otro proyecto interno que la tenía hardcodeada en texto plano; pendiente rotarla
- **Modo prueba por defecto ON** en la UI — hay que apagarlo conscientemente para un envío real; es la salvaguarda principal contra enviar correos a empleados reales por error durante pruebas. Cubre los 3 correos de una tanda (individual, recopilatorio al jefe, resumen ejecutivo a coordinación), no solo el correo al empleado
- El historial de envíos (auditoría) es de solo lectura, no expone nada sin token, y el dashboard nunca se conecta directo a la base de datos — todo pasa por la API, por diseño (evita duplicar lógica de acceso a datos y mantiene un único punto de control de permisos)

---

## Trazabilidad de supletorios

La tabla muestra por cada curso donde el empleado tuvo supletorio:

| Curso | Nota | Supletorio 1 | Supletorio 2 | Resultado |
|-------|------|:------------:|:------------:|-----------|
| FIBRA ÓPTICA | 6.00 | 5.00 | 8.00 | APROBADO |
| PRIMEROS AUXILIOS | — | 4.00 | — | REPROBADO |

- **Nota** = nota regular original (motivo del supletorio)
- **Supletorio 1** = primer intento (`convocatoria=1`)
- **Supletorio 2** = segundo intento (`convocatoria=2`) — antes solo existía en Quito; desde 2026-07-06 la API también tiene `convocatoria=2` para TS R2 (380 notas)
- **Resultado** = estado del último intento — definitivo
- Celdas coloreadas por estado

---

## Secrets (no commitear)

`.streamlit/secrets.toml`:
```toml
API_BASE_URL = "http://localhost:8000"
```

Para apuntar a producción cambiar la URL.
