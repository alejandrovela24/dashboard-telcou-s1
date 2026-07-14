# Convocatoria por Curso + Atajo "Marcar NA" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `convocatoria_habilitada` flag to `Curso` so a newly-uploaded course doesn't get swept into Convocatoria's supletorio pool until the admin explicitly activates it, plus a "Marcar NA" shortcut at curso-upload time that skips the full notify-jefe cycle.

**Architecture:** One new boolean column on `Curso` (migration + model), one new filter condition in the existing `supletorios_pendientes_data()` query, two new admin endpoints (`PATCH .../convocatoria-habilitada`, `POST .../marcar-na`), one field added to an existing response schema (`CursoOut`), and two additions to the existing `ui/administracion.py` (a new subsection + an extension of the carga screen).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + pytest (backend, `telcou-api`); Streamlit + requests (frontend, `dashboard-telcou-s1`).

## Global Constraints

- Every new admin write endpoint must be protected with `X-Admin-Token` via the existing `Depends(verify_admin)` from `app.routers.admin` — never duplicate auth logic.
- Never hardcode secrets.
- Tests whose route triggers a real `db.commit()` must use uuid-parameterized identity values (cédula, `Regional.nombre`, `Curso.codigo`) — `tests/conftest.py`'s `db` fixture only rolls back, doesn't truncate, so fixed values collide across pytest runs on the shared test Postgres DB.
- `app/routers/admin.py` currently has unrelated pre-existing **uncommitted** local changes belonging to the repo owner's own separate work (a `logging` refactor, spanning `CAMBIOS_SESION.md`, `app/routers/admin.py`, `app/services/calculadora.py`, `scripts/marcar_inactivos_por_ausencia.py`). Any task that modifies `admin.py` must stash those four files first (`git stash push -m "preserve-wip" -- CAMBIOS_SESION.md app/routers/admin.py app/services/calculadora.py scripts/marcar_inactivos_por_ausencia.py`), do the work on the clean base, commit, then `git stash pop` and verify no conflict markers (`grep -n "<<<<<<<" app/routers/admin.py`) before moving on.
- On Windows, `Stop-Process` on the uvicorn `--reload` parent can leave an orphaned `multiprocessing-fork` child still bound to the port serving stale code — the verification task must explicitly find and kill that orphan (`Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*multiprocessing-fork*' }`) and confirm new endpoints appear in `/openapi.json`, not just that the port responds.
- This repo's remote serves a live production dashboard (`dashboard-telcou-s1`) — never push without explicit user permission. `telcou-api` has no remote — local commits are always safe.
- This feature depends on and modifies the behavior of the existing, already-in-production Convocatoria feature — the migration's `server_default` must guarantee zero behavior change for any course already loaded before this feature ships.

---

### Task 1: Migración Alembic + campo `Curso.convocatoria_habilitada`

**Files:**
- Create: `alembic/versions/<auto>_add_convocatoria_habilitada_to_cursos.py`
- Modify: `app/models/curso.py`
- Test: Create `tests/test_curso_model.py`
- Test: Modify `tests/test_carga_notas.py`

**Interfaces:**
- Produces: `Curso.convocatoria_habilitada: bool` — client-side ORM default `False` for any newly-inserted `Curso` row that doesn't specify the field explicitly; DB-level `server_default='true'` retroactively applied to all pre-existing rows by the migration. Consumed by Task 2 (filter), Task 3 (endpoint to toggle it), Task 5 (exposed via `CursoOut`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_curso_model.py`:

```python
import uuid

from app.models import Regional, Curso


def test_curso_nuevo_sin_especificar_nace_con_convocatoria_habilitada_false(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito ModeloCurso {sufijo}")
    db.add(reg); db.flush()
    curso = Curso(codigo=f"MC-{sufijo}", nombre="CURSO MODELO", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()

    assert curso.convocatoria_habilitada is False


def test_curso_puede_especificar_convocatoria_habilitada_true_explicitamente(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito ModeloCurso2 {sufijo}")
    db.add(reg); db.flush()
    curso = Curso(codigo=f"MC2-{sufijo}", nombre="CURSO MODELO 2", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id, convocatoria_habilitada=True)
    db.add(curso); db.flush()

    assert curso.convocatoria_habilitada is True
```

Agrega al final de `tests/test_carga_notas.py`:

```python
def test_cargar_curso_nuevo_recargar_no_resetea_convocatoria_habilitada(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito PreservaConvHab {sufijo}")
    db.add(reg); db.flush()
    cedula = f"26{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="PRESERVA CONVHAB", regional_id=reg.id)
    db.add(emp); db.flush()

    filas = [{"cedula": cedula, "nombre": "PRESERVA CONVHAB", "area": None, "correo": None, "nota": Decimal("5.00")}]
    r1 = cargar_curso_nuevo(
        db, filas, codigo=f"PCH-{sufijo}", nombre="CURSO PRESERVA", tipo="VIRTUAL",
        mes="ENERO", fecha_inicio=date(2026, 1, 6), fecha_fin=date(2026, 1, 12),
        anio=2026, regional_nombre=f"Quito PreservaConvHab {sufijo}", importado_por="admin",
    )
    curso = db.query(Curso).filter_by(id=r1["curso_id"]).first()
    curso.convocatoria_habilitada = True
    db.commit()

    r2 = cargar_curso_nuevo(
        db, filas, codigo=f"PCH-{sufijo}", nombre="CURSO PRESERVA", tipo="VIRTUAL",
        mes="ENERO", fecha_inicio=date(2026, 1, 6), fecha_fin=date(2026, 1, 12),
        anio=2026, regional_nombre=f"Quito PreservaConvHab {sufijo}", importado_por="admin",
    )
    assert r2["curso_id"] == r1["curso_id"]

    curso_recargado = db.query(Curso).filter_by(id=r1["curso_id"]).first()
    assert curso_recargado.convocatoria_habilitada is True
```

