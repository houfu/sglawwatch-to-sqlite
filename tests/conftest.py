import asyncio
import os
from unittest.mock import MagicMock, AsyncMock

import feedparser
import pytest
import sqlite_utils


@pytest.fixture
def mock_db():
    """Fixture providing a mock SQLite database."""
    mock = MagicMock(spec=sqlite_utils.Database)

    # Set up mock tables
    headlines_table = MagicMock()
    metadata_table = MagicMock()

    # Configure __getitem__ to return appropriate tables
    mock.__getitem__.side_effect = lambda table_name: {
        'headlines': headlines_table,
        'metadata': metadata_table,
    }.get(table_name, MagicMock())

    return mock


@pytest.fixture
def mock_metadata_table(mock_db):
    """Fixture for the metadata table with controlled behavior."""
    metadata = mock_db['metadata']

    # Mock the get method to return a value or raise NotFoundError
    def get_side_effect(key):
        if key == "headlines_last_updated":
            return {"key": key, "value": "2025-05-01T00:00:00"}
        else:
            from sqlite_utils.db import NotFoundError
            raise NotFoundError(f"No such item: {key}")

    metadata.get.side_effect = get_side_effect
    return metadata


@pytest.fixture
def mock_feed_entries():
    """Fixture providing sample RSS feed entries in XML format."""
    return """
 <rss version="2.0">
<channel>
<title>Singapore Law Watch - SLW Today</title>
<link>http://www.singaporelawwatch.sg</link>
<copyright>Copyright 2018, Singapore Government, Singapore Academy of Law.</copyright>
<generator>Singapore Law Watch</generator>
<language>en-gb</language>
<item>
<title>Law don argues in inmates’ appeal that parts of Misuse of Drugs Act are unconstitutional</title>
<link>https://www.singaporelawwatch.sg/Headlines/Law-don-argues-in-inmates-appeal-that-parts-of-Misuse-of-Drugs-Act-are-unconstitutional</link>
<description><p>Deputy A-G counters that presumption of innocence not provided for in Constitution.</p></description>
<author>Straits Times: Selina Lum</author>
<category>Straits Times</category>
<pubDate>08 May 2025 00:01:00</pubDate>
<eventDate/>
</item>
<item>
<title>Singapore and EU sign digital trade pact, deepening cooperation amid global uncertainties</title>
<link>https://www.singaporelawwatch.sg/Headlines/Singapore-and-EU-sign-digital-trade-pact-deepening-cooperation-amid-global-uncertainties</link>
<description><p>The agreement supplements the EU-Singapore Free Trade Agreement (EUSFTA) that entered into force in 2019.</p></description>
<author>Straits Times: Angela Tan</author>
<category>Straits Times</category>
<pubDate>08 May 2025 00:01:00</pubDate>
<eventDate/>
</item>
<item>
<title>Generative AI a top priority for firms but privacy concerns remain: GIC survey</title>
<link>https://www.singaporelawwatch.sg/Headlines/Generative-AI-a-top-priority-for-firms-but-privacy-concerns-remain-GIC-survey</link>
<description><p>Many exploring its use for software development and IT applications.</p></description>
<author>Straits Times: Timothy Goh</author>
<category>Straits Times</category>
<pubDate>08 May 2025 00:01:00</pubDate>
<eventDate/>
</item>
<item>
<title>ADV: Law & Technology in Singapore book launch - 23 May</title>
<link>https://store.lawnet.com/law-and-technology-in-singapore-navigating-the-future-of-legal-practice-in-a-digital-age.html?utm_source=slw_edm&utm_medium=slwleaderboard&utm_campaign=2025may-poem_lawntech2esem-slw_edm-slwleaderboard-&utm_id=poem_lawntech2esem</link>
<description><p>This <a href="https://store.lawnet.com/seminar-book-law-and-technology-in-singapore-navigating-the-future-of-legal-practice-in-a-digital-age.html?utm_source=slw_edm&amp;utm_medium=slwleaderboard&amp;utm_campaign=2025may-poem_lawntech2esem-slw_edm-slwleaderboard-&amp;utm_id=poem_lawntech2esem" target="_blank"><span style="color:#0033ff;">seminar</span></a> marks the release of the second edition of Law and Technology in Singapore, offering a timely exploration of how emerging technologies are reshaping legal practice and frameworks in Singapore. The authors will provide an overview of how technology intersects with various areas of Singapore law, examine current legal practices, and explore future developments.</p></description>
<author>Academy Publishing</author>
<category>Academy Publishing</category>
<pubDate>08 May 2025 00:01:00</pubDate>
<eventDate/>
</item>
</channel>   
</rss>
    """


