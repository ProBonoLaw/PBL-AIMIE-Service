# Contributing

Use Python 3.14, install `requirements.txt` in a virtual environment, and run
`python -m pytest -q` before opening a pull request. Run
`python scripts/check-publication.py` to check source identifiers.

Use synthetic people, records and infrastructure in examples and tests. Never
include case files, medical records, internal document links, private organization
identifiers, credentials or deployment values in commits, issues, PR descriptions
or screenshots. Keep local settings in ignored files and pass deployment settings
through environment variables. Public CI does not need private services.

Explain the behavior changed and how it was validated. Contributions are provided
under the repository's Apache-2.0 license. Report security issues privately as
described in [SECURITY.md](SECURITY.md).
