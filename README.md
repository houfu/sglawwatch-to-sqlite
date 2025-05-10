# sglawwatch-to-sqlite

[![PyPI](https://img.shields.io/pypi/v/sglawwatch-to-sqlite.svg)](https://pypi.org/project/sglawwatch-to-sqlite/)
[![Changelog](https://img.shields.io/github/v/release/houfu/sglawwatch-to-sqlite?include_prereleases&label=changelog)](https://github.com/houfu/sglawwatch-to-sqlite/releases)
[![Tests](https://github.com/houfu/sglawwatch-to-sqlite/actions/workflows/test.yml/badge.svg)](https://github.com/houfu/sglawwatch-to-sqlite/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/houfu/sglawwatch-to-sqlite/blob/master/LICENSE)

A tool to track Singapore's legal developments by importing Singapore Law Watch's RSS feed into a searchable SQLite database.

## Features

- Fetch and parse legal headlines from Singapore Law Watch's RSS feed
- Store headlines with metadata, content, and AI-generated summaries in SQLite
- Full-text search capabilities for legal research
- Support for both local and S3 storage
- Automatic handling of duplicate entries
- Skip advertisements in the feed
- Command-line interface for easy integration into workflows

## Installation

Install this tool using `pip`:
```bash
pip install sglawwatch-to-sqlite
```

## Usage

### Basic Usage

Fetch recent headlines and store them in a local SQLite database:

```bash
sglawwatch-to-sqlite fetch headlines
```

This will create a `sglawwatch.db` file in the current directory.

### Specifying Storage Location

You can specify a different directory for the database:

```bash
sglawwatch-to-sqlite fetch headlines ./data
```

### Using S3 Storage

Store the database in an S3 bucket:

```bash
sglawwatch-to-sqlite fetch headlines s3://my-bucket/path/
```

Or use the `S3_BUCKET_NAME` environment variable:

```bash
export S3_BUCKET_NAME=my-bucket
sglawwatch-to-sqlite fetch headlines s3:///path/
```

### Fetch All Entries

To fetch all entries regardless of what was previously fetched:

```bash
sglawwatch-to-sqlite fetch headlines --all
```

### Fetch All Available Feeds

To fetch all available feeds (currently only headlines):

```bash
sglawwatch-to-sqlite fetch all
```

To reset and fetch all entries from scratch:

```bash
sglawwatch-to-sqlite fetch all --reset
```

### Custom Feed URL

You can specify a custom feed URL:

```bash
sglawwatch-to-sqlite fetch headlines --url https://example.com/feed.xml
```

### Help

For help on available commands:

```bash
sglawwatch-to-sqlite --help
```

For help on specific commands:

```bash
sglawwatch-to-sqlite fetch headlines --help
```

## Environment Variables

- `JINA_API_TOKEN`: API token for Jina AI (used to extract article content)
- `OPENAI_API_KEY`: API key for OpenAI (used to generate summaries)
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`: AWS credentials for S3 storage
- `S3_BUCKET_NAME`: Default S3 bucket name (optional, can be specified in URI)

## Database Schema

The tool creates the following tables:

- `headlines`: Stores article headlines with metadata, content, and summaries
- `metadata`: Stores the last updated timestamp
- `schema_versions`: Tracks database schema versions

The headlines table includes full-text search capabilities on title and summary fields.

## Development

To contribute to this tool, first checkout the code. Then create a new virtual environment:

```bash
cd sglawwatch-to-sqlite
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install the dependencies and test dependencies:

```bash
pip install -e '.[test]'
```

To run the tests:

```bash
python -m pytest
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](https://github.com/houfu/sglawwatch-to-sqlite/blob/master/LICENSE) file for details.