@pytest.fixture
def mock_feed(mock_feed_entries):
    """Fixture providing a mock feedparser result."""
    mock = MagicMock(spec=feedparser.FeedParserDict)
    mock.bozo = False
    mock.entries = mock_feed_entries
    mock.feed = {
        'title': 'Singapore Law Watch Headlines',
        'updated': 'Fri, 09 May 2025 12:00:00 GMT'
    }
    return mock


@pytest.fixture
def mock_feed_error():
    """Fixture providing a mock feedparser result with an error."""
    mock = MagicMock(spec=feedparser.FeedParserDict)
    mock.bozo = True
    mock.bozo_exception = "XML parsing error: mismatched tag at line 42"
    mock.entries = []
    mock.feed = {}
    return mock


@pytest.fixture
def mock_jina_response():
    """Fixture providing a mock response from Jina API."""
    return """
    <article>
        <h1>New Court Decision on Property Law</h1>
        <p>In a landmark decision handed down yesterday, the High Court ruled 
        that property owners must adhere to stricter disclosure requirements 
        when selling residential properties.</p>
        <p>The decision in Smith v. Jones (2025) will have far-reaching implications
        for the real estate market in Singapore.</p>
        <p>Legal experts suggest this may lead to significant changes in how 
        property transactions are conducted nationwide.</p>
    </article>
    """


@pytest.fixture
def mock_openai_response():
    """Fixture providing a mock response from OpenAI API."""
    return "The High Court has established stricter disclosure requirements for property sellers in a landmark ruling. Smith v. Jones (2025) mandates comprehensive disclosure of property defects, potentially transforming Singapore's real estate transactions and strengthening buyer protections. Industry experts anticipate significant adjustments to current practices."


@pytest.fixture
def mock_env_vars():
    """Fixture to set and restore environment variables."""
    original_env = os.environ.copy()
    os.environ['JINA_API_TOKEN'] = 'mock-jina-token'
    os.environ['OPENAI_API_KEY'] = 'mock-openai-key'

    yield

    # Reset environment to original state
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_httpx_client():
    """Fixture providing a mock httpx.AsyncClient."""
    mock_client = AsyncMock()

    # Mock response for Jina API
    mock_response = AsyncMock()
    mock_response.text = "<article>Sample article content</article>"
    mock_response.status_code = 200

    # Configure the client to return the mock response
    mock_client.__aenter__.return_value.get.return_value = mock_response

    return mock_client


@pytest.fixture
def mock_openai_client():
    """Fixture providing a mock OpenAI client."""
    mock_client = AsyncMock()

    # Create a mock response object
    mock_response = AsyncMock()
    mock_response.output_text = "This is a concise legal summary."

    # Set up the client to return the mock response
    mock_client.responses.create.return_value = mock_response

    return mock_client


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test case.

    This is needed for pytest-asyncio to work properly.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_boto3_client():
    """Mock boto3 client for S3 testing."""
    mock_client = MagicMock()

    # Configure the download_file method
    mock_client.download_file = MagicMock()

    # Configure the upload_file method
    mock_client.upload_file = MagicMock()

    return mock_client


@pytest.fixture
def mock_boto3():
    """Mock the boto3 module for S3 testing."""
    mock_module = MagicMock()
    mock_module.client.return_value = MagicMock()
    return mock_module


@pytest.fixture
def mock_s3_env():
    """Fixture to set and restore S3-related environment variables."""
    original_env = os.environ.copy()
    os.environ['AWS_ACCESS_KEY_ID'] = 'mock-aws-key'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'mock-aws-secret'
    os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
    os.environ['S3_BUCKET_NAME'] = 'mock-bucket'

    yield

    # Reset environment to original state
    os.environ.clear()
    os.environ.update(original_env)

