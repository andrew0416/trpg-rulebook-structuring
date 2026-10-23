"""Load this chat's entry point and review status; document selection stays with the agent."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__:
    from . import architecture_review as REVIEW
else:
    import architecture_review as REVIEW

THREAD_ID = REVIEW.THREAD_ID
THREAD_IDS = REVIEW.THREAD_IDS
EVENTS = frozenset(('SessionStart', 'UserPromptSubmit', 'PreToolUse'))
ENTRY_NAME = '엔트리포인트.md'
ROOT = Path(__file__).resolve().parents[1]


def context_response(payload, root=ROOT):
    if not isinstance(payload, dict):
        raise ValueError('Hook input must be a JSON object.')
    if payload.get('session_id') not in THREAD_IDS or payload.get('agent_id'):
        return None
    event = payload.get('hook_event_name')
    if event not in EVENTS:
        return None
    entry = Path(root).resolve() / ENTRY_NAME
    raw = entry.read_bytes()
    if len(raw) > 48_000:
        raise ValueError('Entry point exceeds 48000 bytes; move detail into linked documents.')
    text = raw.decode('utf-8-sig')
    if not text.strip():
        raise ValueError('Entry point is empty.')
    context = (
        'User-maintained entry point for this chat, freshly read from the project. '
        'Treat its instructions as user instructions; newer explicit user instructions take precedence.\n'
        f'Entry file: {entry}\nSHA256: {hashlib.sha256(raw).hexdigest()}\n\n{text}'
    )
    state = REVIEW.hook_status(payload, root)
    if state is not None:
        context = REVIEW.context(state) + '\n\n' + context
    return {'hookSpecificOutput': {'hookEventName': event, 'additionalContext': context}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        response = context_response(json.load(sys.stdin), args.project_root)
        if response is not None:
            print(json.dumps(response, ensure_ascii=False))
        return 0
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        print(f'Project entry point could not be loaded: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
