# Administración — Carga de Notas por CSV — Diseño

**Fecha:** 2026-07-13
**Repos afectados:** `telcou-api` (backend, `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api`) y `dashboard-telcou-s1` (frontend, este repo)

## 1. Alcance

Una sección nueva **"🛠️ Administración"** en el sidebar del dashboard, con tres flujos conectados entre sí:

1. **Carga de curso desde CSV** — subir el export crudo de Moodle de un curso (nuevo o supletorio de uno existente) y convertirlo en filas `Nota`.
2. **Alta de empleado nuevo** — cuando una cédula del CSV no tiene match en la BD, completar los datos faltantes y crearlo, sin salir del flujo de carga.
3. **Novedades** — para un curso ya cargado, ver qué colaboradores activos de esa regional no tienen ninguna nota (no rindieron), notificar a su jefe inmediato agrupado, y resolver el estado final de cada uno cuando se sepa qué pasó.

Fuera de alcance por ahora (mencionado por el usuario como trabajo futuro, no se construye en esta iteración): lectura automática de las respuestas de correo de los jefes para resolver novedades sin intervención manual. El flujo de resolución en esta iteración es manual — el admin elige el estado final por persona.

## 2. Formato de entrada — CSV de Moodle

Export crudo de Moodle, uno por curso, confirmado que es siempre el mismo formato (Quito y TS R2 usan la misma plataforma). Ejemplo real inspeccionado: `ES26-EVALUACIÓN- ESTÁNDAR DE SOPORTE-calificaciones.csv.xls` (extensión `.xls` engañosa — es CSV, UTF-8 con BOM).

| Columna | Uso |
|---|---|
| `Nombre` | Nombre completo del colaborador |
| `Ciudad` | Informativo, no se usa (la regional la define el admin en el formulario) |
| `Departamento` | → `Empleado.area`, si hay que crear el empleado |
| `Dirección de correo` | → `VariableAdicional.correo`, si hay que crear el empleado |
| `Número de ID` | **Cédula** — verificado contra 4 empleados reales, coincide exacto incluyendo ceros a la izquierda (ej. `0503422164`). Se normaliza con `zfill(10)`, mismo criterio que los importadores existentes. |
| `Estado` | Informativo (`Finalizado`) — no se usa para lógica |
| `Calificación/10,00` | Nota, con coma decimal (formato Ecuador) — parsear reemplazando `,` por `.` |
| `P. 1 /1,00` … `P. 10 /1,00` | Puntaje por pregunta — se ignoran, no se guardan |

**Fila a descartar:** la última fila del export es un resumen "Promedio general" con `Nombre` vacío — se filtra por `Nombre` no vacío.

**Umbral de aprobación:** 7.5 (mismo valor que `importar_quito2026.py`/`importar_ts2026.py`) — `Calificación >= 7.5` → `APROBADO`, si no → `REPROBADO`.

## 3. Modelo de datos — sin migraciones

Verificado explícitamente: `Empleado` (`cedula, nombre, genero, area, jefe_inmediato, regional_id, inactivo, tipo_movimiento, sucursal`) y `VariableAdicional` (`correo, jefe_correo, jefe_inmediato, dia`) ya tienen todos los campos necesarios para el alta de un empleado nuevo. `Nota.estado` es una columna de texto libre (`String(30)`, sin `CHECK` de base de datos), así que un valor nuevo no requiere migración.

**Único valor nuevo:** `PENDIENTE_JUSTIFICACION` — estado de una nota creada automáticamente al enviar una "novedad" a un jefe, para un colaborador activo sin ninguna nota en ese curso. Significa "se le avisó al jefe, todavía sin resolver". `valor=None` (igual que `FALTA_INJUSTIFICADA`/`FALTA_JUSTIFICADA` hoy).

**Cuenta como pendiente de supletorio mientras no se resuelve** — se agrega a `NECESITA_SUPLETORIO` en `app/services/convocatoria.py`: `NECESITA_SUPLETORIO = {"REPROBADO", "FALTA_INJUSTIFICADA", "PENDIENTE_JUSTIFICACION"}`. Regla del usuario: *"falta hasta que se demuestre lo contrario"*.

**Resolución de una novedad** (acción manual del admin, catálogo ya existente en el sistema — no se inventan estados nuevos):
- **F** (`FALTA_INJUSTIFICADA`, `valor=None`) — no justificó, va directo a supletorio. Mismo criterio que ya usa todo el sistema (Convocatoria, Analítica, el marcador "F" de Reportería) — la nota queda idéntica a como se ve cualquier F que vino de la carga original, sin marca especial.
- **J** (`FALTA_JUSTIFICADA`, `valor=None`) — justificó con motivo válido, no exige supletorio.
- **NA** (`NO_APLICA`, `valor=None`) — no debía rendir ese curso (convocado por error). No exige supletorio.
- **V** (`VACACIONES`) u otro estado del catálogo existente si el caso lo amerita.

