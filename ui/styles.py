import html

import streamlit as st

ESTADO_COLORS: dict[str, tuple[str, str]] = {
    "APROBADO":            ("rgba(16,185,129,0.15)",  "#10b981"),
    "ASISTENCIA":          ("rgba(59,130,246,0.15)",  "#3b82f6"),
    "EXONERADO":           ("rgba(107,114,128,0.15)", "#6b7280"),
    "COPIA":               ("rgba(249,115,22,0.15)",  "#f97316"),
    "REPROBADO":           ("rgba(239,68,68,0.15)",   "#ef4444"),
    "FALTA_INJUSTIFICADA": ("rgba(239,68,68,0.15)",   "#ef4444"),
    "FALTA_JUSTIFICADA":   ("rgba(234,179,8,0.15)",   "#eab308"),
    "VACACIONES":          ("rgba(234,179,8,0.10)",   "#ca8a04"),
    "NUEVO":               ("rgba(139,92,246,0.15)",  "#8b5cf6"),
    "CAMBIO":              ("rgba(107,114,128,0.12)", "#6b7280"),
    "SALIO":               ("rgba(107,114,128,0.12)", "#6b7280"),
}

ESTADO_LABEL: dict[str, str] = {
    "APROBADO":            "Aprobado",
    "REPROBADO":           "Reprobado",
    "FALTA_INJUSTIFICADA": "Falta",
    "FALTA_JUSTIFICADA":   "Justificada",
    "ASISTENCIA":          "Asistencia",
    "EXONERADO":           "Exonerado",
    "COPIA":               "Copia",
    "VACACIONES":          "Vacaciones",
    "NUEVO":               "Nuevo",
    "CAMBIO":              "Cambio",
    "SALIO":               "Salió",
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
[data-testid="stSidebar"] .stMarkdown h1 {
    color: #00A8A8;
    font-size: 1.3rem;
    font-weight: 800;
    letter-spacing: 0.05em;
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
    font-weight: 600;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #00A8A8 !important;
    border-bottom-color: #00A8A8 !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] {
    border: 1px solid #1e3a4a;
    border-radius: 8px;
}

/* ── Divider ── */
hr { border-color: #1e3a4a; }

/* ── Alert blocks ── */
[data-testid="stInfo"]    { background: rgba(0,168,168,0.08); border-color: #00A8A8; }
[data-testid="stSuccess"] { background: rgba(16,185,129,0.08); }
[data-testid="stWarning"] { background: rgba(234,179,8,0.08); }
[data-testid="stError"]   { background: rgba(239,68,68,0.08); }

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #1e3a4a;
    border-radius: 8px;
    background: #1A2332;
}

/* ── Forms ── */
[data-testid="stForm"] {
    border: 1px solid #1e3a4a;
    border-radius: 8px;
    padding: 1rem;
    background: #141e2d;
}
</style>
""", unsafe_allow_html=True)


def badge(estado: str) -> str:
    bg, color = ESTADO_COLORS.get(estado, ("rgba(100,100,100,0.15)", "#888"))
    label = html.escape(ESTADO_LABEL.get(estado, estado))
    return (
        f'<span style="background:{bg};color:{color};border:1px solid {color}44;'
        f'padding:2px 10px;border-radius:12px;font-size:0.75rem;font-weight:600;">'
        f'{label}</span>'
    )


def style_notas_df(df):
    def row_style(row):
        estado = row.get("Estado", row.get("estado", ""))
        bg, _ = ESTADO_COLORS.get(estado, ("", ""))
        return [f"background-color: {bg};" if bg else ""] * len(row)
    return df.style.apply(row_style, axis=1)
