"""
ui-dashboard: Streamlit app for tracking blink / head-nod / authenticity /
image-seg / verify-token / callback status from the uidb-backed catalog table.

Run: streamlit run app.py
"""

from datetime import date, timedelta

import streamlit as st

import uidb_client
import metrics
import charts
import fraud_metrics

st.set_page_config(page_title="LivePhoto Status Dashboard", layout="wide")

# --- Sidebar: filters + manual refresh ---------------------------------
st.sidebar.header("Filters")

default_start = date.today() - timedelta(days=7)
start_date = st.sidebar.date_input("Start date", value=default_start)
end_date = st.sidebar.date_input("End date", value=date.today())

source_options = ["All"]
try:
    source_options += uidb_client.fetch_distinct_sources()
except Exception as e:
    st.sidebar.warning(f"Could not load SOURCE list: {e}")

selected_source = st.sidebar.selectbox("Source", source_options)
source_filter = None if selected_source == "All" else selected_source

refresh_clicked = st.sidebar.button("🔄 Refresh", type="primary", use_container_width=True)

if "df" not in st.session_state:
    st.session_state["df"] = None
    st.session_state["last_refreshed"] = None

if refresh_clicked or st.session_state["df"] is None:
    if start_date > end_date:
        st.sidebar.error("Start date must be before end date.")
    else:
        with st.spinner("Fetching from uidb..."):
            try:
                st.session_state["df"] = uidb_client.fetch_txn_data(
                    start_date, end_date, source=source_filter
                )
                st.session_state["last_refreshed"] = date.today()
            except Exception as e:
                st.sidebar.error(f"Fetch failed: {e}")

df = st.session_state["df"]

st.title("LivePhoto / KYC Status Dashboard")

if df is None or df.empty:
    st.info("No data loaded yet. Set your filters and click Refresh.")
    st.stop()

st.caption(f"{len(df)} rows loaded · {start_date} to {end_date} · source: {selected_source}")

# --- KPI row -------------------------------------------------------------
kpis = metrics.kpi_summary(df)
k1, k2, k3 = st.columns(3)
k1.metric("Total Transactions", kpis["total_txns"])
k2.metric(
    "Callback Success Rate",
    f"{kpis['callback_success_rate']}%" if kpis["callback_success_rate"] is not None else "—",
)
k3.metric(
    "Avg Callback Latency",
    f"{kpis['avg_callback_latency']}s" if kpis["avg_callback_latency"] is not None else "—",
)

st.divider()

# --- Volume trend ----------------------------------------------------------
st.plotly_chart(charts.volume_trend_figure(metrics.daily_volume(df)), use_container_width=True)

# --- Funnel ------------------------------------------------------------
st.plotly_chart(charts.funnel_figure(metrics.funnel_counts(df)), use_container_width=True)

# --- Per-stage status breakdown (tabs) ----------------------------------
st.subheader("Status by Stage")
stage_tabs = st.tabs(list(metrics.STAGES.keys()))
for tab, stage_name in zip(stage_tabs, metrics.STAGES.keys()):
    with tab:
        breakdown = metrics.stage_status_breakdown(df, stage_name)
        if breakdown.empty:
            st.write("No data for this stage in the selected range.")
        else:
            st.plotly_chart(
                charts.stage_status_figure(breakdown, stage_name), use_container_width=True
            )

# --- Latency ---------------------------------------------------------------
st.subheader("Latency")
lat_stats = metrics.latency_stats(df)
if not lat_stats.empty:
    st.dataframe(lat_stats, use_container_width=True, hide_index=True)
    st.plotly_chart(charts.latency_box_figure(metrics.latency_raw_long(df)), use_container_width=True)
else:
    st.write("No latency data available for the selected range.")

# --- Exceptions --------------------------------------------------------
st.subheader("Exceptions")
exc = metrics.exception_rows(df)
if exc.empty:
    st.success("No exceptions in the selected range.")
else:
    st.dataframe(exc, use_container_width=True, hide_index=True)

# --- Raw data ------------------------------------------------------------
with st.expander("Raw data"):
    st.dataframe(df, use_container_width=True)
    st.download_button(
        "Download CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"catalog_{start_date}_{end_date}.csv",
        mime="text/csv",
    )

st.divider()

# --- Attempt / Fraud Pattern Analysis -------------------------------------
# Independent of the date-range filter above: runs its own aggregate SQL
# against the full history for one SOURCE.
st.subheader("Attempt / Fraud Pattern Analysis")
st.caption(
    "Groups attempts by the part of TXN_ID before the first '_' (one user's "
    "journey), using the number after the final '~' as the attempt number. "
    "Flags users with rapid-fire retries (burst pattern) -- suggestive of "
    "scripted/bot attempts rather than a human manually retrying."
)

fraud_sources = [s for s in source_options if s != "All"]
if not fraud_sources:
    st.info("No sources available to analyze.")
else:
    fraud_source = st.selectbox("Source to analyze", fraud_sources, key="fraud_source")

    c1, c2 = st.columns(2)
    with c1:
        burst_gap_seconds = st.number_input(
            "Burst gap: attempts within N seconds of each other",
            min_value=1, value=5, step=1,
        )
    with c2:
        min_burst_pairs = st.number_input(
            "Flag as suspected bot: at least N such rapid pairs",
            min_value=1, value=3, step=1,
        )

    if st.button("Run Attempt Analysis"):
        with st.spinner("Running attempt-pattern queries..."):
            try:
                st.session_state["fraud_total_users"] = fraud_metrics.fetch_total_users(
                    fraud_source
                )
                st.session_state["fraud_burst_cases"] = fraud_metrics.fetch_burst_cases(
                    fraud_source, burst_gap_seconds, min_burst_pairs
                )
            except Exception as e:
                st.error(f"Attempt analysis failed: {e}")

    total_users = st.session_state.get("fraud_total_users")
    burst_cases = st.session_state.get("fraud_burst_cases")

    if total_users is not None:
        st.caption(f"{total_users} unique users (BASE_TXN_ID) found for {fraud_source}")

        if burst_cases is not None:
            pct = round(100 * len(burst_cases) / total_users, 2) if total_users else 0.0
            st.metric(
                f"Suspected bot/burst (\u2265{min_burst_pairs} pairs \u2264{burst_gap_seconds}s apart)",
                f"{pct}%",
                help=f"{len(burst_cases)} of {total_users} users",
            )

            st.markdown("**Suspected fraud \u2014 burst/velocity pattern**")
            if burst_cases.empty:
                st.write("No users matched this pattern.")
            else:
                st.dataframe(burst_cases, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download CSV (burst pattern)",
                    burst_cases.to_csv(index=False).encode("utf-8"),
                    file_name=f"fraud_burst_pattern_{fraud_source}.csv",
                    mime="text/csv",
                    key="dl_burst",
                )
