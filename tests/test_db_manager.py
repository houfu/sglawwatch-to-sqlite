import os
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from sglawwatch_to_sqlite.db_manager import DatabaseManager
from sglawwatch_to_sqlite.storage import DB_FILENAME


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def db_manager(temp_dir):
    """Setup a test database manager and return it."""
    return DatabaseManager(temp_dir)


def test_database_manager_initialization(temp_dir):
    """Test that DatabaseManager initializes correctly."""
    db_manager = DatabaseManager(temp_dir)
    db = db_manager.get_database()

    # Check if all expected tables exist
    table_names = db.table_names()
    assert "schema_versions" in table_names
    assert "headlines" in table_names
    assert "metadata" in table_names

    # Check if schema_versions has expected schema
    schema_versions_schema = db["schema_versions"].columns_dict
    assert "table_name" in schema_versions_schema
    assert "version" in schema_versions_schema
    assert "updated_at" in schema_versions_schema

    # Check if headlines table has expected schema
    headlines_schema = db["headlines"].columns_dict
    assert "id" in headlines_schema
    assert "category" in headlines_schema
    assert "title" in headlines_schema
    assert "source_link" in headlines_schema
    assert "author" in headlines_schema
    assert "date" in headlines_schema
    assert "summary" in headlines_schema
    assert "text" in headlines_schema
    assert "imported_on" in headlines_schema

    # Check if metadata has expected schema
    metadata_schema = db["metadata"].columns_dict
    assert "key" in metadata_schema
    assert "value" in metadata_schema

    # Verify the database was created with the fixed name
    assert os.path.exists(os.path.join(temp_dir, DB_FILENAME))


def test_database_manager_save(db_manager):
    """Test DatabaseManager.save method."""
    # Mock the storage save method
    db_manager.storage.save = MagicMock(return_value="saved/path")

    # Call save
    result = db_manager.save()

    # Verify the mock was called correctly
    db_manager.storage.save.assert_called_once_with(db_manager.local_path)
    assert result == "saved/path"


def test_register_table_version(db_manager):
    """Test that _register_table_version adds entries to schema_versions."""
    db = db_manager.get_database()

    # First clear any existing entries for test table
    db["schema_versions"].delete_where("table_name = ?", ["test_table"])

    # Register a new version
    db_manager._register_table_version("test_table", 2)

    # Check if entry exists
    entry = db["schema_versions"].get("test_table")
    assert entry["table_name"] == "test_table"
    assert entry["version"] == 2

    # Parse date to ensure it's a valid ISO format
    try:
        datetime.fromisoformat(entry["updated_at"])
        valid_date = True
    except ValueError:
        valid_date = False

    assert valid_date


def test_get_last_updated_existing_key(db_manager):
    """Test get_last_updated when the key already exists."""
    db = db_manager.get_database()

    # Setup test data
    feed_type = "test_feed"
    test_timestamp = datetime.now().isoformat()
    db["metadata"].insert({"key": f"{feed_type}_last_updated", "value": test_timestamp})

    # Get the value
    result = db_manager.get_last_updated(feed_type)

    # Check result
    assert result == test_timestamp


def test_get_last_updated_new_key(db_manager):
    """Test get_last_updated when the key doesn't exist."""
    db = db_manager.get_database()

    # Setup test data - Make sure the key doesn't exist
    feed_type = "nonexistent_feed"
    db["metadata"].delete_where("key = ?", [f"{feed_type}_last_updated"])

    # Get the value
    result = db_manager.get_last_updated(feed_type)

    # Check result - Should be empty string and a new entry should be created
    assert result == ""

    # Verify new entry was created
    entry = db["metadata"].get(f"{feed_type}_last_updated")
    assert entry["key"] == f"{feed_type}_last_updated"
    assert entry["value"] == ""


def test_update_last_updated(db_manager):
    """Test update_last_updated function."""
    db = db_manager.get_database()

    # Test the function
    db_manager.update_last_updated("headlines", "2025-05-10T12:34:56")

    # Verify the value was updated
    entry = db["metadata"].get("headlines_last_updated")
    assert entry["value"] == "2025-05-10T12:34:56"


@patch("sglawwatch_to_sqlite.storage.S3Storage")
def test_database_manager_s3(mock_s3_storage, temp_dir):
    """Test DatabaseManager with S3 URI."""
    # Setup mock
    mock_instance = MagicMock()
    mock_instance.get_local_path.return_value = os.path.join(temp_dir, DB_FILENAME)
    mock_s3_storage.return_value = mock_instance

    # Create DatabaseManager with S3 URI
    db_manager = DatabaseManager("s3://test-bucket/path/")

    # Verify the mock was created and used
    mock_s3_storage.assert_called_once_with("s3://test-bucket/path/")
    mock_instance.get_local_path.assert_called_once()

    # Verify the database manager has the correct storage
    assert db_manager.storage == mock_instance