# Ventana de Convocatoria a Supletorios — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a coordinator manage each TS R2 employee's supletorio training day (permanent or single-week change, with reason and full traceability) and bulk-email pending-supletorio employees by day/regional, with a mandatory test mode before any real send.

**Architecture:** Two repos. `telcou-api` (FastAPI + PostgreSQL + SQLAlchemy + Alembic) gets three new/changed tables, a shared `app/services/convocatoria.py` (day resolution + the now-reusable pending-supletorios query) and `app/services/mailer.py` (SMTP via stdlib `smtplib`), plus five endpoints spread across the existing `empleados`, `analitica`, and `admin` routers. `dashboard-telcou-s1` (Streamlit) gets a new `ui/convocatoria.py` tab that consumes those endpoints through two new write helpers (`_patch`/`_post`) added to `api_client.py`.

**Tech Stack:** Python 3.12, FastAPI 0.111, SQLAlchemy 2.0, Alembic 1.13, pytest 8.2 + httpx TestClient, Streamlit 1.57, `smtplib`/`email.mime` (stdlib, no new dependency).

**Full design reference:** `docs/superpowers/specs/2026-07-08-convocatoria-supletorios-design.md` (this repo) — read it before starting; this plan implements it section by section.

## Global Constraints

- Backend repo: `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api` (no git remote — commits are local only)
- Frontend repo: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1` (has `origin` on GitHub, which runs the **live** deployed dashboard — never `git push` without explicit user approval; local commits only)
- `SMTP_HOST=smtp.telconet.ec`, `SMTP_PORT=465`, `smtplib.SMTP_SSL` (not STARTTLS) — already in `.env`/`.env.example` of `telcou-api`
- Días válidos: exactamente `LUNES`, `MARTES`, `MIERCOLES`, `JUEVES`, `VIERNES` (sin tildes, sin espacios) — cualquier otro valor se normaliza a `None`
- Escrituras (`PATCH`, `POST /admin/...`) requieren header `X-Admin-Token`, verificado con `app.routers.admin.verify_admin` (ya existe, reutilizar — no duplicar)
- Sin dependencias nuevas en `requirements.txt` de ningún repo
- Todas las tablas/columnas nuevas via Alembic migration (`alembic revision -m "..."` → completar `upgrade()`/`downgrade()` a mano, siguiendo el patrón de `alembic/versions/ed3f38a536b6_add_variables_adicionales.py`)
- Todo archivo de test nuevo sigue el patrón ya establecido: fixture `client(db)` con `app.dependency_overrides[get_db] = lambda: db`, fixtures de datos con `Regional`/`Empleado`/`Curso`/`Nota` reales (no mocks de ORM)

---

## Fase A — Servicios base (sin endpoints todavía)

### Task 1: `app/services/convocatoria.py` — días válidos y cálculo de semana

**Files:**
- Create: `app/services/convocatoria.py`
- Test: `tests/test_convocatoria_service.py`

**Interfaces:**
- Produces: `DIAS_VALIDOS: set[str]`, `lunes_de_semana(d: date) -> date`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_convocatoria_service.py
from datetime import date
from app.services.convocatoria import DIAS_VALIDOS, lunes_de_semana


def test_dias_validos_contiene_exactamente_lunes_a_viernes():
    assert DIAS_VALIDOS == {"LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"}


def test_lunes_de_semana_de_un_jueves():
    assert lunes_de_semana(date(2026, 7, 9)) == date(2026, 7, 6)


def test_lunes_de_semana_de_un_lunes_es_el_mismo_dia():
    assert lunes_de_semana(date(2026, 7, 6)) == date(2026, 7, 6)


def test_lunes_de_semana_de_un_domingo():
    assert lunes_de_semana(date(2026, 7, 12)) == date(2026, 7, 6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m pytest tests/test_convocatoria_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.convocatoria'`

- [ ] **Step 3: Write minimal implementation**

```python
# app/services/convocatoria.py
from datetime import date, timedelta

DIAS_VALIDOS = {"LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"}


def lunes_de_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_convocatoria_service.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
git add app/services/convocatoria.py tests/test_convocatoria_service.py
git commit -m "feat: dias validos y calculo de lunes de semana para convocatoria"
```

---

### Task 2: Columna `correo` en `variables_adicionales`

**Files:**
- Modify: `app/models/variable_adicional.py`
- Create: alembic migration (via `alembic revision`)
- Modify: `scripts/importar_variables_adicionales.py`
- Test: `tests/test_convocatoria_service.py` (append)

**Interfaces:**
- Consumes: `DIAS_VALIDOS` from Task 1
- Produces: `VariableAdicional.correo: str | None`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_convocatoria_service.py`:

```python
from app.models import Regional, Empleado
from app.models.variable_adicional import VariableAdicional


def test_variable_adicional_guarda_correo_del_empleado(db):
    reg = Regional(nombre="TS R2 VarAdic")
    db.add(reg); db.flush()
    emp = Empleado(cedula="1111111111", nombre="EMP VARADIC", regional_id=reg.id)
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, correo="empleado@telconet.ec", dia="LUNES"))
    db.flush()

    va = db.query(VariableAdicional).filter_by(empleado_id=emp.id).first()
    assert va.correo == "empleado@telconet.ec"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convocatoria_service.py::test_variable_adicional_guarda_correo_del_empleado -v`
Expected: FAIL — `TypeError: 'correo' is an invalid keyword argument for VariableAdicional`

- [ ] **Step 3: Add the column to the model**

Edit `app/models/variable_adicional.py`:

```python
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class VariableAdicional(Base):
    __tablename__ = "variables_adicionales"

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False, unique=True)
    correo = Column(String(150))
    jefe_correo = Column(String(150))
    jefe_inmediato = Column(String(200))
    dia = Column(String(10))

    empleado = relationship("Empleado", back_populates="variable_adicional")
```

(`dia` shrinks from `String(30)` to `String(10)` since it's now strictly normalized to `LUNES`..`VIERNES` or `NULL` — longest valid value `MIERCOLES` is 9 chars.)

- [ ] **Step 4: Generate and fill in the migration**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -m alembic revision -m "add_correo_to_variables_adicionales"`

This creates `alembic/versions/<hash>_add_correo_to_variables_adicionales.py` with `down_revision = 'ed3f38a536b6'` (current head) auto-filled. Edit its body:

```python
def upgrade() -> None:
    op.add_column('variables_adicionales', sa.Column('correo', sa.String(length=150), nullable=True))
    op.alter_column('variables_adicionales', 'dia', type_=sa.String(length=10))


def downgrade() -> None:
    op.alter_column('variables_adicionales', 'dia', type_=sa.String(length=30))
    op.drop_column('variables_adicionales', 'correo')
```

Run: `python -m alembic upgrade head`
Expected: `Running upgrade ed3f38a536b6 -> <hash>, add_correo_to_variables_adicionales`

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_convocatoria_service.py -v`
Expected: 5 passed

- [ ] **Step 6: Update the import script — correo + robust día normalization**

Edit `scripts/importar_variables_adicionales.py`. Replace the `normalizar_dia` function and the `importar()` body's `VariableAdicional` insert:

```python
import sys
sys.path.insert(0, ".")

from app.services.convocatoria import DIAS_VALIDOS

_DIA_ALIASES = {
    "MIÉRCOLES": "MIERCOLES",
    "MIERC": "MIERCOLES",
    "MARTE": "MARTES",
    "LUNEZ": "LUNES",
}


