from datetime import datetime

import click
import sqlite_utils

from sglawwatch_to_sqlite.storage import Storage

# Current table versions
TABLE_VERSIONS = {
    "headlines": 1,
    "metadata": 1
}


class DatabaseManager:
    """
    A class that manages both the database and its storage.
    """

    def __init__(self, database_uri):
        """
        Initialize a DatabaseManager with a database URI.

        Args:
            database_uri: Either a local file path or an S3 URI (s3://bucket/path)
        """
        try:
            # Create the appropriate storage
            self.storage = Storage.create(database_uri)

            # Get the local path (will download from S3 if needed)
            self.local_path = self.storage.get_local_path()

            # Connect to the database
            self.db = sqlite_utils.Database(self.local_path)

            # Set up tables if needed
            self._setup_tables()
        except Exception as e:
            click.echo(f"Error connecting to database at {database_uri}: {e}", err=True)
            raise click.Abort()

    def _setup_tables(self):
        """Set up the necessary tables in the database."""
        try:
            # Check/create schema_versions table first
            if "schema_versions" not in self.db.table_names():
                self.db["schema_versions"].create({
                    "table_name": str,
                    "version": int,
                    "updated_at": str
                }, pk="table_name")
                click.echo("Created schema version tracking table")

            # Create the headlines table if it doesn't exist
            if "headlines" not in self.db.table_names():
                self.db["headlines"].create({
                    "id": str,  # Unique identifier for each article
                    "category": str,  # The category of the news article
                    "title": str,  # The title of the article
                    "source_link": str,  # URL to the source article
                    "author": str,  # Author of the article
                    "date": str,  # Publication date in ISO format
                    "summary": str,  # Summary text
                    "text": str,  # Full text content
                    "imported_on": str  # When the article was imported
                }, pk="id")

                # Create indexes for common query patterns
                self.db["headlines"].create_index(["date"])
                self.db["headlines"].create_index(["author"])

                self.db["headlines"].enable_fts(["title", "summary"], create_triggers=True)

                self._register_table_version("headlines", TABLE_VERSIONS["headlines"])

            # Create the metadata table if it doesn't exist
            if "metadata" not in self.db.table_names():
                self.db["metadata"].create({
                    "key": str,
                    "value": str
                }, pk="key")
                self._register_table_version("metadata", TABLE_VERSIONS["metadata"])

        except Exception as e:
            click.echo(f"Error creating table: {e}", err=True)
            raise click.Abort()

    def _register_table_version(self, table_name, version):
        """Register a new table version in the schema_versions table"""
        self.db["schema_versions"].insert({
            "table_name": table_name,
            "version": version,
            "updated_at": datetime.now().isoformat()
        })
        click.echo(f"Registered {table_name} table with schema version {version}")

    def get_database(self):
        """Get the sqlite_utils Database object."""
        return self.db

    def save(self):
        """Save the database, handling S3 upload if needed."""
        return self.storage.save(self.local_path)

    def get_last_updated(self, feed_type):
        """Get the last updated timestamp for a specific feed type"""
        metadata_key = f"{feed_type}_last_updated"
        try:
            return self.db["metadata"].get(metadata_key)["value"]
        except sqlite_utils.db.NotFoundError:
            self.db["metadata"].insert({"key": metadata_key, "value": ""})
            return ""

    def update_last_updated(self, feed_type, timestamp):
        """Update the last updated timestamp for a specific feed type"""
        metadata_key = f"{feed_type}_last_updated"
        self.db["metadata"].upsert({"key": metadata_key, "value": timestamp}, pk="key")
