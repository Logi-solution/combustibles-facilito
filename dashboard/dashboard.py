"""
Dashboard de precios de combustibles (Facilito / OSINERGMIN).

Lee todos los CSV diarios de ../data_historica/ (uno por dia, generados por
scripts/scraper_facilito.py) y arma un reporte interactivo:

1. Selectores de Departamento / Provincia / Distrito (independientes: cada uno
   puede dejarse en "Todos" sin necesidad de fijar los de arriba).
2. Precio promedio por departamento, uno por tipo de combustible.
3. Precio promedio por distrito (top 5 mas barato -> mas caro), uno por tipo
   de combustible, con opcion de ver la lista completa.
4. Curva de evolucion de precios (diaria / semanal / mensual), un grafico por
   tipo de combustible.
5. Calendario (mes/anio) en la barra lateral: al hacer clic en un dia, los
   graficos de arriba usan ese dia como referencia en vez del ultimo dia
   disponible.
6. Cantidad de estaciones activas (segun filtros vigentes).
7. Espacio reservado arriba a la izquierda para el logo de Logi Solution.
"""

import calendar as cal_module
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data_historica"

PRODUCTOS = ["Gasolina Regular", "Gasolina Premium", "Diesel DB5"]
DIAS_SEMANA = ["L", "M", "X", "J", "V", "S", "D"]

