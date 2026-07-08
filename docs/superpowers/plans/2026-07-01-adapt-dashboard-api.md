# Dashboard TelcoU — Adaptación a API REST

> **Para workers agentes:** SUB-SKILL REQUERIDA: Usar `superpowers:subagent-driven-development` (recomendado) o `superpowers:executing-plans` para implementar este plan tarea por tarea. Los pasos usan sintaxis checkbox (`- [ ]`) para seguimiento.

**Goal:** Reemplazar la fuente de datos Google Sheets del dashboard-telcou-s1 por llamadas a `telcou-api` (FastAPI + PostgreSQL), y aplicar el tema visual teal/azul oscuro del framework parcial.

**Architecture:** El dashboard pasa de leer CSVs de Google Sheets a consumir una API REST local. Se extrae la lógica en módulos separados: `api_client.py` para todas las llamadas HTTP, y una carpeta `ui/` con un archivo por tab. `app.py` queda como punto de entrada + sidebar.

**Tech Stack:** Python 3.12, Streamlit 1.57, `requests` para HTTP, `pandas` para tablas, `streamlit-authenticator` no se usa en este proyecto (ese es el otro proyecto).

## Global Constraints

- Directorio de trabajo: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1`
- NO tocar `C:\Users\USUARIO\Desktop\TelcoU DB new` bajo ninguna circunstancia
- La API corre en `http://localhost:8000` (configurable via `st.secrets["API_BASE_URL"]`)
- Campos eliminados (no existen en la API): `dia_capacitacion`, `aula`, `cod`, `correo`, `jefe_correo`
- El estado "VACACIONES" SÍ existe en la API (el importer mapea "V" → "VACACIONES") → mostrar en badge amarillo, no cuenta como falta
- Mapeo de estados API → UI:
  - `FALTA_INJUSTIFICADA` → F (rojo)
  - `FALTA_JUSTIFICADA` → J (verde)
  - `APROBADO` → nota numérica verde
  - `REPROBADO` → nota numérica roja
  - `ASISTENCIA` → asistencia sin nota (azul)
  - `EXONERADO` → exonerado (gris)
  - `COPIA` → penalizado (naranja)
- Caché de API: TTL 900 segundos (`@st.cache_data(ttl=900)`)
- Año por defecto: 2025 (S1)
- Tema visual: azul oscuro `#0F1623`, teal `#00A8A8`, texto `#E2E8F0`

---

## Mapa de Archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `api_client.py` | Crear | Todas las llamadas HTTP a telcou-api, caché, manejo de errores |
| `ui/__init__.py` | Crear | Package marker vacío |
| `ui/styles.py` | Crear | CSS custom, tema azul/teal, logo sidebar |
| `ui/colaboradores.py` | Crear | Renderizado completo del tab Colaboradores |
| `ui/areas.py` | Crear | Renderizado completo del tab Áreas (por área, regional y sucursal) |
| `app.py` | Reescribir | Entry point: sidebar, tabs, routing, logo |
| `.streamlit/config.toml` | Modificar | Colores teal/azul oscuro del framework parcial |
| `.streamlit/secrets.toml` | Modificar | Agregar `API_BASE_URL` |
| `secrets_TEMPLATE.toml` | Modificar | Documentar `API_BASE_URL` |
| `requirements.txt` | Modificar | Agregar `requests>=2.31.0` |

---

## Referencia: Endpoints de la API que se usarán

```
GET /empleados/                         → lista de empleados (filtros: area, regional, anio, inactivo)
GET /empleados/{cedula}/notas           → notas de un empleado (filtros: anio, mes, regional)
GET /empleados/{cedula}/resumen         → resumen anual (total, promedio, faltas, supletorios)
GET /empleados/{cedula}/trazabilidad    → historial original + supletorio
GET /analitica/areas                    → estadísticas agregadas por área
GET /analitica/regionales               → estadísticas por regional
GET /analitica/sucursales               → estadísticas por sucursal (requiere regional)
```

## Referencia: Campos disponibles en EmpleadoOut

```python
{
  "id": int,
  "cedula": str,
  "nombre": str,
  "genero": str | None,
  "area": str | None,
  "jefe_inmediato": str | None,
  "regional": {"id": int, "nombre": str},
  "inactivo": bool,
  "tipo_movimiento": str | None
}
```

## Referencia: Campos disponibles en NotaDetalleOut

