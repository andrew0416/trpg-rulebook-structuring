"""Behavior checks for chat isolation, fresh reads and ledger-derived navigation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from tools import build_reuse_vault as BUILD
from tools import vault_context as HOOK


class VaultContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ptk-vault-check-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        checkpoint = self.root / HOOK.REVIEW.CHECKPOINT
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_text(json.dumps({
            'architecture_review': {
                'scope_thread_id': HOOK.THREAD_ID,
                'cadence': {'interval': 5, 'turns_since_last_review': 0, 'phase': 'counter'},
            },
        }), encoding='utf-8')

    def run_hook(self, payload):
        return subprocess.run(
            [sys.executable, '-X', 'utf8', str(Path(HOOK.__file__)), '--project-root', str(self.root)],
            input=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )

    def payload(self, event='UserPromptSubmit', **kw):
        return dict(session_id=HOOK.THREAD_ID, hook_event_name=event, **kw)

    def test_native_events_read_only_entrypoint_and_do_not_follow_links(self):
        text = '# 현재 설정\n[인덱스](vaults/인덱스.md)를 읽고 필요한 문서를 선택하라.\n'
        (self.root / HOOK.ENTRY_NAME).write_text(text, encoding='utf-8-sig')
        # No index exists here. Reading linked documents is deliberately the agent's job.
        for event in HOOK.EVENTS:
            with self.subTest(event=event):
                result = self.run_hook(self.payload(event))
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)['hookSpecificOutput']
                self.assertEqual(output['hookEventName'], event)
                self.assertTrue(output['additionalContext'].endswith((self.root / HOOK.ENTRY_NAME).read_bytes().decode('utf-8-sig')))
                self.assertIn(str(self.root / HOOK.ENTRY_NAME), output['additionalContext'])
                self.assertNotIn('Desktop', output['additionalContext'])

    def test_next_invocation_observes_user_changed_current_setting(self):
        path = self.root / HOOK.ENTRY_NAME
        path.write_text('첫 설정', encoding='utf-8')
        first = json.loads(self.run_hook(self.payload()).stdout)
        path.write_text('새 설정: 다른 인덱스에서 이동 문서를 읽어라.', encoding='utf-8')
        second = json.loads(self.run_hook(self.payload('PreToolUse')).stdout)
        self.assertIn('첫 설정', first['hookSpecificOutput']['additionalContext'])
        self.assertNotIn('첫 설정', second['hookSpecificOutput']['additionalContext'])
        self.assertTrue(second['hookSpecificOutput']['additionalContext'].endswith(path.read_text(encoding='utf-8')))

    @unittest.skipUnless(sys.platform == 'win32', 'Native Windows PowerShell connection')
    def test_powershell_connection_matches_python_native_payload_and_chat_isolation(self):
        script = BUILD.ROOT / 'tools' / 'inject_vault_entrypoint.ps1'
        for payload in [dict(session_id=thread, hook_event_name=event)
                        for thread in HOOK.THREAD_IDS for event in HOOK.EVENTS] + [dict(session_id='another-chat', hook_event_name='PreToolUse')]:
            with self.subTest(payload=payload):
                result = subprocess.run(
                    ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(script)],
                    input=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = HOOK.context_response(payload)
                if expected is None:
                    self.assertEqual(result.stdout, b'')
                else:
                    self.assertEqual(json.loads(result.stdout.decode('utf-8-sig')), expected)

    def test_other_chat_agent_and_event_are_silent_even_without_entrypoint(self):
        rows = [dict(session_id='another-chat', hook_event_name='UserPromptSubmit')]
        for thread in HOOK.THREAD_IDS:
            rows.extend((dict(session_id=thread, hook_event_name='PreToolUse', agent_id='child-agent'),
                         dict(session_id=thread, hook_event_name='Stop')))
        for payload in rows:
            with self.subTest(payload=payload):
                result = self.run_hook(payload)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))

    def test_inherited_chat_uses_fresh_entrypoint_and_preserves_paused_history(self):
        inherited = '01a14aef-37f2-7e03-a4fa-fc84f67d1e22'
        path = self.root / HOOK.ENTRY_NAME
        path.write_text('승계 전 설정', encoding='utf-8')
        self.run_hook(self.payload(turn_id='original-turn'))
        HOOK.REVIEW.ReviewStore(self.root).transact(
            lambda review: HOOK.REVIEW.set_paused(review, True, 'Preserve the user-requested pause.'))
        checkpoint = self.root / HOOK.REVIEW.CHECKPOINT
        frozen = checkpoint.read_bytes()
        for event in HOOK.EVENTS:
            text = '승계 채팅의 최신 설정: ' + event
            path.write_text(text, encoding='utf-8')
            result = self.run_hook(dict(session_id=inherited, hook_event_name=event, turn_id='new-' + event))
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)['hookSpecificOutput']
            self.assertEqual(output['hookEventName'], event)
            self.assertTrue(output['additionalContext'].endswith(text))
            self.assertIn('일시중지 · 1/5', output['additionalContext'])
            self.assertEqual(checkpoint.read_bytes(), frozen)

    def test_missing_empty_invalid_utf8_entrypoint_reports_error_without_fallback(self):
        path = self.root / HOOK.ENTRY_NAME
        for content in (None, b'  \r\n', b'\xff\xfeinvalid'):
            with self.subTest(content=content):
                if content is not None:
                    path.write_bytes(content)
                result = self.run_hook(self.payload())
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'could not be loaded', result.stderr)

    def test_oversized_entrypoint_is_explicit_error(self):
        (self.root / HOOK.ENTRY_NAME).write_bytes(b'a' * 48_001)
        result = self.run_hook(self.payload())
        self.assertEqual(result.returncode, 2)
        self.assertIn(b'48000', result.stderr)

    def test_original_ids_meanings_routes_and_clause_membership_are_preserved(self):
        raw = (BUILD.ROOT / BUILD.PLAN).read_bytes()
        plan = json.loads(raw.decode('utf-8-sig'))
        original = json.dumps(plan, ensure_ascii=False, sort_keys=True)
        docs = BUILD.render(plan)
        self.assertEqual(original, json.dumps(plan, ensure_ascii=False, sort_keys=True))
        frozen = plan['foundation_discovery']['foundation_freeze']
        notes = [p for p in docs if p.parent.name == '공통기반' and p.stem != '인덱스']
        self.assertEqual({p.stem for p in notes}, set(frozen['unit_ids']))
        self.assertEqual(len(notes), 57)
        for unit in frozen['units']:
            self.assertIn(unit['observable_outcome'], docs[Path(f'vaults/공통기반/{unit["id"]}.md')])
        audit = plan['post_foundation_reuse']['itemized_audit']
        for item in audit['items']:
            note = docs[Path(f'vaults/재사용/{item["route"]}.md')]
            self.assertIn(item['id'], note)
        self.assertEqual(raw, (BUILD.ROOT / BUILD.PLAN).read_bytes())

    def test_paused_counter_keeps_fresh_document_injection_and_resumes(self):
        path = self.root / HOOK.ENTRY_NAME
        path.write_text('현재 문서 설정', encoding='utf-8')
        self.run_hook(self.payload(turn_id='first-turn'))
        HOOK.REVIEW.ReviewStore(self.root).transact(lambda review: HOOK.REVIEW.set_paused(review, True, 'Pause counter only.'))
        checkpoint = self.root / HOOK.REVIEW.CHECKPOINT
        frozen = checkpoint.read_bytes()
        for event in ('SessionStart', 'UserPromptSubmit', 'PreToolUse'):
            result = self.run_hook(self.payload(event, turn_id='paused-' + event))
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('일시중지 · 1/5', context)
            self.assertTrue(context.endswith('현재 문서 설정'))
            self.assertEqual(checkpoint.read_bytes(), frozen)
        path.write_text('사용자가 바꾼 최신 문서', encoding='utf-8')
        context = json.loads(self.run_hook(self.payload('PreToolUse', turn_id='another-paused-turn')).stdout)['hookSpecificOutput']['additionalContext']
        self.assertTrue(context.endswith('사용자가 바꾼 최신 문서'))
        self.assertEqual(checkpoint.read_bytes(), frozen)
        HOOK.REVIEW.ReviewStore(self.root).transact(lambda review: HOOK.REVIEW.set_paused(review, False, 'Explicit resume.'))
        result = self.run_hook(self.payload(turn_id='after-resume'))
        context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
        self.assertIn('카운터 페이즈 · 2/5', context)
        self.assertTrue(context.endswith('사용자가 바꾼 최신 문서'))

    def test_native_hook_turn_id_counts_once_and_injects_current_phase(self):
        (self.root / HOOK.ENTRY_NAME).write_text('현재 진입 설정', encoding='utf-8')
        for event in ('UserPromptSubmit', 'PreToolUse', 'PreToolUse'):
            result = self.run_hook(self.payload(event, turn_id='actual-turn'))
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('카운터 페이즈 · 1/5', context)
            self.assertIn('actual-turn', context)
            self.assertTrue(context.endswith('현재 진입 설정'))

    def test_invalid_review_state_does_not_inject_a_successful_fallback(self):
        (self.root / HOOK.ENTRY_NAME).write_text('현재 진입 설정', encoding='utf-8')
        (self.root / HOOK.REVIEW.CHECKPOINT).write_text('{}', encoding='utf-8')
        result = self.run_hook(self.payload(turn_id='actual-turn'))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b'')
        self.assertIn(b'could not be loaded', result.stderr)

    def test_generated_local_links_resolve_to_real_documents_code_and_logs(self):
        plan = json.loads((BUILD.ROOT / BUILD.PLAN).read_text(encoding='utf-8-sig'))
        docs = BUILD.render(plan)
        handwritten = [BUILD.ROOT / HOOK.ENTRY_NAME, *[p for p in (BUILD.ROOT / 'vaults').rglob('*.md') if BUILD.MARKER not in p.read_text(encoding='utf-8-sig')]]
        all_docs = {**{p.relative_to(BUILD.ROOT): p.read_text(encoding='utf-8-sig') for p in handwritten}, **docs}
        for relative, content in all_docs.items():
            for target in re.findall(r'\]\(<?([^\s)<>]+)>?\)', content):
                path = target.split('#', 1)[0]
                if not path or '://' in path:
                    continue
                resolved = (BUILD.ROOT / relative.parent / path).resolve()
                with self.subTest(document=str(relative), target=target):
                    self.assertTrue(resolved.is_file(), str(resolved))

    def test_rebuild_is_idempotent_and_does_not_modify_handwritten_files_or_authority(self):
        source = self.root / BUILD.PLAN
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((BUILD.ROOT / BUILD.PLAN).read_bytes())
        user = self.root / 'vaults' / '작업지시.md'
        user.parent.mkdir(parents=True)
        user.write_text('사용자 지시를 유지한다.', encoding='utf-8')
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        first = BUILD.build(self.root)
        self.assertGreater(first['changed'], 0)
        self.assertEqual(BUILD.build(self.root)['changed'], 0)
        self.assertEqual(before, hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(user.read_text(encoding='utf-8'), '사용자 지시를 유지한다.')
        # A user-owned file in a generated destination must never be silently replaced.
        path = self.root / 'vaults' / '공통기반' / 'movement.path.md'
        path.write_text('수기 보충', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'handwritten'):
            BUILD.build(self.root)
        self.assertEqual(path.read_text(encoding='utf-8'), '수기 보충')


if __name__ == '__main__':
    unittest.main()
