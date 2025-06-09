"""
Integration tests for the assets CLI commands.

These tests verify the end-to-end functionality of the assets commands,
ensuring proper integration between CLI, metadata manager, and storage layers.
"""

import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from sglawwatch_to_sqlite.cli import cli
from sglawwatch_to_sqlite.metadata_manager import METADATA_FILENAME


@pytest.fixture
def runner():
    """Create a Click testing runner."""
    return CliRunner()


@pytest.fixture
def complete_test_environment():
    """Create a complete test environment with all necessary files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create main metadata.json for datasette
        main_metadata = {
            "title": "My Datasette Instance",
            "databases": {
                "existing_db": {
                    "title": "Existing Database",
                    "description": "Should be preserved"
                }
            }
        }
        main_metadata_path = os.path.join(temp_dir, METADATA_FILENAME)
        with open(main_metadata_path, "w") as f:
            json.dump(main_metadata, f, indent=2)

        # Create zeeker assets directory
        assets_dir = os.path.join(temp_dir, "zeeker_assets")
        os.makedirs(assets_dir)

        # Create zeeker metadata.json
        zeeker_metadata = {
            "databases": {
                "sglawwatch": {
                    "title": "Singapore Law Watch Headlines",
                    "description": "Legal news headlines from Singapore Law Watch",
                    "tables": {
                        "headlines": {
                            "title": "Headlines",
                            "facets": ["category", "author"]
                        }
                    }
                }
            },
            "extra_css_urls": ["/static/databases/sglawwatch/custom.css"]
        }
        zeeker_metadata_path = os.path.join(assets_dir, "metadata.json")
        with open(zeeker_metadata_path, "w") as f:
            json.dump(zeeker_metadata, f, indent=2)

        # Create templates
        templates_dir = os.path.join(assets_dir, "templates")
        os.makedirs(templates_dir)
        templates = {
            "database-sglawwatch.html": "<h1>Custom Database Page</h1>",
            "table-sglawwatch-headlines.html": "<h1>Custom Headlines Table</h1>",
            "row-sglawwatch-headlines.html": "<div>Custom Row View</div>",
        }
        for template_name, content in templates.items():
            with open(os.path.join(templates_dir, template_name), "w") as f:
                f.write(content)

        # Create static assets
        static_dir = os.path.join(assets_dir, "static")
        os.makedirs(static_dir)
        static_files = {
            "custom.css": "body { background: #f0f0f0; }",
            "custom.js": "console.log('Singapore Law Watch loaded');",
        }
        for file_name, content in static_files.items():
            with open(os.path.join(static_dir, file_name), "w") as f:
                f.write(content)

        # Create subdirectory in static
        images_dir = os.path.join(static_dir, "images")
        os.makedirs(images_dir)
        with open(os.path.join(images_dir, "logo.svg"), "w") as f:
            f.write('<svg><circle r="10" /></svg>')

        yield {
            "temp_dir": temp_dir,
            "main_metadata_path": main_metadata_path,
            "assets_dir": assets_dir,
            "zeeker_metadata_path": zeeker_metadata_path,
            "templates_dir": templates_dir,
            "static_dir": static_dir,
        }


class TestAssetsWorkflowIntegration:
    """Test complete assets workflow integration."""

    def test_full_assets_workflow_local(self, runner, complete_test_environment):
        """Test complete assets workflow with local storage."""
        env = complete_test_environment

        # Step 1: Validate assets
        result = runner.invoke(
            cli,
            [
                "assets",
                "validate",
                "--assets-dir",
                env["assets_dir"],
            ],
        )
        assert result.exit_code == 0
        assert "All validations passed!" in result.output

        # Step 2: Update metadata from assets
        with patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text") as mock_read_text:
            # Mock the project metadata
            project_metadata = {
                "title": "Singapore Law Watch Headlines",
                "description": "Legal news database",
                "tables": {"headlines": {"title": "Headlines"}}
            }
            mock_read_text.return_value = json.dumps(project_metadata)

            result = runner.invoke(
                cli,
                [
                    "assets",
                    "update-metadata",
                    env["temp_dir"],
                ],
            )
            assert result.exit_code == 0
            assert "updated" in result.output

            # Verify metadata was updated correctly
            with open(env["main_metadata_path"], "r") as f:
                updated_metadata = json.load(f)

            assert "sglawwatch" in updated_metadata["databases"]
            assert "existing_db" in updated_metadata["databases"]  # Preserved
            assert updated_metadata["databases"]["sglawwatch"]["title"] == "Singapore Law Watch Headlines"

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_full_assets_workflow_s3(self, mock_storage_class, runner, complete_test_environment):
        """Test complete assets workflow with S3 storage."""
        env = complete_test_environment

        # Setup S3 storage mock
        mock_storage = MagicMock()
        mock_storage_class.create.return_value = mock_storage

        # Step 1: Validate assets (works the same for S3)
        result = runner.invoke(
            cli,
            [
                "assets",
                "validate",
                "--assets-dir",
                env["assets_dir"],
            ],
        )
        assert result.exit_code == 0

        # Step 2: Upload assets to S3
        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://test-bucket/path/",
                "--assets-dir",
                env["assets_dir"],
            ],
        )
        assert result.exit_code == 0
        assert "Zeeker assets uploaded successfully!" in result.output

        # Verify storage interactions
        mock_storage_class.create.assert_called_with("s3://test-bucket/path/")
        mock_storage.upload_zeeker_assets.assert_called_once_with(
            env["assets_dir"], "sglawwatch"
        )

    def test_assets_validation_catches_errors(self, runner, complete_test_environment):
        """Test that validation catches various error conditions."""
        env = complete_test_environment

        # Create a banned template
        banned_template = os.path.join(env["templates_dir"], "database.html")
        with open(banned_template, "w") as f:
            f.write("<h1>Banned Template</h1>")

        result = runner.invoke(
            cli,
            [
                "assets",
                "validate",
                "--assets-dir",
                env["assets_dir"],
            ],
        )
        assert result.exit_code == 1
        assert "BANNED template name: database.html" in result.output

    def test_metadata_update_preserves_structure(self, runner, complete_test_environment):
        """Test that metadata update preserves existing structure."""
        env = complete_test_environment

        with patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text") as mock_read_text:
            # Mock minimal project metadata
            mock_read_text.return_value = '{"title": "Test Project"}'

            # Read original metadata
            with open(env["main_metadata_path"], "r") as f:
                original_metadata = json.load(f)

            result = runner.invoke(
                cli,
                [
                    "assets",
                    "update-metadata",
                    env["temp_dir"],
                ],
            )
            assert result.exit_code == 0

            # Verify original structure preserved
            with open(env["main_metadata_path"], "r") as f:
                updated_metadata = json.load(f)

            assert updated_metadata["title"] == original_metadata["title"]
            assert "existing_db" in updated_metadata["databases"]
            assert "sglawwatch" in updated_metadata["databases"]

    def test_dry_run_shows_changes_without_applying(self, runner, complete_test_environment):
        """Test that dry run shows changes without applying them."""
        env = complete_test_environment

        with patch("sglawwatch_to_sqlite.metadata_manager.pkg_resources.read_text") as mock_read_text:
            mock_read_text.return_value = '{"title": "Test Project"}'

            # Read original metadata
            with open(env["main_metadata_path"], "r") as f:
                original_metadata = json.load(f)

            # Run with dry-run
            result = runner.invoke(
                cli,
                [
                    "assets",
                    "update-metadata",
                    env["temp_dir"],
                    "--dry-run",
                ],
            )
            assert result.exit_code == 0
            assert "Changes would be made" in result.output

            # Verify no changes were actually made
            with open(env["main_metadata_path"], "r") as f:
                current_metadata = json.load(f)

            assert current_metadata == original_metadata
            assert "sglawwatch" not in current_metadata["databases"]


class TestAssetsErrorHandlingIntegration:
    """Test error handling across the assets workflow."""

    def test_upload_without_validation_fails_on_missing_files(self, runner):
        """Test upload fails gracefully when required files are missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create empty assets directory
            assets_dir = os.path.join(temp_dir, "empty_assets")
            os.makedirs(assets_dir)

            result = runner.invoke(
                cli,
                [
                    "assets",
                    "upload",
                    "s3://test-bucket/path/",
                    "--assets-dir",
                    assets_dir,
                    "--skip-validation",
                ],
            )
            assert result.exit_code == 1
            assert "Required file missing" in result.output

    def test_metadata_update_handles_storage_errors(self, runner):
        """Test metadata update handles storage errors gracefully."""
        with patch("sglawwatch_to_sqlite.cli.MetadataManager") as mock_metadata_manager:
            mock_metadata_manager.side_effect = Exception("Storage unavailable")

            result = runner.invoke(
                cli,
                [
                    "assets",
                    "update-metadata",
                    "s3://unreachable-bucket/",
                ],
            )
            assert result.exit_code == 1
            assert "Error updating metadata" in result.output

    @patch("sglawwatch_to_sqlite.cli.Storage")
    def test_upload_handles_s3_errors(self, mock_storage_class, runner, complete_test_environment):
        """Test upload handles S3 errors gracefully."""
        env = complete_test_environment

        # Setup storage to fail
        mock_storage = MagicMock()
        mock_storage.upload_zeeker_assets.side_effect = Exception("S3 access denied")
        mock_storage_class.create.return_value = mock_storage

        result = runner.invoke(
            cli,
            [
                "assets",
                "upload",
                "s3://test-bucket/path/",
                "--assets-dir",
                env["assets_dir"],
            ],
        )
        assert result.exit_code == 1
        assert "Error uploading Zeeker assets" in result.output


