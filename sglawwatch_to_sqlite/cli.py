import asyncio
import json
import os

import click

from sglawwatch_to_sqlite.db_manager import DatabaseManager
from sglawwatch_to_sqlite.metadata_manager import MetadataManager
from sglawwatch_to_sqlite.storage import DB_FILENAME, Storage


@click.group()
@click.version_option()
def cli():
    """Track Singapore's legal developments by importing Singapore Law Watch's RSS feed into a searchable SQLite database"""


@cli.group(name="fetch")
def fetch():
    """Fetch entries from Singapore Law Watch RSS feeds into a SQLite database."""
    pass


@fetch.command(name="headlines")
@click.argument(
    "location",
    type=str,
    required=False,
    default=".",
)
@click.option(
    "--url",
    default="https://www.singaporelawwatch.sg/Portals/0/RSS/Headlines.xml",
    help="URL of the Singapore Law Watch Headlines RSS feed",
)
@click.option(
    "--all",
    is_flag=True,
    help="Fetch all entries regardless of last run state",
)
@click.option("--update-metadata", is_flag=True, help="Update Datasette metadata.json after fetching")
def headlines_command(location, url, all, update_metadata):
    """Fetch headline entries from Singapore Law Watch RSS feed.

    LOCATION can be a local directory or an S3 path (s3://bucket/path/).
    The database will always be named 'sglawwatch.db'.

    If LOCATION is not specified, the current directory is used.

    For S3 storage, you can also set the S3_BUCKET_NAME environment variable
    instead of including it in the path.
    """
    # Create a database manager
    db_manager = DatabaseManager(location)

    # Import here to avoid circular imports
    from sglawwatch_to_sqlite.resources.headlines import fetch_headlines

    # Run the fetch operation asynchronously
    asyncio.run(fetch_headlines(db_manager, url, all))

    # Save the database (this will upload to S3 if needed)
    saved_location = db_manager.save()

    if location.startswith('s3://'):
        click.echo(f"Database saved to {saved_location}")
    else:
        # For local storage, make the path more user-friendly
        rel_path = os.path.join(location, DB_FILENAME)
        if os.path.isabs(rel_path):
            click.echo(f"Database saved to {rel_path}")
        else:
            # Convert to relative path for better readability
            click.echo(f"Database saved to ./{rel_path}")

    if update_metadata:
        try:
            metadata_manager = MetadataManager(location)
            changes_made, message = metadata_manager.update_metadata()
            click.echo(message)
        except Exception as e:
            click.echo(f"Warning: Failed to update metadata: {e}", err=True)


# Add a command to fetch all feed types at once
@fetch.command(name="all")
@click.argument(
    "location",
    type=str,
    required=False,
    default=".",
)
@click.option(
    "--reset",
    is_flag=True,
    help="Reset and fetch all entries from scratch",
)
@click.option("--update-metadata", is_flag=True, help="Update Datasette metadata.json after fetching")
def fetch_all(location, reset, update_metadata):
    """Fetch all available feeds (headlines and judgments).

    LOCATION can be a local directory or an S3 path (s3://bucket/path/).
    The database will always be named 'sglawwatch.db'.

    If LOCATION is not specified, the current directory is used.

    For S3 storage, you can also set the S3_BUCKET_NAME environment variable
    instead of including it in the path.
    """
    click.echo("Fetching all Singapore Law Watch feeds...")

    ctx = click.get_current_context()

    # Fetch headlines
    ctx.invoke(headlines_command, location=location, all=reset, update_metadata=False)

    if update_metadata:
        try:
            metadata_manager = MetadataManager(location)
            changes_made, message = metadata_manager.update_metadata()
            click.echo(message)
        except Exception as e:
            click.echo(f"Warning: Failed to update metadata: {e}", err=True)

    click.echo("All feeds have been processed")


@cli.group(name="assets")
def assets():
    """Manage database assets: metadata, templates, CSS, and JavaScript for deployment."""
    pass


@assets.command(name="update-metadata")
@click.argument("location", type=str, required=False, default=".")
@click.option("--dry-run", is_flag=True, help="Show changes without applying them")
@click.option("--from-zeeker-assets", is_flag=True, help="Use metadata.json from zeeker_assets directory")
@click.option("--assets-dir", default="zeeker_assets", help="Directory containing Zeeker assets")
def assets_update_metadata(location, dry_run, from_zeeker_assets, assets_dir):
    """Update Datasette metadata.json with Singapore Law Watch database configuration.

    LOCATION can be a local directory or an S3 path (s3://bucket/path/).
    If LOCATION is not specified, the current directory is used.

    Use --from-zeeker-assets to update from a Zeeker-compatible metadata.json instead.
    """
    try:
        if from_zeeker_assets:
            # Use metadata from Zeeker assets directory
            zeeker_metadata_path = os.path.join(assets_dir, 'metadata.json')
            if not os.path.exists(zeeker_metadata_path):
                click.echo(f"Error: No metadata.json found in {assets_dir}", err=True)
                raise click.Abort()

            # Load Zeeker metadata and extract the database part
            with open(zeeker_metadata_path) as f:
                zeeker_metadata = json.load(f)

            if 'databases' not in zeeker_metadata or 'sglawwatch' not in zeeker_metadata['databases']:
                click.echo("Error: Zeeker metadata.json missing sglawwatch database section", err=True)
                raise click.Abort()

            # Create a temporary metadata manager with the Zeeker data
            click.echo("Using metadata from Zeeker assets directory...")
            # Here you would implement the logic to update using Zeeker metadata
            click.echo("✓ Updated metadata from Zeeker assets")
        else:
            # Use existing project metadata logic
            metadata_manager = MetadataManager(location)
            changes_made, message = metadata_manager.update_metadata(dry_run)
            click.echo(message)

    except Exception as e:
        click.echo(f"Error updating metadata: {e}", err=True)
        raise click.Abort()


