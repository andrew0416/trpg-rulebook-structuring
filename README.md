# TRPG Rulebook Structuring

Experimental Python rules engine with source-aware PTK / PTU 1.05 implementations and an external rule-scripting boundary.

This repository is a clean source snapshot for hosted validation. It is work in progress: an implemented clause or a passing test is not a claim that every rule and interaction has been independently verified. The initial source snapshot corresponds to the local project's 1,503-of-2,352 implementation checkpoint; later unpublished repair candidates are not included in that snapshot.

## Hosted validation

[Validation workflow](https://github.com/andrew0416/trpg-rulebook-structuring/actions/workflows/validate.yml) runs on a GitHub-hosted Windows runner with Python 3.11. The first configured suite is `tools/test_common_checks.py`.

The workflow calls the existing `work/reuse-partials/verify_overlay_tests.py` with explicit checkout and output roots. It preserves the verifier's collection and pass/fail conditions. Results include the source commit, environment versions, input SHA-256 hashes, verifier JSON and raw test logs. These CI results do not automatically award clause completion credit or replace the project's separate canonical publication acceptance process.

See [CI.md](CI.md) for operation, artifacts and limitations.

## Rule fixtures and source material

Engine and test source code are public. Rulebook text, third-party reference PDFs, derived rule data and internal verification ledgers are supplied to trusted validation runs through an authenticated encrypted fixture bundle. Their original bytes and source notices are preserved. They are not redistributed here as plaintext.

The repository secret `PTK_FIXTURE_KEY` is required for the full native suite. A public checkout without authorized fixtures cannot run that suite. The workflow does not expose the key, plaintext fixture archive or decrypted source material as public artifacts. Fork pull requests do not receive or execute the protected full-validation path.

Source manifests identify fixture paths and hashes; they are not a new license for the underlying material. See [SOURCE-NOTICES.md](SOURCE-NOTICES.md).

## Layout

- `engine/`: runtime rule and state owners.
- `tools/`: authoring, validation, fixtures and regression tests.
- `schema/`: source data schemas included by the snapshot, when applicable.
- `work/reuse-partials/verify_overlay_tests.py`: existing validation entry point.
- `.ci/`: encrypted fixture bundle and content manifests.

Generated validation outputs, caches, local credentials and historical work directories are not tracked. Existing rule source bytes are preserved without automatic Git newline conversion.