```python
{
  "id": int,
  "curso_codigo": str,
  "curso_nombre": str,
  "mes": str | None,
  "anio": int,
  "valor": Decimal | None,
  "estado": str,           # APROBADO, REPROBADO, FALTA_INJUSTIFICADA, etc.
  "observacion": str | None,
  "tipo": str,             # REGULAR o SUPLETORIO
  "nota_original_id": int | None
}
```

---

## Tarea 1: Cliente API + Configuración

**Archivos:**
- Crear: `api_client.py`
- Modificar: `requirements.txt`
- Modificar: `.streamlit/secrets.toml`
- Modificar: `secrets_TEMPLATE.toml`

**Produce:** Funciones `get_empleados()`, `get_notas_empleado()`, `get_resumen_empleado()`, `get_trazabilidad_empleado()`, `get_areas()`, `get_regionales()` — todas cacheadas con TTL 900s.

- [ ] **Paso 1: Actualizar requirements.txt**

Contenido final de `requirements.txt`:
```
streamlit>=1.32.0
pandas>=2.0.0
numpy>=1.26.0
requests>=2.31.0
```

- [ ] **Paso 2: Instalar dependencias**

```bash
pip install "requests>=2.31.0"
```
Esperado: `Successfully installed requests-X.X.X` o `Requirement already satisfied`

- [ ] **Paso 3: Actualizar secrets.toml con API_BASE_URL**

Contenido de `.streamlit/secrets.toml`:
```toml
API_BASE_URL = "http://localhost:8000"
```
> Nota: Quitar SHEET_ID y demás GIDs — ya no se usan.

- [ ] **Paso 4: Actualizar secrets_TEMPLATE.toml**

```toml
# ============================================================
# SECRETS TEMPLATE — NO SUBIR ESTE ARCHIVO A GITHUB
# Copiar estos valores en:
# Streamlit Cloud → tu app → Settings → Secrets
# ============================================================

# URL base de telcou-api (FastAPI + PostgreSQL)
API_BASE_URL = "http://localhost:8000"
```

- [ ] **Paso 5: Crear api_client.py**

```python
import requests
import streamlit as st
from typing import Optional


def _base() -> str:
    return st.secrets.get("API_BASE_URL", "http://localhost:8000").rstrip("/")


def _get(path: str, params: dict = None) -> list | dict | None:
    try:
        r = requests.get(f"{_base()}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("No se puede conectar a la API. Verifica que telcou-api esté corriendo.")
        return None
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None
        st.error(f"Error de API ({e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error inesperado: {e}")
        return None


@st.cache_data(ttl=900, show_spinner=False)
def get_empleados(
    area: Optional[str] = None,
    regional: Optional[str] = None,
    anio: Optional[int] = None,
    inactivo: Optional[bool] = None,
) -> list[dict]:
    params = {}
    if area:     params["area"] = area
    if regional: params["regional"] = regional
    if anio:     params["anio"] = anio
    if inactivo is not None: params["inactivo"] = inactivo
    return _get("/empleados/", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_notas_empleado(
    cedula: str,
    anio: Optional[int] = None,
    mes: Optional[str] = None,
    regional: Optional[str] = None,
) -> list[dict]:
    params = {}
    if anio:     params["anio"] = anio
    if mes:      params["mes"] = mes
    if regional: params["regional"] = regional
    return _get(f"/empleados/{cedula}/notas", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_resumen_empleado(cedula: str, anio: int) -> dict | None:
    return _get(f"/empleados/{cedula}/resumen", {"anio": anio})


@st.cache_data(ttl=900, show_spinner=False)
def get_trazabilidad_empleado(cedula: str, anio: Optional[int] = None) -> list[dict]:
    params = {}
    if anio: params["anio"] = anio
    return _get(f"/empleados/{cedula}/trazabilidad", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_areas(anio: int, regional: Optional[str] = None) -> list[dict]:
    params = {"anio": anio}
    if regional: params["regional"] = regional
    return _get("/analitica/areas", params) or []


@st.cache_data(ttl=900, show_spinner=False)
def get_regionales(anio: int) -> list[dict]:
    return _get("/analitica/regionales", {"anio": anio}) or []
```

- [ ] **Paso 6: Verificar conexión a la API**

```bash
curl -s http://localhost:8000/empleados/ | python -c "import sys,json; d=json.load(sys.stdin); print(f'OK: {len(d)} empleados')"
```
Esperado: `OK: N empleados` (N ≥ 0)

> Si la API no está corriendo, iniciarla primero en `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api` con `uvicorn app.main:app --reload`

---

## Tarea 2: Tema Visual + Estilos

