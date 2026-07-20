# Reporte "Calificaciones generales" en formato Macro — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new report endpoint + Streamlit UI that generates a `.xlsx` with two sheets ("PERSONAL TECNICO - QUITO", "PERSONAL TECNICO - TS R2") replicating the exact matrix layout of the real macro the user already uses (one row per colaborador, one column per curso, Excel summary formulas), selectable by month range and with an optional "combinado" mode showing supletorio results.

**Architecture:** New service module `app/services/reporte_matriz.py` in telcou-api (separate from `app/services/reportes.py`, which is untouched), using `openpyxl.Workbook()` normal mode (not `write_only` — this report has ~1,000-1,500 rows total, far below the 68k-row case that forced write_only elsewhere, and normal mode is needed for merged cells and formula-string cells). A new `GET /analitica/reporte-calificaciones-macro` endpoint streams the file. A new "Calificaciones (formato macro)" option is added to Reportería's report-type selector in the Streamlit frontend.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, openpyxl, pytest (backend, telcou-api); Streamlit, requests (frontend, dashboard-telcou-s1); Playwright/chromium-cli for browser verification.

## Global Constraints

- No Alembic migration — this feature only reads existing tables (`Nota`, `Curso`, `Empleado`, `VariableAdicional`, `Regional`) and writes an Excel file.
- Estado→código mapping (from the spec, cross-verified against the *existing production* `app/services/importer.py::interpretar_valor()` — the two must stay consistent since one is the inverse of the other):
  - `FALTA_INJUSTIFICADA`→`F`, `FALTA_JUSTIFICADA`→`J`, `VACACIONES`→`V`, `NO_APLICA`→`NA`, `NUEVO`→`N`, `CAMBIO`→`CAMBIO`, `SALIO`→`SALIÓ`, `ASISTENCIA`→`A`, `COPIA`→`"0 por copia"` (literal string).
  - `APROBADO` / `REPROBADO` / `EXONERADO` → the numeric `nota.valor`.
  - `PENDIENTE_JUSTIFICACION` or no nota at all → blank cell.
- Cell rule: without `combinado`, a curso's cell always shows the **most recent result** — if a SUPLETORIO exists for that empleado+curso (pick the one with the highest `convocatoria` if more than one), show its estado/valor instead of the REGULAR's.
- Summary formulas (both regionals, written as literal formula-text strings, not precomputed values) over the row's own curso-column range `<rango>`:
  - `=COUNTIF(<rango>,"0 por copia")`, `=COUNTIF(<rango>,"F")`, `=COUNTIF(<rango>,"<7.5")`, `=COUNT(<rango>)`, `=SUM(<rango>)/<celda_conteo>`.
