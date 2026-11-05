"""Synthetic answer serialization example; never print configured source URLs."""

import os
from urllib.parse import urlsplit


def example_payload():
    # Private GitHub jobs map vars.SHAREPOINT_EXAMPLE_DOCUMENT_URL to this env var.
    source = os.environ.get("SHAREPOINT_EXAMPLE_DOCUMENT_URL") or "https://example.invalid/documents/example.pdf"
    parsed = urlsplit(source)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("SHAREPOINT_EXAMPLE_DOCUMENT_URL must be HTTPS without credentials, query, or fragment")
    return {
        "answer": 'Alex Example submitted the form ("docId":"example-document").',
        "chat_history": [],
        "sources": [{"docId": "example-document", "pages": [1]}],
        "context": [{
            "id": None,
            "metadata": {"id": "example-document", "title": "Synthetic example", "source": source, "pages": [1]},
            "page_content": "Alex Example submitted a sample form.",
            "type": "Document",
        }],
    }


if __name__ == "__main__":
    from activities.types import AnswerWithSourcesResult

    AnswerWithSourcesResult.model_validate(example_payload()).model_dump(by_alias=True)
    print("Synthetic example validated; source configuration was not printed.")
