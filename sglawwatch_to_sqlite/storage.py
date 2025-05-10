import os
import tempfile
from urllib.parse import urlparse

import click

# Fixed database filename
DB_FILENAME = "sglawwatch.db"


class Storage:
    """
    Abstract base class for database storage.
    """

    def get_local_path(self):
        """Get the local path to the database"""
        raise NotImplementedError()

    def save(self, local_path=None):
        """Save the database"""
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

    def get_local_path(self):
        # Ensure the directory exists
        if self.directory and not os.path.exists(self.directory):
            os.makedirs(self.directory)
        return self.path

    def save(self, local_path=None):
        """
        Save a database file to the storage location.

        Args:
            local_path: Path to the local database file to save.
                       If None, assumes the database is already at self.path.

        Returns:
            The final path where the database was saved.
        """
        # For local storage, nothing needs to be done if the path is the same
        if local_path and local_path != self.path:
            import shutil

            # Make sure the target directory exists
            if not os.path.exists(self.directory):
                os.makedirs(self.directory)

            shutil.copy2(local_path, self.path)
        return self.path


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

        self._temp_file = None

    def _verify_boto3(self):
        """Import boto3 and check if it's available."""
        try:
            import boto3  # noqa: F401
            return True
        except ImportError:
            click.echo("boto3 is required for S3 storage. Install it with 'uv install boto3'.", err=True)
            raise click.Abort()

    def get_local_path(self):
        self._verify_boto3()

        # Create a temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.db')
        os.close(temp_fd)
        self._temp_file = temp_path

        # Download the file from S3 if it exists
        try:
            import boto3
            from botocore.exceptions import ClientError

            s3_client = boto3.client('s3')
            try:
                click.echo(f"Downloading database from s3://{self.bucket}/{self.key}")
                s3_client.download_file(self.bucket, self.key, temp_path)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    click.echo(
                        f"No existing database found at s3://{self.bucket}/{self.key}. A new one will be created.")
                else:
                    click.echo(f"Error downloading from S3: {e}", err=True)
                    raise click.Abort()
        except Exception as e:
            click.echo(f"Error accessing S3: {e}", err=True)
            raise click.Abort()

        return temp_path

    def save(self, local_path=None):
        self._verify_boto3()

        if not local_path:
            local_path = self._temp_file

        if not local_path or not os.path.exists(local_path):
            click.echo(f"Error: Local database file not found: {local_path}", err=True)
            raise click.Abort()

        try:
            import boto3

            s3_client = boto3.client('s3')
            click.echo(f"Uploading database to s3://{self.bucket}/{self.key}")
            s3_client.upload_file(local_path, self.bucket, self.key)
            click.echo("Database successfully uploaded to S3")
            return f"s3://{self.bucket}/{self.key}"
        except Exception as e:
            click.echo(f"Error uploading to S3: {e}", err=True)
            raise click.Abort()
        finally:
            # Clean up the temporary file
            if self._temp_file and os.path.exists(self._temp_file):
                os.unlink(self._temp_file)