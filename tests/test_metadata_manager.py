# tests/test_metadata_manager.py
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import click
import pytest

from sglawwatch_to_sqlite.metadata_manager import MetadataManager, METADATA_FILENAME, \
    DATABASE_NAME


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
        "description": "A database of legal news headlines from Singapore Law Watch",
        "license": "Apache License 2.0",
        "license_url": "https://github.com/houfu/sglawwatch-to-sqlite/blob/master/LICENSE",
        "source": "Singapore Law Watch",
        "source_url": "https://www.singaporelawwatch.sg/",
        "about": "This database contains legal news headlines imported from Singapore Law Watch's RSS feed.",
        "about_url": "https://github.com/houfu/sglawwatch-to-sqlite",
        "tables": {
            "headlines": {
                "title": "Legal Headlines",
                "description": "Headlines from Singapore Law Watch's RSS feed",
                "sortable_columns": ["date", "author"],
                "facets": ["category", "author", "date"],
                "columns": {
                    "id": {
                        "title": "ID",
                        "description": "Unique identifier for each headline"
                    },
                    "category": {
                        "title": "Category",
                        "description": "The category of the news article"
                    },
                    "title": {
                        "title": "Title",
                        "description": "The headline title"
                    },
                    "source_link": {
                        "title": "Source",
                        "description": "URL to the original article"
                    },
                    "author": {
                        "title": "Author",
                        "description": "The author or publication"
                    },
                    "date": {
                        "title": "Date",
                        "description": "Publication date in ISO format"
                    },
                    "summary": {
                        "title": "Summary",
                        "description": "AI-generated summary of the article"
                    },
                    "text": {
                        "title": "Content",
                        "description": "Full text content of the article"
                    },
                    "imported_on": {
                        "title": "Imported On",
                        "description": "When the article was imported into the database"
                    }
                }
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
    """Mock the project_metadata.json file."""
    with patch('sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text',
               return_value=json.dumps(sample_project_metadata)):
        return sample_project_metadata


def test_metadata_manager_initialization(temp_dir, metadata_file, mock_project_metadata):
    """Test that MetadataManager initializes correctly."""
    with patch('os.path.dirname', return_value=os.path.dirname(metadata_file)):
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


def test_metadata_manager_invalid_json(temp_dir):
    """Test behavior when metadata.json contains invalid JSON."""
    # Create an invalid JSON file
    metadata_path = os.path.join(temp_dir, METADATA_FILENAME)
    with open(metadata_path, 'w') as f:
        f.write("{invalid json")

    # Mock project_metadata.json to exist
    with patch('os.path.exists', return_value=True):
        with patch('builtins.open') as mock_open:
            def side_effect(path, *args, **kwargs):
                if path == metadata_path:
                    # Use the real file for metadata.json
                    return open.__enter__(path, *args, **kwargs)
                else:
                    # Mock for project_metadata.json
                    mock = MagicMock()
                    mock.__enter__.return_value.read.return_value = "{}"
                    return mock

            mock_open.side_effect = side_effect

            # Initialization should raise Abort
            with pytest.raises(click.exceptions.Abort):
                MetadataManager(temp_dir)


def test_metadata_manager_update_no_changes(temp_dir, metadata_file, mock_project_metadata):
    """Test update when no changes are needed."""
    with patch('os.path.dirname') as mock_dirname:
        mock_dirname.return_value = temp_dir

        # Setup existing metadata to already include our project metadata
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        metadata["databases"][DATABASE_NAME] = mock_project_metadata

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f)

        # Initialize manager and try to update
        manager = MetadataManager(temp_dir)
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

        assert DATABASE_NAME in updated_metadata["databases"]
        assert updated_metadata["databases"][DATABASE_NAME]["title"] == mock_project_metadata["title"]


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
        assert "Changes would be made" in message

        # Check that the file wasn't actually updated
        with open(metadata_file, 'r') as f:
            updated_metadata = json.load(f)

        assert DATABASE_NAME not in updated_metadata["databases"]


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

        assert DATABASE_NAME in updated_metadata["databases"]
        assert updated_metadata["databases"][DATABASE_NAME] == mock_project_metadata
