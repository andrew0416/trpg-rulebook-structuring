"""Native rank3/Exalted producers preserve existing legacy authority and effects."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
import blessing_skill_features as B
import class_passive_combat as PASSIVE
import native_acquisition_adapters as N
import state_grants as G
from encounter import usable_moves
import tools.test_native_acquisition_adapters as FIXTURES


class NativeBlessingAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def fixture(self, uid, role='contractor'):
        case = FIXTURES.NativeAcquisitionAdapterTests('runTest')
        case.rules = self.rules
        return case, case.fixture(uid, role=role)

    def reject_unexportable(self, e, operation, pattern):
        """Corrupt legacy authority is intentionally not a valid codec input."""
        actors = list(e.everyone)
        memo = {id(e.r): e.r, id(e): e, id(e.gm): e.gm,
                id(e.rng): e.rng, id(e.r.rulings): e.r.rulings,
                **{id(actor): actor for actor in actors}}
        def snapshot():
            # Random and Rulings identities stay stable; their complete state is
            # compared explicitly instead of comparing newly deep-copied objects.
            return deepcopy(([vars(actor) for actor in actors], vars(e), vars(e.gm),
                             vars(e.r.rulings), vars(e.rng), e.rng.getstate()), memo.copy())
        before = snapshot()
        with self.assertRaisesRegex(ValueError, pattern):
            operation()
        self.assertEqual(snapshot(), before)

    def test_both_role_routes_for_both_gifts_reject_rank_two_and_accept_rank_three(self):
        for uid in (N.RESILIENCE, N.INSIGHT):
            for role in N.ROUTES:
                with self.subTest(gift=uid, role=role):
                    case, (e, a, selection) = self.fixture(uid, role)
                    a.spec['feat_ranks'][N.ROUTES[role]] = 2
                    case.reject(e, lambda: case.acquire(e, a, uid, selection), 'rank3')
                    a.spec['feat_ranks'][N.ROUTES[role]] = 3
                    row = case.acquire(e, a, uid, selection)
                    self.assertEqual(row['snapshot']['route_rank'], 3)
                    self.assertEqual(row['snapshot']['grant'], [role, 3, 1])
                    self.assertEqual(a.spec['_blessing_gift_approvals'][uid]['acquisition']['basis'], N.LABEL)
                    self.assertTrue(B.approval(a, uid))

    def test_dual_role_requires_actual_choice_and_role_configuration_cannot_disagree(self):
        for role in N.ROUTES:
            case, (e, a, selection) = self.fixture(N.INSIGHT, role)
            other = N.ROUTES['messiah' if role == 'contractor' else 'contractor']
            a.spec['feats'].append(other)
            a.spec['feat_ranks'][other] = 3
            missing = deepcopy(selection)
            missing.pop('role')
            case.reject(e, lambda: case.acquire(e, a, N.INSIGHT, missing), 'exact native Blessing')
            mismatch = deepcopy(selection)
            mismatch['configuration']['role'] = '메시아' if role == 'contractor' else '계약자'
            case.reject(e, lambda: case.acquire(e, a, N.INSIGHT, mismatch), 'contradicts')
            row = case.acquire(e, a, N.INSIGHT, selection)
            self.assertEqual(row['selection']['role'], role)

    def test_independent_prerequisite_permission_is_not_supplied_by_generic_new_gm_reason(self):
        case, (e, a, selection) = self.fixture(N.INSIGHT)
        a.spec['_blessing_gift_approvals'].pop('gift/고대의-지혜')
        self.reject_unexportable(e, lambda: case.acquire(e, a, N.INSIGHT, selection), 'independent prerequisite Gift permission')
        self.assertNotIn(N.INSIGHT, a.spec['gifts'])

    def test_explicit_prerequisite_permission_waiver_is_source_bound_and_retained(self):
        case, (e, a, selection) = self.fixture(N.INSIGHT)
        a.spec['_blessing_gift_approvals'].pop('gift/고대의-지혜')
        a.spec['gifts'].remove('gift/고대의-지혜')
        selection['waivers'] = [{'source_id': N.INSIGHT, 'provider': 'native', 'stage': 'acquire',
            'checks': ['owned:gift/고대의-지혜', 'prerequisite_permission'],
            'reason': 'explicit exception only for this named prerequisite and its permission'}]
        row = case.acquire(e, a, N.INSIGHT, selection)
        check = next(c for c in row['qualification']['checks'] if c['id'] == 'prerequisite_permission')
        self.assertEqual(check['state'], 'waived')
        self.assertTrue(B.approval(a, N.INSIGHT))

    def test_grant_rank_and_role_slot_boundaries_are_not_waived_by_gm_permission(self):
        for role, invalid_slots in (('messiah', (0, 2)), ('contractor', (0, 3))):
            for slot in invalid_slots:
                case, (e, a, selection) = self.fixture(N.INSIGHT, role)
                selection['slot'] = slot
                case.reject(e, lambda: case.acquire(e, a, N.INSIGHT, selection), 'grant slot')
        case, (e, a, selection) = self.fixture(N.INSIGHT)
        selection['grant_rank'] = 4
        case.reject(e, lambda: case.acquire(e, a, N.INSIGHT, selection), 'rank3')
        a.spec['feat_ranks'][N.ROUTES['contractor']] = 4
        row = case.acquire(e, a, N.INSIGHT, selection)
        self.assertEqual(row['snapshot']['grant'], ['contractor', 4, 1])

    def test_native_rank3_slots_are_independent_and_legacy_slot_history_is_not_inferred(self):
        case, (e, a, first) = self.fixture(N.RESILIENCE)
        case.acquire(e, a, N.RESILIENCE, first)
        a.spec['gifts'].append('gift/고대의-지혜')
        a.spec['gift_patrons']['gift/고대의-지혜'] = '뮤'
        B.confirm(e, a, 'gift/고대의-지혜', reason='independent actual prerequisite', configuration={'role': 'contractor'})
        second = {'role': 'contractor', 'grant_rank': 3, 'slot': 1,
            'configuration': {'role': '계약자'}, 'permission': {'reason': 'GM permits exact second blessing'}, 'waivers': []}
        case.reject(e, lambda: case.acquire(e, a, N.INSIGHT, second, 'native/request/2'), 'slot already used')
        second['slot'] = 2
        case.acquire(e, a, N.INSIGHT, second, 'native/request/2')
        self.assertEqual(len([row for row in N.receipts(a) if row['state'] == 'active']), 2)
        case, (e, a, selection) = self.fixture(N.INSIGHT)
        a.spec['gifts'].append(N.RESILIENCE)
        # This legacy owned record deliberately has no source-grant slot history.
        self.reject_unexportable(e, lambda: case.acquire(e, a, N.INSIGHT, selection), 'legacy rank3.*unresolved')

    def test_confirmation_remains_existing_owned_migration_and_does_not_create_native_slot(self):
        for uid in (N.RESILIENCE, N.INSIGHT):
            case, (e, a, selection) = self.fixture(uid)
            a.spec['feat_ranks'][N.ROUTES['contractor']] = 1
            a.spec['gifts'].append(uid)
            record = B.confirm(e, a, uid, reason='GM declares already-owned history only', configuration=selection['configuration'])
            self.assertNotEqual(record['acquisition'].get('basis'), N.LABEL)
            self.assertEqual(N.receipts(a), [])
            self.assertTrue(B.approval(a, uid))
            self.reject_unexportable(e, lambda: case.acquire(e, a, uid, selection), 'already-owned')

    def test_later_route_and_added_prerequisite_loss_do_not_cancel_valid_native_history(self):
        for uid in (N.RESILIENCE, N.INSIGHT):
            case, (e, a, selection) = self.fixture(uid)
            row = case.acquire(e, a, uid, selection)
            parent = N.DEFINITIONS[uid]['parents'][0]
            a.spec['gifts'].remove(parent)
            a.spec['feats'].remove(N.ROUTES['contractor'])
            a.spec['feat_ranks'].pop(N.ROUTES['contractor'])
            self.assertTrue(B.approval(a, uid))
            restored, actor = case.restore(e, a)
            self.assertTrue(B.approval(actor, uid))
            self.assertEqual(N.receipts(actor)[0]['snapshot'], row['snapshot'])

    def test_native_resilience_configuration_remains_fixed_and_real_patron_domain_is_required(self):
        case, (e, a, selection) = self.fixture(N.RESILIENCE, 'messiah')
        invalid = deepcopy(selection)
        invalid['configuration']['selected_types'] = ['불꽃', '노말']
        case.reject(e, lambda: case.acquire(e, a, N.RESILIENCE, invalid), 'eligible patron types')
        case.acquire(e, a, N.RESILIENCE, selection)
        self.assertEqual(PASSIVE.resistance_steps(e, a, '불꽃'), 1)
        a.spec['class_passive_choices'][N.RESILIENCE]['selected_types'] = ['물', '얼음']
        self.reject_unexportable(e, lambda: PASSIVE.resistance_steps(e, a, '불꽃'), 'choices changed')

    def test_native_insight_role_mutation_is_rejected_before_observation_or_payment(self):
        case, (e, a, selection) = self.fixture(N.INSIGHT)
        case.acquire(e, a, N.INSIGHT, selection)
        a.spec['gift_choices'][N.INSIGHT]['role'] = '메시아'
        self.reject_unexportable(e, lambda: B.approval(a, N.INSIGHT), 'role changed')
        self.reject_unexportable(e, lambda: B.confirm(e, a, N.INSIGHT, reason='cannot reselect native role', configuration={'role': '메시아'}), 'already recorded')

    def test_exalted_requires_actual_mewtwo_and_generic_reason_cannot_waive_prerequisites(self):
        for patron_id in ('missing-patron', 'native-acquirer'):
            case, (e, a, selection) = self.fixture(N.PSYSTRIKE)
            selection['permission']['patron_id'] = patron_id
            case.reject(e, lambda: case.acquire(e, a, N.PSYSTRIKE, selection), 'Mewtwo')
        case, (e, a, selection) = self.fixture(N.PSYSTRIKE)
        selection.pop('permission')
        case.reject(e, lambda: case.acquire(e, a, N.PSYSTRIKE, selection), 'exact Exalted Gift permission')

    def test_exalted_zero_to_one_accepts_and_one_to_two_rejects_including_alias_ownership(self):
        other = 'feat/칠색조의-약속된-기프트-성스러운불꽃'
        for alias in (other, '칠색조의 약속된 기프트 - 성스러운불꽃'):
            case, (e, a, selection) = self.fixture(N.PSYSTRIKE)
            a.spec['feats'].append(alias)
            case.reject(e, lambda: case.acquire(e, a, N.PSYSTRIKE, selection), 'second Exalted')
        case, (e, a, selection) = self.fixture(N.PSYSTRIKE)
        row = case.acquire(e, a, N.PSYSTRIKE, selection)
        self.assertEqual(row['snapshot']['exalted_count'], 0)
        self.assertIn(e.r.resolve_move('move/사이코브레이크'), usable_moves(e, a))
        selection['waivers'] = [{'source_id': N.PSYSTRIKE, 'provider': 'native', 'stage': 'acquire',
            'checks': ['one_exalted'], 'reason': 'generic permission cannot redefine source capacity'}]
        case, (e, a, _) = self.fixture(N.PSYSTRIKE)
        a.spec['feats'].append(other)
        case.reject(e, lambda: case.acquire(e, a, N.PSYSTRIKE, selection), 'may only name existing prerequisites')

    def test_psystrike_grant_preserves_independent_move_after_final_native_source_removal(self):
        case, (e, a, selection) = self.fixture(N.PSYSTRIKE)
        G.grant_moves(a, ['move/사이코브레이크'], 'independent/known-move', 'feature',
            owner_id=a.entity_id, lifetime='while_owned', rule_id=N.PSYSTRIKE, tutor_points=0)
        case.acquire(e, a, N.PSYSTRIKE, selection)
        self.assertEqual(a.moves.count('move/사이코브레이크'), 1)
        case.withdraw(e, a, N.PSYSTRIKE)
        self.assertIn(e.r.resolve_move('move/사이코브레이크'), usable_moves(e, a))
        G.revoke(a, 'independent/known-move', engine=e)
        self.assertNotIn(e.r.resolve_move('move/사이코브레이크'), usable_moves(e, a))
        self.assertEqual(N.receipts(a)[0]['state'], 'ended')

    def test_native_receipt_corruption_is_rejected_without_current_rank_guessing(self):
        for uid in (N.RESILIENCE, N.INSIGHT, N.PSYSTRIKE):
            case, (e, a, selection) = self.fixture(uid)
            case.acquire(e, a, uid, selection)
            record = a.spec[G.KEY]['sources'][N._sid(a, uid)][N.KEY]
            record['snapshot']['trainer'] = False
            self.reject_unexportable(e, lambda: N.validate_actor(a), 'integrity changed')


if __name__ == '__main__':
    unittest.main()
