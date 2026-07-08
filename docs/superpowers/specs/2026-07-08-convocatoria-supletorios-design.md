# Ventana de Convocatoria a Supletorios — Diseño

**Fecha:** 2026-07-08
**Repos afectados:** `telcou-api` (backend, `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api`) y `dashboard-telcou-s1` (frontend, este repo)

## 1. Alcance

Una tab nueva **"📧 Convocatoria"** en el dashboard con dos capacidades relacionadas, sobre el mismo dato base (`día` de capacitación) y la misma audiencia (empleados con supletorio pendiente):

1. **Gestión del día de capacitación** — cambiar el día asignado a un empleado (con motivo, permanente o solo para una semana puntual), con trazabilidad completa.
2. **Envío masivo de correos de convocatoria** — a los empleados con supletorio pendiente asignados a un día/regional, con sus notas, nombres de curso y links.

Esto es específicamente para **convocatorias a supletorios** — un proceso periódico (una semana cada cierto tiempo), no recurrente semana a semana. Es un proceso distinto al de "capacitación ordinaria" que maneja el proyecto legado `Envio convocatorias antiguo` (envío automático recurrente, con correos a jefes, generación de Excel de asistencia y QR de WhatsApp) — ese proyecto queda fuera, no se reutiliza su código ni su alcance, solo se tomó como referencia su configuración SMTP ya validada y el patrón de plantilla HTML.

Fuera de alcance por ahora (explícitamente descartado en el diseño): aula, modalidad, y las hojas `CONFIG_SEMANAS`/`CONFIG_CAPACITACIONES`/`NOVEDADES_LOG` del Excel de Israel (sistema de ciclos semanales de capacitación ordinaria en TS R2). Correos a jefes inmediatos, Excel de asistencia, QR de WhatsApp (existían en el proyecto legado, no se piden aquí).

## 2. Modelo de datos (telcou-api)

### `variables_adicionales` — se agrega columna faltante
- `correo` (String) — correo del propio empleado. Hoy la tabla solo tiene `jefe_correo`; la hoja BASE del Excel sí trae el correo del empleado (columna 4) pero no se importaba.
- `dia` (ya existe) — al importar se normaliza a `LUNES`..`VIERNES` (mayúsculas, trim, corrigiendo variantes mal escritas comunes) o `NULL` si el valor no es un día real (`SALIÓ`, `CAMBIO`, `NO RECIBE CAPACITACIONES`, vacío). Esos estados especiales ya se reflejan en `Empleado.inactivo`/`tipo_movimiento`, no hace falta duplicarlos en `dia`.

### Tabla nueva `dia_cambios`
Sirve como log de auditoría Y como fuente de excepciones activas — una sola tabla para ambos propósitos.

| Campo | Tipo | Nota |
|---|---|---|
| `id` | Integer PK | |
| `empleado_id` | FK → empleados | |
| `dia_nuevo` | String | `LUNES`..`VIERNES` |
| `tipo` | String | `PERMANENTE` \| `SEMANAL` |
| `semana_inicio` | Date, nullable | Solo si `tipo=SEMANAL` — el lunes de la semana a la que aplica |
| `motivo` | Text | |
| `editado_por` | String, nullable | Texto libre, opcional (no hay login — administración única por ahora) |
| `fecha_creacion` | DateTime | default now |

**Regla de resolución — "día efectivo" de un empleado para una semana dada:**
- Si `tipo=PERMANENTE`: al insertar el log, también se actualiza `variables_adicionales.dia` en el mismo momento (la tabla base ya queda al día, no hace falta resolver nada extra al leer).
- Si `tipo=SEMANAL`: **no** se toca `variables_adicionales.dia`. Al calcular quién está convocado un día X en una semana W: si existe una fila `SEMANAL` con `semana_inicio=W` para ese empleado, se usa su `dia_nuevo`; si no, se usa `variables_adicionales.dia` (el día base).

### Tabla nueva `envios_convocatoria`
Historial de correos enviados, para no reenviar por error y para poder filtrar reintentos.

| Campo | Tipo |
|---|---|
| `id` | Integer PK |
| `empleado_id` | FK → empleados |
| `curso_id` | FK → cursos |
| `fecha_envio` | DateTime |
| `enviado_por` | String, nullable |
| `modo_prueba` | Boolean, default false |

Una fila por `(empleado, curso)` notificado. Los envíos en modo prueba se registran igual (con `modo_prueba=true`) para trazabilidad, pero no cuentan como "ya se le avisó de verdad" al mostrar el aviso de reenvío en la vista previa.

## 3. Endpoints nuevos (telcou-api)

Los de escritura (`PATCH`, `POST /admin/...`) requieren header `X-Admin-Token`, mismo mecanismo que `/admin/importar`.

| Método | Ruta | Qué hace |
|---|---|---|
| `PATCH` | `/empleados/{cedula}/dia` | Body: `{dia_nuevo, tipo, semana_inicio?, motivo, editado_por?}`. Aplica el cambio (permanente o semanal) e inserta en `dia_cambios`. |
| `GET` | `/empleados/{cedula}/dia-historial` | Lista de cambios de día de ese empleado, más recientes primero. |
| `GET` | `/analitica/convocatoria-preview?dia=&regional=&semana=` | Resuelve el "día efectivo" de cada empleado de esa regional para esa semana, cruza con `/analitica/supletorios-pendientes`, y devuelve por empleado: cursos pendientes (nombre, nota, `curso.url_telcou`), si tiene `correo` registrado, y si ya existe un envío no-prueba en `envios_convocatoria` para alguno de esos cursos. |
| `GET` | `/analitica/supletorios-pendientes/buscar?nombre=&regional=` | Búsqueda por nombre dentro del universo de pendientes (para el buscador "Agregar por nombre"), sin filtrar por día. |
| `POST` | `/admin/enviar-convocatoria` | Body: `{cedulas: [...], semana, modo_prueba: bool, correo_prueba?: str}`. Envía un correo por empleado (todos sus cursos pendientes listados adentro), registra cada envío en `envios_convocatoria`, y devuelve `{enviados: [...], fallidos: [...]}`. Ejecución síncrona, `SMTP_TIMEOUT` configurable. Si `modo_prueba=true`, todos los correos de la tanda se redirigen a `correo_prueba` (obligatorio en ese caso) — el nombre real del destinatario queda visible en el asunto/cuerpo para poder revisar la plantilla. |

