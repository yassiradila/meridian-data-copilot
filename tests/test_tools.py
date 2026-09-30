"""
Unit tests for Meridian Data Copilot tools.
Tests SQL safety guards against PostgreSQL stellantis_db, PDF retrieval, and charts.
"""

import pytest
from src.database import execute_sql, validate_read_only_sql
from src.rag import search_documents
from src.charts import generate_chart


def test_sql_read_only_safety():
    # Destructive operations must be rejected immediately
    with pytest.raises(ValueError, match="(Prohibited destructive keyword|Only read-only SELECT)"):
        validate_read_only_sql("DROP TABLE dealerships;")

    with pytest.raises(ValueError, match="(Prohibited destructive keyword|Only read-only SELECT)"):
        validate_read_only_sql("DELETE FROM sales WHERE sale_id = 'TXN-001';")

    with pytest.raises(ValueError, match="(Prohibited destructive keyword|Only read-only SELECT)"):
        validate_read_only_sql("UPDATE vehicles SET base_price_mad = 999 WHERE vehicle_id = 1;")

    with pytest.raises(ValueError, match="(Prohibited destructive keyword|Only read-only SELECT)"):
        validate_read_only_sql("INSERT INTO dealerships VALUES (10, 'Fake', 'City', 'Reg', 'Type');")

    with pytest.raises(ValueError, match="Multiple SQL statements"):
        validate_read_only_sql("SELECT 1; DROP TABLE sales;")


def test_sql_execution_valid():
    res = execute_sql("SELECT COUNT(*) as total_dealerships FROM dealerships;")
    assert res["success"] is True
    assert res["row_count"] == 1
    assert res["rows"][0]["total_dealerships"] == 7


def test_sql_vehicles_catalog():
    res = execute_sql("SELECT COUNT(*) as total_models FROM vehicles;")
    assert res["success"] is True
    assert res["rows"][0]["total_models"] == 14


def test_sql_killer_use_case_kenitra_may_june():
    query = """
    SELECT 
        TO_CHAR(s.sale_date, 'YYYY-MM') as month,
        SUM(s.quantity) as total_units,
        ROUND(SUM(s.total_revenue_mad), 2) as total_revenue
    FROM sales s
    JOIN vehicles v ON s.vehicle_id = v.vehicle_id
    WHERE v.assembly_plant = 'Kénitra'
      AND s.sale_date >= '2024-05-01' AND s.sale_date <= '2024-06-30'
    GROUP BY TO_CHAR(s.sale_date, 'YYYY-MM')
    ORDER BY month;
    """
    res = execute_sql(query)
    assert res["success"] is True
    assert len(res["rows"]) == 2
    may_row = res["rows"][0]
    june_row = res["rows"][1]
    
    assert may_row["month"] == "2024-05"
    assert june_row["month"] == "2024-06"
    assert float(june_row["total_revenue"]) < float(may_row["total_revenue"])


def test_pdf_search_incident_logistique():
    results = search_documents(
        query="incident logistique juin 2024 rupture approvisionnement Kenitra retard livraison",
        n_results=2
    )
    assert len(results) > 0
    top_chunk = results[0]
    assert "Rapport_Incident_Logistique_Juin_2024.pdf" in top_chunk["source"]


def test_pdf_search_usine_kenitra():
    results = search_documents(
        query="capacite usine Kenitra Zone Franche Atlantique AFZ effectif Florian Huettl",
        n_results=2
    )
    assert len(results) > 0
    sources = [r["source"] for r in results]
    assert any("Empreinte_Industrielle_Usines_Stellantis.pdf" in s for s in sources)


def test_chart_generation():
    test_data = [
        {"month": "2024-05", "revenue": 5341000.0},
        {"month": "2024-06", "revenue": 3732000.0}
    ]
    res = generate_chart(test_data, chart_type="bar", x_col="month", y_col="revenue", title="May vs June Kenitra Sales")
    assert res["success"] is True
    assert res["figure"] is not None
