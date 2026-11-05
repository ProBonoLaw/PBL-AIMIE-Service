import orjson
from langchain_core.documents import Document

from AIInteractionService.db.azuresearch import _result_to_document
from AIInteractionService.utils.formatters import format_source
from orchestrators.utils import convert_document_to_simplified_document, convert_to_document


def test_normal_search_result_does_not_promote_empty_fact_fields():
    result = {
        "@search.score": 1,
        "id": "normal-id",
        "content": "# Child Support Order\n\n\n",
        "metadata": orjson.dumps({
            "Header 1": "Child Support Order",
            "title": "CHILD_SUPPORT_ORDER_FINAL.pdf",
            "source": "https://example.com/source.pdf",
            "sourceId": "3",
            "tags": [],
            "pages": [1],
            "pos": 1,
        }),
        "tags": [],
        "hitCount": 1,
        "where": None,
        "what": None,
        "who": [],
        "why": None,
        "whenStarted": None,
        "whenEnded": None,
    }

    doc = _result_to_document(result)

    assert doc.metadata["id"] == "normal-id"
    assert doc.metadata["tags"] == []
    assert doc.metadata["hitCount"] == 1
    assert "where" not in doc.metadata
    assert "what" not in doc.metadata
    assert "who" not in doc.metadata
    assert "why" not in doc.metadata
    assert "whenStarted" not in doc.metadata
    assert "whenEnded" not in doc.metadata


def test_fact_event_search_result_preserves_fact_event_fields():
    when = {"year": "2030", "month": "5", "day": "12", "season": None, "quarter": None}
    result = {
        "@search.score": 1,
        "id": "fact-id",
        "content": "2030-05-12 - Jordan informed Alex.",
        "metadata": orjson.dumps({
            "headers": ["Unknown", "reason", orjson.dumps(when).decode()],
            "tags": ["fact", "event"],
            "source": "https://example.com/source.pdf",
            "sourceId": "example-source",
            "pages": [3],
        }),
        "where": "Unknown",
        "what": "Jordan told Alex that Casey would attend the example workshop.",
        "who": ["Jordan", "Alex", "Casey", "Example Center"],
        "why": "Casey registered for the example workshop.",
        "whenStarted": when,
        "whenEnded": when,
    }

    doc = _result_to_document(result)

    assert doc.metadata["id"] == "fact-id"
    assert doc.metadata["where"] == "Unknown"
    assert doc.metadata["what"] == "Jordan told Alex that Casey would attend the example workshop."
    assert doc.metadata["who"] == ["Jordan", "Alex", "Casey", "Example Center"]
    assert doc.metadata["why"] == "Casey registered for the example workshop."
    assert doc.metadata["whenStarted"] == when
    assert doc.metadata["whenEnded"] == when


def test_fact_tag_without_event_does_not_promote_event_fields():
    result = {
        "@search.score": 1,
        "id": "fact-only-id",
        "content": "Jordan informed Alex.",
        "metadata": orjson.dumps({
            "tags": ["fact"],
            "sourceId": "example-source",
            "pages": [3],
        }),
        "where": "Unknown",
        "what": "Jordan told Alex that Casey would attend the example workshop.",
        "who": ["Jordan", "Alex"],
        "why": "Casey registered for the example workshop.",
        "whenStarted": {"year": "2030", "month": "5", "day": "12"},
        "whenEnded": {"year": "2030", "month": "5", "day": "12"},
    }

    doc = _result_to_document(result)

    assert doc.metadata["tags"] == ["fact"]
    assert "where" not in doc.metadata
    assert "what" not in doc.metadata
    assert "who" not in doc.metadata
    assert "why" not in doc.metadata
    assert "whenStarted" not in doc.metadata
    assert "whenEnded" not in doc.metadata


def test_claim_assertion_and_allegation_events_preserve_fact_event_fields():
    for qualifying_tag in ["claim", "assertion", "allegation"]:
        result = {
            "@search.score": 1,
            "id": f"{qualifying_tag}-event-id",
            "content": "Jordan claimed Alex was informed.",
            "metadata": orjson.dumps({
                "tags": [qualifying_tag, "event"],
                "sourceId": "example-source",
                "pages": [3],
            }),
            "where": "Unknown",
            "what": "Jordan claimed Alex was informed.",
            "who": ["Jordan", "Alex"],
            "why": "Jordan made the claim in the record.",
            "whenStarted": {"year": "2030"},
            "whenEnded": {"year": "2030"},
        }

        doc = _result_to_document(result)

        assert doc.metadata["tags"] == [qualifying_tag, "event"]
        assert doc.metadata["where"] == "Unknown"
        assert doc.metadata["what"] == "Jordan claimed Alex was informed."
        assert doc.metadata["who"] == ["Jordan", "Alex"]
        assert doc.metadata["why"] == "Jordan made the claim in the record."
        assert doc.metadata["whenStarted"] == {"year": "2030"}
        assert doc.metadata["whenEnded"] == {"year": "2030"}


def test_fact_event_fields_are_formatted_for_agent_context():
    metadata = {
        "id": "fact-id",
        "title": "facts.json",
        "sourceId": "example-source",
        "pages": [3],
        "tags": ["claim", "event"],
        "where": "Unknown",
        "what": "Jordan told Alex that Casey would attend the example workshop.",
        "who": ["Jordan", "Alex", "Casey", "Example Center"],
        "why": "Casey registered for the example workshop.",
        "whenStarted": {"year": "2030", "month": "5", "day": "12"},
        "whenEnded": {"year": "2030", "month": "5", "day": "12"},
    }

    source = format_source(metadata)

    assert source["tags"] == ["claim", "event"]
    assert source["where"] == "Unknown"
    assert source["what"] == "Jordan told Alex that Casey would attend the example workshop."
    assert source["who"] == ["Jordan", "Alex", "Casey", "Example Center"]
    assert source["why"] == "Casey registered for the example workshop."
    assert source["whenStarted"] == {"year": "2030", "month": "5", "day": "12"}
    assert source["whenEnded"] == {"year": "2030", "month": "5", "day": "12"}


def test_simplified_document_round_trips_fact_event_fields():
    doc = Document(
        page_content="2030-05-12 - Jordan informed Alex.",
        metadata={
            "id": "fact-id",
            "title": None,
            "source": "https://example.com/source.pdf",
            "sourceId": "example-source",
            "pages": [3],
            "pos": None,
            "tags": ["fact", "event"],
            "where": "Unknown",
            "what": "Jordan told Alex that Casey would attend the example workshop.",
            "who": ["Jordan", "Alex", "Casey", "Example Center"],
            "why": "Casey registered for the example workshop.",
            "whenStarted": {"year": "2030", "month": "5", "day": "12"},
            "whenEnded": {"year": "2030", "month": "5", "day": "12"},
        },
    )

    simplified = convert_document_to_simplified_document(doc)
    restored = convert_to_document([simplified])[0]

    assert simplified.tags == ["fact", "event"]
    assert simplified.where == "Unknown"
    assert simplified.when_started == {"year": "2030", "month": "5", "day": "12"}
    assert restored.metadata["tags"] == ["fact", "event"]
    assert restored.metadata["where"] == "Unknown"
    assert restored.metadata["whenStarted"] == {"year": "2030", "month": "5", "day": "12"}
