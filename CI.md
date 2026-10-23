# Native revision CI with private fixtures

The **Validate revisions** workflow runs the selected packet's final required test IDs on GitHub-hosted `windows-2022` with Python 3.11. The unchanged fixed verifier enforces exact packet selection. This validates the declared revision scope and earns **zero clause-completion credit**.

Only reviewed code, schema files, CI configuration and public test-ID packets are public plaintext. Rulebook inputs and supporting fixture data are stored in `.ci/fixtures.zip.enc`, authenticated with AES-256-GCM. `.ci/fixtures-manifest.json` contains only relative paths, byte sizes and SHA-256 hashes. This repository does not relicense those sources or grant redistribution rights. Private candidate ledgers and original source documents are not published as plaintext.

## Running

Maintainers configure the repository Actions secret **PTK_FIXTURE_KEY** with the 64 hexadecimal characters representing the bundle's 32-byte key. The key must not be committed, placed in command-line arguments, or included in artifacts.

Relevant pushes to `main` and `codex/**` run the current `next_revisions` packet on one Windows VM. Manual `all_revisions` runs the three historical revision groups on independent VMs with `max-parallel: 3` and `fail-fast: false`. The job additionally requires repository identity `andrew0416/trpg-rulebook-structuring`, a push or manual event, and one of those trusted branch refs. Pull requests and external forks do not receive the private-fixture validation; there is no `pull_request_target` workflow.

**Actions → Validate revisions → Run workflow** offers a fixed choice on a trusted branch:

| Choice | Scope | Unique required IDs |
| --- | --- | ---: |
| `all_revisions` (manual default) | All three historical revision groups, each on its own VM | 259 across groups |
| `move_revisions` | Voice/keyword final 99 plus Push Buttons final 23 | 122 |
| `rank_revisions` | Declared ranks final 107, martial ranks final 20, integration final 2 | 126 |
| `retraining` | Edge choice retraining final 13 | 13 |
| `common_checks` | Existing full common-check module | 34 currently |
| `next_revisions` | Root-reviewed integration packet, one VM and one physical execution | Defined by the packet |

Push validation selects `.ci/suites/next_revisions.json` directly; that current integration packet must be present. A single push runs its full declared scope once, without also launching the historical groups. Manual `all_revisions` preserves those three groups, and each explicit manual suite choice still selects only that suite. Older commits use their own workflow definitions. A single integration packet avoids combining parallel execution histories into one sequential acceptance history.

The three groups make 261 test executions because two IDs are shared across independent groups. `rank_revisions` already includes the 34 common checks, so manual `all_revisions` does not add a redundant smoke job. Within each group only exact duplicate IDs are removed by the existing verifier. Its `tools.` module identity rules remain unchanged.

The [public suite packets](.ci/suites/) retain the original candidate IDs, relative provenance paths, candidate SHA-256 hashes, and final `required_test_ids` as exact `completed[*].tests` declarations. The `completed` key is required by the existing verifier format; it does not claim accepted clauses. Withdrawn assumptions and superseded initial failure allocations do not become current obligations. Original private candidate ledgers are not needed on the runner.

Each VM calls the adapter with one fixed suite name. The workflow never interpolates dispatch input into shell source; the selected name is passed through an environment variable and an argv argument. The helper validates it against argparse choices:

```powershell
python -B -X utf8 tools/ci_validate.py --root "$env:GITHUB_WORKSPACE" --suite move_revisions
```

The adapter removes the fixture key from its environment before launching any child and retains it only in a local variable. Only the Node fixture-decryption and evidence-encryption children receive it. The native verifier never inherits that key. Node's built-in crypto authenticates the complete bundle before writing a plaintext ZIP into a new directory under `RUNNER_TEMP`. Python rejects unsafe paths, duplicate names, symlink entries, tracked-file collisions, unexpected members, and size/hash mismatches. Existing differing local files are never overwritten. Tracked files are copied with byte checks into a new `D:/trpg-rulebook-structuring/ci/<run ID>-<attempt>-<suite>` directory, and the authenticated fixtures are restored there. That directory must not already exist. Local invocations without a GitHub run ID use a fresh UUID. The native process uses this frozen stage as both stage and canonical root. The temporary plaintext fixture ZIP is removed before game verification. After verification, the same unchanged AES-256-GCM helper encrypts the raw evidence with a fresh IV. The raw evidence ZIP exists only in a new temporary directory under `RUNNER_TEMP`, which is cleaned on success or failure.

A selected JSON suite packet may declare `"certification_stage_id": "39891250011-1-next_revisions"`. This chooses `D:/trpg-rulebook-structuring/ci/<certification_stage_id>` so a later run on a fresh VM can capture the same absolute stage as an earlier execution. The field must be a non-reserved single path component of 1–128 ASCII letters, digits, underscores or hyphens, beginning with a letter or digit. Absent the field, the original run-ID/attempt/suite path remains. An existing runner stage is still refused; this field does not authorize overwriting it.

