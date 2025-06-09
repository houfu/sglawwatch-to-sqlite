"""
Datasette Metadata Manager

This module manages Datasette metadata integration for the sglawwatch-to-sqlite tool.

How it works:
- Loads existing metadata.json from local or S3 storage
- Updates it with project-specific configuration from repository metadata.json
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
- Edit repository metadata.json to change how database appears in Datasette
- Configure tables, columns, facets, and database-level metadata
- Run update command to apply changes

Requirements:
- metadata.json must exist in target location
- S3 storage requires proper read/write permissions
- Database name is always "sglawwatch" (without .db extension)

See: https://docs.datasette.io/en/stable/metadata.html for Datasette metadata options
"""
"""
Updated metadata_manager.py to work with the new asset structure
"""

import json
import os
import importlib.resources as pkg_resources

import click

from sglawwatch_to_sqlite.storage import Storage
from sglawwatch_to_sqlite.tools import get_hash_id

DATABASE_NAME = "sglawwatch"
METADATA_FILENAME = "metadata.json"


class MetadataManager:
    """
    Manages Datasette metadata.json, supporting both traditional and Zeeker workflows.
    """

    def __init__(self, database_uri, use_zeeker_assets=False, assets_dir="zeeker_assets"):
        """
        Initialize a MetadataManager with a database URI.

        Args:
            database_uri: Either a local file path or an S3 URI (s3://bucket/path)
            use_zeeker_assets: If True, prefer metadata from assets directory
            assets_dir: Directory containing Zeeker assets
        """
        try:
            # Create the appropriate storage
            self.storage = Storage.create(database_uri)
            self.use_zeeker_assets = use_zeeker_assets
            self.assets_dir = assets_dir

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

            # Load project metadata template based on workflow
            self.project_metadata = self._load_project_metadata()

        except json.JSONDecodeError as e:
            click.echo(f"Error parsing JSON: {e}", err=True)
            raise click.Abort()
        except Exception as e:
            click.echo(f"Error initializing metadata manager at {database_uri}: {e}", err=True)
            raise click.Abort()

    def _load_project_metadata(self):
        """Load project metadata from appropriate source."""

        # If using Zeeker assets, try to load from assets directory first
        if self.use_zeeker_assets:
            zeeker_metadata_path = os.path.join(self.assets_dir, 'metadata.json')
            if os.path.exists(zeeker_metadata_path):
                with open(zeeker_metadata_path, 'r') as f:
                    zeeker_metadata = json.load(f)

                # Extract just the database portion for compatibility with existing logic
                if 'databases' in zeeker_metadata and DATABASE_NAME in zeeker_metadata['databases']:
                    click.echo(f"Using metadata from {zeeker_metadata_path}")
                    return zeeker_metadata['databases'][DATABASE_NAME]
                else:
                    click.echo(
                        f"Warning: {zeeker_metadata_path} missing database section, falling back to internal metadata")

        # Fall back to internal project metadata
        try:
            # First try the original project_metadata.json
            project_data = pkg_resources.read_text(
                'sglawwatch_to_sqlite',
                'project_metadata.json'
            )
            click.echo("Using internal project_metadata.json")
            return json.loads(project_data)
        except FileNotFoundError:
            # If project_metadata.json doesn't exist, try metadata.json
            try:
                project_data = pkg_resources.read_text(
                    'sglawwatch_to_sqlite',
                    'metadata.json'
                )
                click.echo("Using internal metadata.json")
                metadata = json.loads(project_data)

                # If it's a complete metadata structure, extract the database part
                if 'databases' in metadata and DATABASE_NAME in metadata['databases']:
                    return metadata['databases'][DATABASE_NAME]
                else:
                    return metadata
            except FileNotFoundError:
                # Create a minimal fallback metadata
                click.echo("Warning: No internal metadata found, using minimal fallback")
                return {
                    "title": "Singapore Law Watch Headlines",
                    "description": "Headlines from Singapore Law Watch's RSS feed",
                    "tables": {
                        "headlines": {
                            "title": "Legal Headlines",
                            "description": "Headlines from Singapore Law Watch's RSS feed"
                        }
                    }
                }

    def update_metadata(self, dry_run=False):
        """
        Update Datasette metadata with project metadata.

        Args:
            dry_run: If True, don't save changes, just preview them

        Returns:
            A tuple (bool, str) indicating if changes were made and a message
        """
        # Check if database entry exists in the metadata
        db_name = DATABASE_NAME

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

        if dry_run:
            # Create a copy to show what would change WITHOUT modifying self.metadata
            preview_metadata = json.loads(json.dumps(self.metadata))  # Deep copy
            preview_metadata["databases"][db_name] = self.project_metadata
            message = f"Changes would be made to {METADATA_FILENAME} (dry run):\n"
            message += json.dumps(preview_metadata, indent=2)
            return True, message

        # Only update the actual metadata for non-dry-run
        self.metadata["databases"][db_name] = self.project_metadata

        # Save the updated metadata
        with open(self.local_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        # Save to storage location
        saved_location = self.storage.save(self.local_path, filename=METADATA_FILENAME)

        message = f"Metadata updated and saved to {saved_location}"
        return True, message

    def update_from_zeeker_assets(self, assets_dir=None, dry_run=False):
        """
        Update metadata using complete Zeeker assets metadata.json.

        This merges the complete Zeeker metadata with existing metadata,
        preserving other database configurations.

        Args:
            assets_dir: Directory containing Zeeker assets (defaults to self.assets_dir)
            dry_run: If True, don't save changes, just preview them

        Returns:
            A tuple (bool, str) indicating if changes were made and a message
        """
        if assets_dir is None:
            assets_dir = self.assets_dir

        zeeker_metadata_path = os.path.join(assets_dir, 'metadata.json')
        if not os.path.exists(zeeker_metadata_path):
            raise FileNotFoundError(f"No metadata.json found in {assets_dir}")

        with open(zeeker_metadata_path, 'r') as f:
            zeeker_metadata = json.load(f)

        # Merge Zeeker metadata with existing metadata
        # This is a more sophisticated merge than just updating the database section
        original_metadata = json.dumps(self.metadata, sort_keys=True)

        # Update root-level properties from Zeeker metadata
        for key in ['title', 'description', 'license', 'license_url', 'source', 'source_url', 'about', 'about_url']:
            if key in zeeker_metadata:
                self.metadata[key] = zeeker_metadata[key]

        # Append CSS/JS URLs (don't replace)
        if 'extra_css_urls' in zeeker_metadata:
            if 'extra_css_urls' not in self.metadata:
                self.metadata['extra_css_urls'] = []
            for url in zeeker_metadata['extra_css_urls']:
                if url not in self.metadata['extra_css_urls']:
                    self.metadata['extra_css_urls'].append(url)

        if 'extra_js_urls' in zeeker_metadata:
            if 'extra_js_urls' not in self.metadata:
                self.metadata['extra_js_urls'] = []
            for url in zeeker_metadata['extra_js_urls']:
                if url not in self.metadata['extra_js_urls']:
                    self.metadata['extra_js_urls'].append(url)

        # Merge database configurations
        if 'databases' not in self.metadata:
            self.metadata['databases'] = {}

        if 'databases' in zeeker_metadata:
            for db_name, db_config in zeeker_metadata['databases'].items():
                self.metadata['databases'][db_name] = db_config

        # Check if changes were made
        new_metadata = json.dumps(self.metadata, sort_keys=True)
        changes_needed = original_metadata != new_metadata

        if not changes_needed:
            message = "No changes needed - metadata is already up to date with Zeeker assets"
            return False, message

        if dry_run:
            message = f"Changes would be made to {METADATA_FILENAME} using Zeeker assets (dry run):\n"
            message += json.dumps(self.metadata, indent=2)
            return True, message

        # Save the updated metadata
        with open(self.local_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        # Save to storage location
        saved_location = self.storage.save(self.local_path, filename=METADATA_FILENAME)

        message = f"Metadata updated from Zeeker assets and saved to {saved_location}"
        return True, message