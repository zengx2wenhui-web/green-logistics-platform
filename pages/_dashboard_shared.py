"""Shared dashboard helpers for themed comparison pages."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from utils.comparison_scenarios import SCENARIO_LABELS, SCENARIO_ORDER


SCENARIO_COLOR_MAP = {
    "baseline_direct": "#D94841",
    "diesel_same_routes": "#C97C5D",
    "optimized_current": "#80B332",
}

_DEFAULT_SCENARIO_COLOR = "#2F6BFF"


def inject_green_dashboard_style(page_prefix: str) -> None:
    """Inject the green dashboard theme used across analytics pages."""
    safe_prefix = str(page_prefix or "").strip().replace("_", "-")
    st.markdown(
        f"""
        <style>
        .stApp {{ background: #dfe7d6; }}
        .block-container {{
            max-width: 1240px;
            padding-top: 1.25rem;
            padding-left: 3rem;
            padding-right: 3rem;
            padding-bottom: 4rem;
        }}
        .block-container h1 {{
            margin: 0.35rem 0 0.25rem;
            font-size: 3.2rem;
            font-weight: 700;
            color: #111111;
            letter-spacing: -0.02em;
        }}
        .block-container p {{
            color: #111111;
            font-size: 1.05rem;
        }}
        div[class*="st-key-{safe_prefix}-card"],
        div[class*="st-key-{safe_prefix}-panel"] {{
            background: linear-gradient(135deg, rgba(223, 239, 188, 0.94) 0%, rgba(214, 234, 174, 0.92) 100%);
            border: 1px solid #d0e2b4;
            border-radius: 28px;
            padding: 1.55rem 1.7rem 1.65rem;
            box-shadow: 0 8px 24px rgba(123, 145, 91, 0.22);
            margin-top: 1.25rem;
            overflow: hidden;
        }}
        div[class*="st-key-{safe_prefix}-card"] > div,
        div[class*="st-key-{safe_prefix}-panel"] > div {{
            gap: 0.95rem;
        }}
        div[class*="st-key-{safe_prefix}-card"] h3,
        div[class*="st-key-{safe_prefix}-panel"] h3 {{
            font-size: 1.95rem;
            font-weight: 700;
            color: #111111;
            margin-bottom: 0.15rem;
        }}
        [data-testid="stHorizontalBlock"] {{ gap: 1rem; }}
        div[data-testid="stAlert"] {{
            border-radius: 18px !important;
            border: 0 !important;
        }}
        div[data-testid="stDataFrame"] {{
            background: rgba(255, 255, 255, 0.95) !important;
            border-radius: 18px !important;
            overflow: hidden !important;
        }}
        div[data-testid="stMetric"] {{
            background: transparent !important;
            border: 0 !important;
            padding: 0.1rem 0 !important;
        }}
        div[data-testid="stMetric"] label {{
            color: #111111 !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
        }}
        div[data-testid="stMetricValue"] {{
            color: #111111 !important;
            font-size: 2rem !important;
            font-weight: 700 !important;
        }}
        div[data-testid="stPlotlyChart"] {{
            background: transparent !important;
            border-radius: 18px !important;
            overflow: hidden;
        }}
        div[data-testid="stExpander"] {{
            border-radius: 18px !important;
            overflow: hidden;
            border: 1px solid rgba(0, 0, 0, 0.06) !important;
            background: rgba(255, 255, 255, 0.55) !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 0.45rem;
            padding-bottom: 0.3rem;
        }}
        .stTabs [data-baseweb="tab"] {{
            background: rgba(255, 255, 255, 0.58);
            border-radius: 14px 14px 0 0;
            padding: 0.55rem 1rem;
        }}
        .stTabs [aria-selected="true"] {{
            background: rgba(255, 255, 255, 0.92);
        }}
        div[data-baseweb="select"] > div {{
            border-radius: 14px !important;
        }}
        .stButton > button,
        .stDownloadButton > button {{
            height: 3rem !important;
            border-radius: 14px !important;
            font-size: 1.02rem !important;
            border: 0 !important;
            box-shadow: 0 5px 13px rgba(0, 0, 0, 0.18) !important;
        }}
        .stButton > button[kind="primary"] {{
            background: #2cb46d !important;
            color: #ffffff !important;
        }}
        .stDownloadButton > button,
        .stButton > button:not([kind="primary"]) {{
            background: #ffffff !important;
            color: #111111 !important;
        }}
        @media (max-width: 900px) {{
            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
                padding-bottom: 3rem;
            }}
            .block-container h1 {{
                font-size: 2.55rem;
            }}
            div[class*="st-key-{safe_prefix}-card"],
            div[class*="st-key-{safe_prefix}-panel"] {{
                padding: 1.2rem 1rem 1.35rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_green_chart_theme(
    fig: go.Figure,
    *,
    height: int = 380,
    showlegend: bool = True,
    legend_orientation: str = "h",
    legend_x: float = 1.0,
    legend_y: float = 1.02,
    legend_xanchor: str = "right",
    legend_yanchor: str = "bottom",
    top_margin: int = 72,
    bottom_margin: int = 18,
    left_margin: int = 18,
    right_margin: int = 18,
) -> go.Figure:
    """Apply the app's chart theme to a Plotly figure."""
    legend = {
        "orientation": legend_orientation,
        "yanchor": legend_yanchor,
        "y": legend_y,
        "xanchor": legend_xanchor,
        "x": legend_x,
        "bgcolor": "rgba(255,255,255,0.55)",
    }
    fig.update_layout(
        height=height,
        showlegend=showlegend,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,0.68)",
        margin={"l": left_margin, "r": right_margin, "t": top_margin, "b": bottom_margin},
        font={"family": "Microsoft YaHei, Segoe UI, sans-serif", "color": "#18311A"},
        title={"x": 0.02, "xanchor": "left", "font": {"size": 20, "color": "#18311A"}},
        legend=legend,
        hoverlabel={"bgcolor": "#F7FAF2", "font": {"color": "#18311A"}},
    )
    fig.update_xaxes(
        showgrid=False,
        linecolor="rgba(24,49,26,0.18)",
        tickfont={"color": "#18311A"},
        title_font={"color": "#18311A"},
    )
    fig.update_yaxes(
        gridcolor="rgba(24,49,26,0.08)",
        zeroline=False,
        tickfont={"color": "#18311A"},
        title_font={"color": "#18311A"},
    )
    return fig


def _iter_plot_values(raw_values: object) -> list[object]:
    if raw_values is None:
        return []
    if isinstance(raw_values, (str, bytes)):
        return [raw_values]
    try:
        return list(raw_values)
    except TypeError:
        return [raw_values]


def _chunk_axis_label(text: object, *, chunk_size: int) -> str:
    value = str(text or "").strip()
    if not value or chunk_size <= 0 or len(value) <= chunk_size:
        return value
    return "<br>".join(value[idx : idx + chunk_size] for idx in range(0, len(value), chunk_size))


def _format_wrapped_category_label(label: object, *, chunk_size: int) -> str:
    raw_label = str(label or "").strip()
    if not raw_label:
        return ""

    for separator in (" -> ", "\u2192", "->"):
        if separator in raw_label:
            left, right = raw_label.split(separator, 1)
            return f"{_chunk_axis_label(left, chunk_size=chunk_size)}<br>-><br>{_chunk_axis_label(right, chunk_size=chunk_size)}"

    return _chunk_axis_label(raw_label, chunk_size=chunk_size)


def wrap_categorical_axis_labels(
    fig: go.Figure,
    *,
    axis: str = "x",
    chunk_size: int = 10,
) -> go.Figure:
    """Wrap long categorical tick labels onto multiple lines."""
    axis_name = str(axis or "x").strip().lower()
    if axis_name not in {"x", "y"}:
        return fig

    tickvals: list[object] = []
    for trace in fig.data:
        values = getattr(trace, axis_name, None)
        for value in _iter_plot_values(values):
            if value is None:
                continue
            try:
                if pd.isna(value):
                    continue
            except TypeError:
                pass
            if value not in tickvals:
                tickvals.append(value)

    if not tickvals:
        return fig

    axis_kwargs = {
        "tickmode": "array",
        "tickvals": tickvals,
        "ticktext": [_format_wrapped_category_label(value, chunk_size=chunk_size) for value in tickvals],
        "automargin": True,
    }
    if axis_name == "x":
        fig.update_xaxes(**axis_kwargs)
    else:
        fig.update_yaxes(**axis_kwargs)
    return fig


def tune_bar_value_labels(
    fig: go.Figure,
    *,
    orientation: str = "v",
    headroom_ratio: float = 0.18,
) -> go.Figure:
    """Move bar labels outside and reserve enough headroom to avoid overlap."""
    max_value = 0.0
    is_horizontal = str(orientation).lower().startswith("h")

    for trace in fig.data:
        if getattr(trace, "type", "") != "bar":
            continue
        trace.textposition = "outside"
        trace.cliponaxis = False
        values = trace.x if is_horizontal else trace.y
        for value in _iter_plot_values(values):
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                continue
            if pd.isna(numeric_value):
                continue
            max_value = max(max_value, numeric_value)

    if max_value <= 0:
        return fig

    axis_max = max_value * (1 + max(headroom_ratio, 0.08))
    if is_horizontal:
        fig.update_xaxes(range=[0, axis_max])
    else:
        fig.update_yaxes(range=[0, axis_max])
    return fig


def build_scenario_summary_dataframe(comparison_scenarios: list[dict]) -> pd.DataFrame:
    """Build a normalized comparison dataframe for scenario-level charts."""
    if not comparison_scenarios:
        return pd.DataFrame()

    baseline_emission = 0.0
    for scenario in comparison_scenarios:
        if str(scenario.get("id") or "").strip() == "baseline_direct":
            baseline_emission = float(scenario.get("total_emission", 0) or 0)
            break
    if baseline_emission <= 0:
        baseline_emission = float(comparison_scenarios[0].get("total_emission", 0) or 0)

    rows = []
    for scenario in comparison_scenarios:
        scenario_id = str(scenario.get("id") or "").strip()
        total_emission = float(scenario.get("total_emission", 0) or 0)
        reduction_kg = float(
            scenario.get(
                "reduction_vs_baseline",
                baseline_emission - total_emission,
            )
            or 0
        )
        reduction_pct = float(
            scenario.get(
                "reduction_vs_baseline_pct",
                (reduction_kg / baseline_emission * 100) if baseline_emission > 0 else 0.0,
            )
            or 0
        )
        rows.append(
            {
                "方案ID": scenario_id,
                "方案": str(scenario.get("label") or scenario_id or "未命名方案"),
                "总碳排放(kg CO2)": round(total_emission, 2),
                "总距离(km)": round(float(scenario.get("total_distance_km", 0) or 0), 2),
                "末端距离(km)": round(float(scenario.get("terminal_distance_km", 0) or 0), 2),
                "干线距离(km)": round(float(scenario.get("trunk_distance_km", 0) or 0), 2),
                "末端碳排(kg CO2)": round(float(scenario.get("terminal_emission", 0) or 0), 2),
                "干线碳排(kg CO2)": round(float(scenario.get("trunk_emission", 0) or 0), 2),
                "车辆数": int(scenario.get("num_vehicles_used", 0) or 0),
                "中转枢纽数": len(list(scenario.get("depot_results", []) or [])),
                "车队构成": str(scenario.get("fleet_mix_text") or ""),
                "减排量(kg CO2)": round(reduction_kg, 2),
                "减排比例(%)": round(reduction_pct, 1),
            }
        )

    scenario_df = pd.DataFrame(rows)
    if scenario_df.empty:
        return scenario_df

    scenario_df["_sort"] = scenario_df["方案ID"].apply(
        lambda scenario_id: SCENARIO_ORDER.index(scenario_id) if scenario_id in SCENARIO_ORDER else len(SCENARIO_ORDER)
    )
    scenario_df = scenario_df.sort_values(["_sort", "方案ID"]).drop(columns="_sort").reset_index(drop=True)
    return scenario_df


def render_scenario_triptych(scenario_df: pd.DataFrame) -> None:
    """Render the three-scenario summary row as fixed three columns."""
    scenario_map = {
        str(row.get("方案ID") or ""): row
        for row in scenario_df.to_dict("records")
    }
    cols = st.columns(3)
    for idx, scenario_id in enumerate(SCENARIO_ORDER):
        row = scenario_map.get(scenario_id)
        with cols[idx]:
            st.markdown(f"#### {SCENARIO_LABELS.get(scenario_id, scenario_id)}")
            if not row:
                st.info("当前结果尚未生成该方案，请重新执行路径优化后查看。")
                continue

            reduction_pct = float(row.get("减排比例(%)", 0) or 0)
            if scenario_id == "baseline_direct":
                delta_text = "基准对照"
            else:
                delta_prefix = "-" if reduction_pct > 0 else "+"
                delta_text = f"较基线 {delta_prefix}{abs(reduction_pct):.1f}%"

            st.metric("总碳排放", f"{float(row.get('总碳排放(kg CO2)', 0) or 0):,.2f} kg CO2", delta=delta_text)
            st.caption(
                f"总距离 {float(row.get('总距离(km)', 0) or 0):,.2f} km | "
                f"车辆 {int(row.get('车辆数', 0) or 0)} 辆 | "
                f"枢纽 {int(row.get('中转枢纽数', 0) or 0)} 个"
            )


def build_scenario_emission_figure(
    scenario_df: pd.DataFrame,
    *,
    title: str = "三方案碳排放对比",
) -> go.Figure:
    """Build the primary emissions comparison chart."""
    fig = go.Figure()
    if scenario_df.empty:
        return apply_green_chart_theme(fig, height=400, showlegend=False)

    colors = [
        SCENARIO_COLOR_MAP.get(str(scenario_id or ""), _DEFAULT_SCENARIO_COLOR)
        for scenario_id in scenario_df["方案ID"]
    ]
    y_max = max(float(value or 0) for value in scenario_df["总碳排放(kg CO2)"])
    fig.add_bar(
        x=scenario_df["方案"],
        y=scenario_df["总碳排放(kg CO2)"],
        marker={"color": colors, "line": {"color": "rgba(17,17,17,0.08)", "width": 1}},
        text=[f"{float(value):,.2f}" for value in scenario_df["总碳排放(kg CO2)"]],
        textposition="outside",
        cliponaxis=False,
        customdata=scenario_df[
            [
                "总距离(km)",
                "减排量(kg CO2)",
                "减排比例(%)",
                "车辆数",
                "中转枢纽数",
            ]
        ].values,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "总碳排放：%{y:,.2f} kg CO2<br>"
            "总距离：%{customdata[0]:,.2f} km<br>"
            "较基线减排：%{customdata[1]:,.2f} kg CO2<br>"
            "减排比例：%{customdata[2]:.1f}%<br>"
            "车辆数：%{customdata[3]}<br>"
            "中转枢纽：%{customdata[4]}<extra></extra>"
        ),
    )
    for row in scenario_df.to_dict("records"):
        reduction_pct = float(row.get("减排比例(%)", 0) or 0)
        if abs(reduction_pct) < 0.05:
            continue
        is_better = reduction_pct > 0
        fig.add_annotation(
            x=row.get("方案", ""),
            y=float(row.get("总碳排放(kg CO2)", 0) or 0),
            yshift=28,
            text=f"较基线 {'-' if is_better else '+'}{abs(reduction_pct):.1f}%",
            showarrow=False,
            font={"size": 12, "color": "#365314" if is_better else "#8B1E1E"},
            bgcolor="rgba(247, 250, 242, 0.96)" if is_better else "rgba(253, 242, 242, 0.96)",
            bordercolor="rgba(128, 179, 50, 0.45)" if is_better else "rgba(217, 72, 65, 0.45)",
            borderpad=4,
        )

    fig.update_layout(
        title=title,
        yaxis={"title": "kg CO2", "range": [0, y_max * 1.28 if y_max > 0 else 1]},
    )
    return apply_green_chart_theme(fig, height=410, showlegend=False)


def build_scenario_breakdown_figure(
    scenario_df: pd.DataFrame,
    *,
    value_columns: tuple[str, str],
    legend_labels: tuple[str, str],
    title: str,
) -> go.Figure:
    """Build a stacked scenario breakdown chart."""
    fig = go.Figure()
    if scenario_df.empty:
        return apply_green_chart_theme(fig, height=360)

    first_col, second_col = value_columns
    first_label, second_label = legend_labels
    second_visible = second_col in scenario_df.columns and scenario_df[second_col].fillna(0).sum() > 0

    fig.add_bar(
        name=first_label,
        x=scenario_df["方案"],
        y=scenario_df[first_col],
        marker_color="#80B332",
        hovertemplate=f"<b>%{{x}}</b><br>{first_label}：%{{y:,.2f}}<extra></extra>",
    )
    if second_col in scenario_df.columns:
        fig.add_bar(
            name=second_label,
            x=scenario_df["方案"],
            y=scenario_df[second_col],
            marker_color="#5F6C76",
            hovertemplate=f"<b>%{{x}}</b><br>{second_label}：%{{y:,.2f}}<extra></extra>",
            visible=True if second_visible else "legendonly",
        )

    fig.update_layout(
        title=title,
        barmode="stack",
        yaxis={"title": first_col.split("(")[-1].rstrip(")") if "(" in first_col else first_col},
    )
    return apply_green_chart_theme(fig, height=360, showlegend=True)
