import os

import psycopg2


def connect():
    """Create a local PostgreSQL connection from environment variables."""
    return psycopg2.connect(
        dbname=os.environ.get('UNITRADE_DB_NAME') or os.environ.get('PGDATABASE', 'unitrade_db'),
        user=os.environ.get('UNITRADE_DB_USER') or os.environ.get('PGUSER', 'openpg'),
        password=os.environ.get('UNITRADE_DB_PASSWORD') or os.environ.get('PGPASSWORD'),
        host=os.environ.get('UNITRADE_DB_HOST') or os.environ.get('PGHOST', 'localhost'),
        port=os.environ.get('UNITRADE_DB_PORT') or os.environ.get('PGPORT', '5432'),
    )
