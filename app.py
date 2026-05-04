import os
import re
import math
import unicodedata
from datetime import datetime, date
from typing import List, Optional, Tuple, Dict

import numpy as np
import pandas as pd
import streamlit as st

# =========================
# CONFIGURACIÓN GENERAL
# =========================
st.set_page_config(page_title="Dashboard Capacitación TELCOU 2025", layout="wide")

# =========================
# AUTENTICACIÓN
# =========================
def _check_credentials(username: str, password: str) -> bool:
    try:
        users = st.secrets["users"]
        return users.get(username) == password
    except Exception:
        return False

def _login_screen():
    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/1px-PNG_transparency_demonstration_1.png", width=1)
        st.markdown(
            """
            <div style='text-align:center; margin-bottom:8px;'>
                <span style='font-size:2rem; font-weight:800; color:#E31837;'>TELCOU</span><br>
                <span style='font-size:1rem; color:#aaa;'>Dashboard Capacitación 2025</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input("Usuario", placeholder="usuario")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Ingresar", use_container_width=True)
            if submitted:
                if _check_credentials(username, password):
                    st.session_state["authenticated"] = True
                    st.session_state["current_user"] = username
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    _login_screen()
    st.stop()

# Botón de cerrar sesión en sidebar
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.get('current_user', '')}**")
    if st.button("Cerrar sesión", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state["current_user"] = ""
        st.rerun()

# --- Leer secrets de Streamlit Cloud o variables de entorno ---
def get_cfg(key: str, default: str = "") -> str:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)

SHEET_ID       = get_cfg("SHEET_ID",       "1QNvkdzmudLvl9QG9_uKxjXheBOBo5W7B7KlbKvEF-x8")
GID_PERSONAL   = get_cfg("GID_PERSONAL",   "0")
GID_CURSOS     = get_cfg("GID_CURSOS",     "1861551444")
WS_SUPLETORIOS = get_cfg("WS_SUPLETORIOS", "SUPLETORIOS UIO")
GID_SUPLET     = get_cfg("GID_SUPLET",     "1445384812")

S1_INICIO = date(2025, 1, 6)
S1_FIN    = date(2025, 6, 15)
CODIGOS_S1 = [
    "ES25","ATGC25","MC25","MBP25","SGSI25","LEC25","BUC25","GPP25","RIL25",
    "LACS25","NFO25","DBT25","CCTV25","SCG25","AU25","LARI25","FRUA25","ITSPS25",
    "ELNN25","REU25","PECA25","GRP25","GA25","PTA25","PVE25","BPR25","PLAF25",
    "CSV25","PS25","PA25","NSCD25","RO25","RSSA25","SCIS25","FO25"
]
MESES_S1  = [(1,"Enero"),(2,"Febrero"),(3,"Marzo"),(4,"Abril"),(5,"Mayo"),(6,"Junio")]
MESES_ALL = [m for m,_ in MESES_S1]
MES_LABEL = {m:l for m,l in MESES_S1}

# =========================
# UTILIDADES
# =========================
def normalizar_texto(s: str) -> str:
    if s is None: return ""
    if not isinstance(s, str): s = str(s)
    s = s.replace("\u00A0"," ").strip()
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"\s+"," ", s)

def normalize_key(s: str) -> str:
    return re.sub(r"[^A-Z0-9_]+","", normalizar_texto(s).upper())

def to_float_safe(v) -> Optional[float]:
    try:
        if v is None or (isinstance(v,float) and math.isnan(v)): return None
        return float(str(v).strip().replace(",", "."))
    except Exception:
        return None

def norm_code(texto: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+","", str(texto or "").upper())

# =========================
# REGLAS SUPLETORIO
# =========================
def umbral_para_curso(code_norm: str, desc_norm: str, area_norm: str) -> float:
    is_oc = (area_norm == "OBRAS CIVILES")
    is_tm = ("TALLER" in area_norm) and ("MOV" in area_norm)
    if code_norm == "CSV25":
        return 7.0 if is_oc else 7.5
    return 7.0 if (is_oc or is_tm) else 7.5

def es_supletorio(valor_celda, code_norm: str, desc_norm: str, area_norm: str) -> Tuple[bool, Optional[float]]:
    if valor_celda is None:
        return False, None
    txt = normalizar_texto(str(valor_celda)).upper()
    if txt in {"F","FALTA"}:
        return True, None
    nota = to_float_safe(valor_celda)
    if nota is None:
        return False, None
    return (nota < umbral_para_curso(code_norm, desc_norm, area_norm)), nota

# =========================
# CARGA DE DATOS
# =========================
@st.cache_data(ttl=900, show_spinner=False)
def cargar_personal_cursos(SHEET_ID: str, gid_personal: str, gid_cursos: str):
    df_personal = pd.read_csv(
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid_personal}"
    )
    df_personal.columns = [normalizar_texto(c) for c in df_personal.columns]
    idx = {normalize_key(c): c for c in df_personal.columns}

    def col_real(*cands):
        for c in cands:
            k = normalize_key(c)
            if k in idx: return idx[k]
        for c in cands:
            k = normalize_key(c)
            for kk,h in idx.items():
                if k in kk: return h
        return None

    ren = {}
    m = {
        "nombre":         ("nombre","apellidos y nombres","colaborador","empleado"),
        "ci":             ("ci","cedula","identificacion","cédula"),
        "area":           ("area","área"),
        "jefe_inmediato": ("jefe inmediato","jefe"),
        "jefe_correo":    ("jefe_correo","correo jefe","correo del jefe"),
        "cod":            ("cod","codigo","código"),
        "correo":         ("correo","email"),
        "dia_capacitacion":("dia capacitacion","diacapacitacion","dia","día"),
        "aula":           ("aula",),
        "estado":         ("estado",)
    }
    for dst,cands in m.items():
        c = col_real(*cands)
        if c: ren[c]=dst
    df_personal = df_personal.rename(columns=ren)
    if "estado" not in df_personal.columns: df_personal["estado"]="ACTIVO"

    cursos_colmap={}
    for code in CODIGOS_S1:
        k=normalize_key(code)
        if k in idx: cursos_colmap[code]=idx[k]
        else:
            cand=[h for kk,h in idx.items() if k in kk]
            if cand: cursos_colmap[code]=cand[0]

    df_cursos = pd.read_csv(
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid_cursos}"
    )
    df_cursos.columns = [normalizar_texto(c).lower() for c in df_cursos.columns]

    def pick_ci(cols,*alts):
        cl=[c.lower() for c in cols]
        for a in alts:
            al=normalizar_texto(a).lower()
            if al in cl: return cols[cl.index(al)]
        for a in alts:
            al=normalizar_texto(a).lower()
            for i,c in enumerate(cols):
                if al in c.lower(): return cols[i]
        return None

    c_codigo=pick_ci(df_cursos.columns,"codigo","código","codigocurso","curso","cod")
    c_desc  =pick_ci(df_cursos.columns,"descripcion","descripción","capacitacion","curso descripcion")
    c_mod   =pick_ci(df_cursos.columns,"modalidad","modo")
    c_ini   =pick_ci(df_cursos.columns,"inicio","fecha inicio","fechainicio","fecha_inicio") or pick_ci(df_cursos.columns,"fechainicio")
    c_fin   =pick_ci(df_cursos.columns,"fin","fecha fin","fechafin","fecha_fin") or pick_ci(df_cursos.columns,"fechafin")

    def parse_date(x):
        if pd.isna(x): return None
        s=str(x).strip()
        for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%m/%d/%Y"):
            try: return datetime.strptime(s,fmt).date()
            except: pass
        return None

    df_cursos["codigo_std"]  = df_cursos[c_codigo] if c_codigo else ""
    df_cursos["desc_std"]    = df_cursos[c_desc]   if c_desc   else ""
    df_cursos["modalidad"]   = df_cursos[c_mod]    if c_mod    else ""
    df_cursos["inicio_date"] = df_cursos[c_ini].apply(parse_date) if c_ini else None
    df_cursos["fin_date"]    = df_cursos[c_fin].apply(parse_date) if c_fin else None
    df_cursos["codigo_norm"] = df_cursos["codigo_std"].astype(str).str.upper().str.strip()
    df_cursos["desc_norm"]   = df_cursos["desc_std"].astype(str).str.upper().str.strip()

    return df_personal, df_cursos, cursos_colmap

@st.cache_data(ttl=900, show_spinner=False)
def cargar_supletorios(SHEET_ID: str, gid_sup: str, ws_name: str) -> Optional[pd.DataFrame]:
    try:
        df=pd.read_csv(
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid_sup}"
        )
        df.columns=[normalizar_texto(c) for c in df.columns]
        return df
    except Exception:
        return None

def preparar_lookup_suple(df_sup: Optional[pd.DataFrame]) -> Dict[str, Dict[str, float]]:
    if df_sup is None or df_sup.empty:
        return {}

    df = df_sup.copy()
    df.columns = [normalizar_texto(c) for c in df.columns]
    cols_lc = [c.lower() for c in df.columns]

    def pick(*alts):
        for a in alts:
            if a.lower() in cols_lc:
                return df.columns[cols_lc.index(a.lower())]
        for a in alts:
            for i, c in enumerate(cols_lc):
                if a.lower() in c:
                    return df.columns[i]
        return None

    c_nom = pick("nombre","apellidos y nombres","colaborador","empleado nombre","empleado")
    c_ci  = pick("cedula","cédula","ci","identificacion")
    c_emp = pick("cod","codigo empleado","codigo","idempleado","empleado id","cod_empleado")
    c_cur = pick("curso","codigo curso","codigocurso","codigo","cod")
    c_nsu = pick("nota suple","nota supletorio","nota_suple","supletorio","nota","calificacion supletorio")

    lookup: Dict[str, Dict[str, float]] = {}

    def push(key, code, note):
        if not key or not code: return
        if key not in lookup: lookup[key] = {}
        n = to_float_safe(note)
        if n is not None: lookup[key][norm_code(code)] = n

    if c_cur and c_nsu:
        df["_NOM"]  = df[c_nom].astype(str).apply(lambda x: normalizar_texto(x).upper()) if c_nom else ""
        df["_CI"]   = df[c_ci].astype(str).str.strip() if c_ci else ""
        df["_COD"]  = df[c_emp].astype(str).str.strip().upper() if c_emp else ""
        df["_CODE"] = df[c_cur].astype(str).apply(norm_code)
        for _, r in df.iterrows():
            nom,ci,cod,code = r.get("_NOM",""),r.get("_CI",""),r.get("_COD",""),r.get("_CODE","")
            for key in [nom, f"CI:{ci}" if ci else "", f"COD:{cod}" if cod else ""]:
                push(key, code, r.get(c_nsu))
        if any(len(v)>0 for v in lookup.values()):
            return lookup

    curso_cols = [c for c in df.columns if re.fullmatch(r"[A-Z]{2,}\d{2,3}", norm_code(c))]
    if curso_cols:
        nom_series = df[c_nom].astype(str).apply(lambda x: normalizar_texto(x).upper()) if c_nom else pd.Series([""]*len(df))
        ci_series  = df[c_ci].astype(str).str.strip() if c_ci else pd.Series([""]*len(df))
        cod_series = df[c_emp].astype(str).str.strip().str.upper() if c_emp else pd.Series([""]*len(df))
        for i, r in df.iterrows():
            nom = nom_series.iloc[i] if not nom_series.empty else ""
            ci  = ci_series.iloc[i]  if not ci_series.empty  else ""
            cod = cod_series.iloc[i] if not cod_series.empty else ""
            for c in curso_cols:
                code = norm_code(c)
                for key in [nom, f"CI:{ci}" if ci else "", f"COD:{cod}" if cod else ""]:
                    push(key, code, r.get(c))
    return lookup

def buscar_nota_suple(lookup: Dict[str, Dict[str, float]], nombre: str, ci: str, cod: str, curso_code: str) -> Optional[float]:
    code = norm_code(curso_code)
    nom_key = normalizar_texto(nombre).upper()
    if nom_key in lookup and code in lookup[nom_key]: return lookup[nom_key][code]
    if ci:
        key=f"CI:{str(ci).strip()}"
        if key in lookup and code in lookup[key]: return lookup[key][code]
    if cod:
        key=f"COD:{str(cod).strip().upper()}"
        if key in lookup and code in lookup[key]: return lookup[key][code]
    return None

# =========================
# MÉTRICAS Y CONTEOS
# =========================
TOK_NA = {"NA","N/A","NO APLICA","NO CONVOCADO","NC","-","—","","NAN","NINGUNO"}

def filtrar_por_semestre_y_mes(df_cursos: pd.DataFrame, codigos: List[str], meses: Optional[List[int]]) -> List[str]:
    mask = df_cursos["codigo_norm"].isin(codigos) & df_cursos["inicio_date"].between(S1_INICIO,S1_FIN,inclusive="both")
    if meses:
        mask &= df_cursos["inicio_date"].apply(lambda d: d.month if d else 0).isin(meses)
    return df_cursos.loc[mask,"codigo_norm"].tolist()

def vectorizar_conteos(df_per: pd.DataFrame, cols_eval: List[str]) -> pd.DataFrame:
    if not cols_eval:
        return pd.DataFrame(index=df_per.index, data={
            "V":0,"F":0,"J":0,"NA":0,"convocado":0,
            "asistencias":0,"porc_asistencia":np.nan,"promedio":np.nan
        })
    vals_raw = df_per[cols_eval].copy()
    vals_str = vals_raw.astype(str).map(lambda x: normalizar_texto(x).upper())
    vals_num = vals_str.map(to_float_safe)
    m_V  = (vals_str == "V")
    m_F  = (vals_str == "F")
    m_J  = (vals_str == "J")
    m_NA = (vals_str.isin(TOK_NA) | vals_raw.isna())
    V  = m_V.sum(axis=1); F  = m_F.sum(axis=1)
    J  = m_J.sum(axis=1); NA = m_NA.sum(axis=1)
    convocado   = len(cols_eval) - NA
    asistencias = (convocado - F).clip(lower=0)
    porc_asistencia = asistencias.div(convocado.where(convocado!=0, np.nan))
    promedio = vals_num.mean(axis=1, skipna=True)
    return pd.DataFrame({
        "V":V,"F":F,"J":J,"NA":NA,"convocado":convocado,
        "asistencias":asistencias,"porc_asistencia":porc_asistencia,"promedio":promedio
    }, index=df_per.index)

# =========================
# PÍLDORAS (toggle)
# =========================
def pill_toggle(label: str, key: str, color_on: str, color_off: str = "#374151") -> bool:
    if key not in st.session_state:
        st.session_state[key] = False
    is_on = st.session_state[key]
    bg = color_on if is_on else color_off
    opacity = "1" if is_on else "0.45"
    clicked = st.button(label, key=f"{key}_btn", use_container_width=True)
    st.markdown(
        f"""
        <style>
        div[data-testid="baseButton-secondary"]#{key}_btn {{
            background: {bg} !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 8px 10px !important;
            font-weight: 700 !important;
            opacity: {opacity} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )
    if clicked:
        st.session_state[key] = not is_on
        is_on = st.session_state[key]
    return is_on

