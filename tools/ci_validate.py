"""Restore authenticated private fixtures and record one unchanged verifier run."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import platform
import re
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from uuid import uuid4
import zipfile

from ci_physical import safe_id, diagnostic_profile

SUITES = {
    "changed_revisions": ".ci/suites/changed_revisions.json",
    "performance_probe": ".ci/suites/performance_probe.json",
    "frequency_equivalence": ".ci/suites/frequency_equivalence.json",
    "metadata_revisions": ".ci/suites/metadata_revisions.json",
    "procedural_22": ".ci/suites/procedural_22.json",
    "common_checks": "tools/test_common_checks.py",
    "move_revisions": ".ci/suites/move_revisions.json",
    "rank_revisions": ".ci/suites/rank_revisions.json",
    "retraining": ".ci/suites/retraining.json",
    "next_revisions": ".ci/suites/next_revisions.json",
    "final_revisions_01": ".ci/suites/final_revisions_01.json",
    "final_revisions_02": ".ci/suites/final_revisions_02.json",
    "final_revisions_03": ".ci/suites/final_revisions_03.json",
    "final_revisions_04": ".ci/suites/final_revisions_04.json",
    "final_revisions_05": ".ci/suites/final_revisions_05.json",
    "final_revisions_06": ".ci/suites/final_revisions_06.json",
    "final_revisions_07": ".ci/suites/final_revisions_07.json",
    "final_revisions_08": ".ci/suites/final_revisions_08.json",
    "final_revisions_09": ".ci/suites/final_revisions_09.json",
}
SUITES.update({f"repair_revisions_{n:02d}": f".ci/suites/repair_revisions_{n:02d}.json" for n in range(1, 10)})
SUITES.update({f"final_revisions_{n:02d}": f".ci/suites/final_revisions_{n:02d}.json" for n in range(10, 19)})
SUITES.update({f"procedural_{n:02d}": f".ci/suites/procedural_{n:02d}.json" for n in range(1, 22)})
NATIVE_TIMEOUT_SECONDS = 5400
STAGE_PARENT = Path("D:/trpg-rulebook-structuring/ci")
VERIFIER = "work/reuse-partials/verify_overlay_tests.py"
BUNDLE = ".ci/fixtures.zip.enc"
MANIFEST = ".ci/fixtures-manifest.json"
PRIVATE_POLICY_PATH = "data/ability-exchange-policy.json"
PRIVATE_POLICY_ENV = "PTK_ABILITY_EXCHANGE_POLICY_B64"
CI_ENVIRONMENT = (
    "GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
    "GITHUB_EVENT_NAME", "RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion",
)


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.STDOUT)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def input_hashes(root, names):
    hashes = {}
    for name in sorted(names):
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Input leaves the checkout: {name}")
        hashes[name] = file_hash(path)
    return hashes


def input_drift(root, before, output):
    after, errors, raw_errors = {}, {}, {}
    for name in before:
        try:
            after.update(input_hashes(root, [name]))
        except (OSError, ValueError) as exc:
            after[name] = None
            errors[name] = type(exc).__name__
            raw_errors[name] = traceback.format_exc()
    changed = [name for name in before if before[name] != after[name]]
    write_json(output / "input-sha256-after.json", after)
    result = {"unchanged": not changed, "changed_paths": changed, "read_errors": errors}
    write_json(output / "input-comparison.json", result)
    if raw_errors:
        write_json(output / "input-read-errors.json", raw_errors)
    return result


def verifier_command(root, suite, output):
    if suite not in SUITES:
        raise ValueError("Unknown CI suite")
    return [
        sys.executable, "-B", "-u", "-X", "utf8", *(["-I"] if suite.startswith("procedural_") else []), str(root / "tools/ci_physical.py"),
        "--stage", str(root), "--inputs", str(output / "input-sha256.json"),
        "--target", SUITES[suite], "--output", str(output),
    ]


def copy_stage(root, stage, hashes):
    stage.mkdir(parents=True, exist_ok=False)
    for name, expected in hashes.items():
        source, destination = root / name, stage / name
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError("Stage source leaves checkout")
        if not destination.resolve().is_relative_to(stage):
            raise ValueError("Stage destination leaves execution root")
        body = source.read_bytes()
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError("Tracked source changed before stage copy")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(body)
        if file_hash(destination) != expected:
            raise ValueError("Stage bytes differ from authenticated source")


def execution_stage(suite, packet=None):
    run_id = os.environ.get("GITHUB_RUN_ID", uuid4().hex)
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    if re.fullmatch("[a-zA-Z0-9-]+", run_id) is None or re.fullmatch("[0-9]+", attempt) is None:
        raise ValueError("Unsafe CI run identity")
    if suite not in SUITES:
        raise ValueError("Unknown CI suite")
    stage_id = (packet["certification_stage_id"] if packet and "certification_stage_id" in packet
                else run_id + "-" + attempt + "-" + suite)
    parent = STAGE_PARENT.resolve()
    stage = parent / safe_id(stage_id)
    if stage.is_symlink() or stage.resolve().parent != parent:
        raise ValueError("Execution stage leaves its fixed parent")
    return stage.resolve()


def fixture_path(name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\0" in name:
        raise ValueError("Invalid fixture path")
    path = PurePosixPath(name)
    if (path.is_absolute() or path.as_posix() != name
            or any(part in (".", "..") or part.startswith(".")
                   or part.endswith((" ", ".")) or PureWindowsPath(part).is_reserved()
                   for part in path.parts)
            or name.casefold() == "output/ci" or name.casefold().startswith("output/ci/")
            or name.casefold().startswith("tools/ci_")):
        raise ValueError("Unsafe or protected fixture path")
    return name


def fixture_rows(manifest, tracked):
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        raise ValueError("Unsupported fixture manifest")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Fixture manifest must list files")
    protected = {name.casefold() for name in tracked}
    by_name, seen = {}, set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "sha256", "size"}:
            raise ValueError("Invalid fixture manifest entry")
        name = fixture_path(row["path"])
        folded = name.casefold()
        if folded in seen or folded in protected:
            raise ValueError("Duplicate fixture path or collision with public tracked file")
        if (type(row["size"]) is not int or row["size"] < 0
                or not isinstance(row["sha256"], str)
                or re.fullmatch("[0-9a-f]{64}", row["sha256"]) is None):
            raise ValueError("Invalid fixture size or SHA-256")
        seen.add(folded)
        by_name[name] = row
    return by_name


def _fixture_destination(root, name, row, *, require_new=False):
    destination = root / name
    if not destination.resolve().is_relative_to(root):
        raise ValueError("Fixture path leaves the checkout")
    for candidate in (destination, *destination.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            raise ValueError("Fixture destination contains a symlink")
    if require_new and destination.exists():
        raise ValueError("Private fixture destination already exists")
    if destination.exists() and (
            not destination.is_file() or destination.stat().st_size != row["size"]
            or file_hash(destination) != row["sha256"]):
        raise ValueError("Existing fixture differs; refusing to overwrite it")
    return destination


def restore_fixtures(root, archive, manifest, tracked):
    rows = fixture_rows(manifest, tracked)
    with zipfile.ZipFile(archive) as bundle:
        entries, folded = {}, set()
        for info in bundle.infolist():
            name = fixture_path(info.orig_filename)
            kind = stat.S_IFMT(info.external_attr >> 16)
            if (name != info.filename or info.is_dir() or kind not in (0, stat.S_IFREG)
                    or name.casefold() in folded):
                raise ValueError("ZIP contains duplicate, symlink, or non-file entries")
            folded.add(name.casefold())
            entries[name] = info
        if set(entries) != set(rows):
            raise ValueError("ZIP paths do not exactly match the fixture manifest")
        for name, info in entries.items():
            row = rows[name]
            if info.file_size != row["size"]:
                raise ValueError("ZIP size differs from fixture manifest")
            _fixture_destination(root, name, row)
        # ZIP contents are authenticated before this function is called.
        for name, info in entries.items():
            row = rows[name]
            content = bundle.read(info)
            if len(content) != row["size"] or hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ValueError("Fixture content SHA-256 differs from manifest")
            destination = root / name
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as stream:
                    stream.write(content)
    return {name: row["sha256"] for name, row in rows.items()}


def private_policy_rows(manifest, bundled_manifest, tracked):
    rows = fixture_rows(manifest, tracked)
    if set(rows) != {PRIVATE_POLICY_PATH} or rows[PRIVATE_POLICY_PATH]["size"] > 16384:
        raise ValueError("Private policy manifest must declare the one small policy input")
    # Reuse the same case-insensitive collision rules across both private channels.
    fixture_rows({"version": 1, "files": [*bundled_manifest["files"], *manifest["files"]]}, tracked)
    return rows


def restore_private_policy(root, encoded, manifest, bundled_manifest, tracked):
    rows = private_policy_rows(manifest, bundled_manifest, tracked)
    row = rows[PRIVATE_POLICY_PATH]
    if not isinstance(encoded, str) or len(encoded) != 4 * ((row["size"] + 2) // 3):
        raise ValueError("Private policy secret is missing or has an invalid encoded size")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError, UnicodeError):
        raise ValueError("Private policy secret is not strict Base64") from None
    if (base64.b64encode(content).decode("ascii") != encoded
            or len(content) != row["size"]
            or hashlib.sha256(content).hexdigest() != row["sha256"]):
        raise ValueError("Private policy bytes differ from the tracked manifest")
    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeError, ValueError):
        raise ValueError("Private policy must be a UTF-8 JSON object") from None
    if not isinstance(document, dict):
        raise ValueError("Private policy must be a UTF-8 JSON object")
    destination = _fixture_destination(root, PRIVATE_POLICY_PATH, row, require_new=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(content)
    return {PRIVATE_POLICY_PATH: row["sha256"]}


def run_command(command, root, log, timeout=900, env=None):
    started = time.monotonic()
    outcome = {"command": command, "exit_code": 1, "status": "error"}
    with log.open("xb") as stream:
        try:
            result = subprocess.run(
                command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                timeout=timeout, check=False, env=env,
            )
            outcome.update(
                exit_code=result.returncode,
                status="pass" if result.returncode == 0 else "fail",
            )
        except subprocess.TimeoutExpired:
            outcome.update(exit_code=124, status="timeout")
            stream.write(b"\nCI timeout; this run did not complete.\n")
        except OSError:
            stream.write(traceback.format_exc().encode("utf-8"))
    outcome["elapsed_seconds"] = time.monotonic() - started
    return outcome


def crypt_file(root, mode, source, destination, key, log):
    crypto_env = {**os.environ, "PTK_FIXTURE_KEY": key}
    try:
        return run_command(
            ["node", str(root / "tools/ci_fixtures.mjs"), mode, str(source), str(destination)],
            root, log, env=crypto_env,
        )
    finally:
        crypto_env.pop("PTK_FIXTURE_KEY")


def encrypt_evidence(root, output, key, temp_root):
    files = [path for path in output.glob("*.log") if path.name != "evidence-encrypt.log"]
    files += list((output / "verifier").glob("tests-*.json"))
    files += list((output / "verifier").glob("tests-*.log"))
    files += [path for path in (output / "physical").glob("*") if path.is_file()]
    # Generated first-read evidence must survive the existing encrypted archive.
    for directory in ("procedural-generated", "procedural-additional", "ordinary-generated", "ordinary-extended-generated"):
        files += [path for path in (output / "physical" / directory).rglob("*") if path.is_file()]
    if (output / "input-read-errors.json").exists():
        files.append(output / "input-read-errors.json")
    with tempfile.TemporaryDirectory(prefix="ptk-evidence-", dir=temp_root) as directory:
        archive = Path(directory).resolve() / "evidence.zip"
        if not archive.is_relative_to(temp_root):
            raise ValueError("Evidence temporary directory leaves RUNNER_TEMP")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(files):
                if path.is_symlink() or not path.resolve().is_relative_to(output):
                    raise ValueError("Raw evidence leaves its run directory")
                bundle.write(path, path.relative_to(output).as_posix())
        sealed = output / "evidence.zip.enc"
        result = crypt_file(root, "encrypt", archive, sealed, key, output / "evidence-encrypt.log")
        if result["exit_code"] != 0:
            raise RuntimeError("Evidence encryption failed")
    evidence = {"file": sealed.name, "sha256": file_hash(sealed), "raw_file_count": len(files)}
    # Keep the complete original archive. A separate encrypted diagnostic view
    # avoids downloading each job's duplicate input corpus during failure repair.
    # It is explicitly insufficient for physical-input acceptance.
    try:
        diagnostics = [path for path in files if path.suffix != ".zip"]
        excluded = {path.relative_to(output).as_posix(): file_hash(path)
                    for path in files if path.suffix == ".zip"}
        with tempfile.TemporaryDirectory(prefix="ptk-diagnostics-", dir=temp_root) as directory:
            archive = Path(directory).resolve() / "diagnostics.zip"
            if not archive.is_relative_to(temp_root):
                raise ValueError("Diagnostic temporary directory leaves RUNNER_TEMP")
            with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
                for path in sorted(diagnostics):
                    if path.is_symlink() or not path.resolve().is_relative_to(output):
                        raise ValueError("Raw diagnostic leaves its run directory")
                    bundle.write(path, path.relative_to(output).as_posix())
                bundle.writestr("diagnostic-scope.json", json.dumps({
                    "schema_version": 1, "kind": "diagnostic_only",
                    "complete_input_capture": False, "full_evidence": evidence,
                    "excluded_input_archives": excluded,
                }, sort_keys=True))
            small = output / "diagnostics.zip.enc"
            result = crypt_file(root, "encrypt", archive, small, key, output / "diagnostics-encrypt.log")
            if result["exit_code"] != 0:
                raise RuntimeError("Diagnostic encryption failed")
        evidence["diagnostics"] = {"file": small.name, "sha256": file_hash(small),
                                   "raw_file_count": len(diagnostics), "complete_input_capture": False}
    except Exception as exc:
        # A convenience artifact must not change the original verifier outcome
        # or conceal the full authenticated evidence that was already preserved.
        evidence["diagnostics_error_type"] = type(exc).__name__
    return evidence


def public_summary(suite, reports, outcome, public_ids):
    """Only IDs from public packets, fixed statuses and numeric timings leave raw evidence."""
    def number(value):
        return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None

    summaries = []
    for details in reports:
        ids = list(dict.fromkeys(name for name in details.get("collected", [])
                                if isinstance(name, str) and name in public_ids))
        tests = {name: {"id": name, "status": "not_run"} for name in ids}
        for row in details.get("test_durations", []):
            if row.get("id") in tests and number(row.get("seconds")) is not None:
                tests[row["id"]].update(status="pass", seconds=number(row["seconds"]))
        counts = {}
        for field, status in (("skipped", "skip"), ("expected_failures", "expected_failure"),
                              ("unexpected_successes", "unexpected_success"),
                              ("failures", "fail"), ("errors", "error")):
            rows = details.get(field, [])
            counts[field] = len(rows)
            for row in rows:
                label = row.get("id") if isinstance(row, dict) else row
                if not isinstance(label, str):
                    continue
                holder = re.fullmatch(r"(?:setUpClass|tearDownClass|setUpModule|tearDownModule) \(([A-Za-z0-9_.]+)\)", label)
                for name in ids:
                    # Subtest labels may embed private values; publish only their parent ID.
                    if (label == name or label.startswith((name + " (", name + " ["))
                            or holder and name.startswith(holder[1] + ".")):
                        tests[name]["status"] = status
        for name in details.get("retry_ids", []):
            if name in tests and tests[name]["status"] == "pass":
                tests[name]["status"] = "unverified"
        kind = details.get("kind")
        summaries.append({
            "kind": kind if kind in ("run", "collection", "discovery_error", "routing_error") else "unknown",
            "successful": details.get("successful") is True,
            "tests_run": number(details.get("tests_run")),
            "collected_count": len(details.get("collected", [])),
            "undisplayed_test_count": len(details.get("collected", [])) - len(ids),
            "status_counts": {status: sum(row["status"] == status for row in tests.values())
                              for status in sorted({row["status"] for row in tests.values()})},
            "discovery_error_count": len(details.get("discovery_errors", [])),
            "result_counts": counts,
            "timing": {name: number(details.get(name)) for name in
                       ("elapsed_seconds", "discovery_seconds", "suite_seconds")},
            "tests": list(tests.values()),
        })
    return {"schema_version": 1, "suite": suite, "report_count": len(summaries),
            "verifier_status": outcome["status"], "verifier_exit_code": outcome["exit_code"],
            "reports": summaries}


def self_check():
    def rejects(call):
        try:
            call()
        except ValueError:
            return
        raise AssertionError("Unsafe or mismatched fixture was accepted")

    with tempfile.TemporaryDirectory(prefix="ci-validate-self-check-") as directory:
        root = Path(directory).resolve()
        content = b"line\r\n\x00"
        name = "input/source.txt"
        manifest = {"version": 1, "files": [{
            "path": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
        }]}
        archive = root / "fixture.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(name, content)
        hashes = restore_fixtures(root, archive, manifest, [])
        assert (root / name).read_bytes() == content
        assert input_hashes(root, [name]) == hashes
        rejects(lambda: input_hashes(root, ["../outside.txt"]))
        for unsafe in ("../outside", "/absolute", "C:/absolute", "input\\bad", "input/../bad",
                       ".git/config", ".github/workflows/evil.yml", "output/ci/evil",
                       "tools/ci_fixtures.mjs", "input/NUL.txt", "input/file:stream"):
            rejects(lambda unsafe=unsafe: fixture_path(unsafe))
        rejects(lambda: restore_fixtures(root, archive, manifest, [name]))
        duplicate = {"version": 1, "files": [manifest["files"][0], manifest["files"][0]]}
        rejects(lambda: fixture_rows(duplicate, []))
        mismatch = {"version": 1, "files": [{
            **manifest["files"][0], "sha256": "0" * 64,
        }]}
        rejects(lambda: restore_fixtures(root, archive, mismatch, []))
        (root / name).write_bytes(b"keep existing")
        rejects(lambda: restore_fixtures(root, archive, manifest, []))
        assert (root / name).read_bytes() == b"keep existing"
        (root / name).unlink()
        rejects(lambda: restore_fixtures(root, archive, mismatch, []))
        assert not (root / name).exists()
        for entries in (
                [("../outside.txt", content)],
                [(name, content), ("input/SOURCE.txt", content)],
                [("input/unlisted.txt", content)]):
            with zipfile.ZipFile(archive, "w") as bundle:
                for entry, body in entries:
                    bundle.writestr(entry, body)
            rejects(lambda: restore_fixtures(root, archive, manifest, []))
        link = zipfile.ZipInfo(name)
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(link, "target")
        rejects(lambda: restore_fixtures(root, archive, manifest, []))
        for suite, target in SUITES.items():
            command = verifier_command(root, suite, root)
            assert command[command.index("--target") + 1] == target
            assert command[command.index("--inputs") + 1] == str(root / "input-sha256.json")
            assert command[command.index("--stage") + 1] == str(root)
            assert "--cases" not in command and "--mode" not in command
        rejects(lambda: verifier_command(root, "../outside; echo injected", root))
        from unittest.mock import patch
        # Synthetic only: exact CRLF bytes survive the additional Secret channel.
        private_content = b'{"synthetic":true}\r\n'
        encoded = base64.b64encode(private_content).decode("ascii")
        private_manifest = {"version": 1, "files": [{
            "path": PRIVATE_POLICY_PATH, "size": len(private_content),
            "sha256": hashlib.sha256(private_content).hexdigest(),
        }]}
        private_hashes = restore_private_policy(root, encoded, private_manifest, manifest, [])
        private_path = root / PRIVATE_POLICY_PATH
        assert private_path.read_bytes() == private_content
        assert input_hashes(root, [PRIVATE_POLICY_PATH]) == private_hashes
        rejects(lambda: restore_private_policy(root, encoded, private_manifest, manifest, []))
        assert private_path.read_bytes() == private_content
        private_path.unlink()
        for bad in (None, "", encoded + "\n", "!" * len(encoded), encoded[:-1] + "!"):
            rejects(lambda bad=bad: restore_private_policy(root, bad, private_manifest, manifest, []))
            assert not private_path.exists()
        wrong_hash = {"version": 1, "files": [{**private_manifest["files"][0], "sha256": "0" * 64}]}
        rejects(lambda: restore_private_policy(root, encoded, wrong_hash, manifest, []))
        wrong_size = {"version": 1, "files": [{**private_manifest["files"][0], "size": len(private_content) + 1}]}
        rejects(lambda: restore_private_policy(root, encoded, wrong_size, manifest, []))
        rejects(lambda: private_policy_rows(private_manifest, manifest, [PRIVATE_POLICY_PATH.upper()]))
        duplicate_channel = {"version": 1, "files": [
            {**private_manifest["files"][0], "path": PRIVATE_POLICY_PATH.upper()}]}
        rejects(lambda: private_policy_rows(private_manifest, duplicate_channel, []))
        duplicate_private = {"version": 1, "files": private_manifest["files"] * 2}
        rejects(lambda: private_policy_rows(duplicate_private, manifest, []))
        unsafe_private = {"version": 1, "files": [
            {**private_manifest["files"][0], "path": "../policy.json"}]}
        rejects(lambda: private_policy_rows(unsafe_private, manifest, []))
        oversized = {"version": 1, "files": [{**private_manifest["files"][0], "size": 16385}]}
        rejects(lambda: private_policy_rows(oversized, manifest, []))
        for invalid_json in (b"not-json", b"[]", b"\xff"):
            invalid_manifest = {"version": 1, "files": [{
                "path": PRIVATE_POLICY_PATH, "size": len(invalid_json),
                "sha256": hashlib.sha256(invalid_json).hexdigest(),
            }]}
            rejects(lambda invalid_json=invalid_json, invalid_manifest=invalid_manifest:
                    restore_private_policy(root, base64.b64encode(invalid_json).decode("ascii"),
                                           invalid_manifest, manifest, []))
            assert not private_path.exists()
        def assert_secret_environment_cleared():
            assert "PTK_FIXTURE_KEY" not in os.environ
            assert PRIVATE_POLICY_ENV not in os.environ
        # main() must pop both values before even its first child or self-check callback.
        with patch.dict(os.environ, {"PTK_FIXTURE_KEY": "a" * 64, PRIVATE_POLICY_ENV: encoded}), \
             patch.object(sys, "argv", ["ci_validate.py", "--self-check"]), \
             patch.dict(globals(), {"self_check": assert_secret_environment_cleared}):
            assert main() == 0

        with patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}):
            assert execution_stage("next_revisions").name == "123-2-next_revisions"
            fixed = {"certification_stage_id": "39891250011-1-next_revisions"}
            assert execution_stage("next_revisions", fixed).name == fixed["certification_stage_id"]
            for unsafe in ("../escape", "a/b", "a\\b", "C:escape", ".", "CON", "nul",
                           "id.", "id ", "", None, 42, "a" * 129):
                rejects(lambda: execution_stage("next_revisions", {"certification_stage_id": unsafe}))
        stage_source = root / "stage-source"
        stage_source.mkdir()
        (stage_source / "tracked.txt").write_bytes(content)
        pinned = input_hashes(stage_source, ["tracked.txt"])
        stage_copy = root / "stage-copy"
        copy_stage(stage_source, stage_copy, pinned)
        assert input_hashes(stage_copy, pinned) == pinned
        (stage_source / "tracked.txt").write_bytes(b"changed")
        rejects(lambda: copy_stage(stage_source, root / "bad-copy", pinned))
        failed = run_command(
            [sys.executable, "-c", "from pathlib import Path; import json; "
             "Path('failed-raw.json').write_text(json.dumps({'successful': False})); "
             "print('raw failure'); raise SystemExit(7)"],
            root, root / "failed.log",
        )
        assert failed["exit_code"] == 7 and failed["status"] == "fail"
        assert b"raw failure" in (root / "failed.log").read_bytes()
        assert json.loads((root / "failed-raw.json").read_text()) == {"successful": False}
        passed = run_command(
            [sys.executable, "-c", "import os; assert 'PTK_FIXTURE_KEY' not in os.environ; "
             "assert 'PTK_ABILITY_EXCHANGE_POLICY_B64' not in os.environ"],
            root, root / "passed.log",
        )
        assert passed["exit_code"] == 0 and passed["status"] == "pass"
        timed_out = run_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            root, root / "timeout.log", timeout=0.05,
        )
        assert timed_out["exit_code"] == 124 and timed_out["status"] == "timeout"
        assert b"CI timeout" in (root / "timeout.log").read_bytes()
        (root / "public.py").write_bytes(b"public code")
        (root / name).write_bytes(content)
        before = input_hashes(root, ["public.py", name])
        for folder in ("stable", "changed"):
            (root / folder).mkdir()
        # Generated logs and JSON are deliberately outside the declared inputs.
        assert input_drift(root, before, root / "stable")["unchanged"]
        (root / "public.py").write_bytes(b"changed code")
        (root / name).unlink()
        drift = input_drift(root, before, root / "changed")
        assert not drift["unchanged"]
        assert set(drift["changed_paths"]) == {"public.py", name}
        assert name in drift["read_errors"]
        assert (root / "failed.log").read_bytes().count(b"raw failure") == 1
        assert json.loads((root / "failed-raw.json").read_text()) == {"successful": False}
        marker = "PRIVATE_SOURCE_AND_LOCALS_SENTINEL"
        case_ids = ["tools.test_ci_synthetic.Check.test_" + status
                    for status in ("pass", "fail", "error", "skip", "expected", "unexpected", "pending")]
        raw = {
            "kind": "run", "successful": False, "collected": case_ids, "tests_run": 6,
            "test_durations": [{"id": name, "seconds": 0.1} for name in case_ids[:-1]],
            "failures": [{"id": case_ids[1] + " (value='" + marker + "')", "traceback": marker}],
            "errors": [{"id": case_ids[2], "traceback": marker}],
            "skipped": [{"id": case_ids[3], "reason": marker}],
            "expected_failures": [case_ids[4]], "unexpected_successes": [case_ids[5]],
            "discovery_errors": [marker], "elapsed_seconds": 0.8,
        }
        summary = public_summary("common_checks", [raw], failed, case_ids)
        assert marker not in json.dumps(summary)
        assert [row["status"] for row in summary["reports"][0]["tests"]] == [
            "pass", "fail", "error", "skip", "expected_failure", "unexpected_success", "not_run"]
        assert summary["verifier_exit_code"] == 7
        assert public_summary("common_checks", [], timed_out, case_ids)["verifier_status"] == "timeout"
        assert marker not in json.dumps(public_summary("common_checks", [
            {"kind": "routing_error", "successful": False, "workflow": {"reason": marker}}], failed, case_ids))
        undisclosed = "tools.test_private.Check.test_" + marker
        assert marker not in json.dumps(public_summary(
            "common_checks", [{**raw, "collected": [*case_ids, undisclosed]}], failed, case_ids))
        evidence = root / "evidence"
        (evidence / "verifier").mkdir(parents=True)
        (evidence / "physical").mkdir()
        write_json(evidence / "summary.json", summary)
        write_json(evidence / "verifier/tests-synthetic.json", raw)
        (evidence / "verifier/tests-synthetic.log").write_text(marker, encoding="utf-8")
        (evidence / "command.log").write_bytes((root / "failed.log").read_bytes() + marker.encode())
        (evidence / "setup-error.log").write_text(marker, encoding="utf-8")
        (evidence / "input-read-errors.json").write_bytes((root / "changed/input-read-errors.json").read_bytes())
        (evidence / "physical/ci-native.json").write_text(marker, encoding="utf-8")
        (evidence / "physical/ci-native-inputs.zip").write_bytes(b"physical input " + marker.encode())
        (evidence / "physical/ci-native-events.jsonl").write_text(marker, encoding="utf-8")
        raw_paths = ["physical/ci-native.json", "physical/ci-native-inputs.zip",
                     "physical/ci-native-events.jsonl", "verifier/tests-synthetic.json", "verifier/tests-synthetic.log",
                     "command.log", "setup-error.log", "input-read-errors.json"]
        raw_hashes = input_hashes(evidence, raw_paths)
        project = Path(__file__).resolve().parents[1]
        key = os.urandom(32).hex()
        assert "PTK_FIXTURE_KEY" not in os.environ
        sealed = encrypt_evidence(project, evidence, key, root)
        assert sealed["raw_file_count"] == len(raw_paths)
        assert sealed["sha256"] == file_hash(evidence / "evidence.zip.enc")
        assert marker.encode() not in (evidence / "evidence.zip.enc").read_bytes()
        assert input_hashes(evidence, raw_paths) == raw_hashes
        assert not list(root.glob("ptk-evidence-*"))
        recovered = root / "recovered.zip"
        result = crypt_file(project, "decrypt", evidence / "evidence.zip.enc", recovered,
                            key, root / "recovered.log")
        assert result["exit_code"] == 0
        with zipfile.ZipFile(recovered) as bundle:
            assert set(bundle.namelist()) == set(raw_paths)
            for name in raw_paths:
                assert hashlib.sha256(bundle.read(name)).hexdigest() == raw_hashes[name]
        compact = sealed["diagnostics"]
        assert compact["complete_input_capture"] is False
        assert compact["sha256"] == file_hash(evidence / compact["file"])
        assert marker.encode() not in (evidence / compact["file"]).read_bytes()
        small_recovered = root / "diagnostics-recovered.zip"
        result = crypt_file(project, "decrypt", evidence / compact["file"], small_recovered,
                            key, root / "diagnostics-recovered.log")
        assert result["exit_code"] == 0
        with zipfile.ZipFile(small_recovered) as bundle:
            expected = set(raw_paths) - {"physical/ci-native-inputs.zip"}
            assert set(bundle.namelist()) == expected | {"diagnostic-scope.json"}
            for name in expected:
                assert hashlib.sha256(bundle.read(name)).hexdigest() == raw_hashes[name]
            scope = json.loads(bundle.read("diagnostic-scope.json"))
            assert scope["kind"] == "diagnostic_only" and scope["complete_input_capture"] is False
            assert scope["full_evidence"]["sha256"] == sealed["sha256"]
            assert scope["excluded_input_archives"] == {
                "physical/ci-native-inputs.zip": raw_hashes["physical/ci-native-inputs.zip"]}
        assert not list(root.glob("ptk-diagnostics-*"))
        assert "PTK_FIXTURE_KEY" not in os.environ
        rejected = root / "encryption-failure"
        rejected.mkdir()
        (rejected / "command.log").write_text(marker, encoding="utf-8")
        try:
            encrypt_evidence(project, rejected, "invalid", root)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Failed evidence encryption was accepted")
        assert not (rejected / "evidence.zip.enc").exists()
        assert (rejected / "command.log").read_text(encoding="utf-8") == marker
        assert not list(root.glob("ptk-evidence-*"))
    from ci_physical_selfcheck import self_check as physical_self_check
    physical_self_check(Path(__file__).resolve().parents[1])
    print("CI adapter self-check passed; no private inputs or game tests used.")


def main():
    # Keep the key local; only the two Node crypto children receive it.
    fixture_key = os.environ.pop("PTK_FIXTURE_KEY", None)
    private_policy = os.environ.pop(PRIVATE_POLICY_ENV, None)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, default="common_checks")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        fixture_key = None
        private_policy = None
        self_check()
        return 0

    root = args.root.resolve()
    output = root / "output" / "ci" / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema_version": 4,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "target": SUITES[args.suite],
        "root": str(root),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "ci": {key: os.environ[key] for key in CI_ENVIRONMENT if key in os.environ},
        "scope": "Authenticated frozen CI stage; declared suite only. Physical evidence requires independent acceptance and source/impact review.",
        "input_manifest": "input-sha256.json",
        "input_manifest_after": "input-sha256-after.json",
        "input_comparison": "input-comparison.json",
        "native_timeout_seconds": NATIVE_TIMEOUT_SECONDS,
        "public_summary": "summary.json",
    }
    outcome = {"exit_code": 1, "status": "setup_error"}
    baseline = None
    stage = None
    public_ids = set()
    temp_root = None
    try:
        metadata["node_version"] = subprocess.check_output(
            ["node", "--version"], timeout=10, stderr=subprocess.STDOUT).decode("ascii").strip()
        metadata["git_version"] = git(root, "--version").decode("ascii").strip()
        metadata["git_sha"] = git(root, "rev-parse", "HEAD").decode("ascii").strip()
        metadata["tracked_changes"] = bool(
            git(root, "status", "--porcelain", "--untracked-files=no")
        )
        tracked = [name for name in git(root, "ls-files", "-z").decode("utf-8").split("\0") if name]
        hashes = input_hashes(root, tracked)
        for required in (SUITES[args.suite], VERIFIER, BUNDLE, MANIFEST,
                         "tools/ci_fixtures.mjs", "tools/ci_physical.py"):
            if required not in hashes:
                raise ValueError("The suite, fixed verifier, crypto adapter and fixture bundle/manifest must be Git-tracked")
        if args.suite == 'frequency_equivalence':
            for required in ('tools/ci_frequency_gate.py','tools/ci_frequency_equivalence.py'):
                if required not in hashes:raise ValueError('Equivalence adapter and frozen harness must be Git-tracked')
        if args.suite.startswith('procedural_') and 'tools/ci_procedural_gate.py' not in hashes:
            raise ValueError('Procedural adapter must be Git-tracked')
        # This allowlist controls public display only; the fixed verifier still owns execution.
        selected_packet = None
        for target in SUITES.values():
            if target.endswith(".json") and target in hashes:
                packet = json.loads((root / target).read_text(encoding="utf-8"))
                if target == SUITES[args.suite]:
                    selected_packet = packet
                public_ids.update(case for row in packet["completed"].values() for case in row["tests"])
        if diagnostic_profile(selected_packet, SUITES[args.suite]):
            metadata['diagnostic_profile'] = True
        metadata["fixture_bundle_sha256"] = hashes[BUNDLE]
        metadata["fixture_manifest_sha256"] = hashes[MANIFEST]
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        fixture_rows(manifest, tracked)
        private_manifest = None
        if "private_policy" in manifest:
            private_manifest = {"version": 1, "files": [manifest["private_policy"]]}
            private_policy_rows(private_manifest, manifest, tracked)
            if private_policy is None:
                raise ValueError("The declared private policy Secret is required")
        elif private_policy is not None:
            raise ValueError("Private policy Secret requires Git-tracked manifest metadata")
        if fixture_key is None:
            raise ValueError("PTK_FIXTURE_KEY is required to authenticate the private fixtures")
        temp_root = Path(os.environ["RUNNER_TEMP"]).resolve()
        stage = execution_stage(args.suite, selected_packet)
        copy_stage(root, stage, hashes)
        metadata["execution_stage"] = str(stage)
        metadata["evidence_id"] = output.name
        metadata["physical_metadata"] = "physical/ci-native.json"
        with tempfile.TemporaryDirectory(prefix="ptk-fixtures-", dir=temp_root) as directory:
            archive = Path(directory).resolve() / "fixtures.zip"
            if not archive.is_relative_to(temp_root):
                raise ValueError("Fixture temporary directory leaves the selected runner temp")
            restored = crypt_file(
                root, "decrypt", root / BUNDLE, archive, fixture_key, output / "fixture-decrypt.log")
            if restored["exit_code"] != 0:
                raise ValueError("Fixture decryption failed; see fixture-decrypt.log")
            metadata["fixture_archive_sha256"] = file_hash(archive)
            hashes.update(restore_fixtures(stage, archive, manifest, tracked))
            metadata["fixture_file_count"] = len(manifest["files"])
        if private_manifest is not None:
            hashes.update(restore_private_policy(stage, private_policy, private_manifest, manifest, tracked))
            metadata["fixture_file_count"] += 1
        private_policy = None
        if 'engine/marksman.py' in hashes:
            if 'tools/ci_prepare_marksman_source.py' not in hashes:
                raise ValueError('Marksman source preparation must be Git-tracked')
            from ci_prepare_marksman_source import prepare_stage as prepare_marksman_source, SourcePreparationError
            try:
                metadata['marksman_source_preparation'] = prepare_marksman_source(stage, manifest, hashes, output)
            except SourcePreparationError as exc:
                metadata['marksman_source_preparation'] = exc.safe_report
                raise
        if args.suite.startswith('procedural_'):
            from ci_procedural_gate import prepare_stage
            prepare_stage(stage, selected_packet, hashes, output / 'procedural-preparation.log')
        write_json(output / "input-sha256.json", hashes)
        baseline = hashes
        command = verifier_command(stage, args.suite, output)
        outcome = run_command(
            command, stage, output / "command.log", timeout=NATIVE_TIMEOUT_SECONDS)
        metadata["verifier_outcome"] = dict(outcome)
    except Exception as exc:
        metadata["setup_error_type"] = type(exc).__name__
        raw_error = traceback.format_exc()
        if isinstance(exc, subprocess.CalledProcessError) and exc.output:
            raw_error += "\n" + exc.output.decode("utf-8", errors="replace")
        (output / "setup-error.log").write_text(raw_error, encoding="utf-8")
    finally:
        private_policy = None
        if baseline is not None:
            try:
                comparison = input_drift(stage, baseline, output)
                metadata["inputs_unchanged"] = comparison["unchanged"]
                if not comparison["unchanged"]:
                    outcome.update(exit_code=1, status="input_drift")
            except Exception as exc:
                (output / "input-check-error.log").write_text(traceback.format_exc(), encoding="utf-8")
                metadata["input_check_error_type"] = type(exc).__name__
                metadata["inputs_unchanged"] = False
                outcome.update(exit_code=1, status="input_check_error")
        try:
            reports = [json.loads(path.read_text(encoding="utf-8"))
                       for path in sorted((output / "verifier").glob("tests-*.json"))]
            if args.suite == 'frequency_equivalence':
                from ci_frequency_gate import public_summary as equivalence_summary
                summary = equivalence_summary(output / 'physical/frequency-equivalence.json',
                    metadata.get('verifier_outcome', outcome))
            elif args.suite.startswith('procedural_'):
                from ci_procedural_gate import public_summary as procedural_summary
                summary = procedural_summary(output / 'physical/procedural-runner.json',metadata.get('verifier_outcome', outcome))
            else:
                summary = public_summary(args.suite, reports, metadata.get('verifier_outcome', outcome), public_ids)
            write_json(output / 'summary.json', summary)
        except Exception as exc:
            (output / "summary-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            metadata["summary_error_type"] = type(exc).__name__
            outcome.update(exit_code=1, status="summary_error")
        try:
            if fixture_key is not None:
                temp_root = temp_root or Path(os.environ["RUNNER_TEMP"]).resolve()
                metadata["encrypted_evidence"] = encrypt_evidence(root, output, fixture_key, temp_root)
                metadata["evidence_status"] = "encrypted"
            else:
                metadata["evidence_status"] = "unavailable_missing_key"
                outcome.update(exit_code=1, status="setup_error")
        except Exception as exc:
            # Keep detailed packaging errors local; only the type is public.
            (output / "evidence-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            metadata["evidence_error_type"] = type(exc).__name__
            metadata["evidence_status"] = "encryption_failed"
            outcome.update(exit_code=1, status="evidence_error")
        finally:
            fixture_key = None
        metadata.update(outcome)
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "run.json", metadata)
    print(f"CI {metadata['status']}: suite={args.suite}, public_summary={output / 'summary.json'}")
    return metadata["exit_code"]



if __name__ == "__main__":
    raise SystemExit(main())
