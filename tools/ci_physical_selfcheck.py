"""Synthetic checks for CI capture; no game imports or private acceptance dependency."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def synthetic_run(project, home, variant="pass", timeout=20):
    stage, output = home / "stage", home / "evidence"
    stage.mkdir(parents=True)
    for name in ("tools/ci_physical.py", "work/reuse-partials/verify_overlay_tests.py"):
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / name, target)
    (stage / "input.txt").write_text("synthetic input", encoding="utf-8")
    packet = stage / "packet.json"
    case = "tools.test_ci_physical_synthetic.Check.test_observable"
    cases = [case]
    if variant == "timeout_failure":
        cases.append(case.replace("test_observable", "test_slow"))
    packet.write_text(json.dumps({"completed": {"synthetic": {"tests": cases}}}), encoding="utf-8")
    body = '''import os
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class Check(unittest.TestCase):
    def test_observable(self):
        self.assertNotIn("PTK_FIXTURE_KEY", os.environ)
        self.assertEqual((ROOT / "input.txt").read_text(encoding="utf-8"), "synthetic input")
'''
    body += {
        "pass": "",
        "failure": '        self.fail("synthetic raw failure")\n',
        "changed": '        (ROOT / "input.txt").write_text("changed", encoding="utf-8")\n',
        "missing": '''        fresh = ROOT / "unlisted.txt"
        fresh.write_text("not captured", encoding="utf-8")
        self.assertEqual(fresh.read_text(encoding="utf-8"), "not captured")
''',
        "wrong_origin": '''        import importlib.util, sys
        outside = ROOT.parent / "outside.py"
        spec = importlib.util.spec_from_file_location("outside_project", outside)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.assertEqual(module.VALUE, 7)
''',
        "timeout": '        import time\n        time.sleep(30)\n',
        "timeout_failure": '''        self.fail("failure before timeout")
    def test_slow(self):
        import time
        time.sleep(30)
''',
    }[variant]
    (stage / "tools/test_ci_physical_synthetic.py").write_text(body, encoding="utf-8")
    (home / "outside.py").write_text("VALUE = 7\n", encoding="utf-8")
    return capture(stage, output, case, timeout)


def capture(stage, output, case, timeout=20):
    output.mkdir(parents=True, exist_ok=False)
    hashes = {path.relative_to(stage).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in stage.rglob("*") if path.is_file()}
    manifest = output / "input-sha256.json"
    manifest.write_text(json.dumps(hashes), encoding="utf-8")
    command = [sys.executable, "-B", "-X", "utf8", str(stage / "tools/ci_physical.py"),
               "--stage", str(stage), "--inputs", str(manifest), "--target", str(stage / "packet.json"),
               "--output", str(output)]
    from ci_validate import run_command
    outcome = run_command(command, stage, output / "command.log", timeout=timeout)
    metadata = output / "physical/ci-native.json"
    return {"stage": stage, "output": output, "outcome": outcome, "case": case,
            "metadata": json.loads(metadata.read_text(encoding="utf-8")) if metadata.exists() else None}



def continuity_runs(project, home):
    stage = home / "stage"
    (stage / "tools").mkdir(parents=True)
    for name in ("tools/ci_physical.py", "work/reuse-partials/verify_overlay_tests.py"):
        destination = stage / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / name, destination)
    cases = ["tools.test_ci_continuity.Check.test_kept",
             "tools.test_ci_continuity.Check.test_repaired"]
    (stage / "tools/test_ci_continuity.py").write_text('''import os
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]

class Check(unittest.TestCase):
    def test_kept(self):
        self.assertNotIn("PTK_FIXTURE_KEY", os.environ)
        self.assertEqual(2 + 2, 4)

    def test_repaired(self):
        self.assertNotIn("PTK_FIXTURE_KEY", os.environ)
        self.assertEqual((ROOT / "repair.txt").read_text(encoding="utf-8"), "fixed")
''', encoding="utf-8")
    packet = stage / "packet.json"
    packet.write_text(json.dumps({"completed": {"synthetic": {"tests": cases}}}), encoding="utf-8")
    (stage / "repair.txt").write_text("broken", encoding="utf-8")
    first = capture(stage, home / "run-first", cases[0])
    (stage / "repair.txt").write_text("fixed", encoding="utf-8")
    packet.write_text(json.dumps({"completed": {"synthetic": {"tests": cases[1:]}}}), encoding="utf-8")
    second = capture(stage, home / "run-second", cases[1])
    return {"stage": stage, "cases": cases, "first": first, "second": second}


def chaining_runs(project, home):
    prefix = "tools.test_ci_chain.Check."
    order = [prefix + name for name in ("test_a", "test_b", "test_c")]
    body = '''import unittest

class Check(unittest.TestCase):
    builds = []
    @classmethod
    def prepare_chained_cases(cls, cases):
        by_name = {case._testMethodName: case for case in cases}
        if not {"test_a", "test_b", "test_c"} <= by_name.keys():
            return None
        context = {}
        ordered = [by_name[name] for name in ("test_a", "test_b", "test_c")]
        for case in ordered:
            case.context = context
        return ordered  # HOOK_RESULT

    def build_o(self):
        self.builds.append("O")
        return {"phase": "O"}

    def build_o_a(self):
        self.builds.append("O_A")
        return {"phase": "A"}

    def build_o_ab(self):
        self.builds.append("O_AB")
        return {"phase": "B"}

    def test_a(self):
        state = self.build_o()
        self.assertEqual(state["phase"], "O")
        state["phase"] = "A"
        self.assertTrue(True)  # FIRST_STAGE
        if hasattr(self, "context"):
            self.context["state"] = state
            self.context["object_id"] = id(state)

    def test_b(self):
        state = self.context["state"] if hasattr(self, "context") else self.build_o_a()
        self.assertEqual(state["phase"], "A")
        if hasattr(self, "context"):
            self.assertEqual(id(state), self.context["object_id"])
            self.assertEqual(self.builds, ["O"])
        else:
            self.assertEqual(self.builds, ["O_A"])
        state["phase"] = "B"

    def test_c(self):
        state = self.context["state"] if hasattr(self, "context") else self.build_o_ab()
        self.assertEqual(state["phase"], "B")
        if hasattr(self, "context"):
            self.assertEqual(id(state), self.context["object_id"])
            self.assertEqual(self.builds, ["O"])
        else:
            self.assertEqual(self.builds, ["O_AB"])
        state["phase"] = "C"
'''
    runs = {}
    for mode in ("whole", "only_b", "only_c", "failed_a", "omitted_case"):
        stage = home / mode / "stage"
        (stage / "tools").mkdir(parents=True)
        for name in ("tools/ci_physical.py", "work/reuse-partials/verify_overlay_tests.py"):
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project / name, destination)
        selected = order[1:2] if mode == "only_b" else order[2:] if mode == "only_c" else order[::-1]
        code = body
        if mode == "failed_a":
            code = code.replace("self.assertTrue(True)  # FIRST_STAGE", "self.fail('upstream stage failed')")
        if mode == "omitted_case":
            code = code.replace("return ordered  # HOOK_RESULT", "return ordered[:-1]")
        (stage / "tools/test_ci_chain.py").write_text(code, encoding="utf-8")
        (stage / "packet.json").write_text(json.dumps({"completed": {"chain": {"tests": selected}}}), encoding="utf-8")
        run = runs[mode] = capture(stage, home / mode / "evidence", selected[0])
        meta = run["metadata"]
        assert meta is not None and meta["stable_hashes"] and meta["complete_pre_input_capture"]
        details = json.loads(Path(meta["original_cli_report"]).read_text(encoding="utf-8"))
        if mode == "omitted_case":
            assert meta["actual_test_ids"] == [] and meta["tests"] == 0
            assert details["discovery_errors"] and run["outcome"]["exit_code"] != 0
            continue
        expected = selected if mode in ("only_b", "only_c") else order
        assert meta["test_ids"] == meta["actual_test_ids"] == expected
        assert details["selected_case_ids"] == selected
        assert bool(details["chained_cases"]) == (mode not in ("only_b", "only_c"))
        assert meta["tests"] == len(expected)
        assert [row["id"] for row in meta["method_timings"]] == expected
        if mode == "failed_a":
            assert meta["failure_ids"] == order[:1] and meta["error_ids"] == order[1:]
            assert run["outcome"]["exit_code"] != 0
        else:
            assert meta["successful"] and run["outcome"]["exit_code"] == 0
    return runs


def engine_namespace_runs(project, home):
    """Exercise the shared loader using only generated engine/test modules."""
    runs = {}
    for variant in ('api_first', 'tests_first', 'inputs_first',
                    'sparse_fallback', 'sparse_override', 'missing'):
        run_home = home / variant
        stage = run_home / 'stage'
        canonical = run_home / 'canonical' if variant.startswith('sparse_') else stage
        for root in dict.fromkeys((stage, canonical)):
            (root / 'engine').mkdir(parents=True)
            (root / 'tools').mkdir()
        verifier = stage / 'work/reuse-partials/verify_overlay_tests.py'
        verifier.parent.mkdir(parents=True)
        shutil.copyfile(project / 'work/reuse-partials/verify_overlay_tests.py', verifier)
        api_body = 'class Rules: pass\nclass Engine: pass\nclass Combatant: pass\nORIGIN = '
        (canonical / 'engine/engine.py').write_text(api_body + repr('canonical') + '\n', encoding='utf-8')
        (canonical / 'engine/root_inputs.py').write_text("ORIGIN = 'canonical'\n", encoding='utf-8')
        expected_api = expected_inputs = 'canonical'
        if variant == 'sparse_fallback':
            (stage / 'engine/root_inputs.py').write_text("ORIGIN = 'stage'\n", encoding='utf-8')
            expected_inputs = 'stage'
        elif variant == 'sparse_override':
            (stage / 'engine/engine.py').write_text(api_body + repr('stage') + '\n', encoding='utf-8')
            expected_api = 'stage'
        source = stage if expected_api == 'stage' else canonical
        modules = [('tools.test_ci_api', 'Check'),
                   ('engine.test_playthrough', 'PlaythroughTests'),
                   ('engine.test_maintenance', 'MaintenanceTests'),
                   ('tools.test_root_inputs_independent', 'Independent')]
        for module, cls in modules:
            # The root-input consumer deliberately imports its helper first.
            imports = ('from engine import root_inputs\nfrom engine import Rules, Engine, Combatant\n'
                       if cls == 'Independent' else
                       'from engine import Rules, Engine, Combatant\nfrom engine import root_inputs\n')
            body = 'import unittest\n' + imports + f'''
class {cls}(unittest.TestCase):
    def test_identity(self):
        import engine
        self.assertIs(Rules, engine.Rules)
        self.assertIs(Engine, engine.Engine)
        self.assertIs(Combatant, engine.Combatant)
        self.assertIs(root_inputs, engine.root_inputs)
        self.assertEqual(engine.ORIGIN, {expected_api!r})
        self.assertEqual(root_inputs.ORIGIN, {expected_inputs!r})
        self.assertEqual(engine.__file__, {str(source / 'engine/engine.py')!r})
'''
            # Cover a staged qualified module as well as canonical fallbacks.
            root = stage if variant.startswith('sparse_') and cls == 'PlaythroughTests' else canonical
            (root.joinpath(*module.split('.')).with_suffix('.py')).write_text(body, encoding='utf-8')
        order = [0, 1, 2, 3]
        if variant == 'tests_first':
            order = [1, 2, 0, 3]
        elif variant == 'inputs_first':
            order = [3, 0, 1, 2]
        cases = [modules[index][0] + '.' + modules[index][1] + '.test_identity' for index in order]
        if variant == 'missing':
            cases = ['engine.test_absent.Check.test_one', 'engine.test_absent.Check.test_two']
        packet = stage / 'packet.json'
        packet.write_text(json.dumps({'completed': {'synthetic': {'tests': cases}}}), encoding='utf-8')
        record = run_home / 'record'
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                           TEMP=str(run_home), TMP=str(run_home), TMPDIR=str(run_home))
        outcome = subprocess.run(
            [sys.executable, '-B', '-X', 'utf8', str(verifier), '--auto', str(packet),
             '--stage', str(stage), '--canonical', str(canonical), '--record', str(record)],
            cwd=stage, env=environment, capture_output=True, text=True, encoding='utf-8', timeout=20)
        reports = list(record.glob('*.json'))
        assert len(reports) == 1, (variant, outcome.stdout, outcome.stderr)
        details = json.loads(reports[0].read_text(encoding='utf-8'))
        assert details['requested'] == cases
        if variant == 'missing':
            assert outcome.returncode != 0 and not details['successful']
            assert details['tests_run'] == 0 and len(details['collected']) == 2
            assert len(set(details['collected'])) == 1
            assert any('duplicate test IDs' in error for error in details['discovery_errors'])
        else:
            assert outcome.returncode == 0, (variant, details, outcome.stdout, outcome.stderr)
            assert details['successful'] and not details['discovery_errors']
            assert details['selected_case_ids'] == details['collected'] == cases
            assert details['tests_run'] == len(cases) and not details['skipped']
        runs[variant] = details
    return runs


def self_check(project):
    assert "PTK_FIXTURE_KEY" not in os.environ
    # The unchanged verifier rejects C: stages. Tests only copy its source and
    # one generated synthetic test into a fresh D: directory.
    with tempfile.TemporaryDirectory(prefix="ci-physical-self-check-", dir=project.parent) as directory:
        home = Path(directory).resolve()
        runs = {}
        for variant in ("pass", "failure", "changed", "missing", "wrong_origin", "timeout", "timeout_failure"):
            run = runs[variant] = synthetic_run(
                project, home / variant, variant, timeout=1.5 if variant.startswith("timeout") else 20)
            meta = run["metadata"]
            physical = run["output"] / "physical"
            with zipfile.ZipFile(physical / "ci-native-inputs.zip") as archive:
                before = json.loads(archive.read("physical-sha256.json"))
                assert len(archive.namelist()) == len(before) + 1
                for path, digest in before.items():
                    name = "stage/" + Path(path).relative_to(run["stage"]).as_posix()
                    assert hashlib.sha256(archive.read(name)).hexdigest() == digest
            if variant.startswith("timeout"):
                assert run["outcome"]["status"] == "timeout" and meta is None
                assert b"test_observable" in (physical / "ci-native-partial.log").read_bytes()
                events = [json.loads(line) for line in
                          (physical / "ci-native-events.jsonl").read_text(encoding="utf-8").splitlines()]
                assert any(row["event"] == "test_start" for row in events)
                assert not any(row["event"] == "finished" for row in events)
                if variant == "timeout_failure":
                    assert any(row["event"] == "test_diagnostic" and
                               "failure before timeout" in row["traceback"] for row in events)
                    assert b"FAIL\n" in (physical / "ci-native-partial.log").read_bytes()
                continue
            assert meta["actual_test_ids"] == [run["case"]] and meta["tests"] == 1
            assert meta["physical_open_saved_before_overlay"]
            assert str(run["stage"] / "input.txt") in meta["first_actual_read_sha256"]
            assert meta["loaded_module_origins_before_execution"]
            assert meta["loaded_module_origins"]
            original = Path(meta["original_cli_log"])
            assert original.read_bytes() == (physical / "ci-native.log").read_bytes()
            assert original.read_text(encoding="utf-8") == (physical / "ci-native-partial.log").read_text(encoding="utf-8")
            assert (run["outcome"]["exit_code"] == 0) == (variant == "pass")
            if variant == "pass":
                assert meta["successful"] and meta["stable_hashes"]
                assert meta["complete_pre_input_capture"] and meta["complete_loaded_input_capture"]
                assert meta["runtime_test_data_sha256_before"] == meta["runtime_test_data_sha256_after"]
            elif variant == "failure":
                assert meta["failure_ids"] == [run["case"]]
                assert b"synthetic raw failure" in original.read_bytes()
            elif variant == "changed":
                assert not meta["stable_hashes"]
            elif variant == "missing":
                assert not meta["complete_pre_input_capture"]
            elif variant == "wrong_origin":
                assert any(row["module"] == "outside_project" for row in meta["changed_origin_errors"])
        engine_namespace_runs(project, home / "engine-namespace")
        chaining_runs(project, home / "chaining")
        continuity = continuity_runs(project, home / "continuity")
        first, second = continuity["first"], continuity["second"]
        assert first["outcome"]["exit_code"] == 1 and second["outcome"]["exit_code"] == 0
        assert first["metadata"]["actual_test_ids"] == continuity["cases"]
        assert first["metadata"]["failure_ids"] == continuity["cases"][1:]
        assert second["metadata"]["actual_test_ids"] == continuity["cases"][1:]
        assert first["metadata"]["execution_stage"] == second["metadata"]["execution_stage"]
        assert first["metadata"]["finished_utc"] <= second["metadata"]["started_utc"]
        assert first["metadata"]["raw_log"] != second["metadata"]["raw_log"]
        assert first["metadata"]["frozen_inputs"] != second["metadata"]["frozen_inputs"]
        from ci_physical import evidence_references
        for unsafe in ("../escape", "/absolute", "C:escape", "bad/name", "bad\\name",
                       ".", "", "CON", "id.", "id ", None, 42):
            try:
                evidence_references(continuity["stage"], unsafe)
            except ValueError:
                pass
            else:
                raise AssertionError("Unsafe evidence ID accepted")
        original = second["output"] / "physical/ci-native.json"
        destination = continuity["stage"] / second["metadata"]["metadata_path"]
        destination.parent.mkdir(parents=True)
        shutil.copyfile(original, destination)
        saved = destination.read_bytes()
        duplicate = capture(continuity["stage"], home / "duplicate/run-second", continuity["cases"][1])
        assert duplicate["outcome"]["exit_code"] != 0 and duplicate["metadata"] is None
        assert destination.read_bytes() == saved
    print("CI physical self-check passed: synthetic boundaries, engine namespace/order, stage builders/chaining and same-stage failure/subset continuity.")


if __name__ == "__main__":
    os.environ.pop("PTK_FIXTURE_KEY", None)
    self_check(Path(__file__).resolve().parents[1])
