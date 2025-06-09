import json
import os
import tempfile
from unittest.mock import patch, MagicMock, mock_open

import pytest
from click.testing import CliRunner

from sglawwatch_to_sqlite.cli import cli


@pytest.fixture
def runner():
    """Create a Click testing runner."""
    return CliRunner()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


@pytest.fixture
def sample_metadata():
    """Sample metadata.json content."""
    return {
        "title": "Test Datasette",
        "databases": {
            "other_db": {"title": "Other Database"}
        }
    }


@pytest.fixture
def sample_zeeker_assets_dir(temp_dir):
    """Create a sample zeeker assets directory."""
    assets_dir = os.path.join(temp_dir, "zeeker_assets")
    os.makedirs(assets_dir)

    # Create metadata.json
    metadata = {
        "databases": {
            "sglawwatch": {
                "title": "Singapore Law Watch",
                "description": "Legal headlines database"
            }
        },
        "extra_css_urls": ["/static/databases/sglawwatch/custom.css"]
    }
    with open(os.path.join(assets_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f)

    # Create templates directory
    templates_dir = os.path.join(assets_dir, "templates")
    os.makedirs(templates_dir)
    with open(os.path.join(templates_dir, "database-sglawwatch.html"), "w") as f:
        f.write("<h1>Custom Template</h1>")

    # Create static directory
    static_dir = os.path.join(assets_dir, "static")
    os.makedirs(static_dir)
    with open(os.path.join(static_dir, "custom.css"), "w") as f:
        f.write("body { color: blue; }")

    return assets_dir


class TestAssetsUpdateMetadata:
    """Tests for the assets update-metadata command."""

    @patch("sglawwatch_to_sqlite.cli.MetadataManager")
    def test_update_metadata_success(self, mock_metadata_manager, runner):
        """Test successful metadata update."""
        # Setup mock
        mock_manager = MagicMock()
        mock_manager.update_metadata.return_value = (
            True,
            "Metadata updated successfully"
        )
        mock_metadata_manager.return_value = mock_manager

        # Run command
        result = runner.invoke(cli, ["assets", "update-metadata", "./data"])

        # Assert
        assert result.exit_code == 0
        assert "Metadata updated successfully" in result.output
        mock_metadata_manager.assert_called_once_with("./data")
        mock_manager.update_metadata.assert_called_once_with(False)

    @patch("sglawwatch_to_sqlite.cli.MetadataManager")
    def test_update_metadata_dry_run(self, mock_metadata_manager, runner):
        """Test metadata update with dry run."""
        # Setup mock
        mock_manager = MagicMock()
        mock_manager.update_metadata.return_value = (
            True,
            "Changes would be made (dry run)"
        )
        mock_metadata_manager.return_value = mock_manager

        # Run command with dry run
        result = runner.invoke(cli, ["assets", "update-metadata", "--dry-run"])

        # Assert
        assert result.exit_code == 0
        assert "Changes would be made" in result.output
        mock_manager.update_metadata.assert_called_once_with(True)

    @patch("sglawwatch_to_sqlite.cli.MetadataManager")
    def test_update_metadata_s3_location(self, mock_metadata_manager, runner):
        """Test metadata update with S3 location."""
        # Setup mock
        mock_manager = MagicMock()
        mock_manager.update_metadata.return_value = (
            True,
            "Metadata updated and saved to s3://bucket/path/metadata.json"
        )
        mock_metadata_manager.return_value = mock_manager

        # Run command
        result = runner.invoke(
            cli,
            ["assets", "update-metadata", "s3://test-bucket/path/"]
        )

        # Assert
        assert result.exit_code == 0
        mock_metadata_manager.assert_called_once_with("s3://test-bucket/path/")

    @patch("sglawwatch_to_sqlite.cli.MetadataManager")
    def test_update_metadata_error(self, mock_metadata_manager, runner):
        """Test metadata update with error."""
        # Setup mock to raise exception
        mock_metadata_manager.side_effect = Exception("Test error")

        # Run command
        result = runner.invoke(cli, ["assets", "update-metadata"])

        # Assert
        assert result.exit_code == 1
        assert "Error updating metadata: Test error" in result.output

    def test_update_metadata_from_zeeker_assets_missing(self, runner, temp_dir):
        """Test update metadata from missing zeeker assets."""
        result = runner.invoke(
            cli,
            [
                "assets",
                "update-metadata",
                "--from-zeeker-assets",
                "--assets-dir",
                "nonexistent"
            ]
        )

        assert result.exit_code == 1
        assert "No metadata.json found in nonexistent" in result.output

    def test_update_metadata_from_zeeker_assets_invalid_structure(
            self, runner, temp_dir
    ):
        """Test update metadata from zeeker assets with invalid structure."""
        # Create assets directory with invalid metadata
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        invalid_metadata = {"title": "No databases section"}
        with open(os.path.join(assets_dir, "metadata.json"), "w") as f:
            json.dump(invalid_metadata, f)

        result = runner.invoke(
            cli,
            [
                "assets",
                "update-metadata",
                "--from-zeeker-assets",
                "--assets-dir",
                assets_dir,
            ],
        )

        assert result.exit_code == 1
        assert "missing sglawwatch database section" in result.output


class TestAssetsValidate:
    """Tests for the assets validate command."""

    def test_validate_missing_directory(self, runner):
        """Test validate with missing assets directory."""
        result = runner.invoke(
            cli,
            ["assets", "validate", "--assets-dir", "nonexistent"]
        )

        assert result.exit_code == 1
        assert "Assets directory not found: nonexistent" in result.output

    def test_validate_success(self, runner, sample_zeeker_assets_dir):
        """Test successful validation."""
        result = runner.invoke(
            cli,
            ["assets", "validate", "--assets-dir", sample_zeeker_assets_dir]
        )

        assert result.exit_code == 0
        assert "✓ metadata.json is valid JSON" in result.output
        assert "✓ Template: database-sglawwatch.html" in result.output
        assert "✓ Static asset: custom.css" in result.output
        assert "All validations passed!" in result.output

    def test_validate_missing_metadata(self, runner, temp_dir):
        """Test validation with missing metadata.json."""
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        result = runner.invoke(
            cli,
            ["assets", "validate", "--assets-dir", assets_dir]
        )

        assert result.exit_code == 1
        assert "Missing required file: metadata.json" in result.output

    def test_validate_invalid_json(self, runner, temp_dir):
        """Test validation with invalid JSON in metadata.json."""
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        # Create invalid JSON file
        with open(os.path.join(assets_dir, "metadata.json"), "w") as f:
            f.write("{invalid json")

        result = runner.invoke(
            cli,
            ["assets", "validate", "--assets-dir", assets_dir]
        )

        assert result.exit_code == 1
        assert "Invalid JSON in metadata.json" in result.output

    def test_validate_banned_template_names(self, runner, temp_dir):
        """Test validation catches banned template names."""
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        # Create valid metadata.json
        metadata = {"databases": {}}
        with open(os.path.join(assets_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f)

        # Create templates directory with banned name
        templates_dir = os.path.join(assets_dir, "templates")
        os.makedirs(templates_dir)
        with open(os.path.join(templates_dir, "database.html"), "w") as f:
            f.write("<h1>Banned Template</h1>")

        result = runner.invoke(
            cli,
            ["assets", "validate", "--assets-dir", assets_dir]
        )

        assert result.exit_code == 1
        assert "BANNED template name: database.html" in result.output

    def test_validate_css_url_warnings(self, runner, temp_dir):
        """Test validation shows warnings for non-standard CSS URLs."""
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        # Create metadata with non-standard CSS URL
        metadata = {
            "databases": {},
            "extra_css_urls": ["/some/other/path/style.css"]
        }
        with open(os.path.join(assets_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f)

        result = runner.invoke(
            cli,
            ["assets", "validate", "--assets-dir", assets_dir]
        )

        assert result.exit_code == 0
        assert "doesn't follow Zeeker pattern" in result.output
        assert "warning(s) to review" in result.output


class TestAssetsUpload:
    """Tests for the assets upload command."""

    def test_upload_invalid_s3_location(self, runner):
        """Test upload with invalid S3 location."""
        result = runner.invoke(
            cli,
            ["assets", "upload", "invalid://location"]
        )

        assert result.exit_code == 1
        assert "must be an S3 URI" in result.output

    def test_upload_missing_assets_directory(self, runner):
        """Test upload with missing assets directory."""
        result = runner.invoke(
            cli,
            ["assets", "upload", "s3://bucket/path/", "--assets-dir", "nonexistent"]
        )

        assert result.exit_code == 1
        assert "Assets directory not found: nonexistent" in result.output

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_upload_missing_required_files(self, mock_storage, runner, temp_dir):
        """Test upload with missing required files."""
        # Create empty assets directory
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://bucket/path/",
                "--assets-dir",
                assets_dir,
                "--skip-validation",
            ],
        )

        assert result.exit_code == 1
        assert "Required file missing" in result.output

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_upload_success(self, mock_storage, runner, sample_zeeker_assets_dir):
        """Test successful upload."""
        # Setup mock storage
        mock_storage_instance = MagicMock()
        mock_storage.create.return_value = mock_storage_instance

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://bucket/path/",
                "--assets-dir",
                sample_zeeker_assets_dir,
            ],
        )

        assert result.exit_code == 0
        assert "Zeeker assets uploaded successfully!" in result.output
        assert "Zeeker integration complete!" in result.output

        # Verify storage methods were called
        mock_storage.create.assert_called_once_with("s3://bucket/path/")
        mock_storage_instance.upload_zeeker_assets.assert_called_once_with(
            sample_zeeker_assets_dir, "sglawwatch"
        )

    @patch("sglawwatch_to_sqlite.cli.Storage")
    @patch("sglawwatch_to_sqlite.cli.MetadataManager")
    def test_upload_with_metadata_update(
            self, mock_metadata_manager, mock_storage, runner, sample_zeeker_assets_dir
    ):
        """Test upload with metadata update."""
        # Setup mocks
        mock_storage_instance = MagicMock()
        mock_storage.create.return_value = mock_storage_instance

        mock_manager = MagicMock()
        mock_manager.update_metadata.return_value = (
            True,
            "Metadata updated"
        )
        mock_metadata_manager.return_value = mock_manager

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://bucket/path/",
                "--assets-dir",
                sample_zeeker_assets_dir,
                "--update-metadata",
            ],
        )

        assert result.exit_code == 0
        assert "Zeeker assets uploaded successfully!" in result.output
        assert "Metadata update: Metadata updated" in result.output

        # Verify metadata manager was called
        mock_metadata_manager.assert_called_once_with("s3://bucket/path/")
        mock_manager.update_metadata.assert_called_once()

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_upload_storage_error(self, mock_storage, runner, sample_zeeker_assets_dir):
        """Test upload with storage error."""
        # Setup mock to raise exception
        mock_storage_instance = MagicMock()
        mock_storage_instance.upload_zeeker_assets.side_effect = Exception(
            "S3 upload failed"
        )
        mock_storage.create.return_value = mock_storage_instance

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://bucket/path/",
                "--assets-dir",
                sample_zeeker_assets_dir,
            ],
        )

        assert result.exit_code == 1
        assert "Error uploading Zeeker assets: S3 upload failed" in result.output

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_upload_custom_database_name(
            self, mock_storage, runner, sample_zeeker_assets_dir
    ):
        """Test upload with custom database name."""
        # Setup mock storage
        mock_storage_instance = MagicMock()
        mock_storage.create.return_value = mock_storage_instance

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://bucket/path/",
                "--assets-dir",
                sample_zeeker_assets_dir,
                "--database-name",
                "custom_db",
            ],
        )

        assert result.exit_code == 0

        # Verify custom database name was used
        mock_storage_instance.upload_zeeker_assets.assert_called_once_with(
            sample_zeeker_assets_dir, "custom_db"
        )

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_upload_validation_failure(
            self, mock_storage, runner, temp_dir
    ):
        """Test upload when validation fails."""
        # Create assets directory with invalid content
        assets_dir = os.path.join(temp_dir, "assets")
        os.makedirs(assets_dir)

        # Create invalid JSON file
        with open(os.path.join(assets_dir, "metadata.json"), "w") as f:
            f.write("{invalid json")

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://bucket/path/",
                "--assets-dir",
                assets_dir,
            ],
        )

        assert result.exit_code == 1
        assert "Validation failed" in result.output

        # Verify storage was never called due to validation failure
        mock_storage.create.assert_not_called()


class TestAssetsIntegration:
    """Integration tests for assets commands."""

    def test_assets_help(self, runner):
        """Test assets group help."""
        result = runner.invoke(cli, ["assets", "--help"])

        assert result.exit_code == 0
        assert "Manage database assets" in result.output
        assert "update-metadata" in result.output
        assert "validate" in result.output
        assert "upload" in result.output

    def test_update_metadata_help(self, runner):
        """Test update-metadata command help."""
        result = runner.invoke(cli, ["assets", "update-metadata", "--help"])

        assert result.exit_code == 0
        assert "Update Datasette metadata.json" in result.output
        assert "--dry-run" in result.output
        assert "--from-zeeker-assets" in result.output

    def test_validate_help(self, runner):
        """Test validate command help."""
        result = runner.invoke(cli, ["assets", "validate", "--help"])

        assert result.exit_code == 0
        assert "Validate Zeeker assets directory" in result.output
        assert "--assets-dir" in result.output

    def test_upload_help(self, runner):
        """Test upload command help."""
        result = runner.invoke(cli, ["assets", "upload", "--help"])

        assert result.exit_code == 0
        assert "Upload Zeeker customization assets to S3" in result.output
        assert "--database-name" in result.output
        assert "--update-metadata" in result.output