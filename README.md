# TRPG Rulebook Structuring

Experimental Python rules engine with source-aware PTK / PTU 1.05 implementations and an external rule-scripting boundary.

Before reviewing rule compliance, consult [User rule decisions and audit exclusions](USER_RULE_DECISIONS.md). Explicit user rules are intentional differences from the source rules; their implementations still require verification.

This repository is a clean source snapshot for hosted validation. It is work in progress: an implemented clause or a passing test is not a claim that every rule and interaction has been independently verified. The initial source snapshot corresponds to the local project's 1,503-of-2,352 implementation checkpoint. The current revision integrates the five repair and extension candidates described in [REVISION.md](REVISION.md), without changing the clause completion count.

## Hosted validation

[Validation workflow](https://github.com/andrew0416/trpg-rulebook-structuring/actions/workflows/validate.yml) runs on a GitHub-hosted Windows runner with Python 3.11. Revision validation runs the move, rank and retraining groups on independent runners. The original `tools/test_common_checks.py` smoke suite remains available for manual dispatch.

The workflow calls the existing `work/reuse-partials/verify_overlay_tests.py` with explicit checkout and output roots. It preserves the verifier's collection and pass/fail conditions. Public results include the source commit, environment versions, input SHA-256 hashes and concise test outcomes. Original verifier JSON and detailed logs are preserved in an authenticated encrypted evidence archive. These CI results do not automatically award clause completion credit or replace the project's separate canonical publication acceptance process.

See [CI.md](CI.md) for operation, artifacts and limitations.

## Rule fixtures and source material

Engine and test source code are public. Rulebook text, third-party reference PDFs, derived rule data and internal verification ledgers are supplied to trusted validation runs through an authenticated encrypted fixture bundle. Their original bytes and source notices are preserved. They are not redistributed here as plaintext.

The repository secret `PTK_FIXTURE_KEY` is required for the full native suite. A public checkout without authorized fixtures cannot run that suite. The workflow does not expose the key, plaintext fixture archive or decrypted source material as public artifacts. Only trusted same-repository `main` and `codex/**` branches execute the protected validation path. Fork pull requests do not receive the fixture key.

Source manifests identify fixture paths and hashes; they are not a new license for the underlying material. See [SOURCE-NOTICES.md](SOURCE-NOTICES.md).

## Layout

- `engine/`: runtime rule and state owners.
- `tools/`: authoring, validation, fixtures and regression tests.
- `schema/`: source data schemas included by the snapshot, when applicable.
- `work/reuse-partials/verify_overlay_tests.py`: existing validation entry point.
- `.ci/`: encrypted fixture bundle and content manifests.

Generated validation outputs, caches, local credentials and historical work directories are not tracked. Existing rule source bytes are preserved without automatic Git newline conversion.