- Two sheets always present in the output, even with 0 data rows for a regional — never omit a sheet.
- Header-row content order (row 1-5) differs per regional per the spec's `CONFIG_QUITO`/`CONFIG_TS_R2` `orden_filas_cabecera`; row 6 is always the fixed "encabezados" + week-range row, identical mechanics for both regionals. The pure-boilerplate decorative row ("REGISTRO DE EVALUACIONES" / form-code text, present in the two real example files but carrying no data derived from the database) is **not** reproduced — out of scope, confirmed pragmatic simplification, does not affect data fidelity.
- Out of scope (do not build): "PLATAFORMA"/"CUADRO" sheets (TS R2 staging sheets), "MEJOR ALUMNO MENSUAL" sheet, editing the generated `.xlsx` back into the system.
- Windows gotcha: `Stop-Process` on the uvicorn `--reload` parent can leave an orphaned multiprocessing-fork child still bound to the port serving stale code — verify via `/openapi.json` after any restart, not just process-list.
- `tests/conftest.py`'s `db` fixture only rolls back (doesn't truncate) — any test creating `Regional`/`Empleado`/`Curso` rows must use unique names/cédulas (via `uuid`) to avoid collisions across pytest runs, following the existing `_cedula_unica()` helper pattern in `tests/test_reportes.py`.
- `app/routers/admin.py` has unrelated pre-existing uncommitted local changes (owner's own `logging` refactor) — no task in this plan touches `admin.py`; if a task unexpectedly needs to, stash `CAMBIOS_SESION.md`, `app/routers/admin.py`, `app/services/calculadora.py`, `scripts/marcar_inactivos_por_ausencia.py` first, pop after committing.

---

### Task 1: Query helpers, estado→código mapping, and "resultado vigente" logic

**Files:**
- Create: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\app\services\reporte_matriz.py`
- Test: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\tests\test_reporte_matriz.py`

**Interfaces:**
- Consumes: `app.models.curso.Curso`, `app.models.empleado.Empleado`, `app.models.nota.Nota`, `app.models.regional.Regional`, `app.models.variable_adicional.VariableAdicional` (existing models, no changes). `app.services.importer.MES_NUMERO` (existing dict, reused — do not redefine). `app.services.convocatoria.NECESITA_SUPLETORIO` (existing set `{"REPROBADO", "FALTA_INJUSTIFICADA", "PENDIENTE_JUSTIFICACION"}`, reused in Task 3).
- Produces (for later tasks in this plan):
  - `CONFIG_QUITO: dict`, `CONFIG_TS_R2: dict` (module-level constants, exact shape below).
  - `FIELD_LABELS: dict[str, str]` (module-level constant, exact shape below).
  - `_codigo_celda(estado: str, valor: Decimal | None) -> str | float | None`
  - `_resultado_vigente(entrada: dict | None) -> Nota | None`
  - `_datos_periodo(db: Session, regional_nombre: str, anio: int, mes_desde: str | None, mes_hasta: str | None) -> tuple[list[Curso], list[Empleado], dict[int, VariableAdicional], dict[tuple[int, int], dict]]` — returns `(cursos_ordenados, empleados_ordenados, variables_por_empleado_id, agrupado)` where `agrupado[(empleado_id, curso_id)] = {"regular": Nota | None, "supletorios": list[Nota]}`.

- [ ] **Step 1: Write the failing tests for the mapping and query helpers**

```python
# tests/test_reporte_matriz.py
import uuid
from datetime import date
from decimal import Decimal

from app.models import Regional, Empleado, Curso, Nota
from app.models.variable_adicional import VariableAdicional
from app.services.reporte_matriz import (
    CONFIG_QUITO,
    CONFIG_TS_R2,
    _codigo_celda,
    _resultado_vigente,
    _datos_periodo,
)


def _cedula_unica(prefijo):
    return f"{prefijo}{uuid.uuid4().int % 10**7:07d}"


def test_config_quito_orden_y_columnas_fijas():
    assert CONFIG_QUITO["titulo_sheet"] == "PERSONAL TECNICO - QUITO"
    assert CONFIG_QUITO["orden_filas_cabecera"] == ["codigo", "link", "titulo_mes_resumen", "nombre_curso", "tipo"]
    assert CONFIG_QUITO["columnas_fijas"] == ["cedula", "correo_jefe", "nombre", "genero", "area", "jefe_inmediato", "dia"]
    assert CONFIG_QUITO["etiqueta_columna_variable"] == "DÍA DE CAPACITACIÓN"


def test_config_ts_r2_orden_y_columnas_fijas():
    assert CONFIG_TS_R2["titulo_sheet"] == "PERSONAL TECNICO - TS R2"
    assert CONFIG_TS_R2["orden_filas_cabecera"] == ["titulo_mes_resumen", "nombre_curso", "link", "codigo", "tipo"]
    assert CONFIG_TS_R2["columnas_fijas"] == ["correo", "cedula", "nombre", "genero", "area", "jefe_inmediato", "sucursal"]
    assert CONFIG_TS_R2["etiqueta_columna_variable"] == "TECNICA SUCURSAL"


def test_codigo_celda_mapea_estados_no_numericos():
    assert _codigo_celda("FALTA_INJUSTIFICADA", None) == "F"
    assert _codigo_celda("FALTA_JUSTIFICADA", None) == "J"
    assert _codigo_celda("VACACIONES", None) == "V"
    assert _codigo_celda("NO_APLICA", None) == "NA"
    assert _codigo_celda("NUEVO", None) == "N"
    assert _codigo_celda("CAMBIO", None) == "CAMBIO"
    assert _codigo_celda("SALIO", None) == "SALIÓ"
    assert _codigo_celda("ASISTENCIA", None) == "A"
    assert _codigo_celda("COPIA", Decimal("0.00")) == "0 por copia"


def test_codigo_celda_numericos_y_pendiente():
    assert _codigo_celda("APROBADO", Decimal("8.67")) == 8.67
    assert _codigo_celda("REPROBADO", Decimal("4.00")) == 4.0
    assert _codigo_celda("EXONERADO", Decimal("10.00")) == 10.0
    assert _codigo_celda("PENDIENTE_JUSTIFICACION", None) is None


def test_resultado_vigente_sin_supletorio_devuelve_regular():
    regular = Nota(estado="REPROBADO", valor=Decimal("4.0"), tipo="REGULAR")
    entrada = {"regular": regular, "supletorios": []}
    assert _resultado_vigente(entrada) is regular


def test_resultado_vigente_con_supletorio_devuelve_el_mas_reciente():
    regular = Nota(estado="REPROBADO", valor=Decimal("4.0"), tipo="REGULAR", convocatoria=1)
    sup1 = Nota(estado="REPROBADO", valor=Decimal("6.0"), tipo="SUPLETORIO", convocatoria=1)
    sup2 = Nota(estado="APROBADO", valor=Decimal("8.0"), tipo="SUPLETORIO", convocatoria=2)
    entrada = {"regular": regular, "supletorios": [sup1, sup2]}
    resultado = _resultado_vigente(entrada)
    assert resultado is sup2


def test_resultado_vigente_entrada_none_devuelve_none():
    assert _resultado_vigente(None) is None


def test_datos_periodo_filtra_por_rango_de_meses_y_ordena_cronologicamente(db):
    sufijo = uuid.uuid4().hex[:6]
    reg = Regional(nombre=f"Quito Matriz {sufijo}")
    db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("91"), nombre=f"MATRIZ UNO {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso_ene = Curso(codigo=f"ENE-{sufijo}", nombre="CURSO ENERO", tipo="PRESENCIAL",
                       mes="ENERO", anio=2026, regional_id=reg.id,
                       fecha_inicio=date(2026, 1, 12), fecha_fin=date(2026, 1, 18))
    curso_mar = Curso(codigo=f"MAR-{sufijo}", nombre="CURSO MARZO", tipo="PRESENCIAL",
                       mes="MARZO", anio=2026, regional_id=reg.id,
                       fecha_inicio=date(2026, 3, 2), fecha_fin=date(2026, 3, 8))
    db.add_all([curso_ene, curso_mar]); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso_ene.id, valor=Decimal("9.0"), estado="APROBADO", tipo="REGULAR"))
    db.add(Nota(empleado_id=emp.id, curso_id=curso_mar.id, valor=Decimal("8.0"), estado="APROBADO", tipo="REGULAR"))
    db.flush()

    cursos, empleados, variables, agrupado = _datos_periodo(db, f"Quito Matriz {sufijo}", 2026, "ENERO", "ENERO")
    assert [c.id for c in cursos] == [curso_ene.id]
    assert [e.id for e in empleados] == [emp.id]

    cursos_todo, _, _, _ = _datos_periodo(db, f"Quito Matriz {sufijo}", 2026, None, None)
    assert [c.id for c in cursos_todo] == [curso_ene.id, curso_mar.id]


def test_datos_periodo_incluye_inactivos(db):
    """La matriz debe mostrar SALIO/CAMBIO — a diferencia de _notas_generales_data()
    (reportes.py), NO se filtran los empleados inactivos aqui."""
    sufijo = uuid.uuid4().hex[:6]
    reg = Regional(nombre=f"Quito MatrizInactivo {sufijo}")
    db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("92"), nombre=f"MATRIZ SALIO {sufijo}", regional_id=reg.id,
                    inactivo=True, tipo_movimiento="SALIO")
    db.add(emp); db.flush()
    curso = Curso(codigo=f"SAL-{sufijo}", nombre="CURSO SALIO", tipo="PRESENCIAL",
                   mes="ABRIL", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="SALIO", tipo="REGULAR"))
    db.flush()

    _, empleados, _, _ = _datos_periodo(db, f"Quito MatrizInactivo {sufijo}", 2026, None, None)
    assert emp.id in [e.id for e in empleados]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_matriz.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.reporte_matriz'`

- [ ] **Step 3: Implement the module**

```python
# app/services/reporte_matriz.py
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.curso import Curso
from app.models.empleado import Empleado
from app.models.nota import Nota
from app.models.regional import Regional
from app.models.variable_adicional import VariableAdicional
from app.services.importer import MES_NUMERO

CONFIG_QUITO = {
    "titulo_sheet": "PERSONAL TECNICO - QUITO",
    "regional_nombre": "Quito",
    "titulo_registro": "REGISTRO DE EVALUACIONES PERSONAL TÉCNICO-UIO",
    "orden_filas_cabecera": ["codigo", "link", "titulo_mes_resumen", "nombre_curso", "tipo"],
    "columnas_fijas": ["cedula", "correo_jefe", "nombre", "genero", "area", "jefe_inmediato", "dia"],
    "etiqueta_columna_variable": "DÍA DE CAPACITACIÓN",
}
CONFIG_TS_R2 = {
    "titulo_sheet": "PERSONAL TECNICO - TS R2",
    "regional_nombre": "TS R2",
    "titulo_registro": "REGISTRO DE EVALUACIONES PERSONAL TÉCNICO-UIO",
    "orden_filas_cabecera": ["titulo_mes_resumen", "nombre_curso", "link", "codigo", "tipo"],
    "columnas_fijas": ["correo", "cedula", "nombre", "genero", "area", "jefe_inmediato", "sucursal"],
    "etiqueta_columna_variable": "TECNICA SUCURSAL",
}

FIELD_LABELS = {
    "cedula": "N.CEDULA",
    "correo_jefe": "CORREO JEFE",
    "correo": "CORREO",
    "nombre": "NOMBRE Y APELLIDOS",
    "genero": "GENERO",
    "area": "AREA",
    "jefe_inmediato": "JEFE INMEDIATO",
}

ESTADO_A_CODIGO = {
    "FALTA_INJUSTIFICADA": "F",
    "FALTA_JUSTIFICADA": "J",
    "VACACIONES": "V",
    "NO_APLICA": "NA",
    "NUEVO": "N",
    "CAMBIO": "CAMBIO",
    "SALIO": "SALIÓ",
    "ASISTENCIA": "A",
    "COPIA": "0 por copia",
}
ESTADOS_NUMERICOS = {"APROBADO", "REPROBADO", "EXONERADO"}


def _codigo_celda(estado: str, valor: Decimal | None) -> str | float | None:
    if estado in ESTADOS_NUMERICOS:
        return float(valor) if valor is not None else None
    if estado == "PENDIENTE_JUSTIFICACION":
        return None
    return ESTADO_A_CODIGO.get(estado)


def _resultado_vigente(entrada: dict | None) -> Nota | None:
    if not entrada:
        return None
    supletorios = entrada.get("supletorios") or []
    if supletorios:
        return max(supletorios, key=lambda n: n.convocatoria)
    return entrada.get("regular")


def _mes_num(mes: str | None) -> int:
    return MES_NUMERO.get((mes or "").strip().upper(), 0)


def _datos_periodo(
    db: Session, regional_nombre: str, anio: int, mes_desde: str | None, mes_hasta: str | None,
) -> tuple[list[Curso], list[Empleado], dict[int, VariableAdicional], dict[tuple[int, int], dict]]:
    regional = db.query(Regional).filter(Regional.nombre == regional_nombre).first()
    if not regional:
        return [], [], {}, {}

    cursos = db.query(Curso).filter(Curso.anio == anio, Curso.regional_id == regional.id).all()
    if mes_desde or mes_hasta:
        num_desde = _mes_num(mes_desde) or 1
        num_hasta = _mes_num(mes_hasta) or 12
        cursos = [c for c in cursos if num_desde <= _mes_num(c.mes) <= num_hasta]
    cursos.sort(key=lambda c: (_mes_num(c.mes) or 99, c.fecha_inicio or date.min, c.id))

    curso_ids = [c.id for c in cursos]
    if not curso_ids:
        return cursos, [], {}, {}

    empleado_ids = {
        eid for (eid,) in db.query(Nota.empleado_id)
        .join(Curso, Nota.curso_id == Curso.id)
        .filter(Nota.tipo == "REGULAR", Curso.anio == anio, Curso.regional_id == regional.id)
        .distinct()
    }
    if not empleado_ids:
        return cursos, [], {}, {}

    empleados = (
        db.query(Empleado)
        .filter(Empleado.id.in_(empleado_ids))
        .order_by(Empleado.nombre)
        .all()
    )
    variables = {
        va.empleado_id: va
        for va in db.query(VariableAdicional).filter(VariableAdicional.empleado_id.in_(empleado_ids))
    }

    notas = (
        db.query(Nota)
        .filter(Nota.empleado_id.in_(empleado_ids), Nota.curso_id.in_(curso_ids))
        .all()
    )
    agrupado: dict[tuple[int, int], dict] = {}
    for n in notas:
        clave = (n.empleado_id, n.curso_id)
        entrada = agrupado.setdefault(clave, {"regular": None, "supletorios": []})
        if n.tipo == "REGULAR":
            entrada["regular"] = n
        else:
            entrada["supletorios"].append(n)

    return cursos, empleados, variables, agrupado
```

**Note on scope vs. `_notas_generales_data()` in `reportes.py`:** that function filters `Empleado.inactivo.is_(False)` because the list-format reports only care about currently-active people. This matrix report must NOT apply that filter — showing `SALIO`/`CAMBIO` codes for people who left mid-year is the entire point of those codes existing in the macro. `test_datos_periodo_incluye_inactivos` above locks this in.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_matriz.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
git add app/services/reporte_matriz.py tests/test_reporte_matriz.py
git commit -m "feat: query helpers y mapeo estado-codigo para reporte matriz de calificaciones"
```

---

### Task 2: Sheet builder (header rows, merges, fixed columns, curso columns, summary formulas) + public function

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\app\services\reporte_matriz.py`
- Test: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\tests\test_reporte_matriz.py`

**Interfaces:**
- Consumes: everything from Task 1 (`CONFIG_QUITO`, `CONFIG_TS_R2`, `FIELD_LABELS`, `_codigo_celda`, `_resultado_vigente`, `_datos_periodo`).
- Produces:
  - `_rango_semana(curso: Curso) -> str` — e.g. `"12 AL 18"` from `fecha_inicio`/`fecha_fin` day numbers, `""` if either is `None`.
  - `_construir_hoja_matriz(wb, config: dict, cursos: list[Curso], empleados: list[Empleado], variables: dict, agrupado: dict, combinado: bool = False) -> None` — builds one full sheet in `wb` (header + data rows + summary formulas). `combinado` is accepted here (parameter threaded through) but Task 2 only needs the `combinado=False` path to work; Task 3 implements the `True` branch.
  - `generar_reporte_calificaciones_macro_excel(db: Session, anio: int, mes_desde: str | None = None, mes_hasta: str | None = None, combinado: bool = False) -> BytesIO` — the public entry point, builds both sheets in one workbook.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_reporte_matriz.py
import openpyxl
from io import BytesIO

from app.services.reporte_matriz import (
    generar_reporte_calificaciones_macro_excel,
    _rango_semana,
)


def test_rango_semana_formatea_dia_a_dia():
    curso = Curso(fecha_inicio=date(2026, 1, 12), fecha_fin=date(2026, 1, 18))
    assert _rango_semana(curso) == "12 AL 18"


def test_rango_semana_vacio_sin_fechas():
    curso = Curso(fecha_inicio=None, fecha_fin=None)
    assert _rango_semana(curso) == ""


def test_macro_genera_dos_hojas_con_nombres_exactos(db):
    buffer = generar_reporte_calificaciones_macro_excel(db, 2026)
    wb = openpyxl.load_workbook(buffer)
    assert wb.sheetnames == ["PERSONAL TECNICO - QUITO", "PERSONAL TECNICO - TS R2"]


def test_macro_hoja_vacia_solo_cabecera_si_regional_sin_datos(db):
    # anio sin ningun curso cargado en ninguna regional -> ambas hojas solo cabecera
    buffer = generar_reporte_calificaciones_macro_excel(db, 1999)
    wb = openpyxl.load_workbook(buffer)
    ws = wb["PERSONAL TECNICO - QUITO"]
    assert ws.max_row == 6  # solo las 6 filas de cabecera, sin datos


def test_macro_celda_curso_muestra_codigo_f_para_falta_injustificada(db):
    sufijo = uuid.uuid4().hex[:6]
    reg = Regional(nombre="Quito"); reg2 = None
    existente = db.query(Regional).filter_by(nombre="Quito").first()
    if existente:
        reg = existente
    else:
        db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("93"), nombre=f"MACRO FALTA {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"MACF-{sufijo}", nombre="CURSO MACRO FALTA", tipo="PRESENCIAL",
                  mes="MAYO", anio=2026, regional_id=reg.id,
                  fecha_inicio=date(2026, 5, 4), fecha_fin=date(2026, 5, 10))
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="FALTA_INJUSTIFICADA", tipo="REGULAR"))
    db.flush()

    buffer = generar_reporte_calificaciones_macro_excel(db, 2026, mes_desde="MAYO", mes_hasta="MAYO")
    wb = openpyxl.load_workbook(buffer, data_only=False)
    ws = wb["PERSONAL TECNICO - QUITO"]

    fila = next(row for row in ws.iter_rows(min_row=7, values_only=True) if row[0] == emp.cedula)
    # columnas fijas Quito: #, cedula, correo_jefe, nombre, genero, area, jefe_inmediato, dia -> indices 0..7
    # primera columna de curso = indice 8
    assert fila[8] == "F"


def test_macro_celda_curso_usa_nota_mas_reciente_supletorio(db):
    sufijo = uuid.uuid4().hex[:6]
    reg = db.query(Regional).filter_by(nombre="Quito").first() or Regional(nombre="Quito")
    if not reg.id:
        db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("94"), nombre=f"MACRO SUPLE {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"MACS-{sufijo}", nombre="CURSO MACRO SUPLE", tipo="PRESENCIAL",
                  mes="JUNIO", anio=2026, regional_id=reg.id,
                  fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 7))
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="REPROBADO", valor=Decimal("4.0"),
                tipo="REGULAR", convocatoria=1))
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="APROBADO", valor=Decimal("8.0"),
                tipo="SUPLETORIO", convocatoria=1))
    db.flush()

    buffer = generar_reporte_calificaciones_macro_excel(db, 2026, mes_desde="JUNIO", mes_hasta="JUNIO")
    wb = openpyxl.load_workbook(buffer)
    ws = wb["PERSONAL TECNICO - QUITO"]
    fila = next(row for row in ws.iter_rows(min_row=7, values_only=True) if row[0] == emp.cedula)
    assert fila[8] == 8.0  # muestra el supletorio aprobado, no el 4.0 del regular


def test_macro_formulas_resumen_usan_rango_correcto(db):
    sufijo = uuid.uuid4().hex[:6]
    reg = db.query(Regional).filter_by(nombre="Quito").first() or Regional(nombre="Quito")
    if not reg.id:
        db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("95"), nombre=f"MACRO FORMULA {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"MACFR-{sufijo}", nombre="CURSO MACRO FORMULA", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="APROBADO", valor=Decimal("9.0"), tipo="REGULAR"))
    db.flush()

    buffer = generar_reporte_calificaciones_macro_excel(db, 2026, mes_desde="JULIO", mes_hasta="JULIO")
    wb = openpyxl.load_workbook(buffer, data_only=False)
    ws = wb["PERSONAL TECNICO - QUITO"]
    fila_idx = next(
        i for i, row in enumerate(ws.iter_rows(min_row=7, values_only=True), start=7)
        if row[0] == emp.cedula
    )
    fila = list(ws[fila_idx])
    # con 1 sola columna de curso (indice de columna 9, letra "I" tras las 8 fijas), el rango es I<fila>:I<fila>
    formulas = [c.value for c in fila]
    idx_0copia = 9  # columnas fijas (8) + 1 columna de curso (indice 8) -> resumen empieza en indice 9
    assert formulas[idx_0copia] == f'=COUNTIF(I{fila_idx}:I{fila_idx},"0 por copia")'
    assert formulas[idx_0copia + 1] == f'=COUNTIF(I{fila_idx}:I{fila_idx},"F")'
    assert formulas[idx_0copia + 2] == f'=COUNTIF(I{fila_idx}:I{fila_idx},"<7.5")'
    assert formulas[idx_0copia + 3] == f'=COUNT(I{fila_idx}:I{fila_idx})'
    assert formulas[idx_0copia + 4] == f'=SUM(I{fila_idx}:I{fila_idx})/{openpyxl.utils.get_column_letter(idx_0copia + 4)}{fila_idx}'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_matriz.py -v -k macro`
Expected: FAIL with `ImportError: cannot import name 'generar_reporte_calificaciones_macro_excel'`

- [ ] **Step 3: Implement the sheet builder and public function**

Append to `app/services/reporte_matriz.py`:

```python
from io import BytesIO

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

COLUMNAS_RESUMEN = ["0 POR COPIA", "NÚMERO DE FALTAS", "# DE SUPLETORIOS"]


def _rango_semana(curso: Curso) -> str:
    if not curso.fecha_inicio or not curso.fecha_fin:
        return ""
    return f"{curso.fecha_inicio.day} AL {curso.fecha_fin.day}"


def _valor_empleado(empleado: Empleado, variable: VariableAdicional | None, campo: str):
    if campo == "correo_jefe":
        return variable.jefe_correo if variable else None
    if campo == "correo":
        return variable.correo if variable else None
    if campo == "dia":
        return variable.dia if variable else None
    return getattr(empleado, campo, None)


def _construir_hoja_matriz(
    wb, config: dict, cursos: list[Curso], empleados: list[Empleado],
    variables: dict[int, VariableAdicional], agrupado: dict[tuple[int, int], dict],
    combinado: bool = False,
) -> None:
    ws = wb.create_sheet(title=config["titulo_sheet"])
    n_fijas = len(config["columnas_fijas"]) + 1  # +1 por la columna "#"
    n_cursos = len(cursos)
    col_primer_curso = n_fijas + 1

    # --- Bloque de titulo (filas 1-5, columnas fijas excepto la ultima/variable) ---
    ws.merge_cells(start_row=1, start_column=1, end_row=5, end_column=n_fijas - 1)
    ws.cell(row=1, column=1, value=config["titulo_registro"]).font = Font(bold=True)

    # --- Columna variable (dia / tecnica sucursal): merge filas 1-6 ---
    ws.merge_cells(start_row=1, start_column=n_fijas, end_row=6, end_column=n_fijas)
    ws.cell(row=1, column=n_fijas, value=config["etiqueta_columna_variable"]).font = Font(bold=True)

    # --- Fila 6: encabezados fijos reales (# + columnas_fijas, sin la ultima que ya tiene su label arriba) ---
    ws.cell(row=6, column=1, value="#").font = Font(bold=True)
    for i, campo in enumerate(config["columnas_fijas"][:-1], start=2):
        ws.cell(row=6, column=i, value=FIELD_LABELS[campo]).font = Font(bold=True)

    # --- Filas de cada curso (contenido por tipo segun orden_filas_cabecera) + fila 6 = semana ---
    fila_por_tipo = {tipo: i + 1 for i, tipo in enumerate(config["orden_filas_cabecera"])}
    fila_mes = fila_por_tipo["titulo_mes_resumen"]

    for j, curso in enumerate(cursos):
        col = col_primer_curso + j
        valores = {
            "codigo": curso.codigo,
            "link": curso.url_telcou or "",
            "nombre_curso": curso.nombre,
            "tipo": curso.tipo,
        }
        for tipo, fila in fila_por_tipo.items():
            if tipo == "titulo_mes_resumen":
                continue
            ws.cell(row=fila, column=col, value=valores[tipo])
        ws.cell(row=6, column=col, value=_rango_semana(curso))

    # --- Fila de mes (agrupa columnas consecutivas del mismo mes) ---
    inicio_grupo = 0
    for j in range(1, n_cursos + 1):
        fin_de_grupo = j == n_cursos or cursos[j].mes != cursos[inicio_grupo].mes
        if fin_de_grupo:
            col_ini = col_primer_curso + inicio_grupo
            col_fin = col_primer_curso + j - 1
            if col_fin > col_ini:
                ws.merge_cells(start_row=fila_mes, start_column=col_ini, end_row=fila_mes, end_column=col_fin)
            ws.cell(row=fila_mes, column=col_ini, value=cursos[inicio_grupo].mes).font = Font(bold=True)
            inicio_grupo = j

    # --- Columnas resumen (0 por copia / faltas / supletorios / promedios) ---
    col_resumen = col_primer_curso + n_cursos
    for i, titulo in enumerate(COLUMNAS_RESUMEN):
        col = col_resumen + i
        ws.merge_cells(start_row=1, start_column=col, end_row=fila_mes, end_column=col)
        ws.cell(row=1, column=col, value=titulo).font = Font(bold=True)
    col_conteo = col_resumen + len(COLUMNAS_RESUMEN)
    col_promedio = col_conteo + 1
    ws.merge_cells(start_row=fila_mes, start_column=col_conteo, end_row=fila_mes, end_column=col_promedio)
    ws.cell(row=fila_mes, column=col_conteo, value="PROMEDIOS").font = Font(bold=True)
    ws.cell(row=6, column=col_conteo, value="conteo").font = Font(bold=True)
    ws.cell(row=6, column=col_promedio, value="Promedio").font = Font(bold=True)

    # --- Filas de datos ---
    fila_actual = 7
    letra_inicio = get_column_letter(col_primer_curso)
    letra_fin = get_column_letter(col_primer_curso + n_cursos - 1) if n_cursos else letra_inicio

    for i, emp in enumerate(empleados, start=1):
        variable = variables.get(emp.id)
        ws.cell(row=fila_actual, column=1, value=i)
        for c, campo in enumerate(config["columnas_fijas"], start=2):
            ws.cell(row=fila_actual, column=c, value=_valor_empleado(emp, variable, campo))

        for j, curso in enumerate(cursos):
            col = col_primer_curso + j
            entrada = agrupado.get((emp.id, curso.id))
            resultado = _resultado_vigente(entrada)
            if resultado is not None:
                ws.cell(row=fila_actual, column=col, value=_codigo_celda(resultado.estado, resultado.valor))

        if n_cursos:
            rango = f"{letra_inicio}{fila_actual}:{letra_fin}{fila_actual}"
            ws.cell(row=fila_actual, column=col_resumen, value=f'=COUNTIF({rango},"0 por copia")')
            ws.cell(row=fila_actual, column=col_resumen + 1, value=f'=COUNTIF({rango},"F")')
            ws.cell(row=fila_actual, column=col_resumen + 2, value=f'=COUNTIF({rango},"<7.5")')
            ws.cell(row=fila_actual, column=col_conteo, value=f'=COUNT({rango})')
            letra_conteo = get_column_letter(col_conteo)
            ws.cell(row=fila_actual, column=col_promedio,
                    value=f'=SUM({rango})/{letra_conteo}{fila_actual}')

        fila_actual += 1

    for col in range(1, col_promedio + 1):
        ws.column_dimensions[get_column_letter(col)].width = 16


def generar_reporte_calificaciones_macro_excel(
    db: Session, anio: int, mes_desde: str | None = None, mes_hasta: str | None = None,
    combinado: bool = False,
) -> BytesIO:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    for config in (CONFIG_QUITO, CONFIG_TS_R2):
        cursos, empleados, variables, agrupado = _datos_periodo(
            db, config["regional_nombre"], anio, mes_desde, mes_hasta,
        )
        _construir_hoja_matriz(wb, config, cursos, empleados, variables, agrupado, combinado=combinado)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_matriz.py -v`
Expected: all passed (Task 1's 9 + Task 2's 7 = 16 passed)

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
git add app/services/reporte_matriz.py tests/test_reporte_matriz.py
git commit -m "feat: generador de hoja matriz y funcion publica del reporte de calificaciones formato macro"
```

---

### Task 3: Modo `combinado` (columna extra de supletorio)

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\app\services\reporte_matriz.py`
- Test: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\tests\test_reporte_matriz.py`

**Interfaces:**
- Consumes: `NECESITA_SUPLETORIO` from `app.services.convocatoria` (existing constant: `{"REPROBADO", "FALTA_INJUSTIFICADA", "PENDIENTE_JUSTIFICACION"}`). Everything from Task 2.
- Produces: `_construir_hoja_matriz(..., combinado=True)` now actually builds the extra columns (the `False` path from Task 2 is unchanged).

**Rule (from the spec, made concrete):** a curso gets one extra "(SUPLETORIO)" column when, among the roster for that curso, at least one empleado has either (a) a `SUPLETORIO` nota, or (b) a `REGULAR` nota whose `estado` is in `NECESITA_SUPLETORIO` with no supletorio yet. Each row's companion cell shows that specific empleado's own supletorio result (via `_codigo_celda` on the most-recent supletorio nota) if they have one, else blank — even if the column exists because of a *different* empleado's activity.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_reporte_matriz.py
def test_macro_combinado_agrega_columna_supletorio(db):
    sufijo = uuid.uuid4().hex[:6]
    reg = db.query(Regional).filter_by(nombre="Quito").first() or Regional(nombre="Quito")
    if not reg.id:
        db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("96"), nombre=f"MACRO COMBI {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"MACCO-{sufijo}", nombre="CURSO MACRO COMBI", tipo="PRESENCIAL",
                  mes="AGOSTO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="REPROBADO", valor=Decimal("4.0"),
                tipo="REGULAR", convocatoria=1))
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="APROBADO", valor=Decimal("8.0"),
                tipo="SUPLETORIO", convocatoria=1))
    db.flush()

    buffer_normal = generar_reporte_calificaciones_macro_excel(db, 2026, mes_desde="AGOSTO", mes_hasta="AGOSTO")
    wb_normal = openpyxl.load_workbook(buffer_normal)
    ws_normal = wb_normal["PERSONAL TECNICO - QUITO"]
    # sin combinado: 8 fijas + 1 curso + 5 resumen = 14 columnas
    assert ws_normal.max_column == 14

    buffer_combi = generar_reporte_calificaciones_macro_excel(
        db, 2026, mes_desde="AGOSTO", mes_hasta="AGOSTO", combinado=True,
    )
    wb_combi = openpyxl.load_workbook(buffer_combi)
    ws_combi = wb_combi["PERSONAL TECNICO - QUITO"]
    # con combinado: +1 columna de supletorio para este curso = 15 columnas
    assert ws_combi.max_column == 15

    fila = next(row for row in ws_combi.iter_rows(min_row=7, values_only=True) if row[0] == emp.cedula)
    assert fila[8] == 8.0  # celda REGULAR: nota mas reciente (supletorio aprobado)
    assert fila[9] == 8.0  # celda companera "(SUPLETORIO)": el resultado del supletorio


def test_macro_combinado_no_agrega_columna_si_nadie_tiene_supletorio(db):
    sufijo = uuid.uuid4().hex[:6]
    reg = db.query(Regional).filter_by(nombre="Quito").first() or Regional(nombre="Quito")
    if not reg.id:
        db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("97"), nombre=f"MACRO SIN COMBI {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"MACSC-{sufijo}", nombre="CURSO MACRO SIN COMBI", tipo="PRESENCIAL",
                  mes="SEPTIEMBRE", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="APROBADO", valor=Decimal("9.0"), tipo="REGULAR"))
    db.flush()

    buffer = generar_reporte_calificaciones_macro_excel(
        db, 2026, mes_desde="SEPTIEMBRE", mes_hasta="SEPTIEMBRE", combinado=True,
    )
    wb = openpyxl.load_workbook(buffer)
    ws = wb["PERSONAL TECNICO - QUITO"]
    assert ws.max_column == 14  # sin columna extra: nadie necesito/rindio supletorio
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_matriz.py -v -k combinado`
Expected: FAIL — `assert ws_combi.max_column == 15` fails (still 14, no extra column built yet)

- [ ] **Step 3: Implement the combinado branch**

In `app/services/reporte_matriz.py`, add the import and helper, then modify `_construir_hoja_matriz` to insert companion columns:

```python
from app.services.convocatoria import NECESITA_SUPLETORIO


def _curso_tiene_actividad_supletorio(curso: Curso, empleados: list[Empleado], agrupado: dict) -> bool:
    for emp in empleados:
        entrada = agrupado.get((emp.id, curso.id))
        if not entrada:
            continue
        if entrada["supletorios"]:
            return True
        regular = entrada["regular"]
        if regular and regular.estado in NECESITA_SUPLETORIO:
            return True
    return False
```

Replace the curso-columns loop in `_construir_hoja_matriz` (the block starting at `for j, curso in enumerate(cursos):` through the mes-grouping block) with a version that expands the column list up front when `combinado=True`, so every downstream index (`col_resumen`, data rows, formula ranges) is computed against the real final column count:

```python
    # --- Expandir columnas si combinado: cada curso con actividad de supletorio
    # obtiene una columna companera inmediatamente despues, sufijo " (SUPLETORIO)" ---
    columnas_curso: list[tuple[Curso, bool]] = []  # (curso, es_columna_supletorio)
    for curso in cursos:
        columnas_curso.append((curso, False))
        if combinado and _curso_tiene_actividad_supletorio(curso, empleados, agrupado):
            columnas_curso.append((curso, True))
    n_cursos = len(columnas_curso)

    for j, (curso, es_supletorio) in enumerate(columnas_curso):
        col = col_primer_curso + j
        sufijo_nombre = " (SUPLETORIO)" if es_supletorio else ""
        valores = {
            "codigo": curso.codigo,
            "link": curso.url_telcou or "",
            "nombre_curso": curso.nombre + sufijo_nombre,
            "tipo": curso.tipo,
        }
        for tipo, fila in fila_por_tipo.items():
            if tipo == "titulo_mes_resumen":
                continue
            ws.cell(row=fila, column=col, value=valores[tipo])
        ws.cell(row=6, column=col, value=_rango_semana(curso))

    # --- Fila de mes (agrupa columnas consecutivas del mismo mes, incluyendo companeras) ---
    inicio_grupo = 0
    for j in range(1, n_cursos + 1):
        fin_de_grupo = j == n_cursos or columnas_curso[j][0].mes != columnas_curso[inicio_grupo][0].mes
        if fin_de_grupo:
            col_ini = col_primer_curso + inicio_grupo
            col_fin = col_primer_curso + j - 1
            if col_fin > col_ini:
                ws.merge_cells(start_row=fila_mes, start_column=col_ini, end_row=fila_mes, end_column=col_fin)
            ws.cell(row=fila_mes, column=col_ini, value=columnas_curso[inicio_grupo][0].mes).font = Font(bold=True)
            inicio_grupo = j
```

And in the data-rows loop, replace the curso-cell-writing block (`for j, curso in enumerate(cursos): ... entrada = agrupado.get(...)`) with:

```python
        for j, (curso, es_supletorio) in enumerate(columnas_curso):
            col = col_primer_curso + j
            entrada = agrupado.get((emp.id, curso.id))
            if es_supletorio:
                supletorios = (entrada or {}).get("supletorios") or []
                resultado = max(supletorios, key=lambda n: n.convocatoria) if supletorios else None
            else:
                resultado = _resultado_vigente(entrada)
            if resultado is not None:
                ws.cell(row=fila_actual, column=col, value=_codigo_celda(resultado.estado, resultado.valor))
```

(The rest of `_construir_hoja_matriz` — title block, variable column, fixed headers row 6, summary columns, formula-writing per row — is unchanged; it already reads `n_cursos` and `col_primer_curso` generically, so it keeps working once `n_cursos`/`columnas_curso` reflect the expanded list.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_matriz.py -v`
Expected: all passed (18 total)

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest -q`
Expected: all passed (239 previous + 18 new = 257 passed)

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
git add app/services/reporte_matriz.py tests/test_reporte_matriz.py
git commit -m "feat: modo combinado con columna de supletorio en reporte matriz de calificaciones"
```

---

### Task 4: Endpoint `GET /analitica/reporte-calificaciones-macro`

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\app\routers\analitica.py`
- Test: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api\tests\test_reporte_endpoint.py`

**Interfaces:**
- Consumes: `generar_reporte_calificaciones_macro_excel` from Task 3 (final signature: `(db, anio, mes_desde=None, mes_hasta=None, combinado=False) -> BytesIO`).
- Produces: `GET /analitica/reporte-calificaciones-macro?anio=&mes_desde=&mes_hasta=&combinado=` — streaming `.xlsx`, no admin token required (matches the sibling `/reporte-calificaciones`/`/reporte-asistencia` endpoints, which are also unauthenticated GETs).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_reporte_endpoint.py
def test_reporte_calificaciones_macro_sin_anio_retorna_422(client):
    r = client.get("/analitica/reporte-calificaciones-macro")
    assert r.status_code == 422


def test_reporte_calificaciones_macro_devuelve_xlsx_con_dos_hojas(client, db):
    sufijo = uuid.uuid4().hex[:6]
    reg = db.query(Regional).filter_by(nombre="Quito").first()
    if not reg:
        reg = Regional(nombre="Quito")
        db.add(reg); db.flush()
    emp = Empleado(cedula=_cedula_unica("98"), nombre=f"ENDPOINT MACRO {sufijo}", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"EPM-{sufijo}", nombre="CURSO ENDPOINT MACRO", tipo="PRESENCIAL",
                  mes="OCTUBRE", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="APROBADO", valor=Decimal("9.0"), tipo="REGULAR"))
    db.flush()

    r = client.get("/analitica/reporte-calificaciones-macro",
                    params={"anio": 2026, "mes_desde": "OCTUBRE", "mes_hasta": "OCTUBRE"})
    assert r.status_code == 200
    assert r.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "calificaciones_macro_2026.xlsx" in r.headers["content-disposition"]

    wb = openpyxl.load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["PERSONAL TECNICO - QUITO", "PERSONAL TECNICO - TS R2"]
    cedulas = [row[1] for row in wb["PERSONAL TECNICO - QUITO"].iter_rows(min_row=7, values_only=True)]
    assert emp.cedula in cedulas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_endpoint.py -v -k macro`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Add the endpoint**

In `app/routers/analitica.py`, add to the existing import block from `app.services.reportes` (around line 53-60) a new import line, and add the route after the `reporte-calificaciones-html` endpoint (around line 380):

```python
from app.services.reporte_matriz import generar_reporte_calificaciones_macro_excel
```

```python
@router.get("/reporte-calificaciones-macro")
def reporte_calificaciones_macro(
    anio: int = Query(...),
    mes_desde: str | None = Query(None, description="Nombre de mes en español, ej. ENERO — opcional"),
    mes_hasta: str | None = Query(None, description="Nombre de mes en español, ej. JUNIO — opcional"),
    combinado: bool = Query(False, description="Agrega una columna extra de supletorio por curso con actividad de supletorio"),
    db: Session = Depends(get_db),
):
    """
    Reporte Excel en el mismo formato de matriz que el macro manual real
    (una fila por colaborador, una columna por curso, con formulas de
    resumen). Dos hojas fijas: "PERSONAL TECNICO - QUITO" y
    "PERSONAL TECNICO - TS R2".
    """
    buffer = generar_reporte_calificaciones_macro_excel(
        db, anio, mes_desde=mes_desde, mes_hasta=mes_hasta, combinado=combinado,
    )
    filename = f"calificaciones_macro_{anio}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_reporte_endpoint.py -v -k macro`
Expected: 2 passed

- [ ] **Step 5: Run the full backend suite**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest -q`
Expected: all passed (259 total)

- [ ] **Step 6: Commit**

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
git add app/routers/analitica.py tests/test_reporte_endpoint.py
git commit -m "feat: endpoint GET /analitica/reporte-calificaciones-macro"
```

---

### Task 5: Frontend — `api_client.py` + `ui/reporteria.py`

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\api_client.py`
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\ui\reporteria.py`

**Interfaces:**
- Consumes: `GET /analitica/reporte-calificaciones-macro` from Task 4.
- Produces: `api_client.get_reporte_calificaciones_macro_excel(anio: int, mes_desde: str | None = None, mes_hasta: str | None = None, combinado: bool = False) -> bytes | None`; `ui/reporteria.py::_seccion_calificaciones_macro(anio: int) -> None` wired into `TIPOS_REPORTE`.

- [ ] **Step 1: Add the api_client function**

In `api_client.py`, immediately after `get_reporte_calificaciones_html` (existing function), add:

```python
def get_reporte_calificaciones_macro_excel(
    anio: int, mes_desde: Optional[str] = None, mes_hasta: Optional[str] = None,
    combinado: bool = False,
) -> bytes | None:
    params = {"anio": anio, "combinado": combinado}
    if mes_desde:
        params["mes_desde"] = mes_desde
    if mes_hasta:
        params["mes_hasta"] = mes_hasta
    return _get_bytes("/analitica/reporte-calificaciones-macro", params)
```

- [ ] **Step 2: Add the report section to `ui/reporteria.py`**

Modify `TIPOS_REPORTE` and `render_tab_reporteria`:

```python
TIPOS_REPORTE = ["Supletorios pendientes", "Asistencia", "Calificaciones generales", "Calificaciones (formato macro)"]


def render_tab_reporteria(anio: int) -> None:
    st.title("📥 Reportería")

    tipo = st.radio("Tipo de reporte", TIPOS_REPORTE, key="rep_tipo", horizontal=True)
    st.divider()

    if tipo == "Supletorios pendientes":
        _seccion_supletorios(anio)
    elif tipo == "Asistencia":
        _seccion_asistencia(anio)
    elif tipo == "Calificaciones generales":
        _seccion_calificaciones(anio)
    else:
        _seccion_calificaciones_macro(anio)
```

Add the new section function at the end of the file:

```python
MESES = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


def _seccion_calificaciones_macro(anio: int) -> None:
    st.markdown("### Calificaciones (formato macro)")
    st.caption(
        "Replica el formato exacto del macro manual: una fila por colaborador, una columna "
        "por curso, con las mismas fórmulas de resumen (0 por copia, faltas, supletorios, "
        "promedio). Dos hojas en el mismo archivo: Quito y TS R2."
    )

    col1, col2 = st.columns(2)
    opciones_mes = ["Todo el año"] + MESES
    mes_desde_sel = col1.selectbox("Desde", opciones_mes, key="rep_macro_desde")
    mes_hasta_sel = col2.selectbox("Hasta", opciones_mes, key="rep_macro_hasta")
    mes_desde = None if mes_desde_sel == "Todo el año" else mes_desde_sel
    mes_hasta = None if mes_hasta_sel == "Todo el año" else mes_hasta_sel

    combinado = st.checkbox(
        "Incluir supletorios", key="rep_macro_combinado",
        help="Agrega una columna extra por cada curso con supletorio pendiente o rendido, "
             "mostrando su propio resultado.",
    )

    sufijo_archivo = ""
    if mes_desde or mes_hasta:
        sufijo_archivo = f"_{mes_desde or 'inicio'}-{mes_hasta or 'fin'}"

    with st.spinner("Generando Excel…"):
        excel_contenido = api.get_reporte_calificaciones_macro_excel(
            anio, mes_desde=mes_desde, mes_hasta=mes_hasta, combinado=combinado,
        )
    if excel_contenido:
        st.download_button(
            label=f"⬇️ Descargar calificaciones (formato macro) {anio}{sufijo_archivo} (.xlsx)",
            data=excel_contenido,
            file_name=f"calificaciones_macro_{anio}{sufijo_archivo}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="rep_macro_dl_excel",
        )
    else:
        st.info("No se pudo generar el Excel. Verifica la conexión con telcou-api.")
```

- [ ] **Step 3: Manual syntax check**

Run: `cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1" && python -m py_compile api_client.py ui/reporteria.py`
Expected: no output (success)

- [ ] **Step 4: Restart both servers and verify with Playwright**

First, restart telcou-api cleanly (Windows orphan-process gotcha — kill the full process chain, not just the parent):

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
# find and kill any process bound to :8000 (parent + orphaned multiprocessing-fork child), then:
python -m uvicorn app.main:app --reload --port 8000
```

Verify it's really serving the new route before trusting it:

```bash
curl -s http://localhost:8000/openapi.json | grep -o '"/analitica/reporte-calificaciones-macro"'
```

Expected: prints the path (confirms the reloaded server has the new route, not stale code from an orphaned worker).

Restart Streamlit (`streamlit run app.py`), then drive it with the same Playwright/chromium-cli pattern used throughout this session (`playwright-core` from the global n8n install + cached `chromium-1228`):

```js
// scratchpad script — navigate to Reportería, select the new radio option,
// pick a month range, check the checkbox, and capture a real download event.
const { chromium } = require("C:\\Users\\USUARIO\\AppData\\Roaming\\npm\\node_modules\\n8n\\node_modules\\playwright-core");

(async () => {
  const browser = await chromium.launch({
    executablePath: "C:/Users/USUARIO/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe",
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1600 }, acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));

  await page.goto("http://localhost:8501", { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(2000);
  await page.locator('label:has-text("Reportería")').first().click();
  await page.waitForTimeout(3000);
  await page.locator('label:has-text("Calificaciones (formato macro)")').first().click();
  await page.waitForTimeout(2000);

  const bodyText = await page.locator("body").innerText();
  console.log("HAS_TITULO:", bodyText.includes("Calificaciones (formato macro)"));
  console.log("HAS_CHECKBOX:", bodyText.includes("Incluir supletorios"));

  const [download] = await Promise.all([
    page.waitForEvent("download", { timeout: 20000 }),
    page.locator('button:has-text("Descargar calificaciones")').first().click(),
  ]);
  console.log("DOWNLOAD_FILENAME:", download.suggestedFilename());

  console.log("ERRORS:", JSON.stringify(errors));
  await browser.close();
})().catch((e) => { console.error("SCRIPT FAILED:", e); process.exit(1); });
```

Expected console output: `HAS_TITULO: true`, `HAS_CHECKBOX: true`, `DOWNLOAD_FILENAME: calificaciones_macro_2026.xlsx` (or with a month-range suffix depending on default selections), `ERRORS: []`.

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
git add api_client.py ui/reporteria.py
git commit -m "feat: seccion Calificaciones (formato macro) en Reporteria"
```

---

### Task 6: Real-data regression check against the actual example file

This task has no automated pytest assertions — it is a manual verification against the real dev database and the real example file the whole feature was built from, run once before considering the feature done.

- [ ] **Step 1: Generate the report against the real dev DB for a known slice**

```bash
curl -s "http://localhost:8000/analitica/reporte-calificaciones-macro?anio=2026&mes_desde=ENERO&mes_hasta=FEBRERO" \
  -o "C:\Users\USUARIO\AppData\Local\Temp\claude\C--Users-USUARIO-Desktop-DesarrollosRodri-dashboard-telcou-s1\8bcdabbc-5d68-4db7-a36e-7de2d0cef448\scratchpad\calificaciones_macro_generado.xlsx"
```

- [ ] **Step 2: Compare CAGUA OVANDO KLEVER ANTONIO's row against the original**

```python
import openpyxl

original = openpyxl.load_workbook(
    r"C:\Users\USUARIO\Desktop\TelcoU DB new\2026\Quito\ejemplo formatos.xlsx", data_only=True,
)["PERSONAL TECNICO"]
generado = openpyxl.load_workbook(
    r"C:\Users\USUARIO\AppData\Local\Temp\claude\...\calificaciones_macro_generado.xlsx", data_only=True,
)["PERSONAL TECNICO - QUITO"]

fila_original = next(r for r in original.iter_rows(min_row=7, values_only=True) if r[1] == 802165928)
fila_generada = next(r for r in generado.iter_rows(min_row=7, values_only=True) if r[1] == "0802165928")

print("Original (cols I-V):", fila_original[8:22])
print("Generado (cols I..):", fila_generada[8:8 + len(fila_original[8:22])])
```

Expected: the run of `A` values from the original for CAGUA OVANDO's courses matches the generated sheet's cells for the same courses (allowing for the codigo formatting difference — original stores cédula as `int`, generated stores it as the zero-padded `str` `"0802165928"`, per this codebase's established cédula normalization convention).

- [ ] **Step 3: Spot-check 2 more known real employees**

Repeat Step 2 for 2 more cédulas visible in the original file's first ~20 rows (e.g. row 7 "ABRIL CABEZAS MANUEL ALCIVAR" cédula `202037412`, row 8 "ACELDO GRANDA ALEX ALEJANDRO" cédula `1718443169`) — confirm their per-curso cell values (numeric grades and letter codes alike) match between the original and the generated report for the ENERO-FEBRERO courses.

- [ ] **Step 4: Open the generated file in real Excel/LibreOffice**

Open `calificaciones_macro_generado.xlsx` in Excel (or LibreOffice Calc if Excel isn't available) and confirm:
- The 4 summary formulas recalculate to sensible numbers (not `#NAME?`/`#REF!`) for at least 3 rows.
- Both sheet tabs ("PERSONAL TECNICO - QUITO", "PERSONAL TECNICO - TS R2") are present and visually resemble the real macro's layout (merged title block, month headers spanning course columns, día/técnica-sucursal column).

- [ ] **Step 5: Record the result**

No commit for this task (verification only) — note the outcome (pass/fail, any discrepancies found and how they were resolved) in the final summary to the user.

---

### Task 7: Documentation

Matches this session's established practice after every feature — update all 3 documentation locations.

- [ ] **Step 1: `dashboard-telcou-s1/docs/README.md`**

Add a dated bullet under the Reportería section (`## 📥 Reportería` or equivalent existing heading) describing: the new "Calificaciones (formato macro)" report type, that it replicates the real manual macro's exact matrix layout (one row per colaborador, one column per curso, real Excel summary formulas), the month-range filter, and the `combinado` toggle. Add `get_reporte_calificaciones_macro_excel` to the `api_client.py — Funciones disponibles` table.

- [ ] **Step 2: Obsidian vault "TelcoU Dashboard"**

Add a row to `## Historial de desarrollo` (dated today) describing the feature in one line. Update "Secciones disponibles" summary table's Reportería row if it enumerates report types.

- [ ] **Step 3: Obsidian vault "TelcoU DB API" — index file**

Add a row to `## Endpoints API`:
```
| GET | `/analitica/reporte-calificaciones-macro?anio=&mes_desde=&mes_hasta=&combinado=` | **NUEVO (fecha de hoy)** — replica el formato de matriz del macro manual real (una fila por colaborador, una columna por curso, formulas de resumen), 2 hojas fijas (Quito/TS R2) |
```
No new row needed in `## Migraciones aplicadas` (no migration this time — note this explicitly if the table's surrounding prose implies every feature adds one). Add a `- [x]` entry to `## Pendientes` describing the feature, same verbose single-paragraph style as the existing entries, mentioning: the estado→código mapping cross-verified against `app/services/importer.py::interpretar_valor()`, the "nota más reciente" rule for supletorios, the `combinado` mode, and the real-data regression check performed in Task 6.

- [ ] **Step 4: Obsidian vault "TelcoU DB API" — `docs/API_ENDPOINTS.md`**

Add a `###` section for the new endpoint, matching the existing per-endpoint format (param table + JSON/behavior notes), positioned near the other `/analitica/reporte-*` sections. Include the estado→código mapping table and a short note on the "nota más reciente" rule, since this endpoint's behavior is meaningfully different from the other report endpoints in the same file.

- [ ] **Step 5: Obsidian vault "TelcoU DB API" — `docs/ESQUEMA_BD.md`**

No schema changes this feature (no migration) — skip, unless the query pattern itself reveals something worth documenting (e.g., the "matrix report includes inactivos, unlike list reports" distinction) as a note near the existing `notas`/`cursos` table documentation.

- [ ] **Step 6: Commit documentation changes**

```bash
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
git add docs/README.md
git commit -m "docs: reporte de calificaciones formato macro"
```

(Obsidian vault files are outside both git repos tracked in this session — no commit needed for those, per this session's established practice.)
