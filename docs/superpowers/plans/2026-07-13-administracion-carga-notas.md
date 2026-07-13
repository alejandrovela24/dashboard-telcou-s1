# Administración — Carga de Notas por CSV — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nueva sección "🛠️ Administración" en el dashboard para cargar notas de capacitaciones (nuevas o supletorios) desde el export crudo de Moodle, dar de alta empleados nuevos en el mismo flujo, y gestionar "novedades" (activos sin nota → aviso agrupado al jefe → resolución manual).

**Architecture:** Backend nuevo servicio `app/services/carga_notas.py` (parser CSV + upsert de curso/notas) más 4 endpoints en `telcou-api` (todos protegidos con `X-Admin-Token`), reutilizando `mailer.py`/`Importacion`/el patrón de recopilatorio-por-jefe ya existentes. Frontend nueva `ui/administracion.py` con 2 secciones (Carga de curso, Novedades), registrada como 5ª entrada del sidebar.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (backend), Streamlit 1.57 + pandas + requests (frontend), pytest + TestClient para tests backend.

## Global Constraints

- **Sin migraciones de base de datos** — `Empleado`/`VariableAdicional` ya tienen todos los campos necesarios; `Nota.estado` es texto libre (`String(30)`, sin `CHECK`), así que `PENDIENTE_JUSTIFICACION` no requiere cambio de esquema.
- **Umbral de aprobación:** `Decimal("7.5")` — `nota >= 7.5` → `APROBADO`, si no → `REPROBADO`. Mismo valor que `importar_quito2026.py`/`importar_ts2026.py`.
- **CSV de Moodle, formato fijo:** UTF-8 con BOM (`encoding="utf-8-sig"`), coma decimal en las notas, columna `Número de ID` = cédula (normalizar con `.zfill(10)` si es numérica), fila final "Promedio general" con `Nombre` vacío se descarta.
- **Catálogo de resolución de novedades:** únicamente estados ya existentes en el sistema — `FALTA_INJUSTIFICADA`, `FALTA_JUSTIFICADA`, `NO_APLICA`, `VACACIONES`, `EXONERADO`, `ASISTENCIA`. Nunca se inventan estados nuevos aquí; solo se resuelve hacia el catálogo existente.
- **`PENDIENTE_JUSTIFICACION` cuenta como pendiente de supletorio** mientras no se resuelve — se agrega a `NECESITA_SUPLETORIO` en `app/services/convocatoria.py`.
- **Modo prueba obligatorio y ON por defecto** para el correo de novedades — si `modo_prueba=True`, `correo_prueba` es requerido (400 si falta). Mismo mecanismo que `POST /admin/enviar-convocatoria`.
- **Todos los endpoints nuevos requieren `X-Admin-Token`** vía `Depends(verify_admin)` (importado de `app.routers.admin`) — nunca duplicar la lógica de autenticación.
- **Cédulas sin match en la BD no abortan el resto de una carga** — se acumulan y se reportan aparte.
- **Modo B (supletorio) requiere una nota REGULAR previa** para esa persona+curso — si no existe, esa fila se reporta como error, nunca se crea un supletorio huérfano.
- **TDD en todo el backend:** test que falla → implementación mínima → test pasa → commit. Los tests que disparan un `db.commit()` real deben usar identificadores (cédula, nombre de regional) parametrizados con `uuid` para no colisionar entre corridas de pytest — el fixture `db` de `tests/conftest.py` solo hace `rollback()`, no trunca.
- **Nunca pushear a GitHub desde `dashboard-telcou-s1`** sin permiso explícito (el remoto sirve un dashboard en producción). `telcou-api` no tiene remoto — los commits locales son siempre seguros.
- **Gotcha de Windows:** al reiniciar `uvicorn --reload`, un `Stop-Process` sobre el proceso padre puede dejar un hijo `multiprocessing-fork` huérfano sirviendo código viejo en el mismo puerto. El paso de verificación debe confirmar explícitamente que no quedó un huérfano (buscar procesos `multiprocessing-fork` y matarlos) antes de confiar en que el servidor está arriba.

---

### Task 1: `PENDIENTE_JUSTIFICACION` en `NECESITA_SUPLETORIO`

**Files:**
- Modify: `app/services/convocatoria.py:13`
- Test: `tests/test_convocatoria_service.py`

**Interfaces:**
- Produces: `NECESITA_SUPLETORIO` (set) ahora incluye `"PENDIENTE_JUSTIFICACION"`, consumido por `supletorios_pendientes_data()` (ya existente) y por todas las tareas posteriores que dependen de esa lógica.

- [ ] **Step 1: Write the failing tests**

Abre `tests/test_convocatoria_service.py`. Cambia la línea de import existente:

```python
from app.services.convocatoria import DIAS_VALIDOS, lunes_de_semana
```

por:

```python
from app.services.convocatoria import DIAS_VALIDOS, lunes_de_semana, NECESITA_SUPLETORIO
```

Agrega al final del archivo:

```python
def test_pendiente_justificacion_esta_en_necesita_supletorio():
    assert "PENDIENTE_JUSTIFICACION" in NECESITA_SUPLETORIO


def test_pendiente_justificacion_cuenta_como_supletorio_pendiente(db):
    import uuid
    from app.services.convocatoria import supletorios_pendientes_data

    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"TS R2 PendJust {sufijo}")
    db.add(reg); db.flush()
    emp = Empleado(cedula=f"66{uuid.uuid4().int % 10**8:08d}", nombre="EMP PENDJUST", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"PJ-{sufijo}", nombre="CURSO PENDJUST", tipo="PRESENCIAL",
                  mes="JULIO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    db.add(Nota(empleado_id=emp.id, curso_id=curso.id, estado="PENDIENTE_JUSTIFICACION", tipo="REGULAR"))
    db.flush()

    data = supletorios_pendientes_data(db, 2026, regional=f"TS R2 PendJust {sufijo}")
    assert len(data) == 1
    assert data[0]["ultimo_estado"] == "PENDIENTE_JUSTIFICACION"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_convocatoria_service.py -k pendiente_justificacion -v`
Expected: FAIL — `ImportError: cannot import name 'NECESITA_SUPLETORIO'` (el import falla porque el nombre no está exportado con ese valor todavía, o el primer assert falla).

- [ ] **Step 3: Implementación mínima**

En `app/services/convocatoria.py:13`, cambia:

```python
NECESITA_SUPLETORIO = {"REPROBADO", "FALTA_INJUSTIFICADA"}
```

por:

```python
NECESITA_SUPLETORIO = {"REPROBADO", "FALTA_INJUSTIFICADA", "PENDIENTE_JUSTIFICACION"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_convocatoria_service.py -v`
Expected: todos los tests del archivo PASS, incluyendo los 2 nuevos.

- [ ] **Step 5: Commit**

```bash
git add app/services/convocatoria.py tests/test_convocatoria_service.py
git commit -m "feat: PENDIENTE_JUSTIFICACION cuenta como pendiente de supletorio"
```

---

### Task 2: Parser del CSV de Moodle

**Files:**
- Create: `app/services/carga_notas.py`
- Test: `tests/test_carga_notas.py`

**Interfaces:**
- Produces: `parsear_csv_moodle(contenido: bytes) -> list[dict]`, cada dict con claves `cedula: str, nombre: str, area: str | None, correo: str | None, nota: Decimal`. Consumido por Task 3 y Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_carga_notas.py`:

```python
from decimal import Decimal

from app.services.carga_notas import parsear_csv_moodle

CSV_EJEMPLO = (
    'Nombre,Ciudad,Departamento,"Dirección de correo","Número de ID",Estado,'
    '"Comenzado el",Finalizado,"Tiempo requerido","Calificación/10,00",'
    '"P. 1 /1,00","P. 2 /1,00"\n'
    '"PEREZ JUAN",QUITO,"OPERACIONES URBANAS",jperez@telconet.ec,1723555437,Finalizado,'
    '"12 de enero de 2026  08:15","12 de enero de 2026  08:17","2 minutos","10,00","1,00","1,00"\n'
    '"GOMEZ ANA",QUITO,GIS,agomez@telconet.ec,0503422164,Finalizado,'
    '"12 de enero de 2026  08:16","12 de enero de 2026  08:26","9 minutos","6,00","1,00","0,00"\n'
    '"TORRES LUIS",QUITO,GIS,ltorres@telconet.ec,123456789,Finalizado,'
    '"12 de enero de 2026  08:18","12 de enero de 2026  08:28","5 minutos","4,00","0,00","1,00"\n'
    ',,,,,,,,,"6,67","0,67","0,67"\n'
)


def test_parsea_filas_validas_y_descarta_promedio_general():
    filas = parsear_csv_moodle(CSV_EJEMPLO.encode("utf-8-sig"))
    assert len(filas) == 3
    assert filas[0]["nombre"] == "PEREZ JUAN"
    assert filas[0]["cedula"] == "1723555437"
    assert filas[0]["nota"] == Decimal("10.00")
    assert filas[0]["area"] == "OPERACIONES URBANAS"
    assert filas[0]["correo"] == "jperez@telconet.ec"


def test_preserva_cedula_con_cero_a_la_izquierda():
    filas = parsear_csv_moodle(CSV_EJEMPLO.encode("utf-8-sig"))
    assert filas[1]["cedula"] == "0503422164"


def test_normaliza_cedula_corta_con_zfill():
    filas = parsear_csv_moodle(CSV_EJEMPLO.encode("utf-8-sig"))
    assert filas[2]["cedula"] == "0123456789"


