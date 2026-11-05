#!/usr/bin/env python3
"""Resolve a Test ACR tag to a fixed commit tag and manifest digest."""

import json
import re
import sys


def resolve(requested_tag: str, tag_rows: list[dict]) -> tuple[str, str]:
    if requested_tag != "latest" and not re.fullmatch(r"sha-[0-9a-f]{40}", requested_tag):
        raise ValueError("Image tag must be latest or sha- followed by a full commit SHA")

    matching = [row for row in tag_rows if row.get("name") == requested_tag]
    if len(matching) != 1:
        raise ValueError(f"Test ACR tag {requested_tag!r} was not found")
    digest = matching[0].get("digest", "")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"Test ACR tag {requested_tag!r} has an invalid digest")

    if requested_tag == "latest":
        commit_tags = [row for row in tag_rows if row.get("digest") == digest
                       and re.fullmatch(r"sha-[0-9a-f]{40}", row.get("name", ""))]
        if not commit_tags:
            raise ValueError("Test ACR latest has no matching immutable commit tag")
        requested_tag = max(commit_tags, key=lambda row: row.get("lastUpdateTime", ""))["name"]

    return requested_tag, digest


if __name__ == "__main__":
    try:
        tag, digest = resolve(sys.argv[1], json.load(sys.stdin))
    except (IndexError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"Could not resolve production image: {error}", file=sys.stderr)
        sys.exit(1)
    print(tag, digest)
