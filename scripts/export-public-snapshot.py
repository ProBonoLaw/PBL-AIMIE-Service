#!/usr/bin/env python3
"""Export reviewed working-tree source without Git history or ignored files.

The output is a new directory, never a Git clone. No remote is contacted.
"""

import argparse
import importlib.util
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publication_check", ROOT / "scripts/check-publication.py")
publication_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication_check)


def export(root, output):
    root, output = root.resolve(), output.resolve()
    if output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Export to a new directory outside the source repository")
    if output.exists():
        raise ValueError("Output already exists; refusing to overwrite it")
    files = publication_check.candidate_files(root)
    findings = list(publication_check.inspect_files(root, files))
    if findings:
        raise ValueError("Publication check failed; run scripts/check-publication.py for paths and line numbers")
    output.mkdir(parents=True)
    try:
        for relative in files:
            source = root / relative
            if not source.exists():
                continue
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o755 if source.stat().st_mode & 0o111 else 0o644)
    except Exception:
        shutil.rmtree(output)
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = export(ROOT, args.output)
    except ValueError as error:
        parser.error(str(error))
    print(f"Exported candidate source to {output}; scan and review it before initializing a new Git repository")


if __name__ == "__main__":
    main()
