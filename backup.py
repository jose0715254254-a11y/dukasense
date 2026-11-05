
import sqlite3
import tempfile

from database import connect, create_tables


REQUIRED_TABLES = {
    "products",
    "stock_purchases",
    "sales",
    "expenses",
    "settings"
}


def create_backup_bytes():
    """Create a complete SQLite backup and return its bytes."""

    with tempfile.NamedTemporaryFile(suffix=".db") as temp_file:

        source = connect()
        destination = sqlite3.connect(temp_file.name)

        try:
            source.backup(destination)
            destination.commit()

        finally:
            destination.close()
            source.close()

        with open(temp_file.name, "rb") as file:
            return file.read()


def restore_database(uploaded_bytes):
    """Validate and restore a backup, preserving the current database."""

    # First preserve the current database.
    safety_backup = create_backup_bytes()

    with tempfile.NamedTemporaryFile(suffix=".db") as temp_file:

        temp_file.write(uploaded_bytes)
        temp_file.flush()

        source = sqlite3.connect(temp_file.name)

        try:

            integrity = source.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if integrity != "ok":
                raise ValueError("The backup file is damaged.")

            tables = {
                row[0]
                for row in source.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }

            missing_tables = REQUIRED_TABLES - tables

            if missing_tables:
                raise ValueError(
                    "This is not a valid DukaSense backup. "
                    f"Missing tables: {', '.join(sorted(missing_tables))}"
                )

            destination = connect()

            try:
                source.backup(destination)
                destination.commit()

            finally:
                destination.close()

            # Re-run database initialization and migrations.
            create_tables()

        except Exception:

            # If restoration fails, recover the previous database.
            source.close()

            with tempfile.NamedTemporaryFile(
                suffix=".db"
            ) as safety_file:

                safety_file.write(safety_backup)
                safety_file.flush()

                safety_connection = sqlite3.connect(
                    safety_file.name
                )

                current_connection = connect()

                try:
                    safety_connection.backup(current_connection)
                    current_connection.commit()

                finally:
                    safety_connection.close()
                    current_connection.close()

            raise

        else:
            source.close()
