"""Actual numeric species Reach uses one native distance and explicit conflicts."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from builder import build_pokemon
from engine import Rules
from native_scenario_fixture import assert_rejected_unchanged
import test_category2_body_modes as FIXTURE
import body_state as BODY
import state_codec as CODEC
import state_grants as GRANTS
import world_entities as WORLD


class NumericMeleeReachSourceRevisionTests(unittest.TestCase):
    setUpClass=classmethod(FIXTURE.Tests.setUpClass.__func__)
    setUp=FIXTURE.Tests.setUp
    add=FIXTURE.Tests.add
    pokemon=FIXTURE.Tests.pokemon
    begin=FIXTURE.Tests.begin
    known=FIXTURE.Tests.known

    def actual_species(self,name,pos=(3,3)):
        self.p.pos=(1,7);self.t.pos=(2,8)
        actor=self.add(build_pokemon(self.r,name,20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
        actor.pos=pos
        self.e.gm.observe_loyalty(actor,6,reason='actual obeying catalog-built Pokemon')
        self.known(actor,'몸통박치기')
        width=BODY.WIDTH[actor.spec['size']]
        self.e.gm.set_footprint(actor,[(x,y) for x in range(width) for y in range(width)],
                                reason='GM observed this individual square occupied body')
        return actor

    def target_at(self,actor,distance):
        target=self.pokemon(level=50)
        target.pos=(max(x for x,_ in BODY.cells(actor,require_complete=True))+distance,3)
        return target

    def choose(self,actor,value):
        pending=self.e.gm.observe_melee_reach_source(actor)
        self.assertEqual(pending['status'],'PolicyInputsRequired')
        self.assertEqual(pending['obligations'][0]['decision_kind'],'source_conflict')
        choice={'value':value,'reason':'actual GM selects this complete Reach source interpretation',
                'scope':pending['decision_scope']}
        return self.e.gm.observe_melee_reach_source(actor,choice)

    def native_hit(self,actor,target):
        self.begin(actor)
        before=(target.hp,actor.pos,actor.budget['shift'])
        with patch.object(self.e,'d20',return_value=15):
            damage=self.e.use_move(actor,target,'move/몸통박치기',set_damage=True)
        self.assertGreater(damage,0)
        self.assertLess(target.hp,before[0])
        self.assertEqual((actor.pos,actor.budget['shift']),before[1:])
        self.assertEqual(actor.budget['standard'],0)
        self.assertTrue(actor.move_uses)

    def test_actual_four_agreeing_species_use_absolute_native_range_and_exception_observation(self):
        for name,label,distance in [('독파리','도달 2',2),('롱스톤','도달 3',3),
                                    ('강철톤','도달 3',3),('메가강철톤','도달 3',3)]:
            with self.subTest(species=name):
                self.setUp()
                actor=self.actual_species(name)
                self.assertIn(label,actor.spec['capabilities'])
                self.assertEqual(BODY.melee_reach(actor),distance)
                self.assertNotIn(BODY.REACH_SOURCE_OBSERVATION,actor.spec)
                target=self.target_at(actor,distance)
                move=self.r.move('move/몸통박치기')
                self.assertIn(target,self.e.targets_in_range(actor,move,self.e.everyone,target))
                self.assertFalse(BODY.adjacent(actor,target))
                self.native_hit(actor,target)
                self.begin(actor)
                target.pos=(target.pos[0]+1,target.pos[1])
                before=deepcopy((target.hp,actor.spec,actor.budget,actor.move_uses,self.e.rng.getstate()))
                self.assertEqual(self.e.use_move(actor,target,'move/몸통박치기'),0)
                self.assertEqual((target.hp,actor.spec,actor.budget,actor.move_uses,self.e.rng.getstate()),before)
                self.assertNotIn(target,self.e.targets_in_range(actor,move,self.e.everyone,target))
                self.e.gm.observe_melee_reach(actor,distance+2,anatomy='long_limbs',
                                            reason='GM measured this actual exceptional limb reach')
                self.assertEqual(BODY.melee_reach(actor),distance+2)
                self.assertIn(target,self.e.targets_in_range(actor,move,self.e.everyone,target))

    def test_actual_tangrowth_requires_scoped_choice_and_both_complete_alternatives_reach_native_attack(self):
        for value,distance in [('core_size_rule',3),('species_explicit_distance',2)]:
            with self.subTest(source=value):
                self.setUp()
                actor=self.actual_species('덩쿠림보')
                self.assertEqual((actor.spec['size'],actor.spec['capabilities']),('대형',['도달 2']))
                target=self.target_at(actor,3)
                self.begin(actor)
                assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,target,'move/몸통박치기'),
                                          reason_pattern='explicit current numeric Reach source choice')
                before=self.e.export_state()
                pending=self.e.gm.observe_melee_reach_source(actor)
                self.assertEqual(self.e.export_state(),before)  # Query never fabricates a past GM decision.
                self.assertEqual(set(pending['obligations'][0]['constraints']['choices']),
                                 {'core_size_rule','species_explicit_distance'})
                self.assertEqual(self.choose(actor,value),distance)
                row=actor.spec[BODY.REACH_SOURCE_OBSERVATION]
                self.assertEqual(row['policy']['values']['variant'],value)
                self.assertEqual(row['policy']['values']['native_scope']['csv_row'],472)
                self.assertEqual(row['policy']['values']['definitions']['species_explicit_distance']['distance'],2)
                move=self.r.move('move/몸통박치기')
                self.assertEqual(target in self.e.targets_in_range(actor,move,self.e.everyone,target),distance==3)
                if distance==2:
                    before=deepcopy((target.hp,actor.budget,actor.move_uses,self.e.rng.getstate()))
                    self.assertEqual(self.e.use_move(actor,target,'move/몸통박치기'),0)
                    self.assertEqual((target.hp,actor.budget,actor.move_uses,self.e.rng.getstate()),before)
                    target.pos=(target.pos[0]-1,target.pos[1])
                self.native_hit(actor,target)
                self.e.gm.observe_melee_reach(actor,5,anatomy='long_limbs',reason='actual longer measured vines')
                self.assertEqual(BODY.melee_reach(actor),5)

    def test_same_semantic_choice_follows_current_size_and_native_approach_without_rechoice(self):
        for value,small,large in [('core_size_rule',2,3),('species_explicit_distance',2,2)]:
            with self.subTest(source=value):
                self.setUp()
                actor=self.actual_species('덩쿠림보')
                self.choose(actor,value)
                retained=deepcopy(actor.spec[BODY.REACH_SOURCE_OBSERVATION])
                actor.spec['size']='중형'  # Actual new body-size observation, separate from source interpretation.
                self.e.gm.set_footprint(actor,[(0,0)],reason='GM observed the current medium body')
                self.assertEqual(BODY.melee_reach(actor),small)
                actor.spec['size']='대형'
                self.e.gm.set_footprint(actor,[(0,0),(0,1),(1,0),(1,1)],reason='GM observed the current large body')
                self.assertEqual(BODY.melee_reach(actor),large)
                self.assertEqual(actor.spec[BODY.REACH_SOURCE_OBSERVATION],retained)
                target=self.target_at(actor,large+1)
                self.begin(actor)
                before=(actor.pos,actor.budget['shift'],target.hp)
                with patch.object(self.e,'d20',return_value=15):
                    self.e.use_move_on(actor,target,'move/몸통박치기',self.e.everyone,set_damage=True)
                self.assertNotEqual(actor.pos,before[0])
                self.assertLess(actor.budget['shift'],before[1])
                self.assertLess(target.hp,before[2])
                self.assertEqual(actor.budget['standard'],0)
                self.assertEqual(actor.spec[BODY.REACH_SOURCE_OBSERVATION],retained)

    def test_gm_and_fresh_rules_json_keep_actual_source_choice_and_inactive_history_without_granting_reach(self):
        for value,distance in [('core_size_rule',3),('species_explicit_distance',2)]:
            for restoration in ('gm','json'):
                with self.subTest(source=value,restoration=restoration):
                    self.setUp()
                    actor=self.actual_species('덩쿠림보')
                    self.choose(actor,value)
                    identity=actor.entity_id
                    retained=deepcopy(actor.spec[BODY.REACH_SOURCE_OBSERVATION])
                    GRANTS.overlay(actor,'fixture:actual-temporary-capability-loss',capabilities=[])
                    self.assertEqual(BODY.melee_reach(actor),1)
                    if restoration=='gm':
                        self.e.gm.snapshot('actual Reach source absent')
                        GRANTS.revoke(actor,'fixture:actual-temporary-capability-loss')
                        self.assertEqual(BODY.melee_reach(actor),distance)
                        self.e.gm.restore('actual Reach source absent')
                    else:
                        self.e=CODEC.load_engine(Rules(ROOT,ruleset='core'),json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False)))
                    actor=WORLD.actor_index(self.e)[identity]
                    self.assertEqual(BODY.melee_reach(actor),1)
                    self.assertEqual(actor.spec[BODY.REACH_SOURCE_OBSERVATION],retained)
                    GRANTS.revoke(actor,'fixture:actual-temporary-capability-loss')
                    self.assertEqual(BODY.melee_reach(actor),distance)
                    self.e.gm.observe_melee_reach(actor,5,anatomy='long_limbs',reason='actual restored individual exceptional reach')
                    self.assertEqual(BODY.melee_reach(actor),5)
                    self.assertEqual(actor.spec[BODY.REACH_SOURCE_OBSERVATION],retained)

    def test_stale_or_foreign_choice_and_live_malformed_numeric_sources_fail_before_native_payment(self):
        actor=self.actual_species('덩쿠림보')
        pending=self.e.gm.observe_melee_reach_source(actor)
        choice={'value':'core_size_rule','reason':'actual current GM Core interpretation','scope':pending['decision_scope']}
        other=self.actual_species('덩쿠림보',pos=(10,3))
        assert_rejected_unchanged(self.e,lambda:self.e.gm.observe_melee_reach_source(other,choice),
                                  reason_pattern='decision scope changed')
        self.e.gm.observe_melee_reach_source(actor,choice)
        target=self.target_at(actor,3)
        self.begin(actor)
        GRANTS.grant(actor,'capabilities','도달','fixture:independent-reach','fixture')
        assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,target,'move/몸통박치기'),
                                  reason_pattern='decision scope changed')
        self.choose(actor,'core_size_rule')
        GRANTS.revoke(actor,'fixture:independent-reach')
        assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,target,'move/몸통박치기'),
                                  reason_pattern='decision scope changed')
        self.choose(actor,'core_size_rule')
        catalog=self.r.species[actor.spec['species']]
        with patch.dict(catalog,{'size':'중형'}):
            assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,target,'move/몸통박치기'),
                                      reason_pattern='cells disagree with the current catalog')
        with patch.dict(self.r.selection.aliases,{BODY.REACH_SOURCE:'edge/미용사'}):
            assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,target,'move/몸통박치기'),
                                      reason_pattern='selected Reach source')
        for malformed in ('도달 4','도달 2.5','도달 -1','도달2x'):
            with self.subTest(label=malformed):
                GRANTS.grant(actor,'capabilities',malformed,'fixture:unsupported-numeric-reach','fixture')
                assert_rejected_unchanged(self.e,lambda:self.e.use_move(actor,target,'move/몸통박치기'),
                                          reason_pattern='unsupported numeric Reach source')
                GRANTS.revoke(actor,'fixture:unsupported-numeric-reach')
        self.assertEqual(BODY.melee_reach(actor),3)


if __name__=='__main__':unittest.main()
