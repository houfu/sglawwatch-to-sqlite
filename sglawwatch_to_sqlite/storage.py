import os
import tempfile
from urllib.parse import urlparse

import click

from sglawwatch_to_sqlite.tools import verify_boto3

# Fixed database filename
DB_FILENAME = "sglawwatch.db"


class Storage:
    """
    Abstract base class for database storage.
    """

    def get_local_path(self, filename=DB_FILENAME):
        """Get the local path to the file"""
        raise NotImplementedError()

    def save(self, local_path=None, filename=DB_FILENAME):
        """Save the file"""
        raise NotImplementedError()

    @staticmethod
    def create(location):
        """
        Factory method to create the appropriate storage object.

        Args:
            location: Either a local directory path or an S3 URI (s3://bucket/path/)
                      If no location is specified, the current directory is used.
        """
        if not location:
            # Default to current directory
            return LocalStorage(".")

        if location.startswith('s3://'):
            return S3Storage(location)
        else:
            return LocalStorage(location)


class LocalStorage(Storage):
    """
    Local filesystem storage for the database.
    """

    def __init__(self, directory):
        # Ensure the directory doesn't have a filename at the end
        if os.path.isfile(directory) or directory.endswith('.db'):
            directory = os.path.dirname(directory) or "."

        self.directory = directory
        self.path = os.path.join(directory, DB_FILENAME)

    def get_local_path(self, filename=DB_FILENAME):
        # Ensure the directory exists
        if self.directory and not os.path.exists(self.directory):
            os.makedirs(self.directory, exist_ok=True)
        return os.path.join(self.directory, filename)

    def save(self, local_path=None, filename=DB_FILENAME):
        """
        Save a file to the storage location.

        Args:
            local_path: Path to the local file to save.
                       If None, assumes the file is already at self.path.
            filename: Name of the file to save.

        Returns:
            The final path where the file was saved.
        """
        target_path = os.path.join(self.directory, filename)

        # For local storage, nothing needs to be done if the path is the same
        if local_path and local_path != target_path:
            import shutil

            # Make sure the target directory exists
            if not os.path.exists(self.directory):
                os.makedirs(self.directory)

            shutil.copy2(local_path, target_path)
        return target_path


class S3Storage(Storage):
    """
    S3 storage for the database.
    """

    def __init__(self, s3_uri):
        self.s3_uri = s3_uri

        # Parse the S3 URI
        parsed = urlparse(s3_uri)

        # Check if we have a bucket name in the URI
        if parsed.netloc:
            self.bucket = parsed.netloc
        else:
            # Try to get bucket name from environment variable
            self.bucket = os.environ.get('S3_BUCKET_NAME')
            if not self.bucket:
                click.echo(
                    "Error: S3 bucket name must be specified either in the URI or via S3_BUCKET_NAME environment variable",
                    err=True)
                raise click.Abort()

        # Parse the key (path in the bucket)
        self.key = parsed.path.lstrip('/')

        # If the key doesn't end with a filename, append the fixed DB filename
        if not self.key or self.key.endswith('/'):
            self.key = f"{self.key}{DB_FILENAME}"
        elif not os.path.basename(self.key) or not os.path.splitext(self.key)[1]:
            # It doesn't have a file extension, assume it's a directory
            self.key = f"{self.key}/{DB_FILENAME}"

        # Get endpoint URL from environment variable if available
        self.endpoint_url = os.environ.get('S3_ENDPOINT_URL')
        self.region_name = os.environ.get('AWS_DEFAULT_REGION', 'default')

        self._temp_file = None
        self._temp_files = {}

    def _get_s3_client(self):
        """Get an S3 client with proper configuration."""
        import boto3

        # Create boto3 client with custom endpoint if provided
        client_kwargs = {}
        if self.endpoint_url:
            client_kwargs['endpoint_url'] = self.endpoint_url
            client_kwargs['region_name'] = self.region_name

        return boto3.client('s3', **client_kwargs)

    def _get_full_key(self, filename):
        """Get the full S3 key for a filename."""
        if not self.key or self.key.endswith('/'):
            return f"{self.key}{filename}"
        else:
            # If key already has a filename, use the directory
            base_dir = os.path.dirname(self.key)
            if base_dir:
                return f"{base_dir}/{filename}"
            else:
                return filename

    def get_local_path(self, filename=DB_FILENAME):
        verify_boto3()

        # Create a temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
        os.close(temp_fd)
        self._temp_files[filename] = temp_path

        # Download the file from S3 if it exists
        try:
            from botocore.exceptions import ClientError

            s3_client = self._get_s3_client()
            full_key = self._get_full_key(filename)

            try:
                click.echo(f"Downloading {filename} from s3://{self.bucket}/{full_key}")
                s3_client.download_file(self.bucket, full_key, temp_path)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    if filename == DB_FILENAME:
                        click.echo(
                            f"No existing database found at s3://{self.bucket}/{full_key}. A new one will be created.")
                    else:
                        # For non-database files, raise a FileNotFoundError
                        raise FileNotFoundError(f"File {filename} not found at s3://{self.bucket}/{full_key}")
                else:
                    click.echo(f"Error downloading from S3: {e}", err=True)
                    raise click.Abort()
        except Exception as e:
            if isinstance(e, FileNotFoundError):
                raise  # Re-raise FileNotFoundError for non-DB files
            click.echo(f"Error accessing S3: {e}", err=True)
            raise click.Abort()

        return temp_path

    def save(self, local_path=None, filename=DB_FILENAME):
        verify_boto3()

        if not local_path:
            local_path = self._temp_files.get(filename)

        if not local_path or not os.path.exists(local_path):
            click.echo(f"Error: Local file not found: {local_path}", err=True)
            raise click.Abort()

        try:
            s3_client = self._get_s3_client()
            full_key = self._get_full_key(filename)

            click.echo(f"Uploading {filename} to s3://{self.bucket}/{full_key}")
            s3_client.upload_file(local_path, self.bucket, full_key)
            click.echo(f"{filename} successfully uploaded to S3")
            return f"s3://{self.bucket}/{full_key}"
        except Exception as e:
            click.echo(f"Error uploading to S3: {e}", err=True)
            raise click.Abort()
        finally:
            # Clean up the temporary file
            if filename in self._temp_files and os.path.exists(self._temp_files[filename]):
                os.unlink(self._temp_files[filename])
                del self._temp_files[filename]