## 4. Configuración SMTP

Ya aplicada en `.env` de `telcou-api` (real) y `.env.example` (plantilla sin secreto), reutilizando la cuenta ya validada en el proyecto `TelcoU_Notificaciones`:

```
SMTP_HOST=smtp.telconet.ec
SMTP_PORT=465
SMTP_USER=telcou_aut@telconet.ec
SMTP_PASSWORD=<en .env, no en .env.example>
SMTP_FROM=telcou_aut@telconet.ec
SMTP_FROM_NAME=Capacitaciones TelcoU
SMTP_USE_SSL=true
SMTP_TIMEOUT=60
```

`smtplib.SMTP_SSL` (no STARTTLS/587 — el proyecto legado probó ambos y SSL/465 es el que funciona contra `smtp.telconet.ec`). Sin dependencias nuevas (`smtplib` + `email.mime` de la librería estándar).

**Nota de seguridad:** esta contraseña estaba hardcodeada en texto plano en `TelcoU_Notificaciones/scripts/enviar_notificaciones.py` y en `Envio convocatorias antiguo/.../config.json` (con otra cuenta). Se reutilizó por rapidez (decisión del usuario) pero queda pendiente rotarla — no es urgente para este proyecto ya que aquí vive solo en `.env` gitignoreado.

## 5. UI en el dashboard

Tab nueva **"📧 Convocatoria"**, vista unificada (una sola pantalla):

1. **Filtros:** Regional (TS R2 / Quito — Quito queda visible en el selector aunque hoy no tenga datos, para cuando se cargue su Excel) · Día (`LUNES`-`VIERNES`) · Semana (date_input, default = lunes de la semana actual) → botón "Cargar convocatoria del día".
2. **Tabla principal** — resultado de `GET /analitica/convocatoria-preview`: checkbox (marcado por defecto) · Nombre · Cursos pendientes (nombre + nota cada uno, con link) · ¿Correo? · ¿Ya enviado antes? (aviso, no bloquea). Fila sin correo: sin checkbox disponible.
3. **Acción "Cambiar día"** por fila — abre mini-formulario (día nuevo, tipo permanente/semanal + selector de semana si aplica, motivo, editado por) → `PATCH /empleados/{cedula}/dia` → la persona sale de la tabla principal al guardar.
4. **Buscador "Agregar por nombre"** — busca solo entre empleados con supletorio pendiente (`GET /supletorios-pendientes/buscar`), sin importar su día actual. Al elegir uno, mismo mini-formulario que en (3), con día nuevo pre-cargado al día que se está armando. Al guardar, aparece en la tabla principal.
5. **Envío:**
   - Toggle **"Modo prueba"** (default siempre ON al cargar la tab — hay que apagarlo conscientemente para un envío real) + campo "Correo de prueba" (obligatorio si el modo está activo).
   - Botón "Confirmar y enviar a los N seleccionados" → `POST /admin/enviar-convocatoria` → resumen final (✅ enviados / ❌ fallidos con motivo). En modo prueba, el resumen aclara "(modo prueba — redirigido a `correo_prueba`)".

**Autenticación hacia la API:** `ADMIN_TOKEN` se agrega a `.streamlit/secrets.toml` (server-side, nunca llega al navegador); `api_client.py` lo incluye como header `X-Admin-Token` en los `PATCH`/`POST` nuevos. Se agregan helpers `_patch()` y `_post()` en `api_client.py` (hoy solo existe `_get()`), sin `@st.cache_data` (son escrituras).

## 6. Manejo de errores

- **SMTP caído/timeout en un envío puntual:** no aborta el lote — cada envío se intenta independiente; los fallidos aparecen en el resumen con motivo y no quedan registrados en `envios_convocatoria` (permite reintentar solo esos).
- **Empleado sin correo:** excluido de los checkboxes en la vista previa, no se intenta enviar.
- **Cambio de día a alguien sin pendiente activo:** el buscador ya filtra solo pendientes, pero el `PATCH` no depende de tener un pendiente — si el estado cambió entre cargar la lista y guardar, el cambio de día igual aplica (es una acción independiente del cálculo de "quién aparece en la lista").
- **API caída al abrir la tab:** mismo patrón que el resto del dashboard — `st.error` con mensaje claro, no pantalla en blanco.

## 7. Verificación

Dado que toca correos reales:
1. Verificar en navegador (mismo patrón Playwright usado para "Detalle de Pendientes") que la tabla carga filtrada por día/regional, que "Cambiar día" saca a la persona de la lista al instante, y que "Agregar por nombre" la mete.
2. Probar el modo prueba primero — confirmar que el correo llega solo a `correo_prueba`, con el contenido/plantilla correctos (notas, nombres de curso, links) y el nombre real del destinatario visible en el cuerpo.
3. Recién con eso validado, probar un envío real a un único destinatario de control antes de usarlo para una tanda completa.
