"""Run unittest modules/classes/methods with an optional sparse code overlay.

The integration stage contains a full Python-code overlay but intentionally
does not duplicate hundreds of megabytes of canonical data.  Test modules
normally derive their Rules root from ``__file__``; redirect those fixture
roots after import so the code under test stays staged while rule data remains
canonical.
"""

from __future__ import annotations

import argparse
import builtins
from collections import Counter
from datetime import datetime, timezone
from enum import IntFlag
from functools import partial
from hashlib import sha256
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import time
import traceback
import unittest
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile


STAGE = Path(__file__).resolve().parent
CANONICAL = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
ROOT_NAMES = ("ROOT", "PROJECT_ROOT", "REPO_ROOT")


_OPEN = builtins.open
_IO_OPEN = io.open
_EXISTS = os.path.exists
_ISFILE = os.path.isfile
_PATH_EXISTS = Path.exists
_PATH_IS_FILE = Path.is_file


class WorkflowState(IntFlag):
    PACKET = 1
    REPORT = 2
    PARTIAL = 4
    FAILURE = 8
    SCOPE_KNOWN = 16
    ROOTS_KNOWN = 32
    NEEDS_AGENT = 64


class WorkflowMode(IntFlag):
    ALLOCATE = 1
    RUN = 2
    SAVE = 4
    BRIEF = 8


def native_platform():
    if hasattr(sys, "getwindowsversion"):
        return "Windows-" + ".".join(map(str, sys.getwindowsversion()[:3]))
    if hasattr(os, "uname"):
        system = os.uname()
        return f"{system.sysname}-{system.release}-{system.machine}"
    return sys.platform


