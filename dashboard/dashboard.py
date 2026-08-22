"""
Dashboard de precios de combustibles (Facilito / OSINERGMIN).

Lee todos los CSV diarios de ../data_historica/ (uno por dia, generados por
scripts/scraper_facilito.py) y arma un reporte compacto pensado para caber
en una sola pantalla:

1. Selectores de Departamento / Provincia / Distrito / Combustible
   (independientes: cada uno puede dejarse en "Todos").
2. KPIs: estaciones activas, precio promedio, minimo y maximo del dia.
3. Precio promedio por departamento (combustible seleccionado).
4. Top distritos mas baratos (lista compacta, menor a mayor) + ver todos.
5. Evaluacion entre proveedores: top estaciones mas baratas + ver todos.
6. Evolucion de precios (diaria/semanal/mensual), los 3 combustibles juntos.
7. Calendario en la barra lateral: clic en un dia cambia la fecha de
   referencia de los KPIs y comparativas.
8. Espacio reservado arriba a la izquierda para el logo de Logi Solution.
"""

import base64
import calendar as cal_module
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data_historica"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "logo.png"

PRODUCTOS = ["Gasolina Regular", "Gasolina Premium", "Diesel DB5"]
COLOR_PRODUCTO = {
    "Gasolina Regular": "#E94217",
    "Gasolina Premium": "#012C63",
    "Diesel DB5": "#CB1E1E",
}
COLOR_BAR = "#012C63"
DIAS_SEMANA = ["L", "M", "X", "J", "V", "S", "D"]
MESES_ABBR = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Oct", 11: "Nov", 12: "Dic"}
CHART_H = 140

