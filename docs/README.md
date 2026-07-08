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
│   └── analitica.py          # Tab "Analítica" (nuevo)
├── .streamlit/
│   ├── config.toml           # Tema visual (azul oscuro #0F1623 + teal #00A8A8)
│   └── secrets.toml          # API_BASE_URL (no commitear)
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

Todas las funciones usan `@st.cache_data(ttl=900)`. Para refrescar manualmente: botón "Limpiar caché" en el sidebar.

Timeout de requests: 30s (subido de 10s — `listado-cursos` procesa ~77k notas y puede tardar unos segundos en frío).

---

## Seguridad (fixes 2026-07-01)

- **XSS:** `badge()` en `ui/styles.py` aplica `html.escape()` al label antes de insertarlo en el `<span>` (el HTML se renderiza con `unsafe_allow_html=True`, así que cualquier valor de `estado` no confiable debía escaparse)
- **Path/query injection:** la cédula se URL-encodea con `urllib.parse.quote(cedula, safe='')` en `api_client.py` antes de interpolarla en la ruta (`/empleados/{cedula}/...`)
- **Timeout:** subido de 10s a 30s en `_get()` para evitar cortes prematuros en `listado-cursos`
- **`enableXsrfProtection`**: en `false` en `.streamlit/config.toml` — alineado intencionalmente así porque Streamlit Cloud maneja su propio proxy/CSRF; no reactivar sin probar en producción primero

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
