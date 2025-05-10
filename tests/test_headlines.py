import datetime
import hashlib
from unittest.mock import patch, MagicMock

import pytest

from sglawwatch_to_sqlite.resources.headlines import (
    get_hash_id,
    convert_date_to_iso,
    get_jina_reader_content,
    get_summary,
    process_entry,
    fetch_headlines
)


# Test get_hash_id function
def test_get_hash_id():
    # Given
    entry_date = datetime.datetime(2025, 5, 8, 0, 1, 0).isoformat()
    entry_title = "Test Case Headline"

    # When
    hash_id = get_hash_id(entry_date, entry_title)

    # Then - create the expected hash manually to verify
    expected = hashlib.md5(f"{entry_date}|{entry_title}".encode()).hexdigest()
    assert hash_id == expected

    # Verify different inputs produce different hashes
    assert get_hash_id(entry_date, "Different Title") != hash_id


# Test convert_date_to_iso function
def test_convert_date_to_iso():
    # Test standard format
    assert convert_date_to_iso("08 May 2025 00:01:00") == "2025-05-08T00:01:00"

    # Test abbreviated month format
    assert convert_date_to_iso("08 May 2025 00:01:00") == "2025-05-08T00:01:00"

    mock_now = datetime.datetime(2025, 5, 8, 0, 1, 0)

    # Test error handling with mock datetime.now
    with patch('sglawwatch_to_sqlite.resources.headlines.datetime') as mock_datetime:
        mock_datetime.now.return_value = mock_now
        mock_datetime.strptime.side_effect = ValueError("Invalid date format")
        mock_datetime.fromisoformat = datetime.datetime.fromisoformat  # Keep this method working

        # Should return current date in ISO format when parsing fails
        assert convert_date_to_iso("invalid date") == "2025-05-08T00:01:00"


# Test get_jina_reader_content function with fixtures
@pytest.mark.asyncio
async def test_get_jina_reader_content(mock_httpx_client, mock_env_vars):
    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        # Test
        content = await get_jina_reader_content("https://example.com/article")

        # Verify
        assert content == "<article>Sample article content</article>"
        # Verify correct URL and headers were used
        mock_httpx_client.__aenter__.return_value.get.assert_called_once()


# Test get_summary function with fixtures
@pytest.mark.asyncio
async def test_get_summary(mock_openai_client):
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake-api-key'}):
        with patch('openai.AsyncOpenAI', return_value=mock_openai_client):
            # Test
            summary = await get_summary("This is a long article text that needs summarizing.")

            # Verify
            assert summary == "This is a concise legal summary."
            # Verify OpenAI was called with correct parameters
            mock_openai_client.responses.create.assert_called_once()


# Test process_entry function
@pytest.mark.asyncio
async def test_process_entry_new_entry():
    # Create mock DatabaseManager
    mock_db_manager = MagicMock()
    mock_db = MagicMock()
    mock_db_manager.get_database.return_value = mock_db

    # Mock entry
    entry = {
        'published': '08 May 2025 00:01:00',
        'title': 'Test Article',
        'category': 'Legal',
        'link': 'https://example.com/article',
        'author': 'John Doe'
    }

    # Mock external functions
    with patch('sglawwatch_to_sqlite.resources.headlines.get_jina_reader_content',
               return_value="Article content"):
        with patch('sglawwatch_to_sqlite.resources.headlines.get_summary',
                   return_value="Article summary"):
            # Test with a last_updated timestamp before the entry date
            timestamp, is_new, entry_data = await process_entry(mock_db_manager, entry, "2025-05-07T00:00:00")

            # Verify
            assert timestamp.isoformat() == "2025-05-08T00:01:00"
            assert is_new is True
            assert entry_data is not None
            assert entry_data["title"] == "Test Article"

            # Verify database interaction
            mock_db_manager.get_database.assert_called_once()
            mock_db["headlines"].insert.assert_called_once()


