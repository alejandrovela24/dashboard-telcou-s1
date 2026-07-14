# Convocatoria por Curso + Atajo "Marcar NA" al Cargar — Diseño

**Fecha:** 2026-07-14
**Repos afectados:** `telcou-api` (backend, `C:\Users\USUARIO\Desktop\TelcoU DB new\telcou-api`) y `dashboard-telcou-s1` (frontend, este repo)
**Depende de:** feature "Administración — Carga de Notas por CSV" (`2026-07-13-administracion-carga-notas-design.md`), ya completa y en producción.

## 1. Alcance

Dos cambios de comportamiento sobre la sección **🛠️ Administración**, motivados por un caso real: el cronograma de capacitaciones tiene varias fases, y el admin quiere poder cargar el curso de la siguiente fase (sus notas deben quedar visibles en Analítica/Colaboradores de inmediato) sin que eso dispare de forma prematura el proceso de **Convocatoria** (feature separada, ya en producción, que envía correos de supletorio).

1. **Convocatoria por curso** — un curso recién cargado no debe aparecer en la vista previa ni en el envío real de Convocatoria hasta que el admin decida explícitamente que ya le toca su ronda de supletorio. Los cursos ya cargados hoy no cambian de comportamiento.
2. **Atajo "Marcar NA"** — al cargar un curso nuevo, permitir marcar de inmediato como `NO_APLICA` a quienes el admin ya sabe que no fueron convocados a ese curso, sin pasar por el ciclo completo de Novedades (notificar al jefe → esperar → resolver).

Fuera de alcance: activación automática por fecha (`fecha_fin + X días`) — el admin la rechazó explícitamente, prefiere control manual total. Fuera de alcance también: cualquier cambio a cómo `cargar_supletorio` (Modo B) selecciona notas REGULAR — un curso con `convocatoria_habilitada=false` sigue aceptando cargas de supletorio con total normalidad; el campo nuevo solo afecta si el curso aparece en la lista de gente a convocar.

## 2. Modelo de datos — con migración

Nuevo campo en `Curso`:

```python
convocatoria_habilitada = Column(Boolean, nullable=False, default=False, server_default=text("true"))
```

- **`server_default=text("true")`** — aplicado por la migración de Alembic (`ALTER TABLE cursos ADD COLUMN convocatoria_habilitada BOOLEAN NOT NULL DEFAULT true`). Esto retropuebla **todos los cursos ya existentes** con `true`: cero cambio de comportamiento para lo que ya está cargado hoy.
- **`default=False`** — valor a nivel de aplicación (Python/SQLAlchemy) que se usa cuando el ORM/Core arma un `INSERT` sin especificar el campo explícitamente. Todo curso creado de aquí en adelante vía `cargar_curso_nuevo()` nace con `convocatoria_habilitada=False`.
- El `on_conflict_do_update` de `cargar_curso_nuevo()` (recarga de un curso ya existente, mismo código+año+regional) **no incluye este campo en su `set_={...}`** — recargar el CSV de un curso nunca resetea ni toca este valor, se preserva lo que el admin haya decidido.

## 3. Filtro en Convocatoria

`supletorios_pendientes_data()` (`app/services/convocatoria.py`) — la única función detrás tanto de `GET /analitica/convocatoria-preview` como de `POST /admin/enviar-convocatoria` — agrega un filtro a su query existente:

```python
.filter(Nota.tipo == "REGULAR", Curso.anio == anio, Empleado.inactivo.is_(False), Curso.convocatoria_habilitada.is_(True))
```

Nada más de la función cambia. Un curso con `convocatoria_habilitada=False` simplemente no contribuye ninguna fila a la lista de pendientes de supletorio — ni en la vista previa, ni en el envío real — hasta que se active.

## 4. Panel "Convocatoria por curso" (nuevo, en Administración)

Nueva subsección en `ui/administracion.py`, entre "Carga de curso" y "Novedades". Lista los cursos del año seleccionado (reusa `GET /cursos/`, que ahora incluye `convocatoria_habilitada` en la respuesta) con un switch por curso.

**Endpoint nuevo:** `PATCH /admin/curso/{curso_id}/convocatoria-habilitada`

```json
{ "habilitada": true }
```

Actualiza el campo in place. Protegido con `X-Admin-Token`. 404 si el curso no existe.

**Cambio en `CursoOut`** (`app/schemas/curso.py`): se agrega `convocatoria_habilitada: bool`. Este schema ya es usado por múltiples pantallas (Analítica, Convocatoria, los selectores de curso en Administración) — agregar un campo es compatible hacia atrás, ningún consumidor existente se rompe.

## 5. Atajo "Marcar NA" al cargar un curso nuevo

