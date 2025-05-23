"""
Datasette Metadata Manager

This module manages Datasette metadata integration for the sglawwatch-to-sqlite tool.

How it works:
- Loads existing metadata.json from local or S3 storage
- Updates it with project-specific configuration from repository project_metadata.json
- Preserves other database configs in the same file
- Calculates hash to determine if updates are needed

CLI usage:
    # Dedicated update command
    sglawwatch-to-sqlite metadata update ./data [--dry-run]

    # With fetch commands
    sglawwatch-to-sqlite fetch headlines ./data --update-metadata
    sglawwatch-to-sqlite fetch all ./data --update-metadata

    # S3 storage
    sglawwatch-to-sqlite metadata update s3://bucket/path/ [--dry-run]

Customization:
- Edit repository project_metadata.json to change how database appears in Datasette
- Configure tables, columns, facets, and database-level metadata
- Run update command to apply changes

Requirements:
- project_metadata.json must exist in target location
- S3 storage requires proper read/write permissions
- Database name is always "sglawwatch" (without .db extension)

See: https://docs.datasette.io/en/stable/metadata.html for Datasette metadata options
"""

import json
import os
import importlib.resources as pkg_resources

import click

from sglawwatch_to_sqlite.storage import Storage
from sglawwatch_to_sqlite.tools import get_hash_id

DATABASE_NAME = "sglawwatch"


# Filename constants
METADATA_FILENAME = "metadata.json"


class MetadataManager:
    """
    Manages Datasette metadata.json, adding project-specific metadata.
    """

    def __init__(self, database_uri):
        """
        Initialize a MetadataManager with a database URI.

        Args:
            database_uri: Either a local file path or an S3 URI (s3://bucket/path)
        """
        try:
            # Create the appropriate storage
            self.storage = Storage.create(database_uri)

            # Get the local path for metadata.json
            try:
                self.local_path = self.storage.get_local_path(filename=METADATA_FILENAME)
                # Load existing metadata if it exists
                if os.path.exists(self.local_path):
                    with open(self.local_path, 'r') as f:
                        self.metadata = json.load(f)
                else:
                    raise FileNotFoundError(f"No existing {METADATA_FILENAME} found")
            except FileNotFoundError as e:
                click.echo(f"Error: {e}. Cannot update non-existent metadata file.", err=True)
                raise click.Abort()

            # Load project metadata template (now using project_metadata.json)
            project_data = pkg_resources.read_text(
                'sglawwatch_to_sqlite',
                'project_metadata.json'
            )
            self.project_metadata = json.loads(project_data)

        except json.JSONDecodeError as e:
            click.echo(f"Error parsing JSON: {e}", err=True)
            raise click.Abort()
        except Exception as e:
            click.echo(f"Error initializing metadata manager at {database_uri}: {e}", err=True)
            raise click.Abort()

    def update_metadata(self, dry_run=False):
        """
        Update Datasette metadata with project metadata.

        Args:
            dry_run: If True, don't save changes, just preview them

        Returns:
            A tuple (bool, str) indicating if changes were made and a message
        """
        # Check if database entry exists in the metadata
        db_name = DATABASE_NAME  # DB filename without extension

        # Initialize database metadata if it doesn't exist
        if "databases" not in self.metadata:
            self.metadata["databases"] = {}

        # Check if the database section needs to be created or updated
        changes_needed = False

        if db_name not in self.metadata["databases"]:
            # Database entry doesn't exist at all
            changes_needed = True
        else:
            # Database entry exists, check if it's different from project metadata
            current_db_metadata = self.metadata["databases"][db_name]
            # Sort both dictionaries to ensure consistent comparison
            changes_needed = json.dumps(current_db_metadata, sort_keys=True) != json.dumps(self.project_metadata,
                                                                                           sort_keys=True)

        if not changes_needed:
            message = "No changes needed - metadata is already up to date"
            return False, message

        # Update the metadata
        self.metadata["databases"][db_name] = self.project_metadata

        if dry_run:
            message = f"Changes would be made to {METADATA_FILENAME} (dry run):\n"
            message += json.dumps(self.metadata, indent=2)
            return True, message

        # Save the updated metadata
        with open(self.local_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        # Save to storage location
        saved_location = self.storage.save(self.local_path, filename=METADATA_FILENAME)

        message = f"Metadata updated and saved to {saved_location}"
        return True, message