st.set_page_config(page_title="Precios de combustibles - Facilito", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stMain"] {background: linear-gradient(180deg, #EAF0FB 0%, #F2ECE6 100%);}
    header[data-testid="stHeader"] {display: none !important;}
    section[data-testid="stSidebar"] {background: #FFFFFF !important;}
    section[data-testid="stSidebar"] > div {background: #FFFFFF !important;}
    [data-testid="stVerticalBlock"][height] {background: #FFFFFF;}
    .accent-bar {height:4px; margin:-1rem -1rem 0.3rem -1rem; border-radius:8px 8px 0 0;}
    .kpi-tile {border-radius:10px; padding:0.6rem 0.8rem;}
    .kpi-tile .kpi-label {font-size:0.72rem; opacity:0.85;}
    .kpi-tile .kpi-value {font-size:1.25rem; font-weight:600; margin-top:2px; text-align:center;}
    .block-container {padding-top: 3.6rem; padding-bottom: 0.15rem;}
    h3, h4, h5 {font-size: 0.92rem !important; margin: 0 0 0.2rem 0 !important;}
    [data-testid="stMetricValue"] {font-size: 1.2rem;}
    [data-testid="stMetricLabel"] {font-size: 0.72rem;}
    .rank-row {display:flex; justify-content:space-between; font-size:12px; padding:1px 0; border-bottom:1px solid rgba(128,128,128,0.15);}
    .rank-row:last-child {border-bottom:none;}
    div[data-testid="stVerticalBlock"] {gap: 0.25rem !important;}
    [data-testid="stHorizontalBlock"] {gap: 0.5rem !important; align-items: stretch !important;}
    div[data-testid="stColumn"] {padding: 0.15rem !important; display: flex !important; flex-direction: column !important;}
    div[data-testid="stColumn"] > div {flex: 1 1 auto !important; display: flex !important; flex-direction: column !important;}
    div[data-testid="stColumn"] > div > [data-testid="stVerticalBlock"] {flex: 1 1 auto !important; height: 100% !important;}
    hr {margin: 0.4rem 0 !important;}
    [data-testid="stSidebarUserContent"] {padding-top: 2.75rem !important;}
    section[data-testid="stSidebar"] button {
        min-height: 1.7rem !important;
        height: 1.7rem !important;
        padding: 0 !important;
        font-size: 12px !important;
        line-height: 1.7rem !important;
    }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
        gap: 0.25rem !important;
        margin-bottom: 0 !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {
        gap: 0.1rem !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stElementContainer"] {
        margin-bottom: 0 !important;
    }
    [data-testid="stSidebarCollapseButton"] {display: none !important;}
    [data-testid="collapsedControl"] {display: none !important;}
    button[data-testid="baseButton-headerNoPadding"] {display: none !important;}
    section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        overflow-y: auto !important;
        scrollbar-width: none !important;
    }
    section[data-testid="stSidebar"]::-webkit-scrollbar,
    section[data-testid="stSidebar"] > div::-webkit-scrollbar,
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]::-webkit-scrollbar {
        display: none !important;
        width: 0 !important;
    }

    @media (max-width: 768px) {
        .lg-topbar-logo {
            position: static !important;
            width: 100% !important;
            height: 64px !important;
        }
        .lg-topbar-title {
            position: static !important;
            width: 100% !important;
            height: auto !important;
            flex-direction: column !important;
            align-items: flex-start !important;
            gap: 4px;
            padding: 10px 1.3rem !important;
        }
        .block-container {padding-top: 0.6rem !important;}
        [data-testid="stHorizontalBlock"] {flex-direction: column !important;}
        div[data-testid="stColumn"] {width: 100% !important; flex: 1 1 100% !important;}
        .st-key-card_dep, .st-key-card_dep > div, .st-key-card_dep [data-testid="stVerticalBlock"],
        .st-key-card_topdist, .st-key-card_topdist > div, .st-key-card_topdist [data-testid="stVerticalBlock"],
        .st-key-card_prov, .st-key-card_prov > div, .st-key-card_prov [data-testid="stVerticalBlock"],
        .st-key-card_evo, .st-key-card_evo > div, .st-key-card_evo [data-testid="stVerticalBlock"] {
            height: auto !important;
            max-height: none !important;
            overflow: visible !important;
        }
        [data-testid="collapsedControl"] {display: flex !important;}
        button[data-testid="baseButton-headerNoPadding"] {display: flex !important;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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


def ranked_bar(df_agg: pd.DataFrame, cat_col: str, val_col: str, height: int = CHART_H):
    fig = go.Figure(
        go.Bar(
            x=df_agg[val_col],
            y=df_agg[cat_col],
            orientation="h",
            text=df_agg[val_col].map(lambda v: f"{v:.2f}"),
            textposition="outside",
            marker_color=COLOR_BAR,
        )
    )
    fig.update_yaxes(autorange="reversed")
    max_val = df_agg[val_col].max()
    fig.update_xaxes(range=[0, max_val * 1.18])
    fig.update_layout(height=height, margin=dict(l=0, r=30, t=5, b=5), xaxis_title=None, yaxis_title=None)
    return fig


def kpi_tile(label: str, value: str, bg: str, color: str):
    st.markdown(
        f"""<div class="kpi-tile" style="background:{bg}; color:{color};">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def accent_bar(color: str):
    st.markdown(f"<div class='accent-bar' style='background:{color};'></div>", unsafe_allow_html=True)


def render_ranked_list(df_agg: pd.DataFrame, label_col: str, top_n: int = 5):
    top = df_agg.sort_values("Precio_Soles_Galon", ascending=True).head(top_n).reset_index(drop=True)
    if top.empty:
        st.caption("Sin datos para esta selección.")
        return
    rows_html = "".join(
        f"<div class='rank-row'><span>{i + 1}. {r[label_col]}</span><span><b>S/ {r['Precio_Soles_Galon']:.2f}</b></span></div>"
        for i, r in top.iterrows()
    )
    st.markdown(rows_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Calendario (sidebar)
# ---------------------------------------------------------------------------

@st.cache_data
def get_logo_base64() -> str:
    if not LOGO_PATH.exists():
        return ""
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("utf-8")


def render_top_bar(last_update: str):
    logo_b64 = get_logo_base64()
    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" style="max-height:75px; max-width:202px; width:auto; object-fit:contain;">'
        if logo_b64
        else '<span style="font-size:12px; color:#012C63;">Logo Logi Solution</span>'
    )
    st.markdown(
        f"""
        <div class="lg-topbar-logo" style="position:fixed; top:0; left:0; width:300px; height:100px; z-index:9999999;
                    background:#FFFFFF; display:flex; align-items:center; justify-content:center; padding:10px;">
          {logo_html}
        </div>
        <div class="lg-topbar-title" style="position:fixed; top:0; left:300px; width:calc(100% - 300px); height:56px; z-index:9999999;
                    background:linear-gradient(90deg, #012C63 0%, #8F3D1A 100%); display:flex;
                    justify-content:space-between; align-items:center; padding:0 1.3rem; color:#FFFFFF;">
          <div style="font-weight:600; font-size:1.05rem;">Panel de precios de combustibles</div>
          <div style="font-size:0.78rem; opacity:0.92;">Última actualización: {last_update}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_header():
    st.sidebar.markdown(
        """
        <div style="text-align:center;">
          <div style="font-size:1rem; font-weight:600;">Análisis de precios de combustibles</div>
          <div style="font-size:0.78rem; color:var(--text-secondary,#888); margin-top:4px;">
            La Libertad · Ica · Piura · Lima · Lambayeque
          </div>
          <div style="font-size:0.7rem; color:var(--text-secondary,#888); margin-top:6px;">
            Fuente de precios: <a href="https://www.facilito.gob.pe/facilito/pages/facilito/buscadorEESS.jsp" target="_blank">facilito.gob.pe</a>
          </div>
          <div style="font-size:0.66rem; color:var(--text-secondary,#888); margin-top:4px;">
            Datos actualizados diariamente a la 1:00 pm (hora Perú).
          </div>
          <div style="font-size:0.66rem; color:var(--text-secondary,#888); margin-top:3px;">
            Uso con fines de análisis estadístico; no constituye el precio oficial vigente.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("<div style='height:34px'></div>", unsafe_allow_html=True)


def render_calendar(available_dates: set):
    today = date.today()
    st.session_state.setdefault("range_start", None)
    st.session_state.setdefault("range_end", None)
    st.session_state.setdefault("date_mode", "Día")
    st.session_state.setdefault("cal_year", today.year)
    st.session_state.setdefault("cal_month", today.month)

    st.sidebar.markdown("**Calendario**")
    st.sidebar.radio("Selección", ["Día", "Rango"], key="date_mode", horizontal=True, label_visibility="collapsed")

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
        c.markdown(f"<div style='text-align:center;font-size:11px;color:gray;padding-bottom:16px;'>{lbl}</div>", unsafe_allow_html=True)

    start = st.session_state.range_start
    end = st.session_state.range_end

    def _select_day(d):
        cur_start = st.session_state.range_start
        cur_end = st.session_state.range_end
        if st.session_state.date_mode == "Día":
            st.session_state.range_start = d
            st.session_state.range_end = d
        else:
            if cur_start is None or cur_end is not None:
                st.session_state.range_start = d
                st.session_state.range_end = None
            else:
                if d < cur_start:
                    st.session_state.range_start, st.session_state.range_end = d, cur_start
                else:
                    st.session_state.range_end = d

    for week in weeks:
        cols = st.sidebar.columns(7)
        for c, day in zip(cols, week):
            if day == 0:
                c.write("")
                continue
            d = date(st.session_state.cal_year, st.session_state.cal_month, day)
            has_data = d in available_dates
            if start is None:
                in_selection = False
            elif end is None:
                in_selection = d == start
            else:
                in_selection = start <= d <= end
            c.button(
                str(day),
                key=f"day_{d.isoformat()}",
                disabled=not has_data,
                type="primary" if in_selection else "secondary",
                use_container_width=True,
                on_click=_select_day,
                args=(d,),
            )

    if st.session_state.range_start:
        s, e = st.session_state.range_start, st.session_state.range_end
        if e is None:
            st.sidebar.caption(f"Desde {s.strftime('%d/%m/%Y')} — elige el día final")
        elif s == e:
            st.sidebar.caption(f"Fecha seleccionada: {s.strftime('%d/%m/%Y')}")
        else:
            st.sidebar.caption(f"Del {s.strftime('%d/%m/%Y')} al {e.strftime('%d/%m/%Y')}")
        def _clear_selection():
            st.session_state.range_start = None
            st.session_state.range_end = None

        st.sidebar.button("Quitar selección", use_container_width=True, key="clear_selection", on_click=_clear_selection)
    else:
        st.sidebar.caption("Sin fecha seleccionada: se usa el dato más reciente.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

df = load_data()

if df.empty:
    st.warning("Todavía no hay archivos en data_historica/. El dashboard se llenará a medida que corra la extracción diaria.")
    st.stop()

render_top_bar(df["Fecha"].max().strftime("%d/%m/%Y"))
render_sidebar_header()

available_dates = set(df["Fecha"].unique())
render_calendar(available_dates)

f1, f2, f3, f4 = st.columns(4)
depto_opts = ["Todos"] + sorted(df["Región"].unique())
depto = f1.selectbox("Departamento", depto_opts, key="sel_depto")

prov_scope = df if depto == "Todos" else df[df["Región"] == depto]
prov_opts = ["Todas"] + sorted(prov_scope["Provincia"].unique())
if st.session_state.get("sel_prov") not in prov_opts:
    st.session_state.sel_prov = "Todas"
prov = f2.selectbox("Provincia", prov_opts, key="sel_prov")

dist_scope = prov_scope if prov == "Todas" else prov_scope[prov_scope["Provincia"] == prov]
dist_opts = ["Todos"] + sorted(dist_scope["Distrito"].unique())
if st.session_state.get("sel_dist") not in dist_opts:
    st.session_state.sel_dist = "Todos"
dist = f3.selectbox("Distrito", dist_opts, key="sel_dist")

producto = f4.selectbox("Combustible", PRODUCTOS, key="sel_producto")

df_scoped = scoped(df, depto, prov, dist)

if st.session_state.range_start:
    fecha_ini = st.session_state.range_start
    fecha_fin = st.session_state.range_end or st.session_state.range_start
else:
    fecha_ini = fecha_fin = df["Fecha"].max()

label_fecha = fecha_ini.strftime("%d/%m") if fecha_ini == fecha_fin else f"{fecha_ini.strftime('%d/%m')}-{fecha_fin.strftime('%d/%m')}"

dia_scope_fuel = df_scoped[
    (df_scoped["Fecha"] >= fecha_ini) & (df_scoped["Fecha"] <= fecha_fin) & (df_scoped["Tipo_Combustible"] == producto)
]

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
activas = (
    df_scoped[(df_scoped["Fecha"] >= fecha_ini) & (df_scoped["Fecha"] <= fecha_fin)][["Distrito", "Establecimiento"]]
    .drop_duplicates()
    .shape[0]
)
with k1:
    kpi_tile(f"Estaciones activas ({label_fecha})", f"{activas:,}", "#E7ECF5", "#012C63")
with k2:
    kpi_tile(
        f"Precio promedio · {producto}",
        f"S/ {dia_scope_fuel['Precio_Soles_Galon'].mean():.2f}" if not dia_scope_fuel.empty else "—",
        "#FCE9E0", "#B23A12",
    )
with k3:
    kpi_tile(
        "Más barato",
        f"S/ {dia_scope_fuel['Precio_Soles_Galon'].min():.2f}" if not dia_scope_fuel.empty else "—",
        "#E3F3EA", "#1E7A4C",
    )
with k4:
    kpi_tile(
        "Más caro",
        f"S/ {dia_scope_fuel['Precio_Soles_Galon'].max():.2f}" if not dia_scope_fuel.empty else "—",
        "#FBE7E7", "#A61B1B",
    )

# --- Fila 1: comparativa por departamento | top distritos ---
r1c1, r1c2 = st.columns(2)
CARD_H_ROW1 = 220
CARD_H_ROW2 = 237

with r1c1:
    with st.container(border=True, height=CARD_H_ROW1, key="card_dep"):
        accent_bar("#012C63")
        st.markdown(f"##### Precio promedio por departamento · {producto}")
        d = df[(df["Fecha"] >= fecha_ini) & (df["Fecha"] <= fecha_fin) & (df["Tipo_Combustible"] == producto)]
        agg = d.groupby("Región")["Precio_Soles_Galon"].mean().reset_index().sort_values("Precio_Soles_Galon")
        if agg.empty:
            st.caption("Sin datos para esta fecha.")
        else:
            st.plotly_chart(ranked_bar(agg, "Región", "Precio_Soles_Galon"), use_container_width=True, key="dep_chart")

with r1c2:
    with st.container(border=True, height=CARD_H_ROW1, key="card_topdist"):
        accent_bar("#CB1E1E")
        st.markdown(f"##### Top distritos más baratos · {producto}")
        agg = dia_scope_fuel.groupby("Distrito")["Precio_Soles_Galon"].mean().reset_index()
        render_ranked_list(agg, "Distrito")
        if not agg.empty:
            st.container(height=9, border=False)
            with st.expander(f"Ver los {len(agg)} distritos (menor a mayor)"):
                st.dataframe(
                    agg.sort_values("Precio_Soles_Galon").rename(columns={"Precio_Soles_Galon": "Precio (S/)"}).reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Distrito": st.column_config.TextColumn("Distrito", width="medium"),
                        "Precio (S/)": st.column_config.NumberColumn("Precio (S/)", width="small", format="%.2f"),
                    },
                )

# --- Fila 2: evaluación entre proveedores | evolución de precios ---
r2c1, r2c2 = st.columns(2)
with r2c1:
    with st.container(border=True, height=CARD_H_ROW2, key="card_prov"):
        accent_bar("#E94217")
        st.markdown(f"##### Evaluación entre proveedores · {producto}")
        prov_agg = (
            dia_scope_fuel.assign(Proveedor=dia_scope_fuel["Establecimiento"] + " · " + dia_scope_fuel["Distrito"])
            .groupby("Proveedor")["Precio_Soles_Galon"]
            .mean()
            .reset_index()
        )
        render_ranked_list(prov_agg, "Proveedor")
        if not prov_agg.empty:
            st.container(height=9, border=False)
            with st.expander(f"Ver los {len(prov_agg)} proveedores (menor a mayor)"):
                st.dataframe(
                    prov_agg.sort_values("Precio_Soles_Galon").rename(columns={"Precio_Soles_Galon": "Precio (S/)"}).reset_index(drop=True),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Proveedor": st.column_config.TextColumn("Proveedor", width="medium"),
                        "Precio (S/)": st.column_config.NumberColumn("Precio (S/)", width="small", format="%.2f"),
                    },
                )

with r2c2:
    with st.container(border=True, height=CARD_H_ROW2, key="card_evo"):
        accent_bar("#8F3D1A")
        top_row1, top_row2 = st.columns([3, 2])
        top_row1.markdown("##### Evolución de precios")
        granularidad = top_row2.selectbox("Granularidad", ["Diaria", "Semanal", "Mensual"], label_visibility="collapsed")

        fig = go.Figure()
        for prod in PRODUCTOS:
            d = df_scoped[df_scoped["Tipo_Combustible"] == prod].copy()
            d["Fecha"] = pd.to_datetime(d["Fecha"])
            serie = d.groupby("Fecha")["Precio_Soles_Galon"].mean().reset_index().sort_values("Fecha")
            if granularidad == "Semanal":
                serie = serie.set_index("Fecha").resample("W").mean().reset_index()
                serie["Label"] = "Sem " + serie["Fecha"].dt.isocalendar().week.astype(str)
                x_vals = serie["Label"]
            elif granularidad == "Mensual":
                serie = serie.set_index("Fecha").resample("ME").mean().reset_index()
                serie["Label"] = serie["Fecha"].dt.month.map(MESES_ABBR)
                x_vals = serie["Label"]
            else:
                x_vals = serie["Fecha"]
            if not serie.empty:
                fig.add_trace(
                    go.Scatter(
                        x=x_vals, y=serie["Precio_Soles_Galon"], mode="lines+markers",
                        name=prod, line=dict(color=COLOR_PRODUCTO[prod]),
                    )
                )
        if granularidad == "Diaria" and st.session_state.range_start:
            s = pd.Timestamp(st.session_state.range_start)
            e = pd.Timestamp(st.session_state.range_end or st.session_state.range_start)
            if s == e:
                fig.add_vline(x=s, line_dash="dash", line_color="gray")
            else:
                fig.add_vrect(x0=s, x1=e, fillcolor="gray", opacity=0.15, line_width=0)
        if granularidad == "Diaria":
            fig.update_xaxes(tickformat="%d/%m", dtick="D1")
        fig.update_layout(
            height=CHART_H, margin=dict(l=0, r=0, t=5, b=0), yaxis_title="S/ por galón", xaxis_title=None,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10)),
        )
        st.plotly_chart(fig, use_container_width=True, key="evo_chart")