def read_object(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError(f'expected a JSON object: {path}')
    return value


def test_module(value, stage, canonical, *, preserve_selector=False):
    """Normalize a test reference; only direct inputs retain class/method tails.

    Saved reports and navigation still expand to whole declared modules.
    Unknown direct selectors reach unittest discovery, never a module fallback.
    """
    path = Path(value)
    if path.is_absolute():
        resolved = path.resolve()
        for root in (stage, canonical):
            if resolved.is_relative_to(root):
                value = resolved.relative_to(root).as_posix()
                break
        else:
            raise ValueError(f'test path leaves the selected roots: {value}')
    parts = value.replace('\\', '.').replace('/', '.').split('.')
    index = next((i for i, part in enumerate(parts) if part.startswith('test_')), None)
    # Only the module position has a file extension; selector tails are exact.
    if index is not None and parts[index + 1:] == ['py']:
        parts.pop()
    module_parts = parts[:index + 1] if preserve_selector and index is not None else parts
    if not all(part.replace('-', '_').isidentifier() for part in module_parts):
        raise ValueError(f'not a test reference: {value}')
    if index is None:
        raise ValueError(f'no declared test module: {value}')
    selector = parts[index + 1:] if preserve_selector else []
    parts = parts[:index + 1]
    if len(parts) == 1 and not any((root / (parts[0] + '.py')).is_file()
                                  for root in (stage, canonical)):
        parts.insert(0, 'tools')
    return '.'.join([*parts, *selector])


def workflow_plan(targets, *, stage=None, canonical=None):
    """Route observable evidence to existing runners, not to another LLM.

    Historical success/frequency never authorizes omitting a declared test.
    A report restores *current full packet declarations*, including omissions.
    A navigation target selects whole declared modules, never a lookup sample.
    A direct test reference keeps its explicitly selected module/class/method.
    """
    started = time.perf_counter()
    canonical_fixed = canonical is not None
    canonical = Path(canonical or CANONICAL).resolve()
    stage = Path(stage).resolve() if stage else None
    state = WorkflowState(0)
    packets, reports, modules, required_ids, reasons = [], [], [], [], []
    navigation = notes = None
    for target in targets:
        path = Path(target)
        if path.suffix.lower() == '.json':
            path = path.resolve()
            data = read_object(path)
            if 'completed' in data:
                state |= WorkflowState.PACKET
                packets.append(path)
                reasons.append('current_packet_declarations')
                continue
            if data.get('version') != 1 or data.get('kind') not in (
                    'run', 'collection', 'discovery_error'):
                raise ValueError(f'unsupported workflow input: {path}')
            state |= WorkflowState.REPORT
            reports.append(path)
            saved_stage, saved_canonical = Path(data['stage']), Path(data['canonical'])
            if not saved_stage.is_absolute() or not saved_canonical.is_absolute():
                raise ValueError('saved roots must be absolute')
            saved_stage, saved_canonical = saved_stage.resolve(), saved_canonical.resolve()
            if (stage is not None and stage != saved_stage
                    or (canonical_fixed and canonical != saved_canonical)):
                raise ValueError('workflow roots differ from the saved report')
            stage, canonical, canonical_fixed = saved_stage, saved_canonical, True
            if data.get('successful') is False:
                state |= WorkflowState.FAILURE
            partial = (data.get('allocation_scope') in ('partial', 'retry')
                       or data.get('origin_allocation_scope') == 'partial'
                       or data.get('omitted_allocation') or data.get('omitted_case_ids'))
            if partial:
                state |= WorkflowState.PARTIAL
            entries = (data.get('origin_allocation') or data.get('allocation') or [])
            entries = [*entries, *data.get('omitted_allocation', [])]
            if entries:
                for entry in entries:
                    packet = Path(entry['packet'])
                    if not packet.is_absolute():
                        raise ValueError('saved packet paths must be absolute')
                    packets.append(packet.resolve())
                    required_ids.extend(entry['tests'])
                required_ids.extend(data.get('omitted_case_ids', []))
                reasons.append('restore_current_full_packets_not_old_pass_or_retry_subset')
            elif partial:
                raise ValueError('partial/retry report has no full packet provenance; scope needs review')
            else:
                requested = data.get('requested')
                collected = data.get('collected')
                if (not isinstance(requested, list) or not requested
                        or not isinstance(collected, list) or not collected):
                    raise ValueError('report has no declared or collected test scope')
                modules.extend(test_module(name, stage, canonical) for name in requested)
                required_ids.extend(collected)
                reasons.append('expand_saved_selection_to_current_whole_modules')
            continue
        active_stage = stage or canonical
        try:
            modules.append(test_module(target, active_stage, canonical, preserve_selector=True))
            reasons.append('explicit_current_test_reference')
            continue
        except ValueError:
            pass
        if navigation is None:
            spec = importlib.util.spec_from_file_location(
                '_workflow_navigation', canonical / 'tools/reuse_navigation.py')
            navigation = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(navigation)
            notes = navigation.load(canonical)
        uid, focus = navigation.resolve(notes, target)
        if focus == 'clause':
            raise ValueError('clause-level acceptance requires explicit packet scope, not related samples')
        note = notes[uid]
        declared = [row['file'] for row in note['tests']]
        for row in note['tests']:
            module = test_module(row['file'], active_stage, canonical)
            required_ids.extend(module + '.' + case for case in row.get('tests', []))
        declared.extend(note['contract'].get('required_test_modules') or [])
        for check in note['checks']:
            if check.get('suite'):
                declared.append(check['suite'])
            declared.extend(check.get('cases', []))
            required_ids.extend(check.get('cases', []))
        if not declared:
            raise ValueError(f'{target}: no declared test scope; agent must choose acceptance checks')
        modules.extend(test_module(name, active_stage, canonical) for name in declared)
        reasons.append('whole_contract_modules:' + uid)
    if packets and modules:
        raise ValueError('do not mix packet obligations and module scopes in one auto request')
    packets = list(dict.fromkeys(packets))
    if stage is None:
        if len(packets) > 1:
            raise ValueError('multiple packet overlays require an explicit integration --stage')
        stage = packets[0].parent if packets else canonical
    if os.name == 'nt' and any(root.drive.casefold() == 'c:' for root in (stage, canonical)):
        raise ValueError('C: workspaces are disabled for this workflow; use D:')
    if not stage.is_dir() or not canonical.is_dir():
        raise ValueError('stage and canonical must be existing directories')
    if packets:
        # Validate now, before any imports/fixtures. The runner reuses this contract.
        for path in packets:
            groups = read_object(path)['completed']
            if not isinstance(groups, dict) or not groups:
                raise ValueError(f'no completed test groups: {path}')
            for row in groups.values():
                if (not isinstance(row.get('tests'), list) or not row['tests']
                        or not all(isinstance(case, str) and case.strip() for case in row['tests'])):
                    raise ValueError(f'invalid packet test declarations: {path}')
        state |= WorkflowState.PACKET
    if not packets and not modules:
        raise ValueError('no declared workflow scope')
    if not all(isinstance(name, str) and name for name in required_ids):
        raise ValueError('invalid recorded test IDs')
    state |= WorkflowState.SCOPE_KNOWN | WorkflowState.ROOTS_KNOWN
    return dict(policy_version=1, route='packet_full' if packets else 'declared_modules',
                state=int(state), state_names=[flag.name for flag in WorkflowState if state & flag],
                targets=list(targets), stage=str(stage), canonical=str(canonical),
                packets=[str(path) for path in packets], modules=list(dict.fromkeys(modules)),
                required_ids=list(dict.fromkeys(required_ids)),
                decisions=list(dict.fromkeys(reasons)), agent_required=False,
                selection_seconds=time.perf_counter() - started,
                default_record=str(reports[0].parent if reports else
                                   canonical / 'work/reuse-partials/workflow-maintenance/general-workflow'),
                coverage_limit='Declared scope only; not complete change-impact or clause acceptance proof.')


def workflow_stats(paths):
    """Bounded replay of explicit reports; no hidden-reasoning time estimates."""
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError('duplicate reports would inflate statistics')
    routes, outcomes, states, policy_outcomes, rows = Counter(), Counter(), Counter(), Counter(), []
    for path in resolved:
        data = read_object(path)
        if data.get('version') != 1 or data.get('kind') not in (
                'run', 'collection', 'discovery_error', 'routing_error'):
            raise ValueError(f'not an execution/collection report: {path}')
        outcomes[data['kind'] + ('_pass' if data.get('successful') else '_fail')] += 1
        policy_outcomes[data.get('workflow', {}).get('next_action', 'unrecorded')] += 1
        try:
            if data['kind'] == 'routing_error':
                raise ValueError(data['workflow']['reason'])
            plan = workflow_plan([str(path)], canonical=data['canonical'])
            route, flags, reason = plan['route'], plan['state_names'], None
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            route, flags, reason = 'needs_agent', ['NEEDS_AGENT'], str(exc)
        routes[route] += 1
        states.update(flags)
        rows.append(dict(report=str(path), route=route, reason=reason))
    return dict(kind='workflow_statistics', reports=len(rows), routes=dict(routes),
                historical_outcomes=dict(outcomes), observed_states=dict(states), rows=rows,
                recorded_policy_outcomes=dict(policy_outcomes),
                model_calls_measured=None, reasoning_time_measured=None,
                meaning='Current routing replay only; no test imports/runs, accuracy or call-saving estimate.')


def record_routing_error(args, mode, reason):
    """Retain failed routing too, otherwise statistics hide the expensive gaps."""
    result = dict(route='needs_agent', state=int(WorkflowState.NEEDS_AGENT),
                  agent_required=True, reason=reason, tests_run=0)
    if mode & WorkflowMode.SAVE:
        output = (args.record or (args.canonical or CANONICAL) /
                  'work/reuse-partials/workflow-maintenance/general-workflow').resolve()
        if os.name == 'nt' and output.drive.casefold() == 'c:':
            raise ValueError('C: evidence outputs are disabled; use D:')
        output.mkdir(parents=True, exist_ok=True)
        report = output / ('tests-' + uuid4().hex + '.json')
        log = report.with_suffix('.log')
        policy = dict(result, policy_version=1, targets=args.auto, mode=mode,
                      state_names=['NEEDS_AGENT'], next_action='choose_scope')
        details = dict(version=1, kind='routing_error', successful=False, tests_run=0,
                       collected=[], retry_ids=[], elapsed_seconds=0.0,
                       workflow=policy, log_path=str(log))
        with log.open('x', encoding='utf-8') as stream:
            stream.write('Routing needs review; no tests imported or executed.\n' + reason + '\n')
        with report.open('x', encoding='utf-8') as stream:
            json.dump(details, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        result.update(report=str(report), full_log=str(log))
    return result


class FixtureRootLoader(importlib.machinery.SourceFileLoader):
    def exec_module(self, module):
        api = module.__name__ == 'engine'
        if api:
            existing = sys.modules.get('engine.engine')
            if existing is not None and existing is not module:
                raise ImportError('Conflicting engine.engine module identity')
            # Qualified imports must reuse this same API before helper imports run.
            sys.modules['engine.engine'] = module
            module.engine = module
        try:
            super().exec_module(module)
            if api and (sys.modules.get('engine.engine') is not module or module.engine is not module):
                raise ImportError('Engine API alias changed during initialization')
        except BaseException:
            if api and sys.modules.get('engine.engine') is module:
                del sys.modules['engine.engine']
            raise
        # Test bodies also import staged fixture modules after initial discovery.
        redirect_fixture_roots((module,))


class StageOverlayFinder(importlib.abc.MetaPathFinder):
    """Load changed engine and tools modules from a sparse candidate first.

    The canonical ``engine.py`` prepends its own directory to ``sys.path``.
    A path-only overlay would therefore silently switch later imports back to
    canonical modules.  The finder keeps candidate modules authoritative even
    when an unchanged canonical module adjusts the path during import.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'engine':
            # Keep the bare engine.py API and its qualified test/helper imports.
            locations = [str(root / 'engine') for root in dict.fromkeys((STAGE, CANONICAL))]
            for root in dict.fromkeys((STAGE, CANONICAL)):
                source = root / 'engine' / 'engine.py'
                if _ISFILE(source):
                    return importlib.util.spec_from_file_location(
                        fullname, source, loader=FixtureRootLoader(fullname, str(source)),
                        submodule_search_locations=locations)
        if STAGE == CANONICAL:
            return None
        if "." in fullname:
            source = STAGE.joinpath(*fullname.split('.')).with_suffix('.py')
            if _ISFILE(source):
                return importlib.util.spec_from_file_location(
                    fullname, source, loader=FixtureRootLoader(fullname, str(source)))
            package = source.with_suffix('') / '__init__.py'
            if _ISFILE(package):
                return importlib.util.spec_from_file_location(
                    fullname, package, loader=FixtureRootLoader(fullname, str(package)),
                    submodule_search_locations=[str(package.parent),
                                                str(CANONICAL.joinpath(*fullname.split('.')))])
            return None
        for parent in (STAGE / "engine", STAGE, STAGE / "tools"):
            source = parent / f"{fullname}.py"
            if _ISFILE(source):
                return importlib.util.spec_from_file_location(
                    fullname, source, loader=FixtureRootLoader(fullname, str(source)))
        package = STAGE / fullname / '__init__.py'
        if _ISFILE(package):
            return importlib.util.spec_from_file_location(
                fullname, package, loader=FixtureRootLoader(fullname, str(package)),
                submodule_search_locations=[str(package.parent), str(CANONICAL / fullname)])
        return None


def _relative_to(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def overlay_read_path(value, *, roots=None):
    """Choose a staged file first and otherwise fall back to canonical data.

    Candidate modules run from ``STAGE`` while their ``Rules`` objects point at
    ``CANONICAL``.  Both directions therefore need a read-only overlay: a new
    staged policy must shadow the canonical path, and unchanged data missing
    from the sparse stage must resolve back to canonical.
    """
    if isinstance(value, int):
        return value
    try:
        path = Path(value)
        resolved = path.resolve(strict=False)
        stage_root, canonical_root = roots if roots is not None else (
            STAGE.resolve(strict=False), CANONICAL.resolve(strict=False))
    except (TypeError, OSError, ValueError):
        return value
    relative = _relative_to(resolved, canonical_root)
    if relative is not None:
        staged = STAGE / relative
        return staged if _EXISTS(staged) else value
    relative = _relative_to(resolved, stage_root)
    if relative is not None and not _EXISTS(path):
        canonical = CANONICAL / relative
        return canonical if _EXISTS(canonical) else value
    return value


def _read_only_mode(args, kwargs) -> bool:
    mode = args[0] if args else kwargs.get("mode", "r")
    return isinstance(mode, str) and not any(flag in mode for flag in "wax+")


def install_filesystem_overlay() -> None:
    # Roots are fixed per CLI run; file resolution/existence stays live.
    read_path = partial(overlay_read_path, roots=(
        STAGE.resolve(strict=False), CANONICAL.resolve(strict=False)))

    def open_overlay(file, *args, **kwargs):
        chosen = read_path(file) if _read_only_mode(args, kwargs) else file
        return _OPEN(chosen, *args, **kwargs)

    def io_open_overlay(file, *args, **kwargs):
        chosen = read_path(file) if _read_only_mode(args, kwargs) else file
        return _IO_OPEN(chosen, *args, **kwargs)

    builtins.open = open_overlay
    io.open = io_open_overlay
    os.path.exists = lambda value: _EXISTS(read_path(value))
    os.path.isfile = lambda value: _ISFILE(read_path(value))
    Path.exists = lambda self: _PATH_EXISTS(Path(read_path(self)))
    Path.is_file = lambda self: _PATH_IS_FILE(Path(read_path(self)))


def module_name(value: str) -> str:
    value = value.removesuffix(".py").replace("/", ".").replace("\\", ".")
    if '.' in value or any(_ISFILE(root / f'{value}.py') or
                           _ISFILE(root / value / '__init__.py')
                           for root in (STAGE, CANONICAL)):
        return value
    return f"tools.{value}"


def redirect_fixture_roots(modules=None) -> None:
    for loaded in tuple(sys.modules.values()) if modules is None else modules:
        if loaded is None:
            continue
        for name in ROOT_NAMES:
            value = getattr(loaded, name, None)
            if not isinstance(value, Path):
                continue
            try:
                value.resolve().relative_to(STAGE)
            except (OSError, ValueError):
                continue
            setattr(loaded, name, CANONICAL)


def test_cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from test_cases(test)
        else:
            yield test


def prepare_chained_suite(suite):
    """Connect opt-in compatible cases without changing case identity or coverage.

    Hooks prepare only empty shared contexts. Real fixtures are constructed by
    the first running case; independently selected cases retain their builders.
    """
    cases = list(test_cases(suite))
    grouped = {}
    for case in cases:
        grouped.setdefault(type(case), []).append(case)
    replacements, chains = {}, []
    for cls, selected in grouped.items():
        hook = getattr(cls, 'prepare_chained_cases', None)
        if hook is None:
            continue
        before = {id(case): case.id() for case in selected}
        if len(before) != len(selected):
            raise ValueError('Chained selection repeats a TestCase instance')
        prepared = hook(tuple(selected))
        if any(case.id() != before[id(case)] for case in selected):
            raise ValueError('Chaining changed a test case identity')
        if prepared is None:
            continue
        prepared = list(prepared)
        if Counter(map(id, prepared)) != Counter(map(id, selected)):
            raise ValueError('Chaining must preserve every selected TestCase instance exactly once')
        replacements[cls] = iter(prepared)
        chains.append({'class': cls.__module__ + '.' + cls.__qualname__,
                       'selected_test_ids': [case.id() for case in selected],
                       'execution_test_ids': [case.id() for case in prepared]})
    if not chains:
        return suite, []
    def ordinary_suites(node):
        if isinstance(node, unittest.TestSuite):
            return type(node) is unittest.TestSuite and all(ordinary_suites(child) for child in node)
        return True
    if not ordinary_suites(suite):
        raise ValueError('Chaining cannot replace a custom TestSuite execution contract')
    ordered = [next(replacements[type(case)]) if type(case) in replacements else case
               for case in cases]
    return unittest.TestSuite(ordered), chains


class ReportingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.failed_parents = set()
        self.test_durations = []

    def startTest(self, test):
        self._case_cpu_started = time.process_time()
        self._case_started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        self.test_durations.append({'id': test.id(),
                                    'seconds': time.perf_counter() - self._case_started,
                                    'process_cpu_seconds': time.process_time() - self._case_cpu_started})
        super().stopTest(test)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.failed_parents.add(test.id())


def retry_ids(result, collected, *, include_unverified=False):
    names = set(result.failed_parents)
    unresolved = result.skipped + result.expectedFailures if include_unverified else []
    for test, _ in result.failures + result.errors + unresolved:
        name = test.id()
        if name in collected:
            names.add(name)
        elif isinstance(getattr(test, 'test_case', None), unittest.TestCase):
            names.add(test.test_case.id())
        elif name.startswith(('setUpClass (', 'tearDownClass (', 'setUpModule (', 'tearDownModule (')):
            owner = name.split(' (', 1)[1].removesuffix(')')
            names.update(case for case in collected if case.startswith(owner + '.'))
    names.update(test.id() for test in result.unexpectedSuccesses)
    return [case for case in collected if case in names]


def packet_allocation(paths, parser):
    allocation = []
    for path in paths:
        try:
            packet = json.loads(path.read_text(encoding='utf-8-sig'))
            groups = packet['completed']
            if not isinstance(groups, dict) or not groups:
                raise ValueError('completed must contain test groups')
            for group, details in groups.items():
                cases = details['tests']
                if not isinstance(cases, list) or not cases or not all(
                        isinstance(case, str) and case.strip() for case in cases):
                    raise ValueError(f'{group}: tests must be a nonempty list of case IDs')
                allocation.append({'packet': str(path.resolve()), 'group': group,
                                   'tests': [module_name(case) for case in cases]})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f'invalid test packet {path}: {exc}')
    return allocation


def brief_summary(details, report_path, log_path, *, include_timing=False):
    """Keep the decision signal in stdout; retain complete evidence on disk."""
    lines = [f"{details['kind']}: {'PASS' if details['successful'] else 'FAIL'}; "
             f"ran={details['tests_run']}; collected={len(details['collected'])}; "
             f"elapsed={details['elapsed_seconds']:.3f}s"]
    if (details.get('allocation_scope') == 'partial'
            or details.get('origin_allocation_scope') == 'partial'):
        lines.append(f"PARTIAL scope: omitted groups={len(details.get('omitted_allocation', []))}, "
                     f"case IDs={len(details.get('omitted_case_ids', []))}; not full packet verification")
    issues = [(row['id'], row['traceback'].strip().splitlines()[-1])
              for key in ('failures', 'errors') for row in details.get(key, [])]
    issues += [(row['id'], 'skipped: ' + row['reason']) for row in details.get('skipped', [])]
    issues += [(name, 'expected failure') for name in details.get('expected_failures', [])]
    issues += [(name, 'unexpected success') for name in details.get('unexpected_successes', [])]
    issues += [('discovery', error.strip().splitlines()[-1])
               for error in details.get('discovery_errors', [])]
    for name, reason in issues[:8]:
        lines.append(f"  {name}: {reason}")
    if len(issues) > 8:
        lines.append(f"  +{len(issues) - 8} more issues in JSON report")
    if details.get('retry_ids'):
        lines.append(f"retry_ids={len(details['retry_ids'])}; exact IDs in JSON report")
    if details.get('repeat_from'):
        lines.append('repeated saved selection; current execution, not reused PASS')
    for row in details.get('expanded_packets', []):
        lines.append('expanded_packet=' + row['packet'])
    if details.get('workflow'):
        policy = details['workflow']
        lines.append(f"workflow={policy['route']}; state={policy['state']}; next={policy['next_action']}")
        lines.append('declared scope only; not complete change-impact coverage')
    lines.extend((f"report={report_path}",
                  f"full_log={log_path if log_path else 'not recorded'}"))
    if include_timing:
        timing = [f'{label}={details[key]:.3f}s' for label, key in (
            ('discovery', 'discovery_seconds'), ('suite', 'suite_seconds'),
            ('outside_methods', 'unattributed_suite_seconds')) if key in details]
        if timing:
            lines.append('timing: ' + '; '.join(timing))
        for row in sorted(details.get('test_durations', []), key=lambda row: -row['seconds'])[:3]:
            lines.append(f"slow_method: {row['seconds']:.3f}s {row['id']}")
    return '\n'.join(lines) + '\n'


def physical_execution(args, parser):
    """Freeze declared inputs, then run this same verifier under physical hooks.

    Input directories are explicit, not inferred change-impact declarations.
    The fresh import is important: its overlay must cache our physical hooks,
    not the unobserved opens cached by the outer CLI during startup.
    """
    clock = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    if (not args.stage or not args.canonical or not args.record
            or args.report or args.log or args.collect_only or args.inspect_report
            or args.workflow_stats or args.quiet
            or (args.auto and args.mode is not None and not args.mode & WorkflowMode.RUN)):
        parser.error('--physical requires explicit --stage, --canonical, --record and a full log run')
    stage, canonical, output = (value.resolve() for value in
                                (args.stage, args.canonical, args.record))
    if not stage.is_dir() or not canonical.is_dir():
        parser.error('physical stage and canonical must be existing directories')
    if os.name == 'nt' and any(path.drive.casefold() == 'c:' for path in
                               (stage, canonical, output)):
        parser.error('C: workspaces/evidence outputs are disabled; use D:')
    if not output.is_relative_to(stage) or output == stage:
        parser.error('physical --record must be a directory below stage')
    physical_spec = args.physical.resolve()
    runner = Path(__file__).resolve()
    try:
        declaration = read_object(physical_spec)
        entries = declaration['inputs']
        if (set(declaration) - {'version', 'inputs'} or declaration.get('version', 1) != 1
                or not isinstance(entries, list) or not entries
                or not all(isinstance(value, str) and value.strip() for value in entries)):
            raise ValueError('expected {"version": 1, "inputs": [file or directory, ...]}')
        paths = {physical_spec, runner}
        # Selection evidence is consumed by the inner CLI, so freeze it too.
        paths.update(value.resolve() for value in (args.candidate, args.failed_from,
                     args.repeat_from) if value is not None)
        paths.update(value.resolve() for value in (args.packets or []))
        paths.update(Path(value).resolve() for value in (args.auto or [])
                     if Path(value).suffix.lower() == '.json')
        for value in entries:
            selected = Path(value)
            if not selected.is_absolute():
                if '..' in selected.parts:
                    raise ValueError('relative physical inputs cannot leave stage')
                selected = stage / selected
            selected = selected.resolve()
            if selected.is_dir():
                if not any(selected.is_relative_to(root) for root in (stage, canonical)):
                    raise ValueError('input directories must be inside stage or canonical')
                if output.is_relative_to(selected) or selected.is_relative_to(output):
                    raise ValueError('input directory overlaps --record; declare narrower input roots')
                for path in selected.rglob('*'):
                    if path.is_file() and path.suffix == '.pyc':
                        raise ValueError('pre-existing bytecode can be read despite -B; move it outside input roots before capture: ' + str(path))
                    if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                        resolved = path.resolve()
                        if not resolved.is_relative_to(selected):
                            raise ValueError('input directory contains an escaping symlink: ' + str(path))
                        paths.add(resolved)
            elif selected.is_file():
                paths.add(selected)
            else:
                raise ValueError('physical input does not exist: ' + str(selected))
        if any(not path.is_file() for path in paths):
            raise ValueError('selection evidence must be existing files')
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error('physical inputs: ' + str(exc))

    physical_open, physical_builtin = io.open, builtins.open
    originals = (os.path.exists, os.path.isfile, Path.exists, Path.is_file)
    runtime_roots = {Path(value).resolve() for value in (sys.prefix, sys.base_prefix)}
    physical_reading = 0

    def physical_bytes(path):
        nonlocal physical_reading
        physical_reading += 1
        try:
            with physical_open(path, 'rb') as stream:
                return stream.read()
        finally:
            physical_reading -= 1

    def digest(path):
        try:
            return sha256(physical_bytes(path)).hexdigest()
        except OSError:
            return None

    def archive_name(path):
        for root, prefix in ((stage, 'stage/'), (canonical, 'canonical/')):
            if path.is_relative_to(root):
                return prefix + path.relative_to(root).as_posix()
        return 'tooling/' + path.name

    names = [archive_name(path) for path in paths]
    if len(names) != len(set(names)):
        parser.error('physical input paths collide in ZIP tooling names')
    record = output / ('physical-' + uuid4().hex)
    record.mkdir(parents=True, exist_ok=False)
    for name in ('TEMP', 'TMP', 'TMPDIR'):
        os.environ[name] = str(record)
    sys.dont_write_bytecode = True
    import tempfile
    tempfile.tempdir = str(record)
    archive_path = record / 'inputs.zip'
    before = {}
    # Seal the ZIP before any test import; unknown late reads never extend it.
    with ZipFile(archive_path, 'x', compression=ZIP_DEFLATED) as archive:
        for path in sorted(paths, key=str):
            body = physical_bytes(path)
            before[str(path)] = sha256(body).hexdigest()
            archive.writestr(archive_name(path), body)
        archive.writestr('physical-sha256.json', json.dumps(before, indent=2))
    actual, first_reads, pre_origins, origin_errors, unsupported_reads = [], {}, {}, [], []
    result = None

    def observe(file, positional, keyword):
        mode = positional[0] if positional else keyword.get('mode', 'r')
        if not isinstance(mode, str) or not ('r' in mode or '+' in mode):
            return
        if isinstance(file, int):
            unsupported_reads.append('unresolved file-descriptor read: ' + str(file))
            return
        try:
            path = Path(file).resolve()
            key = str(path)
            # Runtime scratch and reports are outputs, not pre-existing inputs.
            if (path.is_relative_to(record) or key in first_reads or not originals[1](path)
                    or key not in before and any(path.is_relative_to(root) for root in runtime_roots)):
                return
            first_reads[key] = digest(path)
        except (OSError, TypeError, ValueError):
            return

    def tracked_open(file, *positional, **keyword):
        observe(file, positional, keyword)
        return physical_builtin(file, *positional, **keyword)

    def tracked_io_open(file, *positional, **keyword):
        observe(file, positional, keyword)
        return physical_open(file, *positional, **keyword)

    audit_active = True

    def audit_open(event, arguments):
        # Import machinery and os.open bypass Python open wrappers.
        if event == 'open' and audit_active and not physical_reading:
            path, mode, flags = arguments
            if isinstance(mode, str):
                observe(path, (mode,), {})
            elif flags & (os.O_WRONLY | os.O_RDWR) != os.O_WRONLY:
                observe(path, ('rb',), {})

    def origins():
        found = {}
        for name, module in sorted(tuple(sys.modules.items())):
            file = getattr(module, '__file__', None)
            if not file:
                continue
            path = Path(file).resolve()
            if (path.suffix == '.py' and (str(path) in before
                    or not any(path.is_relative_to(root) for root in runtime_roots))):
                found[name] = {'file': str(path), 'sha256': digest(path)}
        return found

    def check_origins(found):
        errors = []
        for name, origin in found.items():
            path = Path(origin['file'])
            if stage != canonical and any(path.is_relative_to(canonical / part)
                                          for part in ('engine', 'tools')):
                errors.append('canonical code escaped private stage: ' + origin['file'])
            if before.get(origin['file']) != origin['sha256']:
                errors.append('loaded origin was not frozen or changed: ' + origin['file'])
        return list(dict.fromkeys(errors))

    old_start, old_run = unittest.TestResult.startTest, unittest.TextTestRunner.run

    def start_test(self, test):
        actual.append(test.id())
        return old_start(self, test)

    def run_suite(self, suite):
        nonlocal pre_origins, result
        pre_origins = origins()
        origin_errors.extend(check_origins(pre_origins))
        if origin_errors:
            raise RuntimeError('; '.join(origin_errors))
        result = old_run(self, suite)
        return result

    original_argv = sys.argv[:]
    inner_argv = []
    arguments = iter(original_argv)
    for value in arguments:
        if value == '--physical':
            next(arguments)
        elif value.startswith('--physical='):
            continue
        elif value == '--record':
            next(arguments)
            inner_argv.extend(('--record', str(record)))
        elif value.startswith('--record='):
            inner_argv.extend(('--record', str(record)))
        else:
            inner_argv.append(value)
    preparation_seconds = time.perf_counter() - clock
    code, exception = 1, None
    builtins.open, io.open = tracked_open, tracked_io_open
    sys.addaudithook(audit_open)
    unittest.TestResult.startTest, unittest.TextTestRunner.run = start_test, run_suite
    try:
        spec = importlib.util.spec_from_file_location('_physical_verifier', runner)
        inner = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = inner
        spec.loader.exec_module(inner)
        sys.argv = inner_argv
        try:
            inner.main()
        except SystemExit as done:
            code = done.code if type(done.code) is int else 1
    except BaseException:
        exception = traceback.format_exc()
    finally:
        audit_active = False
        sys.argv = original_argv
        builtins.open, io.open = physical_builtin, physical_open
        os.path.exists, os.path.isfile, Path.exists, Path.is_file = originals
        unittest.TestResult.startTest, unittest.TextTestRunner.run = old_start, old_run
    loaded = origins()
    origin_errors.extend(check_origins(loaded))
    after = {path: digest(path) for path in before}
    missing_reads = sorted(set(first_reads) - set(before))
    missing_loaded = [value for value in loaded.values() if value['file'] not in before]
    changed_reads = [path for path, value in first_reads.items()
                     if path in before and before[path] != value]
    reports = sorted(record.glob('tests-*.json'))
    details = read_object(reports[0]) if len(reports) == 1 else {}
    report = reports[0] if len(reports) == 1 else record / 'tests-incomplete.json'
    log = Path(details['log_path']) if details.get('log_path') else record / 'tests-incomplete.log'
    if not log.is_file():
        with log.open('x', encoding='utf-8') as stream:
            stream.write('Physical execution did not produce a complete test report.\n' + (exception or ''))
    physical_errors = list(dict.fromkeys(origin_errors + unsupported_reads +
        (['pre/post input SHA maps differ'] if before != after else []) +
        (['read inputs missing pre-capture'] if missing_reads else []) +
        (['first-read SHA differs from frozen input'] if changed_reads else [])))
    if (physical_errors or missing_loaded or not details.get('successful')
            or details.get('kind') != 'run' or not actual
            or details.get('collected') != actual or len(actual) != len(set(actual))):
        code = 1
    metadata = dict(
        purpose='Existing verifier physical capture; declared scope, not source/impact/credit acceptance.',
        clause_delta=0, process_id=os.getpid(), command=original_argv,
        started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
        seconds=time.perf_counter() - clock, preparation_seconds=preparation_seconds,
        successful=code == 0, exit_code=code,
        original_cli_report=str(report), current_cli_report=report.relative_to(stage).as_posix(),
        original_cli_log=str(log), execution_stage=str(stage),
        test_ids=details.get('collected', []), actual_test_ids=actual,
        tests=result.testsRun if result else 0,
        failure_ids=[test.id() for test, _ in result.failures] if result else [],
        error_ids=[test.id() for test, _ in result.errors] if result else [], exception=exception,
        stable_hashes=before == after, runtime_test_data_sha256_before=before,
        runtime_test_data_sha256_after=after, loaded_module_origins_before_execution=pre_origins,
        loaded_module_origins=loaded, physical_open_saved_before_overlay=True,
        frozen_inputs=archive_path.relative_to(stage).as_posix(), raw_log=log.relative_to(stage).as_posix(),
        actual_read_paths=sorted(first_reads), first_actual_read_sha256=first_reads,
        input_paths_missing_pre_execution_capture=missing_reads,
        complete_pre_input_capture=not missing_reads,
        loaded_inputs_missing_pre_execution_capture=missing_loaded,
        complete_loaded_input_capture=not missing_loaded,
        changed_origin_errors=list(dict.fromkeys(origin_errors)), capture_errors=physical_errors,
        method_timings=details.get('test_durations', []))
    metadata_path = record / 'physical.json'
    with metadata_path.open('x', encoding='utf-8') as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(physical_capture='PASS' if code == 0 else 'FAIL',
                         tests=metadata['tests'], inputs=len(before), reads=len(first_reads),
                         errors=physical_errors, metadata=str(metadata_path),
                         seconds=metadata['seconds']), ensure_ascii=False))
    raise SystemExit(code)


def main() -> None:
    global STAGE, CANONICAL
    parser = argparse.ArgumentParser()
    parser.add_argument("modules", nargs="*", help="module, class or exact method; .py paths also accepted")
    parser.add_argument('--auto', nargs='+', metavar='TARGET',
                        help='direct test references keep exact module/class/method scope; packets, reports and navigation restore full declarations')
    parser.add_argument('--mode', type=lambda value: int(value, 0), metavar='BITS',
                        help='with --auto: ALLOCATE=1 RUN=2 SAVE=4 BRIEF=8; default 15, collect-only 13')
    parser.add_argument('--workflow-stats', type=Path, nargs='+', metavar='REPORT',
                        help='read-only routing replay/statistics for explicit reports; never runs tests')
    parser.add_argument(
        "--candidate",
        type=Path,
        help="run the exact test case IDs declared by a candidate packet",
    )
    parser.add_argument('--packets', type=Path, nargs='+',
                        help='merge exact test IDs from packets on an explicit integration stage')
    parser.add_argument('--groups', nargs='+', metavar='GROUP',
                        help='with --packets, run only these uniquely named completed groups')
    parser.add_argument('--cases', nargs='+', metavar='CASE',
                        help='with --packets, run only these exact declared case IDs')
    parser.add_argument('--expand-declarations', action='store_true',
                        help='expand explicit packet module/class refs with unittest and save exact packets')
    parser.add_argument('--stage', type=Path, help='sparse code overlay (candidate directory by default)')
    parser.add_argument('--canonical', type=Path, help='project code/data root')
    parser.add_argument('--report', type=Path, help='new JSON run/collection report; never overwrites evidence')
    parser.add_argument('--inspect-report', type=Path,
                        help='summarize an existing JSON report without importing or rerunning tests')
    parser.add_argument('--failed-from', type=Path, help='rerun only failed cases from a prior JSON report')
    parser.add_argument('--repeat-from', type=Path,
                        help='run exact collected cases from a saved run/collection, keeping its roots and scope')
    parser.add_argument('--record', type=Path, metavar='DIR',
                        help='save new UUID report/log in DIR and print a brief summary')
    parser.add_argument('--physical', type=Path, metavar='INPUTS_JSON',
                        help='freeze explicit input files/directories and capture physical run evidence')
    parser.add_argument('--also', nargs='+', metavar='CASE',
                        help='with --failed-from, also rerun exact cases collected in the original run')
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument('--brief', action='store_true',
                        help='print a compact decision summary; requires --report and --log')
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="import test modules and report resolved cases/sources without running the suite",
    )
    parser.add_argument(
        "--log",
        type=Path,
        help="write the complete unittest report to this file",
    )
    args = parser.parse_args()

    if args.physical:
        physical_execution(args, parser)

    if args.workflow_stats:
        if any((args.modules, args.auto, args.mode is not None, args.candidate, args.packets,
                args.groups, args.cases, args.stage, args.canonical, args.report, args.log,
                args.inspect_report, args.failed_from, args.repeat_from, args.record, args.also,
                args.collect_only, args.brief, args.quiet, args.expand_declarations)):
            parser.error('--workflow-stats is read-only and cannot combine with execution options')
        try:
            print(json.dumps(workflow_stats(args.workflow_stats), ensure_ascii=False, indent=2))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            parser.error(f'workflow statistics: {exc}')
        return
    workflow = None
    if args.auto:
        if any((args.modules, args.candidate, args.packets, args.groups, args.cases,
                args.inspect_report, args.failed_from, args.repeat_from, args.also,
                args.report, args.log, args.brief, args.collect_only)):
            parser.error('--auto owns scope and outputs; use --mode/--record, not manual selection flags')
        mode = 15 if args.mode is None else args.mode
        if (mode < 1 or mode & ~15 or not mode & WorkflowMode.ALLOCATE
                or mode & WorkflowMode.BRIEF and not mode & WorkflowMode.SAVE):
            parser.error('mode needs ALLOCATE=1; BRIEF=8 needs SAVE=4; unknown bits are rejected')
        if args.record and not mode & WorkflowMode.SAVE:
            parser.error('--record requires SAVE=4 in --mode')
        try:
            workflow = workflow_plan(args.auto, stage=args.stage, canonical=args.canonical)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            try:
                result = record_routing_error(args, mode, str(exc))
            except (OSError, ValueError) as write_error:
                parser.error(f'cannot record routing error: {write_error}; original gap: {exc}')
            print(json.dumps(result, ensure_ascii=False))
            raise SystemExit(2)
        workflow['mode'] = mode
        args.stage, args.canonical = Path(workflow['stage']), Path(workflow['canonical'])
        if workflow['packets']:
            args.packets = list(map(Path, workflow['packets']))
        else:
            args.modules = workflow['modules']
        args.collect_only = not bool(mode & WorkflowMode.RUN)
        if mode & WorkflowMode.SAVE:
            args.record = args.record or Path(workflow['default_record'])
        args.brief = bool(mode & WorkflowMode.BRIEF)
    elif args.mode is not None:
        parser.error('--mode requires --auto')

    if args.inspect_report:
        if any((args.modules, args.candidate, args.packets, args.groups, args.cases,
                args.stage, args.canonical, args.report, args.failed_from, args.repeat_from,
                args.record, args.also,
                args.collect_only, args.log, args.brief, args.quiet, args.expand_declarations)):
            parser.error('--inspect-report is read-only and cannot combine with test options')
        try:
            previous_report = json.loads(args.inspect_report.read_text(encoding='utf-8-sig'))
            if previous_report['version'] != 1 or previous_report['kind'] not in (
                    'run', 'collection', 'discovery_error', 'routing_error'):
                raise ValueError('unsupported report version or kind')
            sys.stdout.write(brief_summary(previous_report, args.inspect_report.resolve(),
                                           previous_report.get('log_path'), include_timing=True))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            parser.error(f'cannot inspect report: {exc}')
        return

    if args.groups and not args.packets:
        parser.error('--groups requires --packets')
    if args.cases and not args.packets:
        parser.error('--cases requires --packets')
    if args.also and not args.failed_from:
        parser.error('--also requires --failed-from')
    if args.record:
        if args.report or args.log:
            parser.error('--record replaces explicit --report and --log')
        output_dir = args.record.resolve()
        if workflow and os.name == 'nt' and output_dir.drive.casefold() == 'c:':
            parser.error('C: evidence outputs are disabled; use D:')
        if output_dir.exists() and not output_dir.is_dir():
            parser.error('--record must name a directory')
        stem = 'tests-' + uuid4().hex
        args.report, args.log = output_dir / (stem + '.json'), output_dir / (stem + '.log')
        args.brief = not args.auto or bool(workflow['mode'] & WorkflowMode.BRIEF)
    if args.brief and (not args.report or not args.log):
        parser.error('--brief requires both --report and --log for complete evidence')
    if args.expand_declarations and (not (args.candidate or args.packets)
                                    or args.cases or not args.report):
        parser.error('--expand-declarations requires recorded packet scope and cannot combine with --cases')
    if sum(map(bool, (args.modules, args.candidate, args.packets, args.failed_from, args.repeat_from))) != 1:
        parser.error("provide modules, --candidate, --packets, --failed-from or --repeat-from, exactly one")
    if args.packets and not args.stage:
        parser.error('--packets requires an explicit --stage; packet overlays are not merged')
    if args.canonical:
        CANONICAL = args.canonical.resolve()
    if args.stage:
        STAGE = args.stage.resolve()
    saved_selection = args.failed_from or args.repeat_from
    if saved_selection:
        option = 'failed-from' if args.failed_from else 'repeat-from'
        try:
            previous = json.loads(saved_selection.read_text(encoding='utf-8-sig'))
            kinds = ('run',) if args.failed_from else ('run', 'collection')
            if previous.get('version') != 1 or previous.get('kind') not in kinds:
                raise ValueError('requires a completed run report' if args.failed_from
                                 else 'requires a run or collection report')
            saved_canonical, saved_stage = Path(previous['canonical']), Path(previous['stage'])
            if not saved_canonical.is_absolute() or not saved_stage.is_absolute():
                raise ValueError('saved roots must be absolute')
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            parser.error(f'{option}: {exc}')
        if args.canonical and CANONICAL != saved_canonical:
            parser.error(f'{option} canonical root differs from the original run')
        if args.stage and STAGE != saved_stage:
            parser.error(f'{option} stage differs from the original run')
        CANONICAL, STAGE = saved_canonical, saved_stage
        requested = previous.get('retry_ids' if args.failed_from else 'collected', [])
        if (not isinstance(requested, list) or not requested
                or not all(isinstance(name, str) and name in previous.get('collected', [])
                           for name in requested)
                or len(requested) != len(set(requested))):
            parser.error('report contains no retryable failed tests' if args.failed_from
                         else 'report contains no distinct collected case IDs')
        origin_requested = previous.get('origin_requested', previous.get('collected', []))
        if (not isinstance(origin_requested, list)
                or not all(isinstance(name, str) for name in origin_requested)):
            parser.error('report contains invalid original test IDs')
        if args.also:
            if len(args.also) != len(set(args.also)) or any(
                    name not in origin_requested for name in args.also):
                parser.error('--also requires distinct exact cases from the original run')
            requested = list(dict.fromkeys([*requested, *args.also]))

    # The verifier may be invoked from the shared integration toolbox while
    # the candidate lives in a separate sparse overlay.  Resolve imports and
    # read fallbacks from the packet directory, rather than from this script's
    # directory, so bundled lane tests remain directly executable.
    allocation = []
    omitted_allocation = []
    omitted_case_ids = []
    if args.candidate:
        candidate_stage = args.candidate.resolve().parent
        if args.stage and STAGE != candidate_stage:
            parser.error('--stage must match the candidate directory')
        STAGE = candidate_stage
        allocation = packet_allocation([args.candidate], parser)
    elif args.packets:
        allocation = packet_allocation(args.packets, parser)
        if args.groups:
            for group in args.groups:
                if sum(entry['group'] == group for entry in allocation) != 1:
                    parser.error(f'--groups requires one matching group across packets: {group}')
            selected = set(args.groups)
            omitted_allocation = [entry for entry in allocation if entry['group'] not in selected]
            allocation = [entry for entry in allocation if entry['group'] in selected]
        if args.cases:
            declared = {case for entry in allocation for case in entry['tests']}
            if len(args.cases) != len(set(args.cases)) or any(
                    case not in declared for case in args.cases):
                parser.error('--cases requires distinct exact IDs declared in the selected packets/groups')
            selected = set(args.cases)
            narrowed = []
            for entry in allocation:
                kept = [case for case in entry['tests'] if case in selected]
                if kept:
                    omitted_case_ids.extend(case for case in entry['tests'] if case not in selected)
                    narrowed.append({**entry, 'tests': kept})
                else:
                    omitted_allocation.append(entry)
            allocation = narrowed
            omitted_case_ids = list(dict.fromkeys(omitted_case_ids))
    if allocation:
        requested = [case for group in allocation for case in group['tests']]
    elif not saved_selection:
        # Workflow test references are already normalized, including exact tails.
        requested = list(args.modules) if workflow else [module_name(value) for value in args.modules]
    requested = list(dict.fromkeys(requested))
    if allocation or args.also or args.repeat_from:
        # unittest repeats setUpClass/tearDownClass whenever a class is revisited.
        # Keep each class's declared order, but place its cases together.
        by_class = {}
        for case in requested:
            by_class.setdefault(case.rpartition('.')[0], []).append(case)
        requested = [case for cases in by_class.values() for case in cases]
    required_selection = bool(workflow) or bool(allocation) or bool(
        saved_selection and (previous.get('required_selection') or previous.get('allocation')
                             or previous.get('origin_allocation')))
    if not STAGE.is_dir() or not CANONICAL.is_dir():
        parser.error('stage and canonical must be existing directories')
    if args.report and args.report.exists():
        parser.error('--report must be a new file; preserve the previous run')
    if args.log and args.log.exists():
        parser.error('--log must be a new file; preserve the previous run')
    outputs = [p.resolve() for p in (args.log, args.report) if p is not None]
    inputs = [p.resolve() for p in (args.candidate, saved_selection) if p is not None]
    inputs.extend(p.resolve() for p in (args.packets or []))
    if workflow:
        inputs.extend(Path(value).resolve() for value in args.auto if Path(value).suffix.lower() == '.json')
    if len(set(outputs)) != len(outputs) or set(outputs) & set(inputs):
        parser.error('log/report outputs must be distinct from each other and their input evidence')
    # Test bodies may change cwd; output locations belong to the invoking CLI.
    if args.log:
        args.log = args.log.resolve()
    if args.report:
        args.report = args.report.resolve()
    if workflow:
        # Keep fixture scratch data beside the chosen evidence, not in the OS C: temp.
        scratch = (args.record or Path(workflow['default_record'])).resolve()
        if os.name == 'nt' and scratch.drive.casefold() == 'c:':
            parser.error('C: scratch outputs are disabled; use D:')
        scratch.mkdir(parents=True, exist_ok=True)
        for name in ('TEMP', 'TMP', 'TMPDIR'):
            os.environ[name] = str(scratch)
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
        import tempfile
        tempfile.tempdir = str(scratch)

    # Sparse bundles contain only changed modules.  Keep them first, then let
    # ordinary imports fall back to untouched canonical Python modules.
    sys.path[:0] = [
        str(STAGE),
        str(STAGE / "engine"),
        str(STAGE / "tools"),
        str(CANONICAL),
        str(CANONICAL / "engine"),
        str(CANONICAL / "tools"),
    ]
    sys.meta_path.insert(0, StageOverlayFinder())
    if STAGE != CANONICAL:
        install_filesystem_overlay()
    runtime_environment = {'python_version': sys.version, 'python_executable': sys.executable,
                           'platform': native_platform(), 'cpu_clock': 'time.process_time'}
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    started = time.perf_counter()
    declaration_packets, declaration_allocation, declaration_refs = {}, [], []
    declaration_requested = requested[:]
    if args.expand_declarations:
        declaration_allocation = [*allocation, *omitted_allocation]
        try:
            for path in dict.fromkeys(row['packet'] for row in declaration_allocation):
                packet = declaration_packets[path] = read_object(path)
                refs = packet.get('required_test_ids', [])
                if (not isinstance(refs, list) or 'required_test_ids' in packet and not refs
                        or not all(isinstance(ref, str) and ref.strip() for ref in refs)
                        or len(refs) != len(set(refs))):
                    raise ValueError('required_test_ids must contain distinct nonempty test references')
                declaration_refs.extend(module_name(ref) for ref in refs)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error('cannot expand packet: ' + str(exc))
    references = list(dict.fromkeys([*requested, *declaration_refs,
        *(ref for row in declaration_allocation for ref in row['tests'])]))
    resolved_cases = {}
    for name in references:
        try:
            selected_suite = loader.loadTestsFromName(name)
            resolved_cases[name] = list(test_cases(selected_suite))
            if (workflow or args.expand_declarations) and not resolved_cases[name]:
                loader.errors.append(f'Declared scope collected no tests: {name}')
            if not args.expand_declarations:
                suite.addTests(selected_suite)
        except Exception:
            # Import/load_tests failures must use the same fail-before-fixture path.
            loader.errors.append(traceback.format_exc())
    if args.expand_declarations and not loader.errors:
        def expanded(refs):
            return list(dict.fromkeys(test.id() for ref in refs for test in resolved_cases[ref]))

        full_ids = set(expanded(ref for row in declaration_allocation for ref in row['tests']))
        missing_required = set(expanded(declaration_refs)) - full_ids
        if missing_required:
            loader.errors.append('Required test references leave declared packet scope: ' +
                                 repr(sorted(missing_required)))
        selected = {}
        for ref in requested:
            for test in resolved_cases[ref]:
                selected.setdefault(test.id(), test)
        by_class = {}
        for case, test in selected.items():
            by_class.setdefault(case.rpartition('.')[0], []).append(test)
        suite.addTests(test for tests in by_class.values() for test in tests)
        requested = [test.id() for test in test_cases(suite)]
        allocation = [{**row, 'tests': expanded(row['tests'])} for row in allocation]
        omitted_allocation = [{**row, 'tests': expanded(row['tests'])} for row in omitted_allocation]
    redirect_fixture_roots()
    selected_case_ids = [test.id() for test in test_cases(suite)]
    chained_cases = []
    if not loader.errors:
        try:
            suite, chained_cases = prepare_chained_suite(suite)
        except Exception:
            loader.errors.append(traceback.format_exc())
    cases = list(test_cases(suite))
    collected = [test.id() for test in cases]
    sources = {test.__class__.__module__: getattr(sys.modules.get(test.__class__.__module__), '__file__', None)
               for test in cases}
    details = {'version': 1, 'kind': 'discovery_error', 'canonical': str(CANONICAL),
               'stage': str(STAGE), 'requested': requested, 'collected': collected,
               'sources': sources, 'tests_run': 0, 'retry_ids': [],
               'required_selection': required_selection, 'discovery_errors': loader.errors,
               'selected_case_ids': selected_case_ids, 'chained_cases': chained_cases,
               'runtime_environment': runtime_environment}
    if workflow:
        details['workflow'] = workflow
        if len(collected) != len(set(collected)):
            details['discovery_errors'].append('Auto scope resolved duplicate test IDs; review load_tests')
        missing = sorted(set(workflow['required_ids']) - set(collected))
        if missing:
            details['discovery_errors'].append(f'Recorded test obligations are missing: {missing!r}')
    if args.log:
        details['log_path'] = str(args.log)
    if args.expand_declarations:
        details['allocation_declarations'] = declaration_allocation
        details['declared_requested'] = declaration_requested
        details['declaration_expansion'] = {ref: [test.id() for test in cases]
                                            for ref, cases in resolved_cases.items()}
    if args.repeat_from:
        details['repeat_from'] = str(args.repeat_from.resolve())
        for key in ('allocation', 'allocation_scope', 'origin_requested', 'origin_allocation',
                    'origin_allocation_scope', 'omitted_allocation', 'omitted_case_ids',
                    'declared_count', 'shared_ids'):
            if key in previous:
                details[key] = previous[key]
    if args.failed_from:
        details['retry_from'] = str(args.failed_from.resolve())
        details['allocation_scope'] = 'retry'
        details['origin_requested'] = origin_requested
        if args.also:
            details['additional_requested'] = args.also
        origin = previous.get('origin_allocation', previous.get('allocation'))
        if origin:
            details['origin_allocation'] = origin
            details['origin_allocation_scope'] = previous.get(
                'origin_allocation_scope', previous.get('allocation_scope', 'full'))
            if previous.get('omitted_allocation'):
                details['omitted_allocation'] = previous['omitted_allocation']
            if previous.get('omitted_case_ids'):
                details['omitted_case_ids'] = previous['omitted_case_ids']
    if allocation:
        details['allocation'] = allocation
        details['allocation_scope'] = 'partial' if omitted_allocation or omitted_case_ids else 'full'
        if omitted_allocation:
            details['omitted_allocation'] = omitted_allocation
        if omitted_case_ids:
            details['omitted_case_ids'] = omitted_case_ids
        details['declared_count'] = sum(len(group['tests']) for group in allocation)
        details['shared_ids'] = [name for name in requested if sum(
            name in group['tests'] for group in allocation) > 1]
        if not loader.errors and selected_case_ids != requested:
            details['discovery_errors'].append(
                'Packet selection must resolve to exactly its declared test methods; '
                f'requested={requested!r}, selected={selected_case_ids!r}')
    if (args.also or args.repeat_from) and not loader.errors and selected_case_ids != requested:
        details['discovery_errors'].append(
            'Exact selection must resolve to exactly its declared test methods; '
            f'requested={requested!r}, selected={selected_case_ids!r}')
    # Keep completed test output even if the process is interrupted before the
    # final JSON report. unittest flushes each case; a partial log is not PASS.
    report = None
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        report = args.log.open('x+', encoding='utf-8', buffering=1)
    details['discovery_seconds'] = time.perf_counter() - started
    if args.expand_declarations and not details['discovery_errors']:
        details['expanded_packets'] = []
        for index, (source, packet) in enumerate(declaration_packets.items()):
            for row in packet['completed'].values():
                row['tests'] = expanded(module_name(ref) for ref in row['tests'])
            if 'required_test_ids' in packet:
                packet['required_test_ids'] = expanded(module_name(ref) for ref in packet['required_test_ids'])
            destination = args.report.with_name(f'expanded-packet-{index}-' + args.report.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('x', encoding='utf-8') as stream:
                json.dump(packet, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            details['expanded_packets'].append({'source_packet': source, 'packet': str(destination)})
    if details['discovery_errors']:
        # Resolve every requested case before any expensive fixture executes.
        stream = report if report is not None else sys.stderr
        stream.write("Test discovery failed; no tests executed.\n")
        stream.write("\n".join(details['discovery_errors']))
        successful = False
    elif not collected:
        stream = report if report is not None else sys.stderr
        stream.write('No test cases collected; no tests executed.\n')
        successful = False
    elif args.collect_only:
        stream = report if report is not None else sys.stdout
        stream.write(f"Collected {suite.countTestCases()} test case(s); no tests executed.\n")
        for name, source in sources.items():
            stream.write(f"{name}: {source}\n")
        details['kind'] = 'collection'
        successful = True
    else:
        run_cpu_started = time.process_time()
        run_started = time.perf_counter()
        result = unittest.TextTestRunner(
            stream=report,
            verbosity=1 if args.quiet else 2,
            resultclass=ReportingResult,
        ).run(suite)
        suite_seconds = time.perf_counter() - run_started
        suite_process_cpu_seconds = time.process_time() - run_cpu_started
        successful = result.wasSuccessful() and not (
            required_selection and (result.skipped or result.expectedFailures))
        if required_selection and (result.skipped or result.expectedFailures):
            (report if report is not None else sys.stderr).write(
                'Required packet tests were skipped or expected failures; run remains unverified.\n')
        details.update(kind='run', tests_run=result.testsRun,
                       test_durations=result.test_durations,
                       suite_seconds=suite_seconds,
                       suite_process_cpu_seconds=suite_process_cpu_seconds,
                       unattributed_suite_seconds=max(
                           0.0, suite_seconds - sum(item['seconds']
                                                    for item in result.test_durations)),
                       retry_ids=retry_ids(result, collected, include_unverified=required_selection),
                       failures=[{'id': test.id(), 'traceback': error} for test, error in result.failures],
                       errors=[{'id': test.id(), 'traceback': error} for test, error in result.errors],
                       skipped=[{'id': test.id(), 'reason': reason} for test, reason in result.skipped],
                       expected_failures=[test.id() for test, _ in result.expectedFailures],
                       unexpected_successes=[test.id() for test in result.unexpectedSuccesses])
    details.update(successful=successful, elapsed_seconds=time.perf_counter() - started)
    if workflow:
        workflow['next_action'] = ('choose_scope' if details['discovery_errors'] or not collected
                                   else 'repair') if not successful else (
            'execute' if args.collect_only else 'done_declared_scope')
        workflow['agent_required'] = not successful
        if not successful:
            workflow['state'] |= int(WorkflowState.NEEDS_AGENT)
            workflow['state_names'].append('NEEDS_AGENT')
    if report is not None:
        report.flush()
        report.seek(0)
        body = report.read()
        report.close()
        sys.stdout.write(brief_summary(details, args.report, args.log) if args.brief else body)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(details, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    raise SystemExit(0 if successful else 1)


if __name__ == "__main__":
    main()
