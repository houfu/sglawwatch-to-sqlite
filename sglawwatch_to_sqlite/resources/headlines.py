import asyncio
import os
from datetime import datetime

import click
import feedparser
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from sglawwatch_to_sqlite.db_manager import DatabaseManager

SYSTEM_PROMPT_TEXT = "As an AI expert in legal affairs, your task is to provide concise, yet comprehensive " \
                     "summaries of legal news articles for time-constrained attorneys. These summaries " \
                     "should highlight the critical legal aspects, relevant precedents, and implications of " \
                     "the issues discussed in the articles.\n\nDespite their complexity, the summaries " \
                     "should be accessible and digestible, written in an engaging and conversational style. " \
                     "Accuracy and attention to detail are essential, as the readers will be legal " \
                     "professionals who may use these summaries to inform their practice.\n\n" \
                     "### Instructions: \n1. Begin the summary with a brief introduction of the topic of " \
                     "the article.\n2. Outline the main legal aspects, implications, and precedents " \
                     "highlighted in the article. \n3. End the summary with a succinct conclusion or " \
                     "takeaway.\n\nThe summaries should not be longer than 100 words, but ensure they " \
                     "efficiently deliver the key legal insights, making them beneficial for quick " \
                     "comprehension. The end goal is to help the lawyers understand the crux of the " \
                     "articles without having to read them in their entirety."


def get_hash_id(entry_date: str, entry_title: str) -> str:
    """Generate a hash ID for the entry."""
    import hashlib
    return hashlib.md5(f"{entry_date}|{entry_title}".encode()).hexdigest()


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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=1, max=10))
async def get_jina_reader_content(link: str) -> str:
    """Fetch content from the Jina reader link."""
    jina_token = os.environ.get('JINA_API_TOKEN')
    if not jina_token:
        click.echo("JINA_API_TOKEN environment variable not set", err=True)
        return ""
    jina_link = f"https://r.jina.ai/{link}"
    headers = {
        "Authorization": f"Bearer {jina_token}",
        "X-Retain-Images": "none",
        "X-Target-Selector": "article"
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.get(jina_link, headers=headers)
        return r.text
    except httpx.RequestError as e:
        click.echo(f"Error fetching content from Jina reader: {e}", err=True)
        return ""


async def get_summary(text: str) -> str:
    """Generate a summary of the article text using OpenAI."""
    if not os.environ.get('OPENAI_API_KEY'):
        click.echo("OPENAI_API_KEY environment variable not set", err=True)
        return ""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(max_retries=3, timeout=60)
    try:
        response = await client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": SYSTEM_PROMPT_TEXT
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Here is an article to summarise:\n {text}"
                        }
                    ]
                }
            ],
            text={
                "format": {
                    "type": "text"
                }
            },
            temperature=0.42,
            max_output_tokens=2048,
            top_p=1,
            store=False
        )
        return response.output_text
    except Exception as e:
        click.echo(f"Error generating summary from OpenAI: {e}", err=True)
        return ""


async def process_entry(db_manager: DatabaseManager, entry: dict, last_updated: str) -> tuple[datetime, bool, dict]:
    """Process a single feed entry."""
    entry_date = datetime.fromisoformat(convert_date_to_iso(entry['published']))
    last_updated_date = datetime.fromisoformat(last_updated) if last_updated else None

    # Check if the entry is newer than the last updated date
    is_new_entry = True
    if last_updated_date:
        is_new_entry = entry_date > last_updated_date

    # Prepare the entry data
    entry_data = {
        "id": get_hash_id(entry_date.isoformat(), entry['title']),
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


async def fetch_headlines(db_manager: DatabaseManager, url: str, all_entries=False) -> list:
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

    tasks = []
    for entry in feed.entries:
        # Skip entries with titles starting with "ADV"
        if entry.get('title', '').startswith('ADV:'):
            skipped_adv_count += 1
            click.echo(f"Skipping advertisement: {entry.get('title', '')}")
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

    return new_entries