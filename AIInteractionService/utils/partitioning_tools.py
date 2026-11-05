from typing import Generator, List, Sequence
from .section_extractor import SectionExtractor


def get_partitions[T](validation_requests: List[T], partition_size: int) -> Sequence[List[T]]:
    validation_partitions = [
        validation_requests[i:i + partition_size]
        for i in range(0, len(validation_requests), partition_size)
    ]

    return validation_partitions