**Archivos:**
- Crear: `ui/__init__.py`
- Crear: `ui/styles.py`
- Modificar: `.streamlit/config.toml`

**Produce:** Función `inject_styles()` que inyecta CSS custom; `config.toml` con tema teal/azul del framework parcial.

- [ ] **Paso 1: Actualizar .streamlit/config.toml**

```toml
[theme]
base = "dark"
primaryColor = "#00A8A8"
backgroundColor = "#0F1623"
secondaryBackgroundColor = "#1A2332"
textColor = "#E2E8F0"
font = "sans serif"

[server]
headless = true
enableCORS = false
enableXsrfProtection = true

[browser]
gatherUsageStats = false
```

> Nota: `enableXsrfProtection` vuelve a `true` — era `false` solo para desarrollo del auth-test.

- [ ] **Paso 2: Crear ui/__init__.py**

```python
```
(Archivo vacío — solo marca el package)

- [ ] **Paso 3: Crear ui/styles.py**

```python
import streamlit as st


ESTADO_COLORS = {
    "APROBADO":            ("rgba(16,185,129,0.15)", "#10b981"),
    "ASISTENCIA":          ("rgba(59,130,246,0.15)", "#3b82f6"),
    "EXONERADO":           ("rgba(107,114,128,0.15)", "#6b7280"),
    "COPIA":               ("rgba(249,115,22,0.15)", "#f97316"),
    "REPROBADO":           ("rgba(239,68,68,0.15)", "#ef4444"),
    "FALTA_INJUSTIFICADA": ("rgba(239,68,68,0.15)", "#ef4444"),
    "FALTA_JUSTIFICADA":   ("rgba(234,179,8,0.15)", "#eab308"),
}

ESTADO_LABEL = {
    "APROBADO":            "Aprobado",
    "REPROBADO":           "Reprobado",
    "FALTA_INJUSTIFICADA": "Falta",
    "FALTA_JUSTIFICADA":   "Justificada",
    "ASISTENCIA":          "Asistencia",
    "EXONERADO":           "Exonerado",
    "COPIA":               "Copia",
}


def inject_styles() -> None:
    st.markdown("""
<style>
/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1f2d 0%, #0F1623 100%);
    border-right: 1px solid #1e3a4a;
}
[data-testid="stSidebar"] .stMarkdown h2 {
    color: #00A8A8;
    font-size: 0.8rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
}

/* ── Métricas ── */
[data-testid="metric-container"] {
    background: #1A2332;
    border: 1px solid #1e3a4a;
    border-radius: 8px;
    padding: 0.75rem 1rem;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    color: #94a3b8;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #E2E8F0;
    font-size: 1.5rem;
    font-weight: 700;
}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: #94a3b8;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #00A8A8;
    border-bottom-color: #00A8A8;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border: 1px solid #1e3a4a;
    border-radius: 8px;
}

/* ── Divider ── */
hr {
    border-color: #1e3a4a;
}

/* ── Info / Warning / Success blocks ── */
[data-testid="stInfo"]    { background: rgba(0,168,168,0.08); border-color: #00A8A8; }
[data-testid="stSuccess"] { background: rgba(16,185,129,0.08); }
[data-testid="stWarning"] { background: rgba(234,179,8,0.08); }
[data-testid="stError"]   { background: rgba(239,68,68,0.08); }
</style>
""", unsafe_allow_html=True)


def badge(estado: str) -> str:
    bg, color = ESTADO_COLORS.get(estado, ("rgba(100,100,100,0.15)", "#888"))
    label = ESTADO_LABEL.get(estado, estado)
    return (
        f'<span style="background:{bg};color:{color};border:1px solid {color}33;'
        f'padding:2px 8px;border-radius:12px;font-size:0.75rem;font-weight:600;">'
        f'{label}</span>'
    )


def style_notas_df(df):
    def row_style(row):
        estado = row.get("estado", "")
        bg, _ = ESTADO_COLORS.get(estado, ("", ""))
        return [f"background-color: {bg};" if bg else ""] * len(row)
    return df.style.apply(row_style, axis=1)
```

---

## Tarea 3: Tab Colaboradores

**Archivos:**
- Crear: `ui/colaboradores.py`

**Consumes:** `api_client.get_empleados`, `api_client.get_notas_empleado`, `api_client.get_resumen_empleado`, `api_client.get_trazabilidad_empleado`, `ui.styles.badge`, `ui.styles.style_notas_df`

**Produce:** Función `render_tab_colaboradores(anio: int)` que renderiza el tab completo.

