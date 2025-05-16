import os

import click
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

SYSTEM_PROMPT_TEXT = "As an AI expert in legal affairs, your task is to provide concise, yet comprehensive " \
                     "summaries of legal news articles for time-constrained attorneys. These summaries " \
                     "should highlight the critical legal aspects, relevant precedents, and implications of " \
                     "the issues discussed in the articles.\n\nDespite their complexity, the summaries " \
                     "should be accessible and digestible, written in an engaging and conversational style. " \
                     "Accuracy and attention to detail are essential, as the readers will be legal " \
                     "professionals who may use these summaries to inform their practice.\n\n" \
                     "### Instructions: \n1. Begin the summary with a brief introduction of the topic of " \
                     "the article.\n2. Outline the main legal aspects, implications, and precedents " \
                     "highlighted in the article. \n3. End the summary with a succinct conclusion or " \
                     "takeaway.\n\nThe summaries should not be longer than 100 words, but ensure they " \
                     "efficiently deliver the key legal insights, making them beneficial for quick " \
                     "comprehension. The end goal is to help the lawyers understand the crux of the " \
                     "articles without having to read them in their entirety."


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=1, max=10))
async def get_jina_reader_content(link: str) -> str:
    """Fetch content from the Jina reader link."""
    jina_token = os.environ.get('JINA_API_TOKEN')
    if not jina_token:
        click.echo("JINA_API_TOKEN environment variable not set", err=True)
        return ""
    jina_link = f"https://r.jina.ai/{link}"
    headers = {
        "Authorization": f"Bearer {jina_token}",
        "X-Retain-Images": "none",
        "X-Target-Selector": "article"
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.get(jina_link, headers=headers)
        return r.text
    except httpx.RequestError as e:
        click.echo(f"Error fetching content from Jina reader: {e}", err=True)
        return ""


async def get_summary(text: str) -> str:
    """Generate a summary of the article text using OpenAI."""
    if not os.environ.get('OPENAI_API_KEY'):
        click.echo("OPENAI_API_KEY environment variable not set", err=True)
        return ""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(max_retries=3, timeout=60)
    try:
        response = await client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": SYSTEM_PROMPT_TEXT
                        }
                    ]
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"Here is an article to summarise:\n {text}"
                        }
                    ]
                }
            ],
            text={
                "format": {
                    "type": "text"
                }
            },
            temperature=0.42,
            max_output_tokens=2048,
            top_p=1,
            store=False
        )
        return response.output_text
    except Exception as e:
        click.echo(f"Error generating summary from OpenAI: {e}", err=True)
        return ""


def get_hash_id(elements: list[str], delimiter: str = "|") -> str:
    """Generate a hash ID from a list of strings.

    Args:
        elements: List of strings to be hashed.
        delimiter: String used to join elements (default: "|").

    Returns:
        A hexadecimal MD5 hash of the joined elements.

    Examples:
        >>> get_hash_id(["2025-05-16", "Meeting Notes"])
        '1a2b3c4d5e6f7g8h9i0j'

        >>> get_hash_id(["user123", "login", "192.168.1.1"], delimiter=":")
        '7h8i9j0k1l2m3n4o5p6q'
    """
    import hashlib

    if not elements:
        raise ValueError("At least one element is required")

    joined_string = delimiter.join(str(element) for element in elements)
    return hashlib.md5(joined_string.encode()).hexdigest()
