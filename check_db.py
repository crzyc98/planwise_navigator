import duckdb
import os
import yaml


# Get the database path from dbt profile
def get_dbt_database_path():
    profiles_path = os.path.expanduser("~/.dbt/profiles.yml")
    try:
        with open(profiles_path, "r") as f:
            profiles = yaml.safe_load(f)
        # Get the database path from the profile
        db_path = profiles["planwise_navigator"]["outputs"]["dev"]["path"]
        # Expand any user paths or environment variables
        return os.path.expanduser(os.path.expandvars(db_path))
    except Exception as e:
        print(f"Error reading dbt profile: {e}")
        return None


# Get the database path from dbt profile
db_path = get_dbt_database_path()

if not db_path:
    # Fallback to local path if profile can't be read
    db_path = os.path.join(os.path.dirname(__file__), "simulation.duckdb")
    print(f"Using fallback database path: {db_path}")
else:
    print(f"Using database path from dbt profile: {db_path}")

print(f"Connecting to database at: {db_path}")

# Check if database file exists
if not os.path.exists(db_path):
    print(f"Error: Database file not found at {db_path}")
    exit(1)
else:
    print("Database file exists")

try:
    # Connect to the database
    con = duckdb.connect(database=db_path, read_only=False)
    print("\n=== Database Connection Successful ===")

    # List all schemas with their tables
    print("\n=== All Schemas and Tables ===")
    query = """
    SELECT
        table_schema,
        table_name,
        table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name
    """

    tables = con.execute(query).fetchall()

    if not tables:
        print("No tables found in any schema!")
    else:
        for schema, table, table_type in tables:
            print(f"Schema: {schema}, Table: {table} ({table_type})")

    # Check for stg_census_data in any schema
    print("\n=== Searching for stg_census_data ===")
    query = """
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE LOWER(table_name) = 'stg_census_data'
    """

    result = con.execute(query).fetchall()

    if not result:
        print("stg_census_data table not found in any schema!")
    else:
        for schema, table in result:
            print(f"Found {schema}.{table}")

            # Get row count
            try:
                count = con.execute(
                    f'SELECT COUNT(*) FROM "{schema}"."{table}"'
                ).fetchone()[0]
                print(f"  Rows: {count}")

                # Show columns
                print("  Columns:")
                columns = con.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = ? AND table_name = ?
                    ORDER BY ordinal_position
                """,
                    [schema, table],
                ).fetchall()

                for col_name, col_type in columns:
                    print(f"    {col_name}: {col_type}")

                # Show sample data if table is not empty
                if count > 0:
                    print("  Sample data (first 3 rows):")
                    data = con.execute(
                        f'SELECT * FROM "{schema}"."{table}" LIMIT 3'
                    ).fetchall()
                    for row in data:
                        print(f"    {row}")

            except Exception as e:
                print(f"  Error querying table: {e}")

    # List all schemas (including system schemas)
    print("\n=== All Schemas ===")
    schemas = con.execute(
        "SELECT schema_name FROM information_schema.schemata"
    ).fetchall()
    for (schema,) in schemas:
        print(f"- {schema}")

    # Try to find any tables in main schema
    print("\n=== Checking main schema ===")
    try:
        tables_in_main = con.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
        """
        ).fetchall()

        if not tables_in_main:
            print("No tables found in 'main' schema")
        else:
            print("Tables in 'main' schema:")
            for (table,) in tables_in_main:
                print(f"- {table}")
    except Exception as e:
        print(f"Error checking main schema: {e}")

except Exception as e:
    print(f"\nError: {e}")

finally:
    if "con" in locals():
        con.close()
        print("\nDatabase connection closed")
