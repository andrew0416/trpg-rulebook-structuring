"""Restore authenticated private fixtures and record one unchanged verifier run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
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

SUITES = {"common_checks": "tools/test_common_checks.py"}
VERIFIER = "work/reuse-partials/verify_overlay_tests.py"
BUNDLE = ".ci/fixtures.zip.enc"
MANIFEST = ".ci/fixtures-manifest.json"
CI_ENVIRONMENT = (
    "GITHUB_SHA", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
    "GITHUB_EVENT_NAME", "RUNNER_OS", "RUNNER_ARCH", "ImageOS", "ImageVersion",
)


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


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
            destination = root / name
            if not destination.resolve().is_relative_to(root):
                raise ValueError("Fixture path leaves the checkout")
            for candidate in (destination, *destination.parents):
                if candidate == root:
                    break
                if candidate.is_symlink():
                    raise ValueError("Fixture destination contains a symlink")
            if destination.exists() and (
                    not destination.is_file() or destination.stat().st_size != row["size"]
                    or file_hash(destination) != row["sha256"]):
                raise ValueError("Existing fixture differs; refusing to overwrite it")
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
        failed = run_command(
            [sys.executable, "-c", "print('raw failure'); raise SystemExit(7)"],
            root, root / "failed.log",
        )
        assert failed["exit_code"] == 7 and failed["status"] == "fail"
        assert b"raw failure" in (root / "failed.log").read_bytes()
        passed = run_command(
            [sys.executable, "-c", "pass"], root, root / "passed.log",
        )
        assert passed["exit_code"] == 0 and passed["status"] == "pass"
        timed_out = run_command(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            root, root / "timeout.log", timeout=0.05,
        )
        assert timed_out["exit_code"] == 124 and timed_out["status"] == "timeout"
    print("CI adapter self-check passed; no private inputs or game tests used.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=SUITES, default="common_checks")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0

    # Only the decrypt child receives the secret; native tests never inherit it.
    fixture_key = os.environ.pop("PTK_FIXTURE_KEY", None)
    root = args.root.resolve()
    output = root / "output" / "ci" / uuid4().hex
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "suite": args.suite,
        "target": SUITES[args.suite],
        "root": str(root),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "ci": {key: os.environ[key] for key in CI_ENVIRONMENT if key in os.environ},
        "scope": "Public code and authenticated private fixtures; declared suite only. Not canonical publication or clause acceptance evidence.",
        "input_manifest": "input-sha256.json",
    }
    outcome = {"exit_code": 1, "status": "setup_error"}
    try:
        metadata["git_sha"] = git(root, "rev-parse", "HEAD").decode("ascii").strip()
        metadata["tracked_changes"] = bool(
            git(root, "status", "--porcelain", "--untracked-files=no")
        )
        tracked = [name for name in git(root, "ls-files", "-z").decode("utf-8").split("\0") if name]
        hashes = input_hashes(root, tracked)
        for required in (SUITES[args.suite], VERIFIER, BUNDLE, MANIFEST, "tools/ci_fixtures.mjs"):
            if required not in hashes:
                raise ValueError("The suite, fixed verifier, crypto adapter and fixture bundle/manifest must be Git-tracked")
        metadata["fixture_bundle_sha256"] = hashes[BUNDLE]
        metadata["fixture_manifest_sha256"] = hashes[MANIFEST]
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        fixture_rows(manifest, tracked)
        if fixture_key is None:
            raise ValueError("PTK_FIXTURE_KEY is required to authenticate the private fixtures")
        temp_root = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
        with tempfile.TemporaryDirectory(prefix="ptk-fixtures-", dir=temp_root) as directory:
            archive = Path(directory).resolve() / "fixtures.zip"
            if not archive.is_relative_to(temp_root):
                raise ValueError("Fixture temporary directory leaves the selected runner temp")
            decrypt_env = {**os.environ, "PTK_FIXTURE_KEY": fixture_key}
            fixture_key = None
            restored = run_command(
                ["node", str(root / "tools/ci_fixtures.mjs"), "decrypt", str(root / BUNDLE), str(archive)],
                root, output / "fixture-decrypt.log", env=decrypt_env,
            )
            decrypt_env.pop("PTK_FIXTURE_KEY")
            if restored["exit_code"] != 0:
                raise ValueError("Fixture decryption failed; see fixture-decrypt.log")
            metadata["fixture_archive_sha256"] = file_hash(archive)
            hashes.update(restore_fixtures(root, archive, manifest, tracked))
            metadata["fixture_file_count"] = len(manifest["files"])
        write_json(output / "input-sha256.json", hashes)
        command = [
            sys.executable, "-B", "-u", "-X", "utf8", str(root / VERIFIER),
            "--auto", SUITES[args.suite], "--canonical", str(root),
            "--stage", str(root), "--record", str(output / "verifier"),
        ]
        outcome = run_command(command, root, output / "command.log")
    except (OSError, ValueError, subprocess.CalledProcessError, zipfile.BadZipFile):
        (output / "setup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        fixture_key = None
        metadata.update(outcome)
        metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(output / "run.json", metadata)
    print(f"CI {metadata['status']}: suite={args.suite}, evidence={output}")
    log = output / "command.log"
    if log.exists():
        print(log.read_text(encoding="utf-8", errors="replace"))
    return metadata["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())