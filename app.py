import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="Volume & Rejection Rate Dashboard", layout="wide")

st.title("📦 Volume & Rejection Rate Dashboard")
st.markdown("Forecast vs Actual volumes with rejection rate trends")

# ── Load data ──────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    p12 = pd.read_excel("data/Past 12 months.xlsx")
    py  = pd.read_excel("data/Year Previous.xlsx")
    return p12, py

try:
    p12_raw, py_raw = load_data()
except FileNotFoundError:
    st.error(
        "Please place the two Excel files in the same directory as this script:\n"
        "- `1771993364194_Past_12_months.xlsx`\n"
        "- `1771993364194_Year_Previous.xlsx`"
    )
    st.stop()

ALL = "All"

# ── Sidebar filters (cascading) ────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")

    # ── Fiscal Year ──
    year_options = [ALL] + sorted(p12_raw["Fiscal Year"].unique().tolist())
    sel_year = st.selectbox("Fiscal Year", year_options, index=0)

    # Apply year filter to drive downstream options
    df_after_year = p12_raw if sel_year == ALL else p12_raw[p12_raw["Fiscal Year"] == sel_year]

    # ── Plant (cascades from year) ──
    plant_options = [ALL] + sorted(df_after_year["Plant"].unique().tolist())
    sel_plant = st.selectbox("Plant", plant_options, index=0)

    # Apply plant filter to drive category options
    df_after_plant = df_after_year if sel_plant == ALL else df_after_year[df_after_year["Plant"] == sel_plant]

    # ── Product Category (cascades from year + plant) ──
    cat_options = [ALL] + sorted(df_after_plant["Product Category"].unique().tolist())
    sel_cat = st.selectbox("Product Category", cat_options, index=0)

    # ── Fiscal Week Range ──
    all_weeks = sorted(p12_raw["Fiscal Week"].unique().tolist())
    week_range = st.select_slider(
        "Fiscal Week Range",
        options=all_weeks,
        value=(min(all_weeks), max(all_weeks))
    )

    st.divider()
    st.caption("Filters cascade: Plant options reflect selected Year; Category options reflect selected Plant.")

# ── Apply all filters to raw data ─────────────────────────────────────────────
def apply_filters(df, include_year=True):
    mask = df["Fiscal Week"].between(week_range[0], week_range[1])
    if include_year and sel_year != ALL:
        mask &= df["Fiscal Year"] == sel_year
    if sel_plant != ALL:
        mask &= df["Plant"] == sel_plant
    if sel_cat != ALL:
        mask &= df["Product Category"] == sel_cat
    return df[mask]

p12_filt = apply_filters(p12_raw, include_year=True)
py_filt  = apply_filters(py_raw,  include_year=False)  # prior year: no year filter

# ── Aggregate to fiscal week level ────────────────────────────────────────────
def agg_p12(df):
    grp = (
        df.groupby(["Fiscal Year", "Fiscal Week"], as_index=False)
        .agg(
            Actual      =("Actual Yield Kg",    "sum"),
            Forecast    =("Forecast Kg",        "sum"),
            RejectionKg =("Rejection Kg",       "sum"),
            OGW         =("Outer Gross Weight", "sum"),
        )
    )
    grp["Rejection_Rate"] = (grp["RejectionKg"] / grp["OGW"] * 100).where(grp["OGW"] > 0).round(2)
    grp["Label"] = "FY" + grp["Fiscal Year"].astype(int).astype(str) + " W" + grp["Fiscal Week"].astype(int).astype(str)
    return grp.sort_values(["Fiscal Year", "Fiscal Week"]).reset_index(drop=True)

def agg_py(df):
    grp = (
        df.groupby(["Fiscal Year", "Fiscal Week"], as_index=False)
        .agg(
            RejectionKg =("Rejection Kg",       "sum"),
            OGW         =("Outer Gross Weight", "sum"),
        )
    )
    grp["Rejection_Rate"] = (grp["RejectionKg"] / grp["OGW"] * 100).where(grp["OGW"] > 0).round(2)
    return grp

p12 = agg_p12(p12_filt)
py  = agg_py(py_filt)

if p12.empty:
    st.warning("⚠️ No data matches the current filters. Please adjust your selections.")
    st.stop()

# ── Active filter chips ────────────────────────────────────────────────────────
chips = []
chips.append(f"📅 Year: **{sel_year}**")
chips.append(f"🏭 Plant: **{sel_plant}**")
chips.append(f"🫐 Category: **{sel_cat}**")
chips.append(f"📆 Weeks: **{week_range[0]}–{week_range[1]}**")
st.markdown("  |  ".join(chips))