La fila `PENDIENTE_JUSTIFICACION` se actualiza in place (mismo `id` de `Nota`) al resolverse — no se crea una fila nueva.

## 4. Flujo 1 — Carga de curso desde CSV

Nuevo servicio `app/services/carga_notas.py`.

**Parser** (`parsear_csv_moodle(contenido: bytes) -> list[dict]`): lee con `encoding="utf-8-sig"`, filtra filas con `Nombre` vacío, devuelve `[{cedula, nombre, area, correo, nota: Decimal}]` por fila válida.

**Modo A — Curso nuevo.** El admin llena en el formulario: código, nombre, tipo (`PRESENCIAL`/`VIRTUAL`/`ZOOM`), mes, fecha inicio/fin, regional. Se crea (o actualiza si ya existe, mismo código+año+regional) el `Curso`, y cada fila del CSV se guarda como `Nota(tipo="REGULAR", convocatoria=1)`.

**Modo B — Supletorio de curso existente.** El admin elige un `Curso` ya cargado (selector, filtrable por regional/año) y un número de convocatoria (2, 3…). Cada fila se guarda como `Nota(tipo="SUPLETORIO", convocatoria=N)`, con `nota_original_id` apuntando al `id` de la nota `REGULAR` de esa misma persona+curso (si no existe una nota REGULAR previa para esa persona en ese curso, esa fila se reporta como error — no se puede tener un supletorio sin un regular al que enlazarlo).

**Upsert:** `ON CONFLICT (empleado_id, curso_id, tipo, convocatoria) DO UPDATE` — mismo patrón que los importadores existentes. Recargar un CSV del mismo curso corrige o completa sin duplicar.

**Cédulas sin match:** no bloquean el resto de la carga. Se acumulan en una lista `sin_match` que la UI usa para lanzar el Flujo 2 por cada una. En Modo B, si una cédula está en `sin_match` (persona nueva) esa fila tampoco tiene REGULAR previo que enlazar — cae también en el error de "sin regular al que enlazarlo", no se resuelve dando de alta al empleado (no debería existir un supletorio de alguien que nunca tomó el curso original).

**Auditoría:** cada carga registra una fila en la tabla `Importacion` ya existente (`archivo, regional_id, anio, tipo, registros_nuevos, registros_actualizados, registros_ignorados, importado_por`).

## 5. Flujo 2 — Alta de empleado nuevo

Para cada cédula sin match del CSV: el admin ve un formulario pre-llenado con lo que el CSV ya trae (`cedula`, `nombre`, `area` ← Departamento, `correo` ← Dirección de correo) y solo completa lo que falta:

- **Jefe inmediato** y **su correo** (obligatorios — sin esto, Convocatoria no puede notificarlo)
- **Sucursal** (solo si la regional del curso es TS R2)
- **Género** (opcional)

Al guardar: `INSERT` en `Empleado` + `VariableAdicional`, y automáticamente se procesa la fila pendiente de esa persona en el CSV que se estaba cargando (ya no queda en `sin_match`).

## 6. Flujo 3 — Novedades

**Consulta "quiénes no han rendido"** (automática al terminar una carga, y disponible después eligiendo cualquier curso ya cargado de una lista): activos (`Empleado.inactivo=False`) de la regional del curso, cruzados contra las notas que tengan para ese `curso_id`. Cada persona cae en uno de dos grupos, en la misma respuesta:
- **Sin nota todavía** — elegible para que se le envíe la novedad (`nota_id=None`).
- **Novedad ya enviada, pendiente de resolver** — tiene una `Nota` con `estado="PENDIENTE_JUSTIFICACION"` para ese curso (`nota_id` presente, es la que se actualiza al resolver).

Esto permite que el admin vuelva días después a la misma pantalla y siga viendo, sin tener que recordar nada, tanto a quién falta notificar como a quién falta resolver.

**Enviar novedad:** el admin selecciona a quiénes del primer grupo notificar (checkboxes, todos marcados por defecto) y confirma. Se agrupa por `jefe_correo` (mismo patrón que el recopilatorio de Convocatoria — un correo por jefe, no uno por persona) y se manda vía `mailer.py`, con **modo prueba obligatorio y ON por defecto**, igual que el resto del sistema. Al enviar (real o de prueba se registra igual, pero solo el envío real marca la nota), se crea `Nota(estado="PENDIENTE_JUSTIFICACION", tipo="REGULAR", convocatoria=1, valor=None)` para cada persona notificada de verdad — pasa del primer grupo al segundo.

