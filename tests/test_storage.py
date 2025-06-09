import os
import tempfile
from unittest.mock import patch, MagicMock

import click
import pytest
from botocore.exceptions import ClientError

from sglawwatch_to_sqlite.storage import Storage, LocalStorage, S3Storage, DB_FILENAME


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


def test_storage_factory_local():
    """Test Storage.create factory method with local path."""
    storage = Storage.create("./data")
    assert isinstance(storage, LocalStorage)
    assert storage.directory == "./data"
    assert storage.path.endswith(DB_FILENAME)


def test_storage_factory_s3():
    """Test Storage.create factory method with S3 URI."""
    storage = Storage.create("s3://my-bucket/path/")
    assert isinstance(storage, S3Storage)
    assert storage.bucket == "my-bucket"
    assert storage.key == f"path/{DB_FILENAME}"


def test_local_storage_init():
    """Test LocalStorage initialization."""
    # With directory path
    storage = LocalStorage("./data")
    assert storage.directory == "./data"
    assert storage.path == f"./data/{DB_FILENAME}"

    # With file path
    storage = LocalStorage("./data/mydb.db")
    assert storage.directory == "./data"
    assert storage.path == f"./data/{DB_FILENAME}"

    # With current directory
    storage = LocalStorage(".")
    assert storage.directory == "."
    assert storage.path == f"./{DB_FILENAME}"


def test_local_storage_get_local_path(temp_dir):
    """Test LocalStorage.get_local_path with a temporary directory."""
    sub_dir = os.path.join(temp_dir, "data")
    storage = LocalStorage(sub_dir)

    # Directory shouldn't exist yet
    assert not os.path.exists(sub_dir)

    # get_local_path should create the directory
    path = storage.get_local_path()
    assert os.path.exists(sub_dir)
    assert path == os.path.join(sub_dir, DB_FILENAME)


def test_local_storage_save(temp_dir):
    """Test LocalStorage.save method."""
    # Create a source file
    source_path = os.path.join(temp_dir, "source.db")
    with open(source_path, "w") as f:
        f.write("test data")

    # Setup storage in a subdirectory
    dest_dir = os.path.join(temp_dir, "dest")
    storage = LocalStorage(dest_dir)

    # Save the file
    result = storage.save(source_path)

    # Check the result
    assert result == os.path.join(dest_dir, DB_FILENAME)
    assert os.path.exists(result)

    # Check the content was copied
    with open(result, "r") as f:
        assert f.read() == "test data"


def test_s3_storage_init():
    """Test S3Storage initialization with various URI formats."""
    # With bucket and path
    storage = S3Storage("s3://my-bucket/path/to/data/")
    assert storage.bucket == "my-bucket"
    assert storage.key == f"path/to/data/{DB_FILENAME}"

    # With bucket but no path
    storage = S3Storage("s3://my-bucket")
    assert storage.bucket == "my-bucket"
    assert storage.key == DB_FILENAME

    # With bucket and file
    storage = S3Storage("s3://my-bucket/path/to/data/custom.db")
    assert storage.bucket == "my-bucket"
    assert storage.key == "path/to/data/custom.db"


def test_s3_storage_from_env():
    """Test S3Storage initialization with bucket from environment."""
    # Set environment variable
    with patch.dict(os.environ, {"S3_BUCKET_NAME": "env-bucket"}):
        # Without bucket in URI
        storage = S3Storage("s3:///path/to/data/")
        assert storage.bucket == "env-bucket"
        assert storage.key == f"path/to/data/{DB_FILENAME}"


def test_s3_storage_missing_bucket():
    """Test S3Storage initialization with missing bucket."""
    # Clear environment variable
    with patch.dict(os.environ, {"S3_BUCKET_NAME": ""}):
        # Without bucket in URI
        with pytest.raises(click.exceptions.Abort):
            with patch("click.echo") as mock_echo:
                S3Storage("s3:///path/to/data/")
                # This will be called but we won't get here because of the exception
                mock_echo.assert_called_with(
                    "Error: S3 bucket name must be specified either in the URI or via S3_BUCKET_NAME environment variable",
                    err=True
                )


@patch("boto3.client")
def test_s3_storage_get_local_path_new_file(mock_boto3_client):
    """Test S3Storage.get_local_path when the file doesn't exist in S3."""
    # Mock S3 client
    mock_s3 = MagicMock()
    mock_boto3_client.return_value = mock_s3

    # Setup mock to simulate file not found
    mock_error = ClientError(
        error_response={"Error": {"Code": "404"}},
        operation_name="download_file"
    )
    mock_s3.download_file.side_effect = mock_error

    # Test the method
    storage = S3Storage("s3://test-bucket/path/")
    local_path = storage.get_local_path()

    # Check the result
    assert local_path.endswith(".db")
    assert os.path.exists(local_path)

    # Verify the mock was called correctly
    mock_s3.download_file.assert_called_once_with(
        "test-bucket", f"path/{DB_FILENAME}", local_path
    )