st.divider()

# ── KPI summary cards ──────────────────────────────────────────────────────────
total_actual   = p12["Actual"].sum()
total_forecast = p12["Forecast"].sum()
vol_attainment = (total_actual / total_forecast * 100) if total_forecast else 0
avg_reject     = (p12["RejectionKg"].sum() / p12["OGW"].sum() * 100) if p12["OGW"].sum() else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Actual Volume (kg)", f"{total_actual:,.0f}")
k2.metric("Total Forecast Volume (kg)", f"{total_forecast:,.0f}")
k3.metric("Volume Attainment", f"{vol_attainment:.1f}%")
k4.metric(
    "Avg Rejection Rate",
    f"{avg_reject:.2f}%",
    delta=f"{avg_reject - 2:.2f}% vs 2% target",
    delta_color="inverse"
)

st.divider()

# ── Chart ──────────────────────────────────────────────────────────────────────
fig = make_subplots(specs=[[{"secondary_y": True}]])

x_labels = p12["Label"].tolist()

fig.add_trace(go.Bar(
    x=x_labels, y=p12["Forecast"],
    name="Forecast Volume (kg)",
    marker_color="rgba(99, 155, 229, 0.6)",
    marker_line_color="rgba(99, 155, 229, 1)", marker_line_width=1,
), secondary_y=False)

fig.add_trace(go.Bar(
    x=x_labels, y=p12["Actual"],
    name="Actual Volume (kg)",
    marker_color="rgba(46, 196, 182, 0.75)",
    marker_line_color="rgba(46, 196, 182, 1)", marker_line_width=1,
), secondary_y=False)

fig.add_trace(go.Scatter(
    x=x_labels, y=p12["Rejection_Rate"],
    name="Actual Rejection Rate (%)",
    mode="lines+markers",
    line=dict(color="#e63946", width=2.5),
    marker=dict(size=7, symbol="circle"),
), secondary_y=True)

py_lookup  = py.groupby("Fiscal Week")["Rejection_Rate"].mean()
prev_rates = p12["Fiscal Week"].map(py_lookup).tolist()

fig.add_trace(go.Scatter(
    x=x_labels, y=prev_rates,
    name="Prior Year Rejection Rate (%)",
    mode="lines+markers",
    line=dict(color="#f4a261", width=2, dash="dash"),
    marker=dict(size=7, symbol="diamond"),
), secondary_y=True)

fig.add_trace(go.Scatter(
    x=x_labels, y=[2.0] * len(x_labels),
    name="2% Target",
    mode="lines",
    line=dict(color="#6d2b7a", width=1.8, dash="dot"),
    hoverinfo="skip",
), secondary_y=True)

fig.update_layout(
    barmode="group",
    title=dict(text="Weekly Forecast vs Actual Volume with Rejection Rates", font=dict(size=18)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
    plot_bgcolor="rgba(250,250,252,1)",
    paper_bgcolor="white",
    height=560,
    margin=dict(l=60, r=60, t=80, b=100),
    xaxis=dict(tickangle=-45, tickfont=dict(size=10), gridcolor="rgba(220,220,220,0.4)"),
)
fig.update_yaxes(title_text="Volume (kg)", secondary_y=False, gridcolor="rgba(220,220,220,0.4)", tickformat=",")
fig.update_yaxes(title_text="Rejection Rate (%)", secondary_y=True, gridcolor=None, ticksuffix="%")

st.plotly_chart(fig, use_container_width=True)

# ── Data table ────────────────────────────────────────────────────────────────
with st.expander("📊 View underlying data"):
    display = p12[["Label", "Fiscal Year", "Fiscal Week", "Forecast", "Actual", "RejectionKg", "OGW", "Rejection_Rate"]].copy()
    display.columns = ["Label", "Fiscal Year", "Fiscal Week", "Forecast (kg)", "Actual (kg)", "Rejection (kg)", "OGW (kg)", "Rejection Rate (%)"]
    st.dataframe(display.style.format({
        "Forecast (kg)": "{:,.0f}", "Actual (kg)": "{:,.0f}",
        "Rejection (kg)": "{:,.1f}", "OGW (kg)": "{:,.1f}",
        "Rejection Rate (%)": "{:.2f}%",
    }), use_container_width=True)

st.caption("Data sources: Past 12 Months & Year Previous Excel files · 2% rejection rate target shown as dotted line")
