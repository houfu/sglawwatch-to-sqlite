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