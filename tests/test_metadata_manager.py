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
    """Mock the metadata.json file."""
    with patch('sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text',
               return_value=json.dumps(sample_project_metadata)):
        yield sample_project_metadata


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

    # Mock metadata.json to exist
    with patch('os.path.exists', return_value=True):
        with patch('builtins.open') as mock_open:
            def side_effect(path, *args, **kwargs):
                if path == metadata_path:
                    # Use the real file for metadata.json
                    return open.__enter__(path, *args, **kwargs)
                else:
                    # Mock for metadata.json
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


class TestMetadataManagerS3Integration:
    """Tests for MetadataManager with S3 storage."""

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_metadata_manager_s3_init(self, mock_read_text, mock_storage_class):
        """Test MetadataManager initialization with S3 URI."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage.get_local_path.return_value = "/tmp/metadata.json"
        mock_storage_class.create.return_value = mock_storage

        # Create a temporary metadata file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"databases": {}}, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = '{"title": "Test Project"}'

        try:
            # Test initialization
            manager = MetadataManager("s3://test-bucket/path/")

            # Verify storage was created correctly
            mock_storage_class.create.assert_called_once_with("s3://test-bucket/path/")
            mock_storage.get_local_path.assert_called_once_with(filename=METADATA_FILENAME)

            # Verify metadata was loaded
            assert manager.metadata == {"databases": {}}
            assert manager.project_metadata == {"title": "Test Project"}

        finally:
            os.unlink(temp_path)

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_metadata_manager_s3_file_not_found(self, mock_read_text, mock_storage_class):
        """Test MetadataManager when metadata.json doesn't exist on S3."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage.get_local_path.side_effect = FileNotFoundError("No existing metadata.json found")
        mock_storage_class.create.return_value = mock_storage

        mock_read_text.return_value = '{"title": "Test Project"}'

        # Test initialization should fail gracefully
        with pytest.raises(click.exceptions.Abort):
            MetadataManager("s3://test-bucket/path/")

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_metadata_manager_s3_save(self, mock_read_text, mock_storage_class):
        """Test MetadataManager save with S3 storage."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage

        # Create a temporary metadata file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"databases": {}}, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_storage.save.return_value = "s3://test-bucket/path/metadata.json"
        mock_read_text.return_value = '{"title": "Test Project"}'

        try:
            # Test save operation
            manager = MetadataManager("s3://test-bucket/path/")
            changes_made, message = manager.update_metadata()

            # Verify save was called with correct parameters
            mock_storage.save.assert_called_once_with(temp_path, filename=METADATA_FILENAME)
            assert "s3://test-bucket/path/metadata.json" in message

        finally:
            os.unlink(temp_path)


class TestMetadataManagerErrorHandling:
    """Tests for MetadataManager error handling."""

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    def test_metadata_manager_storage_creation_error(self, mock_storage_class):
        """Test MetadataManager when storage creation fails."""
        mock_storage_class.create.side_effect = Exception("Storage creation failed")

        with pytest.raises(click.exceptions.Abort):
            MetadataManager("invalid://uri")

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_metadata_manager_corrupted_existing_metadata(self, mock_read_text, mock_storage_class):
        """Test MetadataManager with corrupted existing metadata file."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage

        # Create a corrupted metadata file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{invalid json content")
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = '{"title": "Test Project"}'

        try:
            with pytest.raises(click.exceptions.Abort):
                MetadataManager("./test")
        finally:
            os.unlink(temp_path)

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_metadata_manager_corrupted_project_metadata(self, mock_read_text, mock_storage_class):
        """Test MetadataManager with corrupted project metadata."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage

        # Create a valid metadata file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"databases": {}}, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = "{invalid project json}"

        try:
            with pytest.raises(click.exceptions.Abort):
                MetadataManager("./test")
        finally:
            os.unlink(temp_path)


class TestMetadataManagerUpdateScenarios:
    """Tests for various metadata update scenarios."""

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_update_metadata_preserves_other_databases(self, mock_read_text, mock_storage_class):
        """Test that updating metadata preserves other database configurations."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage
        mock_storage.save.return_value = "/tmp/metadata.json"

        # Create metadata with existing database
        existing_metadata = {
            "title": "My Datasette",
            "databases": {
                "other_db": {
                    "title": "Other Database",
                    "description": "Should be preserved"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(existing_metadata, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = '{"title": "SG Law Watch", "description": "New project"}'

        try:
            manager = MetadataManager("./test")
            changes_made, message = manager.update_metadata()

            # Verify other database was preserved
            assert changes_made
            assert "other_db" in manager.metadata["databases"]
            assert manager.metadata["databases"]["other_db"]["title"] == "Other Database"

            # Verify our database was added
            assert DATABASE_NAME in manager.metadata["databases"]
            assert manager.metadata["databases"][DATABASE_NAME]["title"] == "SG Law Watch"

        finally:
            os.unlink(temp_path)

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_update_metadata_no_databases_section(self, mock_read_text, mock_storage_class):
        """Test updating metadata when no databases section exists."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage
        mock_storage.save.return_value = "/tmp/metadata.json"

        # Create metadata without databases section
        existing_metadata = {
            "title": "My Datasette",
            "description": "No databases yet"
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(existing_metadata, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = '{"title": "SG Law Watch"}'

        try:
            manager = MetadataManager("./test")
            changes_made, message = manager.update_metadata()

            # Verify databases section was created
            assert changes_made
            assert "databases" in manager.metadata
            assert DATABASE_NAME in manager.metadata["databases"]

        finally:
            os.unlink(temp_path)

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_update_metadata_complex_project_structure(self, mock_read_text, mock_storage_class):
        """Test updating with complex project metadata structure."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage
        mock_storage.save.return_value = "/tmp/metadata.json"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"databases": {}}, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path

        # Complex project metadata
        complex_project_metadata = {
            "title": "Singapore Law Watch Headlines",
            "description": "Legal news database",
            "license": "Apache-2.0",
            "tables": {
                "headlines": {
                    "title": "Headlines",
                    "facets": ["category", "author"],
                    "sortable_columns": ["date"],
                    "columns": {
                        "title": {"description": "Article title"},
                        "date": {"description": "Publication date"}
                    }
                }
            }
        }
        mock_read_text.return_value = json.dumps(complex_project_metadata)

        try:
            manager = MetadataManager("./test")
            changes_made, message = manager.update_metadata()

            # Verify complex structure was preserved
            assert changes_made
            db_metadata = manager.metadata["databases"][DATABASE_NAME]
            assert db_metadata["license"] == "Apache-2.0"
            assert "headlines" in db_metadata["tables"]
            assert "facets" in db_metadata["tables"]["headlines"]

        finally:
            os.unlink(temp_path)

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_update_metadata_save_failure(self, mock_read_text, mock_storage_class):
        """Test handling of save failure during metadata update."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage
        mock_storage.save.side_effect = Exception("Save failed")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"databases": {}}, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = '{"title": "Test"}'

        try:
            manager = MetadataManager("./test")

            # Dry run should work
            changes_made, message = manager.update_metadata(dry_run=True)
            assert changes_made
            assert "dry run" in message

            # Actual update should fail
            with pytest.raises(Exception, match="Save failed"):
                manager.update_metadata(dry_run=False)

        finally:
            os.unlink(temp_path)


class TestMetadataManagerConstants:
    """Tests for metadata manager constants and configuration."""

    def test_database_name_constant(self):
        """Test that DATABASE_NAME constant is correct."""
        assert DATABASE_NAME == "sglawwatch"

    def test_metadata_filename_constant(self):
        """Test that METADATA_FILENAME constant is correct."""
        assert METADATA_FILENAME == "metadata.json"

    @patch("sglawwatch_to_sqlite.metadata_manager.Storage")
    @patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text")
    def test_database_name_used_consistently(self, mock_read_text, mock_storage_class):
        """Test that DATABASE_NAME is used consistently throughout."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage
        mock_storage.save.return_value = "/tmp/metadata.json"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"databases": {}}, f)
            temp_path = f.name

        mock_storage.get_local_path.return_value = temp_path
        mock_read_text.return_value = '{"title": "Test"}'

        try:
            manager = MetadataManager("./test")
            manager.update_metadata()

            # Verify DATABASE_NAME was used as the key
            assert DATABASE_NAME in manager.metadata["databases"]
            assert manager.metadata["databases"][DATABASE_NAME]["title"] == "Test"

        finally:
            os.unlink(temp_path)