- [ ] **Paso 1: Crear ui/colaboradores.py**

```python
import pandas as pd
import streamlit as st

import api_client as api
from ui.styles import badge, style_notas_df


MESES = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre",
]

ESTADOS_INASISTENCIA = {
    "FALTA_INJUSTIFICADA": ("F · Falta", "#ef4444"),
    "FALTA_JUSTIFICADA":   ("J · Justificada", "#eab308"),
}

ESTADOS_SUPLETORIO = {"APROBADO", "REPROBADO", "FALTA_INJUSTIFICADA"}


def render_tab_colaboradores(anio: int) -> None:
    with st.spinner("Cargando empleados..."):
        empleados = api.get_empleados(anio=anio)

    if not empleados:
        st.warning("No se encontraron empleados. Verifica que la API esté conectada.")
        return

    nombres = sorted({e["nombre"] for e in empleados if e.get("nombre")})

    with st.form("form_colab"):
        c1, c2 = st.columns([3, 1])
        with c1:
            seleccion = st.multiselect(
                "Colaborador(es) — escribe para filtrar",
                options=nombres,
                default=[],
                placeholder="Empieza a escribir…",
            )
        with c2:
            meses_sel = st.multiselect(
                "Mes(es)", options=MESES, default=MESES
            )
        st.form_submit_button("Aplicar")

    if not seleccion:
        st.info("Selecciona uno o más colaboradores.")
        return

    lookup = {e["nombre"]: e for e in empleados}

    for nombre in seleccion:
        emp = lookup.get(nombre)
        if not emp:
            st.warning(f"No encontrado: {nombre}")
            continue

        cedula = emp["cedula"]
        _render_empleado(emp, cedula, anio, meses_sel)
        st.divider()


def _render_empleado(emp: dict, cedula: str, anio: int, meses_sel: list[str]) -> None:
    estado_texto = "INACTIVO" if emp.get("inactivo") else "ACTIVO"
    regional = emp.get("regional", {}).get("nombre", "—")

    # ── Encabezado ──
    c1, c2 = st.columns([3, 2])
    with c1:
        st.subheader(f"👤 {emp['nombre']}")
        st.caption(f"Estado: **{estado_texto}** · Regional: **{regional}**")
        st.write(f"Área: **{emp.get('area', '—')}**")
        if emp.get("tipo_movimiento"):
            st.write(f"Tipo movimiento: **{emp['tipo_movimiento']}**")
    with c2:
        st.write(f"Cédula: **{cedula}**")
        st.write(f"Jefe: **{emp.get('jefe_inmediato', '—')}**")

    # ── Resumen ──
    with st.spinner("Cargando resumen..."):
        resumen = api.get_resumen_empleado(cedula, anio)

    if resumen:
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Capacitaciones", resumen.get("total_capacitaciones", 0))
        m2.metric("Promedio", f"{float(resumen['promedio']):.2f}" if resumen.get("promedio") else "—")
        m3.metric("Faltas (F)", resumen.get("faltas_injustificadas", 0))
        m4.metric("Justificadas (J)", resumen.get("faltas_justificadas", 0))
        m5.metric("Supletorios", resumen.get("supletorios", 0))

    # ── Notas ──
    with st.spinner("Cargando notas..."):
        notas = api.get_notas_empleado(cedula, anio=anio)

    if meses_sel:
        notas = [n for n in notas if n.get("mes") in meses_sel or n.get("mes") is None]

    notas_reg  = [n for n in notas if n.get("tipo") == "REGULAR"]
    notas_supe = [n for n in notas if n.get("tipo") == "SUPLETORIO"]

    # ── Inasistencias ──
    st.markdown("### 📌 Inasistencias")
    inasis = [n for n in notas_reg if n.get("estado") in ESTADOS_INASISTENCIA]

    if inasis:
        rows = []
        for n in inasis:
            label, _ = ESTADOS_INASISTENCIA[n["estado"]]
            rows.append({
                "Código":      n["curso_codigo"],
                "Curso":       n["curso_nombre"],
                "Mes":         n.get("mes", "—"),
                "Tipo":        label,
                "Observación": n.get("observacion") or "—",
            })
        df_inasis = pd.DataFrame(rows)

        def style_inasis(df):
            def row(r):
                color = (
                    "rgba(239,68,68,0.12)"  if "Falta"      in r["Tipo"] else
                    "rgba(234,179,8,0.12)"  if "Justificada" in r["Tipo"] else ""
                )
                return [f"background-color:{color};" if color else ""] * len(r)
            return df.style.apply(row, axis=1)

        st.dataframe(style_inasis(df_inasis), use_container_width=True)
    else:
        st.info("Sin inasistencias registradas para los filtros seleccionados.")

    # ── Supletorios ──
    st.markdown("### 🎯 Supletorios")
    if notas_supe:
        rows = []
        for n in notas_supe:
            estado = n.get("estado", "")
            rows.append({
                "Código":      n["curso_codigo"],
                "Curso":       n["curso_nombre"],
                "Mes":         n.get("mes", "—"),
                "Nota":        float(n["valor"]) if n.get("valor") is not None else None,
                "Estado":      estado,
                "Observación": n.get("observacion") or "—",
            })
        df_supe = pd.DataFrame(rows)

        def style_supe(df):
            def row(r):
                color = (
                    "rgba(16,185,129,0.12)"  if r["Estado"] == "APROBADO"  else
                    "rgba(239,68,68,0.12)"   if r["Estado"] == "REPROBADO" else ""
                )
                return [f"background-color:{color};" if color else ""] * len(r)
            return df.style.apply(row, axis=1)

        aprobados = sum(1 for n in notas_supe if n.get("estado") == "APROBADO")
        k1, k2, k3 = st.columns(3)
        k1.metric("Total Supletorios", len(notas_supe))
        k2.metric("Aprobados", aprobados)
        k3.metric("Pendientes / Reprobados", len(notas_supe) - aprobados)

        st.dataframe(style_supe(df_supe), use_container_width=True)
    else:
        st.info("Sin supletorios registrados.")

    # ── Todas las notas ──
    with st.expander("📋 Ver todas las notas del período"):
        if notas_reg:
            rows = []
            for n in notas_reg:
                rows.append({
                    "Código":  n["curso_codigo"],
                    "Curso":   n["curso_nombre"],
                    "Mes":     n.get("mes", "—"),
                    "Nota":    float(n["valor"]) if n.get("valor") is not None else None,
                    "Estado":  n.get("estado", ""),
                    "Obs":     n.get("observacion") or "—",
                })
            df_notas = pd.DataFrame(rows)
            st.dataframe(style_notas_df(df_notas), use_container_width=True)
        else:
            st.info("Sin notas regulares.")
```