def normalizar_dia(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    s = _DIA_ALIASES.get(s, s)
    return s if s in DIAS_VALIDOS else None
```

In the `importar()` function, add a `correo` read next to the existing `jefe_correo`/`jefe_inmediato`/`dia` reads (column `COL_CORREO` is already defined as `4` in the existing `COL_CI, COL_CORREO, COL_JEFE_CORREO, COL_JEFE_INMEDIATO, COL_DIA = 3, 4, 5, 6, 10` line — it was never wired in):

```python
        correo = ws.cell(row=fila, column=COL_CORREO).value
        jefe_correo = ws.cell(row=fila, column=COL_JEFE_CORREO).value
        jefe_inmediato = ws.cell(row=fila, column=COL_JEFE_INMEDIATO).value
        dia = normalizar_dia(ws.cell(row=fila, column=COL_DIA).value)

        if dry_run:
            totales["nuevos"] += 1
            continue

        stmt = (
            insert(VariableAdicional)
            .values(
                empleado_id=empleado_id,
                correo=str(correo).strip() if correo else None,
                jefe_correo=str(jefe_correo).strip() if jefe_correo else None,
                jefe_inmediato=str(jefe_inmediato).strip() if jefe_inmediato else None,
                dia=dia,
            )
            .on_conflict_do_update(
                index_elements=["empleado_id"],
                set_={"correo": str(correo).strip() if correo else None,
                      "jefe_correo": str(jefe_correo).strip() if jefe_correo else None,
                      "jefe_inmediato": str(jefe_inmediato).strip() if jefe_inmediato else None,
                      "dia": dia},
            )
        )
```

This script has no dedicated pytest coverage (matches the existing convention — no `scripts/*.py` has tests in this repo); verify it manually in Task 18 with `--dry-run` before the real run.

- [ ] **Step 7: Commit**

```bash
git add app/models/variable_adicional.py alembic/versions/*_add_correo_to_variables_adicionales.py \
        scripts/importar_variables_adicionales.py tests/test_convocatoria_service.py
git commit -m "feat: correo del empleado en variables_adicionales, normalizacion robusta de dia"
```

---

### Task 3: Tabla `dia_cambios` (modelo + migración)

**Files:**
- Create: `app/models/dia_cambio.py`
- Modify: `app/models/__init__.py`
- Modify: `app/models/empleado.py`
- Create: alembic migration
- Test: `tests/test_convocatoria_service.py` (append)

**Interfaces:**
- Produces: `DiaCambio` model (fields per spec Section 2: `empleado_id`, `dia_nuevo`, `tipo`, `semana_inicio`, `motivo`, `editado_por`, `fecha_creacion`)

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from app.models.dia_cambio import DiaCambio


def test_dia_cambio_semanal_no_requiere_semana_inicio_a_nivel_orm(db):
    reg = Regional(nombre="TS R2 DiaCambio")
    db.add(reg); db.flush()
    emp = Empleado(cedula="2222222222", nombre="EMP DIACAMBIO", regional_id=reg.id)
    db.add(emp); db.flush()

    cambio = DiaCambio(
        empleado_id=emp.id, dia_nuevo="JUEVES", tipo="SEMANAL",
        semana_inicio=date(2026, 7, 6), motivo="no pudo asistir el lunes",
    )
    db.add(cambio); db.flush()

    guardado = db.query(DiaCambio).filter_by(empleado_id=emp.id).first()
    assert guardado.dia_nuevo == "JUEVES"
    assert guardado.tipo == "SEMANAL"
    assert guardado.semana_inicio == date(2026, 7, 6)
    assert guardado.fecha_creacion is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convocatoria_service.py::test_dia_cambio_semanal_no_requiere_semana_inicio_a_nivel_orm -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.dia_cambio'`

- [ ] **Step 3: Create the model**

```python
# app/models/dia_cambio.py
from sqlalchemy import Column, Integer, String, Date, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class DiaCambio(Base):
    __tablename__ = "dia_cambios"

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    dia_nuevo = Column(String(10), nullable=False)
    tipo = Column(String(12), nullable=False)  # PERMANENTE | SEMANAL
    semana_inicio = Column(Date, nullable=True)  # solo si tipo=SEMANAL
    motivo = Column(Text, nullable=False)
    editado_por = Column(String(150), nullable=True)
    fecha_creacion = Column(DateTime, server_default=func.now(), nullable=False)

    empleado = relationship("Empleado", back_populates="dia_cambios")
```

- [ ] **Step 4: Wire into `__init__.py` and `Empleado`**

Edit `app/models/__init__.py`:

```python
from app.models.regional import Regional
from app.models.empleado import Empleado
from app.models.curso import Curso
from app.models.curso_alias import CursoAlias
from app.models.curso_codigo_regional import CursoCodigoRegional
from app.models.nota import Nota
from app.models.importacion import Importacion
from app.models.variable_adicional import VariableAdicional
from app.models.dia_cambio import DiaCambio

__all__ = ["Regional", "Empleado", "Curso", "CursoAlias", "CursoCodigoRegional", "Nota",
           "Importacion", "VariableAdicional", "DiaCambio"]
```

Edit `app/models/empleado.py`, add after the `variable_adicional` relationship:

```python
    dia_cambios = relationship("DiaCambio", back_populates="empleado", cascade="all, delete-orphan")
```

- [ ] **Step 5: Generate and fill in the migration**

Run: `python -m alembic revision -m "add_dia_cambios"`

Edit the generated file (`down_revision` = the hash from Task 2's migration):

```python
def upgrade() -> None:
    op.create_table(
        'dia_cambios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empleado_id', sa.Integer(), nullable=False),
        sa.Column('dia_nuevo', sa.String(length=10), nullable=False),
        sa.Column('tipo', sa.String(length=12), nullable=False),
        sa.Column('semana_inicio', sa.Date(), nullable=True),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('editado_por', sa.String(length=150), nullable=True),
        sa.Column('fecha_creacion', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['empleado_id'], ['empleados.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_dia_cambios_id'), 'dia_cambios', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dia_cambios_id'), table_name='dia_cambios')
    op.drop_table('dia_cambios')
```

Run: `python -m alembic upgrade head`
Expected: `Running upgrade <task2_hash> -> <hash>, add_dia_cambios`

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_convocatoria_service.py -v`
Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add app/models/dia_cambio.py app/models/__init__.py app/models/empleado.py \
        alembic/versions/*_add_dia_cambios.py tests/test_convocatoria_service.py
git commit -m "feat: tabla dia_cambios (log de auditoria y excepciones semanales)"
```

---

### Task 4: `resolver_dia_efectivo()` en el servicio de convocatoria

**Files:**
- Modify: `app/services/convocatoria.py`
- Test: `tests/test_convocatoria_service.py` (append)

**Interfaces:**
- Consumes: `DiaCambio`, `VariableAdicional` models (Tasks 2, 3)
- Produces: `resolver_dia_efectivo(db: Session, empleado_id: int, semana_inicio: date) -> str | None`

- [ ] **Step 1: Write the failing test**

```python
from app.models.dia_cambio import DiaCambio
from app.services.convocatoria import resolver_dia_efectivo


def test_resolver_dia_efectivo_usa_dia_base_sin_excepcion(db):
    reg = Regional(nombre="TS R2 Resolver1")
    db.add(reg); db.flush()
    emp = Empleado(cedula="3333333333", nombre="EMP RESOLVER1", regional_id=reg.id)
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, dia="LUNES"))
    db.flush()

    assert resolver_dia_efectivo(db, emp.id, date(2026, 7, 6)) == "LUNES"


def test_resolver_dia_efectivo_usa_excepcion_semanal_vigente_y_vuelve_al_dia_base_otra_semana(db):
    reg = Regional(nombre="TS R2 Resolver2")
    db.add(reg); db.flush()
    emp = Empleado(cedula="4444444444", nombre="EMP RESOLVER2", regional_id=reg.id)
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, dia="LUNES"))
    db.add(DiaCambio(
        empleado_id=emp.id, dia_nuevo="JUEVES", tipo="SEMANAL",
        semana_inicio=date(2026, 7, 6), motivo="no pudo asistir el lunes",
    ))
    db.flush()

    assert resolver_dia_efectivo(db, emp.id, date(2026, 7, 6)) == "JUEVES"
    assert resolver_dia_efectivo(db, emp.id, date(2026, 7, 13)) == "LUNES"


def test_resolver_dia_efectivo_sin_variable_adicional_retorna_none(db):
    reg = Regional(nombre="TS R2 Resolver3")
    db.add(reg); db.flush()
    emp = Empleado(cedula="4444444445", nombre="EMP RESOLVER3", regional_id=reg.id)
    db.add(emp); db.flush()

    assert resolver_dia_efectivo(db, emp.id, date(2026, 7, 6)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convocatoria_service.py -k resolver_dia_efectivo -v`
Expected: FAIL — `ImportError: cannot import name 'resolver_dia_efectivo'`

- [ ] **Step 3: Implement**

Append to `app/services/convocatoria.py`:

```python
from sqlalchemy.orm import Session
from app.models.dia_cambio import DiaCambio
from app.models.variable_adicional import VariableAdicional


def resolver_dia_efectivo(db: Session, empleado_id: int, semana_inicio: date) -> str | None:
    excepcion = (
        db.query(DiaCambio)
        .filter(
            DiaCambio.empleado_id == empleado_id,
            DiaCambio.tipo == "SEMANAL",
            DiaCambio.semana_inicio == semana_inicio,
        )
        .order_by(DiaCambio.fecha_creacion.desc())
        .first()
    )
    if excepcion:
        return excepcion.dia_nuevo
    va = db.query(VariableAdicional).filter_by(empleado_id=empleado_id).first()
    return va.dia if va else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_convocatoria_service.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/convocatoria.py tests/test_convocatoria_service.py
git commit -m "feat: resolucion de dia efectivo (excepcion semanal o dia base)"
```

---

### Task 5: Tabla `envios_convocatoria` (modelo + migración)

**Files:**
- Create: `app/models/envio_convocatoria.py`
- Modify: `app/models/__init__.py`
- Create: alembic migration
- Test: `tests/test_convocatoria_service.py` (append)

- [ ] **Step 1: Write the failing test**

```python
from app.models.envio_convocatoria import EnvioConvocatoria


def test_envio_convocatoria_registra_empleado_curso_y_modo_prueba(db):
    reg = Regional(nombre="TS R2 Envio")
    db.add(reg); db.flush()
    emp = Empleado(cedula="5555555555", nombre="EMP ENVIO", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo="ENV01", nombre="CURSO ENVIO", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()

    envio = EnvioConvocatoria(empleado_id=emp.id, curso_id=curso.id, modo_prueba=True)
    db.add(envio); db.flush()

    guardado = db.query(EnvioConvocatoria).filter_by(empleado_id=emp.id).first()
    assert guardado.curso_id == curso.id
    assert guardado.modo_prueba is True
    assert guardado.fecha_envio is not None
```

(Add `from app.models import Curso` to the test file's imports if not already present.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convocatoria_service.py::test_envio_convocatoria_registra_empleado_curso_y_modo_prueba -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.envio_convocatoria'`

- [ ] **Step 3: Create the model**

```python
# app/models/envio_convocatoria.py
from sqlalchemy import Column, Integer, Boolean, DateTime, String, ForeignKey, func
from sqlalchemy.orm import relationship
from app.database import Base


class EnvioConvocatoria(Base):
    __tablename__ = "envios_convocatoria"

    id = Column(Integer, primary_key=True, index=True)
    empleado_id = Column(Integer, ForeignKey("empleados.id"), nullable=False)
    curso_id = Column(Integer, ForeignKey("cursos.id"), nullable=False)
    fecha_envio = Column(DateTime, server_default=func.now(), nullable=False)
    enviado_por = Column(String(150), nullable=True)
    modo_prueba = Column(Boolean, nullable=False, default=False, server_default="false")

    empleado = relationship("Empleado")
    curso = relationship("Curso")
```

- [ ] **Step 4: Wire into `__init__.py`**

```python
from app.models.envio_convocatoria import EnvioConvocatoria
```

add `"EnvioConvocatoria"` to `__all__`.

- [ ] **Step 5: Generate and fill in the migration**

Run: `python -m alembic revision -m "add_envios_convocatoria"`

Edit (`down_revision` = Task 3's migration hash):

```python
def upgrade() -> None:
    op.create_table(
        'envios_convocatoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('empleado_id', sa.Integer(), nullable=False),
        sa.Column('curso_id', sa.Integer(), nullable=False),
        sa.Column('fecha_envio', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('enviado_por', sa.String(length=150), nullable=True),
        sa.Column('modo_prueba', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['empleado_id'], ['empleados.id']),
        sa.ForeignKeyConstraint(['curso_id'], ['cursos.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_envios_convocatoria_id'), 'envios_convocatoria', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_envios_convocatoria_id'), table_name='envios_convocatoria')
    op.drop_table('envios_convocatoria')
```

Run: `python -m alembic upgrade head`

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_convocatoria_service.py -v`
Expected: 10 passed

- [ ] **Step 7: Commit**

```bash
git add app/models/envio_convocatoria.py app/models/__init__.py \
        alembic/versions/*_add_envios_convocatoria.py tests/test_convocatoria_service.py
git commit -m "feat: tabla envios_convocatoria (historial de correos enviados)"
```

---

### Task 6: Configuración SMTP en `app/config.py`

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_convocatoria_service.py` (append)

- [ ] **Step 1: Write the failing test**

```python
from app.config import settings


def test_settings_expone_configuracion_smtp():
    assert settings.smtp_host == "smtp.telconet.ec"
    assert settings.smtp_port == 465
    assert settings.smtp_use_ssl is True
    assert settings.smtp_timeout == 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_convocatoria_service.py::test_settings_expone_configuracion_smtp -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'smtp_host'`

- [ ] **Step 3: Implement**

Edit `app/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    admin_token: str
    test_database_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "Capacitaciones TelcoU"
    smtp_use_ssl: bool = True
    smtp_timeout: int = 60

    model_config = {"env_file": ".env"}


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_convocatoria_service.py -v`
Expected: 11 passed (reads real values from `.env`, already populated per the design's Section 4)

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_convocatoria_service.py
git commit -m "feat: exponer configuracion SMTP en Settings"
```

---

### Task 7: `app/services/mailer.py` — plantilla y envío SMTP

**Files:**
- Create: `app/services/mailer.py`
- Test: `tests/test_mailer.py`

**Interfaces:**
- Consumes: `settings` (Task 6)
- Produces: `construir_cuerpo_html(nombre: str, cursos: list[dict]) -> str`, `enviar_correo(destinatario: str, asunto: str, cuerpo_html: str) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_mailer.py
from unittest.mock import patch, MagicMock
from app.services.mailer import construir_cuerpo_html, enviar_correo


def test_construir_cuerpo_html_incluye_nombre_curso_nota_y_link():
    html = construir_cuerpo_html(
        "JUAN PEREZ",
        [{"curso": "FIBRA OPTICA", "nota": 5.0, "url": "http://moodle.telconet.ec/x"}],
    )
    assert "JUAN PEREZ" in html
    assert "FIBRA OPTICA" in html
    assert "5.0" in html
    assert "http://moodle.telconet.ec/x" in html


def test_construir_cuerpo_html_con_multiples_cursos():
    html = construir_cuerpo_html(
        "ANA GOMEZ",
        [
            {"curso": "CURSO A", "nota": 4.0, "url": "http://x/a"},
            {"curso": "CURSO B", "nota": None, "url": "http://x/b"},
        ],
    )
    assert "CURSO A" in html
    assert "CURSO B" in html


@patch("app.services.mailer.smtplib.SMTP_SSL")
def test_enviar_correo_hace_login_y_sendmail(mock_smtp_ssl):
    mock_server = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = mock_server

    enviar_correo("destino@telconet.ec", "Asunto Test", "<p>cuerpo</p>")

    mock_smtp_ssl.assert_called_once()
    mock_server.login.assert_called_once()
    mock_server.sendmail.assert_called_once()
    args = mock_server.sendmail.call_args[0]
    assert args[1] == ["destino@telconet.ec"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mailer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.mailer'`

- [ ] **Step 3: Implement**

```python
# app/services/mailer.py
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings


def construir_cuerpo_html(nombre: str, cursos: list[dict]) -> str:
    filas = "".join(
        f"<tr><td>{c['curso']}</td>"
        f"<td>{c['nota'] if c['nota'] is not None else '—'}</td>"
        f"<td><a href=\"{c['url'] or '#'}\">{c['url'] or 'sin link'}</a></td></tr>"
        for c in cursos
    )
    return f"""
    <html><body>
    <p>Estimado/a <strong>{nombre}</strong>,</p>
    <p>Tiene pendiente rendir supletorio en las siguientes capacitaciones:</p>
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Capacitación</th><th>Nota</th><th>Link</th></tr>
      {filas}
    </table>
    <p>{settings.smtp_from_name}</p>
    </body></html>
    """


def enviar_correo(destinatario: str, asunto: str, cuerpo_html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from}>"
    msg["To"] = destinatario
    msg.attach(MIMEText(cuerpo_html, "html"))

    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout) as server:
        server.login(settings.smtp_user, settings.smtp_password)
        server.sendmail(settings.smtp_from, [destinatario], msg.as_string())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_mailer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/mailer.py tests/test_mailer.py
git commit -m "feat: servicio de envio de correo (plantilla HTML + smtplib.SMTP_SSL)"
```

---

### Task 8: Extraer `supletorios_pendientes_data()` — refactor sin cambiar comportamiento

**Files:**
- Modify: `app/services/convocatoria.py`
- Modify: `app/routers/analitica.py`
- Test: `tests/test_analitica.py` (append characterization test first)

**Interfaces:**
- Produces: `supletorios_pendientes_data(db, anio, regional=None, curso=None, sucursal=None, nombre=None) -> list[dict]` — one dict per (empleado, curso pendiente) with keys `empleado_id, curso_id, cedula, nombre, regional, sucursal, area, curso, curso_url, mes, anio, ultimo_intento, ultima_nota, ultimo_estado`

- [ ] **Step 1: Write a characterization test for the CURRENT endpoint (before touching it)**

Append to `tests/test_analitica.py`:

```python
def test_supletorios_pendientes_reprobado_sin_intento_aparece_como_intento_0(client, db):
    reg = Regional(nombre="TS R2 SupPend")
    db.add(reg); db.flush()
    emp = Empleado(cedula="6060606060", nombre="EMP SUPPEND", regional_id=reg.id, area="OPU")
    db.add(emp); db.flush()
    curso = Curso(codigo="SP01", nombre="CURSO SUPPEND", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, valor=Decimal("4.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.flush()

    r = client.get("/analitica/supletorios-pendientes?anio=2026&regional=TS R2 SupPend")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["cedula"] == "6060606060"
    assert data[0]["ultimo_intento"] == 0
    assert data[0]["ultimo_estado"] == "REPROBADO"
```

- [ ] **Step 2: Run it against the CURRENT (unrefactored) code to confirm it passes**

Run: `python -m pytest tests/test_analitica.py::test_supletorios_pendientes_reprobado_sin_intento_aparece_como_intento_0 -v`
Expected: PASS (this locks in current behavior before refactoring)

- [ ] **Step 3: Move the query logic into the service, add `curso_url` and `nombre` filter**

Append to `app/services/convocatoria.py`:

```python
from collections import defaultdict
from sqlalchemy.orm import Session
from app.models.curso import Curso
from app.models.nota import Nota
from app.models.empleado import Empleado
from app.models.regional import Regional

NECESITA_SUPLETORIO = {"REPROBADO", "FALTA_INJUSTIFICADA"}


def supletorios_pendientes_data(
    db: Session,
    anio: int,
    regional: str | None = None,
    curso: str | None = None,
    sucursal: str | None = None,
    nombre: str | None = None,
) -> list[dict]:
    q_reg = (
        db.query(Nota, Curso, Empleado, Regional)
        .join(Curso, Nota.curso_id == Curso.id)
        .join(Empleado, Nota.empleado_id == Empleado.id)
        .join(Regional, Empleado.regional_id == Regional.id)
        .filter(Nota.tipo == "REGULAR", Curso.anio == anio, Empleado.inactivo.is_(False))
    )
    q_sup = (
        db.query(Nota, Empleado)
        .join(Empleado, Nota.empleado_id == Empleado.id)
        .filter(Nota.tipo == "SUPLETORIO", Empleado.inactivo.is_(False))
    )
    if regional:
        q_reg = q_reg.filter(Regional.nombre.ilike(f"%{regional}%"))
    if curso:
        q_reg = q_reg.filter(Curso.nombre.ilike(f"%{curso}%"))
    if sucursal:
        q_reg = q_reg.filter(Empleado.sucursal.ilike(f"%{sucursal}%"))
    if nombre:
        q_reg = q_reg.filter(Empleado.nombre.ilike(f"%{nombre}%"))

    sup_por_original: dict[int, list[Nota]] = defaultdict(list)
    for n, _ in q_sup.all():
        if n.nota_original_id:
            sup_por_original[n.nota_original_id].append(n)

    result: list[dict] = []
    for n, c, e, r in q_reg.all():
        if n.estado not in NECESITA_SUPLETORIO:
            continue

        base = {
            "empleado_id": e.id, "curso_id": c.id,
            "cedula": e.cedula, "nombre": e.nombre, "regional": r.nombre,
            "sucursal": e.sucursal, "area": e.area,
            "curso": c.nombre, "curso_url": c.url_telcou, "mes": c.mes, "anio": c.anio,
        }

        intentos = sup_por_original.get(n.id)
        if not intentos:
            result.append({
                **base, "ultimo_intento": 0,
                "ultima_nota": float(n.valor) if n.valor is not None else None,
                "ultimo_estado": n.estado,
            })
            continue

        ultima = max(intentos, key=lambda x: x.convocatoria)
        if ultima.estado == "REPROBADO":
            result.append({
                **base, "ultimo_intento": ultima.convocatoria,
                "ultima_nota": float(ultima.valor) if ultima.valor is not None else None,
                "ultimo_estado": ultima.estado,
            })

    return sorted(result, key=lambda x: (x["regional"], x["curso"], x["nombre"]))
```

- [ ] **Step 4: Point the existing endpoint at the service function**

In `app/routers/analitica.py`: remove the module-level `NECESITA_SUPLETORIO` constant (now lives in the service) and replace the body of `supletorios_pendientes()`:

```python
from app.services.convocatoria import supletorios_pendientes_data

# ... (remove: NECESITA_SUPLETORIO = {"REPROBADO", "FALTA_INJUSTIFICADA"})

@router.get("/supletorios-pendientes", response_model=list[SupletorioPendienteOut])
def supletorios_pendientes(
    anio: int = Query(...),
    regional: str | None = Query(None, description="Filtrar por regional (ej: 'TS R2', 'Quito')"),
    curso: str | None = Query(None, description="Filtrar por nombre de capacitación (búsqueda parcial)"),
    sucursal: str | None = Query(None, description="Filtrar por sucursal"),
    db: Session = Depends(get_db),
):
    """
    Empleados activos que necesitan rendir un supletorio (o un siguiente intento)
    y todavía no lo tienen registrado.
    """
    data = supletorios_pendientes_data(db, anio, regional=regional, curso=curso, sucursal=sucursal)
    return [
        SupletorioPendienteOut(
            cedula=d["cedula"], nombre=d["nombre"], regional=d["regional"],
            sucursal=d["sucursal"], area=d["area"], curso=d["curso"],
            mes=d["mes"], anio=d["anio"], ultimo_intento=d["ultimo_intento"],
            ultima_nota=d["ultima_nota"], ultimo_estado=d["ultimo_estado"],
        )
        for d in data
    ]
```

(`_stats_supletorios`/`_stats`/`listado_cursos` are untouched — they don't use `NECESITA_SUPLETORIO`.)

- [ ] **Step 5: Run the characterization test again to confirm the refactor didn't change behavior**

Run: `python -m pytest tests/test_analitica.py::test_supletorios_pendientes_reprobado_sin_intento_aparece_como_intento_0 -v`
Expected: PASS (same assertions, now via the refactored path)

Run the full suite to check nothing else broke: `python -m pytest -v`
Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add app/services/convocatoria.py app/routers/analitica.py tests/test_analitica.py
git commit -m "refactor: extraer supletorios_pendientes_data a servicio compartido"
```

---

## Fase B — Schemas y endpoints

### Task 9: `app/schemas/convocatoria.py`

**Files:**
- Create: `app/schemas/convocatoria.py`

**Interfaces:**
- Produces: `CambiarDiaIn`, `DiaCambioOut`, `CursoPendienteOut`, `ConvocatoriaPreviewOut`, `EnviarConvocatoriaIn`, `EnvioResultado`, `EnviarConvocatoriaOut`

No test for this task — it's pure Pydantic model declarations, exercised indirectly by every endpoint test in Tasks 10–13.

- [ ] **Step 1: Create the file**

```python
# app/schemas/convocatoria.py
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict


class CambiarDiaIn(BaseModel):
    dia_nuevo: str
    tipo: str  # PERMANENTE | SEMANAL
    semana_inicio: date | None = None
    motivo: str
    editado_por: str | None = None


class DiaCambioOut(BaseModel):
    id: int
    dia_nuevo: str
    tipo: str
    semana_inicio: date | None
    motivo: str
    editado_por: str | None
    fecha_creacion: datetime
    model_config = ConfigDict(from_attributes=True)


class CursoPendienteOut(BaseModel):
    curso_id: int
    curso: str
    nota: float | None
    url: str | None


class ConvocatoriaPreviewOut(BaseModel):
    cedula: str
    nombre: str
    regional: str
    tiene_correo: bool
    ya_enviado: bool
    cursos_pendientes: list[CursoPendienteOut]


class EnviarConvocatoriaIn(BaseModel):
    cedulas: list[str]
    semana: date
    modo_prueba: bool = True
    correo_prueba: str | None = None


class EnvioResultado(BaseModel):
    cedula: str
    nombre: str
    detalle: str | None = None


class EnviarConvocatoriaOut(BaseModel):
    enviados: list[EnvioResultado]
    fallidos: list[EnvioResultado]
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && python -c "from app.schemas.convocatoria import CambiarDiaIn, DiaCambioOut, ConvocatoriaPreviewOut, EnviarConvocatoriaIn, EnviarConvocatoriaOut; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas/convocatoria.py
git commit -m "feat: schemas Pydantic para cambio de dia y envio de convocatoria"
```

---

### Task 10: `PATCH /empleados/{cedula}/dia` + `GET /empleados/{cedula}/dia-historial`

**Files:**
- Modify: `app/routers/empleados.py`
- Create: `tests/test_convocatoria_endpoints.py`

**Interfaces:**
- Consumes: `DIAS_VALIDOS`, `lunes_de_semana` (Task 1), `DiaCambio` (Task 3), `CambiarDiaIn`/`DiaCambioOut` (Task 9), `verify_admin` (existing, `app/routers/admin.py`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_convocatoria_endpoints.py
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.config import settings
from app.models import Regional, Empleado
from app.models.variable_adicional import VariableAdicional


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empleado_ts_r2(db):
    reg = Regional(nombre="TS R2 ConvEndpoint")
    db.add(reg); db.flush()
    emp = Empleado(cedula="7070707070", nombre="CONV EMPLEADO", regional_id=reg.id, area="SOPORTE")
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, dia="LUNES", correo="conv@telconet.ec"))
    db.flush()
    return {"regional": reg, "empleado": emp}


def test_cambiar_dia_sin_token_retorna_401(client, empleado_ts_r2):
    r = client.patch(
        "/empleados/7070707070/dia",
        json={"dia_nuevo": "MARTES", "tipo": "PERMANENTE", "motivo": "prueba"},
    )
    assert r.status_code == 401


def test_cambiar_dia_permanente_actualiza_dia_base(client, db, empleado_ts_r2):
    r = client.patch(
        "/empleados/7070707070/dia",
        headers={"X-Admin-Token": settings.admin_token},
        json={"dia_nuevo": "MARTES", "tipo": "PERMANENTE", "motivo": "cambio de turno"},
    )
    assert r.status_code == 200
    assert r.json()["dia_nuevo"] == "MARTES"

    va = db.query(VariableAdicional).filter_by(empleado_id=empleado_ts_r2["empleado"].id).first()
    assert va.dia == "MARTES"


def test_cambiar_dia_semanal_no_toca_dia_base(client, db, empleado_ts_r2):
    r = client.patch(
        "/empleados/7070707070/dia",
        headers={"X-Admin-Token": settings.admin_token},
        json={"dia_nuevo": "JUEVES", "tipo": "SEMANAL",
              "semana_inicio": "2026-07-06", "motivo": "no pudo asistir el lunes"},
    )
    assert r.status_code == 200
    assert r.json()["semana_inicio"] == "2026-07-06"

    va = db.query(VariableAdicional).filter_by(empleado_id=empleado_ts_r2["empleado"].id).first()
    assert va.dia == "LUNES"


def test_cambiar_dia_semanal_sin_semana_inicio_retorna_400(client, empleado_ts_r2):
    r = client.patch(
        "/empleados/7070707070/dia",
        headers={"X-Admin-Token": settings.admin_token},
        json={"dia_nuevo": "JUEVES", "tipo": "SEMANAL", "motivo": "sin semana"},
    )
    assert r.status_code == 400


def test_cambiar_dia_invalido_retorna_400(client, empleado_ts_r2):
    r = client.patch(
        "/empleados/7070707070/dia",
        headers={"X-Admin-Token": settings.admin_token},
        json={"dia_nuevo": "SABADO", "tipo": "PERMANENTE", "motivo": "dia invalido"},
    )
    assert r.status_code == 400


def test_dia_historial_lista_cambios_mas_recientes_primero(client, empleado_ts_r2):
    client.patch(
        "/empleados/7070707070/dia",
        headers={"X-Admin-Token": settings.admin_token},
        json={"dia_nuevo": "MARTES", "tipo": "PERMANENTE", "motivo": "cambio 1"},
    )
    client.patch(
        "/empleados/7070707070/dia",
        headers={"X-Admin-Token": settings.admin_token},
        json={"dia_nuevo": "MIERCOLES", "tipo": "PERMANENTE", "motivo": "cambio 2"},
    )
    r = client.get("/empleados/7070707070/dia-historial")
    assert r.status_code == 200
    motivos = [h["motivo"] for h in r.json()]
    assert motivos == ["cambio 2", "cambio 1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_convocatoria_endpoints.py -v`
Expected: FAIL — `404 Not Found` (routes don't exist yet)

- [ ] **Step 3: Implement**

Edit `app/routers/empleados.py`, add imports and two new routes:

```python
from app.models.dia_cambio import DiaCambio
from app.models.variable_adicional import VariableAdicional
from app.schemas.convocatoria import CambiarDiaIn, DiaCambioOut
from app.services.convocatoria import DIAS_VALIDOS, lunes_de_semana
from app.routers.admin import verify_admin
```

Add at the end of the file:

```python
@router.patch("/{cedula}/dia", response_model=DiaCambioOut)
def cambiar_dia_empleado(
    cedula: str,
    body: CambiarDiaIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    emp = _get_empleado_or_404(cedula, db)

    dia_nuevo = body.dia_nuevo.strip().upper()
    if dia_nuevo not in DIAS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail="dia_nuevo debe ser LUNES, MARTES, MIERCOLES, JUEVES o VIERNES",
        )
    if body.tipo not in {"PERMANENTE", "SEMANAL"}:
        raise HTTPException(status_code=400, detail="tipo debe ser PERMANENTE o SEMANAL")
    if body.tipo == "SEMANAL" and body.semana_inicio is None:
        raise HTTPException(status_code=400, detail="semana_inicio es requerido cuando tipo=SEMANAL")

    cambio = DiaCambio(
        empleado_id=emp.id,
        dia_nuevo=dia_nuevo,
        tipo=body.tipo,
        semana_inicio=lunes_de_semana(body.semana_inicio) if body.tipo == "SEMANAL" else None,
        motivo=body.motivo,
        editado_por=body.editado_por,
    )
    db.add(cambio)

    if body.tipo == "PERMANENTE":
        va = db.query(VariableAdicional).filter_by(empleado_id=emp.id).first()
        if va is None:
            va = VariableAdicional(empleado_id=emp.id)
            db.add(va)
        va.dia = dia_nuevo

    db.commit()
    db.refresh(cambio)
    return cambio


@router.get("/{cedula}/dia-historial", response_model=list[DiaCambioOut])
def dia_historial_empleado(cedula: str, db: Session = Depends(get_db)):
    emp = _get_empleado_or_404(cedula, db)
    return (
        db.query(DiaCambio)
        .filter(DiaCambio.empleado_id == emp.id)
        .order_by(DiaCambio.fecha_creacion.desc())
        .all()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_convocatoria_endpoints.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/empleados.py tests/test_convocatoria_endpoints.py
git commit -m "feat: PATCH /empleados/{cedula}/dia y GET dia-historial con trazabilidad"
```

---

### Task 11: `GET /analitica/supletorios-pendientes/buscar`

**Files:**
- Modify: `app/routers/analitica.py`
- Modify: `tests/test_analitica.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analitica.py`:

```python
def test_supletorios_pendientes_buscar_filtra_por_nombre(client, db):
    reg = Regional(nombre="TS R2 Buscar")
    db.add(reg); db.flush()
    emp1 = Empleado(cedula="8080808080", nombre="PEREZ JUAN", regional_id=reg.id)
    emp2 = Empleado(cedula="8080808081", nombre="GOMEZ ANA", regional_id=reg.id)
    db.add_all([emp1, emp2]); db.flush()
    curso = Curso(codigo="BUS01", nombre="CURSO BUSCAR", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp1.id, curso_id=curso.id, valor=Decimal("3.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.add(Nota(empleado_id=emp2.id, curso_id=curso.id, valor=Decimal("2.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.flush()

    r = client.get("/analitica/supletorios-pendientes/buscar?nombre=PEREZ&anio=2026")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["cedula"] == "8080808080"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analitica.py::test_supletorios_pendientes_buscar_filtra_por_nombre -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement**

In `app/routers/analitica.py`, add above the existing `/supletorios-pendientes` route (more specific path first):

```python
@router.get("/supletorios-pendientes/buscar", response_model=list[SupletorioPendienteOut])
def supletorios_pendientes_buscar(
    nombre: str = Query(..., min_length=2),
    regional: str | None = Query(None),
    anio: int = Query(...),
    db: Session = Depends(get_db),
):
    """Búsqueda por nombre dentro del universo de pendientes, sin filtrar por día — usada
    por el buscador 'Agregar por nombre' de la ventana de Convocatoria."""
    data = supletorios_pendientes_data(db, anio, regional=regional, nombre=nombre)
    return [
        SupletorioPendienteOut(
            cedula=d["cedula"], nombre=d["nombre"], regional=d["regional"],
            sucursal=d["sucursal"], area=d["area"], curso=d["curso"],
            mes=d["mes"], anio=d["anio"], ultimo_intento=d["ultimo_intento"],
            ultima_nota=d["ultima_nota"], ultimo_estado=d["ultimo_estado"],
        )
        for d in data
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analitica.py -v`
Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add app/routers/analitica.py tests/test_analitica.py
git commit -m "feat: GET /analitica/supletorios-pendientes/buscar por nombre"
```

---

### Task 12: `GET /analitica/convocatoria-preview`

**Files:**
- Modify: `app/routers/analitica.py`
- Modify: `tests/test_convocatoria_endpoints.py`

**Interfaces:**
- Consumes: `supletorios_pendientes_data`, `resolver_dia_efectivo`, `lunes_de_semana`, `DIAS_VALIDOS` (all from `app/services/convocatoria.py`), `EnvioConvocatoria` (Task 5), `ConvocatoriaPreviewOut`/`CursoPendienteOut` (Task 9)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_convocatoria_endpoints.py`:

```python
from decimal import Decimal
from datetime import date
from app.models import Curso, Nota
from app.models.dia_cambio import DiaCambio
from app.models.envio_convocatoria import EnvioConvocatoria


def test_convocatoria_preview_incluye_empleado_con_dia_base_coincidente(client, db):
    reg = Regional(nombre="TS R2 Preview1")
    db.add(reg); db.flush()
    emp = Empleado(cedula="9090909090", nombre="PREVIEW UNO", regional_id=reg.id, area="OPU")
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, dia="LUNES", correo="preview1@telconet.ec"))
    curso = Curso(codigo="PRE01", nombre="CURSO PREVIEW", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, url_telcou="http://moodle/pre01")
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, valor=Decimal("3.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.flush()

    r = client.get(
        "/analitica/convocatoria-preview",
        params={"dia": "LUNES", "regional": "TS R2 Preview1", "semana": "2026-07-06"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["cedula"] == "9090909090"
    assert data[0]["tiene_correo"] is True
    assert data[0]["ya_enviado"] is False
    assert data[0]["cursos_pendientes"][0]["curso"] == "CURSO PREVIEW"
    assert data[0]["cursos_pendientes"][0]["url"] == "http://moodle/pre01"


def test_convocatoria_preview_respeta_excepcion_semanal(client, db):
    reg = Regional(nombre="TS R2 Preview2")
    db.add(reg); db.flush()
    emp = Empleado(cedula="9191919191", nombre="PREVIEW DOS", regional_id=reg.id)
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, dia="LUNES", correo="preview2@telconet.ec"))
    curso = Curso(codigo="PRE02", nombre="CURSO PREVIEW 2", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, valor=Decimal("3.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.add(DiaCambio(empleado_id=emp.id, dia_nuevo="JUEVES", tipo="SEMANAL",
                      semana_inicio=date(2026, 7, 6), motivo="excepcion"))
    db.flush()

    r_lunes = client.get(
        "/analitica/convocatoria-preview",
        params={"dia": "LUNES", "regional": "TS R2 Preview2", "semana": "2026-07-06"},
    )
    assert r_lunes.json() == []

    r_jueves = client.get(
        "/analitica/convocatoria-preview",
        params={"dia": "JUEVES", "regional": "TS R2 Preview2", "semana": "2026-07-06"},
    )
    assert len(r_jueves.json()) == 1


def test_convocatoria_preview_marca_ya_enviado(client, db):
    reg = Regional(nombre="TS R2 Preview3")
    db.add(reg); db.flush()
    emp = Empleado(cedula="9292929292", nombre="PREVIEW TRES", regional_id=reg.id)
    db.add(emp); db.flush()
    db.add(VariableAdicional(empleado_id=emp.id, dia="MARTES", correo="preview3@telconet.ec"))
    curso = Curso(codigo="PRE03", nombre="CURSO PREVIEW 3", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, valor=Decimal("3.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.flush()
    db.add(EnvioConvocatoria(empleado_id=emp.id, curso_id=curso.id, modo_prueba=False))
    db.flush()

    r = client.get(
        "/analitica/convocatoria-preview",
        params={"dia": "MARTES", "regional": "TS R2 Preview3", "semana": "2026-07-06"},
    )
    assert r.json()[0]["ya_enviado"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_convocatoria_endpoints.py -k preview -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement**

In `app/routers/analitica.py`, add imports:

```python
from datetime import date
from app.models.envio_convocatoria import EnvioConvocatoria
from app.models.variable_adicional import VariableAdicional
from app.schemas.convocatoria import ConvocatoriaPreviewOut, CursoPendienteOut
from app.services.convocatoria import DIAS_VALIDOS, lunes_de_semana, resolver_dia_efectivo
```

Add the endpoint:

```python
@router.get("/convocatoria-preview", response_model=list[ConvocatoriaPreviewOut])
def convocatoria_preview(
    dia: str = Query(...),
    regional: str = Query(...),
    semana: date = Query(...),
    anio: int | None = Query(None, description="Default: el año de 'semana'"),
    db: Session = Depends(get_db),
):
    dia_norm = dia.strip().upper()
    if dia_norm not in DIAS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail="dia debe ser LUNES, MARTES, MIERCOLES, JUEVES o VIERNES",
        )

    anio_efectivo = anio or semana.year
    semana_inicio = lunes_de_semana(semana)

    data = supletorios_pendientes_data(db, anio_efectivo, regional=regional)

    por_empleado: dict[int, dict] = {}
    for d in data:
        info = por_empleado.setdefault(d["empleado_id"], {
            "empleado_id": d["empleado_id"], "cedula": d["cedula"], "nombre": d["nombre"],
            "regional": d["regional"], "cursos": [],
        })
        info["cursos"].append(d)

    ids_enviados = {
        (env.empleado_id, env.curso_id)
        for env in db.query(EnvioConvocatoria).filter(EnvioConvocatoria.modo_prueba.is_(False)).all()
    }

    result: list[ConvocatoriaPreviewOut] = []
    for emp_id, info in por_empleado.items():
        if resolver_dia_efectivo(db, emp_id, semana_inicio) != dia_norm:
            continue
        va = db.query(VariableAdicional).filter_by(empleado_id=emp_id).first()
        result.append(ConvocatoriaPreviewOut(
            cedula=info["cedula"], nombre=info["nombre"], regional=info["regional"],
            tiene_correo=bool(va and va.correo),
            ya_enviado=any((emp_id, c["curso_id"]) in ids_enviados for c in info["cursos"]),
            cursos_pendientes=[
                CursoPendienteOut(curso_id=c["curso_id"], curso=c["curso"], nota=c["ultima_nota"], url=c["curso_url"])
                for c in info["cursos"]
            ],
        ))
    return sorted(result, key=lambda x: x.nombre)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_convocatoria_endpoints.py -v`
Expected: all passing

- [ ] **Step 5: Commit**

```bash
git add app/routers/analitica.py tests/test_convocatoria_endpoints.py
git commit -m "feat: GET /analitica/convocatoria-preview (dia efectivo + correo + ya-enviado)"
```

---

### Task 13: `POST /admin/enviar-convocatoria`

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `tests/test_convocatoria_endpoints.py`

**Interfaces:**
- Consumes: `enviar_correo`, `construir_cuerpo_html` (Task 7), `supletorios_pendientes_data`, `lunes_de_semana` (services), `EnviarConvocatoriaIn`/`EnviarConvocatoriaOut`/`EnvioResultado` (Task 9)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_convocatoria_endpoints.py`:

```python
from unittest.mock import patch


def _crear_empleado_con_pendiente(db, cedula, correo, nombre="ENVIO TEST"):
    reg = Regional(nombre=f"TS R2 Envio {cedula}")
    db.add(reg); db.flush()
    emp = Empleado(cedula=cedula, nombre=nombre, regional_id=reg.id)
    db.add(emp); db.flush()
    if correo:
        db.add(VariableAdicional(empleado_id=emp.id, dia="LUNES", correo=correo))
    curso = Curso(codigo=f"ENV-{cedula}", nombre="CURSO ENVIO TEST", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id, url_telcou="http://moodle/env")
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, valor=Decimal("3.0"),
                estado="REPROBADO", tipo="REGULAR"))
    db.flush()
    return emp


def test_enviar_convocatoria_sin_token_retorna_401(client):
    r = client.post("/admin/enviar-convocatoria", json={"cedulas": [], "semana": "2026-07-06"})
    assert r.status_code == 401


def test_enviar_convocatoria_modo_prueba_sin_correo_prueba_retorna_400(client):
    r = client.post(
        "/admin/enviar-convocatoria",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [], "semana": "2026-07-06", "modo_prueba": True},
    )
    assert r.status_code == 400


@patch("app.services.mailer.smtplib.SMTP_SSL")
def test_enviar_convocatoria_modo_prueba_redirige_a_correo_prueba(mock_smtp_ssl, client, db):
    from unittest.mock import MagicMock
    mock_server = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = mock_server

    emp = _crear_empleado_con_pendiente(db, "1010101010", "real@telconet.ec")

    r = client.post(
        "/admin/enviar-convocatoria",
        headers={"X-Admin-Token": settings.admin_token},
        json={
            "cedulas": [emp.cedula], "semana": "2026-07-06",
            "modo_prueba": True, "correo_prueba": "prueba@telconet.ec",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["enviados"]) == 1
    assert body["fallidos"] == []

    sendmail_args = mock_server.sendmail.call_args[0]
    assert sendmail_args[1] == ["prueba@telconet.ec"]

    envio = db.query(EnvioConvocatoria).filter_by(empleado_id=emp.id).first()
    assert envio.modo_prueba is True


@patch("app.services.mailer.smtplib.SMTP_SSL")
def test_enviar_convocatoria_sin_correo_va_a_fallidos(mock_smtp_ssl, client, db):
    emp = _crear_empleado_con_pendiente(db, "1111111112", correo=None)

    r = client.post(
        "/admin/enviar-convocatoria",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [emp.cedula], "semana": "2026-07-06", "modo_prueba": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enviados"] == []
    assert len(body["fallidos"]) == 1
    assert "correo" in body["fallidos"][0]["detalle"].lower()
    mock_smtp_ssl.assert_not_called()


@patch("app.services.mailer.smtplib.SMTP_SSL")
def test_enviar_convocatoria_real_no_modo_prueba_va_al_correo_del_empleado(mock_smtp_ssl, client, db):
    from unittest.mock import MagicMock
    mock_server = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = mock_server

    emp = _crear_empleado_con_pendiente(db, "1212121212", "real2@telconet.ec")

    r = client.post(
        "/admin/enviar-convocatoria",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [emp.cedula], "semana": "2026-07-06", "modo_prueba": False},
    )
    assert r.status_code == 200
    assert len(r.json()["enviados"]) == 1

    sendmail_args = mock_server.sendmail.call_args[0]
    assert sendmail_args[1] == ["real2@telconet.ec"]

    envio = db.query(EnvioConvocatoria).filter_by(empleado_id=emp.id).first()
    assert envio.modo_prueba is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_convocatoria_endpoints.py -k enviar_convocatoria -v`
Expected: FAIL — 404

- [ ] **Step 3: Implement**

Edit `app/routers/admin.py`, add imports:

```python
from app.models import Empleado
from app.models.variable_adicional import VariableAdicional
from app.models.envio_convocatoria import EnvioConvocatoria
from app.schemas.convocatoria import EnviarConvocatoriaIn, EnviarConvocatoriaOut, EnvioResultado
from app.services.convocatoria import supletorios_pendientes_data, lunes_de_semana
from app.services.mailer import construir_cuerpo_html, enviar_correo
```

Add the endpoint at the end of the file:

```python
@router.post("/enviar-convocatoria", response_model=EnviarConvocatoriaOut)
def enviar_convocatoria(
    body: EnviarConvocatoriaIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if body.modo_prueba and not body.correo_prueba:
        raise HTTPException(status_code=400, detail="correo_prueba es requerido en modo_prueba")

    semana_inicio = lunes_de_semana(body.semana)
    enviados: list[EnvioResultado] = []
    fallidos: list[EnvioResultado] = []

    for cedula in body.cedulas:
        emp = db.query(Empleado).filter(Empleado.cedula == cedula).first()
        if not emp:
            fallidos.append(EnvioResultado(cedula=cedula, nombre="", detalle="Empleado no encontrado"))
            continue

        va = db.query(VariableAdicional).filter_by(empleado_id=emp.id).first()
        if not va or not va.correo:
            fallidos.append(EnvioResultado(cedula=cedula, nombre=emp.nombre, detalle="Sin correo registrado"))
            continue

        data = supletorios_pendientes_data(db, semana_inicio.year)
        cursos_emp = [d for d in data if d["empleado_id"] == emp.id]
        if not cursos_emp:
            fallidos.append(EnvioResultado(cedula=cedula, nombre=emp.nombre, detalle="Sin supletorios pendientes"))
            continue

        destino = body.correo_prueba if body.modo_prueba else va.correo
        asunto = f"Convocatoria a supletorio{' [PRUEBA]' if body.modo_prueba else ''}"
        cuerpo = construir_cuerpo_html(emp.nombre, [
            {"curso": c["curso"], "nota": c["ultima_nota"], "url": c["curso_url"]} for c in cursos_emp
        ])

        try:
            enviar_correo(destino, asunto, cuerpo)
        except Exception as exc:
            fallidos.append(EnvioResultado(cedula=cedula, nombre=emp.nombre, detalle=str(exc)))
            continue

        for c in cursos_emp:
            db.add(EnvioConvocatoria(
                empleado_id=emp.id, curso_id=c["curso_id"], modo_prueba=body.modo_prueba,
            ))
        db.commit()
        enviados.append(EnvioResultado(cedula=cedula, nombre=emp.nombre))

    return EnviarConvocatoriaOut(enviados=enviados, fallidos=fallidos)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_convocatoria_endpoints.py -v`
Expected: all passing

Run the full backend suite: `python -m pytest -v`
Expected: all passing, no regressions

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin.py tests/test_convocatoria_endpoints.py
git commit -m "feat: POST /admin/enviar-convocatoria con modo prueba y registro en envios_convocatoria"
```

---

## Fase C — Frontend (dashboard-telcou-s1)

### Task 14: `api_client.py` — helpers de escritura + funciones nuevas

**Files:**
- Modify: `api_client.py` (repo root)
- Modify: `.streamlit/secrets.toml`
- Modify: `secrets_TEMPLATE.toml`

No automated tests exist for `api_client.py` in this repo (Streamlit apps here aren't unit-tested — verified manually via the running app, consistent with the rest of the codebase). Verify this task manually in Task 18/19.

- [ ] **Step 1: Add `ADMIN_TOKEN` to secrets**

Edit `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\.streamlit\secrets.toml`:

```toml
API_BASE_URL = "http://localhost:8000"
ADMIN_TOKEN = "telcou_admin_2025"
```

(Value must match `ADMIN_TOKEN` in `telcou-api`'s `.env` — currently `telcou_admin_2025`.)

Edit `secrets_TEMPLATE.toml`, add after the existing `API_BASE_URL` line:

```toml
# Token admin de telcou-api (header X-Admin-Token) — requerido por la tab Convocatoria
ADMIN_TOKEN = "cambiar_este_token_en_produccion"
```

- [ ] **Step 2: Add `_patch()`/`_post()` helpers and the 5 new client functions**

Edit `api_client.py`. After the existing `_get()` function, add:

```python
def _write(method: str, path: str, json: dict = None, params: dict = None) -> dict | list | None:
    headers = {"X-Admin-Token": st.secrets.get("ADMIN_TOKEN", "")}
    try:
        r = requests.request(
            method, f"{_base()}{path}", json=json, params=params, headers=headers, timeout=60,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("No se puede conectar a la API. Verifica que telcou-api esté corriendo en " + _base())
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"Error de API ({e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        st.error(f"Error inesperado al contactar la API: {e}")
        return None


def _patch(path: str, json: dict) -> dict | None:
    return _write("PATCH", path, json=json)


def _post(path: str, json: dict) -> dict | None:
    return _write("POST", path, json=json)
```

At the end of the file, add the 5 new functions (no `@st.cache_data` on these — the reads must reflect the latest writes, and the writes obviously aren't cacheable):

```python
def get_convocatoria_preview(dia: str, regional: str, semana: str) -> list[dict]:
    return _get(
        "/analitica/convocatoria-preview",
        {"dia": dia, "regional": regional, "semana": semana},
    ) or []


def buscar_supletorios_pendientes(nombre: str, anio: int, regional: Optional[str] = None) -> list[dict]:
    params = {"nombre": nombre, "anio": anio}
    if regional:
        params["regional"] = regional
    return _get("/analitica/supletorios-pendientes/buscar", params) or []


def get_dia_historial(cedula: str) -> list[dict]:
    return _get(f"/empleados/{quote(cedula, safe='')}/dia-historial") or []


def cambiar_dia_empleado(
    cedula: str,
    dia_nuevo: str,
    tipo: str,
    motivo: str,
    semana_inicio: Optional[str] = None,
    editado_por: Optional[str] = None,
) -> dict | None:
    body = {"dia_nuevo": dia_nuevo, "tipo": tipo, "motivo": motivo}
    if semana_inicio:
        body["semana_inicio"] = semana_inicio
    if editado_por:
        body["editado_por"] = editado_por
    return _patch(f"/empleados/{quote(cedula, safe='')}/dia", body)


def enviar_convocatoria(
    cedulas: list[str],
    semana: str,
    modo_prueba: bool,
    correo_prueba: Optional[str] = None,
) -> dict | None:
    body = {"cedulas": cedulas, "semana": semana, "modo_prueba": modo_prueba}
    if correo_prueba:
        body["correo_prueba"] = correo_prueba
    return _post("/admin/enviar-convocatoria", body)
```

- [ ] **Step 3: Verify imports and syntax**

Run: `cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1" && python -m py_compile api_client.py && echo OK`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add api_client.py .streamlit/secrets.toml secrets_TEMPLATE.toml
git commit -m "feat: helpers de escritura (_patch/_post) y funciones de convocatoria en api_client"
```

---

### Task 15: `ui/convocatoria.py` — filtros, tabla principal, cambiar día

**Files:**
- Create: `ui/convocatoria.py`

- [ ] **Step 1: Create the file**

```python
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
```

- [ ] **Step 2: Verify it imports cleanly (will fail until Tasks 16 add the two referenced functions — that's expected here)**

Run: `python -c "import ast; ast.parse(open('ui/convocatoria.py').read())" `
Expected: no `SyntaxError` (this only checks syntax, not that `_seccion_agregar_por_nombre`/`_seccion_envio` exist yet — they're added in Task 16)

- [ ] **Step 3: Commit**

```bash
git add ui/convocatoria.py
git commit -m "feat: tab Convocatoria - filtros, tabla principal y formulario cambiar dia"
```

---

### Task 16: `ui/convocatoria.py` — buscador y panel de envío

**Files:**
- Modify: `ui/convocatoria.py`

- [ ] **Step 1: Append the two missing functions**

Add to `ui/convocatoria.py`, after `render_tab_convocatoria`:

```python
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
```

- [ ] **Step 2: Verify full syntax**

Run: `cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1" && python -m py_compile ui/convocatoria.py && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/convocatoria.py
git commit -m "feat: tab Convocatoria - buscador por nombre y panel de envio con modo prueba"
```

---

### Task 17: Enganchar la tab en `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Wire the new tab**

Edit `app.py`:

```python
from ui.convocatoria import render_tab_convocatoria
```

```python
tab_colab, tab_area, tab_analitica, tab_convocatoria = st.tabs(
    ["👥 Colaboradores", "🏢 Áreas", "📈 Analítica", "📧 Convocatoria"]
)
```

```python
with tab_convocatoria:
    render_tab_convocatoria(anio)
```

- [ ] **Step 2: Verify syntax**

Run: `python -m py_compile app.py && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: enganchar tab Convocatoria en app.py"
```

---

## Fase D — Migración de datos, verificación y documentación

### Task 18: Migrar BD, correr import real, smoke test manual

**Files:** ninguno (operación, no código)

- [ ] **Step 1: Confirmar que todas las migraciones están aplicadas**

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api"
python -m alembic upgrade head
python -m alembic current
```
Expected: el head coincide con la última migración de Task 5

- [ ] **Step 2: Dry-run del import de variables_adicionales (ya con correo)**

```bash
python scripts/importar_variables_adicionales.py --dry-run
```
Revisar la salida: cuántas filas con cédula, cuántas sin match. Si se ve razonable, correr sin `--dry-run`:

```bash
python scripts/importar_variables_adicionales.py
```

- [ ] **Step 3: Reiniciar la API (recoge el código nuevo)**

```bash
# Detener el proceso uvicorn existente en :8000 si sigue corriendo, luego:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 4: Smoke test con curl de los 4 endpoints nuevos**

```bash
curl -s "http://localhost:8000/analitica/convocatoria-preview?dia=LUNES&regional=TS%20R2&semana=2026-07-06" | head -c 500

curl -s "http://localhost:8000/analitica/supletorios-pendientes/buscar?nombre=A&anio=2026" | head -c 500

curl -s -X PATCH "http://localhost:8000/empleados/<cedula_real_de_prueba>/dia" \
  -H "X-Admin-Token: telcou_admin_2025" -H "Content-Type: application/json" \
  -d '{"dia_nuevo":"MARTES","tipo":"SEMANAL","semana_inicio":"2026-07-06","motivo":"smoke test"}'

curl -s "http://localhost:8000/empleados/<cedula_real_de_prueba>/dia-historial"
```
Expected: 200 en los 4, sin tracebacks

- [ ] **Step 4: Commit (si el import real modificó algo versionado — normalmente no, son datos en BD, no en git)**

No aplica commit — este task solo toca la base de datos, no archivos del repo.

---

### Task 19: Verificación en navegador (Playwright)

**Files:** ninguno (verificación)

- [ ] **Step 1: Asegurar que API (:8000) y dashboard (:8501) están corriendo**

Mismo patrón que la verificación de "Detalle de Pendientes" en la sesión anterior: iniciar ambos en background, hacer polling con curl hasta que respondan 200.

- [ ] **Step 2: Script Playwright — flujo completo**

Reutilizar el setup de `pw-test` (playwright + chromium headless-shell ya instalados en esta máquina). Escribir un script que:
1. Navegue a `http://localhost:8501`, entre a la tab "📧 Convocatoria"
2. Seleccione Regional=TS R2, Día=LUNES (o el que tenga datos reales tras el import), cargue la convocatoria
3. Tome un screenshot de la tabla principal
4. Click en "Cambiar día" de una fila, llene el formulario (tipo SEMANAL, motivo, semana), guarde
5. Confirme que esa persona desaparece de la lista (screenshot antes/después)
6. Use el buscador "Agregar por nombre", agregue a alguien
7. Active modo prueba, ingrese un correo de prueba, confirme envío
8. Tome screenshot del resumen final
9. `console --errors` / revisar `page.on("console")` para confirmar que no hay excepciones de Streamlit

Expected: cada paso se refleja visualmente, sin tracebacks de Python visibles en pantalla, sin errores de consola.

- [ ] **Step 3: Confirmar en la base de datos que el envío de prueba quedó registrado**

```bash
curl -s "http://localhost:8000/empleados/<cedula_usada>/dia-historial"
```
Expected: incluye el cambio hecho en el paso 4

---

### Task 20: Documentación

**Files:**
- Modify: `docs/README.md` (este repo)
- Modify: Obsidian vault `TelcoU Dashboard` — `TABS.md`, `API_CLIENTE.md`, `ARQUITECTURA.md`, `TelcoU Dashboard.md`
- Modify: Obsidian vault `TelcoU DB API` — `API_ENDPOINTS.md`, `TelcoU DB API.md` (tabla de endpoints + pendientes)
- Modify: memoria de archivo en `C:\Users\USUARIO\.claude\projects\C--Users-USUARIO-Desktop-DesarrollosRodri-dashboard-telcou-s1\memory\`

- [ ] **Step 1: `docs/README.md`** — agregar sección "📧 Convocatoria" a la lista de tabs (junto a Colaboradores/Áreas/Analítica), agregar las 5 funciones nuevas a la tabla de `api_client.py`, agregar nota sobre `ADMIN_TOKEN` en secrets.

- [ ] **Step 2: Vault `TelcoU Dashboard`**
  - `TelcoU Dashboard.md`: agregar fila a "Tabs disponibles" y entradas al "Historial de desarrollo" con fecha real de implementación; **quitar** la sección "Pendiente" que mencionaba `supletorios-pendientes` sin consumir (ya se consume) y actualizar/quitar la nota de conv=2 si ya no aplica.
  - `TABS.md`: nueva sección "📧 Convocatoria (`ui/convocatoria.py`)" con el mismo nivel de detalle que las demás tabs (filtros, tabla, acciones, endpoints que usa).
  - `API_CLIENTE.md`: documentar `get_convocatoria_preview`, `buscar_supletorios_pendientes`, `get_dia_historial`, `cambiar_dia_empleado`, `enviar_convocatoria`, y el helper `_patch`/`_post` (a diferencia de `_get`, requieren `ADMIN_TOKEN`).
  - `ARQUITECTURA.md`: agregar `ui/convocatoria.py` al árbol de archivos y una nota sobre `ADMIN_TOKEN` en la sección de configuración.

- [ ] **Step 3: Vault `TelcoU DB API`**
  - `API_ENDPOINTS.md`: documentar los 5 endpoints nuevos/cambiados (`PATCH /empleados/{cedula}/dia`, `GET .../dia-historial`, `GET /analitica/convocatoria-preview`, `GET /analitica/supletorios-pendientes/buscar`, `POST /admin/enviar-convocatoria`), con la regla de "día efectivo" explicada igual que en la spec.
  - `TelcoU DB API.md`: agregar filas a "Pendientes" marcadas `[x]` para lo implementado, agregar las 3 tablas nuevas a cualquier tabla de esquema si existe, actualizar "Migraciones aplicadas" con las 3 migraciones nuevas.

- [ ] **Step 4: Memoria de archivo**

Actualizar `project_dashboard_vs_api_gap.md` (o crear una nueva memoria si el gap ya se cerró) reflejando que el gap documentado el 2026-07-02 (supletorios-pendientes no consumido) ya se cerró, y agregar los datos nuevos de esta feature: SMTP reutilizado de `TelcoU_Notificaciones` (contraseña expuesta en texto plano ahí, pendiente rotar), estructura de `dia_cambios`/`envios_convocatoria`, y que `telcou-api` no tiene remoto de GitHub mientras `dashboard-telcou-s1` sí (pero solo se hacen commits locales, nunca push sin permiso explícito).

- [ ] **Step 5: Commit (solo en dashboard-telcou-s1 — el vault de Obsidian no es un repo git de este proyecto)**

```bash
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
git add docs/README.md
git commit -m "docs: documentar tab Convocatoria a Supletorios"
```

Y en `telcou-api` si se tocó algo ahí (no debería, esta fase es solo docs del lado que ya tiene el código implementado — los cambios reales de API ya se comitearon en Fases A/B).
