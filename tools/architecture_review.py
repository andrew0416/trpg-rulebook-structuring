"""Four-phase architecture review controller for this chat, using only the standard library."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time

THREAD_ID = '01a13591-353d-7c41-919b-f493eb95bbd2'
# Keep the original checkpoint identity and review history when a chat inherits the hook.
THREAD_IDS = frozenset((THREAD_ID, '01a14aef-37f2-7e03-a4fa-fc84f67d1e22'))
ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = Path('data/verification/category2-work-checkpoint.json')
PHASES = {
    'counter': '카운터 페이즈',
    'discovery': '교정거리 탐색 페이즈',
    'correction': '교정 페이즈',
    'complete': '교정완료 페이즈',
}


def now():
    return datetime.now().astimezone().isoformat()


@contextmanager
def locked(path):
    """An OS lock is released even if a hook process exits unexpectedly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'\0')
            stream.flush()
        deadline = time.monotonic() + 2
        while True:
            stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Review state is busy; retry the same operation.')
                time.sleep(.025)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class ReviewStore:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.path = self.root / CHECKPOINT

    def transact(self, operation):
        with locked(self.path.with_suffix('.json.review.lock')):
            original = self.path.read_bytes()
            document = json.loads(original.decode('utf-8-sig'))
            before = deepcopy(document)
            review = document['architecture_review']
            if review['scope_thread_id'] != THREAD_ID:
                raise ValueError('Review checkpoint belongs to another chat.')
            cadence = review['cadence']
            phase = cadence.get('phase', 'counter')
            cadence['phase'] = {'counting': 'counter', 'correction_in_progress': 'correction'}.get(phase, phase)
            if cadence['phase'] not in PHASES:
                raise ValueError('Unknown review phase.')
            count, interval = cadence['turns_since_last_review'], cadence['interval']
            if type(count) is not int or type(interval) is not int or interval != 5 or not 0 <= count <= interval:
                raise ValueError('Expected a review counter between 0 and 5.')
            if cadence['phase'] == 'counter' and count == interval:
                cadence['phase'] = 'discovery'
            if cadence['phase'] != 'counter' and count != interval:
                raise ValueError('Review phases must hold the counter at 5/5.')
            review.setdefault('controller', {'version': 1, 'seen_turn_ids': [], 'cycle': 0})
            result = operation(review)
            cadence['next_review_after_turns'] = max(0, interval - cadence['turns_since_last_review'])
            if document != before:
                if self.path.read_bytes() != original:
                    raise ValueError('Checkpoint changed concurrently; retry without overwriting it.')
                fd, name = tempfile.mkstemp(prefix=self.path.name + '.', suffix='.tmp', dir=self.path.parent)
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
                        json.dump(document, stream, ensure_ascii=False, indent=2)
                        stream.write('\n')
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, self.path)
                finally:
                    if os.path.exists(name):
                        os.unlink(name)
            return result


def snapshot(review):
    cadence = review['cadence']
    return {
        'paused': review['controller'].get('suspension', {}).get('paused', False),
        'phase': cadence['phase'],
        'phase_label': PHASES[cadence['phase']],
        'counter': cadence['turns_since_last_review'],
        'interval': cadence['interval'],
        'cycle': review['controller']['cycle'],
        'pending': [item['id'] for item in review.get('active_cycle', {}).get('findings', []) if item['status'] != 'verified'],
    }


def hook_status(payload, root=ROOT):
    if payload.get('session_id') not in THREAD_IDS or payload.get('agent_id'):
        return None
    event = payload.get('hook_event_name')
    if event not in {'SessionStart', 'UserPromptSubmit', 'PreToolUse'}:
        return None

    def observe(review):
        cadence, control = review['cadence'], review['controller']
        if snapshot(review)['paused']:
            return snapshot(review)
        turn = payload.get('turn_id')
        if event != 'SessionStart' and isinstance(turn, str) and turn.strip() and turn not in control['seen_turn_ids']:
            control['seen_turn_ids'].append(turn)
            control['last_turn_id'] = turn
            cadence['current_work_turn_marker'] = turn
            cadence['counted_current_work_turn'] = True
            if cadence['phase'] == 'counter':
                cadence['turns_since_last_review'] += 1
                if cadence['turns_since_last_review'] == cadence['interval']:
                    cadence['phase'] = 'discovery'
        state = snapshot(review)
        state['turn_id'] = turn if isinstance(turn, str) else None
        state['turn_id_missing'] = event != 'SessionStart' and not state['turn_id']
        return state

    return ReviewStore(root).transact(observe)


