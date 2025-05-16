import asyncio
from datetime import datetime
from typing import Tuple, Dict

import click
import feedparser

from sglawwatch_to_sqlite.db_manager import DatabaseManager
from sglawwatch_to_sqlite.tools import get_jina_reader_content, get_summary, get_hash_id


def convert_date_to_iso(date_str: str) -> str:
    """Convert date string like '08 May 2025 00:01:00' to ISO format."""
    try:
        parsed_date = datetime.strptime(date_str, '%d %B %Y %H:%M:%S')
        return parsed_date.isoformat()  # Returns '2025-05-08T00:01:00'
    except ValueError:
        # Handle potential parsing errors
        try:
            # Try alternative format with abbreviated month name
            parsed_date = datetime.strptime(date_str, '%d %b %Y %H:%M:%S')
            return parsed_date.isoformat()
        except ValueError:
            # If all parsing attempts fail, return original or a default
            return datetime.now().isoformat()


async def process_entry(db_manager: DatabaseManager, entry: Dict, last_updated: str) -> Tuple[datetime, bool, Dict]:
    """Process a single feed entry."""
    entry_date = datetime.fromisoformat(convert_date_to_iso(entry['published']))
    last_updated_date = datetime.fromisoformat(last_updated) if last_updated else None

    # Check if the entry is newer than the last updated date
    is_new_entry = True
    if last_updated_date:
        is_new_entry = entry_date > last_updated_date

    # Prepare the entry data
    entry_data = {
        "id": get_hash_id([entry_date.isoformat(), entry['title']]),
        "category": entry.get("category", ""),
        "title": entry.get("title", ""),
        "source_link": entry.get("link", ""),
        "author": entry.get("author", ""),
        "date": entry_date.isoformat(),
        "imported_on": datetime.now().isoformat()
    }

    # Echo information about the entry being processed
    click.echo(f"Processing: {entry_data['title']} from {entry_data['date']}")

    if is_new_entry:
        click.echo(f"  → Fetching content for: {entry_data['title']}")
        entry_data["text"] = await get_jina_reader_content(entry_data["source_link"])

        click.echo(f"  → Generating summary for: {entry_data['title']}")
        entry_data["summary"] = await get_summary(entry_data["text"])

        # Get the database and insert the new entry
        db = db_manager.get_database()
        db["headlines"].insert(entry_data, pk="id")
        click.echo(f"  ✓ Added to database: {entry_data['title']}")
    else:
        click.echo(f"  → Skipping (already processed): {entry_data['title']}")

    return entry_date, is_new_entry, entry_data if is_new_entry else None


async def fetch_headlines(db_manager: DatabaseManager, url: str, all_entries=False, max_age_limit=60) -> list:
    """Fetch headline entries from Singapore Law Watch RSS feed."""
    click.echo(f"Fetching headlines from {url}")

    # Get the last updated timestamp
    last_updated = None if all_entries else db_manager.get_last_updated("headlines")

    # Parse the RSS feed
    feed = feedparser.parse(url)

    if feed.bozo:
        click.echo(f"Warning: RSS feed parsing error - {feed.bozo_exception}", err=True)

    if not feed.entries:
        click.echo("No entries found in the feed.")
        return []

    # Track the most recent entry timestamp
    most_recent_timestamp: None | datetime = None
    new_entries_count = 0
    new_entries = []
    skipped_adv_count = 0
    skipped_old_count = 0
    current_date = datetime.now()

    tasks = []
    for entry in feed.entries:
        # Skip entries with titles starting with "ADV"
        if entry.get('title', '').startswith('ADV:'):
            skipped_adv_count += 1
            click.echo(f"Skipping advertisement: {entry.get('title', '')}")
            continue

        # Skip entries older than max_age_days
        entry_date = datetime.fromisoformat(convert_date_to_iso(entry.get('published', '')))
        days_old = (current_date - entry_date).days
        if days_old > max_age_limit:
            skipped_old_count += 1
            click.echo(f"Skipping old headline ({days_old} days): {entry.get('title', '')}")
            continue

        task = asyncio.create_task(process_entry(db_manager, entry, last_updated))
        tasks.append(task)

    # Wait for all tasks to complete
    results = await asyncio.gather(*tasks)

    # Process results
    for timestamp, is_new, entry_data in results:
        if is_new:
            new_entries_count += 1
            if entry_data:
                new_entries.append(entry_data)

        if not most_recent_timestamp or timestamp > most_recent_timestamp:
            most_recent_timestamp = timestamp

    if most_recent_timestamp:
        db_manager.update_last_updated("headlines", datetime.isoformat(most_recent_timestamp))

    click.echo(f"Added {new_entries_count} new headlines")
    if skipped_adv_count > 0:
        click.echo(f"Skipped {skipped_adv_count} advertisements")
    if skipped_old_count > 0:
        click.echo(f"Skipped {skipped_old_count} headlines older than {max_age_limit} days")

    return new_entries