(`Decimal`, `uuid`, `date`, `Regional`, `Empleado`, `Curso`, `cargar_curso_nuevo` ya están importados en este archivo por tareas anteriores — no dupliques imports.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_curso_model.py -v`
Expected: FAIL — `AttributeError: 'Curso' object has no attribute 'convocatoria_habilitada'` (o similar `TypeError` al pasar `convocatoria_habilitada=True` a `Curso(...)`, ya que el campo no existe todavía).

Run: `pytest tests/test_carga_notas.py -k preserva_convocatoria_habilitada -v`
Expected: FAIL — mismo motivo (`AttributeError`).

- [ ] **Step 3: Modificar el modelo**

En `app/models/curso.py`, cambia el import:

```python
from sqlalchemy import Column, Integer, String, Date, ForeignKey, UniqueConstraint
```

por:

```python
from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, UniqueConstraint, text
```

Agrega el campo nuevo después de `regional_id`:

```python
    regional_id = Column(Integer, ForeignKey("regionales.id"), nullable=False)
    convocatoria_habilitada = Column(Boolean, nullable=False, default=False, server_default=text("true"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_curso_model.py tests/test_carga_notas.py -v`
Expected: todos pasan, incluyendo los 3 nuevos.

- [ ] **Step 5: Generar y aplicar la migración de Alembic**

Run: `alembic revision --autogenerate -m "add_convocatoria_habilitada_to_cursos"`

Esto crea un archivo nuevo en `alembic/versions/` con un `revision` id aleatorio (hex de 12 caracteres) y `down_revision = '77e98ecab951'` (el head actual). Abre el archivo generado y verifica que su contenido coincida con esto (ajusta manualmente si `--autogenerate` no capturó el `server_default` correctamente — es un caso conocido donde autogenerate a veces omite el `server_default` de un `text()`):

```python
"""add_convocatoria_habilitada_to_cursos

Revision ID: <el que Alembic generó>
Revises: 77e98ecab951
Create Date: <fecha generada>

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '<el que Alembic generó>'
down_revision: Union[str, None] = '77e98ecab951'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('cursos', sa.Column('convocatoria_habilitada', sa.Boolean(), server_default=sa.text('true'), nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('cursos', 'convocatoria_habilitada')
    # ### end Alembic commands ###
```

Run: `alembic upgrade head`
Expected: sin errores. Confirma con `alembic current` que el head ahora es el nuevo revision id.

- [ ] **Step 6: Verificar en la BD real que los cursos existentes quedaron en `true`**

```bash
python -c "
from app.database import SessionLocal
from app.models import Curso
db = SessionLocal()
total = db.query(Curso).count()
habilitados = db.query(Curso).filter(Curso.convocatoria_habilitada.is_(True)).count()
print(f'Total cursos: {total}, habilitados: {habilitados}')
db.close()
"
```

Expected: `total` y `habilitados` son el mismo número (todos los cursos ya cargados quedaron en `true`).

- [ ] **Step 7: Commit**

```bash
git add app/models/curso.py tests/test_curso_model.py tests/test_carga_notas.py alembic/versions/
git commit -m "feat: campo Curso.convocatoria_habilitada con migracion (default true retroactivo, false para nuevos)"
```

---

### Task 2: Filtro en `supletorios_pendientes_data()` + fix de regresiones en tests existentes

**Files:**
- Modify: `app/services/convocatoria.py`
- Modify: `tests/test_convocatoria_service.py`
- Modify: `tests/test_convocatoria_endpoints.py`

**Interfaces:**
- Consumes: `Curso.convocatoria_habilitada` (Task 1).
- Produces: `supletorios_pendientes_data()` ahora excluye cursos con `convocatoria_habilitada=False`. Este cambio afecta indirectamente (sin cambiar sus firmas) a `GET /analitica/convocatoria-preview` y `POST /admin/enviar-convocatoria`, ambos ya existentes.

⚠️ **Importante — esta tarea rompe 6 tests existentes si no se corrigen.** Los tests en `test_convocatoria_service.py` y `test_convocatoria_endpoints.py` crean sus propios `Curso(...)` directamente (no vía `cargar_curso_nuevo()`), y ahora que el modelo por defecto pone `convocatoria_habilitada=False`, esos cursos quedarán excluidos del resultado de `supletorios_pendientes_data()` a menos que se les pase `convocatoria_habilitada=True` explícitamente. Esta tarea corrige los 6 sitios exactos.

- [ ] **Step 1: Write the failing test (comportamiento nuevo)**

Agrega al final de `tests/test_convocatoria_service.py`:

```python
def test_curso_sin_convocatoria_habilitada_no_aparece_en_pendientes(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"TS R2 ConvHabFiltro {sufijo}")
    db.add(reg); db.flush()
    emp = Empleado(cedula=f"67{uuid.uuid4().int % 10**8:08d}", nombre="EMP CONVHAB FILTRO", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"CHF-{sufijo}", nombre="CURSO CONVHAB FILTRO", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, convocatoria_habilitada=False)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="REPROBADO", tipo="REGULAR"))
    db.flush()

    data = supletorios_pendientes_data(db, 2026, regional=f"TS R2 ConvHabFiltro {sufijo}")
    assert data == []

    curso.convocatoria_habilitada = True
    db.commit()

    data_habilitado = supletorios_pendientes_data(db, 2026, regional=f"TS R2 ConvHabFiltro {sufijo}")
    assert len(data_habilitado) == 1
```

(`uuid`, `Regional`, `Empleado`, `Curso`, `Nota`, `supletorios_pendientes_data` ya están importados o se importan localmente en este archivo desde tareas anteriores — el import local de `supletorios_pendientes_data` ya existe dentro de `test_pendiente_justificacion_cuenta_como_supletorio_pendiente`, agrega el mismo import local dentro de esta nueva función si no está ya a nivel de módulo.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_convocatoria_service.py -k convocatoria_habilitada_no_aparece -v`
Expected: FAIL — el primer `assert data == []` falla (`data` tiene 1 elemento, porque el filtro todavía no existe).

- [ ] **Step 3: Agregar el filtro**

En `app/services/convocatoria.py`, cambia:

```python
    q_reg = (
        db.query(Nota, Curso, Empleado, Regional)
        .join(Curso, Nota.curso_id == Curso.id)
        .join(Empleado, Nota.empleado_id == Empleado.id)
        .join(Regional, Empleado.regional_id == Regional.id)
        .filter(Nota.tipo == "REGULAR", Curso.anio == anio, Empleado.inactivo.is_(False))
    )
```

por:

```python
    q_reg = (
        db.query(Nota, Curso, Empleado, Regional)
        .join(Curso, Nota.curso_id == Curso.id)
        .join(Empleado, Nota.empleado_id == Empleado.id)
        .join(Regional, Empleado.regional_id == Regional.id)
        .filter(
            Nota.tipo == "REGULAR", Curso.anio == anio, Empleado.inactivo.is_(False),
            Curso.convocatoria_habilitada.is_(True),
        )
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_convocatoria_service.py -k convocatoria_habilitada_no_aparece -v`
Expected: PASS

- [ ] **Step 5: Correr la suite completa de Convocatoria para ver las regresiones esperadas**

Run: `pytest tests/test_convocatoria_service.py tests/test_convocatoria_endpoints.py -v`
Expected: 6 tests FALLAN (los que crean `Curso(...)` sin `convocatoria_habilitada=True`). Anota cuáles fallan — deben ser exactamente estos:
- `test_pendiente_justificacion_cuenta_como_supletorio_pendiente`
- `test_convocatoria_preview_incluye_empleado_con_dia_base_coincidente`
- `test_convocatoria_preview_respeta_excepcion_semanal`
- `test_convocatoria_preview_marca_ya_enviado`
- `test_enviar_convocatoria_modo_prueba_redirige_a_correo_prueba`
- `test_enviar_convocatoria_sin_correo_va_a_fallidos`
- `test_enviar_convocatoria_real_no_modo_prueba_va_al_correo_del_empleado`
- `test_enviar_convocatoria_smtp_falla_en_uno_no_aborta_el_resto`
- `test_enviar_convocatoria_agrupa_recopilatorio_por_jefe_una_sola_vez`
- `test_enviar_convocatoria_modo_prueba_redirige_recopilatorio_y_resumen_ejecutivo`

(Los últimos 6 comparten el mismo `Curso(...)` dentro del helper `_crear_empleado_con_pendiente`, así que un solo fix los arregla a todos.)

- [ ] **Step 6: Corregir `tests/test_convocatoria_service.py`**

Cambia (línea ~146-147):

```python
    curso = Curso(codigo=f"PJ-{sufijo}", nombre="CURSO PENDJUST", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
```

por:

```python
    curso = Curso(codigo=f"PJ-{sufijo}", nombre="CURSO PENDJUST", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, convocatoria_habilitada=True)
```

- [ ] **Step 7: Corregir `tests/test_convocatoria_endpoints.py` — 4 sitios**

Cambia (línea ~124-125, dentro de `test_convocatoria_preview_incluye_empleado_con_dia_base_coincidente`):

```python
    curso = Curso(codigo="PRE01", nombre="CURSO PREVIEW", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, url_telcou="http://moodle/pre01")
```

por:

```python
    curso = Curso(codigo="PRE01", nombre="CURSO PREVIEW", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, url_telcou="http://moodle/pre01",
                  convocatoria_habilitada=True)
```

Cambia (línea ~151-152, dentro de `test_convocatoria_preview_respeta_excepcion_semanal`):

```python
    curso = Curso(codigo="PRE02", nombre="CURSO PREVIEW 2", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
```

por:

```python
    curso = Curso(codigo="PRE02", nombre="CURSO PREVIEW 2", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, convocatoria_habilitada=True)
```

Cambia (línea ~198-199 y ~214-215, ambas dentro de `test_convocatoria_preview_marca_ya_enviado`):

```python
    curso = Curso(codigo="PRE03", nombre="CURSO PREVIEW 3", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
```

por:

```python
    curso = Curso(codigo="PRE03", nombre="CURSO PREVIEW 3", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, convocatoria_habilitada=True)
```

y:

```python
    curso_prueba = Curso(codigo="PRE04", nombre="CURSO PREVIEW 4", tipo="PRESENCIAL",
                         mes="JULIO", anio=2026, regional_id=reg.id)
```

por:

```python
    curso_prueba = Curso(codigo="PRE04", nombre="CURSO PREVIEW 4", tipo="PRESENCIAL",
                         mes="JULIO", anio=2026, regional_id=reg.id, convocatoria_habilitada=True)
```

- [ ] **Step 8: Corregir el helper `_crear_empleado_con_pendiente` (arregla los 6 tests de `/admin/enviar-convocatoria`)**

Cambia (línea ~295-296):

```python
    curso = Curso(codigo=f"ENV-{cedula}", nombre="CURSO ENVIO TEST", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, url_telcou="http://moodle/env")
```

por:

```python
    curso = Curso(codigo=f"ENV-{cedula}", nombre="CURSO ENVIO TEST", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, url_telcou="http://moodle/env",
                  convocatoria_habilitada=True)
```

- [ ] **Step 9: Run tests to verify everything passes**

Run: `pytest tests/test_convocatoria_service.py tests/test_convocatoria_endpoints.py -v`
Expected: todos pasan (los 10 que fallaban en el Step 5, más el nuevo del Step 1).

Run: `pytest -q` (suite completa)
Expected: todos pasan, sin regresiones fuera de estos dos archivos.

- [ ] **Step 10: Commit**

```bash
git add app/services/convocatoria.py tests/test_convocatoria_service.py tests/test_convocatoria_endpoints.py
git commit -m "feat: filtrar supletorios_pendientes_data por Curso.convocatoria_habilitada"
```

---

### Task 3: Endpoint `PATCH /admin/curso/{curso_id}/convocatoria-habilitada`

**Files:**
- Modify: `app/schemas/carga_notas.py`
- Modify: `app/routers/admin.py`
- Test: `tests/test_carga_notas_endpoint.py`

**Interfaces:**
- Consumes: `Curso.convocatoria_habilitada` (Task 1), `verify_admin`.
- Produces: endpoint `PATCH /admin/curso/{curso_id}/convocatoria-habilitada`, devuelve `{"curso_id": int, "convocatoria_habilitada": bool}`. Consumido por Task 6 (frontend `api_client.py`).

⚠️ Antes de empezar: revisa `git status --short app/routers/admin.py CAMBIOS_SESION.md app/services/calculadora.py scripts/marcar_inactivos_por_ausencia.py`. Si aparecen como modificados (uncommitted), son cambios del dueño del repo ajenos a este plan — ejecuta:

```bash
git stash push -m "preserve-wip" -- CAMBIOS_SESION.md app/routers/admin.py app/services/calculadora.py scripts/marcar_inactivos_por_ausencia.py
```

antes de tocar `admin.py`, y `git stash pop` (verificando que no queden `<<<<<<<` en el archivo) después de tu commit al final de esta tarea.

- [ ] **Step 1: Write the failing tests**

Agrega al final de `tests/test_carga_notas_endpoint.py`:

```python
def test_set_convocatoria_habilitada_sin_token_retorna_401(client):
    r = client.patch("/admin/curso/1/convocatoria-habilitada", json={"habilitada": True})
    assert r.status_code == 401


def test_set_convocatoria_habilitada_curso_inexistente_retorna_404(client):
    r = client.patch(
        "/admin/curso/999999/convocatoria-habilitada",
        headers={"X-Admin-Token": settings.admin_token},
        json={"habilitada": True},
    )
    assert r.status_code == 404


def test_set_convocatoria_habilitada_actualiza_el_campo(client, db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito ConvHabEndpoint {sufijo}")
    db.add(reg); db.flush()
    curso = Curso(codigo=f"CHE-{sufijo}", nombre="CURSO CONV HAB ENDPOINT", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id, convocatoria_habilitada=False)
    db.add(curso); db.flush()

    r = client.patch(
        f"/admin/curso/{curso.id}/convocatoria-habilitada",
        headers={"X-Admin-Token": settings.admin_token},
        json={"habilitada": True},
    )
    assert r.status_code == 200
    assert r.json() == {"curso_id": curso.id, "convocatoria_habilitada": True}

    actualizado = db.query(Curso).filter_by(id=curso.id).first()
    assert actualizado.convocatoria_habilitada is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_carga_notas_endpoint.py -k convocatoria_habilitada -v`
Expected: FAIL — `404 Not Found` (la ruta no existe todavía).

- [ ] **Step 3: Agregar el schema**

En `app/schemas/carga_notas.py`, agrega al final del archivo:

```python
class ConvocatoriaHabilitadaIn(BaseModel):
    habilitada: bool
```

- [ ] **Step 4: Agregar el endpoint**

En `app/routers/admin.py`, amplía el import de `app.schemas.carga_notas` (el que ya trae `CargarCursoOut, EmpleadoNuevoIn, EmpleadoNuevoOut, EnviarNovedadIn, EnviarNovedadOut, ResolverNotaIn`):

```python
from app.schemas.carga_notas import (
    CargarCursoOut,
    EmpleadoNuevoIn,
    EmpleadoNuevoOut,
    EnviarNovedadIn,
    EnviarNovedadOut,
    ResolverNotaIn,
    ConvocatoriaHabilitadaIn,
)
```

Agrega el endpoint al final del archivo (después de `resolver_nota`):

```python
@router.patch("/curso/{curso_id}/convocatoria-habilitada")
def set_convocatoria_habilitada(
    curso_id: int,
    body: ConvocatoriaHabilitadaIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    curso.convocatoria_habilitada = body.habilitada
    db.commit()
    return {"curso_id": curso.id, "convocatoria_habilitada": curso.convocatoria_habilitada}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_carga_notas_endpoint.py -v`
Expected: todos pasan, incluyendo los 3 nuevos.

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `pytest -q`
Expected: todos pasan.

- [ ] **Step 7: Commit (y hacer `git stash pop` si aplicó el Step inicial)**

```bash
git add app/schemas/carga_notas.py app/routers/admin.py tests/test_carga_notas_endpoint.py
git commit -m "feat: endpoint PATCH /admin/curso/{curso_id}/convocatoria-habilitada"
```

---

### Task 4: Endpoint `POST /admin/curso/{curso_id}/marcar-na`

**Files:**
- Modify: `app/schemas/carga_notas.py`
- Modify: `app/routers/admin.py`
- Test: `tests/test_novedades_endpoint.py`

**Interfaces:**
- Consumes: `verify_admin`, el mismo patrón de upsert defensivo (`on_conflict_do_nothing` + chequeo de `rowcount`) ya usado en `enviar_novedad`.
- Produces: endpoint `POST /admin/curso/{curso_id}/marcar-na`, devuelve `{"marcados": list[str]}`. Consumido por Task 8 (frontend).

⚠️ Mismo aviso del stash de Task 3 — revisa y aplica `git stash push`/`pop` alrededor de esta tarea si `admin.py` tiene cambios sin commitear del dueño del repo.

- [ ] **Step 1: Write the failing tests**

Agrega al final de `tests/test_novedades_endpoint.py`:

```python
def test_marcar_na_sin_token_retorna_401(client):
    r = client.post("/admin/curso/1/marcar-na", json={"cedulas": []})
    assert r.status_code == 401


def test_marcar_na_curso_inexistente_retorna_404(client):
    r = client.post(
        "/admin/curso/999999/marcar-na",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": []},
    )
    assert r.status_code == 404


def test_marcar_na_crea_nota_no_aplica(client, db):
    curso, empleados = _curso_con_activos_sin_nota(db, n=2)

    r = client.post(
        f"/admin/curso/{curso.id}/marcar-na",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [empleados[0].cedula]},
    )
    assert r.status_code == 200
    assert r.json() == {"marcados": [empleados[0].cedula]}

    nota = db.query(Nota).filter_by(empleado_id=empleados[0].id, curso_id=curso.id).first()
    assert nota is not None
    assert nota.estado == "NO_APLICA"
    assert nota.valor is None
    assert nota.tipo == "REGULAR"

    # el segundo empleado no se marco, no debe tener ninguna nota
    nota_otro = db.query(Nota).filter_by(empleado_id=empleados[1].id, curso_id=curso.id).first()
    assert nota_otro is None


def test_marcar_na_no_sobreescribe_nota_existente(client, db):
    curso, empleados = _curso_con_activos_sin_nota(db, n=1)
    db.add(Nota(empleado_id=empleados[0].id, curso_id=curso.id, valor=Decimal("9.0"),
                estado="APROBADO", tipo="REGULAR", convocatoria=1))
    db.flush()

    r = client.post(
        f"/admin/curso/{curso.id}/marcar-na",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [empleados[0].cedula]},
    )
    assert r.status_code == 200
    assert r.json() == {"marcados": []}

    nota = db.query(Nota).filter_by(empleado_id=empleados[0].id, curso_id=curso.id).first()
    assert nota.estado == "APROBADO"
    assert nota.valor == Decimal("9.0")
```

(`_curso_con_activos_sin_nota`, `Decimal`, `Nota`, `settings` ya están definidos/importados en este archivo desde la tarea de `enviar_novedad` — reutilízalos, no los redefinas.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_novedades_endpoint.py -k marcar_na -v`
Expected: FAIL — `404 Not Found` (la ruta no existe todavía).

- [ ] **Step 3: Agregar los schemas**

En `app/schemas/carga_notas.py`, agrega al final del archivo:

```python
class MarcarNaIn(BaseModel):
    cedulas: list[str]


class MarcarNaOut(BaseModel):
    marcados: list[str]
```

- [ ] **Step 4: Agregar el endpoint**

En `app/routers/admin.py`, amplía el import de `app.schemas.carga_notas` una vez más:

```python
from app.schemas.carga_notas import (
    CargarCursoOut,
    EmpleadoNuevoIn,
    EmpleadoNuevoOut,
    EnviarNovedadIn,
    EnviarNovedadOut,
    ResolverNotaIn,
    ConvocatoriaHabilitadaIn,
    MarcarNaIn,
    MarcarNaOut,
)
```

Agrega el endpoint al final del archivo (después de `set_convocatoria_habilitada`):

```python
@router.post("/curso/{curso_id}/marcar-na", response_model=MarcarNaOut)
def marcar_na(
    curso_id: int,
    body: MarcarNaIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    marcados: list[str] = []
    for cedula in body.cedulas:
        emp = db.query(Empleado).filter_by(cedula=cedula, regional_id=curso.regional_id).first()
        if not emp:
            continue
        stmt = (
            insert(Nota)
            .values(
                empleado_id=emp.id, curso_id=curso_id,
                estado="NO_APLICA", tipo="REGULAR", convocatoria=1,
            )
            .on_conflict_do_nothing(constraint="uq_nota_empleado_curso_tipo_conv")
        )
        result = db.execute(stmt)
        if result.rowcount:
            marcados.append(cedula)
    db.commit()

    return MarcarNaOut(marcados=marcados)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_novedades_endpoint.py -v`
Expected: todos pasan, incluyendo los 4 nuevos.

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `pytest -q`
Expected: todos pasan.

- [ ] **Step 7: Commit (y hacer `git stash pop` si aplicó)**

```bash
git add app/schemas/carga_notas.py app/routers/admin.py tests/test_novedades_endpoint.py
git commit -m "feat: endpoint POST /admin/curso/{curso_id}/marcar-na"
```

---

### Task 5: `CursoOut` + `GET /cursos/` incluyen `convocatoria_habilitada`

**Files:**
- Modify: `app/schemas/curso.py`
- Modify: `app/routers/cursos.py`
- Test: `tests/test_cursos.py`

**Interfaces:**
- Consumes: `Curso.convocatoria_habilitada` (Task 1).
- Produces: `CursoOut.convocatoria_habilitada: bool`, presente en cada elemento de la respuesta de `GET /cursos/`. Consumido por Task 7 (frontend, panel "Convocatoria por curso").

Esta tarea NO toca `app/routers/admin.py` — no requiere el stash/pop.

- [ ] **Step 1: Write the failing test**

Agrega al final de `tests/test_cursos.py`:

```python
def test_listar_cursos_incluye_convocatoria_habilitada(client, datos):
    r = client.get("/cursos/?anio=2025")
    assert r.status_code == 200
    curso_json = next(c for c in r.json() if c["id"] == datos["curso"].id)
    assert "convocatoria_habilitada" in curso_json
    assert curso_json["convocatoria_habilitada"] is False
```

(La fixture `datos` crea su `Curso(...)` sin especificar `convocatoria_habilitada`, así que hereda el default de aplicación `False` — por eso el assert espera `False` aquí.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cursos.py -k incluye_convocatoria_habilitada -v`
Expected: FAIL — `KeyError` o `AssertionError` (`"convocatoria_habilitada" in curso_json` es `False`, porque el campo no está en la respuesta todavía).

- [ ] **Step 3: Agregar el campo al schema**

En `app/schemas/curso.py`, cambia:

```python
class CursoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo: str
    url_telcou: str | None
    mes: str | None
    fecha_inicio: date | None
    fecha_fin: date | None
    anio: int
    regional_nombre: str
    model_config = ConfigDict(from_attributes=True)
```

por:

```python
class CursoOut(BaseModel):
    id: int
    codigo: str
    nombre: str
    tipo: str
    url_telcou: str | None
    mes: str | None
    fecha_inicio: date | None
    fecha_fin: date | None
    anio: int
    regional_nombre: str
    convocatoria_habilitada: bool
    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 4: Agregar el campo a la construcción en `listar_cursos()`**

En `app/routers/cursos.py`, cambia:

```python
        CursoOut(
            id=c.id,
            codigo=c.codigo,
            nombre=c.nombre,
            tipo=c.tipo,
            url_telcou=c.url_telcou,
            mes=c.mes,
            fecha_inicio=c.fecha_inicio,
            fecha_fin=c.fecha_fin,
            anio=c.anio,
            regional_nombre=c.regional.nombre,
        )
```

por:

```python
        CursoOut(
            id=c.id,
            codigo=c.codigo,
            nombre=c.nombre,
            tipo=c.tipo,
            url_telcou=c.url_telcou,
            mes=c.mes,
            fecha_inicio=c.fecha_inicio,
            fecha_fin=c.fecha_fin,
            anio=c.anio,
            regional_nombre=c.regional.nombre,
            convocatoria_habilitada=c.convocatoria_habilitada,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_cursos.py -v`
Expected: todos pasan, incluyendo el nuevo.

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `pytest -q`
Expected: todos pasan (agregar un campo a `CursoOut` es compatible hacia atrás — ningún consumidor existente se rompe).

- [ ] **Step 7: Commit**

```bash
git add app/schemas/curso.py app/routers/cursos.py tests/test_cursos.py
git commit -m "feat: GET /cursos/ incluye convocatoria_habilitada en cada CursoOut"
```

---

### Task 6: Frontend — `api_client.py`, dos funciones nuevas

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\api_client.py`

**Interfaces:**
- Consumes: endpoints de Tasks 3 y 4.
- Produces: `set_convocatoria_habilitada(curso_id, habilitada) -> dict | None`, `marcar_na(curso_id, cedulas) -> dict | None`. Consumidas por Tasks 7 y 8.

- [ ] **Step 1: Agregar las funciones nuevas**

Agrega al final de `api_client.py`:

```python
def set_convocatoria_habilitada(curso_id: int, habilitada: bool) -> dict | None:
    return _patch(f"/admin/curso/{curso_id}/convocatoria-habilitada", {"habilitada": habilitada})


def marcar_na(curso_id: int, cedulas: list[str]) -> dict | None:
    return _post(f"/admin/curso/{curso_id}/marcar-na", {"cedulas": cedulas})
```

- [ ] **Step 2: Verificar que el archivo no tiene errores de sintaxis**

Run: `python -c "import ast; ast.parse(open('api_client.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api_client.py
git commit -m "feat: funciones de api_client para convocatoria_habilitada y marcar_na"
```

---

### Task 7: Frontend — sección "Convocatoria por curso" en `ui/administracion.py`

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\ui\administracion.py`

**Interfaces:**
- Consumes: `api.get_cursos(anio)` (ya existe, ahora trae `convocatoria_habilitada`), `api.set_convocatoria_habilitada(curso_id, habilitada)` (Task 6).
- Produces: `_seccion_convocatoria_por_curso(anio: int) -> None`, llamada desde `render_tab_administracion`.

- [ ] **Step 1: Agregar la función nueva y registrarla en `render_tab_administracion`**

En `ui/administracion.py`, cambia:

```python
def render_tab_administracion(anio: int) -> None:
    st.title("🛠️ Administración")

    _seccion_carga_curso(anio)
    st.divider()
    _seccion_novedades(anio)
```

por:

```python
def render_tab_administracion(anio: int) -> None:
    st.title("🛠️ Administración")

    _seccion_carga_curso(anio)
    st.divider()
    _seccion_convocatoria_por_curso(anio)
    st.divider()
    _seccion_novedades(anio)
```

Agrega la función nueva en cualquier punto del archivo (por ejemplo, justo antes de `_ESTADOS_RESOLUCION`):

```python
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
            habilitada = st.toggle(
                "Convocatoria", value=c["convocatoria_habilitada"],
                key=f"conv_hab_{c['id']}", label_visibility="collapsed",
            )
            if habilitada != c["convocatoria_habilitada"]:
                resultado = api.set_convocatoria_habilitada(c["id"], habilitada)
                if resultado:
                    st.rerun()
```

- [ ] **Step 2: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('ui/administracion.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/administracion.py
git commit -m "feat: seccion Convocatoria por curso en Administracion"
```

---

### Task 8: Frontend — atajo "Marcar NA" en la carga de curso nuevo

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\ui\administracion.py`

**Interfaces:**
- Consumes: `api.get_no_rindieron(curso_id)` (ya existe), `api.marcar_na(curso_id, cedulas)` (Task 6).
- Produces: extensión de `_seccion_carga_curso` — nueva sección visible tras una carga exitosa en Modo A.

- [ ] **Step 1: Extender `_seccion_carga_curso`**

⚠️ El `resultado` guardado en `st.session_state` puede venir de una carga anterior en el OTRO modo (por ejemplo, el admin subió un supletorio en Modo B, no le dio "Limpiar", y luego cambió el radio a "Curso nuevo" sin volver a subir nada). Comparar contra el `modo` actual del radio en ese momento mostraría el atajo "Marcar NA" para el curso equivocado. Por eso este paso también guarda el modo junto con el resultado, y Task 8 compara contra ESE modo guardado, no contra el radio en vivo.

En `ui/administracion.py`, localiza la línea que guarda el resultado tras una carga exitosa:

```python
        if resultado:
            st.session_state["admin_ultimo_resultado"] = resultado
```

Reemplázala por:

```python
        if resultado:
            st.session_state["admin_ultimo_resultado"] = resultado
            st.session_state["admin_ultimo_resultado_modo"] = modo
```

Luego localiza el bloque final de `_seccion_carga_curso` (el que muestra el resumen tras una carga):

```python
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
```

Reemplázalo por (agrega el bloque de "Marcar NA" al final, solo si el resultado guardado vino de Modo A):

```python
    resultado = st.session_state.get("admin_ultimo_resultado")
    if resultado:
        col_msg, col_clear = st.columns([5, 1])
        with col_msg:
            st.success(f"✅ Nuevos: {resultado['nuevos']} · Actualizados: {resultado['actualizados']}")
        with col_clear:
            if st.button("Limpiar", key="admin_limpiar_resultado"):
                st.session_state.pop("admin_ultimo_resultado", None)
                st.session_state.pop("admin_ultimo_resultado_modo", None)
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
        if st.session_state.get("admin_ultimo_resultado_modo") == "nuevo":
            _seccion_marcar_na(resultado["curso_id"])
```

Agrega la nueva función en cualquier punto del archivo (por ejemplo, justo después de `_form_alta_empleado`):

```python
def _seccion_marcar_na(curso_id: int) -> None:
    with st.spinner("Cargando activos sin nota…"):
        datos = api.get_no_rindieron(curso_id)

    if not datos or not datos.get("sin_notificar"):
        return

    st.markdown(f"#### 🚫 Activos sin nota en este curso ({len(datos['sin_notificar'])})")
    st.caption(
        "Si ya sabes que alguno de estos no fue convocado a este curso, márcalo NA directamente "
        "acá — sin esperar respuesta del jefe. Quien no marques sigue su camino normal por Novedades."
    )

    seleccionadas = []
    for p in datos["sin_notificar"]:
        marcado = st.checkbox(
            f"{p['nombre']} — {p['cedula']}", value=False,
            key=f"na_{curso_id}_{p['cedula']}",
        )
        if marcado:
            seleccionadas.append(p["cedula"])

    if st.button(f"Marcar NA ({len(seleccionadas)} seleccionados)", key=f"btn_marcar_na_{curso_id}"):
        if not seleccionadas:
            st.error("Selecciona al menos una persona.")
            return

        with st.spinner("Marcando…"):
            resultado = api.marcar_na(curso_id, seleccionadas)

        if resultado:
            st.success(f"✅ Marcados como NA: {len(resultado['marcados'])}")
            st.rerun()
```

- [ ] **Step 2: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('ui/administracion.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/administracion.py
git commit -m "feat: atajo Marcar NA tras cargar un curso nuevo"
```

---

### Task 9: Verificación end-to-end

**Files:** ninguno (solo verificación manual/scripted, salvo que se encuentre un bug real).

- [ ] **Step 1: Correr la suite completa del backend**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && pytest -q`
Expected: todos los tests pasan. Si aparece cualquier fallo nuevo (fuera del ya conocido y no relacionado en `test_calculadora.py`, si reaparece), es una regresión real — investigar y corregir antes de continuar.

- [ ] **Step 2: Reiniciar el backend limpiamente (cuidado con el huérfano de Windows)**

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*multiprocessing-fork*' } | Select-Object ProcessId, ParentProcessId
```

Matar todos los PID de esa cadena (`Stop-Process -Id <pid1>,<pid2>,... -Force`), luego iniciar de nuevo:

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Confirmar que los endpoints nuevos aparecen en el esquema (no solo que el puerto responde):

```bash
curl -s http://localhost:8000/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print('/admin/curso/{curso_id}/convocatoria-habilitada' in d['paths']); print('/admin/curso/{curso_id}/marcar-na' in d['paths'])"
```

Expected: `True` en ambas líneas.

- [ ] **Step 3: Smoke test contra datos reales — un curso de prueba nace sin convocatoria y no aparece en la vista previa**

```bash
ADMIN_TOKEN=$(python -c "from app.config import settings; print(settings.admin_token)")

# Crear un curso de prueba minimo con un CSV de una sola fila, con un empleado real que tenga REPROBADO
curl -s -X POST \
  "http://localhost:8000/admin/cargar-curso?modo=nuevo&codigo=CONVHAB-TEST&nombre=CURSO+CONVHAB+TEST&tipo=VIRTUAL&mes=ENERO&fecha_inicio=2026-01-06&fecha_fin=2026-01-12&anio=2026&regional=Quito" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "archivo=@ruta/a/un/csv/de/prueba.csv" | python -m json.tool
```

Anota el `curso_id` de la respuesta. Confirma que nace apagado:

```bash
python -c "
from app.database import SessionLocal
from app.models import Curso
db = SessionLocal()
c = db.query(Curso).filter_by(codigo='CONVHAB-TEST', anio=2026).first()
print('convocatoria_habilitada:', c.convocatoria_habilitada)
db.close()
"
```

Expected: `False`.

- [ ] **Step 4: Activar el curso y confirmar el cambio**

```bash
curl -s -X PATCH "http://localhost:8000/admin/curso/<CURSO_ID>/convocatoria-habilitada" \
  -H "X-Admin-Token: $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"habilitada": true}' | python -m json.tool
```

Expected: `{"curso_id": <CURSO_ID>, "convocatoria_habilitada": true}`.

- [ ] **Step 5: Verificación en el dashboard vía Playwright**

Reiniciar también el dashboard (mismo cuidado con procesos huérfanos). Con ambos servidores arriba:

```javascript
const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Users/USUARIO/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe',
  });
  const page = await browser.newPage({ viewport: { width: 1400, height: 1400 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  await page.goto('http://localhost:8501', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  const adminRadio = page.locator('label', { hasText: 'Administración' }).first();
  await adminRadio.click();
  await page.waitForTimeout(3000);

  const bodyText = await page.locator('body').innerText();
  console.log('HAS_CONVOCATORIA_POR_CURSO:', bodyText.includes('Convocatoria por curso'));
  console.log('HAS_TRACEBACK:', bodyText.includes('Traceback'));
  console.log('ERRORS:', JSON.stringify(errors));
  await page.screenshot({ path: 'administracion_convhab_check.png', fullPage: true });
  await browser.close();
})();
```

Expected: `HAS_CONVOCATORIA_POR_CURSO: true`, `HAS_TRACEBACK: false`, `ERRORS: []`. Revisar el screenshot.

- [ ] **Step 6: Limpieza de los datos de prueba**

El curso `CONVHAB-TEST` y sus notas quedaron en la base de datos real. **No borrar sin confirmar primero con el usuario** — decidir junto con él si se eliminan o se dejan como evidencia de la verificación, igual que en la feature anterior.

---

### Task 10: Documentación

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\docs\README.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\docs\TABS.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\docs\ARQUITECTURA.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\docs\API_CLIENTE.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\TelcoU Dashboard.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU DB API\docs\API_ENDPOINTS.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU DB API\TelcoU DB API.md`

- [ ] **Step 1: `dashboard-telcou-s1/docs/README.md`**

En la sección `### 🛠️ Administración`, agregar un párrafo describiendo el nuevo panel "Convocatoria por curso" (qué hace, por qué existe — cursos nuevos nacen sin convocatoria) y el atajo "Marcar NA" (solo en Modo A, crea la nota directo sin pasar por Novedades). Agregar las 2 funciones nuevas de `api_client.py` a la tabla de funciones disponibles.

- [ ] **Step 2: Vault "TelcoU Dashboard" — `TABS.md`, `ARQUITECTURA.md`, `API_CLIENTE.md`, índice**

`TABS.md`: dentro de la sección `## 🛠️ Administración` ya existente, agregar dos subsecciones nuevas con el mismo nivel de detalle que las existentes: "Convocatoria por curso" (qué es `convocatoria_habilitada`, por qué nace en `false` para cursos nuevos, cómo se activa) y "Atajo Marcar NA" (solo tras Modo A, reutiliza `no-rindieron`, crea `NO_APLICA` directo). `ARQUITECTURA.md`: no requiere cambios de estructura de archivos (no se crean archivos nuevos, solo se modifica `ui/administracion.py` existente) — solo agregar una nota si el archivo documenta el modelo `Curso` en algún lado. `API_CLIENTE.md`: documentar las 2 funciones nuevas. Índice (`TelcoU Dashboard.md`): agregar entrada al historial de desarrollo con fecha 2026-07-14.

- [ ] **Step 3: Vault "TelcoU DB API" — `API_ENDPOINTS.md`, índice**

`API_ENDPOINTS.md`: documentar los 2 endpoints nuevos (`PATCH /admin/curso/{curso_id}/convocatoria-habilitada`, `POST /admin/curso/{curso_id}/marcar-na`) con el mismo formato que los endpoints existentes de Administración (query/body params, ejemplos de respuesta). Documentar el campo nuevo `Curso.convocatoria_habilitada` y su rol en `supletorios_pendientes_data()`. Documentar la migración nueva (revision id, qué hace, por qué el `server_default` es crítico para no romper cursos existentes). Índice (`TelcoU DB API.md`): agregar filas a la tabla de endpoints y al historial/pendientes con fecha 2026-07-14.

- [ ] **Step 4: Commit (solo el repo dashboard-telcou-s1 — los vaults de Obsidian no son un repo git)**

```bash
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
git add docs/README.md
git commit -m "docs: documentar Convocatoria por curso y atajo Marcar NA"
```

---

## Self-Review

**Cobertura del spec:** §2 (modelo de datos + migración) → Task 1. §3 (filtro en Convocatoria) → Task 2. §4 (panel Convocatoria por curso, incluyendo el cambio a `CursoOut`) → Tasks 3, 5, 7. §5 (atajo Marcar NA) → Tasks 4, 8. §6 (endpoints nuevos) → Tasks 3, 4. §7 (UI) → Tasks 6, 7, 8. §8 (seguridad) → `verify_admin` en Tasks 3 y 4, `ON CONFLICT DO NOTHING` en Task 4. §9 (testing) → cubierto en cada task, incluyendo el fix explícito de las 6 regresiones existentes en Task 2 (no estaba en el spec original pero es una consecuencia directa y necesaria del cambio de §2/§3, descubierta al leer el código real antes de escribir el plan). §10 (verificación) → Task 9.

**Consistencia de tipos:** `set_convocatoria_habilitada(curso_id: int, habilitada: bool) -> dict | None` (Task 6) coincide con el endpoint de Task 3 (`ConvocatoriaHabilitadaIn.habilitada: bool`, respuesta `{curso_id, convocatoria_habilitada}`). `marcar_na(curso_id: int, cedulas: list[str]) -> dict | None` (Task 6) coincide con `MarcarNaIn.cedulas: list[str]` / `MarcarNaOut.marcados: list[str]` (Task 4). `_seccion_marcar_na(curso_id: int)` (Task 8) usa `api.get_no_rindieron(curso_id)["sin_notificar"]` — mismo shape ya establecido por la feature anterior (`{cedula, nombre, jefe_correo, nota_id}` por persona), y solo se leen `cedula`/`nombre`, que sí existen ahí.

**Placeholder scan:** sin "TBD"/"TODO". El único punto con un valor no fijado de antemano es el `revision id` autogenerado de Alembic (Task 1, Step 5) — es correcto que sea así, ya que Alembic lo genera en el momento; el plan da instrucciones exactas de qué verificar en el archivo resultante, no dejando ambigüedad sobre el contenido real.