@pytest.mark.asyncio
async def test_process_entry_existing_entry():
    # Create mock DatabaseManager
    mock_db_manager = MagicMock()

    # Mock entry
    entry = {
        'published': '08 May 2025 00:01:00',
        'title': 'Test Article'
    }

    # Test with a last_updated timestamp after the entry date (should skip)
    timestamp, is_new, entry_data = await process_entry(mock_db_manager, entry, "2025-05-09T00:00:00")

    # Verify
    assert timestamp.isoformat() == "2025-05-08T00:01:00"
    assert is_new is False
    assert entry_data is None

    # Verify DB interaction was NOT performed
    mock_db_manager.get_database.assert_not_called()


# Test fetch_headlines with mock feed
@pytest.mark.asyncio
async def test_fetch_headlines(mock_feed):
    # Create mock DatabaseManager
    mock_db_manager = MagicMock()
    mock_db_manager.get_last_updated.return_value = "2025-05-07T00:00:00"

    with patch('feedparser.parse', return_value=mock_feed):
        with patch('sglawwatch_to_sqlite.resources.headlines.process_entry',
                   side_effect=lambda db, entry, last_updated: (
                           datetime.datetime(2025, 5, 8, 0, 1), True, {"id": "123"})):
            # Test
            result = await fetch_headlines(mock_db_manager, "https://example.com/feed")

            # Verify
            assert len(result) > 0
            mock_db_manager.get_last_updated.assert_called_once_with("headlines")
            mock_db_manager.update_last_updated.assert_called_once()


# Test fetch_headlines with no entries
@pytest.mark.asyncio
async def test_fetch_headlines_no_entries():
    # Create mock DatabaseManager
    mock_db_manager = MagicMock()

    # Create a feed with no entries
    empty_feed = MagicMock()
    empty_feed.bozo = False
    empty_feed.entries = []

    with patch('feedparser.parse', return_value=empty_feed):
        # Test
        result = await fetch_headlines(mock_db_manager, "https://example.com/feed")

        # Verify
        assert result == []


# Test fetch_headlines with feed error
@pytest.mark.asyncio
async def test_fetch_headlines_feed_error(mock_feed_error):
    # Create mock DatabaseManager
    mock_db_manager = MagicMock()

    with patch('feedparser.parse', return_value=mock_feed_error):
        with patch('click.echo') as mock_echo:
            # Test
            result = await fetch_headlines(mock_db_manager, "https://example.com/feed")

            # Verify error is logged and empty result is returned
            mock_echo.assert_called_with(
                "No entries found in the feed.",
            )
            assert result == []


@pytest.mark.asyncio
async def test_fetch_headlines_skip_advertisements():
    """Test that headlines with titles starting with 'ADV:' are skipped."""
    # Create mock DatabaseManager
    mock_db_manager = MagicMock()
    mock_db_manager.get_last_updated.return_value = "2025-05-07T00:00:00"

    # Create a mock feed with regular and advertisement entries
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {
            'title': 'Normal Article Title',
            'published': '08 May 2025 00:01:00',
            'link': 'https://example.com/normal'
        },
        {
            'title': 'ADV: Advertisement Article',
            'published': '08 May 2025 00:01:00',
            'link': 'https://example.com/adv'
        },
        {
            'title': 'Another Normal Article',
            'published': '08 May 2025 00:01:00',
            'link': 'https://example.com/another'
        }
    ]

    # Track which entries are processed
    processed_entries = []

    # Mock process_entry to track which entries get processed
    async def mock_process_entry(db, entry, last_updated):
        processed_entries.append(entry['title'])
        return datetime.datetime(2025, 5, 8, 0, 1), True, {"id": "123"}

    with patch('feedparser.parse', return_value=mock_feed):
        with patch('sglawwatch_to_sqlite.resources.headlines.process_entry',
                   side_effect=mock_process_entry):
            with patch('click.echo'):  # To silence output during tests
                # Test
                result = await fetch_headlines(mock_db_manager, "https://example.com/feed")

                # Verify
                assert len(processed_entries) == 2  # Only the non-ADV entries
                assert 'Normal Article Title' in processed_entries
                assert 'Another Normal Article' in processed_entries
                assert 'ADV: Advertisement Article' not in processed_entries
