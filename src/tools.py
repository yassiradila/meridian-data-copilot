"""
LangChain Tool Definitions for Meridian Data Copilot.
Wraps execute_sql, search_documents, and generate_chart into structured tools.
"""

import json
import re
from typing import Any, Dict, List, Optional
from langchain_core.tools import tool
from src.database import execute_sql
from src.rag import search_documents
from src.charts import generate_chart


@tool
def execute_sql_query(query: str) -> str:
    """
    Executes a read-only SQL query against the Stellantis PostgreSQL database (`stellantis_db`).
    Use this tool whenever you need quantitative data, vehicle sales volume, dealership revenue, targets, prices, etc...
    
    Tables available in stellantis_db:
    - dealerships (dealership_id, name, city, region, dealership_type)
    - vehicles (vehicle_id, brand, model, segment, assembly_plant, base_price_mad)
    - sales_targets (target_id, dealership_id, target_year, target_month, target_revenue_mad, target_units)
    - sales (sale_id, sale_date, dealership_id, vehicle_id, client_type, quantity, unit_price_mad, total_revenue_mad)
    
    Returns:
    JSON string with execution status, retrieved columns, row records, and row count.
    If the query fails (e.g. syntax error), the error message is returned so you can self-correct.
    """
    res = execute_sql(query)
    # Token optimization: if rows exceed 25, keep first 25 to protect TPM rate limits
    if res.get("rows") and len(res["rows"]) > 25:
        total_count = len(res["rows"])
        compact_res = {
            "success": res.get("success", True),
            "columns": res.get("columns", []),
            "rows": res["rows"][:25],
            "row_count": 25,
            "total_matches": total_count,
            "note": f"Showing first 25 of {total_count} rows.",
            "executed_query": res.get("executed_query", query)
        }
        return json.dumps(compact_res, default=str, separators=(",", ":"))
    return json.dumps(res, default=str, separators=(",", ":"))


@tool
def search_company_documents(query: str, brand: Optional[str] = None, doc_type: Optional[str] = None) -> str:
    """
    Performs semantic vector search across internal corporate PDFs in data/pdf/.
    Use this tool to find qualitative explanations (e.g. June 2024 supply disruption, plant capacities, vehicle specs, organizational hierarchy).
    
    PDFs indexed:
    - Rapport_Incident_Logistique_Juin_2024.pdf (June 2024 supply constraints and delivery delays)
    - Empreinte_Industrielle_Usines_Stellantis.pdf (Kénitra plant, Sochaux, Vigo, workforce, capacity)
    - Catalogue_Specifications_Techniques_Modeles.pdf (Engine specs, battery capacity, finishes)
    - Stellantis_Maroc_Organisation_Equipes_2024.pdf (Executive directory, team structure)
        
    Returns:
        JSON string containing relevant document chunks with file source, page, section, and text excerpt.
    """
    filters = {}
    if brand:
        filters["brand"] = brand
    if doc_type:
        filters["doc_type"] = doc_type

    chunks = search_documents(query, filters=filters, n_results=3)
    
    compact_chunks = []
    for c in chunks:
        raw_text = c.get("content", "")
        clean_text = re.sub(r"\s+", " ", raw_text).strip()
        if len(clean_text) > 400:
            clean_text = clean_text[:400] + "..."
        compact_chunks.append({
            "source": c.get("source"),
            "section": c.get("section"),
            "page": c.get("page", 1),
            "excerpt": clean_text
        })
    return json.dumps(compact_chunks, default=str, separators=(",", ":"))


@tool
def create_data_chart(
    data: List[Dict[str, Any]],
    chart_type: str = "bar",
    x_col: str = "",
    y_col: str = "",
    title: str = "Stellantis Commercial Analytics"
) -> str:
    """
    Generates a deterministic Plotly data visualization from tabular query results.
    
    Args:
        data: List of row dictionaries returned from a previous SQL execution
        chart_type: 'bar', 'line', 'pie', or 'area'
        x_col: Column name to plot on the X-axis (e.g., 'month', 'dealership_name', 'model', or 'city')
        y_col: Numerical column name to plot on the Y-axis (e.g., 'total_revenue_mad', 'quantity')
        title: Descriptive title for the chart (e.g., 'Peugeot 208 Monthly Sales Trend (MAD)')
        
    Returns:
        JSON string confirming chart generation and summary.
    """
    chart_res = generate_chart(data, chart_type=chart_type, x_col=x_col, y_col=y_col, title=title)
    if chart_res.get("success"):
        return json.dumps({
            "status": "success",
            "message": f"Successfully generated {chart_type} chart titled '{title}'.",
            "chart_type": chart_type,
            "x_col": chart_res.get("x_col"),
            "y_col": chart_res.get("y_col"),
            "title": title,
            "row_count": len(data)
        }, separators=(",", ":"))
    else:
        return json.dumps({
            "status": "error",
            "message": chart_res.get("error", "Unknown error generating chart")
        }, separators=(",", ":"))


MERIDIAN_TOOLS = [execute_sql_query, search_company_documents, create_data_chart]
