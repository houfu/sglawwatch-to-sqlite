import asyncio
import click
import os

from sglawwatch_to_sqlite.db_manager import DatabaseManager
from sglawwatch_to_sqlite.storage import DB_FILENAME


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
def headlines_command(location, url, all):
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
def fetch_all(location, reset):
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
    ctx.invoke(headlines_command, location=location, all=reset)

    click.echo("All feeds have been processed")