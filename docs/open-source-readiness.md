# Open-source readiness

Assessment date: November 5, 2026.

The original repository was **not ready for public transfer**. Local changes now
prepare its source for a new public repository under ProBonoLaw with a fresh initial
commit. The original repository and its history must remain private. Nothing in
this preparation transfers a repository, changes visibility, configures GitHub
variables, pushes commits, or deploys Azure resources.

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
- Docker is unavailable in this workspace, so the image build and container
  recovery smoke test still need to pass in CI. No live Azure deployment was tested.

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
or Production deployment environments. These settings have not been changed by
the local preparation.

## Public-to-private synchronization

Make ProBonoLaw the source of public code changes. Run synchronization from the
**private repository**, fetching public `main` and opening a private integration
PR. This achieves the requested public-to-private direction while keeping private
destination names, credentials, deployment logs and configuration off public
Actions runners.

Store the public source as a private GitHub variable such as
`PUBLIC_UPSTREAM_REPOSITORY=probonolaw/<chosen-repository-name>`. A private workflow
can poll it on a schedule or run manually. For prompt propagation, configure a
GitHub App on the private side to receive public push events. It needs only the
repository permissions required to create the private branch and PR; use a
secret for its credential. A PR created with the default `GITHUB_TOKEN` normally
does not trigger other Actions workflows; use an appropriately scoped GitHub App
token when the integration PR must run CI automatically.

The public and private repositories initially have unrelated histories. After
committing the sanitized source privately, perform a one-time **private** merge
of public `main` using `--allow-unrelated-histories`, resolve any conflicts, and
review the resulting tree. Thereafter merge public commits normally through
private integration PRs. Do not force-push over private history, mirror all refs,
or push private merge commits back into the public repository. Private-only fixes
destined for upstream need a separately reviewed, sanitized public patch.

Keep deployment automation downstream of the private merge. Build new
commit-tagged images there; image promotion verifies that the selected image's
commit belongs to private `main`. Synchronization, new repository creation and
GitHub configuration remain release setup tasks; no synchronization has been
activated by these local changes.
