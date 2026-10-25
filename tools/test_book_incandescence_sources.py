"""C04-061 source branches: original Core, official September, adopted errata.

All Type Ace acquisitions, Bind AP, attacks, teaching hours/TP, Ability grants
and prerequisite refunds use native owners. Only scene helpers are reused.
"""
from unittest.mock import patch
import unittest

import test_book_type_ace_acquisition as FIX
import test_book_type_ace_passives as HELPERS
from engine import Rules, Engine
from ruleset import RuleFilter
from builder import build_pokemon, species_lookup, STATS
import arithmetic_policy as M
import growth_stats as GS
import pokemon_move_edges as EDGES
import state_grants as G
import type_ace as TA


class IncandescenceSourceTests(unittest.TestCase):
    setUp = FIX.TypeAceAcquisitionTests.setUp
    setup = FIX.TypeAceAcquisitionTests.setup
    add = FIX.TypeAceAcquisitionTests.add
    acquire = FIX.TypeAceAcquisitionTests.acquire
    combat = FIX.TypeAceAcquisitionTests.combat
    next_turn = FIX.TypeAceAcquisitionTests.next_turn
    communication = FIX.TypeAceAcquisitionTests.communication
    rejected = FIX.TypeAceAcquisitionTests.rejected
    restore = FIX.TypeAceAcquisitionTests.restore
    valid = FIX.TypeAceAcquisitionTests.valid
    family = HELPERS.TypeAcePassiveTests.family
    attack = HELPERS.TypeAcePassiveTests.attack
    suppress = HELPERS.TypeAcePassiveTests.suppress

    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(FIX.ROOT, ruleset='core')

    def version(self, selected=None, regime=None):
        self.rules = Rules(FIX.ROOT, ruleset='core')
        versions = {} if selected is None else {EDGES.INCANDESCENCE:selected}
        if regime is not None:
            versions['feat/훈련-상황'] = regime
        self.rules.ruleset = RuleFilter({'sources':['core'], 'unit_versions':versions})
        self.rules._apply_ruleset()
        self.setup()
        self.family('불꽃', 'Brightest Flame', 'Incandescence')

    def answer(self,key,value):
        HELPERS.TypeAcePassiveTests.answer(self,key['type'] if isinstance(key,dict) else key,value)

    def learner(self, *, level=30, attack=5, special=5, speed=None):
        spec = build_pokemon(self.rules, '피츄', level, name='actual source-selected Mixed Power learner',
            moves=[], abilities=[], extra={'trainer_id':self.t.entity_id, 'tutor_points':8})
        points = level + 10
        investment = dict.fromkeys(STATS, 0)
        investment.update(atk=attack, spa=special, spe=points - attack - special if speed is None else speed)
        plan = GS.compose(species_lookup(self.rules, '피츄')['base_stats'], investment,
            points=points, rules=self.rules, strategy='balanced')
        spec.update(stats=plan['stats'], initial_allocation=plan)
        self.p = FIX.Combatant(self.rules, spec)
        self.e.gm.add_combatant(self.p, pos=(6, 6), side='party', reason='actual ordinary level-up investment sheet')
        FIX.prepare_body(self.e, self.p, size=spec['size'], offsets=[(0, 0)], reason='actual built Pokemon body')
        self.e.gm.set_types(self.p, ['불꽃'], reason='actual Fire Pokemon')
        self.e.gm.observe_loyalty(self.p, 6, reason='actual willing Pokemon')
        self.e.gm.set_position(self.b, (7, 6), reason='actual adjacent foe')
        for stat in ('def','spd'):
            self.e.gm.set_stat(self.b,stat,value=1,reason='actual low defense keeps comparison above the minimum-damage clamp')
        for mid in ('move/불꽃펀치', 'move/불꽃세례', 'move/몸통박치기'):
            self.e.gm.set_move(self.p, mid, reason='actual known native attack')
        self.communication()

    def bind(self):
        self.combat(self.t)
        TA.activate(self.e, self.t, self.p, 'Incandescence')
        self.next_turn(self.p)

    def baseline(self, move):
        return self.e.roll_damage(self.p, self.b, self.rules.move(move), set_damage=True)

    def hit(self, move, expected):
        hp = self.b.hp
        self.attack(self.p, self.b, move)
        self.assertEqual(hp - self.b.hp, expected)

    def test_original_core_adds_both_full_staged_stats_for_physical_and_special_without_twisted(self):
        self.version('ptu-core-1.05')
        self.learner(attack=12)
        self.e.gm.set_ability(self.p, '트위스트파워', reason='actual independent Ability')
        self.answer({'type':'twisted_power', 'unit':'ability/트위스트파워', 'actor':self.p.name}, True)
        self.e.gm.set_stage(self.p, 'atk', value=1, reason='actual Attack stage')
        self.e.gm.set_stage(self.p, 'spa', value=2, reason='actual Special Attack stage')
        baselines = {mid:self.baseline(mid) for mid in ('move/불꽃펀치', 'move/불꽃세례')}
        self.bind()
        for mid, other in (('move/불꽃펀치', 'spa'), ('move/불꽃세례', 'atk')):
            self.hit(mid, baselines[mid] + self.p.staged(other))
            row = list(self.e._move_completions.values())[-1]
            self.assertFalse(row['twisted_power'])
            self.next_turn(self.p)
        self.restore()
        self.valid()

    def test_official_conditional_effect_is_half_other_without_receipt_and_not_a_permanent_ability_grant(self):
        self.version('september-2015')
        self.learner(attack=12)
        bases = {mid:self.baseline(mid) for mid in ('move/불꽃펀치', 'move/불꽃세례', 'move/몸통박치기')}
        self.answer({'type':'twisted_power', 'unit':'ability/트위스트파워', 'actor':self.p.name}, True)
        self.bind()
        self.assertNotIn('트위스트파워', self.p.abilities)
        for mid, other in (('move/불꽃펀치', 'spa'), ('move/불꽃세례', 'atk'), ('move/몸통박치기', None)):
            self.hit(mid, bases[mid] + (M.ratio(self.p.staged(other), 2) if other else 0))
            self.next_turn(self.p)
        self.restore()
        self.assertFalse(EDGES.official_mixed_power(self.p))
        self.valid()

    def test_official_conditional_ability_choice_can_decline_and_cold_native_continuation_never_reasks(self):
        import passive_events as PASSIVE
        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                self.version('september-2015')
                self.learner(attack=12)
                plain = self.baseline('move/불꽃펀치')
                key = {'type':'twisted_power', 'unit':'ability/트위스트파워', 'actor':self.p.name}
                self.answer(key, accepted)
                self.bind()
                self.e.gm.set_ability(self.b, '회피', reason='actual independently acquired Dodge Ability')
                self.e.watch_move_defense(self.b, [{'actor_id':self.b.entity_id, 'source':'ability/회피'}], reason='actual native defense continuation')
                hp = self.b.hp
                with self.assertRaises(PASSIVE.PassiveEventPending):
                    self.attack(self.p, self.b, 'move/불꽃펀치')
                self.restore()
                self.answer(key, not accepted)  # cannot rechoose an already declared native activation
                self.e.choose_move_defense(self.e._passive_pending, self.b, use=False, options={}, reason='decline actual Dodge')
                self.assertEqual(hp - self.b.hp, plain + (M.ratio(self.p.staged('spa'), 2) if accepted else 0))
                self.assertEqual(list(self.e._move_completions.values())[-1]['twisted_power'], accepted)
                self.assertNotIn('트위스트파워', self.p.abilities)
                self.valid()

    def test_official_mixed_power_is_real_level_up_qualified_tp_hour_ability_and_entire_stats_when_bound(self):
        self.version('september-2015')
        self.learner(attack=12)  # un-staged attacks differ by seven, valid September, invalid adopted.
        self.assertGreater(abs(self.p.stats['atk'] - self.p.stats['spa']), 5)
        before = self.e.elapsed_seconds
        result = self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True)
        self.assertEqual((result['seconds'], self.e.elapsed_seconds - before, self.p.spec['tutor_points']), (3600, 3600, 6))
        self.assertTrue(EDGES.official_mixed_power(self.p))
        self.assertFalse(EDGES.mixed_power(self.p))
        self.assertIn('트위스트파워', self.p.abilities)
        self.assertNotIn('트위스트파워', self.p.spec['abilities'])
        self.rejected(lambda:self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True), 'already acquired')
        bases = {mid:self.baseline(mid) for mid in ('move/불꽃펀치', 'move/불꽃세례')}
        self.answer({'type':'twisted_power', 'unit':'ability/트위스트파워', 'actor':self.p.name}, True)
        self.bind()
        for mid, other in (('move/불꽃펀치', 'spa'), ('move/불꽃세례', 'atk')):
            self.hit(mid, bases[mid] + self.p.staged(other))
            self.assertFalse(list(self.e._move_completions.values())[-1]['twisted_power'])
            self.next_turn(self.p)
        self.restore()
        self.valid()

    def test_official_level_and_each_ordinary_investment_requirements_reject_atomically(self):
        for level, atk, spa in ((9, 5, 5), (30, 4, 5), (30, 5, 4)):
            with self.subTest(level=level, attack=atk, special=spa):
                self.version('september-2015')
                self.learner(level=level, attack=atk, special=spa)
                self.rejected(lambda:self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True),
                    'level ten and five actual ordinary investments')
                self.assertNotIn('트위스트파워', self.p.abilities)

    def test_official_ability_grant_and_adopted_direct_bonus_have_distinct_native_suppression_behavior(self):
        for official in (True, False):
            with self.subTest(official=official):
                self.version('september-2015' if official else None)
                self.learner()
                plain = self.baseline('move/몸통박치기')
                if official:
                    self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True)
                else:
                    EDGES.teach_mixed_power(self.e, self.t, self.p, safe=True)
                    self.e.gm.set_ability(self.p, '트위스트파워', reason='independent suppressible Ability, not the adopted Edge')
                self.combat(self.b)
                self.suppress(self.p, '트위스트파워')
                self.next_turn(self.p)
                self.hit('move/몸통박치기', plain + (0 if official else M.ratio(self.p.staged('spa'), 2)))
                self.restore()
                self.valid()

    def test_official_prerequisite_loss_refunds_once_revokes_only_owned_ability_and_restore_detects_forgery(self):
        self.version('september-2015')
        self.learner(attack=12)
        self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True)
        self.restore()
        self.valid()
        self.e.gm.set_level(self.p, 9, reason='actual loss of official minimum level')
        row = next(r for r in self.p.spec['learned_poke_edges'] if r['source'] == EDGES.OFFICIAL_MIXED)
        self.assertEqual((row['status'], row['refund']['points'], self.p.spec['tutor_points']), ('refunded', 2, 8))
        self.assertNotIn('트위스트파워', self.p.abilities)
        self.e.gm.set_level(self.p, 9, reason='same actual level correction')
        self.assertEqual(self.p.spec['tutor_points'], 8)
        self.restore()
        self.valid()
        # Receipt tampering is a rejection test, not a positive fixture.
        row = next(r for r in self.p.spec['learned_poke_edges'] if r['source'] == EDGES.OFFICIAL_MIXED)
        row['definition_origin'] = dict(EDGES.MIXED_ORIGIN)
        self.assertFalse(self.e.validate_state()['valid'])
        self.version('september-2015')
        self.learner()
        self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True)
        self.e.gm.set_ability(self.p, '트위스트파워', reason='actual independent permanent Ability copy')
        self.e.gm.set_level(self.p, 9, reason='actual source prerequisite lost with independent copy')
        self.assertIn('트위스트파워', self.p.abilities)
        self.assertEqual(self.p.spec['tutor_points'], 8)
        self.restore()
        self.valid()

    def test_official_lost_ordinary_investment_uses_real_reallocation_and_cannot_refund_twice(self):
        import nature_state as N
        self.version('september-2015')
        self.learner()
        self.e.pokemon_activity(self.t, 'teach_edge', target=self.p, edge=EDGES.OFFICIAL_MIXED, safe=True)
        values = dict.fromkeys(STATS, 0)
        values.update(atk=4, spa=5, spe=31)
        neutral = next(name for name in self.rules.mech('pokemon/natures')['by_name'] if N.describe(self.rules, name)['neutral'])
        options = dict(investment=values, source='combat/struggle', reason='actual ordinary stat reallocation',
            ap_cost=0, hp_policy='preserve_damage', request_id='official-mixed-reallocate')
        self.e.commit_growth_nature(self.t, self.p, neutral, **options)
        self.assertFalse(EDGES.official_mixed_power(self.p))
        self.assertEqual(self.p.spec['tutor_points'], 8)
        self.assertNotIn('트위스트파워', self.p.abilities)
        self.e.commit_growth_nature(self.t, self.p, neutral, **options)
        self.assertEqual(self.p.spec['tutor_points'], 8)
        self.restore()
        self.valid()

    def test_adopted_receipt_cannot_masquerade_as_official_and_default_core_profile_stays_adopted(self):
        for version in (None, 'september-2015'):
            with self.subTest(version=version):
                self.version(version, regime='ptu-core-1.05')
                self.learner()
                EDGES.teach_mixed_power(self.e, self.t, self.p, safe=True)
                self.assertTrue(EDGES.mixed_power(self.p))
                self.assertFalse(EDGES.official_mixed_power(self.p))
                self.assertNotIn('트위스트파워', self.p.abilities)
                source = EDGES.incandescence_source(self.rules)
                self.assertEqual(source['version'], version or 'adopted-errata')
                # Both native baselines already include the adopted direct half.
                base = self.baseline('move/불꽃펀치')
                self.bind()
                extra = self.p.staged('spa') - M.ratio(self.p.staged('spa'), 2) if version is None else 0
                self.hit('move/불꽃펀치', base + extra)
                self.restore()
                self.valid()

    def test_unknown_incandescence_version_rejects_actual_acquisition_without_changing_other_selectors(self):
        self.rules = Rules(FIX.ROOT, ruleset='core')
        self.rules.ruleset = RuleFilter({'sources':['core'], 'unit_versions':{EDGES.INCANDESCENCE:'may-2015'}})
        self.rules._apply_ruleset()
        self.setup()
        self.family('불꽃', 'Brightest Flame')
        self.rejected(lambda:self.acquire('Incandescence'), 'unknown Incandescence')
        with self.assertRaisesRegex(ValueError,'unknown Incandescence'):
            self.rules.feat_effects(EDGES.INCANDESCENCE)
        with self.assertRaisesRegex(ValueError,'unknown Incandescence'):
            __import__('crafting_recipes')._selected(self.e,EDGES.INCANDESCENCE)
        self.assertNotIn('feat/훈련-상황', self.rules.ruleset.unit_versions)


if __name__ == '__main__':
    unittest.main()
