# Native CI prototype with private fixtures

The **Validate common checks** workflow runs the unchanged `tools/test_common_checks.py` suite on GitHub-hosted `windows-2022` with Python 3.11. This is one declared test suite, not full rulebook certification.

Only reviewed code, schema files and CI configuration are public plaintext. Rulebook inputs and supporting fixture data are stored in `.ci/fixtures.zip.enc`, authenticated with AES-256-GCM. `.ci/fixtures-manifest.json` contains only relative paths, byte sizes and SHA-256 hashes. This repository does not relicense those sources or grant redistribution rights.

## Running

Maintainers must configure the repository Actions secret **PTK_FIXTURE_KEY** with the 64 hexadecimal characters representing the bundle's 32-byte key. The key must not be committed, placed in command-line arguments, or included in artifacts.

Relevant changes pushed to `main` trigger validation. **Actions → Validate common checks → Run workflow** runs the same suite on `main`. Other branches and pull requests do not receive the private-fixture validation; there is no `pull_request_target` workflow.

The workflow calls:

```powershell
python -B -X utf8 tools/ci_validate.py --root "$env:GITHUB_WORKSPACE" --suite common_checks
```

The adapter removes the fixture key from its environment and passes it only to the Node decryption child. The native verifier never inherits that key. Node's built-in crypto authenticates the complete bundle before writing a plaintext ZIP into a new directory under `RUNNER_TEMP`. Python then rejects unsafe paths, duplicate names, symlink entries, tracked-file collisions, unexpected members, and size/hash mismatches before using the fixtures. Existing differing local files are never overwritten. The temporary plaintext ZIP is removed before game verification.

The original verifier receives:

```powershell
python -B -u -X utf8 work/reuse-partials/verify_overlay_tests.py --auto tools/test_common_checks.py --canonical "$env:GITHUB_WORKSPACE" --stage "$env:GITHUB_WORKSPACE" --record "<new output/ci run directory>/verifier"
```

Its default mode 15 retains full current module selection, execution, JSON recording and the existing required-test rules. Skips and expected failures remain unverified. No engine implementation, test expectation, or verifier rule is changed. Python standard-library modules and built-in Node modules are sufficient; no package installation is needed.

The verifier rejects Windows C: checkouts and evidence directories. CI passes `GITHUB_WORKSPACE` explicitly. An incompatible runner path fails visibly.

## Evidence

Each invocation writes a new `output/ci/<UUID>/` directory:

- `run.json`: Git commit and tracked-change flag, suite/command, timestamps and exit result, Python/platform, selected CI metadata, and encrypted-bundle/manifest/plaintext-ZIP hashes.
- `input-sha256.json`: SHA-256 of every tracked public file and every restored fixture. The manifest's individual paths are included, not just its aggregate hash.
- `fixture-decrypt.log`: operation status without key or source content.
- `command.log`: raw verifier process stdout/stderr.
- `verifier/tests-<UUID>.json` and `.log`: original full test results and unittest output, including failures.
- `setup-error.log` if initialization or fixture validation fails.

Artifact **validation-common_checks-<run ID>-<attempt>** is uploaded even after failure and retained for 14 days. It contains only this output directory, never the plaintext ZIP, restored data directories, historical logs, or the key. The adapter never dumps the process environment. Setup failures before evidence creation remain visible in the GitHub job log.

Subprocesses have a 15-minute timeout, and the complete job has a 20-minute limit. A timeout is an unsuccessful run. Public test failure logs can contain the diagnostic text emitted by the existing tests; the full fixture files are not copied to artifacts.

These results identify this code commit and the authenticated fixture bytes used for one suite. They do not prove that a separately changing local canonical tree was tested, increment clause completion, or replace canonical publication's physical ZIP/read/module evidence. Compare the individual input hashes when relating runs.

`.gitattributes` preserves existing file bytes on Windows. `.gitignore` allows only reviewed code/CI paths and the encrypted fixture bundle plus its metadata; restored source data and outputs stay untracked.

## Adapter checks and fixture packaging

These checks use synthetic bytes and do not read private data or run game tests:

```powershell
node tools/ci_fixtures.mjs --self-check
python -B -X utf8 tools/ci_validate.py --self-check
```

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