# =========================
# CARGA INICIAL
# =========================
with st.spinner("Cargando datos desde Google Sheets..."):
    df_personal, df_cursos, cursos_colmap = cargar_personal_cursos(SHEET_ID, GID_PERSONAL, GID_CURSOS)
    df_sup       = cargar_supletorios(SHEET_ID, GID_SUPLET, WS_SUPLETORIOS)
    lookup_suple = preparar_lookup_suple(df_sup)
    CAT_IDX      = df_cursos.set_index("codigo_norm").to_dict(orient="index")

# =========================
# UI — HEADER
# =========================
st.title("📊 Dashboard Capacitación Técnica TELCOU 2025 — S1")
tab_colab, tab_area = st.tabs(["👥 Colaboradores", "🏢 Áreas (Totales)"])

# =========================
# TAB COLABORADORES
# =========================
with tab_colab:
    with st.form("form_colab"):
        c1,c2 = st.columns([3,1])
        with c2:
            meses_sel = st.multiselect(
                "Mes(es)", options=MESES_ALL, default=MESES_ALL,
                format_func=lambda m: MES_LABEL[m]
            )
        all_names = sorted(df_personal["nombre"].dropna().unique().tolist())
        seleccion = st.multiselect(
            "Colaborador(es) — escribe para ver coincidencias y selecciona",
            options=all_names, default=[], placeholder="Empieza a escribir…"
        )
        ok = st.form_submit_button("Aplicar")

    if not seleccion:
        st.info("Selecciona uno o más colaboradores con el control superior.")
    else:
        codes_activos = [c for c in filtrar_por_semestre_y_mes(df_cursos, CODIGOS_S1, meses_sel) if c in cursos_colmap]
        cols_eval     = [cursos_colmap[c] for c in codes_activos if cursos_colmap[c] in df_personal.columns]
        met_all       = vectorizar_conteos(df_personal, cols_eval)

        st.caption("**Convocado = Cursos del semestre activo – (NA / no convocado, incl. vacíos).** J y V no penalizan asistencia.")

        for nombre in seleccion:
            fila_df = df_personal[df_personal["nombre"]==nombre]
            if fila_df.empty:
                st.warning(f"No hallado: {nombre}"); continue
            fila      = fila_df.iloc[0]
            idx       = fila.name
            area_norm = normalizar_texto(str(fila.get("area",""))).upper()

            V        = int(met_all.loc[idx,"V"])            if idx in met_all.index else 0
            F        = int(met_all.loc[idx,"F"])            if idx in met_all.index else 0
            J        = int(met_all.loc[idx,"J"])            if idx in met_all.index else 0
            convocado= int(met_all.loc[idx,"convocado"])    if idx in met_all.index else 0
            prom     = met_all.loc[idx,"promedio"]          if idx in met_all.index else np.nan
            pa       = met_all.loc[idx,"porc_asistencia"]   if idx in met_all.index else np.nan

            ctop1,ctop2,ctop3 = st.columns([2,2,2])
            with ctop1:
                st.subheader(f"👤 {fila.get('nombre','')}")
                st.caption(f"Estado: **{fila.get('estado','')}**")
                st.write(f"Área: **{fila.get('area','')}** | Código: **{fila.get('cod','')}**")
            with ctop2:
                st.write(f"Cédula: **{fila.get('ci','')}**")
                st.write(f"Correo: **{fila.get('correo','')}**")
                st.write(f"Día: **{fila.get('dia_capacitacion','-')}**")
                st.write(f"Aula: **{fila.get('aula','-')}**")
            with ctop3:
                st.write(f"Jefe: **{fila.get('jefe_inmediato','')}**")
                st.write(f"Correo Jefe: **{fila.get('jefe_correo','')}**")

            m1,m2,m3,m4,m5,m6 = st.columns(6)
            m1.metric("J (Justificadas)", J)
            m2.metric("F (Injustificadas)", F)
            m3.metric("Convocado", convocado)
            m4.metric("Promedio", f"{float(prom):.2f}" if pd.notna(prom) else "—")
            m5.metric("% Asistencia", f"{float(pa)*100:.1f}%" if pd.notna(pa) else "—")
            m6.metric("Vacaciones (V)", V)

            # ---- INASISTENCIAS ----
            faltas_rows = []
            for code in codes_activos:
                col = cursos_colmap.get(code)
                if not col or col not in fila.index: continue
                raw     = fila.get(col)
                val_txt = normalizar_texto(str(raw)).upper()
                meta    = CAT_IDX.get(code, {})
                desc    = str(meta.get("desc_norm",""))
                ini     = meta.get("inicio_date",None)
                fin     = meta.get("fin_date",None)
                tipo    = None
                if val_txt in {"F","FALTA"}:           tipo = "Falta injustificada"
                elif val_txt == "J":                   tipo = "Falta justificada"
                elif val_txt == "V":                   tipo = "Vacaciones"
                elif (val_txt in TOK_NA) or (raw is None or (isinstance(raw,float) and math.isnan(raw))):
                    tipo = "No convocado"
                if tipo:
                    faltas_rows.append({"Código":code,"Descripción":desc.title(),"Inicio":ini,"Fin":fin,"Tipo":tipo})

            st.markdown("### 📌 Resumen de Inasistencias")
            cJ,cF,cV,cNA = st.columns(4)
            with cJ:  on_J  = pill_toggle("J · Justificadas",    key=f"inasis_J_{idx}",  color_on="#16a34a")
            with cF:  on_F  = pill_toggle("F · No justificadas",  key=f"inasis_F_{idx}",  color_on="#dc2626")
            with cV:  on_V  = pill_toggle("V · Vacaciones",       key=f"inasis_V_{idx}",  color_on="#ca8a04")
            with cNA: on_NA = pill_toggle("NA · No convocado",    key=f"inasis_NA_{idx}", color_on="#6b7280")

            tipos_permitidos = set()
            if on_J:  tipos_permitidos.add("Falta justificada")
            if on_F:  tipos_permitidos.add("Falta injustificada")
            if on_V:  tipos_permitidos.add("Vacaciones")
            if on_NA: tipos_permitidos.add("No convocado")

            expected_cols = ["Código","Descripción","Inicio","Fin","Tipo"]
            df_f = pd.DataFrame.from_records(faltas_rows)
            for c in expected_cols:
                if c not in df_f.columns: df_f[c] = pd.Series(dtype="object")
            df_f = df_f[expected_cols]
            if tipos_permitidos and not df_f.empty:
                df_f = df_f[df_f["Tipo"].isin(tipos_permitidos)].reset_index(drop=True)
            else:
                if not tipos_permitidos: df_f = df_f.iloc[0:0].copy()

            activos_txt = ", ".join([t for t,flag in [("J",on_J),("F",on_F),("V",on_V),("NA",on_NA)] if flag])
            st.caption(f"**Filtros activos:** {activos_txt if activos_txt else 'Ninguno'}")

            if df_f.empty:
                st.info("Activa uno o más filtros (J, F, V, NA) para visualizar registros.")
            else:
                def style_inasist(df_show: pd.DataFrame):
                    S = pd.DataFrame("", index=df_show.index, columns=df_show.columns)
                    for i in df_show.index:
                        t = df_show.at[i,"Tipo"]
                        color = (
                            "rgba(255,0,0,0.15)"   if t=="Falta injustificada" else
                            "rgba(0,128,0,0.18)"   if t=="Falta justificada"   else
                            "rgba(255,200,0,0.18)" if t=="Vacaciones"          else
                            "rgba(255,255,255,0.05)"
                        )
                        S.loc[i,:] = f"background-color: {color};"
                    return S
                st.dataframe(df_f.style.apply(style_inasist, axis=None), use_container_width=True)

            # ---- SUPLETORIOS ----
            detalle=[]; aprobados=0
            for code in codes_activos:
                col = cursos_colmap.get(code)
                if not col or col not in fila.index: continue
                raw     = fila.get(col)
                meta    = CAT_IDX.get(code,{})
                desc    = str(meta.get("desc_norm",""))
                ini     = meta.get("inicio_date",None)
                fin     = meta.get("fin_date",None)
                mod     = meta.get("modalidad","")
                es_sup, _ = es_supletorio(raw, code, desc, area_norm)
                if es_sup:
                    um     = umbral_para_curso(code, desc, area_norm)
                    nota_s = buscar_nota_suple(
                        lookup_suple,
                        str(fila.get("nombre","")),
                        str(fila.get("ci","")),
                        str(fila.get("cod","")),
                        code
                    )
                    estado = "Pendiente"
                    if nota_s is not None and nota_s >= um:
                        estado = "Aprobado"; aprobados += 1
                    detalle.append({
                        "Código":code,"Descripción":desc.title(),"Modalidad":mod,
                        "Inicio":ini,"Fin":fin,"Valor Inicial":raw,
                        "Nota Suple":(round(float(nota_s),2) if nota_s is not None else None),
                        "Estado Suple":estado,"_umbral":um
                    })

            registrados=len(detalle); pendientes=registrados-aprobados
            st.markdown("### 🎯 Análisis de Supletorios")
            k1,k2,k3,k4 = st.columns(4)
            k1.metric("Supletorios Registrados", registrados)
            k2.metric("Supletorios Aprobados", aprobados)
            k3.metric("Supletorios Pendientes", pendientes)
            porc_ap = (aprobados/registrados) if registrados>0 else np.nan
            k4.metric("% Aprobación", f"{porc_ap*100:.1f}%" if pd.notna(porc_ap) else "—")

            if detalle:
                df_det    = pd.DataFrame(detalle)
                show_cols = ["Código","Descripción","Modalidad","Inicio","Fin","Valor Inicial","Nota Suple","Estado Suple"]
                umbral_s  = df_det["_umbral"]

                def style_matrix(df_show: pd.DataFrame) -> pd.DataFrame:
                    S = pd.DataFrame("", index=df_show.index, columns=df_show.columns)
                    for i in df_show.index:
                        um     = to_float_safe(umbral_s.get(i))
                        vi_raw = df_show.at[i,"Valor Inicial"]
                        vi_txt = normalizar_texto(str(vi_raw)).upper()
                        vi_num = to_float_safe(vi_raw)
                        if vi_txt in {"F","FALTA"} or (vi_num is not None and um is not None and vi_num < um):
                            S.at[i,"Valor Inicial"] = "background-color: rgba(255,0,0,0.18);"
                        ns = to_float_safe(df_show.at[i,"Nota Suple"])
                        if ns is not None and um is not None:
                            S.at[i,"Nota Suple"] = (
                                "background-color: rgba(0,128,0,0.20);"
                                if ns >= um else
                                "background-color: rgba(255,0,0,0.20);"
                            )
                    return S

                df_show = df_det[show_cols].copy()
                st.markdown("#### 📚 Detalle de Cursos en Supletorio")
                st.dataframe(
                    df_show.style.apply(style_matrix, axis=None).format({"Nota Suple":"{:.2f}"}),
                    use_container_width=True
                )
            else:
                st.info("No se detectaron supletorios con las condiciones y filtros seleccionados.")

            st.divider()

