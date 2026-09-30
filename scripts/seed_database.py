"""
Database Seeding Script.
Initializes the PostgreSQL database schema and seeds all tables:
- dealerships (7 records)
- vehicles (14 records)
- sales_targets (168 records)
- sales (4,395 records)
Reads from compressed data/seed_data.json.gz so that CI and fresh environments
can initialize without external spreadsheet files.
"""

import os
import sys
import gzip
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

load_dotenv()

DEFAULT_DB_URL = "postgresql://postgres:testpassword@localhost:5432/stellantis_db"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DB_URL


def init_and_seed_database(db_url: str = DATABASE_URL) -> None:
    print(f"[Seed] Initializing database at: {db_url}")
    engine = create_engine(db_url)

    seed_file = BASE_DIR / "data" / "seed_data.json.gz"
    if not seed_file.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_file}")

    with gzip.open(seed_file, "rt", encoding="utf-8") as f:
        data = json.load(f)

    with engine.begin() as conn:
        print("[Seed] Creating tables...")
        conn.execute(text("DROP TABLE IF EXISTS sales CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS sales_targets CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS vehicles CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS dealerships CASCADE;"))

        conn.execute(text("""
            CREATE TABLE dealerships (
                dealership_id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                city VARCHAR(50) NOT NULL,
                region VARCHAR(50) NOT NULL,
                dealership_type VARCHAR(50) NOT NULL
            );
            CREATE TABLE vehicles (
                vehicle_id SERIAL PRIMARY KEY,
                brand VARCHAR(50) NOT NULL,
                model VARCHAR(100) NOT NULL UNIQUE,
                segment VARCHAR(50) NOT NULL,
                assembly_plant VARCHAR(100) NOT NULL,
                base_price_mad NUMERIC(12, 2) NOT NULL
            );
            CREATE TABLE sales_targets (
                target_id SERIAL PRIMARY KEY,
                dealership_id INT REFERENCES dealerships(dealership_id),
                target_year INT NOT NULL,
                target_month INT NOT NULL,
                target_revenue_mad NUMERIC(14, 2) NOT NULL,
                target_units INT NOT NULL,
                UNIQUE (dealership_id, target_year, target_month)
            );
            CREATE TABLE sales (
                sale_id VARCHAR(50) PRIMARY KEY,
                sale_date DATE NOT NULL,
                dealership_id INT REFERENCES dealerships(dealership_id),
                vehicle_id INT REFERENCES vehicles(vehicle_id),
                client_type VARCHAR(20) NOT NULL,
                quantity INT NOT NULL,
                unit_price_mad NUMERIC(12, 2) NOT NULL,
                total_revenue_mad NUMERIC(14, 2) NOT NULL
            );
        """))

        # 1. Dealerships
        print(f"[Seed] Seeding {len(data['dealerships'])} dealerships...")
        for d in data["dealerships"]:
            conn.execute(
                text("""
                    INSERT INTO dealerships (dealership_id, name, city, region, dealership_type)
                    VALUES (:dealership_id, :name, :city, :region, :dealership_type)
                    ON CONFLICT (dealership_id) DO NOTHING;
                """),
                d
            )

        # 2. Vehicles
        print(f"[Seed] Seeding {len(data['vehicles'])} vehicles...")
        for v in data["vehicles"]:
            conn.execute(
                text("""
                    INSERT INTO vehicles (vehicle_id, brand, model, segment, assembly_plant, base_price_mad)
                    VALUES (:vehicle_id, :brand, :model, :segment, :assembly_plant, :base_price_mad)
                    ON CONFLICT (vehicle_id) DO NOTHING;
                """),
                v
            )

        # 3. Targets
        print(f"[Seed] Seeding {len(data['sales_targets'])} sales targets...")
        for t in data["sales_targets"]:
            conn.execute(
                text("""
                    INSERT INTO sales_targets (target_id, dealership_id, target_year, target_month, target_revenue_mad, target_units)
                    VALUES (:target_id, :dealership_id, :target_year, :target_month, :target_revenue_mad, :target_units)
                    ON CONFLICT DO NOTHING;
                """),
                t
            )

        # 4. Sales
        print(f"[Seed] Seeding {len(data['sales'])} sales records...")
        conn.execute(
            text("""
                INSERT INTO sales (sale_id, sale_date, dealership_id, vehicle_id, client_type, quantity, unit_price_mad, total_revenue_mad)
                VALUES (:sale_id, :sale_date, :dealership_id, :vehicle_id, :client_type, :quantity, :unit_price_mad, :total_revenue_mad)
                ON CONFLICT (sale_id) DO NOTHING;
            """),
            data["sales"]
        )

    print("[Seed] Database initialization and seeding completed successfully!")


if __name__ == "__main__":
    init_and_seed_database()
