"""Observe the fixed verifier without changing its selection or test runner.

The capture pattern is shared with declared-skill-ranks/execution-04.py.
All inputs are frozen before import; raw progress also survives a killed child.
"""
from __future__ import annotations

import argparse
import builtins
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import time
import traceback
import unittest
import zipfile

VERIFIER = "work/reuse-partials/verify_overlay_tests.py"
PREFIX = "ci-native"


def safe_id(value):
    if (not isinstance(value, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value) is None
            or PureWindowsPath(value).is_reserved()):
        raise ValueError("Unsafe CI path identifier")
    return value


def evidence_references(stage, evidence_id):
    relative = "data/verification/ci-runs/" + safe_id(evidence_id)
    destination = stage / relative
    if not destination.resolve().is_relative_to(stage.resolve()):
        raise ValueError("Evidence reference leaves execution stage")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Evidence ID already exists in execution stage")
    return {
        "evidence_id": evidence_id,
        "metadata_path": relative + "/" + PREFIX + ".json",
        "frozen_inputs": relative + "/" + PREFIX + "-inputs.zip",
        "raw_log": relative + "/" + PREFIX + ".log",
    }


def run(stage, hashes, target, output):
    physical_open, physical_builtin_open = io.open, builtins.open
    stage, output = stage.resolve(), output.resolve()
    if output.is_relative_to(stage):
        raise ValueError("Physical evidence and scratch must be outside the input stage")
    if "PTK_FIXTURE_KEY" in os.environ:
        raise ValueError("Native capture must not inherit the fixture key")
    references = evidence_references(stage, output.name)
    physical = output / "physical"
    physical.mkdir(parents=True, exist_ok=False)
    record = output / "verifier"
    record.mkdir(exist_ok=False)

    def physical_bytes(path):
        with physical_open(path, "rb") as stream:
            return stream.read()

    def digest(path):
        return hashlib.sha256(physical_bytes(path)).hexdigest()

    def write_json(path, value):
        with physical_open(path, "x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

    before = {}
    with zipfile.ZipFile(physical / (PREFIX + "-inputs.zip"), "x",
                         compression=zipfile.ZIP_DEFLATED) as archive:
        for name, expected in sorted(hashes.items()):
            path = stage / name
            if path.is_symlink() or not path.resolve().is_relative_to(stage):
                raise ValueError("Physical input leaves stage")
            body = physical_bytes(path)
            actual = hashlib.sha256(body).hexdigest()
            if actual != expected:
                raise ValueError("Stage differs from authenticated inputs")
            before[str(path.resolve())] = actual
            archive.writestr("stage/" + path.relative_to(stage).as_posix(), body)
        if not before:
            raise ValueError("Physical capture requires declared inputs")
        archive.writestr("physical-sha256.json", json.dumps(before, indent=2))

    selected = (stage / target).resolve()
    if str(selected) not in before or not selected.is_relative_to(stage):
        raise ValueError("Verifier target must be a captured stage input")

    gate = None
    procedural = procedural_capture = procedural_report = None
    procedural_actual = []
    if selected.suffix == '.json':
        value = json.loads(physical_bytes(selected))
        if value.get('execution_kind') == 'frequency_equivalence':
            import ci_frequency_gate as FREQUENCY_GATE
            gate = FREQUENCY_GATE.packet(value)
            harness = str((stage / FREQUENCY_GATE.HARNESS).resolve())
            if harness not in before:raise ValueError('Equivalence harness was not captured before import')
        elif value.get('execution_kind') == 'procedural_runner':
            helper = (stage / 'tools/ci_procedural_gate.py').resolve()
            if str(helper) not in before:raise ValueError('Procedural adapter was not captured')
            helper_spec=importlib.util.spec_from_file_location('ci_procedural_gate',helper)
            PROCEDURAL=importlib.util.module_from_spec(helper_spec);sys.modules[helper_spec.name]=PROCEDURAL
            helper_spec.loader.exec_module(PROCEDURAL)
            procedural=PROCEDURAL.packet(value)
        elif value.get('execution_kind') is not None:
            raise ValueError('Unknown typed CI execution kind')
    gate_report = None
    mode_origins = {}
    started, clock = datetime.now(timezone.utc).isoformat(), time.monotonic()
    actual, reads, missing, origin_errors = [], {}, [], []; actual_modes = {}
    before_execution, result = {}, None
    events = physical_open(physical / (PREFIX + "-events.jsonl"), "x",
                           encoding="utf-8", newline="\n")

    def event(kind, **value):
        if kind == 'procedural_start':
            if procedural is None or value.get('unit_id') != procedural['unit_id'] or procedural_actual:
                raise ValueError('Unexpected or repeated procedural entry')
            procedural_actual.append(value['unit_id'])
        events.write(json.dumps({"event": kind, **value}, ensure_ascii=False) + "\n")
        events.flush()

    event("capture_ready", execution_stage=str(stage), started_utc=started,
          evidence_references=references,
          runtime_test_data_sha256_before=before)

    def observe_read(file, args, kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        if procedural_capture is not None:procedural_capture.observe_open(file,mode)
        if not isinstance(mode, str) or any(flag in mode for flag in "wax+") or isinstance(file, int):
            return
        try:
            path = Path(file).resolve()
        except (TypeError, ValueError, OSError):
            return
        if not path.is_relative_to(stage) or not path.is_file():
            return
        key = str(path)
        if key not in reads:
            reads[key] = digest(path)
            generated = bool(key not in before and procedural_capture is not None and procedural_capture.generated_read(path,reads[key]))
            if key not in before and not generated:
                missing.append(key)
            event("first_read", file=key, sha256=reads[key], captured_before=key in before, declared_generated_input=generated)

    def tracking_open(file, *args, **kwargs):
        observe_read(file, args, kwargs)
        return physical_builtin_open(file, *args, **kwargs)

    def tracking_io_open(file, *args, **kwargs):
        observe_read(file, args, kwargs)
        return physical_open(file, *args, **kwargs)

    def loaded_origins():
        origins = {}
        for name, module in sorted(sys.modules.items()):
            source = getattr(module, "__file__", None)
            if not source:
                continue
            path = Path(source).resolve()
            # Only interpreter libraries are exempt. Project imports outside the
            # frozen stage must be recorded and rejected, including lazy imports.
            if path.is_relative_to(Path(sys.base_prefix).resolve()) and not path.is_relative_to(stage):
                continue
            if path.suffix not in (".py", ".pyc", ".pyd"):
                continue
            try:
                sha = digest(path)
            except OSError:
                sha = None
            origins[name] = {"file": str(path), "sha256": sha}
        return origins

    def check_origins(origins):
        wrong = [dict(module=name, **row) for name, row in origins.items()
                 if row["file"] not in before or before[row["file"]] != row["sha256"]]
        origin_errors.extend(wrong)
        return not wrong

    original_start, original_run = unittest.TestResult.startTest, unittest.TextTestRunner.run
    diagnostic_methods = {name: getattr(unittest.TestResult, name)
                          for name in ("addFailure", "addError", "addSubTest")}

    def observe_diagnostic(method):
        def observed(self, *args, **kwargs):
            counts = {field: len(getattr(self, field)) for field in ("failures", "errors")}
            value = method(self, *args, **kwargs)
            for field, count in counts.items():
                for test, detail in getattr(self, field)[count:]:
                    event("test_diagnostic", outcome=field, id=test.id(), traceback=detail, mode=getattr(self, "_ci_equivalence_mode", None))
            return value
        return observed

    def start_test(self, test):
        actual.append(test.id())
        mode = getattr(self, "_ci_equivalence_mode", None)
        if mode is not None:actual_modes.setdefault(mode, []).append(test.id())
        event("test_start", id=test.id(), mode=getattr(self, "_ci_equivalence_mode", None))
        return original_start(self, test)

    class Tee:
        def __init__(self, original, durable):
            self.original, self.durable = original, durable

        def write(self, body):
            self.durable.write(body)
            self.durable.flush()
            return self.original.write(body)

        def writeln(self, body=None):
            if body:
                self.write(body)
            self.write("\n")

        def flush(self):
            self.durable.flush()
            return self.original.flush()

        def __getattr__(self, name):
            return getattr(self.original, name)

    def run_suite(self, suite):
        nonlocal before_execution, result
        before_execution = loaded_origins()
        event("before_execution", loaded_module_origins=before_execution)
        if not check_origins(before_execution):
            raise RuntimeError("Loaded module is outside authenticated physical inputs")
        original_stream = self.stream
        with physical_open(physical / (PREFIX + "-partial.log"), "x",
                           encoding="utf-8", newline="\n") as stream:
            self.stream = Tee(original_stream, stream)
            try:
                result = original_run(self, suite)
            finally:
                self.stream = original_stream
        return result

    def before_equivalence_mode(mode):
        nonlocal before_execution
        if mode in mode_origins:raise ValueError('Equivalence mode repeated')
        before_execution = loaded_origins()
        mode_origins[mode] = before_execution
        event('before_execution', mode=mode, loaded_module_origins=before_execution)
        if not check_origins(before_execution):
            raise RuntimeError('Equivalence module is outside authenticated physical inputs')

    unittest.TestResult.startTest, unittest.TextTestRunner.run = start_test, run_suite
    for name, method in diagnostic_methods.items():
        setattr(unittest.TestResult, name, observe_diagnostic(method))
    builtins.open, io.open = tracking_open, tracking_io_open
    code, exception = 1, None
    details, report = {}, None
    try:
        if procedural:
            procedural_capture=PROCEDURAL.Capture(stage,procedural,before,physical,event)
            code,procedural_report=PROCEDURAL.execute(stage,procedural,physical/'procedural-runner.json',before_equivalence_mode,capture=procedural_capture)
        else:
            verifier = stage / VERIFIER
            spec = importlib.util.spec_from_file_location("verify_overlay_tests", verifier)
            overlay = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = overlay
            spec.loader.exec_module(overlay)
            sys.argv = [str(verifier), "--auto", target, "--canonical", str(stage),
                        "--stage", str(stage), "--mode", "13" if gate else "15", "--record", str(record)]
            try:
                overlay.main()
            except SystemExit as done:
                code = done.code if isinstance(done.code, int) else 1
            if gate and code == 0:
                collected_reports = list(record.glob('tests-*.json'))
                if len(collected_reports) != 1:raise ValueError('One original collection report required')
                collected = json.loads(physical_bytes(collected_reports[0]))
                if set(collected.get('collected', ())) != set(gate['declared_ids']):
                    raise ValueError('Original verifier collection differs from equivalence allocation')
                if actual:raise ValueError('Collection-only gate unexpectedly executed a test')
                gate_path = physical / 'frequency-equivalence.json'
                code, gate_report = FREQUENCY_GATE.execute(stage, gate, gate_path, before_equivalence_mode)
                if len(actual) != sum(len(rows) for rows in actual_modes.values()):
                    raise ValueError('Unattributed equivalence execution occurred')
                for mode in FREQUENCY_GATE.MODES:
                    if actual_modes.get(mode, []) != gate_report['outcomes'][mode]['started_ids']:
                        raise ValueError('Observed mode executions differ from the equivalence report')
    except BaseException:
        exception = traceback.format_exc()
        print(exception)
    finally:
        builtins.open, io.open = physical_builtin_open, physical_open
        unittest.TestResult.startTest, unittest.TextTestRunner.run = original_start, original_run
        for name, method in diagnostic_methods.items():
            setattr(unittest.TestResult, name, method)
        origins = loaded_origins()
        check_origins(origins)
        after, read_errors = {}, {}
        for path in before:
            try:
                after[path] = digest(Path(path))
            except OSError:
                after[path] = None
                read_errors[path] = traceback.format_exc()
        generated = list(record.glob("tests-*.json"))
        if procedural:
            if procedural_report is None:
                exception=(exception or '')+'\nProcedural report missing.'
            else:
                details={'successful':procedural_report.get('successful') is True,'collected':[],'log_path':str(physical/(PREFIX+'.log'))}
            with physical_open(physical/(PREFIX+'.log'),'xb') as stream:
                for name in ('procedural.stdout.log','procedural.stderr.log'):
                    if (physical/name).is_file():stream.write(physical_bytes(physical/name))
        elif len(generated) == 1:
            report = generated[0]
            details = json.loads(physical_bytes(report))
            log = Path(details["log_path"])
            with physical_open(physical / (PREFIX + ".log"), "xb") as stream:
                stream.write(physical_bytes(log))
        else:
            exception = (exception or "") + "\nExpected exactly one original verifier report."
        gaps = [row for row in origins.values() if before.get(row["file"]) != row["sha256"]]
        if (before != after or missing or origin_errors or exception
                or any(path in before and before[path] != sha for path, sha in reads.items())):
            code = 1
        if procedural_report is not None:
            integrity_ok=(before==after and not missing and not origin_errors and not exception
                          and all(before[path]==sha for path,sha in reads.items() if path in before)
                          and procedural_actual==procedural_report.get('actual_runner_ids'))
            procedural_report['physical_integrity_passed']=integrity_ok
            if not integrity_ok:
                code=1;procedural_report.update(successful=False,status='error',verified_runner_ids=[])
                procedural_report['errors'].append({'type':'PhysicalIntegrityError','message':'Original input/read/origin/entry evidence incomplete'})
                details['successful']=False
            with physical_open(physical/'procedural-runner.json','w',encoding='utf-8',newline='\n') as stream:
                json.dump(procedural_report,stream,ensure_ascii=False,indent=2)
        metadata = {
            "purpose": "Authenticated CI stage; fixed verifier selection and native execution.",
            "clause_delta": 0, "execution_stage": str(stage),
            "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
            "seconds": time.monotonic() - clock,
            "successful": bool(details.get("successful") and code == 0), "exit_code": code,
            "original_cli_report": str(report) if report else None,
            "original_cli_log": details.get("log_path"),
            "test_ids": details.get("collected", []), "actual_test_ids": actual,
            "tests": result.testsRun if result else 0,
            "failure_ids": [test.id() for test, _ in result.failures] if result else [],
            "error_ids": [test.id() for test, _ in result.errors] if result else [],
            "exception": exception, "stable_hashes": before == after,
            "runtime_test_data_sha256_before": before,
            "runtime_test_data_sha256_after": after,
            "loaded_module_origins_before_execution": before_execution,
            "loaded_module_origins": origins,
            "physical_open_saved_before_overlay": True,
            **references,
            "actual_read_paths": sorted(reads), "first_actual_read_sha256": reads,
            "input_paths_missing_pre_execution_capture": missing,
            "complete_pre_input_capture": not missing,
            "loaded_inputs_missing_pre_execution_capture": gaps,
            "complete_loaded_input_capture": not gaps,
            "changed_origin_errors": origin_errors,
            "input_read_errors": read_errors,
            "method_timings": details.get("test_durations", []),
        }
        if gate:
            metadata['execution_kind'] = 'frequency_equivalence_gate'
            metadata['ordinary_test_pass_credit'] = 0
            metadata['equivalence_declared_test_ids'] = metadata['test_ids']
            metadata['equivalence_actual_test_ids'] = metadata['actual_test_ids']
            metadata['test_ids'] = []
            metadata['actual_test_ids'] = []
            metadata['equivalence_report'] = str(physical / 'frequency-equivalence.json')
            metadata['equivalence_report_sha256'] = digest(physical / 'frequency-equivalence.json') if (physical / 'frequency-equivalence.json').exists() else None
            metadata['equivalence_mode_origins'] = mode_origins
            metadata['equivalence_gate'] = FREQUENCY_GATE.public_summary(physical / 'frequency-equivalence.json', {'exit_code': code})
        if procedural:
            metadata.update(execution_kind='procedural_runner_gate',ordinary_test_pass_credit=0,
                procedural_declared_runner_ids=procedural['required_runner_ids'],
                procedural_actual_runner_ids=procedural_actual,
                procedural_verified_runner_ids=procedural_report.get('verified_runner_ids',[]) if procedural_report and code==0 else [],
                procedural_report=str(physical/'procedural-runner.json'),
                procedural_report_sha256=digest(physical/'procedural-runner.json') if procedural_report else None,
                procedural_generated_first_reads=[dict(row,file=key) for key,row in procedural_capture.generated_reads.items()] if procedural_capture else [],
                procedural_nested_method_ids=actual,test_ids=[],actual_test_ids=[],tests=0,failure_ids=[],error_ids=[])
            metadata['purpose']='Original procedural unit; original inputs frozen before entry; only declared generated artifacts captured before first read.'
        write_json(physical / (PREFIX + ".json"), metadata)
        event("finished", exit_code=code, actual_test_ids=actual,
              loaded_module_origins=origins, runtime_test_data_sha256_after=after)
        events.close()
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    hashes = json.loads(args.inputs.read_text(encoding="utf-8"))
    return run(args.stage, hashes, args.target, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