# =========================
# TAB ÁREAS
# =========================
with tab_area:
    with st.form("form_area"):
        cols_ui = st.columns([2,2,2])
        areas_all   = sorted(df_personal.get("area", pd.Series(dtype=str)).dropna().unique())
        estados_all = ["ACTIVO","INACTIVO"]
        with cols_ui[0]:
            filtro_areas2  = st.multiselect("Área",    options=areas_all,   default=areas_all)
        with cols_ui[1]:
            filtro_estado2 = st.multiselect("Estado",  options=estados_all, default=estados_all)
        with cols_ui[2]:
            meses_sel2 = st.multiselect(
                "Mes(es)", options=MESES_ALL, default=MESES_ALL,
                format_func=lambda m: MES_LABEL[m]
            )
        ok2 = st.form_submit_button("Aplicar")

    mask2 = pd.Series(True, index=df_personal.index)
    if filtro_areas2:  mask2 &= df_personal["area"].isin(filtro_areas2)
    if filtro_estado2: mask2 &= df_personal["estado"].astype(str).str.upper().isin([x.upper() for x in filtro_estado2])
    dfp2 = df_personal[mask2].copy()

    codes2 = filtrar_por_semestre_y_mes(df_cursos, CODIGOS_S1, meses_sel2)
    cols2  = [cursos_colmap[c] for c in codes2 if c in cursos_colmap and cursos_colmap[c] in dfp2.columns]
    met2   = vectorizar_conteos(dfp2, cols2)

    if met2.empty:
        st.info("No hay datos para los filtros.")
    else:
        tot_V    = int(met2["V"].sum())
        tot_F    = int(met2["F"].sum())
        tot_J    = int(met2["J"].sum())
        tot_conv = int(met2["convocado"].sum())
        tot_asist= int(met2["asistencias"].sum())
        porc_gl  = (tot_asist/tot_conv) if tot_conv>0 else np.nan
        prom_gl  = met2["promedio"].mean(skipna=True)

        k1,k2,k3,k4,k5 = st.columns(5)
        k1.metric("Vacaciones (V)",   tot_V)
        k2.metric("Faltas (F)",        tot_F)
        k3.metric("Justificadas (J)",  tot_J)
        k4.metric("Convocado",         tot_conv)
        k5.metric("% Asistencia Global", f"{porc_gl*100:.1f}%" if pd.notna(porc_gl) else "—")
        st.caption(f"**Promedio Global:** {prom_gl:.2f}" if pd.notna(prom_gl) else "**Promedio Global:** —")

        df_tmp = pd.concat([dfp2[["area"]], met2], axis=1)
        grp = df_tmp.groupby("area", dropna=True, as_index=False).agg(
            V=("V","sum"), F=("F","sum"), J=("J","sum"),
            Convocado=("convocado","sum"),
            Asistencias=("asistencias","sum")
        )
        grp["% Asistencia"] = (grp["Asistencias"]/grp["Convocado"]).replace([np.inf,-np.inf],np.nan)
        out = grp[["area","V","F","J","Convocado","% Asistencia"]].rename(columns={"area":"Área"})
        out["% Asistencia"] = out["% Asistencia"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "—")
        st.table(out)