**Resolver:** por cada persona del segundo grupo, el admin elige el estado final (F / J / NA / V / otro) desde un selector — actualiza la fila `Nota` existente in place (mismo `nota_id`), usando el `nota_id` que ya trae la consulta.

## 7. Endpoints nuevos (telcou-api)

Todos requieren `X-Admin-Token` (`Depends(verify_admin)`), mismo mecanismo que `/admin/importar`.

| Método | Ruta | Qué hace |
|---|---|---|
| `POST` | `/admin/cargar-curso` | Sube el CSV + metadata (modo A: código/nombre/tipo/mes/fechas/regional; modo B: curso_id + convocatoria). Devuelve `{nuevos, actualizados, sin_match: [{cedula, nombre, area, correo}]}` |
| `POST` | `/admin/empleados` | Crea un empleado nuevo (`Empleado` + `VariableAdicional`) a partir del formulario del Flujo 2 |
| `GET` | `/analitica/curso/{curso_id}/no-rindieron` | Activos de la regional del curso, separados en "sin nota" (`nota_id=None`) y "novedad pendiente de resolver" (`nota_id` de la nota `PENDIENTE_JUSTIFICACION`) |
| `POST` | `/admin/curso/{curso_id}/enviar-novedad` | Cédulas seleccionadas (del grupo "sin nota") + `modo_prueba` + `correo_prueba` — agrupa por jefe, envía, crea las notas `PENDIENTE_JUSTIFICACION` |
| `PATCH` | `/admin/notas/{nota_id}/resolver` | `{estado: "FALTA_INJUSTIFICADA"|"FALTA_JUSTIFICADA"|"NO_APLICA"|...}` — actualiza la nota `PENDIENTE_JUSTIFICACION` in place |

## 8. UI (dashboard-telcou-s1)

Nueva `ui/administracion.py`, sección **"🛠️ Administración"** (5ª entrada del sidebar).

- **Carga de curso:** `st.file_uploader` (CSV) + radio Curso nuevo / Supletorio existente, con los campos correspondientes a cada modo. Tras subir: resumen de nuevos/actualizados, y si hay `sin_match`, un formulario por cada cédula (Flujo 2) antes de considerar la carga completa.
- **Novedades:** selector de curso (de los ya cargados, con año/regional) → dos tablas separadas, ambas alimentadas por la misma consulta: (1) **"Sin notificar"** — checkboxes, todos marcados por defecto, botón "Enviar novedad a jefes" (con el toggle modo prueba ya establecido en el resto del sistema); (2) **"Pendientes de resolver"** — un selector de estado final (F/J/NA/V/…) por fila con botón para guardarlo. Ambas tablas se recalculan solas al recargar la sección, así que volver otro día muestra el estado real sin que el admin tenga que recordar nada.

## 9. Seguridad

- Todos los endpoints de escritura protegidos con `X-Admin-Token`, reusando `verify_admin` — sin duplicar lógica de auth.
- Modo prueba obligatorio y ON por defecto para el correo de novedades — mismo mecanismo y misma salvaguarda que Convocatoria.
- El CSV se procesa en memoria (`BytesIO`/`io.StringIO`), sin escribir a disco, mismo criterio que el reporte Excel/HTML de Reportería.
- Validación de cédula/nota por fila — una fila mal formada no aborta el resto de la carga, se reporta aparte.

## 10. Testing

TDD en el backend, igual que el resto del proyecto: parser del CSV (fila de promedio descartada, coma decimal, cédula con ceros a la izquierda), upsert de curso nuevo, upsert de supletorio con `nota_original_id` correcto (incluyendo el caso de error cuando no hay REGULAR previo), alta de empleado nuevo, consulta de no-rindieron (excluye inactivos, excluye quien ya tiene cualquier nota), envío de novedad agrupado por jefe con modo_prueba, resolución de una nota `PENDIENTE_JUSTIFICACION`, y que `PENDIENTE_JUSTIFICACION` cuente en `NECESITA_SUPLETORIO`.

## 11. Verificación

Con el CSV real de ejemplo (`ES26`, 746 filas): carga como curso nuevo en modo prueba contra una copia/tabla de prueba antes de tocar datos reales; confirmar el conteo de nuevos/actualizados/sin_match coincide con lo esperado; probar el flujo de alta de empleado con una cédula deliberadamente inexistente; confirmar que la consulta de no-rindieron excluye correctamente a inactivos y a quien ya tiene nota.
