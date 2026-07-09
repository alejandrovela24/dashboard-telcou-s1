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
├── app.py                    # Entry point — configura página y tabs
├── api_client.py             # Todas las llamadas a la API con caché
├── ui/
│   ├── styles.py             # CSS global, colores por estado, función badge()
│   ├── colaboradores.py      # Tab "Colaboradores"
│   ├── areas.py              # Tab "Áreas"
│   ├── analitica.py          # Tab "Analítica"
│   └── convocatoria.py       # Tab "Convocatoria" (nuevo — 2026-07-09)
├── .streamlit/
│   ├── config.toml           # Tema visual (azul oscuro #0F1623 + teal #00A8A8)
│   └── secrets.toml          # API_BASE_URL, ADMIN_TOKEN (no commitear)
└── docs/
    ├── README.md             # Este archivo
    └── superpowers/plans/    # Planes de implementación
```

---

## Tabs del dashboard

### 👥 Colaboradores
Busca empleados por nombre. Para cada uno muestra:
- Datos personales (área, jefe, regional, estado activo/inactivo)
- Métricas: total capacitaciones, promedio, faltas, supletorios
- Inasistencias y vacaciones (tabla coloreada)
- **Trazabilidad de supletorios** (tabla horizontal)
- Todas las notas regulares del período (expander)

### 🏢 Áreas
- Estadísticas agregadas por área organizacional
- Estadísticas por regional (Quito / TS R2)
- Estadísticas por sucursal dentro de TS R2

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

Ventana para gestionar el día de capacitación de cada empleado y para enviar convocatorias de supletorio por correo. Solo TS R2 tiene datos hoy (`día`/`correo` vienen de `variables_adicionales`, poblada desde el Excel de Israel — ver `TelcoU DB API`).

- **Filtros:** Regional (TS R2 / Quito) · Día (LUNES-VIERNES) · Semana → botón "Cargar convocatoria del día"
- **Tabla principal:** convocados de ese día (día efectivo — ver más abajo), con sus cursos pendientes (nombre, nota, link), si tienen correo registrado, y si ya se les envió antes. Cada fila tiene una acción **"Cambiar día"**.
- **Cambiar día** (por fila, o desde el buscador): formulario con día nuevo, tipo (`SEMANAL` = solo esa semana, vuelve a su día normal después; `PERMANENTE` = cambia su día de base), motivo, editado por (opcional). Con trazabilidad completa (`GET /empleados/{cedula}/dia-historial`).
- **"Día efectivo"**: si el empleado tiene una excepción `SEMANAL` vigente para la semana consultada, se usa ese día; si no, se usa su día base (`variables_adicionales.dia`).
- **Buscador "Agregar por nombre":** busca solo entre empleados con supletorio pendiente (de cualquier día), para agregarlos al día que se está armando.
- **Envío:** checkbox por persona (marcado por defecto) · toggle **"Modo prueba"** (por defecto ON — hay que apagarlo conscientemente para un envío real; en modo prueba todos los correos de la tanda se redirigen al correo de prueba, con el nombre real del destinatario visible en el cuerpo) · botón "Confirmar y enviar" → resumen final (enviados/fallidos).

> **Verificado en producción (2026-07-09):** un envío real en modo prueba a un empleado real de TS R2 llegó correctamente redirigido a `telcou_aut@telconet.ec` (no al correo real del empleado), registrando 4 filas en `envios_convocatoria` con `modo_prueba=True` sin marcar al empleado como "ya enviado" (los envíos de prueba no cuentan como notificación real).

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
| `get_areas(anio, regional)` | `GET /analitica/areas` | Stats por área |
| `get_regionales(anio)` | `GET /analitica/regionales` | Stats por regional |
| `get_sucursales(anio, regional, nombre)` | `GET /analitica/sucursales` | Stats por ciudad dentro de una regional — `nombre` (2026-07-01) filtra por capacitación seleccionada |
| `get_listado_cursos(anio, mes, nombre)` | `GET /analitica/listado-cursos` | Stats por capacitación con desglose Quito/R2 |
| `get_supletorios_pendientes(anio, regional, curso, sucursal)` | `GET /analitica/supletorios-pendientes` | Listado detallado por empleado de supletorios pendientes (2026-07-07) |
| `get_convocatoria_preview(dia, regional, semana)` | `GET /analitica/convocatoria-preview` | Convocados de un día/regional/semana, con cursos pendientes, correo y estado de envío (2026-07-09) |
| `buscar_supletorios_pendientes(nombre, anio, regional)` | `GET /analitica/supletorios-pendientes/buscar` | Búsqueda por nombre entre pendientes, para el buscador "Agregar por nombre" (2026-07-09) |
| `get_dia_historial(cedula)` | `GET /empleados/{cedula}/dia-historial` | Trazabilidad de cambios de día de un empleado (2026-07-09) |
| `cambiar_dia_empleado(cedula, dia_nuevo, tipo, motivo, semana_inicio, editado_por)` | `PATCH /empleados/{cedula}/dia` | Cambia el día de capacitación (permanente o solo-una-semana) (2026-07-09) |
| `enviar_convocatoria(cedulas, semana, modo_prueba, correo_prueba)` | `POST /admin/enviar-convocatoria` | Envía correos de convocatoria a supletorio, con modo prueba (2026-07-09) |

Todas las funciones usan `@st.cache_data(ttl=900)`, **excepto** las 5 nuevas de arriba (`get_convocatoria_preview` en adelante) — son escrituras o lecturas sensibles a cambios recientes, no se cachean. Para refrescar manualmente las que sí cachean: botón "Limpiar caché" en el sidebar.

Timeout de requests: 30s en lecturas (`_get`), 60s en escrituras (`_patch`/`_post`, usadas por la tab Convocatoria — el envío de correos puede tardar más).

Las escrituras (`PATCH`/`POST`) requieren `ADMIN_TOKEN` en `.streamlit/secrets.toml`, enviado como header `X-Admin-Token` — debe coincidir con `ADMIN_TOKEN` en el `.env` de `telcou-api`.

---

## Seguridad (fixes 2026-07-01)

- **XSS:** `badge()` en `ui/styles.py` aplica `html.escape()` al label antes de insertarlo en el `<span>` (el HTML se renderiza con `unsafe_allow_html=True`, así que cualquier valor de `estado` no confiable debía escaparse)
- **Path/query injection:** la cédula se URL-encodea con `urllib.parse.quote(cedula, safe='')` en `api_client.py` antes de interpolarla en la ruta (`/empleados/{cedula}/...`)
- **Timeout:** subido de 10s a 30s en `_get()` para evitar cortes prematuros en `listado-cursos`
- **`enableXsrfProtection`**: en `false` en `.streamlit/config.toml` — alineado intencionalmente así porque Streamlit Cloud maneja su propio proxy/CSRF; no reactivar sin probar en producción primero

### Seguridad (feature Convocatoria, 2026-07-09)

- Las escrituras (`PATCH /empleados/{cedula}/dia`, `POST /admin/enviar-convocatoria`) requieren `X-Admin-Token` en la API — el dashboard lo manda desde `.streamlit/secrets.toml`, nunca queda expuesto al navegador (Streamlit lo mantiene server-side)
- El envío real de correo usa credenciales SMTP reales (`smtp.telconet.ec`) que viven solo en `.env` de `telcou-api` (gitignoreado) — la contraseña se reutilizó de una cuenta ya validada en otro proyecto interno que la tenía hardcodeada en texto plano; pendiente rotarla
- **Modo prueba por defecto ON** en la UI — hay que apagarlo conscientemente para un envío real; es la salvaguarda principal contra enviar correos a empleados reales por error durante pruebas

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