def set_paused(review, paused, reason):
    reason = text_required(reason, 'Pause/resume reason')
    control = review['controller']
    suspension = control.get('suspension', {})
    if suspension.get('paused', False) != paused:
        suspension = dict(suspension, paused=paused)
        action = 'paused' if paused else 'resumed'
        suspension[action + '_at'] = now()
        suspension[action + '_reason'] = reason
        control['suspension'] = suspension
    return snapshot(review)


def require_running(review):
    if snapshot(review)['paused']:
        raise ValueError('Review counter is paused; resume before phase transitions.')


def text_required(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be nonempty text.')
    return value


def file_proof(value, root, *, local=False):
    path = Path(text_required(value.get('path'), 'Evidence path'))
    path = path if path.is_absolute() else root / path
    path = path.resolve()
    if local and not path.is_relative_to(root):
        raise ValueError('Changed or reviewed runtime files must stay inside the project.')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if value.get('sha256') != digest:
        raise ValueError(f'Evidence hash does not match: {path}')
    return {'path': str(path), 'sha256': digest}


def verification_proof(value, root):
    proof = file_proof(value, root, local=True)
    raw = Path(proof['path']).read_bytes()
    text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    tests = value.get('tests')
    if not isinstance(tests, list) or not tests or any(not isinstance(item, str) or not item for item in tests):
        raise ValueError('Verification must name the direct-consumer tests.')
    if not re.search(r'Ran [1-9][0-9]* tests? in ', text) or not re.search(r'\nOK\s*$', text) or re.search(r'^(FAILED|ERROR:|FAIL:)', text, re.M):
        raise ValueError('Verification log must be a complete passing unittest run.')
    if any(test not in text for test in tests):
        raise ValueError('Named test is absent from the verification log.')
    return dict(proof, tests=tests)


def discover(review, report, root):
    require_running(review)
    phase = review['cadence']['phase']
    recheck_empty_review = phase == 'complete' and not review['active_cycle']['findings']
    if phase != 'discovery' and not recheck_empty_review:
        raise ValueError('Discovery is available only at 5/5 in the discovery phase.')
    references = report.get('reference_files')
    scope = report.get('scope')
    if not isinstance(references, list) or not references or not isinstance(scope, list) or not scope:
        raise ValueError('Discovery needs actual reference files and reviewed project files.')
    record = {
        'at': now(),
        'summary': text_required(report.get('summary'), 'Review summary'),
        'reference_files': [file_proof(item, root) for item in references],
        'runtime_files': [file_proof(item, root, local=True) for item in scope],
        'findings': [],
    }
    findings = report.get('findings')
    if not isinstance(findings, list):
        raise ValueError('Discovery must explicitly list its findings, including an empty list.')
    for item in findings:
        path = file_proof(item, root, local=True)
        record['findings'].append(dict(
            path, id=text_required(item.get('id'), 'Finding ID'),
            impact=text_required(item.get('impact'), 'Finding impact'),
            correction=text_required(item.get('correction'), 'Required correction'),
            status='open',
        ))
    if len({item['id'] for item in record['findings']}) != len(record['findings']):
        raise ValueError('Finding IDs must be unique.')
    if recheck_empty_review:
        previous = review['active_cycle']
        record['cycle'] = previous['cycle']
        record['discovery_revisions'] = [
            *previous.get('discovery_revisions', []),
            {key: value for key, value in previous.items()
             if key not in {'cycle', 'discovery_revisions'}},
        ]
    else:
        previous = review.get('last_review')
        if previous and 'record' not in previous:
            # Preserve the bounded review written before this controller existed.
            review.setdefault('review_history', []).append(previous)
        review['controller']['cycle'] += 1
        record['cycle'] = review['controller']['cycle']
    review['last_review'] = {'cycle': record['cycle'], 'record': 'active_cycle'}
    review['active_cycle'] = record
    review['cadence']['phase'] = 'correction' if findings else 'complete'
    return snapshot(review)


def correct(review, report, root):
    require_running(review)
    if review['cadence']['phase'] not in {'correction', 'complete'}:
        raise ValueError('Corrections are accepted only in the correction phase.')
    items = {item['id']: item for item in review['active_cycle']['findings']}
    corrections = report.get('corrections')
    if not isinstance(corrections, list) or not corrections:
        raise ValueError('A correction report must contain actual corrections.')
    seen = set()
    for change in corrections:
        identity = change.get('id')
        if identity not in items or identity in seen:
            raise ValueError('Correction must name one unresolved finding exactly once.')
        seen.add(identity)
        item = items[identity]
        changed = [file_proof(value, root, local=True) for value in change.get('changed_files', [])]
        verification = [verification_proof(value, root) for value in change.get('verification', [])]
        if not changed or not verification or not any(value['path'] == item['path'] and value['sha256'] != item['sha256'] for value in changed):
            raise ValueError('Correction needs a changed finding file and passing direct-consumer evidence.')
        item['resolution'] = {
            'at': now(), 'summary': text_required(change.get('summary'), 'Correction summary'),
            'changed_files': changed, 'verification': verification,
        }
        item['status'] = 'verified'
    if all(item['status'] == 'verified' for item in items.values()):
        review['cadence']['phase'] = 'complete'
    return snapshot(review)


def complete(review, reason, root):
    require_running(review)
    if review['cadence']['phase'] != 'complete' or snapshot(review)['pending']:
        raise ValueError('Completion declaration requires finished discovery and all corrections verified.')
    cycle = review['active_cycle']
    for item in cycle['findings']:
        for proof in item['resolution']['changed_files']:
            file_proof(proof, root, local=True)
        for proof in item['resolution']['verification']:
            verification_proof(proof, root)
    corrected_paths = {proof['path'] for item in cycle['findings'] for proof in item['resolution']['changed_files']}
    for proof in cycle['runtime_files']:
        if proof['path'] not in corrected_paths:
            file_proof(proof, root, local=True)
    cycle['completed_at'] = now()
    cycle['completion_declaration'] = text_required(reason, 'Completion declaration')
    cycle['completed_phase'] = 'complete'
    history = review.setdefault('review_history', [])
    history.append(cycle)
    pointer = {'cycle': cycle['cycle'], 'record': 'review_history', 'index': len(history) - 1}
    review['last_review'] = dict(pointer)
    review['last_completed_cycle'] = dict(pointer)
    review.pop('active_cycle')
    review['cadence']['phase'] = 'counter'
    review['cadence']['turns_since_last_review'] = 0
    return snapshot(review)


def context(state):
    if state.get('paused'):
        return (f"프로그램 관리 교정 상태: 일시중지 · {state['counter']}/{state['interval']}\n"
                '계수와 자동 교정 주기를 일시중지했다. 엔트리포인트 문서 주입은 유지한다. '
                '명시적으로 resume한 뒤 보존한 상태에서 재개한다.')
    action = {
        'counter': '기존 구현 작업을 계속한다. 카운터를 수동으로 올리거나 초기화하지 않는다.',
        'discovery': '지정 참조 채팅의 최신 관련 결과물과 변경 코드를 비교해 교정거리를 탐색하고 discover 보고서를 제출한다.',
        'correction': '남은 교정 항목을 실제로 수정하고 직접 소비 경로를 검증한 뒤 correct 보고서를 제출한다. 보류만으로 완료하지 않는다.',
        'complete': '탐색·교정 결과를 확인한 뒤 complete 명령으로 교정완료를 선언한다. 선언 즉시 카운터 페이즈 0/5로 돌아간다.',
    }[state['phase']]
    if state['phase'] != 'counter':
        action = ('페이즈 전환으로 중단한 기존 구현이 있으면 그 구현의 직접 검증·장부 반영까지 먼저 마친다. '
                  '그다음 이 페이즈의 작업을 진행한다: ' + action)
    warning = '\nturn_id가 없어 이번 호출은 세지 않았다.' if state.get('turn_id_missing') else ''
    return (
        f"프로그램 관리 교정 상태: {state['phase_label']} · {state['counter']}/{state['interval']}\n"
        f"현재 턴 ID: {state.get('turn_id') or '(세션 시작/미제공)'}\n"
        f"다음 조치: {action}\n"
        f"미해결: {', '.join(state['pending']) or '없음'}\n"
        f"명령·보고서 형식: vaults/교정상태.md. 정본: {CHECKPOINT.as_posix()}#architecture_review"
        f"{warning}"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    for command in ('discover', 'correct'):
        sub.add_parser(command).add_argument('--report', type=Path, required=True)
    sub.add_parser('complete').add_argument('--reason', required=True)
    for command in ('pause', 'resume'):
        sub.add_parser(command).add_argument('--reason', required=True)
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    try:
        report = json.loads(args.report.read_text(encoding='utf-8-sig')) if hasattr(args, 'report') else None
        operations = {
            'status': lambda review: snapshot(review),
            'discover': lambda review: discover(review, report, root),
            'correct': lambda review: correct(review, report, root),
            'complete': lambda review: complete(review, args.reason, root),
            'pause': lambda review: set_paused(review, True, args.reason),
            'resume': lambda review: set_paused(review, False, args.reason),
        }
        state = ReviewStore(root).transact(operations[args.command])
        print(json.dumps(state, ensure_ascii=False))
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        print(f'Review state transition rejected: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

