import datetime
import hashlib
from unittest.mock import patch

import pytest

from sglawwatch_to_sqlite.tools import get_jina_reader_content, get_summary, get_hash_id


@pytest.mark.asyncio
async def test_get_jina_reader_content(mock_httpx_client, mock_env_vars):
    with patch('httpx.AsyncClient', return_value=mock_httpx_client):
        # Test
        content = await get_jina_reader_content("https://example.com/article")

        # Verify
        assert content == "<article>Sample article content</article>"
        # Verify correct URL and headers were used
        mock_httpx_client.__aenter__.return_value.get.assert_called_once()


@pytest.mark.asyncio
async def test_get_summary(mock_openai_client):
    with patch.dict('os.environ', {'OPENAI_API_KEY': 'fake-api-key'}):
        with patch('openai.AsyncOpenAI', return_value=mock_openai_client):
            # Test
            summary = await get_summary("This is a long article text that needs summarizing.")

            # Verify
            assert summary == "This is a concise legal summary."
            # Verify OpenAI was called with correct parameters
            mock_openai_client.responses.create.assert_called_once()


class TestGetHashId:
    def test_basic_functionality(self):
        """Test the function with basic string inputs."""
        result = get_hash_id(["2025-05-16", "Meeting Notes"])
        expected = hashlib.md5("2025-05-16|Meeting Notes".encode()).hexdigest()
        assert result == expected

    def test_single_element(self):
        """Test the function with a single element."""
        result = get_hash_id(["single_element"])
        expected = hashlib.md5("single_element".encode()).hexdigest()
        assert result == expected

    def test_custom_delimiter(self):
        """Test the function with a custom delimiter."""
        result = get_hash_id(["user", "login", "192.168.1.1"], delimiter=":")
        expected = hashlib.md5("user:login:192.168.1.1".encode()).hexdigest()
        assert result == expected

    def test_non_string_elements(self):
        """Test the function with non-string elements."""
        result = get_hash_id([123, True, 3.14])
        expected = hashlib.md5("123|True|3.14".encode()).hexdigest()
        assert result == expected

    def test_empty_list_raises_error(self):
        """Test that an empty list raises a ValueError."""
        with pytest.raises(ValueError, match="At least one element is required"):
            get_hash_id([])

    @pytest.mark.parametrize(
        "elements,delimiter,expected",
        [
            (
                ["2025-05-16", "Meeting Notes"],
                "|",
                hashlib.md5("2025-05-16|Meeting Notes".encode()).hexdigest(),
            ),
            (
                ["user", "login", "192.168.1.1"],
                ":",
                hashlib.md5("user:login:192.168.1.1".encode()).hexdigest(),
            ),
            (
                [123, "test"],
                "-",
                hashlib.md5("123-test".encode()).hexdigest(),
            ),
        ],
    )
    def test_parametrized_inputs(self, elements, delimiter, expected):
        """Test various input combinations."""
        result = get_hash_id(elements, delimiter)
        assert result == expected

    def test_consistency(self):
        """Test that the same input always produces the same output."""
        elements = ["2025-05-16", "Meeting Notes", "Confidential"]
        first_result = get_hash_id(elements)
        second_result = get_hash_id(elements)
        assert first_result == second_result