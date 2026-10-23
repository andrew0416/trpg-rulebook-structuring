# Native revision CI with private fixtures

The **Validate revisions** workflow runs the five repair candidates' final required test IDs on GitHub-hosted `windows-2022` with Python 3.11. The unchanged fixed verifier enforces exact packet selection. This validates the declared revision scope and earns **zero clause-completion credit**.

Only reviewed code, schema files, CI configuration and public test-ID packets are public plaintext. Rulebook inputs and supporting fixture data are stored in `.ci/fixtures.zip.enc`, authenticated with AES-256-GCM. `.ci/fixtures-manifest.json` contains only relative paths, byte sizes and SHA-256 hashes. This repository does not relicense those sources or grant redistribution rights. Private candidate ledgers and original source documents are not published as plaintext.

## Running

Maintainers configure the repository Actions secret **PTK_FIXTURE_KEY** with the 64 hexadecimal characters representing the bundle's 32-byte key. The key must not be committed, placed in command-line arguments, or included in artifacts.

Relevant pushes to `main` and `codex/**` run three independent Windows VMs with `max-parallel: 3` and `fail-fast: false`. The job additionally requires repository identity `andrew0416/trpg-rulebook-structuring`, a push or manual event, and one of those trusted branch refs. Pull requests and external forks do not receive the private-fixture validation; there is no `pull_request_target` workflow.

**Actions → Validate revisions → Run workflow** offers a fixed choice on a trusted branch:

| Choice | Scope | Unique required IDs |
| --- | --- | ---: |
| `all_revisions` (default) | All three revision groups, each on its own VM | 259 across groups |
| `move_revisions` | Voice/keyword final 99 plus Push Buttons final 23 | 122 |
| `rank_revisions` | Declared ranks final 107, martial ranks final 20, integration final 2 | 126 |
| `retraining` | Edge choice retraining final 13 | 13 |
| `common_checks` | Existing full common-check module | 34 currently |

The three groups make 261 test executions because two IDs are shared across independent groups. `rank_revisions` already includes the 34 common checks, so the default does not add a redundant smoke job. Within each group only exact duplicate IDs are removed by the existing verifier. Its `tools.` module identity rules remain unchanged.

The [public suite packets](.ci/suites/) retain the original candidate IDs, relative provenance paths, candidate SHA-256 hashes, and final `required_test_ids` as exact `completed[*].tests` declarations. The `completed` key is required by the existing verifier format; it does not claim accepted clauses. Withdrawn assumptions and superseded initial failure allocations do not become current obligations. Original private candidate ledgers are not needed on the runner.

Each VM calls the adapter with one fixed suite name. The workflow never interpolates dispatch input into shell source; the selected name is passed through an environment variable and an argv argument. The helper validates it against argparse choices:

```powershell
python -B -X utf8 tools/ci_validate.py --root "$env:GITHUB_WORKSPACE" --suite move_revisions
```

The adapter removes the fixture key from its environment before launching any child and retains it only in a local variable. Only the Node fixture-decryption and evidence-encryption children receive it. The native verifier never inherits that key. Node's built-in crypto authenticates the complete bundle before writing a plaintext ZIP into a new directory under `RUNNER_TEMP`. Python rejects unsafe paths, duplicate names, symlink entries, tracked-file collisions, unexpected members, and size/hash mismatches. Existing differing local files are never overwritten. The temporary plaintext fixture ZIP is removed before game verification. After verification, the same unchanged AES-256-GCM helper encrypts the raw evidence with a fresh IV. The raw evidence ZIP exists only in a new temporary directory under `RUNNER_TEMP`, which is cleaned on success or failure.

The original verifier receives, for example:

```powershell
python -B -u -X utf8 work/reuse-partials/verify_overlay_tests.py --auto .ci/suites/move_revisions.json --canonical "$env:GITHUB_WORKSPACE" --stage "$env:GITHUB_WORKSPACE" --record "<new output/ci run directory>/verifier"
```

`rank_revisions` and `retraining` use their corresponding JSON packets. `common_checks` still passes `tools/test_common_checks.py`. Default mode 15 retains allocation, execution, JSON recording and existing required-test rules. Skips and expected failures remain unverified, and no retry subset can replace a required full run. No verifier acceptance rule or test expectation is relaxed. Python standard-library modules and built-in Node modules are sufficient; no package installation is needed.

The verifier rejects Windows C: checkouts and evidence directories. CI passes `GITHUB_WORKSPACE` explicitly. An incompatible runner path fails visibly.

## Evidence

Each invocation writes a new `output/ci/<UUID>/` directory. The public artifact has an exact filename allowlist:

- `run.json`: Git commit and tracked-change flag, suite/command, timestamps and result, Python/Node/Git/platform versions, selected CI metadata, encrypted-bundle/manifest/plaintext-fixture-ZIP hashes, original verifier outcome, and encrypted-evidence hash. Errors expose their type only.
- `summary.json`: suite, verifier status/exit code, original success flags, test IDs, fixed per-test statuses, counts and numeric timings. IDs must already appear in the public suite packets captured before execution; these include the 34 common checks. Subtest parameters, exception messages, tracebacks, skip reasons, locals and other content fields are excluded. Unlisted IDs are counted without displaying them. This display filter does not select tests or alter the verifier's acceptance rules.
- `input-sha256.json`: SHA-256 of every tracked public file and every authenticated restored fixture before verification.
- `input-sha256-after.json`: hashes of those same declared paths after verification, including failed and timed-out runs; unavailable paths are recorded as null.
- `input-comparison.json`: changed paths and short read-error types. A changed or missing input makes the CI result `input_drift`; an incomplete comparison makes it `input_check_error`. Both fail even if the verifier passed.
- `evidence.zip.enc`: authenticated encrypted original verifier JSON/logs, process output and detailed setup/input/summary error records. Raw bytes and failure results are preserved, not rewritten or deleted.

The plaintext raw files remain on the runner but are excluded from artifact uploads and console output. The encrypted ZIP contains `verifier/tests-<UUID>.json` and `.log`, `command.log`, fixture operation logs, and any detailed error records created before packaging. The plaintext evidence ZIP is never uploaded. Encryption uses the existing `PTKFX001` format and a new output file; it does not overwrite earlier evidence. If packaging or encryption fails, the job fails and public metadata records only a short error type. With a missing key, setup stops before private fixture restoration and publishes only safe metadata/summary.

Only the tracked public files and declared fixture files participate in the before/after comparison. New generated outputs are excluded. This comparison detects differences at the two snapshot boundaries; it is not a trace of every intermediate filesystem write or an input-read/module-origin audit.

Artifact **validation-<suite>-<run ID>-<attempt>** is uploaded even after failure and retained for 14 days. It contains only the six names above when available. Restored fixtures, raw diagnostics, generated scratch directories, historical logs, plaintext ZIPs and the key are excluded. The adapter never dumps the process environment or prints raw command output.

An authorized maintainer can download `evidence.zip.enc` and decrypt it with the same protected key through the Node helper. Supply the key only through the approved process environment and use a new private destination outside the public checkout:

```powershell
node tools/ci_fixtures.mjs decrypt "<downloaded evidence.zip.enc>" "<new private evidence ZIP>"
```

The native verifier has a 30-minute timeout; decryption retains a 15-minute timeout, and the complete job has a 40-minute limit. The previous move/keyword and push runs together took about 956 seconds, exceeding the old 15-minute verifier limit. A timeout is unsuccessful; evidence already written is retained where the job can upload it.

These results identify this Git commit and the authenticated fixture bytes used for the declared checks. They do not prove a separately changing local canonical tree was tested, increment clause completion, or replace canonical publication's physical ZIP/read/module evidence. Compare individual input hashes when relating runs.

`.gitattributes` preserves existing source bytes on Windows. `.gitignore` permits the reviewed code/CI paths, three public suite packets, the declared-ranks example, `REVISION.md`, and the encrypted fixture bundle plus metadata. Restored sources and generated outputs stay untracked.

## Adapter checks and fixture packaging

These checks use synthetic bytes and do not read private data or run game tests:

```powershell
node tools/ci_fixtures.mjs --self-check
python -B -X utf8 tools/ci_validate.py --self-check
```

The Python self-check covers fixed suite argv selection, invalid suite refusal, unsafe fixture paths, preserved raw failure JSON/logs, timeouts, missing or changed inputs, generated-output exclusion, and native-child key isolation. Synthetic sensitive text in tracebacks, subtest values, skip reasons and unknown IDs is absent from public summaries. A real AES-GCM round trip checks raw evidence byte preservation, temporary ZIP cleanup and encryption failure refusal. It does not execute the game suites or use the real fixture key.

A maintainer can encrypt an already prepared ZIP without putting the key in arguments:

```powershell
node tools/ci_fixtures.mjs encrypt "<private ZIP path>" .ci/fixtures.zip.enc
```

The key must already be in the process environment through an approved secret mechanism. Output files must be new. The format is the ASCII header `PTKFX001`, a fresh 12-byte IV, a 16-byte authentication tag, then ciphertext. The header is authenticated as additional data. The JSON manifest format is `{"version":1,"files":[{"path":"input/example.md","sha256":"<64 lowercase hex>","size":123}]}`; the ZIP must contain exactly those files, without directory entries.

## Pinned GitHub Actions

Official release tags and immutable commits were checked against GitHub's release and Git-ref APIs on 2026-10-23:

| Action | Release | Commit |
| --- | --- | --- |
| checkout | [v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| setup-python | [v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0) | `6d4fd22b20465ccc0f7354476588e8df7c9ca0e0` |
| upload-artifact | [v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2) | `cf430e030ddbb5b0abf93d22962f4752f3646cd9` |

All three pinned actions use Node 24. The workflow grants `contents: read` and disables checkout credential persistence.