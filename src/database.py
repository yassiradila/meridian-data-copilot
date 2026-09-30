"""
Database Access Layer (PostgreSQL via SQLAlchemy).
Enforces strict read-only execution, dynamic schema introspection,
and safe connection handling.
"""

import os
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import create_engine, text, inspect
from src.config import DATABASE_URL

# Disallowed SQL keywords for security / read-only guardrails
DANGEROUS_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bTRUNCATE\b",
    r"\bREPLACE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bEXEC\b",
    r"\bPRAGMA\b",
]

_ACTIVE_DB_URL: Optional[str] = None
_ENGINE = None


def get_active_database_url() -> str:
    """Returns the current active database connection string."""
    global _ACTIVE_DB_URL
    return _ACTIVE_DB_URL or os.getenv("DATABASE_URL") or DATABASE_URL


def set_active_database_url(url: Optional[str]) -> None:
    """Sets or overrides the active database connection string and refreshes engine."""
    global _ACTIVE_DB_URL, _ENGINE
    _ACTIVE_DB_URL = url.strip() if url and url.strip() else None
    _ENGINE = None


def get_engine():
    """Returns a singleton SQLAlchemy engine for the active database connection."""
    global _ENGINE
    if _ENGINE is None:
        url = get_active_database_url()
        _ENGINE = create_engine(url, pool_pre_ping=True)
    return _ENGINE


def validate_read_only_sql(query: str) -> None:
    """
    Validates that a SQL query contains only SELECT statements and no destructive operations.
    Raises ValueError if validation fails.
    """
    cleaned = query.strip()

    # Strip comments
    cleaned = re.sub(r"--.*?\n", "\n", cleaned)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL).strip()

    if not cleaned:
        raise ValueError("Empty SQL query provided.")

    # Check for multiple statements (preventing semicolon injection)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    if len(statements) > 1:
        raise ValueError("Multiple SQL statements are strictly prohibited for safety.")

    stmt = statements[0]

    # Must start with SELECT or WITH (for CTEs)
    if not re.match(r"^(SELECT|WITH)\b", stmt, re.IGNORECASE):
        raise ValueError("Only read-only SELECT queries or CTEs (WITH ... SELECT) are allowed.")

    # Check for dangerous write/schema keywords
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, stmt, re.IGNORECASE):
            match = re.search(pattern, stmt, re.IGNORECASE).group()
            raise ValueError(
                f"Prohibited destructive keyword detected: '{match}'. Only read-only operations are permitted."
            )


def execute_sql(query: str, max_rows: int = 200) -> Dict[str, Any]:
    """
    Executes a read-only SQL query against PostgreSQL via SQLAlchemy.
    Returns a structured dictionary with success flag, columns, row records, and row count.
    """
    try:
        validate_read_only_sql(query)
    except ValueError as e:
        return {
            "success": False,
            "error": f"Security Guardrail Violation: {str(e)}",
            "columns": [],
            "rows": [],
            "row_count": 0,
        }

    # Ensure LIMIT is present to prevent memory bloat
    clean_query = query.strip().rstrip(";")
    if not re.search(r"\bLIMIT\s+\d+", clean_query, re.IGNORECASE):
        clean_query = f"{clean_query} LIMIT {max_rows}"

    # Normalize common Moroccan/French accents in SQL literals to prevent 0-match misses
    accent_replacements = [
        (r"(['\"])\s*Tetouan\s*(['\"])", r"\1Tétouan\2"),
        (r"(['\"])\s*Kenitra\s*(['\"])", r"\1Kénitra\2"),
        (r"(['\"])\s*Citroen\s*(['\"])", r"\1Citroën\2"),
        (r"(['\"])\s*Ain Sebaa\s*(['\"])", r"\1Aïn Sebaâ\2"),
    ]
    for pattern, repl in accent_replacements:
        clean_query = re.sub(pattern, repl, clean_query, flags=re.IGNORECASE)

    engine = get_engine()
    try:
        with engine.connect() as conn:
            # Set read-only session in PostgreSQL for defense-in-depth
            if "postgresql" in str(engine.url):
                try:
                    conn.execute(text("SET default_transaction_read_only = ON;"))
                except Exception:
                    pass

            result = conn.execute(text(clean_query))
            columns = list(result.keys()) if result.returns_rows else []
            rows = [dict(zip(columns, row)) for row in result.fetchall()] if result.returns_rows else []

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "executed_query": clean_query,
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Database Execution Error: {str(e)}",
            "columns": [],
            "rows": [],
            "row_count": 0,
            "executed_query": clean_query,
        }


def get_domain_guidelines() -> str:
    """Returns domain instructions and table join guidance for business queries."""
    return """### Stellantis Domain Guidelines & Schema Notes:
- Currencies: All monetary values (`unit_price_mad`, `total_revenue_mad`, `target_revenue_mad`, `base_price_mad`) are in Moroccan Dirhams (MAD).
- To analyze sales by dealership or city: JOIN sales ON sales.dealership_id = dealerships.dealership_id.
- To analyze sales by brand, vehicle model, segment, or assembly plant: JOIN sales ON sales.vehicle_id = vehicles.vehicle_id.
- Vehicles assembled in Morocco: assembly_plant = 'Kénitra' (Peugeot 208, Citroën Ami, Fiat Topolino).
- Vehicles assembled abroad: Peugeot 2008 (Vigo), Peugeot 3008 (Sochaux), Citroën C3 (Trnava), Citroën C4 (Madrid), Fiat 500 (Tychy), Fiat Tipo (Bursa), Jeep Avenger (Tychy), Jeep Compass (Melfi), Alfa Romeo Tonale (Pomigliano d'Arco), Opel Corsa (Saragosse), Opel Mokka (Poissy).
- Monthly aggregation: EXTRACT(YEAR FROM sale_date) and EXTRACT(MONTH FROM sale_date), or TO_CHAR(sale_date, 'YYYY-MM').
- Monthly performance vs targets: Compare SUM(sales.total_revenue_mad) against sales_targets.target_revenue_mad.
- All queries must be strictly READ-ONLY (SELECT only).
"""


def discover_database_schema(db_url: Optional[str] = None) -> str:
    """
    Dynamically introspects the active PostgreSQL database using SQLAlchemy
    and generates a live schema overview with table names, column types, and row counts.
    """
    engine = create_engine(db_url, pool_pre_ping=True) if db_url else get_engine()

    try:
        inspector = inspect(engine)
        table_names = inspector.get_table_names(schema="public")

        schema_lines = ["### Live Stellantis Database Schema (PostgreSQL `stellantis_db`):\n"]
        with engine.connect() as conn:
            for tbl in table_names:
                columns = inspector.get_columns(tbl, schema="public")
                try:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM public.{tbl}")).scalar()
                except Exception:
                    count = 0

                schema_lines.append(f"Table: `{tbl}` ({count:,} records)")
                for col in columns:
                    pk = ", PRIMARY KEY" if col.get("primary_key") else ""
                    schema_lines.append(f"  - {col['name']} ({col['type']}{pk})")
                schema_lines.append("")

        schema_lines.append(get_domain_guidelines())
        return "\n".join(schema_lines)
    except Exception as e:
        return f"### PostgreSQL Connection Warning:\nCould not introspect tables: {str(e)}\n\n"


def check_connection() -> bool:
    """Verifies active connectivity to PostgreSQL."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            res = conn.execute(text("SELECT 1;")).scalar()
            return res == 1
    except Exception:
        return False