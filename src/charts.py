"""
Deterministic Chart Generation Module.
Generates Plotly visual analytics from tabular SQL result data.
"""

from typing import Any, Dict, List, Optional
import pandas as pd
import plotly.express as px


def generate_chart(
    data: List[Dict[str, Any]],
    chart_type: str = "bar",
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    title: str = "Stellantis Commercial Analytics",
    color_col: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically transforms tabular data into a Plotly figure dict.

    Args:
        data: List of row dictionaries (e.g. [{'month': '2024-05', 'revenue': 576719.0}, ...])
        chart_type: 'bar', 'line', 'pie', 'scatter', or 'area'
        x_col: Name of column for horizontal axis or category
        y_col: Name of column for numerical value
        title: Descriptive chart title
        color_col: Optional column for grouped color coding

    Returns:
        Dictionary with status, plotly_figure object, and metadata.
    """
    if not data or not isinstance(data, list):
        return {
            "success": False,
            "error": "No data provided to generate chart.",
            "figure": None,
        }

    df = pd.DataFrame(data)
    if df.empty:
        return {
            "success": False,
            "error": "Dataframe is empty.",
            "figure": None,
        }

    # Infer x_col and y_col if not supplied or mismatched
    cols = list(df.columns)
    if not x_col or x_col not in cols:
        x_col = cols[0]
    if not y_col or y_col not in cols:
        numeric_cols = [c for c in cols if pd.api.types.is_numeric_dtype(df[c])]
        y_col = numeric_cols[0] if numeric_cols else (cols[1] if len(cols) > 1 else cols[0])

    assert isinstance(x_col, str) and isinstance(y_col, str)

    # Convert y_col to numeric if possible
    df[y_col] = pd.to_numeric(df[y_col], errors="coerce").fillna(0)

    c_type = chart_type.lower().strip()
    color_palette = ["#10B981", "#06B6D4", "#6366F1", "#F59E0B", "#EC4899", "#8B5CF6"]

    try:
        if c_type == "bar":
            fig = px.bar(
                df,
                x=x_col,
                y=y_col,
                color=color_col if color_col in df.columns else None,
                title=title,
                text_auto=".2s",
                color_discrete_sequence=color_palette,
            )
            fig.update_traces(marker_line_width=1.5, opacity=0.9)
        elif c_type == "line":
            fig = px.line(
                df,
                x=x_col,
                y=y_col,
                color=color_col if color_col in df.columns else None,
                title=title,
                markers=True,
                color_discrete_sequence=color_palette,
            )
            fig.update_traces(line=dict(width=3), marker=dict(size=8))
        elif c_type == "area":
            fig = px.area(
                df,
                x=x_col,
                y=y_col,
                color=color_col if color_col in df.columns else None,
                title=title,
                color_discrete_sequence=color_palette,
            )
        elif c_type == "pie":
            fig = px.pie(
                df,
                names=x_col,
                values=y_col,
                title=title,
                hole=0.4,
                color_discrete_sequence=color_palette,
            )
        else:  # fallback to bar
            fig = px.bar(
                df,
                x=x_col,
                y=y_col,
                title=title,
                text_auto=".2s",
                color_discrete_sequence=color_palette,
            )

        # Apply cohesive modern dark theme styling
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(15, 23, 42, 0)",
            plot_bgcolor="rgba(30, 41, 59, 0.4)",
            margin=dict(l=40, r=40, t=50, b=40),
            font=dict(family="Inter, -apple-system, BlinkMacSystemFont, sans-serif", color="#E2E8F0"),
            title=dict(font=dict(size=16, color="#F8FAFC")),
            xaxis=dict(gridcolor="rgba(148, 163, 184, 0.15)", showline=True, linecolor="rgba(148, 163, 184, 0.3)"),
            yaxis=dict(gridcolor="rgba(148, 163, 184, 0.15)", showline=True, linecolor="rgba(148, 163, 184, 0.3)"),
            hoverlabel=dict(bgcolor="#1E293B", font_size=13, font_family="Inter"),
        )

        return {
            "success": True,
            "figure": fig,
            "chart_type": c_type,
            "x_col": x_col,
            "y_col": y_col,
            "title": title,
            "data_summary": f"{len(df)} rows visualized across {x_col} and {y_col}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Plotly chart generation error: {str(e)}",
            "figure": None,
        }