---

## Tarea 4: Tab Áreas

**Archivos:**
- Crear: `ui/areas.py`

**Consumes:** `api_client.get_areas`, `api_client.get_regionales`

**Produce:** Función `render_tab_areas(anio: int)` que renderiza el tab completo.

- [ ] **Paso 1: Crear ui/areas.py**

```python
import pandas as pd
import streamlit as st

import api_client as api


def render_tab_areas(anio: int) -> None:
    with st.spinner("Cargando datos por área..."):
        areas_data = api.get_areas(anio=anio)

    if not areas_data:
        st.warning("No hay datos de áreas para el año seleccionado.")
        return

    df = pd.DataFrame(areas_data)

    # ── Métricas globales ──
    total_emp   = int(df["total_empleados"].sum())
    total_caps  = int(df["total_capacitaciones"].sum())
    prom_global = df["promedio"].mean(skipna=True)

    k1, k2, k3 = st.columns(3)
    k1.metric("Total Empleados", total_emp)
    k2.metric("Total Capacitaciones", total_caps)
    k3.metric("Promedio Global", f"{prom_global:.2f}" if pd.notna(prom_global) else "—")

    st.divider()

    # ── Filtro de área ──
    areas_list = sorted(df["area"].dropna().unique().tolist())
    filtro = st.multiselect("Filtrar por Área", options=areas_list, default=areas_list)
    df_filtrado = df[df["area"].isin(filtro)].copy() if filtro else df.copy()

    # ── Tabla ──
    df_show = df_filtrado.rename(columns={
        "area":                "Área",
        "promedio":            "Promedio",
        "total_empleados":     "Empleados",
        "total_capacitaciones":"Capacitaciones",
    })[["Área", "Empleados", "Capacitaciones", "Promedio"]]

    df_show["Promedio"] = df_show["Promedio"].apply(
        lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
    )

    st.markdown("### 🏢 Estadísticas por Área")
    st.table(df_show.sort_values("Área").reset_index(drop=True))

    # ── Regionales ──
    st.markdown("### 🗺️ Estadísticas por Regional")
    with st.spinner("Cargando regionales..."):
        reg_data = api.get_regionales(anio=anio)

    if reg_data:
        df_reg = pd.DataFrame(reg_data).rename(columns={
            "regional":            "Regional",
            "promedio":            "Promedio",
            "total_empleados":     "Empleados",
            "total_capacitaciones":"Capacitaciones",
        })[["Regional", "Empleados", "Capacitaciones", "Promedio"]]

        df_reg["Promedio"] = df_reg["Promedio"].apply(
            lambda x: f"{float(x):.2f}" if pd.notna(x) else "—"
        )
        st.table(df_reg.reset_index(drop=True))
    else:
        st.info("Sin datos de regionales.")
```

