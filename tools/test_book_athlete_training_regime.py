"""C04-061: the five Training Regime passives at their real native boundaries.

Reuses helpers only, never a TestCase subclass. No feat, action-budget or
native completion receipts are inserted by these tests.
"""
from copy import deepcopy
from unittest.mock import patch
import unittest

import test_book_athlete_acquisition as FIX
from engine import Rules, Engine
from ruleset import RuleFilter
import arithmetic_policy as M
import athlete as AT
import movement_actions as MOVE
import passive_events as PASSIVE
import trainer_feature_acquisition as ACQUIRE


class TrainingRegimeTests(FIX.AthleteScene, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(FIX.ROOT, ruleset='core')

    def ready(self, stats=('atk', 'spe'), *, regime=True):
        self.setup(positions={'t':(1, 1), 'q':(2, 1), 'p':(8, 8)})
        self.acquire()
        if regime:
            self.acquire(AT.REGIME)
        self.exercise(stats)

    def answer(self, kind, value, unit=AT.REGIME):
        key = kind  # Rulings.decide matches a prompt type/unit string, not a mapping.
        self.e.rulings.answers = [r for r in self.e.rulings.answers if r['key'] != key]
        self.e.rulings.add_answer(key, value, reason='actual optional choice', scope='permanent')

    def push(self, actor=None, target=None, *, face=6, defender_mod=0):
        return self.e.push(actor or self.t, target or self.q, challenger_skill='육상', defender_skill='전투',
            fixed_accuracy=face, challenger_options={'fixed':[6] * 5},
            defender_options={'fixed':[1] * 4, 'mods':defender_mod})

    def test_attack_bonus_changes_actual_maneuver_hit_not_ordinary_move_or_stale_maneuver_id(self):
        self.ready()
        self.combat(self.t)
        self.assertTrue(self.push())  # 6 + 2 reaches actual AC4 + evasion4.
        self.next_turn(self.t)
        self.q.pos = (2, 1)
        ordinary = self.rules.move('move/몸통박치기')
        with patch.object(Engine, 'd20', return_value=4):
            self.assertFalse(self.e.accuracy_check(self.t, self.q, ordinary)[0])
        # A completed prior native maneuver cannot authorize a direct accuracy call.
        projected = dict(ordinary, id='maneuver/밀기', ac=4, **{'class':'변화'})
        self.assertEqual(AT.maneuver_accuracy(self.e, self.t, projected), 0)
        self.valid()

    def test_attack_requires_regime_and_current_attack_training_and_withdraws_cleanly(self):
        for trained, acquired in ((('spa', 'spe'), True), (('atk', 'spe'), False)):
            with self.subTest(trained=trained, regime=acquired):
                self.ready(trained, regime=acquired)
                self.combat(self.t)
                self.assertFalse(self.push())
        self.ready()
        self.retrain(AT.REGIME)
        self.restore()
        self.combat(self.t)
        self.assertFalse(self.push())
        self.valid()

    def test_attack_included_script_maneuver_uses_actual_native_accuracy_event(self):
        import maneuver_opposed as MANEUVER
        self.ready()
        self.combat(self.t)
        declaration = {'id':'actual-included-maneuver', 'source':'maneuver/밀기',
            'requirements':[{'id':'actual-regime', 'who':'actor',
                'condition':{'kind':'owned', 'fields':['feats'], 'names':[AT.REGIME]}, 'reason':'actual acquired actor source'}],
            'challenger_skills':['육상'], 'defender_skills':['전투'], 'resistance_purpose':'resist_push',
            'geometry':{'range':1, 'remote':False, 'vertical':False}, 'action_cost':'included',
            'accuracy':'ordinary', 'accuracy_class':'변화', 'ac':4, 'opposed':'required',
            'success':'check', 'opportunity':'none', 'effects':[]}
        result = MANEUVER.execute(self.e, self.t, self.q, declaration, challenger_skill='육상',
            defender_skill='전투', fixed_accuracy=6, challenger_options={'fixed':[6] * 5}, defender_options={'fixed':[1] * 4})
        self.assertTrue(result['success'])
        self.assertEqual(self.t._action_history, [])  # explicit script inclusion, not a budget edit

    def test_special_defense_adds_two_only_to_actual_resisting_pool_and_preserves_existing_mods(self):
        self.ready(('spd', 'spe'))
        self.combat(self.q, count=15)
        with patch.object(self.e, 'skill_roll', wraps=self.e.skill_roll) as rolls:
            self.push(self.q, self.t, face=15, defender_mod=3)
        defending = [c for c in rolls.call_args_list if c.args[0] is self.t]
        attacking = [c for c in rolls.call_args_list if c.args[0] is self.q]
        self.assertEqual(defending[0].kwargs['mods'], 5)
        self.assertEqual(attacking[0].kwargs.get('mods', 0), 0)
        self.assertEqual(self.e.skill_roll(self.t, '전투', fixed=[1] * 4, mods=3).modifier, 3)
        self.restore()
        self.valid()

    def test_special_defense_does_not_help_the_initiator_or_an_untrained_defender(self):
        self.ready(('spd', 'spe'))
        self.combat(self.t)
        with patch.object(self.e, 'skill_roll', wraps=self.e.skill_roll) as rolls:
            self.push(face=15)
        self.assertTrue(all(c.kwargs.get('mods', 0) == 0 for c in rolls.call_args_list))
        self.e.end_of_turn(self.t)
        self.e.end_round()
        self.e.end_encounter()
        self.exercise(('atk', 'spe'), reason='replace the two actual trained stats')
        self.restore()
        self.combat(self.q, count=15)
        self.q.pos = (2, 1)
        with patch.object(self.e, 'skill_roll', wraps=self.e.skill_roll) as rolls:
            self.push(self.q, self.t, face=15)
        self.assertTrue(all(c.kwargs.get('mods', 0) == 0 for c in rolls.call_args_list))

    def test_sprint_replaces_half_with_double_for_all_actual_capabilities_and_restore(self):
        self.ready(('spa', 'spe'))
        self.e.gm.set_movement_capabilities(self.t, {'land':6, 'swim':4, 'sky':0, 'burrow':0, 'levitate':0},
            basis='base', reason='actual movement capabilities')
        self.combat(self.t)
        self.assertTrue(self.e.sprint(self.t, source_policy='ch06_once'))
        self.assertEqual((MOVE.distance_budget(self.e, self.t, 'land'), MOVE.distance_budget(self.e, self.t, 'swim')), (12, 8))
        self.assertEqual(MOVE.distance_budget(self.e, self.p, 'land'), 6)
        self.restore()
        self.assertEqual(MOVE.distance_budget(self.e, self.t, 'land'), 12)
        self.valid()

    def test_sprint_without_regime_or_speed_training_remains_fifty_percent(self):
        for stats, acquired in ((('atk', 'spa'), True), (('atk', 'spe'), False)):
            with self.subTest(stats=stats, regime=acquired):
                self.ready(stats, regime=acquired)
                self.combat(self.t)
                self.assertTrue(self.e.sprint(self.t, source_policy='ch06_once'))
                self.assertEqual(MOVE.distance_budget(self.e, self.t, 'land'), 9)

    def damaging(self, *, choose=True, twisted=False):
        self.ready(('spa', 'spe'))
        self.e.gm.set_stat(self.t, 'spa', value=31, reason='actual odd staged Special Attack')
        self.e.gm.set_stat(self.q, 'hp', value=1000, reason='actual high-HP comparison target')
        self.e.gm.set_hp(self.q, value=self.q.max_hp, reason='actual healthy comparison target')
        self.e.gm.set_move(self.t, 'move/괴력', reason='actual known damaging Athlete Move')
        if twisted:
            self.e.gm.set_ability(self.t, '트위스트파워', reason='actual independent Twisted Power')
            self.answer('twisted_power', True, 'ability/트위스트파워')
        self.answer('training_regime_special_attack', choose)
        self.combat(self.t)
        return self.e.roll_damage(self.t, self.q, self.rules.move('move/괴력'), set_damage=True)

    def use(self, actor, target, move, **options):
        result=FIX.AthleteScene.use(self,actor,target,move,**options)
        if move=='move/괴력':
            import maneuver_grants as GRANTS
            for row in list(actor.custom_conditions.get(GRANTS.RECORDS,{}).values()):
                if row['source']==move and row['status']=='awaiting_input':
                    self.e.resolve_maneuver_grant(actor,row['id'],accept=False)
        return result

    def test_special_attack_optional_half_staged_value_is_native_and_not_twisted_stacked(self):
        for chosen, twisted in ((True, False), (True, True), (False, False), (False, True)):
            with self.subTest(chosen=chosen, twisted=twisted):
                baseline = self.damaging(choose=chosen, twisted=twisted)
                hp = self.q.hp
                self.use(self.t, self.q, 'move/괴력')
                bonus = M.ratio(self.t.staged('spa'), 2) if chosen or twisted else 0
                self.assertEqual(hp - self.q.hp, baseline + bonus)
                row = next(r for r in self.e._move_completions.values() if r['actor'] is self.t)
                self.assertEqual(row['athlete_regime']['enabled'], chosen)
                self.assertEqual(row.get('twisted_power', False), twisted and not chosen)
                self.restore()
                self.valid()

    def test_special_attack_does_not_leak_to_non_athlete_or_status_move_and_invalid_choice_is_atomic(self):
        self.damaging(choose=True)
        baseline = self.e.roll_damage(self.t, self.q, self.rules.move('move/몸통박치기'), set_damage=True)
        hp = self.q.hp
        self.use(self.t, self.q, 'move/몸통박치기')
        self.assertEqual(hp - self.q.hp, baseline)
        self.next_turn(self.t)
        self.answer('training_regime_special_attack', 'yes')
        self.rejected(lambda:self.use(self.t, self.q, 'move/괴력'), 'explicit Training Regime')
        self.valid()

    def test_special_attack_untrained_and_withdrawn_feature_and_status_moves_do_not_prompt(self):
        self.ready(('spa', 'spe'))
        self.answer('training_regime_special_attack', 'invalid-if-read')
        self.combat(self.t)
        self.use(self.t, self.q, 'move/블록')
        self.assertNotIn('athlete_regime', list(self.e._move_completions.values())[-1])
        self.ready(('atk', 'spe'))
        self.answer('training_regime_special_attack', 'invalid-if-read')
        self.combat(self.t)
        self.use(self.t, self.q, 'move/괴력')
        self.assertNotIn('athlete_regime', list(self.e._move_completions.values())[-1])
        self.e.end_encounter()
        self.exercise(('spa', 'spe'), reason='actual new trained stats')
        self.retrain(AT.REGIME)
        self.restore()
        self.combat(self.t)
        self.use(self.t, self.q, 'move/괴력')
        self.assertNotIn('athlete_regime', list(self.e._move_completions.values())[-1])
        self.valid()

    def intercept(self, *, cold=False, version=None, stats=('def', 'spe'), faces=6):
        if version is not None:
            self.rules = Rules(FIX.ROOT, ruleset='core')
            self.rules.ruleset = RuleFilter({'sources':['core'], 'unit_versions':{AT.REGIME:version}})
            self.rules._apply_ruleset()
        self.setup(positions={'t':(3, 5), 'p':(3, 2), 'q':(2, 2)})
        self.acquire()
        self.acquire(AT.REGIME)
        self.exercise(stats)
        self.e.gm.set_stat(self.q, 'atk', value=40, reason='actual attacker stat')
        baseline = self.e.roll_damage(self.q, self.t, self.rules.move('move/막치기'), set_damage=True)
        hp = (self.t.hp, self.p.hp)
        self.e.watch_move_defense(self.p, [{'actor_id':self.t.entity_id, 'source':'maneuver/근접-가로채기'}],
            reason='actual ally Intercept declaration')
        self.combat(self.q, count=15)
        with patch.object(Engine, 'd20', return_value=10), self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.q, self.p, 'move/막치기', set_damage=True)
        if cold:
            self.restore()
        event = self.e._passive_pending
        self.e.choose_move_defense(event, self.t, use=True, options={
            'path':[(3, 5), (3, 4), (3, 3), (3, 2)], 'skill':'육상', 'mode':'land',
            'shove_destination':[4, 2], 'roll_options':{'fixed':[faces] * 5}}, reason='actual ally Intercept choice')
        return baseline, hp

    def test_defense_reduces_only_actual_intercept_korean_six_and_original_core_five_cold_restore(self):
        for version, reduction in ((None, 6), ('ptu-core-1.05', 5)):
            with self.subTest(version=version):
                baseline, hp = self.intercept(cold=True, version=version)
                self.assertEqual((hp[0] - self.t.hp, self.p.hp), (baseline - reduction, hp[1]))
                self.assertEqual(self.t._action_history, ['extended', 'full'])  # Actual prior exercise remains recorded.
                self.restore()
                self.valid()

    def test_defense_does_not_reduce_ordinary_damage_fake_intercept_or_untrained_intercept(self):
        baseline, hp = self.intercept(stats=('atk', 'spe'))
        self.assertEqual(hp[0] - self.t.hp, baseline)
        self.ready(('def', 'spe'))
        baseline = self.e.roll_damage(self.q, self.t, self.rules.move('move/막치기'), set_damage=True)
        hp = self.t.hp
        self.e.resolve_attack_damage(self.q, self.t, self.rules.move('move/막치기'), set_damage=True, intercepted=True)
        self.assertEqual(hp - self.t.hp, baseline)
        self.assertEqual(AT.intercept_reduction(self.e, self.t, {'target':self.t, 'intercepted':True}), 0)

    def test_failed_native_intercept_does_not_apply_reduction_to_the_protected_ally(self):
        baseline, hp = self.intercept(faces=1)
        ordinary = self.e.roll_damage(self.q, self.p, self.rules.move('move/막치기'), set_damage=True)
        self.assertEqual((self.t.hp, hp[1] - self.p.hp), (hp[0], ordinary))
        self.valid()

    def test_defense_also_reduces_real_ranged_intercept_special_damage(self):
        self.setup(positions={'t':(4, 5), 'p':(6, 2), 'q':(2, 2)})
        self.acquire()
        self.acquire(AT.REGIME)
        self.exercise(('def', 'spe'))
        self.e.gm.set_move(self.q, 'move/불꽃세례', reason='actual known ranged attack')
        self.e.gm.set_stat(self.q, 'spa', value=40, reason='actual special attacker')
        base = self.e.roll_damage(self.q, self.t, self.rules.move('move/불꽃세례'), set_damage=True)
        hp = (self.t.hp, self.p.hp)
        self.e.watch_move_defense(self.p, [{'actor_id':self.t.entity_id, 'source':'maneuver/원거리-가로채기'}], reason='actual ranged Intercept offer')
        self.combat(self.q, count=15)
        with patch.object(Engine, 'd20', return_value=10), self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.q, self.p, 'move/불꽃세례', set_damage=True)
        self.e.choose_move_defense(self.e._passive_pending, self.t, use=True, options={
            'path':[(4, 5), (4, 4), (4, 3), (4, 2)], 'skill':'육상', 'mode':'land',
            'roll_options':{'fixed':[6] * 5}}, reason='actual successful ranged Intercept')
        self.assertEqual((hp[0] - self.t.hp, self.p.hp), (base - 6, hp[1]))
        self.restore()
        self.valid()

    def test_defense_ally_switch_recipient_is_not_an_actual_intercept(self):
        import warper as WP
        self.ready(('def', 'spe'))
        self.e.gm.set_position(self.t, (3, 2), reason='actual receiving Athlete ally')
        self.e.gm.set_position(self.q, (5, 2), reason='actual incoming ranged foe')
        self.u = self.add('actual acquired Warper', 'trainer', (2, 2), classes=[], feats=[],
            edges=['edge/원소-교감'], edge_choices={'edge/원소-교감':'에스퍼'}, exp_bank=100,
            skills={'교활':6, '집중':3, '전투':2, '육상':3, '곡예':3, '직감':3, '오컬트학':3})
        for feature in (WP.CLASS, WP.SPACE):
            ACQUIRE.acquire_static(self.e, self.u, feature, acquisition_request_id='actual-warper/' + feature)
        self.e.gm.set_move(self.q, 'move/물대포', reason='actual incoming attack')
        ordinary = self.e.roll_damage(self.q, self.t, self.rules.move('move/물대포'), set_damage=True)
        hp = (self.t.hp, self.u.hp)
        self.combat(self.u)
        self.e.arm_warper_move(self.u, WP.SWITCH, ally=self.t, willing=True)
        self.e.end_of_turn(self.u)
        self.e.start_of_turn(self.q, initiative_count=15)
        with patch.object(Engine, 'd20', return_value=10):
            self.e.use_move(self.q, self.u, 'move/물대포', set_damage=True)
        self.assertEqual((hp[0] - self.t.hp, self.u.hp), (ordinary, hp[1]))
        self.assertEqual((self.t.pos, self.u.pos), ((2, 2), (3, 2)))
        self.restore()
        self.valid()

    def test_source_versions_are_independent_explicit_and_unknown_versions_reject_acquisition(self):
        import pokemon_move_edges as EDGES
        self.rules = Rules(FIX.ROOT, ruleset='core')
        self.rules.ruleset = RuleFilter({'sources':['core'], 'unit_versions':{AT.REGIME:'ptu-core-1.05', EDGES.INCANDESCENCE:'september-2015'}})
        self.rules._apply_ruleset()
        self.setup()
        self.acquire()
        receipt = self.acquire(AT.REGIME)
        self.assertEqual(receipt['source']['behavior_source'], {'version':'ptu-core-1.05', 'intercept_reduction':5})
        self.assertEqual(EDGES.incandescence_source(self.rules)['version'], 'september-2015')
        self.restore()
        self.valid()
        self.retrain(AT.REGIME)
        self.rules = Rules(FIX.ROOT, ruleset='core')
        self.rules.ruleset = RuleFilter({'sources':['core'], 'unit_versions':{AT.REGIME:'unknown'}})
        self.rules._apply_ruleset()
        self.setup()
        self.acquire()
        self.rejected(lambda:self.acquire(AT.REGIME, request='different-unknown-source'), 'unknown Training Regime')


if __name__ == '__main__':
    unittest.main()