The stable stage ID identifies a candidate's physical path, not its input version. Every execution keeps its own ZIP and hashes. Root must preserve the original full required-test declaration, first full execution and failures, then decide which prior PASS results survive the actual changes before selecting an impact retry. The CI adapter and physical checker do not prove that unchanged test IDs or a shared path mean unchanged behavior.

The capture wrapper imports the unchanged verifier and calls its existing `main()` with these arguments, for example:

```powershell
python -B -u -X utf8 "<execution stage>/work/reuse-partials/verify_overlay_tests.py" --auto .ci/suites/move_revisions.json --canonical "<execution stage>" --stage "<execution stage>" --mode 15 --record "<new output/ci run directory>/verifier"
```

`rank_revisions` and `retraining` use their corresponding JSON packets. `common_checks` still passes `tools/test_common_checks.py`. Default mode 15 retains allocation, execution, JSON recording and existing required-test rules. Skips and expected failures remain unverified, and no retry subset can replace a required full run. No verifier acceptance rule or test expectation is relaxed. Python standard-library modules and built-in Node modules are sufficient; no package installation is needed.

The verifier rejects Windows C: stages and evidence directories. The stage is explicitly on D:, and evidence stays in the checkout's new `output/ci/<UUID>/` directory. An incompatible evidence path fails visibly. Temporary fixture outputs are redirected by the existing verifier to its record directory outside the input stage.

## Evidence

Each invocation writes a new `output/ci/<UUID>/` directory. The public artifact has an exact filename allowlist:

- `run.json`: Git commit and tracked-change flag, suite/command, timestamps and result, Python/Node/Git/platform versions, selected CI metadata, encrypted-bundle/manifest/plaintext-fixture-ZIP hashes, original verifier outcome, and encrypted-evidence hash. Errors expose their type only.
- `summary.json`: suite, verifier status/exit code, original success flags, test IDs, fixed per-test statuses, counts and numeric timings. IDs must already appear in the public suite packets captured before execution; these include the 34 common checks. Subtest parameters, exception messages, tracebacks, skip reasons, locals and other content fields are excluded. Unlisted IDs are counted without displaying them. This display filter does not select tests or alter the verifier's acceptance rules.
- `input-sha256.json`: SHA-256 of every tracked public file and every authenticated restored fixture in the execution stage before verification.
- `input-sha256-after.json`: hashes of those same declared paths after verification, including failed and timed-out runs; unavailable paths are recorded as null.
- `input-comparison.json`: changed paths and short read-error types. A changed or missing input makes the CI result `input_drift`; an incomplete comparison makes it `input_check_error`. Both fail even if the verifier passed.
- `evidence.zip.enc`: authenticated encrypted original verifier JSON/logs, physical input ZIP, read/module observations, process output and detailed error records. Raw bytes and failure results are preserved, not rewritten or deleted.

The plaintext raw files remain on the runner but are excluded from artifact uploads and console output. The encrypted ZIP contains `verifier/tests-<UUID>.json` and `.log`, `command.log`, fixture operation logs, `physical/*`, and any detailed error records created before packaging. The plaintext evidence ZIP is never uploaded. Encryption uses the existing `PTKFX001` format and a new output file; it does not overwrite earlier evidence. If packaging or encryption fails, the job fails and public metadata records only a short error type. With a missing key, setup stops before private fixture restoration and publishes only safe metadata/summary.

Only tracked public files and declared fixture files participate in the public before/after comparison. Generated outputs stay outside the stage. The private physical capture adds:

- `physical/ci-native-inputs.zip`: captured **before imports and test execution**, with `stage/<relative path>` entries and `physical-sha256.json` mapping original absolute paths to their byte hashes. The ZIP is closed before the native run so a timeout retains it.
- `physical/ci-native.json`: original requested and actual test IDs, real unittest failure/error IDs, pre/post SHA maps, first observed read hashes, module origins before execution and after execution, original report/log paths, and execution chronology. The new `evidence_id` is the adapter's unique `output/ci/<UUID>` directory name. `metadata_path`, `frozen_inputs` and `raw_log` reference `data/verification/ci-runs/<UUID>/ci-native.json`, `ci-native-inputs.zip` and `ci-native.log` relative to the original execution stage. The ID is validated as a safe single component, and an already present logical evidence directory is refused.
- `physical/ci-native.log`: a byte-for-byte copy of the completed original verifier log. The original UUID report and log also remain in `verifier/`.
- `physical/ci-native-partial.log` and `physical/ci-native-events.jsonl`: flushed native runner output, original failure/error tracebacks and observations made during execution. They preserve partial evidence if the process is killed before the original verifier writes its final report.