Justo después de una carga exitosa en Modo A ("Curso nuevo"), la pantalla de Carga de curso agrega una sección: **"Activos de [regional] sin nota en este curso"** — mismo dato que ya calcula `sin_notificar` en `GET /analitica/curso/{curso_id}/no-rindieron` (reutilizado tal cual, sin endpoint de lectura nuevo), mostrado inline con checkboxes (sin marcar por defecto — es una acción deliberada, no la acción "normal" como en Novedades) y un botón **"Marcar NA"**.

**Endpoint nuevo:** `POST /admin/curso/{curso_id}/marcar-na`

```json
{ "cedulas": ["1723555437", "0503422164"] }
```

Por cada cédula: crea `Nota(estado="NO_APLICA", tipo="REGULAR", convocatoria=1, valor=None)` directamente — sin correo, sin `PENDIENTE_JUSTIFICACION` intermedio. Usa `ON CONFLICT (empleado_id, curso_id, tipo, convocatoria) DO NOTHING` (mismo patrón defensivo que `enviar_novedad`) para no sobreescribir una nota real si por algún motivo ya existiera una. Respuesta: `{"marcados": ["1723555437", "0503422164"]}` — solo las cédulas cuyo `INSERT` realmente ocurrió (mismo criterio de precisión que el fix aplicado a `enviar_novedad` en la revisión final de la feature anterior).

Quien no se marca en esta pantalla sigue su camino normal: aparecerá después en Novedades (`sin_notificar`) para el flujo completo de notificar al jefe, exactamente como funciona hoy. `NO_APLICA` no está en `NECESITA_SUPLETORIO`, así que estas personas no generan pendiente de supletorio, sin importar el estado de `convocatoria_habilitada` de ese curso.

## 6. Endpoints nuevos (telcou-api)

Todos requieren `X-Admin-Token` (`Depends(verify_admin)`), mismo mecanismo que el resto de Administración.

| Método | Ruta | Qué hace |
|---|---|---|
| `PATCH` | `/admin/curso/{curso_id}/convocatoria-habilitada` | `{habilitada: bool}` — activa/desactiva si el curso cuenta para Convocatoria |
| `POST` | `/admin/curso/{curso_id}/marcar-na` | `{cedulas: list[str]}` — crea `Nota(estado="NO_APLICA")` directo para cada una, sin pasar por Novedades |

Cambio en endpoint existente: `GET /cursos/` ahora incluye `convocatoria_habilitada` en cada `CursoOut`.

## 7. UI (dashboard-telcou-s1)

`ui/administracion.py` gana una subsección nueva y una extensión a la existente:

- **Convocatoria por curso** (nueva, entre Carga de curso y Novedades): tabla de cursos del año con un `st.toggle` por fila, llamando a `api.set_convocatoria_habilitada(curso_id, habilitada)`.
- **Carga de curso** (extendida): tras una carga exitosa en Modo A, se agrega la sección "Activos sin nota en este curso" con checkboxes + botón "Marcar NA", llamando a `api.marcar_na(curso_id, cedulas)`.

`api_client.py` gana dos funciones: `set_convocatoria_habilitada(curso_id, habilitada) -> dict | None` (vía `_patch`) y `marcar_na(curso_id, cedulas) -> dict | None` (vía `_post`).

## 8. Seguridad

- Ambos endpoints nuevos protegidos con `X-Admin-Token`, reusando `verify_admin` — sin duplicar lógica de auth.
- `marcar-na` usa `ON CONFLICT DO NOTHING` para nunca sobreescribir una nota real existente, mismo criterio que `enviar_novedad`.
- No se toca ningún dato de cursos ya cargados — la migración solo agrega una columna con default retroactivo `true`, no modifica ninguna fila existente de `Nota`.

## 9. Testing

TDD en el backend, igual que el resto del proyecto:
- Migración: curso existente antes de la migración queda `convocatoria_habilitada=True` después de aplicarla; curso creado después vía `cargar_curso_nuevo()` nace en `False`; recargar un curso existente no cambia el valor ya establecido.
- `supletorios_pendientes_data()`: un curso con `convocatoria_habilitada=False` y una nota `REPROBADO` no aparece en el resultado; el mismo curso, una vez activado, sí aparece.
- `PATCH /admin/curso/{curso_id}/convocatoria-habilitada`: 401 sin token, 404 curso inexistente, actualiza correctamente el campo.
- `POST /admin/curso/{curso_id}/marcar-na`: crea la nota NO_APLICA correctamente; no sobreescribe una nota ya existente (ON CONFLICT DO NOTHING, y esa cédula no aparece en `marcados`); 401 sin token.

## 10. Verificación

Contra datos reales: cargar un curso de prueba (código distinto, mismo criterio de aislamiento que la feature anterior — no tocar cursos reales), confirmar que nace con `convocatoria_habilitada=False` y que NO aparece en `GET /analitica/convocatoria-preview` aunque tenga reprobados; activar el switch y confirmar que ahora sí aparece; probar "Marcar NA" para una persona y confirmar que no aparece luego en Novedades ni en Convocatoria. Limpiar los datos de prueba al final, con confirmación previa del usuario antes de borrar nada.