---

## Tarea 5: Reescribir app.py + Integración Final

**Archivos:**
- Reescribir: `app.py`

**Consumes:** `ui.styles.inject_styles`, `ui.colaboradores.render_tab_colaboradores`, `ui.areas.render_tab_areas`

**Produce:** App Streamlit completa con sidebar, selector de año, tabs Colaboradores y Áreas.

- [ ] **Paso 1: Reescribir app.py**

```python
import streamlit as st

from ui.styles import inject_styles
from ui.colaboradores import render_tab_colaboradores
from ui.areas import render_tab_areas

st.set_page_config(
    page_title="Dashboard Capacitación TELCOU",
    page_icon="📊",
    layout="wide",
)

inject_styles()

# ── Sidebar ──
with st.sidebar:
    st.markdown("## TELCOU")
    st.markdown("### 📊 Dashboard Capacitación")
    st.divider()

    anio = st.selectbox("Año", options=[2025, 2024, 2023], index=0)

    st.divider()
    st.caption("telcou-api · PostgreSQL")

    if st.button("🔄 Limpiar caché", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Header ──
st.title("📊 Dashboard Capacitación Técnica TELCOU")
st.caption(f"Año **{anio}** · Datos en tiempo real desde telcou-api")

# ── Tabs ──
tab_colab, tab_area = st.tabs(["👥 Colaboradores", "🏢 Áreas"])

with tab_colab:
    render_tab_colaboradores(anio)

with tab_area:
    render_tab_areas(anio)
```

- [ ] **Paso 2: Arrancar la app y verificar que carga**

```bash
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
streamlit run app.py --server.port 8502
```

Esperado: El dashboard abre en `http://localhost:8502` con tema azul/teal, sidebar con selector de año, y ambos tabs visibles.

- [ ] **Paso 3: Verificar tab Colaboradores**

1. Escribir un nombre de colaborador en el multiselect
2. Click "Aplicar"
3. Verificar que aparecen: encabezado con nombre/área/cédula, 5 métricas (Total Caps, Promedio, Faltas, Justificadas, Supletorios), tabla de inasistencias, sección de supletorios

- [ ] **Paso 4: Verificar tab Áreas**

1. Cambiar al tab "Áreas"
2. Verificar que aparecen métricas globales (empleados, capacitaciones, promedio) y tabla por área
3. Verificar sección de regionales al final

- [ ] **Paso 5: Commit**

```bash
git add app.py api_client.py ui/ .streamlit/config.toml .streamlit/secrets.toml secrets_TEMPLATE.toml requirements.txt docs/
git commit -m "feat: reemplazar Google Sheets por telcou-api, aplicar tema teal/azul"
```

---

## Checklist de Verificación Final

- [ ] La app carga sin errores con la API corriendo
- [ ] La app muestra un mensaje claro cuando la API NO está corriendo (no pantalla blanca)
- [ ] El tema visual es azul oscuro (`#0F1623`) con accent teal (`#00A8A8`)
- [ ] Sidebar muestra selector de año y botón de limpiar caché
- [ ] Tab Colaboradores: buscar por nombre, ver métricas, inasistencias, supletorios
- [ ] Tab Áreas: métricas globales, tabla por área, tabla por regional
- [ ] Campos eliminados NO aparecen: `dia_capacitacion`, `aula`, `cod`, `correo`, `jefe_correo`
- [ ] Estado "Vacaciones (V)" NO aparece en ningún lado
- [ ] `secrets.toml` NO contiene GIDs de Google Sheets (limpio)
- [ ] `config.yaml` de Google Sheets no está en el repositorio

---

## Notas de Dependencia

> **Requisito externo:** La API `telcou-api` debe estar corriendo en `http://localhost:8000` antes de usar el dashboard. Para iniciarla:
> ```bash
> cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
> uvicorn app.main:app --reload --port 8000
> ```
> Si la API no está disponible, el dashboard muestra un mensaje de error en lugar de pantalla en blanco.