@patch("boto3.client")
def test_s3_storage_get_local_path_existing_file(mock_boto3_client):
    """Test S3Storage.get_local_path when the file exists in S3."""
    # Mock S3 client
    mock_s3 = MagicMock()
    mock_boto3_client.return_value = mock_s3

    # Setup mock to write a test file when download_file is called
    def side_effect(bucket, key, filename):
        with open(filename, "w") as f:
            f.write("test data from s3")

    mock_s3.download_file.side_effect = side_effect

    # Test the method
    storage = S3Storage("s3://test-bucket/path/")
    local_path = storage.get_local_path()

    # Check the result
    assert local_path.endswith(".db")
    assert os.path.exists(local_path)

    # Check the content
    with open(local_path, "r") as f:
        assert f.read() == "test data from s3"

    # Verify the mock was called correctly
    mock_s3.download_file.assert_called_once_with(
        "test-bucket", f"path/{DB_FILENAME}", local_path
    )


@patch("boto3.client")
def test_s3_storage_save(mock_boto3_client):
    """Test S3Storage.save method."""
    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test data to upload")
        tmp_path = tmp.name

    try:
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # Test the method
        storage = S3Storage("s3://test-bucket/path/")
        result = storage.save(tmp_path)

        # Check the result
        assert result == f"s3://test-bucket/path/{DB_FILENAME}"

        # Verify the mock was called correctly
        mock_s3.upload_file.assert_called_once_with(
            tmp_path, "test-bucket", f"path/{DB_FILENAME}"
        )
    finally:
        # Clean up
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@pytest.fixture
def mock_zeeker_assets_dir():
    """Create a mock zeeker assets directory structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        assets_dir = os.path.join(temp_dir, "zeeker_assets")
        os.makedirs(assets_dir)

        # Create metadata.json
        metadata_path = os.path.join(assets_dir, "metadata.json")
        with open(metadata_path, "w") as f:
            f.write('{"databases": {"sglawwatch": {"title": "Test"}}}')

        # Create templates directory with files
        templates_dir = os.path.join(assets_dir, "templates")
        os.makedirs(templates_dir)
        with open(os.path.join(templates_dir, "database-sglawwatch.html"), "w") as f:
            f.write("<h1>Custom Database Template</h1>")
        with open(os.path.join(templates_dir, "table-sglawwatch-headlines.html"), "w") as f:
            f.write("<h1>Custom Table Template</h1>")

        # Create static directory with files
        static_dir = os.path.join(assets_dir, "static")
        os.makedirs(static_dir)
        with open(os.path.join(static_dir, "custom.css"), "w") as f:
            f.write("body { color: blue; }")
        with open(os.path.join(static_dir, "custom.js"), "w") as f:
            f.write("console.log('Custom JS');")

        # Create subdirectory in static
        static_subdir = os.path.join(static_dir, "images")
        os.makedirs(static_subdir)
        with open(os.path.join(static_subdir, "logo.svg"), "w") as f:
            f.write("<svg>Logo</svg>")

        yield assets_dir


class TestZeekerAssetsUpload:
    """Tests for upload_zeeker_assets functionality."""

    def test_upload_zeeker_assets_local_storage_error(self, mock_zeeker_assets_dir):
        """Test that upload_zeeker_assets raises error for LocalStorage."""
        storage = LocalStorage("./data")

        with patch("click.echo") as mock_echo:
            storage.upload_zeeker_assets(mock_zeeker_assets_dir, "test_db")
            mock_echo.assert_called_with(
                "Zeeker assets can only be uploaded to S3 storage", err=True
            )

    @patch("boto3.client")
    def test_upload_zeeker_assets_s3_success(self, mock_boto3_client, mock_zeeker_assets_dir):
        """Test successful upload of zeeker assets to S3."""
        # Mock S3 client
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        # Create S3Storage instance
        storage = S3Storage("s3://test_bucket/path/")

        with patch("click.echo") as mock_echo:
            storage.upload_zeeker_assets(mock_zeeker_assets_dir, "test_db")

            # Verify all expected files were uploaded
            expected_calls = [
                # metadata.json
                ("metadata.json", "test-bucket", "assets/databases/test_db/metadata.json"),
                # templates
                ("templates/database-sglawwatch.html", "test-bucket",
                 "assets/databases/test_db/templates/database-sglawwatch.html"),
                ("templates/table-sglawwatch-headlines.html", "test-bucket",
                 "assets/databases/test_db/templates/table-sglawwatch-headlines.html"),
                # static files
                ("static/custom.css", "test-bucket", "assets/databases/test_db/static/custom.css"),
                ("static/custom.js", "test-bucket", "assets/databases/test_db/static/custom.js"),
                ("static/images/logo.svg", "test-bucket", "assets/databases/test_db/static/images/logo.svg"),
            ]

            # Verify upload_file was called for each expected file
            assert mock_s3.upload_file.call_count == 6

            # Check that the right files were uploaded with correct paths
            upload_calls = mock_s3.upload_file.call_args_list
            for call in upload_calls:
                local_path, bucket, s3_key = call[0]
                assert bucket == "test_bucket"
                assert s3_key.startswith("assets/databases/test_db/")
                assert os.path.exists(local_path)

            # Verify echo calls for each upload
            echo_calls = mock_echo.call_args_list
            assert len(echo_calls) >= 6  # At least one call per file

    @patch("boto3.client")
    def test_upload_zeeker_assets_s3_upload_error(self, mock_boto3_client, mock_zeeker_assets_dir):
        """Test handling of S3 upload errors."""
        # Mock S3 client to raise exception
        mock_s3 = MagicMock()
        mock_s3.upload_file.side_effect = Exception("S3 upload failed")
        mock_boto3_client.return_value = mock_s3

        # Create S3Storage instance
        storage = S3Storage("s3://test-bucket/path/")

        with patch("click.echo") as mock_echo:
            storage.upload_zeeker_assets(mock_zeeker_assets_dir, "test_db")

            # Verify error was logged
            error_calls = [call for call in mock_echo.call_args_list if call[1].get('err')]
            assert len(error_calls) > 0
            assert any("Error uploading" in str(call) for call in error_calls)

    def test_upload_zeeker_assets_missing_directory(self):
        """Test upload_zeeker_assets with missing directory."""
        storage = S3Storage("s3://test-bucket/path/")

        # This should raise an exception when trying to walk a non-existent directory
        with pytest.raises(FileNotFoundError):
            storage.upload_zeeker_assets("/nonexistent/path", "test_db")

    @patch("boto3.client")
    def test_upload_zeeker_assets_empty_directory(self, mock_boto3_client):
        """Test upload_zeeker_assets with empty directory."""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        with tempfile.TemporaryDirectory() as empty_dir:
            storage = S3Storage("s3://test-bucket/path/")

            with patch("click.echo"):
                storage.upload_zeeker_assets(empty_dir, "test_db")

                # Should not have uploaded any files
                mock_s3.upload_file.assert_not_called()

    @patch("boto3.client")
    def test_upload_zeeker_assets_custom_database_name(self, mock_boto3_client, mock_zeeker_assets_dir):
        """Test upload_zeeker_assets with custom database name."""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        storage = S3Storage("s3://test-bucket/path/")

        with patch("click.echo"):
            storage.upload_zeeker_assets(mock_zeeker_assets_dir, "my_custom_db")

            # Verify all uploaded files use the custom database name in the path
            upload_calls = mock_s3.upload_file.call_args_list
            for call in upload_calls:
                _, bucket, s3_key = call[0]
                assert s3_key.startswith("assets/databases/my_custom_db/")

    @patch("boto3.client")
    def test_upload_zeeker_assets_preserves_directory_structure(self, mock_boto3_client, mock_zeeker_assets_dir):
        """Test that directory structure is preserved in S3 keys."""
        mock_s3 = MagicMock()
        mock_boto3_client.return_value = mock_s3

        storage = S3Storage("s3://test-bucket/path/")

        with patch("click.echo"):
            storage.upload_zeeker_assets(mock_zeeker_assets_dir, "test_db")

            # Check that subdirectory structure is preserved
            upload_calls = mock_s3.upload_file.call_args_list
            s3_keys = [call[0][2] for call in upload_calls]

            # Verify specific nested file path
            assert "assets/databases/test_db/static/images/logo.svg" in s3_keys
            assert "assets/databases/test_db/templates/database-sglawwatch.html" in s3_keys

    def test_upload_zeeker_assets_verify_boto3_called(self, mock_zeeker_assets_dir):
        """Test that verify_boto3 is called during upload."""
        storage = S3Storage("s3://test-bucket/path/")

        with patch("sglawwatch_to_sqlite.storage.verify_boto3") as mock_verify:
            with patch("boto3.client"):
                with patch("click.echo"):
                    storage.upload_zeeker_assets(mock_zeeker_assets_dir, "test_db")

                    mock_verify.assert_called_once()


class TestStorageFactoryWithZeekerAssets:
    """Test the Storage factory method works with zeeker assets functionality."""

    def test_create_s3_storage_supports_zeeker_upload(self, mock_zeeker_assets_dir):
        """Test that S3Storage created by factory supports zeeker assets."""
        storage = Storage.create("s3://test-bucket/path/")

        assert isinstance(storage, S3Storage)
        assert hasattr(storage, "upload_zeeker_assets")

        # Verify it's callable (even if we don't actually call it)
        assert callable(storage.upload_zeeker_assets)

    def test_create_local_storage_zeeker_upload_error(self, mock_zeeker_assets_dir):
        """Test that LocalStorage created by factory shows error for zeeker upload."""
        storage = Storage.create("./local/path")

        assert isinstance(storage, LocalStorage)

        with patch("click.echo") as mock_echo:
            storage.upload_zeeker_assets(mock_zeeker_assets_dir, "test_db")
            mock_echo.assert_called_with(
                "Zeeker assets can only be uploaded to S3 storage", err=True
            )