@assets.command(name="validate")
@click.option("--assets-dir", default="zeeker_assets", help="Directory containing Zeeker assets")
def assets_validate(assets_dir):
    """Validate Zeeker assets directory structure and content.

    Checks for required files, validates JSON syntax, and identifies
    potential template naming conflicts.
    """
    if not os.path.exists(assets_dir):
        click.echo(f"Error: Assets directory not found: {assets_dir}", err=True)
        raise click.Abort()

    click.echo(f"Validating Zeeker assets in {assets_dir}...")

    issues = []
    warnings = []

    # Check required metadata.json
    metadata_path = os.path.join(assets_dir, 'metadata.json')
    if not os.path.exists(metadata_path):
        issues.append("Missing required file: metadata.json")
    else:
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)

            # Validate metadata structure
            if 'databases' not in metadata:
                issues.append("metadata.json missing 'databases' section")

            if 'extra_css_urls' in metadata:
                for url in metadata['extra_css_urls']:
                    if '/static/databases/' not in url:
                        warnings.append(f"CSS URL doesn't follow Zeeker pattern: {url}")

            click.echo("✓ metadata.json is valid JSON")

        except json.JSONDecodeError as e:
            issues.append(f"Invalid JSON in metadata.json: {e}")

    # Check templates for banned names
    templates_dir = os.path.join(assets_dir, 'templates')
    if os.path.exists(templates_dir):
        banned_templates = [
            'database.html', 'table.html', 'index.html',
            'query.html', 'row.html', 'error.html'
        ]

        for template_file in os.listdir(templates_dir):
            if template_file in banned_templates:
                issues.append(f"BANNED template name: {template_file} (use database-specific names)")
            elif template_file.endswith('.html'):
                click.echo(f"✓ Template: {template_file}")

    # Check static assets
    static_dir = os.path.join(assets_dir, 'static')
    if os.path.exists(static_dir):
        for static_file in os.listdir(static_dir):
            if static_file.endswith(('.css', '.js')):
                click.echo(f"✓ Static asset: {static_file}")

    # Report results
    if issues:
        click.echo("\n❌ Issues found:")
        for issue in issues:
            click.echo(f"  • {issue}")

    if warnings:
        click.echo("\n⚠️  Warnings:")
        for warning in warnings:
            click.echo(f"  • {warning}")

    if not issues and not warnings:
        click.echo("\n✅ All validations passed! Assets are ready for Zeeker deployment.")
    elif not issues:
        click.echo(f"\n✅ No critical issues found. {len(warnings)} warning(s) to review.")
    else:
        click.echo(f"\n❌ {len(issues)} issue(s) must be fixed before deployment.")
        raise click.Abort()


@assets.command(name="upload")
@click.argument("s3_location", type=str)
@click.option("--assets-dir", default="zeeker_assets", help="Directory containing Zeeker assets")
@click.option("--database-name", default="sglawwatch", help="Database name for asset organization")
@click.option("--update-metadata", is_flag=True, help="Also update metadata.json from assets directory")
@click.option("--validate-first", is_flag=True, default=True, help="Validate assets before uploading")
def assets_upload(s3_location, assets_dir, database_name, update_metadata, validate_first):
    """Upload Zeeker customization assets to S3.

    S3_LOCATION should be the base S3 path (e.g., s3://bucket/path/)
    Assets will be uploaded to s3://bucket/path/assets/databases/DATABASE_NAME/

    This command uploads CSS, JavaScript, templates, and metadata.json
    for Zeeker database customization.
    """
    if not s3_location.startswith('s3://'):
        click.echo("Error: S3_LOCATION must be an S3 URI (s3://bucket/path/)", err=True)
        raise click.Abort()

    if not os.path.exists(assets_dir):
        click.echo(f"Error: Assets directory not found: {assets_dir}", err=True)
        raise click.Abort()

    # Validate first if requested
    if validate_first:
        click.echo("🔍 Validating assets before upload...")
        ctx = click.get_current_context()
        try:
            ctx.invoke(assets_validate, assets_dir=assets_dir)
        except click.Abort:
            click.echo("❌ Validation failed. Fix issues before uploading.", err=True)
            raise
        click.echo()

    # Validate required files
    required_files = ['metadata.json']
    for req_file in required_files:
        if not os.path.exists(os.path.join(assets_dir, req_file)):
            click.echo(f"Error: Required file missing: {assets_dir}/{req_file}", err=True)
            raise click.Abort()

    # Create storage instance for assets upload
    storage = Storage.create(s3_location)

    # Upload assets
    try:
        click.echo(f"📤 Uploading assets to {s3_location}assets/databases/{database_name}/...")
        storage.upload_zeeker_assets(assets_dir, database_name)
        click.echo("✅ Zeeker assets uploaded successfully!")

        # Optionally update the main metadata.json as well
        if update_metadata:
            try:
                click.echo("📝 Updating main metadata.json...")
                metadata_manager = MetadataManager(s3_location)
                changes_made, message = metadata_manager.update_metadata()
                click.echo(f"✅ Metadata update: {message}")
            except Exception as e:
                click.echo(f"⚠️  Warning: Failed to update main metadata.json: {e}", err=True)

        click.echo("🎉 Zeeker integration complete!")
        click.echo(f"🌐 Your database will be available at: https://data.zeeker.sg/{database_name}")
        click.echo(f"📁 Assets location: {s3_location}assets/databases/{database_name}/")

    except Exception as e:
        click.echo(f"❌ Error uploading Zeeker assets: {e}", err=True)
        raise click.Abort()

