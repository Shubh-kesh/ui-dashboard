"""Plotly figure builders. Kept separate from app.py so chart styling changes
don't touch data-fetch or aggregation logic."""

import plotly.express as px
import pandas as pd


def volume_trend_figure(daily_df: pd.DataFrame):
    fig = px.bar(daily_df, x="DATE", y="COUNT", title="Transaction Volume by Date")
    fig.update_layout(xaxis_title="Date", yaxis_title="Transactions")
    return fig


def stage_status_figure(breakdown_df: pd.DataFrame, stage_name: str):
    fig = px.bar(
        breakdown_df,
        x="DATE",
        y="COUNT",
        color="STATUS",
        title=f"{stage_name} Status by Date",
        barmode="stack",
    )
    fig.update_layout(xaxis_title="Date", yaxis_title="Count")
    return fig


def funnel_figure(funnel_df: pd.DataFrame):
    fig = px.funnel(funnel_df, x="COUNT", y="STAGE", title="Pipeline Completion Funnel")
    return fig


def latency_box_figure(latency_long_df: pd.DataFrame):
    fig = px.box(
        latency_long_df,
        x="STAGE",
        y="DURATION",
        title="Response Latency by Stage",
        points=False,
    )
    fig.update_layout(xaxis_title="Stage", yaxis_title="Duration (sec)")
    return fig
