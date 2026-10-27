"""Bounded ordinary generated-input proofs for reviewed shadow copies and reports."""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
import sys

CSV_ID = 'tools.test_category2_csv_timed_type_additions.CsvTimedTypeAdditionTests.test_report_collect_adds_exactly_four_denominator_completions'
REPORT_ID = 'engine.test_maintenance.MaintenanceTests.test_source_resolution_counts_and_partial_coverage'
SOURCES = {
    'tools/test_category2_csv_timed_type_additions.py': '2f1dacd24178fec1f65aae3c2a94123ef0b61799ae1e19634bdcbf5627e53d09',
    'engine/test_maintenance.py': '364edeed6eb3e748de441e58c6924a614f52ed2c30189f95312f5fbdbe50180f',
    'tools/crosscheck_drafts.py': 'cf554f7c08fae37d2ce1fc3e8f780c7323673674b781b7ad2242a05159f99c93',
}


class ExtendedGeneratedCapture:
    def __init__(self, stage, before, physical, raw_open, capture_bytes, event):
        self.stage, self.before, self.physical = stage, before, physical
        self.raw_open, self.capture_bytes, self.event = raw_open, capture_bytes, event
        self.history, self.bodies, self.generated_reads, self.errors = {}, {}, {}, []

    def body(self, path):
        with self.raw_open(path, 'rb') as stream:
            return stream.read()

    def digest(self, path):
        return hashlib.sha256(self.body(path)).hexdigest()

    def admit(self, file, operation, test, mode=None, link_source=None):
        if test is None or test.id() not in (CSV_ID, REPORT_ID) or isinstance(file, int):
            return None
        try:
            path = Path(file).resolve()
        except (TypeError, ValueError, OSError):
            return None
        if not path.is_relative_to(self.stage) or path.is_symlink() or str(path) in self.before:
            return None
        frames, frame = [], sys._getframe(1)
        try:
            while frame:
                origin = Path(frame.f_code.co_filename).resolve()
                if origin.is_relative_to(self.stage) and origin != Path(__file__).resolve() and origin.name != 'ci_physical.py':
                    frames.append((frame, origin))
                frame = frame.f_back
            caller_rel = 'tools/test_category2_csv_timed_type_additions.py' if test.id() == CSV_ID else 'engine/test_maintenance.py'
            caller = self.stage / caller_rel
            caller_frames = [f for f, p in frames if p == caller and f.f_code.co_name == test._testMethodName and f.f_locals.get('self') is test]
            if len(caller_frames) != 1 or self.before.get(str(caller)) != SOURCES[caller_rel] or not frames:
                return None
            writer_frame, writer = frames[0]
            writer_rel = writer.relative_to(self.stage).as_posix()
            if self.before.get(str(writer)) != SOURCES.get(writer_rel):
                return None
            linked = None
            if test.id() == CSV_ID:
                if writer != caller or writer_frame is not caller_frames[0]:
                    return None
                shadow = Path(writer_frame.f_locals['shadow']).resolve()
                root_rel = shadow.relative_to(self.stage)
                if len(root_rel.parts) != 1 or not root_rel.name.startswith('csv-timed-type-report-') or not path.is_relative_to(shadow):
                    return None
                relative = path.relative_to(shadow).as_posix()
                if not (relative.startswith('input/') or relative.startswith('data/verification/')):
                    return None
                source = (self.stage / relative).resolve()
                if str(source) not in self.before:
                    return None
                if operation == 'link':
                    if Path(link_source).resolve() != source or self.digest(source) != self.before[str(source)]:
                        return None
                    linked = {'source': str(source), 'source_sha256': self.before[str(source)]}
                elif operation == 'write' and (str(path) not in self.history or self.history[str(path)][-1]['phase'] == 'failed'):
                    if Path(writer_frame.f_locals.get('target', self.stage)).resolve() != path or Path(writer_frame.f_locals.get('source', self.stage)).resolve() != source:
                        return None
                    linked = {'source': str(source), 'source_sha256': self.before[str(source)]}
                elif operation not in ('write', 'unlink'):
                    return None
                if str(path) in self.history and self.history[str(path)][-1]['phase'] != 'failed' and relative != 'data/verification/category2-csv-abilities-moves-status.json':
                    return None
                policy = 'csv_shadow_copy'
            else:
                if operation != 'write' or writer_rel != 'tools/crosscheck_drafts.py' or writer_frame.f_code.co_name != 'main':
                    return None
                if Path(writer_frame.f_locals['root']).resolve() != self.stage or path.relative_to(self.stage).as_posix() not in (
                    'output/draft-crosscheck.jsonl', 'output/draft-crosscheck-resolved.jsonl', 'output/draft-crosscheck.md'):
                    return None
                policy = 'crosscheck_report'
            exists = path.exists()
            previous = self.history.get(str(path), [])
            if not previous and exists or operation in ('link',) and exists:
                return None
            expected = previous[-1].get('sha256') if previous else None
            if exists and (not path.is_file() or self.digest(path) != expected):
                return None
            return {'file': str(path), 'path': path.relative_to(self.stage).as_posix(), 'policy': policy,
                    'test_id': test.id(), 'caller_source': str(caller), 'caller_source_sha256': SOURCES[caller_rel],
                    'caller_function': test._testMethodName, 'writer_source': str(writer),
                    'writer_source_sha256': SOURCES[writer_rel], 'writer_function': writer_frame.f_code.co_name,
                    'writer_line': writer_frame.f_lineno, 'operation': operation, 'mode': mode,
                    'existed_before': exists, 'before_sha256': expected if exists else None,
                    'source_frozen_before_import': True, 'source_preimage': linked}
        except (KeyError, TypeError, ValueError, OSError):
            return None
        finally:
            del frame, frames

    def record(self, phase, proof, body=None):
        row = dict(proof, phase=phase)
        if body is not None:
            row['sha256'] = hashlib.sha256(body).hexdigest()
            row['archive_member'] = 'physical/ordinary-extended-generated/' + row['sha256'] + '.bin'
            self.bodies[row['sha256']] = body
        self.history.setdefault(proof['file'], []).append(row)
        self.event('ordinary_extended_generated_' + phase, **row)
        return row

    def link(self, raw_link, source, target, test, *args, **kwargs):
        proof = self.admit(target, 'link', test, link_source=source)
        if proof is not None:
            self.record('open', proof)
        try:
            result = raw_link(source, target, *args, **kwargs)
        except OSError:
            if proof is not None: self.record('failed', proof)
            raise
        if proof is not None:
            body = self.body(target)
            if hashlib.sha256(body).hexdigest() != proof['source_preimage']['source_sha256']:
                raise ValueError('hardlink bytes differ from frozen source')
            self.record('closed', proof, body)
        return result

    def unlink(self, raw_unlink, file, test, *args, **kwargs):
        proof = self.admit(file, 'unlink', test) if not kwargs.get('dir_fd') else None
        result = raw_unlink(file, *args, **kwargs)
        if proof is not None:
            self.record('unlinked', proof)
        return result

    def writer(self, file, mode, test):
        if mode not in ('w', 'wt', 'wb', 'x', 'xt', 'xb'):
            return None
        return self.admit(file, 'write', test, mode)

    def wrap(self, stream, proof):
        owner = self
        self.record('open', proof)
        class Writer:
            recorded = False
            def __getattr__(self, name): return getattr(stream, name)
            def write(self, *args, **kwargs): return stream.write(*args, **kwargs)
            def writelines(self, *args, **kwargs): return stream.writelines(*args, **kwargs)
            def __enter__(self): stream.__enter__(); return self
            def commit(self):
                if not self.recorded:
                    owner.record('closed', proof, owner.body(proof['file']))
                    self.recorded = True
            def close(self):
                stream.close()
                self.commit()
            def __exit__(self, *args):
                result = stream.__exit__(*args)
                if args[0] is None: self.commit()
                return result
            def __del__(self):
                if not stream.closed:
                    try: self.close()
                    except BaseException: owner.errors.append('unclosed generated writer: ' + proof['file'])
        return Writer()

    def generated_read(self, path, digest):
        history = self.history.get(str(path), [])
        if not history or history[-1]['phase'] != 'closed' or history[-1]['sha256'] != digest:
            return False
        for transition in history:
            if transition['phase'] != 'closed': continue
            body = self.bodies[transition['sha256']]
            destination = self.physical / 'ordinary-extended-generated' / (transition['sha256'] + '.bin')
            destination.parent.mkdir(exist_ok=True)
            if not destination.exists():
                with self.raw_open(destination, 'xb') as stream: stream.write(body)
            elif self.body(destination) != body: raise ValueError('generated archive SHA collision')
        last = history[-1]
        row = {key: last[key] for key in ('file', 'path', 'policy', 'test_id', 'caller_source', 'caller_source_sha256', 'caller_function')}
        row.update(sha256=digest, archive_member=last['archive_member'], transitions=copy.deepcopy(history))
        self.generated_reads[str(path)] = row
        self.event('ordinary_extended_generated_first_read', **row)
        return True