class TestAssetsCommandOptions:
    """Test various command-line options for assets commands."""

    def test_custom_database_name_in_upload(self, runner, complete_test_environment):
        """Test using custom database name in upload."""
        env = complete_test_environment

        with patch("sglawwatch_to_sqlite.cli.Storage") as mock_storage_class:
            mock_storage = MagicMock()
            mock_storage_class.create.return_value = mock_storage

            result = runner.invoke(
                cli,
                [
                    "assets",
                    "upload",
                    "s3://test-bucket/path/",
                    "--assets-dir",
                    env["assets_dir"],
                    "--database-name",
                    "custom_legal_db",
                ],
            )
            assert result.exit_code == 0

            # Verify custom database name was used
            mock_storage.upload_zeeker_assets.assert_called_once_with(
                env["assets_dir"], "custom_legal_db"
            )

    def test_custom_assets_directory(self, runner):
        """Test using custom assets directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create custom assets directory
            custom_assets = os.path.join(temp_dir, "my_custom_assets")
            os.makedirs(custom_assets)

            # Create required metadata.json
            metadata = {"databases": {"sglawwatch": {"title": "Test"}}}
            with open(os.path.join(custom_assets, "metadata.json"), "w") as f:
                json.dump(metadata, f)

            result = runner.invoke(
                cli,
                [
                    "assets",
                    "validate",
                    "--assets-dir",
                    custom_assets,
                ],
            )
            assert result.exit_code == 0
            assert "All validations passed!" in result.output

    def test_upload_with_metadata_update_integration(self, runner, complete_test_environment):
        """Test upload with automatic metadata update."""
        env = complete_test_environment

        with patch("sglawwatch_to_sqlite.cli.Storage") as mock_storage_class:
            with patch("sglawwatch_to_sqlite.cli.MetadataManager") as mock_metadata_manager:
                # Setup mocks
                mock_storage = MagicMock()
                mock_storage_class.create.return_value = mock_storage

                mock_manager = MagicMock()
                mock_manager.update_metadata.return_value = (True, "Metadata updated successfully")
                mock_metadata_manager.return_value = mock_manager

                result = runner.invoke(
                    cli,
                    [
                        "assets",
                        "upload",
                        "s3://test-bucket/path/",
                        "--assets-dir",
                        env["assets_dir"],
                        "--update-metadata",
                    ],
                )
                assert result.exit_code == 0
                assert "Zeeker assets uploaded successfully!" in result.output
                assert "Metadata update: Metadata updated successfully" in result.output

                # Verify both operations were called
                mock_storage.upload_zeeker_assets.assert_called_once()
                mock_metadata_manager.assert_called_once_with("s3://test-bucket/path/")
                mock_manager.update_metadata.assert_called_once()


class TestAssetsCommandHelp:
    """Test that help text is informative and correct."""

    def test_assets_group_help_comprehensive(self, runner):
        """Test that assets group help is comprehensive."""
        result = runner.invoke(cli, ["assets", "--help"])

        assert result.exit_code == 0
        assert "Manage database assets" in result.output
        assert "metadata" in result.output
        assert "templates" in result.output
        assert "CSS" in result.output
        assert "JavaScript" in result.output

    def test_upload_command_help_includes_examples(self, runner):
        """Test that upload command help includes usage examples."""
        result = runner.invoke(cli, ["assets", "upload", "--help"])

        assert result.exit_code == 0
        assert "s3://bucket/path/" in result.output
        assert "DATABASE_NAME" in result.output
        assert "Zeeker" in result.output

    def test_validate_command_help_explains_purpose(self, runner):
        """Test that validate command help explains its purpose."""
        result = runner.invoke(cli, ["assets", "validate", "--help"])

        assert result.exit_code == 0
        assert "structure" in result.output
        assert "content" in result.output
        assert "template" in result.output

    def test_update_metadata_help_explains_options(self, runner):
        """Test that update-metadata help explains options."""
        result = runner.invoke(cli, ["assets", "update-metadata", "--help"])

        assert result.exit_code == 0
        assert "dry-run" in result.output
        assert "zeeker-assets" in result.output
        assert "Datasette" in result.output