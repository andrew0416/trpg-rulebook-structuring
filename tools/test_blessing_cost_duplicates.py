"""Source-bound Signs and historical supplemental/CSV alias regressions."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import patch

STAGE = Path(__file__).resolve().parents[1]
ROOT = STAGE if (STAGE / 'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT', r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0] = [str(STAGE / 'engine'), str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Rules
from ruleset import RuleFilter, ExcludedRuleSelection
import action_points as AP
import blessing_skill_features as B
import blessing_skill_rules as SKILL
import class_passive_combat as PASSIVE
import items
import native_acquisition_adapters as ADMISSION
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import turn
import tools.test_category2_blessing_skill_rules_ten as SKILL_FIXTURE
import tools.test_native_acquisition_adapters as NATIVE_FIXTURE
import tools.test_blessing_authority_repair as INSIGHT_FIXTURE


class BlessingCostDuplicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset='all')

    def skill_case(self, gift=None, role='contractor'):
        case = SKILL_FIXTURE.BlessingSkillRuleTests('runTest')
        case.rules = self.rules
        case.setUp()
        if gift is not None:
            config = {'role': role} if gift in (SKILL.ANCIENT_WISDOM, SKILL.PARAGON) else None
            if gift == SKILL.PARAGON:
                config['category'] = 'mental'
            case.own(gift, configuration=config)
        return case.e, case.a

    def resilience(self, role='contractor'):
        case = NATIVE_FIXTURE.NativeAcquisitionAdapterTests('runTest')
        case.rules = self.rules
        engine, actor, selection = case.fixture(ADMISSION.RESILIENCE, role=role)
        case.acquire(engine, actor, ADMISSION.RESILIENCE, selection)
        return engine, actor

    def begin(self, engine, actor):
        if not engine.encounter_active:
            engine.begin_encounter(engine.everyone)
        engine.start_round(engine.everyone)
        engine.start_of_turn(actor, initiative_count=20)

    def next_turn(self, engine, actor):
        engine.end_of_turn(actor)
        engine.end_round()
        self.begin(engine, actor)

    def activate(self, engine, actor, gift):
        if gift == ADMISSION.RESILIENCE:
            return engine.activate_blessed_resilience(actor, '불꽃')
        return engine.activate_blessing_skill_rule(actor, gift, reason='actual source-bound Sign')

    def fixture(self, gift):
        engine, actor = self.resilience() if gift == ADMISSION.RESILIENCE else self.skill_case(gift)
        self.begin(engine, actor)
        return engine, actor

    def restore(self, engine, actor, mode):
        if mode == 'gm':
            engine.gm.snapshot('blessing-cost')
            engine.gm.restore('blessing-cost', reason='restore actual paid Sign or alias history')
            return engine, actor
        restored = CODEC.load_engine(self.rules, json.loads(json.dumps(CODEC.dump_engine(engine), ensure_ascii=False)))
        return restored, next(value for value in restored.everyone if value.entity_id == actor.entity_id)

    def reject(self, engine, operation, pattern):
        return NATIVE.assert_rejected_unchanged(engine, operation, reason_pattern=pattern)

    def test_each_sign_pays_one_ap_own_action_and_independent_scene_quota(self):
        for gift, action in ((SKILL.ANCIENT_WISDOM, 'free'), (SKILL.PARAGON, 'swift'), (ADMISSION.RESILIENCE, 'standard')):
            with self.subTest(gift=gift):
                engine, actor = self.fixture(gift)
                ap = AP.available(actor)
                history = list(actor._action_history)
                self.activate(engine, actor, gift)
                self.assertEqual(AP.available(actor), ap - 1)
                self.assertEqual(actor._action_history, history + [action])
                entry = actor.spec['frequency_state']['activations']['blessing-sign:' + gift]
                self.assertEqual(entry['used'], 1)
                self.assertEqual(entry['kind'], 'scene')
                if gift == ADMISSION.RESILIENCE:
                    receipt = actor.spec[PASSIVE.STATE]['contractor']
                else:
                    receipt = actor.spec[SKILL.STATE]['activations'][gift]
                self.assertEqual(receipt['ap'], 1)
                self.assertEqual(receipt['cost_source']['file'], 'supp-blessings.md')
                self.assertEqual(receipt['cost_source']['lines'], [248, 270])
        engine, actor = self.skill_case(SKILL.ANCIENT_WISDOM)
        actor.spec['gifts'].append(SKILL.PARAGON)
        engine.confirm_blessing_gift(actor, SKILL.PARAGON, reason='independent acquired Sign',
                                    configuration={'role': 'contractor', 'category': 'mental'})
        self.begin(engine, actor)
        ap = AP.available(actor)
        self.activate(engine, actor, SKILL.ANCIENT_WISDOM)
        self.activate(engine, actor, SKILL.PARAGON)
        self.assertEqual(AP.available(actor), ap - 2)

    def test_ancient_wisdom_consumes_only_successful_bound_check_and_no_same_scene_rearm(self):
        engine, actor = self.fixture(SKILL.ANCIENT_WISDOM)
        engine.gm.set_skill(actor, '오컬트학', 7, reason='actual seven-die skill')
        self.activate(engine, actor, SKILL.ANCIENT_WISDOM)
        self.assertEqual(len(engine.skill_roll(actor, '기술학', fixed=[2] * 3).faces), 3)
        self.reject(engine, lambda: engine.skill_roll(actor, '오컬트학', fixed=[2] * 8), 'fixed|dice|faces')
        self.assertEqual(actor.spec[SKILL.STATE]['activations'][SKILL.ANCIENT_WISDOM]['status'], 'pending')
        self.assertEqual(len(engine.skill_roll(actor, '오컬트학', fixed=[2] * 9).faces), 9)
        self.assertEqual(len(engine.skill_roll(actor, '오컬트학', fixed=[2] * 7).faces), 7)
        self.next_turn(engine, actor)
        self.reject(engine, lambda: self.activate(engine, actor, SKILL.ANCIENT_WISDOM), 'already used this scene')

    def test_each_sign_ap_shortage_and_late_payment_failure_leave_full_world_unchanged(self):
        for gift in (SKILL.ANCIENT_WISDOM, SKILL.PARAGON, ADMISSION.RESILIENCE):
            with self.subTest(gift=gift):
                engine, actor = self.fixture(gift)
                AP.charge(actor, AP.available(actor), mode='spend')
                self.reject(engine, lambda: self.activate(engine, actor, gift), 'one available AP')
                engine, actor = self.fixture(gift)
                original = AP.charge
                def failed_payment(owner, amount, **kwargs):
                    original(owner, amount, **kwargs)
                    raise ValueError('late Sign payment failure')
                with patch.object(AP, 'charge', side_effect=failed_payment):
                    self.reject(engine, lambda: self.activate(engine, actor, gift), 'late Sign payment failure')

    def test_action_failures_do_not_spend_ap_or_frequency_and_shift_is_not_swift(self):
        engine, actor = self.fixture(SKILL.PARAGON)
        for action in ('swift', 'standard'):
            self.assertTrue(turn.spend(engine, actor, action, SKILL.PARAGON))
        self.assertEqual(actor.budget['shift'], 1)
        self.reject(engine, lambda: self.activate(engine, actor, SKILL.PARAGON), 'action is unavailable')
        engine, actor = self.fixture(SKILL.ANCIENT_WISDOM)
        engine.lose_hp(actor, actor.hp, source=SKILL.ANCIENT_WISDOM, loss_kind='loss')
        self.reject(engine, lambda: self.activate(engine, actor, SKILL.ANCIENT_WISDOM), 'action is unavailable')
        engine, actor = self.fixture(ADMISSION.RESILIENCE)
        self.assertTrue(turn.spend(engine, actor, 'standard', ADMISSION.RESILIENCE))
        before = (deepcopy(actor.spec), deepcopy(actor.budget), list(actor._action_history), engine.rng.getstate())
        self.assertEqual(self.activate(engine, actor, ADMISSION.RESILIENCE), (0, 1))
        self.assertEqual((actor.spec, actor.budget, actor._action_history, engine.rng.getstate()), before)

    def test_three_signs_restore_paid_quota_then_refresh_at_actual_scene_boundary(self):
        for gift in (SKILL.ANCIENT_WISDOM, SKILL.PARAGON, ADMISSION.RESILIENCE):
            for mode in ('json', 'gm'):
                with self.subTest(gift=gift, mode=mode):
                    engine, actor = self.fixture(gift)
                    self.activate(engine, actor, gift)
                    if gift == SKILL.ANCIENT_WISDOM:
                        engine.skill_roll(actor, '오컬트학', fixed=[2] * 5)
                    ap = AP.available(actor)
                    engine, actor = self.restore(engine, actor, mode)
                    self.assertEqual(AP.available(actor), ap)
                    self.next_turn(engine, actor)
                    self.reject(engine, lambda: self.activate(engine, actor, gift), 'already used this scene')
                    engine.end_of_turn(actor)
                    engine.end_scene(engine.everyone)
                    self.begin(engine, actor)
                    before = AP.available(actor)
                    self.activate(engine, actor, gift)
                    self.assertEqual(AP.available(actor), before - 1)

    def test_pending_ancient_wisdom_survives_both_restores_and_consumes_once(self):
        for mode in ('json', 'gm'):
            engine, actor = self.fixture(SKILL.ANCIENT_WISDOM)
            self.activate(engine, actor, SKILL.ANCIENT_WISDOM)
            engine, actor = self.restore(engine, actor, mode)
            ap = AP.available(actor)
            self.assertEqual(len(engine.skill_roll(actor, '오컬트학', fixed=[2] * 5).faces), 5)
            self.assertEqual(len(engine.skill_roll(actor, '오컬트학', fixed=[2] * 3).faces), 3)
            self.assertEqual(AP.available(actor), ap)

    def test_paragon_fixed_category_and_acquisition_history_survive_later_prerequisite_loss(self):
        engine, actor = self.fixture(SKILL.PARAGON)
        acquisition = deepcopy(actor.spec['_blessing_gift_approvals'][SKILL.PARAGON]['acquisition'])
        actor.spec['feats'] = []
        self.activate(engine, actor, SKILL.PARAGON)
        for mode in ('gm', 'json'):
            engine, actor = self.restore(engine, actor, mode)
            self.assertEqual(actor.spec['_blessing_gift_approvals'][SKILL.PARAGON]['acquisition'], acquisition)
            self.assertEqual(engine.skill_roll(actor, '기술학', fixed=[2] * 3).modifier, 1)
            self.assertEqual(engine.skill_roll(actor, '매력', fixed=[2] * 3).modifier, 0)
            self.reject(engine, lambda: engine.confirm_blessing_gift(actor, SKILL.PARAGON,
                reason='same gift cannot choose another group', configuration={'role': 'contractor', 'category': 'spirit'}),
                'already recorded')

    def test_resilience_invalid_choice_rejects_then_actual_damage_uses_only_paid_type(self):
        engine, actor = self.resilience()
        self.begin(engine, actor)
        self.reject(engine, lambda: engine.activate_blessed_resilience(actor, '전기'), 'eligible patron type')
        attacker = next(value for value in engine.everyone if value is not actor)
        move = self.rules.move('move/화염방사')
        ordinary = engine.roll_damage(attacker, actor, move, set_damage=True)
        ap = AP.available(actor)
        self.activate(engine, actor, ADMISSION.RESILIENCE)
        self.assertLess(engine.roll_damage(attacker, actor, move, set_damage=True), ordinary)
        self.assertEqual(AP.available(actor), ap - 1)
        self.next_turn(engine, actor)
        self.reject(engine, lambda: engine.activate_blessed_resilience(actor, '물'), 'already used this scene')
        self.assertEqual(PASSIVE.resistance_steps(engine, actor, '불꽃'), 1)
        self.assertEqual(PASSIVE.resistance_steps(engine, actor, '물'), 0)
        engine.end_of_turn(actor)
        engine.end_scene(engine.everyone)
        self.begin(engine, actor)
        engine.activate_blessed_resilience(actor, '물')
        self.assertEqual(PASSIVE.resistance_steps(engine, actor, '불꽃'), 0)
        self.assertEqual(PASSIVE.resistance_steps(engine, actor, '물'), 1)

    def test_messiah_controls_keep_free_static_effects_and_reject_sign_activation(self):
        for gift in (SKILL.ANCIENT_WISDOM, SKILL.PARAGON, ADMISSION.RESILIENCE):
            engine, actor = self.resilience('messiah') if gift == ADMISSION.RESILIENCE else self.skill_case(gift, 'messiah')
            self.begin(engine, actor)
            ap = AP.available(actor)
            if gift == SKILL.ANCIENT_WISDOM:
                for skill in ('오컬트학', '생존'):
                    engine.gm.set_skill(actor, skill, 7, reason='actual seven-die educational skill')
                    result = engine.skill_roll(actor, skill, fixed=[2] * 8,
                        skill_context={'purpose': 'occult_topic', 'reason': 'occult survival knowledge'})
                    self.assertEqual(len(result.faces), 8)
            elif gift == SKILL.PARAGON:
                self.assertEqual(engine.skill_roll(actor, '기술학', fixed=[2] * 3).modifier, 2)
            else:
                self.assertEqual(PASSIVE.resistance_steps(engine, actor, '불꽃'), 1)
                self.assertEqual(PASSIVE.resistance_steps(engine, actor, '물'), 1)
            self.assertEqual(AP.available(actor), ap)
            self.reject(engine, lambda: self.activate(engine, actor, gift), 'Contractor')

    def test_selected_sign_authority_cannot_be_bypassed_by_an_approved_gift(self):
        for gift in (SKILL.ANCIENT_WISDOM, SKILL.PARAGON, ADMISSION.RESILIENCE):
            engine, actor = self.fixture(gift)
            ap, history, rng = AP.available(actor), list(actor._action_history), engine.rng.getstate()
            old = self.rules.ruleset
            try:
                self.rules.ruleset = RuleFilter({'sources': ['core', 'errata', 'fantasy', 'blessings'], 'exclude_units': [B.SIGNER]})
                self.rules._apply_ruleset()
                with self.assertRaises((ValueError, ExcludedRuleSelection)):
                    self.activate(engine, actor, gift)
                self.assertEqual((AP.available(actor), actor._action_history, engine.rng.getstate()), (ap, history, rng))
            finally:
                self.rules.ruleset = old
                self.rules._apply_ruleset()

    def alias_case(self, supplement, csv, order):
        engine, actor = self.skill_case()
        for gift in ((supplement, csv) if order == 'supplement_first' else (csv, supplement)):
            actor.spec.setdefault('gifts', []).append(gift)
            if gift == csv:
                actor.spec.setdefault('gift_patrons', {})[gift] = '메로엣타' if csv == SKILL.DAZZLING_STAGE else '디안시'
            engine.confirm_blessing_gift(actor, gift, reason='preserve this actual historical representation')
        return engine, actor

    def test_stage_aliases_apply_once_for_both_acquisition_orders_and_rank_seven_plus(self):
        self.enterContext(patch.object(self.rules, 'rulings', deepcopy(self.rules.rulings)))
        for declared in (7, 8):
            self.rules.rulings.set_mech('gameplay/skill-rank-dice', 'by_rank_name.선언랭크' + str(declared),
                {'rank': declared, 'dice': str(declared) + 'd6', 'eng': 'Declared Rank ' + str(declared)},
                reason='explicit campaign ranks for the stage bonus boundary', rules=self.rules)
        for order in ('supplement_first', 'csv_first'):
            for rank in (4, 7, 8):
                engine, actor = self.alias_case(B.STAGE, SKILL.DAZZLING_STAGE, order)
                engine.gm.set_skill(actor, '교활', rank, reason='observed social rank')
                history = deepcopy(actor.spec['_blessing_gift_approvals'])
                for purpose in ('singing', 'dancing'):
                    result = engine.skill_roll(actor, '매력', fixed=[2] * 3,
                        skill_context={'purpose': purpose, 'reason': 'actual social performance'})
                    self.assertEqual(result.modifier, rank // 2)
                self.assertEqual(engine.skill_roll(actor, '매력', fixed=[2] * 3).modifier, 0)
                self.assertEqual(engine.skill_roll(actor, '기술학', fixed=[2] * 3,
                    skill_context={'purpose': 'singing', 'reason': 'not a social check'}).modifier, 0)
                self.assertEqual(actor.spec['_blessing_gift_approvals'], history)

    def test_royal_aliases_apply_one_bonus_for_all_six_exact_korean_shards(self):
        for order in ('supplement_first', 'csv_first'):
            for colour, skill in SKILL.SHARDS.items():
                engine, actor = self.alias_case(B.ROYAL, SKILL.ROYAL_PRIVILEGE, order)
                self.assertEqual(engine.skill_roll(actor, skill).modifier, 0)
                actor.spec.setdefault('items', {})[colour + '조각'] = 1
                items.register_item(engine, actor, colour + '조각')
                history = deepcopy(actor.spec['_blessing_gift_approvals'])
                self.assertEqual(engine.skill_roll(actor, skill).modifier, 2)
                self.assertEqual(engine.skill_roll(actor, '생존').modifier, 0)
                self.assertEqual(actor.spec['_blessing_gift_approvals'], history)

    def test_aliases_survive_both_restores_and_either_live_representation_can_be_removed(self):
        for supplement, csv in ((B.STAGE, SKILL.DAZZLING_STAGE), (B.ROYAL, SKILL.ROYAL_PRIVILEGE)):
            for mode in ('json', 'gm'):
                for removed in (supplement, csv):
                    engine, actor = self.alias_case(supplement, csv, 'supplement_first')
                    if supplement == B.ROYAL:
                        actor.spec.setdefault('items', {})['빨강조각'] = 1
                        items.register_item(engine, actor, '빨강조각')
                    else:
                        engine.gm.set_skill(actor, '교활', 4, reason='four-die social maximum')
                    history = deepcopy(actor.spec['_blessing_gift_approvals'])
                    engine, actor = self.restore(engine, actor, mode)
                    context = {'purpose': 'singing', 'reason': 'actual social performance'}
                    self.assertEqual(engine.skill_roll(actor, '협박', skill_context=context).modifier, 2)
                    actor.spec['gifts'].remove(removed)
                    self.assertEqual(engine.skill_roll(actor, '협박', skill_context=context).modifier, 2)
                    self.assertEqual(actor.spec['_blessing_gift_approvals'], history)

    def test_alias_precedence_never_bypasses_missing_approval_or_wrong_patron(self):
        for supplement, csv in ((B.STAGE, SKILL.DAZZLING_STAGE), (B.ROYAL, SKILL.ROYAL_PRIVILEGE)):
            engine, actor = self.skill_case()
            actor.spec['gifts'] = [supplement, csv]
            engine.confirm_blessing_gift(actor, supplement, reason='actual supplement approval')
            # Invalid historical state is not codec-exportable, so compare raw state.
            before = deepcopy(actor.spec), engine.rng.getstate()
            with self.assertRaisesRegex(ValueError, 'GM permission'):
                engine.skill_roll(actor, '협박', skill_context={'purpose': 'singing', 'reason': 'actual performance'})
            self.assertEqual((actor.spec, engine.rng.getstate()), before)
            actor.spec.setdefault('gift_patrons', {})[csv] = '뮤'
            before = deepcopy(actor.spec), engine.rng.getstate()
            with self.assertRaisesRegex(ValueError, 'granting patron contradicts'):
                engine.confirm_blessing_gift(actor, csv, reason='generic permission is not a patron waiver')
            self.assertEqual((actor.spec, engine.rng.getstate()), before)

    def test_aliases_require_both_selected_sources_without_cross_version_fallback(self):
        for supplement, csv in ((B.STAGE, SKILL.DAZZLING_STAGE), (B.ROYAL, SKILL.ROYAL_PRIVILEGE)):
            for excluded in (B.SOURCES[supplement], csv):
                engine, actor = self.alias_case(supplement, csv, 'csv_first')
                before = deepcopy(actor.spec), engine.rng.getstate()
                old = self.rules.ruleset
                try:
                    self.rules.ruleset = RuleFilter({'sources': ['core', 'errata', 'fantasy', 'blessings'],
                                                    'exclude_units': [excluded]})
                    self.rules._apply_ruleset()
                    with self.assertRaises((ValueError, ExcludedRuleSelection)):
                        engine.skill_roll(actor, '협박', skill_context={'purpose': 'singing', 'reason': 'actual performance'})
                    self.assertEqual((actor.spec, engine.rng.getstate()), before)
                finally:
                    self.rules.ruleset = old
                    self.rules._apply_ruleset()

    def test_insight_existing_role_cost_selection_and_both_restore_paths_are_preserved(self):
        fixture = INSIGHT_FIXTURE.BlessingAuthorityTests('runTest')
        fixture.rules = self.rules
        for role in ('계약자', '메시아'):
            for mode in ('json', 'gm'):
                case = fixture.insight(role)
                ap = AP.available(case.a)
                selection = {'weakness': '빛'} if role == '계약자' else None
                result = fixture.observe(case, selection)
                self.assertEqual(result['values'], {'weakness': '빛', 'aligned': True, 'harms_patron_followers': False}
                                 if role == '계약자' else INSIGHT_FIXTURE.VALUES)
                self.assertEqual(AP.available(case.a), ap - (role == '계약자'))
                case.e, case.a = self.restore(case.e, case.a, mode)
                case.t = next(value for value in case.e.everyone if value.entity_id == case.t.entity_id)
                fixture.next_turn(case)
                fixture.reject(case, lambda: fixture.observe(case, selection), 'frequency exhausted')


if __name__ == '__main__':
    unittest.main()
