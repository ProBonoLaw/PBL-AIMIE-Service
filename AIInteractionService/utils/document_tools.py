from typing import List, Optional, Sequence

from langchain_core.documents import Document

from AIInteractionService.generators.common import ensure_document


def deduplicate_sources(source1: List[Document], source2: Optional[Sequence[Document | dict]] =  None) -> List[Document]:
    source_keys = set()
    final_sources: List[Document] = []
    for source in source1:
        if source.metadata['id'] not in source_keys:
            source_keys.add(source.metadata['id'])
            final_sources.append(source)
    if source2 is None:
        return final_sources
    refined_sources = ensure_document(source2)
    for source in refined_sources:
        if source.metadata['id'] not in source_keys:
            source_keys.add(source.metadata['id'])
            final_sources.append(source)
    return final_sources
    