def test_parsea_nota_con_coma_decimal():
    filas = parsear_csv_moodle(CSV_EJEMPLO.encode("utf-8-sig"))
    assert filas[1]["nota"] == Decimal("6.00")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_carga_notas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.carga_notas'`

- [ ] **Step 3: Implementación mínima**

Create `app/services/carga_notas.py`:

```python
import csv
import io
from decimal import Decimal, InvalidOperation

UMBRAL_APROBACION = Decimal("7.5")


def parsear_csv_moodle(contenido: bytes) -> list[dict]:
    """
    Parsea el export crudo de Moodle (calificaciones de un curso). Descarta
    la fila final de "Promedio general" (Nombre vacío) y cualquier fila cuya
    calificación no se pueda interpretar como número.
    """
    texto = contenido.decode("utf-8-sig")
    lector = csv.DictReader(io.StringIO(texto))
    filas: list[dict] = []

    for fila in lector:
        nombre = (fila.get("Nombre") or "").strip()
        if not nombre:
            continue

        cedula_raw = (fila.get("Número de ID") or "").strip()
        cedula = cedula_raw.zfill(10) if cedula_raw.isdigit() else cedula_raw

        nota_raw = (fila.get("Calificación/10,00") or "").strip()
        try:
            nota = Decimal(nota_raw.replace(",", "."))
        except InvalidOperation:
            continue

        filas.append({
            "cedula": cedula,
            "nombre": nombre,
            "area": (fila.get("Departamento") or "").strip() or None,
            "correo": (fila.get("Dirección de correo") or "").strip() or None,
            "nota": nota,
        })

    return filas


def estado_para_nota(nota: Decimal) -> str:
    return "APROBADO" if nota >= UMBRAL_APROBACION else "REPROBADO"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_carga_notas.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/carga_notas.py tests/test_carga_notas.py
git commit -m "feat: parser del CSV de Moodle para carga de notas"
```

---

### Task 3: Servicio — cargar curso nuevo (Modo A)

**Files:**
- Modify: `app/services/carga_notas.py`
- Test: `tests/test_carga_notas.py`

**Interfaces:**
- Consumes: `parsear_csv_moodle()` output shape (Task 2), `estado_para_nota()` (Task 2).
- Produces: `cargar_curso_nuevo(db, filas, *, codigo, nombre, tipo, mes, fecha_inicio, fecha_fin, anio, regional_nombre, importado_por=None) -> dict` con claves `curso_id: int, nuevos: int, actualizados: int, sin_match: list[dict]`. Cada `sin_match` item: `{cedula, nombre, area, correo}`. Consumido por Task 5 (endpoint).

- [ ] **Step 1: Write the failing tests**

Agrega a `tests/test_carga_notas.py` (al inicio del archivo, junto a los demás imports):

```python
import uuid
from datetime import date

from app.models import Regional, Empleado, Curso, Nota
from app.services.carga_notas import cargar_curso_nuevo
```

Agrega al final del archivo:

```python
def test_cargar_curso_nuevo_crea_curso_y_notas_regular(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito CargaNuevo {sufijo}")
    db.add(reg); db.flush()
    cedula = f"17{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="PEREZ JUAN", regional_id=reg.id)
    db.add(emp); db.flush()
    db.flush()

    filas = [{"cedula": cedula, "nombre": "PEREZ JUAN", "area": "OPU", "correo": "j@x.ec", "nota": Decimal("9.00")}]

    resultado = cargar_curso_nuevo(
        db, filas, codigo=f"ES-{sufijo}", nombre="ESTANDAR DE SOPORTE", tipo="VIRTUAL",
        mes="ENERO", fecha_inicio=date(2026, 1, 6), fecha_fin=date(2026, 1, 12),
        anio=2026, regional_nombre=f"Quito CargaNuevo {sufijo}", importado_por="admin",
    )

    assert resultado["nuevos"] == 1
    assert resultado["actualizados"] == 0
    assert resultado["sin_match"] == []

    curso = db.query(Curso).filter_by(id=resultado["curso_id"]).first()
    assert curso.nombre == "ESTANDAR DE SOPORTE"
    nota = db.query(Nota).filter_by(empleado_id=emp.id, curso_id=curso.id).first()
    assert nota.valor == Decimal("9.00")
    assert nota.estado == "APROBADO"
    assert nota.tipo == "REGULAR"
    assert nota.convocatoria == 1


def test_cargar_curso_nuevo_reporta_cedulas_sin_match(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito SinMatch {sufijo}")
    db.add(reg); db.flush()

    filas = [{"cedula": "9999999999", "nombre": "DESCONOCIDO", "area": None, "correo": None, "nota": Decimal("8.00")}]

    resultado = cargar_curso_nuevo(
        db, filas, codigo=f"SM-{sufijo}", nombre="CURSO SIN MATCH", tipo="VIRTUAL",
        mes="ENERO", fecha_inicio=date(2026, 1, 6), fecha_fin=date(2026, 1, 12),
        anio=2026, regional_nombre=f"Quito SinMatch {sufijo}", importado_por="admin",
    )

    assert resultado["nuevos"] == 0
    assert resultado["sin_match"] == [{"cedula": "9999999999", "nombre": "DESCONOCIDO", "area": None, "correo": None}]


def test_cargar_curso_nuevo_recargar_actualiza_no_duplica(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito Recarga {sufijo}")
    db.add(reg); db.flush()
    cedula = f"18{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="LOPEZ ANA", regional_id=reg.id)
    db.add(emp); db.flush()

    filas_v1 = [{"cedula": cedula, "nombre": "LOPEZ ANA", "area": None, "correo": None, "nota": Decimal("5.00")}]
    r1 = cargar_curso_nuevo(
        db, filas_v1, codigo=f"RC-{sufijo}", nombre="CURSO RECARGA", tipo="VIRTUAL",
        mes="ENERO", fecha_inicio=date(2026, 1, 6), fecha_fin=date(2026, 1, 12),
        anio=2026, regional_nombre=f"Quito Recarga {sufijo}", importado_por="admin",
    )
    assert r1["nuevos"] == 1

    filas_v2 = [{"cedula": cedula, "nombre": "LOPEZ ANA", "area": None, "correo": None, "nota": Decimal("9.00")}]
    r2 = cargar_curso_nuevo(
        db, filas_v2, codigo=f"RC-{sufijo}", nombre="CURSO RECARGA", tipo="VIRTUAL",
        mes="ENERO", fecha_inicio=date(2026, 1, 6), fecha_fin=date(2026, 1, 12),
        anio=2026, regional_nombre=f"Quito Recarga {sufijo}", importado_por="admin",
    )
    assert r2["nuevos"] == 0
    assert r2["actualizados"] == 1

    notas = db.query(Nota).filter_by(empleado_id=emp.id, curso_id=r2["curso_id"]).all()
    assert len(notas) == 1
    assert notas[0].valor == Decimal("9.00")
    assert notas[0].estado == "APROBADO"
```

Ojo: `Decimal` debe estar importado en el archivo de test (`from decimal import Decimal`, ya está en el archivo desde Task 2).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_carga_notas.py -k cargar_curso_nuevo -v`
Expected: FAIL — `ImportError: cannot import name 'cargar_curso_nuevo'`

- [ ] **Step 3: Implementación mínima**

Agrega a `app/services/carga_notas.py`:

```python
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.curso import Curso
from app.models.empleado import Empleado
from app.models.importacion import Importacion
from app.models.nota import Nota
from app.models.regional import Regional


def _get_or_create_regional(db: Session, nombre: str) -> Regional:
    regional = db.query(Regional).filter_by(nombre=nombre).first()
    if not regional:
        regional = Regional(nombre=nombre)
        db.add(regional)
        db.flush()
    return regional


