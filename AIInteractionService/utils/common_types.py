from typing_extensions import TypedDict, List, Annotated, Optional, Union


class Source(TypedDict):
    docId: Annotated[
        str,
        ...,
        "Mandatory field, the ID of the document"
    ]
    pages: Annotated[
        Optional[List[int]],
        "List of pages, if known and could be extracted from the document"
    ]


class AnswerWithSources(TypedDict):
    """An answer to the question, with sources."""

    answer: Annotated[
        str,
        ...,
        "The answer to the question.  It must have the docIds of the sources used each applicable sentence."
    ]
    location: Annotated[
        Optional[str],
        "The location of the court case, if known"
    ]
    sources: Annotated[
        List[Source],
        ...,
        "List of sources used to answer the question, include the page number and doc url and doc title, doc ID and headers in JSON format",
    ]
