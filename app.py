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
    cal = pd.read_excel("data/Berries Fiscal Calendar.xlsx", sheet_name="Sheet2")
    return p12, py, cal

try:
    p12_raw, py_raw, cal_raw = load_data()
except FileNotFoundError:
    st.error(
        "Please place files in the data/ folder:\n"
        "- `data/Past 12 months.xlsx`\n"
        "- `data/Year Previous.xlsx`\n"
        "- `data/Berries Fiscal Calendar.xlsx`"
    )
    st.stop()

# ── Build Fiscal Week -> Fiscal Month lookup from official calendar ─────────────
# Must join on BOTH Fiscal Year + Fiscal Week because some week numbers
# fall in different months depending on the year (leap/53-week years).
week_month_lookup = (
    cal_raw
    .groupby(["Fiscal Year", "Fiscal Week"])["Fiscal Month"]
    .first()
    .reset_index()
    .rename(columns={"Fiscal Month": "Fiscal Month Name"})
)

MONTH_ORDER = [
    "January","February","March","April","May","June",
    "July","August","September","October","November","December"
]

def attach_fiscal_month(df):
    df = df.copy()
    df["Fiscal Year"] = pd.to_numeric(df["Fiscal Year"], errors="coerce")
    df["Fiscal Week"] = pd.to_numeric(df["Fiscal Week"], errors="coerce")
    df = df.merge(week_month_lookup, on=["Fiscal Year","Fiscal Week"], how="left")
    # Fallback for any unmatched weeks
    mask = df["Fiscal Month Name"].isna()
    if mask.any():
        fallback = ((df.loc[mask, "Fiscal Week"] - 1) // 4 + 1).clip(1, 12)
        df.loc[mask, "Fiscal Month Name"] = fallback.map(dict(enumerate(MONTH_ORDER, 1)))
    return df

p12_raw = attach_fiscal_month(p12_raw)
py_raw  = attach_fiscal_month(py_raw)

ALL = "All"

# ── Sidebar filters (cascading) ────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")

    year_options = [ALL] + sorted(p12_raw["Fiscal Year"].dropna().unique().tolist())
    sel_year = st.selectbox("Fiscal Year", year_options, index=0)
    df_after_year = p12_raw if sel_year == ALL else p12_raw[p12_raw["Fiscal Year"] == sel_year]

    plant_options = [ALL] + sorted(df_after_year["Plant"].unique().tolist())
    sel_plant = st.selectbox("Plant", plant_options, index=0)
    df_after_plant = df_after_year if sel_plant == ALL else df_after_year[df_after_year["Plant"] == sel_plant]

    cat_options = [ALL] + sorted(df_after_plant["Product Category"].unique().tolist())
    sel_cat = st.selectbox("Product Category", cat_options, index=0)
    df_after_cat = df_after_plant if sel_cat == ALL else df_after_plant[df_after_plant["Product Category"] == sel_cat]

    # ── Fiscal Month filter — from official calendar, cascades from above ──────
    avail_months_raw = df_after_cat["Fiscal Month Name"].dropna().unique().tolist()
    avail_months = [m for m in MONTH_ORDER if m in avail_months_raw]
    sel_month = st.selectbox("Fiscal Month", [ALL] + avail_months, index=0)

    all_weeks = sorted(p12_raw["Fiscal Week"].dropna().unique().tolist())
    week_range = st.select_slider(
        "Fiscal Week Range",
        options=all_weeks,
        value=(min(all_weeks), max(all_weeks))
    )

    st.divider()
    st.caption("Month sourced from Berries Fiscal Calendar. Filters cascade top-down.")

# ── Apply all filters ─────────────────────────────────────────────────────────
def apply_filters(df, include_year=True):
    mask = df["Fiscal Week"].between(week_range[0], week_range[1])
    if include_year and sel_year != ALL:
        mask &= df["Fiscal Year"] == sel_year
    if sel_plant != ALL:
        mask &= df["Plant"] == sel_plant
    if sel_cat != ALL:
        mask &= df["Product Category"] == sel_cat
    if sel_month != ALL:
        mask &= df["Fiscal Month Name"] == sel_month
    return df[mask]

p12_filt = apply_filters(p12_raw, include_year=True)
py_filt  = apply_filters(py_raw,  include_year=False)

# ── Aggregate to fiscal week level ────────────────────────────────────────────
def agg_p12(df):
    grp = (
        df.groupby(["Fiscal Year", "Fiscal Week", "Fiscal Month Name"], as_index=False)
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
chips = [
    f"📅 Year: **{sel_year}**",
    f"🏭 Plant: **{sel_plant}**",
    f"🫐 Category: **{sel_cat}**",
    f"📆 Month: **{sel_month}**",
    f"🗓 Weeks: **{week_range[0]}–{week_range[1]}**",
]
st.markdown("  |  ".join(chips))
st.divider()

# ── KPI cards ─────────────────────────────────────────────────────────────────
total_actual   = p12["Actual"].sum()
total_forecast = p12["Forecast"].sum()
vol_attainment = (total_actual / total_forecast * 100) if total_forecast else 0
avg_reject     = (p12["RejectionKg"].sum() / p12["OGW"].sum() * 100) if p12["OGW"].sum() else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Total Actual Volume (kg)", f"{total_actual:,.0f}")
k2.metric("Total Forecast Volume (kg)", f"{total_forecast:,.0f}")
k3.metric("Volume Attainment", f"{vol_attainment:.1f}%")
k4.metric("Avg Rejection Rate", f"{avg_reject:.2f}%",
          delta=f"{avg_reject - 2:.2f}% vs 2% target", delta_color="inverse")
st.divider()

# ── Weekly chart ───────────────────────────────────────────────────────────────
fig = make_subplots(specs=[[{"secondary_y": True}]])
x_labels = p12["Label"].tolist()

fig.add_trace(go.Bar(
    x=x_labels, y=p12["Forecast"], name="Forecast Volume (kg)",
    marker_color="rgba(99,155,229,0.6)", marker_line_color="rgba(99,155,229,1)", marker_line_width=1,
), secondary_y=False)

fig.add_trace(go.Bar(
    x=x_labels, y=p12["Actual"], name="Actual Volume (kg)",
    marker_color="rgba(46,196,182,0.75)", marker_line_color="rgba(46,196,182,1)", marker_line_width=1,
), secondary_y=False)

fig.add_trace(go.Scatter(
    x=x_labels, y=p12["Rejection_Rate"], name="Actual Rejection Rate (%)",
    mode="lines+markers", line=dict(color="#e63946", width=2.5), marker=dict(size=7),
), secondary_y=True)

py_lookup  = py.groupby("Fiscal Week")["Rejection_Rate"].mean()
prev_rates = p12["Fiscal Week"].map(py_lookup).tolist()
fig.add_trace(go.Scatter(
    x=x_labels, y=prev_rates, name="Prior Year Rejection Rate (%)",
    mode="lines+markers", line=dict(color="#f4a261", width=2, dash="dash"),
    marker=dict(size=7, symbol="diamond"),
), secondary_y=True)

fig.add_trace(go.Scatter(
    x=x_labels, y=[2.0]*len(x_labels), name="2% Target",
    mode="lines", line=dict(color="#6d2b7a", width=1.8, dash="dot"), hoverinfo="skip",
), secondary_y=True)

fig.update_layout(
    barmode="group",
    title=dict(text="Weekly Forecast vs Actual Volume with Rejection Rates", font=dict(size=18)),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified", plot_bgcolor="rgba(250,250,252,1)", paper_bgcolor="white",
    height=560, margin=dict(l=60,r=60,t=80,b=100),
    xaxis=dict(tickangle=-45, tickfont=dict(size=10), gridcolor="rgba(220,220,220,0.4)"),
)
fig.update_yaxes(title_text="Volume (kg)", secondary_y=False,
                 gridcolor="rgba(220,220,220,0.4)", tickformat=",")
fig.update_yaxes(title_text="Rejection Rate (%)", secondary_y=True,
                 gridcolor=None, ticksuffix="%")
st.plotly_chart(fig, use_container_width=True)

# ── Monthly Yield Kg Table ─────────────────────────────────────────────────────
st.subheader("📅 Monthly Yield Kg Summary")

monthly = (
    p12_filt
    .groupby(["Fiscal Year", "Fiscal Month Name"], as_index=False)
    .agg(
        Actual_Yield_Kg=("Actual Yield Kg", "sum"),
        Forecast_Kg    =("Forecast Kg",     "sum"),
    )
)
monthly["Variance_Kg"]  = monthly["Actual_Yield_Kg"] - monthly["Forecast_Kg"]
monthly["Attainment_%"] = (
    (monthly["Actual_Yield_Kg"] / monthly["Forecast_Kg"] * 100)
    .where(monthly["Forecast_Kg"] > 0).round(1)
)
monthly["Month_Sort"] = monthly["Fiscal Month Name"].map(
    {m: i for i, m in enumerate(MONTH_ORDER)}
)
monthly = monthly.sort_values(["Fiscal Year","Month_Sort"]).drop(columns="Month_Sort")

# Pivot: rows = Fiscal Year, columns = Month, values = Actual Yield Kg
avail_month_cols = [m for m in MONTH_ORDER if m in monthly["Fiscal Month Name"].unique()]
pivot = (
    monthly
    .pivot_table(index="Fiscal Year", columns="Fiscal Month Name",
                 values="Actual_Yield_Kg", aggfunc="sum")
    .reindex(columns=avail_month_cols)
)
pivot.index = pivot.index.astype(int).astype(str)
pivot.index.name = "Fiscal Year"
pivot["TOTAL"] = pivot.sum(axis=1)

st.markdown("**Actual Yield Kg — by Fiscal Month** *(colour scale: low=red → high=green)*")
value_cols = [c for c in pivot.columns if c != "TOTAL"]

def colour_monthly(df):
    """
    Matplotlib-free row-wise red→yellow→green colouring.
    Works on Streamlit Cloud where matplotlib is not installed.
    """
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for idx in df.index:
        row = df.loc[idx, value_cols].dropna()
        if row.empty:
            continue
        lo, hi = row.min(), row.max()
        rng = hi - lo if hi != lo else 1
        for col in value_cols:
            if pd.isna(df.loc[idx, col]):
                continue
            t = (df.loc[idx, col] - lo) / rng   # 0 = low (red), 1 = high (green)
            if t < 0.5:
                # red -> yellow
                r, g, b = 220, int(t * 2 * 200), 50
            else:
                # yellow -> green
                r, g, b = int((1 - t) * 2 * 200), 180, 50
            styles.loc[idx, col] = f"background-color: rgb({r},{g},{b}); color: #111; text-align: right; font-size:13px"
        styles.loc[idx, "TOTAL"] = "font-weight: bold; text-align: right; font-size:13px"
    return styles

st.dataframe(
    pivot.style
        .format("{:,.2f}", na_rep="-")
        .apply(colour_monthly, axis=None),
    use_container_width=True,
    height=min(80 + len(pivot) * 38, 420),
)

# Detailed breakdown expander
with st.expander("📊 Monthly Detail — Actual vs Forecast vs Variance"):
    disp = monthly.rename(columns={
        "Fiscal Month Name": "Month",
        "Actual_Yield_Kg":   "Actual Yield (kg)",
        "Forecast_Kg":       "Forecast (kg)",
        "Variance_Kg":       "Variance (kg)",
        "Attainment_%":      "Attainment %",
    })
    disp["Fiscal Year"] = disp["Fiscal Year"].astype(int)
    st.dataframe(
        disp[["Fiscal Year","Month","Actual Yield (kg)","Forecast (kg)","Variance (kg)","Attainment %"]]
        .style.format({
            "Actual Yield (kg)": "{:,.0f}",
            "Forecast (kg)":     "{:,.0f}",
            "Variance (kg)":     "{:+,.0f}",
            "Attainment %":      "{:.1f}%",
        }).map(
            lambda v: "color: #c0392b; font-weight:bold" if isinstance(v,(int,float)) and v < 0 else "",
            subset=["Variance (kg)"]
        ),
        use_container_width=True,
    )

# ── Weekly data table ─────────────────────────────────────────────────────────
with st.expander("📊 View weekly underlying data"):
    disp_w = p12[["Label","Fiscal Year","Fiscal Week","Fiscal Month Name",
                   "Forecast","Actual","RejectionKg","OGW","Rejection_Rate"]].copy()
    disp_w.columns = ["Label","Fiscal Year","Fiscal Week","Fiscal Month",
                       "Forecast (kg)","Actual (kg)","Rejection (kg)","OGW (kg)","Rejection Rate (%)"]
    st.dataframe(disp_w.style.format({
        "Forecast (kg)":      "{:,.0f}",
        "Actual (kg)":        "{:,.0f}",
        "Rejection (kg)":     "{:,.1f}",
        "OGW (kg)":           "{:,.1f}",
        "Rejection Rate (%)": "{:.2f}%",
    }), use_container_width=True)

st.caption("Month mapping sourced from official Berries Fiscal Calendar · 2% rejection target shown as dotted line")
