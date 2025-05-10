import os
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from sglawwatch_to_sqlite.cli import cli
from sglawwatch_to_sqlite.storage import DB_FILENAME


def test_version():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert result.output.startswith("cli, version ")


@patch("sglawwatch_to_sqlite.cli.DatabaseManager")
@patch("sglawwatch_to_sqlite.cli.asyncio.run")
def test_headlines_command_local(mock_run, mock_db_manager_class):
    """Test headlines command with local storage."""
    # Setup mocks
    mock_db_manager = MagicMock()
    mock_db_manager.save.return_value = "./data/sglawwatch.db"
    mock_db_manager_class.return_value = mock_db_manager

    # Run command
    runner = CliRunner()
    result = runner.invoke(cli, ["fetch", "headlines", "./data"])

    # Check result
    assert result.exit_code == 0

    # Verify mocks were called correctly
    mock_db_manager_class.assert_called_once_with("./data")
    mock_run.assert_called_once()
    mock_db_manager.save.assert_called_once()

    # Check output
    assert "Database saved to" in result.output


@patch("sglawwatch_to_sqlite.cli.DatabaseManager")
@patch("sglawwatch_to_sqlite.cli.asyncio.run")
def test_headlines_command_s3(mock_run, mock_db_manager_class):
    """Test headlines command with S3 storage."""
    # Setup mocks
    mock_db_manager = MagicMock()
    mock_db_manager.save.return_value = "s3://test-bucket/path/sglawwatch.db"
    mock_db_manager_class.return_value = mock_db_manager

    # Run command
    runner = CliRunner()
    result = runner.invoke(cli, ["fetch", "headlines", "s3://test-bucket/path/"])

    # Check result
    assert result.exit_code == 0

    # Verify mocks were called correctly
    mock_db_manager_class.assert_called_once_with("s3://test-bucket/path/")
    mock_run.assert_called_once()
    mock_db_manager.save.assert_called_once()

    # Check output
    assert "Database saved to s3://test-bucket/path/sglawwatch.db" in result.output


@patch("sglawwatch_to_sqlite.cli.DatabaseManager")
@patch("sglawwatch_to_sqlite.cli.asyncio.run")
def test_fetch_all_command(mock_run, mock_db_manager_class):
    """Test fetch all command."""
    # Setup mocks
    mock_db_manager = MagicMock()
    mock_db_manager.save.return_value = "./data/sglawwatch.db"
    mock_db_manager_class.return_value = mock_db_manager

    # Run command
    runner = CliRunner()
    result = runner.invoke(cli, ["fetch", "all", "./data", "--reset"])

    # Check result
    assert result.exit_code == 0

    # Verify mocks were called correctly
    mock_db_manager_class.assert_called_once_with("./data")
    mock_run.assert_called_once()

    # Check output
    assert "All feeds have been processed" in result.output


def test_headlines_command_integration():
    """Integration test for headlines command with actual filesystem."""
    runner = CliRunner()
    with runner.isolated_filesystem() as temp_dir:
        # Create a directory for the database
        data_dir = os.path.join(temp_dir, "data")
        os.makedirs(data_dir)

        # Mock the fetch_headlines function to avoid actual network calls
        with patch("sglawwatch_to_sqlite.resources.headlines.fetch_headlines") as mock_fetch:
            # Run the command
            result = runner.invoke(cli, ["fetch", "headlines", data_dir])

            # Check the result
            assert result.exit_code == 0

            # Verify the database file was created
            assert os.path.exists(os.path.join(data_dir, DB_FILENAME))

            # Verify fetch_headlines was called
            mock_fetch.assert_called_once()