st.set_page_config(page_title="Precios de combustibles - Facilito", layout="wide")


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    files = sorted(DATA_DIR.glob("*_combustibles.csv"))
    if not files:
        return pd.DataFrame(
            columns=["Fecha", "Región", "Provincia", "Distrito", "Establecimiento", "Tipo_Combustible", "Precio_Soles_Galon"]
        )
    frames = [pd.read_csv(f, encoding="utf-8-sig") for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["Fecha"] = pd.to_datetime(df["Fecha"]).dt.date
    df["Precio_Soles_Galon"] = pd.to_numeric(df["Precio_Soles_Galon"], errors="coerce")
    return df


def scoped(df: pd.DataFrame, depto: str, prov: str, dist: str) -> pd.DataFrame:
    if depto != "Todos":
        df = df[df["Región"] == depto]
    if prov != "Todas":
        df = df[df["Provincia"] == prov]
    if dist != "Todos":
        df = df[df["Distrito"] == dist]
    return df


# ---------------------------------------------------------------------------
# Calendario (sidebar) - estado en session_state
# ---------------------------------------------------------------------------

def render_calendar(available_dates: set):
    today = date.today()
    st.session_state.setdefault("selected_date", None)
    st.session_state.setdefault("cal_year", today.year)
    st.session_state.setdefault("cal_month", today.month)

    st.sidebar.markdown("**Calendario**")
    nav1, nav2, nav3 = st.sidebar.columns([1, 3, 1])
    if nav1.button("◀", key="cal_prev", use_container_width=True):
        m, y = st.session_state.cal_month - 1, st.session_state.cal_year
        if m == 0:
            m, y = 12, y - 1
        st.session_state.cal_month, st.session_state.cal_year = m, y
    if nav3.button("▶", key="cal_next", use_container_width=True):
        m, y = st.session_state.cal_month + 1, st.session_state.cal_year
        if m == 13:
            m, y = 1, y + 1
        st.session_state.cal_month, st.session_state.cal_year = m, y
    nav2.markdown(
        f"<div style='text-align:center;padding-top:6px'>{cal_module.month_name[st.session_state.cal_month]} {st.session_state.cal_year}</div>",
        unsafe_allow_html=True,
    )

    weeks = cal_module.Calendar(firstweekday=0).monthdayscalendar(st.session_state.cal_year, st.session_state.cal_month)

    header_cols = st.sidebar.columns(7)
    for c, lbl in zip(header_cols, DIAS_SEMANA):
        c.markdown(f"<div style='text-align:center;font-size:11px;color:gray'>{lbl}</div>", unsafe_allow_html=True)

    for week in weeks:
        cols = st.sidebar.columns(7)
        for c, day in zip(cols, week):
            if day == 0:
                c.write("")
                continue
            d = date(st.session_state.cal_year, st.session_state.cal_month, day)
            has_data = d in available_dates
            is_selected = st.session_state.selected_date == d
            if c.button(
                str(day),
                key=f"day_{d.isoformat()}",
                disabled=not has_data,
                type="primary" if is_selected else "secondary",
                use_container_width=True,
            ):
                st.session_state.selected_date = d
                st.rerun()

    if st.session_state.selected_date:
        st.sidebar.caption(f"Fecha seleccionada: {st.session_state.selected_date.strftime('%d/%m/%Y')}")
        if st.sidebar.button("Quitar filtro de fecha", use_container_width=True):
            st.session_state.selected_date = None
            st.rerun()
    else:
        st.sidebar.caption("Sin fecha seleccionada: se usa el dato mas reciente.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

df = load_data()

col_logo, col_title = st.columns([1, 5])
with col_logo:
    with st.container(border=True, height=90):
        st.markdown(
            "<div style='display:flex;align-items:center;justify-content:center;height:100%;"
            "color:var(--text-secondary,#888);font-size:12px;text-align:center'>Logo<br>Logi Solution</div>",
            unsafe_allow_html=True,
        )
with col_title:
    st.title("Precios de combustibles - Facilito")
    st.caption("Histórico diario extraído de OSINERGMIN (La Libertad, Ica, Piura, Lima, Lambayeque)")

if df.empty:
    st.warning("Todavía no hay archivos en data_historica/. El dashboard se llenará a medida que corra la extracción diaria.")
    st.stop()

available_dates = set(df["Fecha"].unique())
render_calendar(available_dates)

# --- Selectores independientes (Departamento / Provincia / Distrito) ---
f1, f2, f3 = st.columns(3)
depto_opts = ["Todos"] + sorted(df["Región"].unique())
depto = f1.selectbox("Departamento", depto_opts)

prov_scope = df if depto == "Todos" else df[df["Región"] == depto]
prov_opts = ["Todas"] + sorted(prov_scope["Provincia"].unique())
prov = f2.selectbox("Provincia", prov_opts)

dist_scope = prov_scope if prov == "Todas" else prov_scope[prov_scope["Provincia"] == prov]
dist_opts = ["Todos"] + sorted(dist_scope["Distrito"].unique())
dist = f3.selectbox("Distrito", dist_opts)

df_scoped = scoped(df, depto, prov, dist)

fecha_ref = st.session_state.selected_date or df["Fecha"].max()
st.divider()

# --- KPI: estaciones activas ---
activas = df_scoped[df_scoped["Fecha"] == fecha_ref][["Distrito", "Establecimiento"]].drop_duplicates().shape[0]
st.metric(f"Estaciones activas ({fecha_ref.strftime('%d/%m/%Y')})", f"{activas:,}")

st.divider()

# --- Precio promedio por departamento (comparación nacional, 1 por combustible) ---
st.subheader("Precio promedio por departamento")
cols = st.columns(3)
for col, producto in zip(cols, PRODUCTOS):
    d = df[(df["Fecha"] == fecha_ref) & (df["Tipo_Combustible"] == producto)]
    agg = d.groupby("Región")["Precio_Soles_Galon"].mean().reset_index().sort_values("Precio_Soles_Galon")
    with col:
        st.markdown(f"**{producto}**")
        if agg.empty:
            st.caption("Sin datos para esta fecha.")
        else:
            fig = px.bar(agg, x="Precio_Soles_Galon", y="Región", orientation="h", text_auto=".2f")
            fig.update_layout(height=220, margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
            st.plotly_chart(fig, use_container_width=True, key=f"dep_{producto}")

st.divider()

# --- Precio promedio por distrito (top 5 + lista completa), 1 por combustible ---
st.subheader("Precio promedio por distrito (top 5 más barato)")
cols = st.columns(3)
for col, producto in zip(cols, PRODUCTOS):
    d = df_scoped[(df_scoped["Fecha"] == fecha_ref) & (df_scoped["Tipo_Combustible"] == producto)]
    agg = d.groupby("Distrito")["Precio_Soles_Galon"].mean().reset_index().sort_values("Precio_Soles_Galon")
    with col:
        st.markdown(f"**{producto}**")
        if agg.empty:
            st.caption("Sin datos para esta selección.")
            continue
        top5 = agg.head(5)
        fig = px.bar(top5, x="Precio_Soles_Galon", y="Distrito", orientation="h", text_auto=".2f")
        fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0), xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig, use_container_width=True, key=f"dist_{producto}")
        with st.expander(f"Ver lista completa ({len(agg)} distritos)"):
            st.dataframe(
                agg.rename(columns={"Precio_Soles_Galon": "Precio (S/)"}).reset_index(drop=True),
                use_container_width=True,
                hide_index=True,
            )

st.divider()

# --- Evolución de precios (diaria / semanal / mensual), 1 por combustible ---
st.subheader("Evolución de precios")
granularidad = st.radio("Granularidad", ["Diaria", "Semanal", "Mensual"], horizontal=True)

cols = st.columns(3)
for col, producto in zip(cols, PRODUCTOS):
    d = df_scoped[df_scoped["Tipo_Combustible"] == producto].copy()
    d["Fecha"] = pd.to_datetime(d["Fecha"])
    serie = d.groupby("Fecha")["Precio_Soles_Galon"].mean().reset_index().sort_values("Fecha")

    if granularidad == "Semanal":
        serie = serie.set_index("Fecha").resample("W").mean().reset_index()
    elif granularidad == "Mensual":
        serie = serie.set_index("Fecha").resample("ME").mean().reset_index()

    with col:
        st.markdown(f"**{producto}**")
        if serie.empty:
            st.caption("Sin datos para esta selección.")
            continue
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=serie["Fecha"], y=serie["Precio_Soles_Galon"], mode="lines+markers", name=producto))
        if st.session_state.selected_date:
            fig.add_vline(x=pd.Timestamp(st.session_state.selected_date), line_dash="dash", line_color="gray")
        fig.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="S/ por galón", xaxis_title=None, showlegend=False)
        st.plotly_chart(fig, use_container_width=True, key=f"evo_{producto}")
