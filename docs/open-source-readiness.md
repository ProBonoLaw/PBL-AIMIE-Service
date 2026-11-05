# Open-source readiness

Assessment date: November 5, 2026.

The original repository was **not ready for public transfer**. The release uses
[ProBonoLaw/PBL-AIMIE-Service](https://github.com/ProBonoLaw/PBL-AIMIE-Service) with
a fresh initial commit. The original repository and its history remain private.
Deployment workflows and environment configuration are managed in the private
repository; public application changes are integrated downstream.

## Findings and changes

| Finding in the original source | Local remediation |
| --- | --- |
| `test.py` contained 15 literal SharePoint document links and identifiable legal, medical and family records | Replaced the entire payload with synthetic content. The optional document URL comes from `SHAREPOINT_EXAMPLE_DOCUMENT_URL`, mapped from a GitHub variable in a private-only workflow. No tenant, site, document title, source ID or case narrative was retained from that payload. |
| Eight evaluation Markdown files under `tests/test1/` and `tests/test2/` contained case-derived conversations/results | Removed those artifacts from the candidate source. They remain in private Git history. |
| Personal examples also appeared in prompt schemas, unit tests and README | Replaced the identified names and examples with synthetic people and values. |
| README, development-container metadata and bootstrap scripts identified the original organization or contact | Removed personal contacts, private repository links and organization-specific defaults. Bootstrap repository identity now comes from `DEPLOYMENT_REPOSITORY`. |
| Deployment code and documentation embedded subscription IDs, resource names, service endpoints, private DNS and addresses | Replaced infrastructure targets with required environment variables and manifest placeholders. Public tests use synthetic targets. See [configuration](deployment-configuration.md). |
| Main-branch workflows could publish images and deploy cloud resources | Cloud jobs now require a private repository and `ENABLE_PRIVATE_DEPLOYMENTS=true`. Public CI builds and validates without private configuration. |
| The default branch had no license | Added the Apache License 2.0, as selected by the repository owner. |
| Accidental reintroduction of sensitive material had no dedicated check | Added identifier checks, Gitleaks tree scanning, ignored credential/export paths, and a tested snapshot exporter that excludes Git history and ignored files. |

The initial local clone was not shallow and contained 345 commits across its
available refs. Inspection found private organization information in commit
metadata and retired sensitive files in earlier trees. A clean final commit on top
of that history does **not** make that history safe to publish. The fresh-history
release below avoids exporting it; no history rewrite is needed in the private
repository.

Gitleaks 8.30.1 scanned the available historical refs. Its two findings were the
same synthetic Azurite smoke-test key in historical versions, not confirmed live
credentials. The configuration allows only that exact synthetic key; other secret
detection rules remain enabled. Automated scanning cannot establish that arbitrary
prose contains no personal information or that every possible credential has been
detected.

## Validation

- 373 Python tests passed, including source configuration, required deployment
  variables, separation of Test/Production targets, and snapshot export checks.
- The synthetic answer serialization example passed without printing its URL.
- Both deployment manifest sets rendered and validated using synthetic values.
- Shell syntax checks and actionlint 1.7.12 passed for the updated workflows.
- The publication identifier check passed. The exported source tree contained
  281 files, no Git history or ignored local settings, and zero Gitleaks findings.
  Rerun these checks on the exact candidate used for publication after any edits.
- Container builds and the Azurite recovery smoke test run in GitHub Actions.
  Publication requires successful Python, manifest, image and publication checks
  for the release revision.
- LangGraph was updated to 1.2.14 to address GHSA-3fx2-cqw9-xr3c; all 373 Python
  tests passed with the patched dependency.

This review covered candidate source files, locally available Git refs, and basic
GitHub repository/security/environment metadata. It did not audit the contents of
issues, PRs, wiki pages, release assets, Actions logs/artifacts, external storage,
or every historical remote ref. A new repository should not import those assets.
Application security and dependency-license/vulnerability audits are separate
from this privacy preparation.

## Fresh-history release

1. Review and retain the sanitized changes in the private repository. The diff
   itself shows removed private values, so keep the cleanup PR and review private.
2. Export the reviewed working tree into a new directory outside this repository:

   ```bash
   python scripts/check-publication.py
   python scripts/export-public-snapshot.py --output /tmp/aimie-public-source
   gitleaks dir /tmp/aimie-public-source --redact --config /tmp/aimie-public-source/.gitleaks.toml
   ```

   The exporter includes tracked edits and nonignored new files, excludes deleted
   files, and refuses symlinks, private-file paths and identifier-check failures.
   It copies no `.git` directory, ignored local settings or credentials. Review
   the resulting files; do not export an unreviewed working tree.
3. Initialize a new repository **inside the exported directory** with a new
   initial commit. Use a public-facing author identity and GitHub noreply address.
   Do not copy the original `.git` directory, remotes, tags or branches. Create a
   new ProBonoLaw repository from this snapshot; do not transfer the original
   repository or use a mirror push. A temporary private staging repository in
   ProBonoLaw can run the complete public CI before changing visibility.
4. Configure branch protection/rulesets and required CI checks. Enable GitHub
   secret scanning, push protection, and private vulnerability reporting. Verify
   public descriptions, commit authors, issues and release assets contain only
   information intended for publication.
5. Keep private deployment configuration in the original repository. Populate the
   variables in [deployment configuration](deployment-configuration.md), set
   environment approval rules, and only then enable private deployment jobs.

The read-only GitHub audit reported the original repository as **internal**, with
secret scanning and push protection disabled and no protection rules on its Test
or Production deployment environments. Release setup configures the new public repository protections and private
deployment environment policies separately from the source cleanup.

## Public-to-private synchronization

Make ProBonoLaw the source of public code changes. Run synchronization from the
**private repository**, fetching public `main` and opening a private integration
PR. This achieves the requested public-to-private direction while keeping private
destination names, credentials, deployment logs and configuration off public
Actions runners.

The private repository runs synchronization every 15 minutes, with a manual
trigger also available. GitHub may delay scheduled runs. Its repository variable
`PUBLIC_UPSTREAM_REPOSITORY` identifies this public repository. The built-in
`GITHUB_TOKEN` creates or updates an integration PR and explicitly dispatches
Python, container and publication checks. The PR merges after required checks
pass, then dispatches private main CI to retain automatic Test deployment.
Production deployment remains manual.

All `.github/workflows` files remain owned by private `main`. Synchronization
preserves those files, including when public workflows change or are deleted;
public workflow changes are listed for private maintainer review. This preserves
the private deployment setup and avoids requiring a token that can modify
workflows. Application conflicts stop integration for review. No private
credentials or destination identifiers are configured in the public repository.

The public and private repositories initially have unrelated histories. After
committing the sanitized source privately, perform a one-time **private** merge
of public `main` using `--allow-unrelated-histories`, resolve any conflicts, and
review the resulting tree. Thereafter merge public commits normally through
private integration PRs. Do not force-push over private history, mirror all refs,
or push private merge commits back into the public repository. Private-only fixes
destined for upstream need a separately reviewed, sanitized public patch.

Keep deployment automation downstream of the private merge. Build new
commit-tagged images there; image promotion verifies that the selected image's
commit belongs to private `main`. Synchronization and deployment controls are configured exclusively in the
private repository. Keep public and private workflow maintenance separate.
