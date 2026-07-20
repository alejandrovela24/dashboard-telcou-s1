# Reporte "Calificaciones generales" en formato Macro — Diseño

**Fecha:** 2026-07-20
**Repos afectados:** telcou-api (backend), dashboard-telcou-s1 (frontend Streamlit)
**Precede a:** plan de implementación vía `superpowers:writing-plans`

## Contexto y motivación

El reporte "Calificaciones generales" (agregado el mismo día 2026-07-20, en formato lista — una fila por colaborador+curso) no sirve como reemplazo del macro manual que el usuario ya usa día a día para el seguimiento del cronograma de capacitaciones. Ese macro real (`C:\Users\USUARIO\Desktop\TelcoU DB new\2026\Quito\ejemplo formatos.xlsx`, hoja "PERSONAL TECNICO", y su equivalente `2026\TS R2\MACRO JUNIO TSR2 2026.xlsx`) es una **matriz**: una fila por colaborador, una columna por curso, con fórmulas Excel de resumen. El usuario ya tiene notas cargadas en el sistema hasta junio 2026 y seguirá cargando notas, novedades y supletorios mes a mes desde julio — necesita poder generar este mismo formato desde el sistema, para cualquier corte de meses, sin perder la continuidad del cronograma.

Este spec cubre **solo** la hoja "PERSONAL TECNICO" de cada regional (la matriz principal). Las hojas auxiliares "PLATAFORMA" y "CUADRO" del macro de TS R2 eran mecanismos manuales de pegado de datos (staging), innecesarios porque el sistema ya tiene la nota real en `notas` — quedan fuera de alcance.

## Análisis del formato original (verificado celda por celda con openpyxl)

### Quito ("ejemplo formatos.xlsx", hoja "PERSONAL TECNICO")

Filas de cabecera (1-6), luego datos desde fila 7:

| Fila | Contenido |
|---|---|
| 1 | Código de curso por columna (`ES26`, `GCT26`, ...) |
| 2 | Título "REGISTRO DE EVALUACIONES" + código de formulario + link Moodle por columna |
| 3 | Título completo "REGISTRO DE EVALUACIONES PERSONAL TÉCNICO-UIO" (celda combinada) + "DÍA DE CAPACITACIÓN" + nombre de MES (combinado sobre los cursos de ese mes) + columnas resumen: "0 POR COPIA" / "NÚMERO DE FALTAS" / "# DE SUPLETORIOS" / "PROMEDIOS" (con subcolumnas "conteo"/"Promedio") |
| 4 | Nombre completo del curso por columna |
| 5 | Tipo de curso (`PRESENCIAL`/`VIRTUAL`) por columna |
| 6 | Encabezados fijos: `#`, `N.CEDULA`, `CORREO JEFE`, `NOMBRE Y APELLIDOS`, `GENERO`, `AREA`, `JEFE INMEDIATO`, `DÍA DE CAPACITACIÓN` (valor), luego rango de semana por columna de curso (ej. "12 AL 18") |

Columnas fijas de datos por fila de colaborador: `#` (fórmula `=ROW()-6`), cédula, correo del jefe, nombre y apellidos, género, área, jefe inmediato, día de capacitación (texto libre).

Columnas resumen (fórmulas reales, ejemplo fila 7, rango de cursos I7:V7):
- `0 POR COPIA`: `=COUNTIF(I7:V7,"0 por copia")`
- `NÚMERO DE FALTAS`: `=COUNTIF(I7:V7,"F")`
- `# DE SUPLETORIOS`: `=COUNTIF(I7:V7,"<7.5")`
- `PROMEDIOS` → `conteo`: `=COUNT(I7:V7)`, `Promedio`: `=SUM(I7:V7)/Z7`

### TS R2 ("MACRO JUNIO TSR2 2026.xlsx", hoja "PERSONAL TECNICO")

Mismo contenido de cabecera pero **orden de filas y set de columnas fijas distinto**:

| Fila | Contenido |
|---|---|
| 2 | Título "REGISTRO DE EVALUACIONES" + código de formulario |
| 3 | Título completo (celda combinada) + nombre de MES |
| 4 | Nombre completo del curso |
| 5 | Link Moodle |
| 6 | Código de curso |
| 7 | Tipo de curso |
| 8 | Encabezados fijos: `#`, `CORREO`, `N.CEDULA`, `NOMBRE Y APELLIDOS`, `GENERO`, `AREA`, `JEFE INMEDIATO`, `TECNICA SUCURSAL` (en vez de "DÍA DE CAPACITACIÓN" — TS R2 no maneja día de capacitación como concepto, maneja sucursal), luego semana por columna |

Datos desde fila 9. En el original, la única columna resumen es "PROMEDIO FINAL", calculada con `=SUMIF(PLATAFORMA!$E$3:$E$746, C9, PLATAFORMA!$C$3:$C$746)` — un lookup contra la hoja de staging "PLATAFORMA". **En la implementación nueva, este cálculo se hace localmente sobre el propio rango de la fila** (igual que Quito), sin ninguna hoja externa, y **se agregan las mismas 4 columnas resumen que Quito** (0 por copia, número de faltas, # de supletorios, promedios) para consistencia entre ambas regionales.

### Mapeo de `notas.estado` → código de celda

| `estado` | Código en la celda |
|---|---|
| `APROBADO` / `REPROBADO` / `EXONERADO` | El valor numérico (`nota.valor`) |
| `FALTA_INJUSTIFICADA` | `F` |
| `FALTA_JUSTIFICADA` | `J` |
| `VACACIONES` | `V` |
| `NO_APLICA` | `NA` |
| `NUEVO` | `N` |
| `CAMBIO` | `CAMBIO` |
| `SALIO` | `SALIÓ` |
| `ASISTENCIA` | `A` |
| `COPIA` | `0 por copia` (texto literal, para que `COUNTIF(...,"0 por copia")` funcione igual que en el original) |
| `PENDIENTE_JUSTIFICACION` | Celda vacía (aún no hay decisión — evita inventar un resultado que todavía no existe) |
| Sin nota en absoluto para ese colaborador+curso | Celda vacía |

**Caso verificado:** el código `A` (visto en el ejemplo real para CAGUA OVANDO KLEVER ANTONIO, cédula 0802165928) corresponde a un colaborador analfabeto — el único caso — que "asiste" a ciertos cursos sin evaluación escrita. Mapea 1:1 al estado `ASISTENCIA` ya existente en el sistema, sin necesidad de un estado nuevo.

## Alcance funcional

### 1. Un solo archivo `.xlsx`, dos hojas

`GET /analitica/reporte-calificaciones-macro` (nuevo, telcou-api) genera un único `.xlsx` con dos hojas: **"PERSONAL TECNICO - QUITO"** y **"PERSONAL TECNICO - TS R2"**, cada una siguiendo el orden de filas/columnas fijas exacto de su regional (tabla de arriba). Cada hoja es independiente — si una regional no tiene datos en el rango pedido, su hoja aparece con solo las cabeceras (0 filas de colaboradores), nunca se omite la hoja completa.

### 2. Selección de período

**Query params:** `anio` (requerido), `mes_desde` / `mes_hasta` (opcionales — nombres de mes en español, ej. `ENERO`). Si se omiten ambos, el reporte es el **consolidado** de todos los cursos del año cargados hasta el momento. Si se especifican, solo se incluyen las columnas de curso cuyo `Curso.mes` cae en ese rango (inclusive). El orden de las columnas de curso sigue el orden cronológico de `Curso.mes` y, dentro del mismo mes, el orden de `Curso.fecha_inicio`.

### 3. Modo combinado (supletorio)

**Query param:** `combinado` (bool, default `false`). Cuando es `true`, se agrega **una columna adicional por curso con supletorio pendiente o rendido** en el período seleccionado: el resultado del supletorio (nota o código) y las características del curso (mismo nombre/código que la columna REGULAR, con el sufijo " (SUPLETORIO)"). Cuando `combinado=false` (default), la celda del curso REGULAR siempre refleja **la nota más reciente disponible** para esa persona en ese curso: si rindió supletorio después de reprobar el REGULAR, la celda muestra el resultado del supletorio (igual que el macro manual, donde solo hay un valor visible por curso). Esto es coherente con cómo se ha usado el macro históricamente — un vistazo rápido por colaborador+curso siempre debe mostrar el resultado vigente, no el intento fallido.

### 4. Columnas resumen (ambas regionales, fórmulas reales)

Se escriben como texto de fórmula (`ws.cell(...).value = '=COUNTIF(...)'`), recalculables por Excel al abrir — igual que el original, no valores precalculados:
- `0 POR COPIA`: `=COUNTIF(<rango_cursos_fila>,"0 por copia")`
- `NÚMERO DE FALTAS`: `=COUNTIF(<rango_cursos_fila>,"F")`
- `# DE SUPLETORIOS`: `=COUNTIF(<rango_cursos_fila>,"<7.5")`
- `PROMEDIOS` → `conteo`: `=COUNT(<rango_cursos_fila>)`, `Promedio`: `=SUM(<rango_cursos_fila>)/<celda_conteo>`

El `<rango_cursos_fila>` se calcula dinámicamente según cuántas columnas de curso entraron en la generación (varía según `mes_desde`/`mes_hasta` y `combinado`).

### 5. Personal nuevo / inactivo / cambio de regional

No requiere infraestructura nueva — ya existe (`Empleado.inactivo`, `tipo_movimiento`, alta vía `POST /admin/empleados`, ver `docs/API_ENDPOINTS.md`). El reporte matriz simplemente refleja fielmente los estados `NUEVO`/`CAMBIO`/`SALIO` ya presentes en `notas.estado` mediante el mapeo de la tabla de arriba — sin lógica adicional.

## Arquitectura

Nuevo módulo `app/services/reporte_matriz.py`, independiente de `app/services/reportes.py` (que sigue sirviendo Supletorios/Asistencia/Calificaciones en formato lista, sin cambios).

**Por qué `openpyxl.Workbook()` normal (no `write_only`):** el reporte de Calificaciones generales en formato lista necesitó `write_only` porque genera ~68,000 filas (una por colaborador+curso). Esta matriz genera ~1 fila por colaborador — para el universo completo de ambas regionales, del orden de 1,000-1,500 filas. Ese volumen es perfectamente manejable en modo normal, que sí permite celdas combinadas (`ws.merge_cells(...)`), lectura de celdas ya escritas y estilos — necesarios para reproducir el layout exacto (títulos combinados, negritas, etc.).

**Por qué una plantilla de cabecera por regional en vez de duplicar la función completa:** Quito y TS R2 comparten el mismo contenido de cabecera (código, link, mes, nombre, tipo) pero en **orden de fila distinto**, y tienen **columnas fijas distintas** (Quito: día de capacitación; TS R2: técnica/sucursal). Se define una función compartida `_generar_hoja_matriz(wb, regional, config, datos)` donde `config` es un diccionario declarativo por regional:

```python
CONFIG_QUITO = {
    "titulo_sheet": "PERSONAL TECNICO - QUITO",
    "orden_filas_cabecera": ["codigo", "link", "titulo_mes_resumen", "nombre_curso", "tipo"],
    "columnas_fijas": ["cedula", "correo_jefe", "nombre", "genero", "area", "jefe_inmediato", "dia"],
    "etiqueta_columna_variable": "DÍA DE CAPACITACIÓN",
}
CONFIG_TS_R2 = {
    "titulo_sheet": "PERSONAL TECNICO - TS R2",
    "orden_filas_cabecera": ["titulo_mes_resumen", "nombre_curso", "link", "codigo", "tipo"],
    "columnas_fijas": ["correo", "cedula", "nombre", "genero", "area", "jefe_inmediato", "sucursal"],
    "etiqueta_columna_variable": "TECNICA SUCURSAL",
}
```

`_generar_hoja_matriz` arma la cabecera fila por fila según `orden_filas_cabecera`, escribe las columnas fijas según `columnas_fijas` (leyendo el campo correspondiente de cada colaborador), y luego una columna por curso del período. Ambas regionales comparten exactamente la misma lógica de columnas resumen (sección 4).

**Función pública:** `generar_reporte_calificaciones_macro_excel(db, anio, mes_desde=None, mes_hasta=None, combinado=False) -> BytesIO`, en `app/services/reporte_matriz.py`.

**Endpoint:** `GET /analitica/reporte-calificaciones-macro?anio=&mes_desde=&mes_hasta=&combinado=` en `app/routers/analitica.py`, streaming `.xlsx`, mismo patrón que los reportes existentes (`Content-Disposition: attachment`).

**Frontend:** nueva opción en el selector "Tipo de reporte" de `ui/reporteria.py` (junto a Supletorios/Asistencia/Calificaciones generales): "Calificaciones (formato macro)". Controles: rango de meses (opcional, dos selectbox mes_desde/mes_hasta con opción "Todo el año"), checkbox "Incluir supletorios" (→ `combinado=true`), botón de descarga. Nueva función `api_client.py::get_reporte_calificaciones_macro_excel(anio, mes_desde, mes_hasta, combinado)`.

## Testing

- Test de mapeo estado→código con datos reales de un curso conocido (incluyendo el caso `A`/ASISTENCIA de CAGUA OVANDO KLEVER ANTONIO si existe en la BD de pruebas, o un caso equivalente sintético).
- Test de las columnas resumen: generar un colaborador con una combinación conocida de F/J/V/numéricas, leer el `.xlsx` resultante con `openpyxl` (`data_only=False`, ya que las fórmulas no se recalculan sin Excel) y verificar que el texto de la fórmula es exactamente el esperado, con el rango de columnas correcto.
- Test del modo `combinado`: colaborador con REGULAR reprobado + SUPLETORIO aprobado después — verificar que sin `combinado` la celda muestra la nota del supletorio, y con `combinado=true` aparecen ambas: la celda REGULAR (nota más reciente) y la columna adicional de supletorio.
- Test de selección de período: `mes_desde`/`mes_hasta` filtra correctamente las columnas de curso incluidas; sin ninguno de los dos, se incluyen todos los cursos del año.
- Test de las dos hojas en el mismo archivo: verificar que ambas existen con los nombres exactos (`"PERSONAL TECNICO - QUITO"`, `"PERSONAL TECNICO - TS R2"`) y que cada una usa su propio orden de columnas fijas.
- Test de regresión visual contra el archivo real: cargar los mismos datos que produjeron `ejemplo formatos.xlsx` (o un subconjunto conocido) y comparar la salida generada, celda por celda, contra los valores reales extraídos del archivo original para al menos 3 colaboradores conocidos.
- Verificación manual en Excel real (abrir el `.xlsx` generado y confirmar que las fórmulas recalculan correctamente al abrir, no solo que el texto de fórmula es sintácticamente válido).

## Fuera de alcance (explícito)

- Hojas "PLATAFORMA" y "CUADRO" del macro de TS R2 (mecanismo de staging manual, ya no necesario).
- Hoja "MEJOR ALUMNO MENSUAL" (presente en ambos archivos de ejemplo) — es una lista curada manualmente con observaciones cualitativas ("Quien asistió a 39 capacitaciones en el año"), no datos derivables automáticamente de `notas`. No se replica en esta fase.
- Edición del `.xlsx` generado de vuelta al sistema (el flujo sigue siendo: sistema → Excel de solo lectura/impresión, igual que los demás reportes).
