# tests/test_metadata_manager.py
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import click
import pytest

from sglawwatch_to_sqlite.metadata_manager import MetadataManager, METADATA_FILENAME


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def sample_metadata():
    """Create a sample metadata.json content."""
    return {
        "title": "Test Datasette",
        "description": "Test description",
        "databases": {
            "other_db": {
                "title": "Other Database"
            }
        }
    }


@pytest.fixture
def sample_project_metadata():
    """Create a sample project metadata content."""
    return {
        "title": "Singapore Law Watch Headlines",
        "description": "A database of legal news headlines",
        "tables": {
            "headlines": {
                "title": "Legal Headlines",
                "sortable_columns": ["date"]
            }
        }
    }


@pytest.fixture
def metadata_file(temp_dir, sample_metadata):
    """Create a temporary metadata.json file."""
    metadata_path = os.path.join(temp_dir, METADATA_FILENAME)
    with open(metadata_path, 'w') as f:
        json.dump(sample_metadata, f)
    return metadata_path


@pytest.fixture
def mock_project_metadata(sample_project_metadata):
    """Create a mock for the project metadata file."""
    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        with patch('builtins.open', new_callable=MagicMock) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.return_value = json.dumps(sample_project_metadata)
            mock_open.return_value = mock_file
            yield sample_project_metadata


def test_metadata_manager_initialization(temp_dir, metadata_file, mock_project_metadata):
    """Test that MetadataManager initializes correctly."""
    with patch('os.path.dirname') as mock_dirname:
        mock_dirname.return_value = temp_dir

        manager = MetadataManager(temp_dir)

        # Verify metadata was loaded correctly
        assert "title" in manager.metadata
        assert "databases" in manager.metadata
        assert "other_db" in manager.metadata["databases"]

        # Verify project metadata was loaded
        assert manager.project_metadata["title"] == "Singapore Law Watch Headlines"


def test_metadata_manager_missing_file(temp_dir):
    """Test behavior when metadata.json doesn't exist."""
    with pytest.raises(click.exceptions.Abort):
        MetadataManager(temp_dir)


def test_metadata_manager_update_no_changes(temp_dir, metadata_file, mock_project_metadata):
    """Test update when no changes are needed."""
    with patch('os.path.dirname') as mock_dirname:
        mock_dirname.return_value = temp_dir

        # Setup existing metadata to already include our project metadata
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        metadata["databases"]["sglawwatch"] = mock_project_metadata

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f)

        # Initialize manager and try to update
        manager = MetadataManager(temp_dir)
        with patch.object(manager, '_calculate_hash') as mock_hash:
            # Make hash function return same value for any input to simulate no changes
            mock_hash.return_value = "same_hash"

            changes_made, message = manager.update_metadata()

            assert not changes_made
            assert "already up to date" in message


def test_metadata_manager_update_with_changes(temp_dir, metadata_file, mock_project_metadata):
    """Test update when changes are needed."""
    with patch('os.path.dirname') as mock_dirname:
        mock_dirname.return_value = temp_dir

        # Initialize manager
        manager = MetadataManager(temp_dir)

        # Run update
        changes_made, message = manager.update_metadata()

        # Verify changes
        assert changes_made
        assert "updated" in message

        # Check that the file was updated
        with open(metadata_file, 'r') as f:
            updated_metadata = json.load(f)

        assert "sglawwatch" in updated_metadata["databases"]
        assert updated_metadata["databases"]["sglawwatch"]["title"] == mock_project_metadata["title"]


def test_metadata_manager_update_dry_run(temp_dir, metadata_file, mock_project_metadata):
    """Test update with dry run option."""
    with patch('os.path.dirname') as mock_dirname:
        mock_dirname.return_value = temp_dir

        # Initialize manager
        manager = MetadataManager(temp_dir)

        # Run update with dry run
        changes_made, message = manager.update_metadata(dry_run=True)

        # Verify changes would be made but weren't
        assert changes_made
        assert "dry run" in message

        # Check that the file wasn't actually updated
        with open(metadata_file, 'r') as f:
            updated_metadata = json.load(f)

        assert "sglawwatch" not in updated_metadata["databases"]


def test_metadata_manager_create_new_database_entry(temp_dir, metadata_file, mock_project_metadata):
    """Test update when database entry doesn't exist yet."""
    with patch('os.path.dirname') as mock_dirname:
        mock_dirname.return_value = temp_dir

        # Initialize manager
        manager = MetadataManager(temp_dir)

        # Run update
        changes_made, message = manager.update_metadata()

        # Verify changes
        assert changes_made
        assert "updated" in message

        # Check that the file was updated with new database entry
        with open(metadata_file, 'r') as f:
            updated_metadata = json.load(f)

        assert "sglawwatch" in updated_metadata["databases"]
        assert updated_metadata["databases"]["sglawwatch"] == mock_project_metadata


@patch("sglawwatch_to_sqlite.storage.S3Storage")
def test_metadata_manager_s3(mock_s3_storage, mock_project_metadata):
    """Test MetadataManager with S3 URI."""
    # Setup mock
    mock_instance = MagicMock()
    mock_instance.get_local_path.return_value = "temp_metadata.json"
    mock_s3_storage.return_value = mock_instance

    # Mock file operations
    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = True
        with patch('builtins.open', new_callable=MagicMock) as mock_open:
            mock_file = MagicMock()
            mock_file.__enter__.return_value.read.side_effect = [
                json.dumps({"title": "Test"}),  # First open for metadata.json
                json.dumps(mock_project_metadata)  # Second open for project metadata
            ]
            mock_open.return_value = mock_file

            # Create metadata manager with S3 URI
            with patch('os.path.dirname') as mock_dirname:
                mock_dirname.return_value = "/tmp"
                manager = MetadataManager("s3://test-bucket/path/")

            # Verify S3Storage was used
            mock_s3_storage.assert_called_once_with("s3://test-bucket/path/")
            mock_instance.get_local_path.assert_called_once_with(filename=METADATA_FILENAME)