def cargar_curso_nuevo(
    db: Session,
    filas: list[dict],
    *,
    codigo: str,
    nombre: str,
    tipo: str,
    mes: str,
    fecha_inicio,
    fecha_fin,
    anio: int,
    regional_nombre: str,
    importado_por: str | None = None,
) -> dict:
    regional = _get_or_create_regional(db, regional_nombre)

    curso_stmt = (
        insert(Curso)
        .values(
            codigo=codigo, nombre=nombre, tipo=tipo, mes=mes,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin,
            anio=anio, regional_id=regional.id,
        )
        .on_conflict_do_update(
            constraint="uq_curso_codigo_anio_regional",
            set_={"nombre": nombre, "tipo": tipo, "mes": mes,
                  "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin},
        )
        .returning(Curso.id)
    )
    curso_id = db.execute(curso_stmt).scalar()

    nuevos = 0
    actualizados = 0
    sin_match: list[dict] = []

    for fila in filas:
        emp = db.query(Empleado).filter_by(cedula=fila["cedula"], regional_id=regional.id).first()
        if not emp:
            sin_match.append({
                "cedula": fila["cedula"], "nombre": fila["nombre"],
                "area": fila["area"], "correo": fila["correo"],
            })
            continue

        estado = estado_para_nota(fila["nota"])
        nota_stmt = (
            insert(Nota)
            .values(
                empleado_id=emp.id, curso_id=curso_id, valor=fila["nota"],
                estado=estado, tipo="REGULAR", convocatoria=1,
            )
            .on_conflict_do_update(
                constraint="uq_nota_empleado_curso_tipo_conv",
                set_={"valor": fila["nota"], "estado": estado},
            )
            .returning(Nota.id, text("(xmax = 0) AS inserted"))
        )
        _, inserted = db.execute(nota_stmt).fetchone()
        if inserted:
            nuevos += 1
        else:
            actualizados += 1

    db.add(Importacion(
        archivo=f"{codigo}-{anio}", regional_id=regional.id, anio=anio, tipo="NOTAS",
        registros_nuevos=nuevos, registros_actualizados=actualizados,
        registros_ignorados=len(sin_match), importado_por=importado_por,
    ))
    db.commit()

    return {"curso_id": curso_id, "nuevos": nuevos, "actualizados": actualizados, "sin_match": sin_match}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_carga_notas.py -v`
Expected: 7 passed (4 del parser + 3 nuevos)

- [ ] **Step 5: Commit**

```bash
git add app/services/carga_notas.py tests/test_carga_notas.py
git commit -m "feat: cargar curso nuevo con notas REGULAR desde CSV (Modo A)"
```

---

### Task 4: Servicio — cargar supletorio de curso existente (Modo B)

**Files:**
- Modify: `app/services/carga_notas.py`
- Test: `tests/test_carga_notas.py`

**Interfaces:**
- Consumes: `parsear_csv_moodle()`, `estado_para_nota()` (Task 2).
- Produces: `cargar_supletorio(db, filas, *, curso_id, convocatoria, importado_por=None) -> dict` con claves `curso_id, nuevos, actualizados, sin_match: list[dict], sin_regular: list[dict]`. Cada `sin_regular` item: `{cedula, nombre}`. Consumido por Task 5.

- [ ] **Step 1: Write the failing tests**

Agrega a `tests/test_carga_notas.py`:

```python
from app.services.carga_notas import cargar_supletorio
```

Al final del archivo:

```python
def test_cargar_supletorio_enlaza_nota_original_id(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"TS R2 Supletorio {sufijo}")
    db.add(reg); db.flush()
    cedula = f"19{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="RUIZ PEDRO", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"SUP-{sufijo}", nombre="CURSO SUPLETORIO", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()
    regular = Nota(empleado_id=emp.id, curso_id=curso.id, valor=Decimal("4.00"),
                    estado="REPROBADO", tipo="REGULAR", convocatoria=1)
    db.add(regular); db.flush()

    filas = [{"cedula": cedula, "nombre": "RUIZ PEDRO", "area": None, "correo": None, "nota": Decimal("8.00")}]

    resultado = cargar_supletorio(db, filas, curso_id=curso.id, convocatoria=2, importado_por="admin")

    assert resultado["nuevos"] == 1
    assert resultado["sin_regular"] == []

    supletorio = db.query(Nota).filter_by(empleado_id=emp.id, curso_id=curso.id, tipo="SUPLETORIO").first()
    assert supletorio.convocatoria == 2
    assert supletorio.valor == Decimal("8.00")
    assert supletorio.estado == "APROBADO"
    assert supletorio.nota_original_id == regular.id


def test_cargar_supletorio_sin_regular_previo_se_reporta_como_error(db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"TS R2 SinRegular {sufijo}")
    db.add(reg); db.flush()
    cedula = f"20{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="SIN REGULAR", regional_id=reg.id)
    db.add(emp); db.flush()
    curso = Curso(codigo=f"SR-{sufijo}", nombre="CURSO SIN REGULAR", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()

    filas = [{"cedula": cedula, "nombre": "SIN REGULAR", "area": None, "correo": None, "nota": Decimal("8.00")}]

    resultado = cargar_supletorio(db, filas, curso_id=curso.id, convocatoria=2, importado_por="admin")

    assert resultado["nuevos"] == 0
    assert resultado["sin_regular"] == [{"cedula": cedula, "nombre": "SIN REGULAR"}]
    assert db.query(Nota).filter_by(empleado_id=emp.id, curso_id=curso.id).count() == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_carga_notas.py -k cargar_supletorio -v`
Expected: FAIL — `ImportError: cannot import name 'cargar_supletorio'`

- [ ] **Step 3: Implementación mínima**

Agrega a `app/services/carga_notas.py`:

```python
def cargar_supletorio(
    db: Session,
    filas: list[dict],
    *,
    curso_id: int,
    convocatoria: int,
    importado_por: str | None = None,
) -> dict:
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        raise ValueError(f"Curso {curso_id} no encontrado")

    nuevos = 0
    actualizados = 0
    sin_match: list[dict] = []
    sin_regular: list[dict] = []

    for fila in filas:
        emp = db.query(Empleado).filter_by(cedula=fila["cedula"], regional_id=curso.regional_id).first()
        if not emp:
            sin_match.append({
                "cedula": fila["cedula"], "nombre": fila["nombre"],
                "area": fila["area"], "correo": fila["correo"],
            })
            continue

        regular = (
            db.query(Nota)
            .filter_by(empleado_id=emp.id, curso_id=curso_id, tipo="REGULAR")
            .first()
        )
        if not regular:
            sin_regular.append({"cedula": fila["cedula"], "nombre": fila["nombre"]})
            continue

        estado = estado_para_nota(fila["nota"])
        nota_stmt = (
            insert(Nota)
            .values(
                empleado_id=emp.id, curso_id=curso_id, valor=fila["nota"],
                estado=estado, tipo="SUPLETORIO", convocatoria=convocatoria,
                nota_original_id=regular.id,
            )
            .on_conflict_do_update(
                constraint="uq_nota_empleado_curso_tipo_conv",
                set_={"valor": fila["nota"], "estado": estado, "nota_original_id": regular.id},
            )
            .returning(Nota.id, text("(xmax = 0) AS inserted"))
        )
        _, inserted = db.execute(nota_stmt).fetchone()
        if inserted:
            nuevos += 1
        else:
            actualizados += 1

    db.add(Importacion(
        archivo=f"{curso.codigo}-supletorio{convocatoria}", regional_id=curso.regional_id,
        anio=curso.anio, tipo="SUPLETORIOS",
        registros_nuevos=nuevos, registros_actualizados=actualizados,
        registros_ignorados=len(sin_match) + len(sin_regular), importado_por=importado_por,
    ))
    db.commit()

    return {
        "curso_id": curso_id, "nuevos": nuevos, "actualizados": actualizados,
        "sin_match": sin_match, "sin_regular": sin_regular,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_carga_notas.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add app/services/carga_notas.py tests/test_carga_notas.py
git commit -m "feat: cargar supletorio de curso existente enlazado a nota REGULAR (Modo B)"
```

---

### Task 5: Endpoint `POST /admin/cargar-curso`

**Files:**
- Create: `app/schemas/carga_notas.py`
- Modify: `app/routers/admin.py`
- Test: `tests/test_carga_notas_endpoint.py`

**Interfaces:**
- Consumes: `cargar_curso_nuevo()`, `cargar_supletorio()`, `parsear_csv_moodle()` (Tasks 2-4), `verify_admin` (existente en `app.routers.admin`).
- Produces: `CargarCursoOut` schema — `{curso_id, nuevos, actualizados, sin_match: [{cedula, nombre, area, correo}], sin_regular: [{cedula, nombre}]}`. El endpoint `POST /admin/cargar-curso`, consumido por Task 11 (frontend).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_carga_notas_endpoint.py`:

```python
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.config import settings
from app.models import Regional, Empleado, Curso, Nota


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _csv_bytes(cedula: str, nombre: str, nota: str) -> bytes:
    csv = (
        'Nombre,Ciudad,Departamento,"Dirección de correo","Número de ID",Estado,'
        '"Comenzado el",Finalizado,"Tiempo requerido","Calificación/10,00"\n'
        f'"{nombre}",QUITO,OPU,x@telconet.ec,{cedula},Finalizado,'
        f'"1 de enero de 2026","1 de enero de 2026","1 minuto","{nota}"\n'
    )
    return csv.encode("utf-8-sig")


def test_cargar_curso_sin_token_retorna_401(client):
    r = client.post(
        "/admin/cargar-curso",
        params={
            "modo": "nuevo", "codigo": "X", "nombre": "X", "tipo": "VIRTUAL", "mes": "ENERO",
            "fecha_inicio": "2026-01-06", "fecha_fin": "2026-01-12", "anio": 2026, "regional": "Quito",
        },
        files={"archivo": ("notas.csv", b"x", "text/csv")},
    )
    assert r.status_code == 401


def test_cargar_curso_modo_invalido_retorna_400(client):
    r = client.post(
        "/admin/cargar-curso",
        params={"modo": "invalido"},
        headers={"X-Admin-Token": settings.admin_token},
        files={"archivo": ("notas.csv", b"x", "text/csv")},
    )
    assert r.status_code == 400


def test_cargar_curso_modo_nuevo_crea_curso_y_notas(client, db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito CargaEndpoint {sufijo}")
    db.add(reg); db.flush()
    cedula = f"21{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="TEST ENDPOINT", regional_id=reg.id)
    db.add(emp); db.flush()

    r = client.post(
        "/admin/cargar-curso",
        params={
            "modo": "nuevo", "codigo": f"CE-{sufijo}", "nombre": "CURSO ENDPOINT", "tipo": "VIRTUAL",
            "mes": "ENERO", "fecha_inicio": "2026-01-06", "fecha_fin": "2026-01-12", "anio": 2026,
            "regional": f"Quito CargaEndpoint {sufijo}",
        },
        headers={"X-Admin-Token": settings.admin_token},
        files={"archivo": ("notas.csv", _csv_bytes(cedula, "TEST ENDPOINT", "9,00"), "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["nuevos"] == 1
    assert body["sin_match"] == []

    nota = db.query(Nota).filter_by(empleado_id=emp.id, curso_id=body["curso_id"]).first()
    assert nota.valor == Decimal("9.00")


def test_cargar_curso_modo_supletorio_requiere_curso_id_y_convocatoria(client):
    r = client.post(
        "/admin/cargar-curso?modo=supletorio",
        headers={"X-Admin-Token": settings.admin_token},
        files={"archivo": ("notas.csv", b"x", "text/csv")},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_carga_notas_endpoint.py -v`
Expected: FAIL — `404 Not Found` en vez de los códigos esperados (la ruta no existe todavía).

- [ ] **Step 3: Implementación mínima**

Create `app/schemas/carga_notas.py`:

```python
from datetime import date
from pydantic import BaseModel


class EmpleadoSinMatch(BaseModel):
    cedula: str
    nombre: str
    area: str | None
    correo: str | None


class EmpleadoSinRegular(BaseModel):
    cedula: str
    nombre: str


class CargarCursoOut(BaseModel):
    curso_id: int
    nuevos: int
    actualizados: int
    sin_match: list[EmpleadoSinMatch] = []
    sin_regular: list[EmpleadoSinRegular] = []


class EmpleadoNuevoIn(BaseModel):
    cedula: str
    nombre: str
    regional: str
    jefe_inmediato: str
    jefe_correo: str
    area: str | None = None
    correo: str | None = None
    genero: str | None = None
    sucursal: str | None = None


class EmpleadoNuevoOut(BaseModel):
    id: int
    cedula: str
    nombre: str


class NoRindioPersona(BaseModel):
    cedula: str
    nombre: str
    jefe_correo: str | None
    nota_id: int | None


class NoRindioOut(BaseModel):
    curso_id: int
    curso: str
    sin_notificar: list[NoRindioPersona]
    pendientes_resolver: list[NoRindioPersona]


class EnviarNovedadIn(BaseModel):
    cedulas: list[str]
    modo_prueba: bool = True
    correo_prueba: str | None = None


class EnviarNovedadOut(BaseModel):
    notificados: list[str]
    recopilatorios_enviados: list[str]


class ResolverNotaIn(BaseModel):
    estado: str
```

En `app/routers/admin.py`, agrega los imports (junto a los existentes al inicio del archivo):

```python
from datetime import date
from app.models.regional import Regional
from app.models.curso import Curso
from app.models.nota import Nota
from app.schemas.carga_notas import (
    CargarCursoOut,
    EmpleadoNuevoIn,
    EmpleadoNuevoOut,
)
from app.services.carga_notas import parsear_csv_moodle, cargar_curso_nuevo, cargar_supletorio
```

Agrega el endpoint (después de `listar_importaciones`, antes de `enviar_convocatoria`):

```python
@router.post("/cargar-curso", response_model=CargarCursoOut)
def cargar_curso(
    archivo: UploadFile = File(...),
    modo: str = Query(..., description="nuevo | supletorio"),
    codigo: str | None = Query(None),
    nombre: str | None = Query(None),
    tipo: str | None = Query(None),
    mes: str | None = Query(None),
    fecha_inicio: date | None = Query(None),
    fecha_fin: date | None = Query(None),
    anio: int | None = Query(None),
    regional: str | None = Query(None),
    curso_id: int | None = Query(None),
    convocatoria: int | None = Query(None),
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if modo not in ("nuevo", "supletorio"):
        raise HTTPException(status_code=400, detail="modo debe ser 'nuevo' o 'supletorio'")

    contenido = archivo.file.read()
    filas = parsear_csv_moodle(contenido)

    if modo == "nuevo":
        if not all([codigo, nombre, tipo, mes, fecha_inicio, fecha_fin, anio, regional]):
            raise HTTPException(
                status_code=400,
                detail="Para modo=nuevo se requieren: codigo, nombre, tipo, mes, fecha_inicio, fecha_fin, anio, regional",
            )
        resultado = cargar_curso_nuevo(
            db, filas, codigo=codigo, nombre=nombre, tipo=tipo, mes=mes,
            fecha_inicio=fecha_inicio, fecha_fin=fecha_fin, anio=anio,
            regional_nombre=regional, importado_por="admin",
        )
    else:
        if curso_id is None or convocatoria is None:
            raise HTTPException(
                status_code=400,
                detail="Para modo=supletorio se requieren: curso_id, convocatoria",
            )
        resultado = cargar_supletorio(
            db, filas, curso_id=curso_id, convocatoria=convocatoria, importado_por="admin",
        )

    return CargarCursoOut(**resultado)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_carga_notas_endpoint.py -v`
Expected: 4 passed

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `pytest -q`
Expected: todos los tests pasan (salvo el fallo preexistente ya conocido en `test_calculadora.py`, no relacionado a este trabajo).

- [ ] **Step 6: Commit**

```bash
git add app/schemas/carga_notas.py app/routers/admin.py tests/test_carga_notas_endpoint.py
git commit -m "feat: endpoint POST /admin/cargar-curso (modo nuevo y supletorio)"
```

---

### Task 6: Endpoint `POST /admin/empleados` — alta de empleado nuevo

**Files:**
- Modify: `app/routers/admin.py`
- Test: `tests/test_carga_notas_endpoint.py`

**Interfaces:**
- Consumes: `EmpleadoNuevoIn`/`EmpleadoNuevoOut` (Task 5).
- Produces: endpoint `POST /admin/empleados`, consumido por Task 12 (frontend, Flujo 2).

- [ ] **Step 1: Write the failing tests**

Agrega a `tests/test_carga_notas_endpoint.py`:

```python
from app.models.variable_adicional import VariableAdicional
```

Al final del archivo:

```python
def test_crear_empleado_sin_token_retorna_401(client):
    r = client.post("/admin/empleados", json={
        "cedula": "1234567890", "nombre": "X", "regional": "Quito",
        "jefe_inmediato": "Y", "jefe_correo": "y@telconet.ec",
    })
    assert r.status_code == 401


def test_crear_empleado_nuevo_crea_empleado_y_variable_adicional(client, db):
    sufijo = uuid.uuid4().hex[:8]
    cedula = f"22{uuid.uuid4().int % 10**8:08d}"

    r = client.post(
        "/admin/empleados",
        headers={"X-Admin-Token": settings.admin_token},
        json={
            "cedula": cedula, "nombre": "NUEVO EMPLEADO", "regional": f"Quito AltaEmp {sufijo}",
            "area": "OPU", "correo": "nuevo@telconet.ec",
            "jefe_inmediato": "JEFE NUEVO", "jefe_correo": "jefe@telconet.ec",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cedula"] == cedula
    assert body["nombre"] == "NUEVO EMPLEADO"

    emp = db.query(Empleado).filter_by(cedula=cedula).first()
    assert emp is not None
    assert emp.area == "OPU"
    va = db.query(VariableAdicional).filter_by(empleado_id=emp.id).first()
    assert va.correo == "nuevo@telconet.ec"
    assert va.jefe_correo == "jefe@telconet.ec"


def test_crear_empleado_cedula_duplicada_en_misma_regional_retorna_409(client, db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"Quito Duplicado {sufijo}")
    db.add(reg); db.flush()
    cedula = f"23{uuid.uuid4().int % 10**8:08d}"
    emp = Empleado(cedula=cedula, nombre="YA EXISTE", regional_id=reg.id)
    db.add(emp); db.flush()

    r = client.post(
        "/admin/empleados",
        headers={"X-Admin-Token": settings.admin_token},
        json={
            "cedula": cedula, "nombre": "YA EXISTE", "regional": f"Quito Duplicado {sufijo}",
            "jefe_inmediato": "J", "jefe_correo": "j@telconet.ec",
        },
    )
    assert r.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_carga_notas_endpoint.py -k crear_empleado -v`
Expected: FAIL — `404 Not Found`

- [ ] **Step 3: Implementación mínima**

En `app/routers/admin.py`, agrega el import de `EmpleadoNuevoIn`/`EmpleadoNuevoOut` (ya en la lista del Task 5) y de `VariableAdicional` (ya importado). Agrega el endpoint después de `cargar_curso`:

```python
@router.post("/empleados", response_model=EmpleadoNuevoOut)
def crear_empleado(
    body: EmpleadoNuevoIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    regional = db.query(Regional).filter_by(nombre=body.regional).first()
    if not regional:
        regional = Regional(nombre=body.regional)
        db.add(regional)
        db.flush()

    existente = db.query(Empleado).filter_by(cedula=body.cedula, regional_id=regional.id).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un empleado con esa cédula en esa regional")

    emp = Empleado(
        cedula=body.cedula, nombre=body.nombre, genero=body.genero,
        area=body.area, jefe_inmediato=body.jefe_inmediato,
        regional_id=regional.id, sucursal=body.sucursal,
    )
    db.add(emp)
    db.flush()

    db.add(VariableAdicional(
        empleado_id=emp.id, correo=body.correo,
        jefe_correo=body.jefe_correo, jefe_inmediato=body.jefe_inmediato,
    ))
    db.commit()

    return EmpleadoNuevoOut(id=emp.id, cedula=emp.cedula, nombre=emp.nombre)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_carga_notas_endpoint.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin.py tests/test_carga_notas_endpoint.py
git commit -m "feat: endpoint POST /admin/empleados para alta de empleado nuevo"
```

---

### Task 7: Endpoint `GET /analitica/curso/{curso_id}/no-rindieron`

**Files:**
- Modify: `app/routers/analitica.py`
- Test: `tests/test_no_rindieron.py`

**Interfaces:**
- Consumes: `NoRindioOut`/`NoRindioPersona` (Task 5), `verify_admin`.
- Produces: endpoint `GET /analitica/curso/{curso_id}/no-rindieron`, devuelve `{curso_id, curso, sin_notificar: [...], pendientes_resolver: [...]}`. Consumido por Task 9 (enviar-novedad, indirectamente vía la UI que selecciona cédulas) y Task 12 (frontend).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_no_rindieron.py`:

```python
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.config import settings
from app.models import Regional, Empleado, Curso, Nota
from app.models.variable_adicional import VariableAdicional


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _cedula_unica(prefijo):
    return f"{prefijo}{uuid.uuid4().int % 10**7:07d}"


def test_no_rindieron_sin_token_retorna_401(client):
    r = client.get("/analitica/curso/1/no-rindieron")
    assert r.status_code == 401


def test_no_rindieron_curso_inexistente_retorna_404(client):
    r = client.get("/analitica/curso/999999/no-rindieron", headers={"X-Admin-Token": settings.admin_token})
    assert r.status_code == 404


def test_no_rindieron_separa_sin_nota_de_pendiente_resolver(client, db):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"TS R2 NoRindio {sufijo}")
    db.add(reg); db.flush()
    curso = Curso(codigo=f"NR-{sufijo}", nombre="CURSO NO RINDIO", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()

    # activo sin ninguna nota — debe caer en sin_notificar
    emp_sin_nota = Empleado(cedula=_cedula_unica("81"), nombre="SIN NOTA", regional_id=reg.id)
    db.add(emp_sin_nota); db.flush()
    db.add(VariableAdicional(empleado_id=emp_sin_nota.id, jefe_correo="jefe1@telconet.ec"))

    # activo con PENDIENTE_JUSTIFICACION — debe caer en pendientes_resolver
    emp_pendiente = Empleado(cedula=_cedula_unica("82"), nombre="PENDIENTE", regional_id=reg.id)
    db.add(emp_pendiente); db.flush()
    db.add(VariableAdicional(empleado_id=emp_pendiente.id, jefe_correo="jefe2@telconet.ec"))
    nota_pendiente = Nota(empleado_id=emp_pendiente.id, curso_id=curso.id, estado="PENDIENTE_JUSTIFICACION", tipo="REGULAR")
    db.add(nota_pendiente); db.flush()

    # activo que SI rindio — no debe aparecer en ninguna lista
    emp_rindio = Empleado(cedula=_cedula_unica("83"), nombre="SI RINDIO", regional_id=reg.id)
    db.add(emp_rindio); db.flush()
    db.add(Nota(empleado_id=emp_rindio.id, curso_id=curso.id, valor=Decimal("9.0"), estado="APROBADO", tipo="REGULAR"))

    # inactivo sin nota — no debe aparecer
    emp_inactivo = Empleado(cedula=_cedula_unica("84"), nombre="INACTIVO", regional_id=reg.id, inactivo=True)
    db.add(emp_inactivo); db.flush()

    db.flush()

    r = client.get(f"/analitica/curso/{curso.id}/no-rindieron", headers={"X-Admin-Token": settings.admin_token})
    assert r.status_code == 200
    body = r.json()

    cedulas_sin_notificar = {p["cedula"] for p in body["sin_notificar"]}
    cedulas_pendientes = {p["cedula"] for p in body["pendientes_resolver"]}

    assert cedulas_sin_notificar == {emp_sin_nota.cedula}
    assert cedulas_pendientes == {emp_pendiente.cedula}

    pendiente_data = next(p for p in body["pendientes_resolver"] if p["cedula"] == emp_pendiente.cedula)
    assert pendiente_data["nota_id"] == nota_pendiente.id
    assert pendiente_data["jefe_correo"] == "jefe2@telconet.ec"

    sin_notificar_data = next(p for p in body["sin_notificar"] if p["cedula"] == emp_sin_nota.cedula)
    assert sin_notificar_data["nota_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_no_rindieron.py -v`
Expected: FAIL — `404 Not Found` (la ruta no existe)

- [ ] **Step 3: Implementación mínima**

En `app/routers/analitica.py`, agrega a los imports existentes:

```python
from app.schemas.carga_notas import NoRindioOut, NoRindioPersona
```

Agrega el endpoint (después de `regional_dia_configurado`, antes de `convocatoria_preview`):

```python
@router.get("/curso/{curso_id}/no-rindieron", response_model=NoRindioOut)
def curso_no_rindieron(
    curso_id: int,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    """
    Activos de la regional del curso, separados en quienes no tienen
    ninguna nota (elegibles para notificar) y quienes ya tienen una nota
    PENDIENTE_JUSTIFICACION (novedad enviada, falta resolver el estado
    final). Deja al admin volver otro dia sin perder de vista a nadie.
    """
    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    activos = (
        db.query(Empleado)
        .options(joinedload(Empleado.variable_adicional))
        .filter(Empleado.regional_id == curso.regional_id, Empleado.inactivo.is_(False))
        .all()
    )
    notas_curso = db.query(Nota).filter(Nota.curso_id == curso_id).all()
    tienen_nota = {n.empleado_id for n in notas_curso}
    pendiente_por_empleado = {
        n.empleado_id: n for n in notas_curso if n.estado == "PENDIENTE_JUSTIFICACION"
    }

    sin_notificar: list[NoRindioPersona] = []
    pendientes_resolver: list[NoRindioPersona] = []

    for emp in activos:
        jefe_correo = emp.variable_adicional.jefe_correo if emp.variable_adicional else None
        if emp.id in pendiente_por_empleado:
            pendientes_resolver.append(NoRindioPersona(
                cedula=emp.cedula, nombre=emp.nombre, jefe_correo=jefe_correo,
                nota_id=pendiente_por_empleado[emp.id].id,
            ))
        elif emp.id not in tienen_nota:
            sin_notificar.append(NoRindioPersona(
                cedula=emp.cedula, nombre=emp.nombre, jefe_correo=jefe_correo, nota_id=None,
            ))

    return NoRindioOut(
        curso_id=curso.id, curso=curso.nombre,
        sin_notificar=sorted(sin_notificar, key=lambda p: p.nombre),
        pendientes_resolver=sorted(pendientes_resolver, key=lambda p: p.nombre),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_no_rindieron.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/analitica.py tests/test_no_rindieron.py
git commit -m "feat: endpoint GET /analitica/curso/{curso_id}/no-rindieron"
```

---

### Task 8: `mailer.py` — plantilla de correo de novedad

**Files:**
- Modify: `app/services/mailer.py`
- Test: `tests/test_mailer.py`

**Interfaces:**
- Produces: `construir_cuerpo_novedad(jefe_nombre: str | None, curso_nombre: str, empleados: list[dict]) -> str`, donde cada `empleados` item es `{"nombre": str}`. Consumido por Task 9.

- [ ] **Step 1: Write the failing test**

Agrega a `tests/test_mailer.py`:

```python
from app.services.mailer import construir_cuerpo_novedad
```

(Agrégalo a la línea de import existente `from app.services.mailer import (...)`, no como línea aparte — edita el bloque de import para incluir `construir_cuerpo_novedad`.)

Al final del archivo:

```python
def test_construir_cuerpo_novedad_incluye_jefe_curso_y_empleados():
    html = construir_cuerpo_novedad(
        "MARIA JEFA", "ESTANDAR DE SOPORTE",
        [{"nombre": "PEREZ JUAN"}, {"nombre": "GOMEZ ANA"}],
    )
    assert "MARIA JEFA" in html
    assert "ESTANDAR DE SOPORTE" in html
    assert "PEREZ JUAN" in html
    assert "GOMEZ ANA" in html
    assert "Total:" in html
    assert "<strong>2</strong>" in html


def test_construir_cuerpo_novedad_sin_jefe_nombre_usa_generico():
    html = construir_cuerpo_novedad(None, "CURSO X", [{"nombre": "X"}])
    assert "Jefe" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_mailer.py -k construir_cuerpo_novedad -v`
Expected: FAIL — `ImportError: cannot import name 'construir_cuerpo_novedad'`

- [ ] **Step 3: Implementación mínima**

Agrega a `app/services/mailer.py`, después de `construir_cuerpo_recopilatorio`:

```python
def construir_cuerpo_novedad(jefe_nombre: str | None, curso_nombre: str, empleados: list[dict]) -> str:
    """empleados: [{"nombre": str}] — colaboradores sin nota en el curso"""
    filas = "".join(
        f'<tr><td style="padding:10px 12px;border-bottom:1px solid #eee;color:{_COLOR_TEXT};font-size:14px;">{html.escape(e["nombre"])}</td></tr>'
        for e in empleados
    )
    contenido = f"""
<p style="color:{_COLOR_TEXT};font-size:14px;line-height:1.6;margin:0 0 12px 0;">Estimado/a <strong>{html.escape(jefe_nombre) if jefe_nombre else "Jefe"}</strong>,</p>
<p style="color:{_COLOR_TEXT};font-size:14px;line-height:1.6;margin:0 0 16px 0;">Los siguientes colaboradores de su equipo no registran nota en la capacitación <strong>{html.escape(curso_nombre)}</strong>. Por favor indíquenos qué ocurrió (falta injustificada, falta justificada, no fue convocado, vacaciones, etc.):</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
<tr style="background-color:{_COLOR_HEADER};">
<th style="padding:10px 12px;color:{_COLOR_ACCENT};font-size:13px;text-align:left;">Colaborador</th>
</tr>
{filas}
</table>
<p style="color:{_COLOR_TEXT};font-size:14px;margin:16px 0 0 0;">Total: <strong>{len(empleados)}</strong> colaborador(es).</p>
"""
    return _wrap_email("Novedad de Capacitación — Su Equipo", contenido)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_mailer.py -v`
Expected: todos pasan, incluyendo los 2 nuevos.

- [ ] **Step 5: Commit**

```bash
git add app/services/mailer.py tests/test_mailer.py
git commit -m "feat: plantilla de correo de novedad para colaboradores sin nota"
```

---

### Task 9: Endpoint `POST /admin/curso/{curso_id}/enviar-novedad`

**Files:**
- Modify: `app/routers/admin.py`
- Test: `tests/test_novedades_endpoint.py`

**Interfaces:**
- Consumes: `EnviarNovedadIn`/`EnviarNovedadOut` (Task 5), `construir_cuerpo_novedad` (Task 8), `enviar_correo` (existente), `verify_admin`.
- Produces: endpoint `POST /admin/curso/{curso_id}/enviar-novedad`. Consumido por Task 13 (frontend).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_novedades_endpoint.py`:

```python
import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from app.config import settings
from app.models import Regional, Empleado, Curso, Nota
from app.models.variable_adicional import VariableAdicional


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _cedula_unica(prefijo):
    return f"{prefijo}{uuid.uuid4().int % 10**7:07d}"


def _curso_con_activos_sin_nota(db, n=2, jefe_correo="jefe@telconet.ec"):
    sufijo = uuid.uuid4().hex[:8]
    reg = Regional(nombre=f"TS R2 Novedad {sufijo}")
    db.add(reg); db.flush()
    curso = Curso(codigo=f"NOV-{sufijo}", nombre="CURSO NOVEDAD", tipo="VIRTUAL",
                  mes="ENERO", anio=2026, regional_id=reg.id)
    db.add(curso); db.flush()

    empleados = []
    for i in range(n):
        cedula = _cedula_unica(f"9{i}")
        emp = Empleado(cedula=cedula, nombre=f"SIN NOTA {i}", regional_id=reg.id)
        db.add(emp); db.flush()
        db.add(VariableAdicional(empleado_id=emp.id, jefe_correo=jefe_correo, jefe_inmediato="JEFE X"))
        empleados.append(emp)
    db.flush()
    return curso, empleados


def test_enviar_novedad_sin_token_retorna_401(client):
    r = client.post("/admin/curso/1/enviar-novedad", json={"cedulas": [], "modo_prueba": True, "correo_prueba": "x@x.ec"})
    assert r.status_code == 401


def test_enviar_novedad_modo_prueba_sin_correo_prueba_retorna_400(client, db):
    curso, _ = _curso_con_activos_sin_nota(db, n=1)
    r = client.post(
        f"/admin/curso/{curso.id}/enviar-novedad",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [], "modo_prueba": True},
    )
    assert r.status_code == 400


@patch("app.services.mailer.smtplib.SMTP_SSL")
def test_enviar_novedad_agrupa_por_jefe_y_crea_pendiente_justificacion(mock_smtp_ssl, client, db):
    mock_server = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = mock_server

    curso, empleados = _curso_con_activos_sin_nota(db, n=2, jefe_correo="jefeunico@telconet.ec")

    r = client.post(
        f"/admin/curso/{curso.id}/enviar-novedad",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [e.cedula for e in empleados], "modo_prueba": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["notificados"]) == {e.cedula for e in empleados}
    assert body["recopilatorios_enviados"] == ["jefeunico@telconet.ec"]

    # un solo correo (agrupado), no uno por persona
    assert mock_server.sendmail.call_count == 1
    sendmail_args = mock_server.sendmail.call_args[0]
    assert sendmail_args[1] == ["jefeunico@telconet.ec"]

    for emp in empleados:
        nota = db.query(Nota).filter_by(empleado_id=emp.id, curso_id=curso.id).first()
        assert nota is not None
        assert nota.estado == "PENDIENTE_JUSTIFICACION"


@patch("app.services.mailer.smtplib.SMTP_SSL")
def test_enviar_novedad_modo_prueba_redirige_y_no_crea_nota(mock_smtp_ssl, client, db):
    mock_server = MagicMock()
    mock_smtp_ssl.return_value.__enter__.return_value = mock_server

    curso, empleados = _curso_con_activos_sin_nota(db, n=1, jefe_correo="jeferreal@telconet.ec")

    r = client.post(
        f"/admin/curso/{curso.id}/enviar-novedad",
        headers={"X-Admin-Token": settings.admin_token},
        json={"cedulas": [empleados[0].cedula], "modo_prueba": True, "correo_prueba": "prueba@telconet.ec"},
    )
    assert r.status_code == 200

    sendmail_args = mock_server.sendmail.call_args[0]
    assert sendmail_args[1] == ["prueba@telconet.ec"]

    # en modo prueba NO se crea la nota PENDIENTE_JUSTIFICACION (no es un aviso real)
    nota = db.query(Nota).filter_by(empleado_id=empleados[0].id, curso_id=curso.id).first()
    assert nota is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_novedades_endpoint.py -v`
Expected: FAIL — `404 Not Found`

- [ ] **Step 3: Implementación mínima**

En `app/routers/admin.py`, agrega a los imports:

```python
from app.schemas.carga_notas import (
    CargarCursoOut,
    EmpleadoNuevoIn,
    EmpleadoNuevoOut,
    EnviarNovedadIn,
    EnviarNovedadOut,
)
from app.services.mailer import construir_cuerpo_novedad
```

(Amplía la línea `from app.schemas.carga_notas import (...)` del Task 5 con las dos clases nuevas; agrega `construir_cuerpo_novedad` a la línea de import existente `from app.services.mailer import (...)`.)

Agrega el endpoint (después de `crear_empleado`):

```python
@router.post("/curso/{curso_id}/enviar-novedad", response_model=EnviarNovedadOut)
def enviar_novedad(
    curso_id: int,
    body: EnviarNovedadIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if body.modo_prueba and not body.correo_prueba:
        raise HTTPException(status_code=400, detail="correo_prueba es requerido en modo_prueba")

    curso = db.query(Curso).filter_by(id=curso_id).first()
    if not curso:
        raise HTTPException(status_code=404, detail="Curso no encontrado")

    por_jefe: dict[str, dict] = {}
    for cedula in body.cedulas:
        emp = db.query(Empleado).filter_by(cedula=cedula, regional_id=curso.regional_id).first()
        if not emp:
            continue
        va = db.query(VariableAdicional).filter_by(empleado_id=emp.id).first()
        if not va or not va.jefe_correo:
            continue
        grupo = por_jefe.setdefault(va.jefe_correo, {"jefe_inmediato": va.jefe_inmediato, "empleados": []})
        grupo["empleados"].append({"cedula": emp.cedula, "nombre": emp.nombre, "empleado_id": emp.id})

    notificados: list[str] = []
    recopilatorios_enviados: list[str] = []

    for jefe_correo, info in por_jefe.items():
        destino = body.correo_prueba if body.modo_prueba else jefe_correo
        asunto = f"Novedad de Capacitación — Su Equipo{' [PRUEBA]' if body.modo_prueba else ''}"
        cuerpo = construir_cuerpo_novedad(info["jefe_inmediato"], curso.nombre, info["empleados"])
        try:
            enviar_correo(destino, asunto, cuerpo)
        except Exception:
            logger.exception("Fallo al enviar novedad a jefe_correo=%s", jefe_correo)
            continue

        recopilatorios_enviados.append(jefe_correo)
        if not body.modo_prueba:
            for e in info["empleados"]:
                stmt = (
                    insert(Nota)
                    .values(
                        empleado_id=e["empleado_id"], curso_id=curso_id,
                        estado="PENDIENTE_JUSTIFICACION", tipo="REGULAR", convocatoria=1,
                    )
                    .on_conflict_do_nothing(constraint="uq_nota_empleado_curso_tipo_conv")
                )
                db.execute(stmt)
                notificados.append(e["cedula"])
    db.commit()

    return EnviarNovedadOut(notificados=notificados, recopilatorios_enviados=recopilatorios_enviados)
```

Agrega el import de `insert` (necesario para `on_conflict_do_nothing`) junto a los demás imports de `app/routers/admin.py`:

```python
from sqlalchemy.dialects.postgresql import insert
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_novedades_endpoint.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add app/routers/admin.py tests/test_novedades_endpoint.py
git commit -m "feat: endpoint POST /admin/curso/{curso_id}/enviar-novedad"
```

---

### Task 10: Endpoint `PATCH /admin/notas/{nota_id}/resolver`

**Files:**
- Modify: `app/routers/admin.py`
- Test: `tests/test_novedades_endpoint.py`

**Interfaces:**
- Consumes: `ResolverNotaIn` (Task 5), `verify_admin`.
- Produces: endpoint `PATCH /admin/notas/{nota_id}/resolver`. Consumido por Task 13 (frontend).

- [ ] **Step 1: Write the failing tests**

Agrega a `tests/test_novedades_endpoint.py`:

```python
def test_resolver_nota_sin_token_retorna_401(client):
    r = client.patch("/admin/notas/1/resolver", json={"estado": "FALTA_INJUSTIFICADA"})
    assert r.status_code == 401


def test_resolver_nota_estado_invalido_retorna_400(client, db):
    curso, empleados = _curso_con_activos_sin_nota(db, n=1)
    nota = Nota(empleado_id=empleados[0].id, curso_id=curso.id, estado="PENDIENTE_JUSTIFICACION", tipo="REGULAR")
    db.add(nota); db.flush()

    r = client.patch(
        f"/admin/notas/{nota.id}/resolver",
        headers={"X-Admin-Token": settings.admin_token},
        json={"estado": "ESTADO_INVENTADO"},
    )
    assert r.status_code == 400


def test_resolver_nota_actualiza_estado_in_place(client, db):
    curso, empleados = _curso_con_activos_sin_nota(db, n=1)
    nota = Nota(empleado_id=empleados[0].id, curso_id=curso.id, estado="PENDIENTE_JUSTIFICACION", tipo="REGULAR")
    db.add(nota); db.flush()
    nota_id = nota.id

    r = client.patch(
        f"/admin/notas/{nota_id}/resolver",
        headers={"X-Admin-Token": settings.admin_token},
        json={"estado": "FALTA_INJUSTIFICADA"},
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "FALTA_INJUSTIFICADA"

    actualizada = db.query(Nota).filter_by(id=nota_id).first()
    assert actualizada.estado == "FALTA_INJUSTIFICADA"
    assert actualizada.valor is None


def test_resolver_nota_que_no_esta_pendiente_retorna_400(client, db):
    curso, empleados = _curso_con_activos_sin_nota(db, n=1)
    nota = Nota(empleado_id=empleados[0].id, curso_id=curso.id, valor=Decimal("9.0"),
                estado="APROBADO", tipo="REGULAR")
    db.add(nota); db.flush()

    r = client.patch(
        f"/admin/notas/{nota.id}/resolver",
        headers={"X-Admin-Token": settings.admin_token},
        json={"estado": "FALTA_INJUSTIFICADA"},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_novedades_endpoint.py -k resolver_nota -v`
Expected: FAIL — `404 Not Found`

- [ ] **Step 3: Implementación mínima**

En `app/routers/admin.py`, la línea de import de `app.schemas.carga_notas` (la del Task 9) queda así, con `ResolverNotaIn` agregado:

```python
from app.schemas.carga_notas import (
    CargarCursoOut,
    EmpleadoNuevoIn,
    EmpleadoNuevoOut,
    EnviarNovedadIn,
    EnviarNovedadOut,
    ResolverNotaIn,
)
```

Agrega la constante + endpoint al final del archivo:

```python
_ESTADOS_RESOLUCION_VALIDOS = {
    "FALTA_INJUSTIFICADA", "FALTA_JUSTIFICADA", "NO_APLICA",
    "VACACIONES", "EXONERADO", "ASISTENCIA",
}


@router.patch("/notas/{nota_id}/resolver")
def resolver_nota(
    nota_id: int,
    body: ResolverNotaIn,
    _: str = Depends(verify_admin),
    db: Session = Depends(get_db),
):
    if body.estado not in _ESTADOS_RESOLUCION_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"estado debe ser uno de: {', '.join(sorted(_ESTADOS_RESOLUCION_VALIDOS))}",
        )

    nota = db.query(Nota).filter_by(id=nota_id).first()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota no encontrada")
    if nota.estado != "PENDIENTE_JUSTIFICACION":
        raise HTTPException(status_code=400, detail="Solo se pueden resolver notas en estado PENDIENTE_JUSTIFICACION")

    nota.estado = body.estado
    db.commit()
    return {"id": nota.id, "estado": nota.estado}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_novedades_endpoint.py -v`
Expected: 8 passed

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -q`
Expected: todos pasan salvo el fallo preexistente ya conocido (`test_calculadora.py`).

- [ ] **Step 6: Commit**

```bash
git add app/routers/admin.py tests/test_novedades_endpoint.py
git commit -m "feat: endpoint PATCH /admin/notas/{nota_id}/resolver"
```

---

### Task 11: Frontend — `api_client.py`, nuevas funciones

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\api_client.py`

**Interfaces:**
- Consumes: endpoints de Tasks 5-10.
- Produces: `_post_file()`, `cargar_curso()`, `crear_empleado()`, `get_no_rindieron()`, `enviar_novedad()`, `resolver_nota()`, `get_cursos()` — todas consumidas por Tasks 12-13.

- [ ] **Step 1: Agregar el helper `_post_file` y las nuevas funciones**

En `api_client.py`, agrega después de `_get_bytes` (antes de `_write`):

```python
def _post_file(path: str, files: dict, params: dict = None) -> dict | list | None:
    headers = {"X-Admin-Token": st.secrets.get("ADMIN_TOKEN", "")}
    try:
        r = requests.post(f"{_base()}{path}", files=files, params=params, headers=headers, timeout=120)
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
```

Agrega al final del archivo:

```python
def get_cursos(anio: Optional[int] = None, regional: Optional[str] = None) -> list[dict]:
    params = {}
    if anio:     params["anio"] = anio
    if regional: params["regional"] = regional
    return _get("/cursos/", params) or []


def cargar_curso(
    archivo_bytes: bytes,
    nombre_archivo: str,
    modo: str,
    *,
    codigo: Optional[str] = None,
    nombre: Optional[str] = None,
    tipo: Optional[str] = None,
    mes: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    anio: Optional[int] = None,
    regional: Optional[str] = None,
    curso_id: Optional[int] = None,
    convocatoria: Optional[int] = None,
) -> dict | None:
    params: dict = {"modo": modo}
    if modo == "nuevo":
        params.update({
            "codigo": codigo, "nombre": nombre, "tipo": tipo, "mes": mes,
            "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin,
            "anio": anio, "regional": regional,
        })
    else:
        params.update({"curso_id": curso_id, "convocatoria": convocatoria})
    files = {"archivo": (nombre_archivo, archivo_bytes, "text/csv")}
    return _post_file("/admin/cargar-curso", files=files, params=params)


def crear_empleado(payload: dict) -> dict | None:
    return _post("/admin/empleados", payload)


def get_no_rindieron(curso_id: int) -> dict | None:
    return _get_admin(f"/analitica/curso/{curso_id}/no-rindieron")


def enviar_novedad(
    curso_id: int,
    cedulas: list[str],
    modo_prueba: bool,
    correo_prueba: Optional[str] = None,
) -> dict | None:
    body = {"cedulas": cedulas, "modo_prueba": modo_prueba}
    if correo_prueba:
        body["correo_prueba"] = correo_prueba
    return _post(f"/admin/curso/{curso_id}/enviar-novedad", body)


def resolver_nota(nota_id: int, estado: str) -> dict | None:
    return _patch(f"/admin/notas/{nota_id}/resolver", {"estado": estado})
```

- [ ] **Step 2: Verificar que el archivo no tiene errores de sintaxis**

Run: `python -c "import ast; ast.parse(open('api_client.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add api_client.py
git commit -m "feat: funciones de api_client para carga de notas y novedades"
```

---

### Task 12: Frontend — `ui/administracion.py`, sección "Carga de curso" (Modo A/B + alta de empleado)

**Files:**
- Create: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\ui\administracion.py`

**Interfaces:**
- Consumes: `api.cargar_curso()`, `api.crear_empleado()`, `api.get_cursos()` (Task 11).
- Produces: `render_tab_administracion(anio: int) -> None`, consumido por Task 14 (`app.py`).

- [ ] **Step 1: Crear el archivo con la sección de carga**

Create `ui/administracion.py`:

```python
import streamlit as st

import api_client as api

TIPOS_CURSO = ["PRESENCIAL", "VIRTUAL", "ZOOM"]
MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
         "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]


def render_tab_administracion(anio: int) -> None:
    st.title("🛠️ Administración")

    _seccion_carga_curso(anio)
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
        metadata["curso_id"] = opciones[seleccionado]
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
        st.success(f"✅ Nuevos: {resultado['nuevos']} · Actualizados: {resultado['actualizados']}")
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


def _seccion_novedades(anio: int) -> None:
    st.markdown("### 📋 Novedades — quiénes no han rendido")
    st.caption("Placeholder — se completa en la siguiente tarea del plan.")
```

- [ ] **Step 2: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('ui/administracion.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/administracion.py
git commit -m "feat: seccion Administracion - carga de curso y alta de empleado nuevo"
```

---

### Task 13: Frontend — `ui/administracion.py`, sección "Novedades"

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\ui\administracion.py`

**Interfaces:**
- Consumes: `api.get_cursos()`, `api.get_no_rindieron()`, `api.enviar_novedad()`, `api.resolver_nota()` (Task 11).

- [ ] **Step 1: Reemplazar el placeholder de `_seccion_novedades`**

En `ui/administracion.py`, reemplaza:

```python
def _seccion_novedades(anio: int) -> None:
    st.markdown("### 📋 Novedades — quiénes no han rendido")
    st.caption("Placeholder — se completa en la siguiente tarea del plan.")
```

por:

```python
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
```

- [ ] **Step 2: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('ui/administracion.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add ui/administracion.py
git commit -m "feat: seccion Novedades en Administracion (notificar jefes + resolver estado)"
```

---

### Task 14: Frontend — registrar la sección en `app.py`

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\app.py`

**Interfaces:**
- Consumes: `render_tab_administracion` (Task 12/13).

- [ ] **Step 1: Registrar la sección**

En `app.py`, agrega el import (junto a los demás `from ui...`):

```python
from ui.administracion import render_tab_administracion
```

Actualiza el diccionario `SECCIONES`:

```python
SECCIONES = {
    "👥 Colaboradores": render_tab_colaboradores,
    "📈 Analítica": render_tab_analitica,
    "📧 Convocatoria": render_tab_convocatoria,
    "📥 Reportería": render_tab_reporteria,
    "🛠️ Administración": render_tab_administracion,
}
```

- [ ] **Step 2: Verificar sintaxis**

Run: `python -c "import ast; ast.parse(open('app.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: registrar seccion Administracion en la navegacion"
```

---

### Task 15: Verificación end-to-end

**Files:** ninguno (solo verificación manual/scripted, sin cambios de código salvo que se encuentre un bug real).

- [ ] **Step 1: Correr la suite completa del backend**

Run: `cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && pytest -q`
Expected: todos los tests pasan salvo el fallo preexistente conocido en `test_calculadora.py` (no relacionado a este trabajo). Si aparece cualquier otro fallo, es una regresión real — investigar y corregir antes de continuar.

- [ ] **Step 2: Reiniciar el backend limpiamente (cuidado con el huérfano de Windows)**

Antes de reiniciar, buscar y matar cualquier proceso `multiprocessing-fork` huérfano del backend anterior:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn.exe*' -or $_.CommandLine -like '*multiprocessing-fork*' } | Select-Object ProcessId, ParentProcessId
```

Matar todos los PID de esa cadena (`Stop-Process -Id <pid1>,<pid2>,... -Force`), luego iniciar de nuevo:

```bash
cd "C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api" && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Esperar unos segundos y confirmar que el endpoint nuevo aparece en el esquema (no solo que el puerto responde — el huérfano puede responder con código viejo):

```bash
curl -s http://localhost:8000/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print('/admin/cargar-curso' in d['paths'])"
```

Expected: `True`. Si es `False` después de un restart aparentemente exitoso, revisar de nuevo por un proceso `multiprocessing-fork` huérfano y matarlo.

- [ ] **Step 3: Smoke test con el CSV real de ejemplo, en modo curso nuevo, contra datos reales**

```bash
ADMIN_TOKEN=$(python -c "from app.config import settings; print(settings.admin_token)")
curl -s -X POST \
  "http://localhost:8000/admin/cargar-curso?modo=nuevo&codigo=ES26-TEST&nombre=ESTANDAR%20DE%20SOPORTE%20TEST&tipo=VIRTUAL&mes=ENERO&fecha_inicio=2026-01-06&fecha_fin=2026-01-18&anio=2026&regional=Quito" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "archivo=@C:/Users/USUARIO/Desktop/TelcoU DB new/2026/Quito/ES26-EVALUACIÓN- ESTÁNDAR DE SOPORTE-calificaciones.csv.xls" \
  | python -m json.tool
```

Usar un `codigo` de prueba distinto (`ES26-TEST`) para no chocar con el curso real `ES26` ya cargado. Confirmar que la respuesta trae `nuevos`/`actualizados`/`sin_match` con valores razonables (dado que el CSV tiene 746 filas de datos, la mayoría debería tener match ya que son las mismas personas del curso real `ES26`).

- [ ] **Step 4: Verificar `no-rindieron` con datos reales**

```bash
curl -s "http://localhost:8000/analitica/curso/<CURSO_ID_DEL_PASO_ANTERIOR>/no-rindieron" \
  -H "X-Admin-Token: $ADMIN_TOKEN" | python -m json.tool
```

Confirmar que `sin_notificar` no está vacío (dado que el curso de prueba `ES26-TEST` es nuevo, todos los activos de Quito que no estén en las 746 filas del CSV deberían aparecer ahí) y que `pendientes_resolver` está vacío (todavía no se envió ninguna novedad).

- [ ] **Step 5: Verificación en el dashboard vía Playwright**

Reiniciar también el dashboard (mismo cuidado con procesos huérfanos, aplica igual a Streamlit). Con ambos servidores arriba:

```javascript
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 1200 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  await page.goto('http://localhost:8501', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  const adminRadio = page.locator('label', { hasText: 'Administración' }).first();
  await adminRadio.click();
  await page.waitForTimeout(3000);

  const bodyText = await page.locator('body').innerText();
  console.log('HAS_CARGA_TITLE:', bodyText.includes('Carga de curso desde CSV'));
  console.log('HAS_NOVEDADES_TITLE:', bodyText.includes('Novedades'));
  console.log('ERRORS:', JSON.stringify(errors));
  await page.screenshot({ path: 'administracion_check.png', fullPage: true });
  await browser.close();
})();
```

Expected: `HAS_CARGA_TITLE: true`, `HAS_NOVEDADES_TITLE: true`, `ERRORS: []`. Revisar el screenshot para confirmar que no hay excepciones de Streamlit visibles en pantalla.

- [ ] **Step 6: Limpieza de los datos de prueba del Step 3**

El curso `ES26-TEST` y sus notas quedaron en la base de datos real tras el smoke test. Decidir con el usuario si se eliminan (`DELETE FROM notas WHERE curso_id = <id>; DELETE FROM cursos WHERE id = <id>;`) o se dejan como evidencia de la verificación — **no borrar sin confirmar primero**, dado que es una base de datos con datos reales en uso activo.

---

### Task 16: Documentación

**Files:**
- Modify: `C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1\docs\README.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\docs\TABS.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\docs\ARQUITECTURA.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\docs\API_CLIENTE.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU Dashboard\TelcoU Dashboard.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU DB API\docs\API_ENDPOINTS.md`
- Modify: `C:\Users\USUARIO\OneDrive\Documents\Obsidian Vault\TelcoU DB API\TelcoU DB API.md`

- [ ] **Step 1: `dashboard-telcou-s1/docs/README.md`**

Agregar `ui/administracion.py` a la estructura de archivos, actualizar "4 secciones" → "5 secciones" en la nota de Navegación, y agregar una sección `### 🛠️ Administración (nuevo — 2026-07-13)` describiendo los 3 flujos (carga de curso, alta de empleado, novedades), el formato del CSV de Moodle, y el nuevo estado `PENDIENTE_JUSTIFICACION`. Agregar las 6 funciones nuevas de `api_client.py` a la tabla de funciones disponibles.

- [ ] **Step 2: Vault "TelcoU Dashboard" — `TABS.md`, `ARQUITECTURA.md`, `API_CLIENTE.md`, índice**

`TABS.md`: nueva sección `## 🛠️ Administración` con el mismo nivel de detalle que las secciones existentes (Carga de curso, Alta de empleado, Novedades — incluyendo la distinción sin_notificar/pendientes_resolver y por qué existe). `ARQUITECTURA.md`: agregar `ui/administracion.py` a la estructura de archivos, actualizar conteo de secciones. `API_CLIENTE.md`: documentar las 6 funciones nuevas, incluyendo el nuevo helper `_post_file()`. Índice (`TelcoU Dashboard.md`): agregar fila a la tabla de secciones y entradas al historial de desarrollo.

- [ ] **Step 3: Vault "TelcoU DB API" — `API_ENDPOINTS.md`, índice**

`API_ENDPOINTS.md`: documentar los 5 endpoints nuevos (`POST /admin/cargar-curso`, `POST /admin/empleados`, `GET /analitica/curso/{curso_id}/no-rindieron`, `POST /admin/curso/{curso_id}/enviar-novedad`, `PATCH /admin/notas/{nota_id}/resolver`) con el mismo formato que los endpoints existentes (query params, ejemplos de respuesta, comportamiento en modo prueba). Documentar el nuevo estado `PENDIENTE_JUSTIFICACION` y su rol en `NECESITA_SUPLETORIO`. Índice (`TelcoU DB API.md`): agregar filas a la tabla de endpoints y al historial/pendientes.

- [ ] **Step 4: Commit (solo el repo dashboard-telcou-s1 — los vaults de Obsidian no son un repo git)**

```bash
cd "C:\Users\USUARIO\Desktop\DesarrollosRodri\dashboard-telcou-s1"
git add docs/README.md
git commit -m "docs: documentar seccion Administracion - carga de notas por CSV"
```

---

## Self-Review

**Cobertura del spec:** Alcance (§1) → Tasks 1-14. Formato CSV (§2) → Task 2. Modelo de datos sin migraciones (§3) → Task 1 (PENDIENTE_JUSTIFICACION), verificado que no hace falta ninguna migración en ningún task. Flujo 1 (§4) → Tasks 2-5. Flujo 2 (§5) → Tasks 5-6, 12. Flujo 3 (§6) → Tasks 7-10, 13. Endpoints (§7) → Tasks 5-10 (los 5 endpoints, más `no-rindieron` cubierto en Task 7). UI (§8) → Tasks 12-14. Seguridad (§9) → `X-Admin-Token` en cada endpoint de escritura (Tasks 5, 6, 9, 10) y en la consulta de novedades (Task 7); modo prueba obligatorio (Task 9). Testing (§10) → cubierto en cada task. Verificación (§11) → Task 15.

**Consistencia de tipos:** `parsear_csv_moodle()` (Task 2) devuelve `{cedula, nombre, area, correo, nota}` — usado igual en `cargar_curso_nuevo` (Task 3) y `cargar_supletorio` (Task 4). `CargarCursoOut` (Task 5) coincide con las claves devueltas por ambas funciones de servicio. `NoRindioPersona.nota_id` es `None` para "sin_notificar" y un `int` para "pendientes_resolver" — verificado consistente entre Task 7 (backend) y Task 13 (frontend, usa `nota_id` como `key` de los widgets de Streamlit). `EnviarNovedadOut.notificados` es `list[str]` (cédulas) en el schema (Task 5) y en la implementación (Task 9) — corregido durante el diseño de Task 9 para no devolver `empleado_id` por error.