The wrapper follows the existing physical-capture pattern: saved physical opens, observed file reads, and observation hooks around the existing unittest runner and `startTest`. It does not select tests or implement a replacement runner. Reads of unlisted stage inputs, changed first-read/pre/post hashes, and project module origins outside the captured inputs fail the run. Interpreter library modules are excluded. These observations are not a trace of every intermediate write, nor proof of source completeness. A timeout or incomplete capture never becomes a synthetic successful execution.

Artifact **validation-<suite>-<run ID>-<attempt>** is uploaded even after failure and retained for 14 days. It contains only the six names above when available. Restored fixtures, raw diagnostics, generated scratch directories, historical logs, plaintext ZIPs and the key are excluded. The adapter never dumps the process environment or prints raw command output.

An authorized maintainer can download `evidence.zip.enc` and decrypt it with the same protected key through the Node helper. Supply the key only through the approved process environment and use a new private destination outside the public checkout:

```powershell
node tools/ci_fixtures.mjs decrypt "<downloaded evidence.zip.enc>" "<new private evidence ZIP>"
```

The native process has a 90-minute timeout; decryption retains a 15-minute timeout, and the complete job has a 105-minute limit. The initial 550-test integration run hit the former 45-minute native limit after 529 tests had started. A timeout is unsuccessful: preserve its original input ZIP, event journal and partial log as non-acceptance evidence, then rerun the full required suite. Missing final metadata or after-execution module origins are never reconstructed from partial observations. The first accepted result must come from a complete run and use its original unique evidence paths.

For canonical acceptance, authenticate/decrypt the evidence with the existing helper. Use the **same absolute** `execution_stage` path recorded by the original execution. Check the physical ZIP manifest and every member's SHA before materializing its `stage/` inputs through the existing Root-reviewed restoration process. Keep the raw archive's names unchanged: copy `physical/ci-native.json` to the exact `metadata_path` recorded inside it, `physical/ci-native.log` to `raw_log`, and `physical/ci-native-inputs.zip` to `frozen_inputs`. These are distinct execution directories under `data/verification/ci-runs/`. Create evidence destinations exclusively and refuse any existing destination; retain original verifier files and partial evidence separately.

Earlier captures using `data/verification/ci-native.*` retain those original paths and bytes permanently. They may be combined with a new capture only at the same original absolute stage path; never rewrite old metadata, logs, ZIPs, IDs or timestamps to make paths fit. A later capture may contain different input bytes even with the same stage ID. Preserve all prior evidence while Root reviews materialization of the current inputs and the continued validity of retained PASS results.

A candidate references each original metadata path in chronological `execution_history` and each original `raw_log` in `logs`, retaining its original exact required IDs and the first full run, including failures. A subset PASS is a later history entry, not a replacement for that history. The unmodified private `acceptance_evidence.verify_acceptance_evidence(stage, spec, canonical_root)` checks the original stage mapping, chronology, raw log IDs, exact obligations and physical hashes. Separate parallel jobs must not be relabeled as a sequential candidate history. No acceptance checker or canonical publishing tool is bundled or changed here.

These results identify the Git commit and authenticated fixture bytes used for the declared checks. They do not prove a separately changing local canonical tree was tested or increment clause completion. Root must independently review source completeness, change impact, required scope and publication input equivalence before accepting or publishing.

`.gitattributes` preserves existing source bytes on Windows. `.gitignore` permits the reviewed code/CI paths, public suite packets, the declared-ranks example, `REVISION.md`, and the encrypted fixture bundle plus metadata. Restored sources and generated outputs stay untracked.

## Adapter checks and fixture packaging

These checks use synthetic bytes and do not read private data or run game tests:

```powershell
node tools/ci_fixtures.mjs --self-check
python -B -X utf8 tools/ci_validate.py --self-check
```

The Python self-check includes the unchanged verifier with one generated synthetic test module; it covers real pass/failure, missing pre-capture, changed inputs, lazy external module origins, first reads and partial timeout preservation. It also checks a real synthetic two-run sequence at one stage (full FAIL followed by subset PASS), safe certification/evidence IDs, and duplicate evidence-ID refusal without modifying prior bytes. It has no dependency on the private acceptance checker. It also covers fixed suite argv selection, invalid suite refusal, unsafe fixture paths, preserved raw failure JSON/logs, timeouts, missing or changed inputs, generated-output exclusion, and native-child key isolation. Synthetic sensitive text in tracebacks, subtest values, skip reasons and unknown IDs is absent from public summaries. A real AES-GCM round trip checks raw evidence byte preservation, temporary ZIP cleanup and encryption failure refusal. It does not execute the game suites or use the real fixture key.

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