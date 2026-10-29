"""Correct-policy adversarial probes; no execution by the source reviewer."""
from copy import copy, deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'engine'), str(ROOT / 'tools')]
from engine import Engine
import stellar_tera_blast as STELLAR
import type_state as TYPES
import world_entities as WORLD
import test_category2_csv_stellar_tera_blast as _fixture


class StellarAdversarial05Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _fixture.StellarTeraBlastTests.setUpClass()
        cls.base_rules = _fixture.StellarTeraBlastTests.rules

    def setUp(self):
        self.rules = copy(self.base_rules)
        self.rules.rulings = deepcopy(self.base_rules.rulings)
        _fixture.StellarTeraBlastTests.setUp(self)

    def native_hit(self):
        with patch.object(Engine, 'd20', return_value=10):
            self.engine.use_move(self.owner, self.foe, 'move/몸통박치기', set_damage=True)
        return self.owner.spec[STELLAR.STATE]['opportunities'][-1]

    def radiate(self):
        opportunity = self.native_hit()
        self.engine.gm.activate_stellar_blast(self.owner, opportunity['id'], '불꽃',
                                            reason='actual native hit and chosen enemy Fire type')
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 10)

    @staticmethod
    def mapping(payload, reference):
        return payload['nodes'][reference['$ref']]['items']

    def radiation_items(self, payload):
        actor = next(node for node in payload['nodes'].values()
                     if node['kind'] == 'actor' and node['entity_id'] == self.owner.entity_id)
        attrs = self.mapping(payload, actor['attrs'])
        spec = self.mapping(payload, next(value for key, value in attrs if key == 'spec'))
        return self.mapping(payload, next(value for key, value in spec if key == STELLAR.STATE))

    def test_cross_map_stellar_aura_does_not_raise_native_damage(self):
        self.radiate()
        for actor, map_id in ((self.owner, 'map-a'), (self.ally, 'map-b'), (self.foe, 'map-b')):
            WORLD.observe_location(self.engine, actor, {'kind': 'grid', 'cell': actor.pos, 'map_id': map_id},
                                   reason='actual separate observed maps')
        self.assertIsNone(WORLD.distance_known(self.owner, self.ally))
        move = self.rules.move('move/불꽃세례')
        remote_damage = self.engine.roll_damage(self.ally, self.foe, move, set_damage=True)
        retained = deepcopy(self.owner.spec[STELLAR.STATE]['history'])
        self.engine.gm.set_ability(self.owner, '스텔라버스트', add=False, reason='actual source withdrawal control')
        ordinary_damage = self.engine.roll_damage(self.ally, self.foe, move, set_damage=True)
        self.assertEqual(self.owner.spec[STELLAR.STATE]['history'], retained)
        self.assertEqual(remote_damage, ordinary_damage,
                         'same numeric cells on another map leaked the Stellar damage aura')

    def test_editing_global_radiation_epoch_cannot_revive_last_encounter_aura(self):
        self.radiate()
        self.engine.end_of_turn(self.owner)
        self.engine.end_encounter(self.engine.everyone)
        self.engine.start_round(self.engine.everyone)
        self.engine.start_of_turn(self.owner, initiative_count=20)
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
        payload = json.loads(json.dumps(self.engine.export_state()))
        normal = Engine.import_state(self.rules, deepcopy(payload))
        self.assertIsNone(STELLAR.active_radiation(normal, WORLD.actor_index(normal)[self.owner.entity_id]))
        state = self.radiation_items(payload)
        old_epoch = next(value for key, value in state if key == 'encounter_epoch')
        self.assertLess(old_epoch, self.engine._party_encounter_epoch)
        for pair in state:
            if pair[0] == 'encounter_epoch':
                pair[1] = self.engine._party_encounter_epoch
        try:
            loaded = Engine.import_state(self.rules, payload)
        except ValueError:
            return
        owner = WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertIsNone(STELLAR.active_radiation(loaded, owner),
                          'editing only the pool epoch revived a paid aura with no current encounter hit')

    def test_undeclared_saved_opportunity_type_cannot_authorize_native_swift_radiation(self):
        opportunity = self.native_hit()
        self.assertEqual(opportunity['types'], ['불꽃'])
        invalid = '__not_a_declared_radiation_type__'
        self.assertNotIn(invalid, TYPES.allowed_types(self.rules))
        payload = json.loads(json.dumps(self.engine.export_state()))
        Engine.import_state(self.rules, deepcopy(payload))
        state = self.radiation_items(payload)
        opportunities = payload['nodes'][next(value for key, value in state if key == 'opportunities')['$ref']]['items']
        first = self.mapping(payload, opportunities[0])
        type_ref = next(value for key, value in first if key == 'types')
        payload['nodes'][type_ref['$ref']]['items'] = [invalid]
        try:
            loaded = Engine.import_state(self.rules, payload)
            owner = WORLD.actor_index(loaded)[self.owner.entity_id]
            loaded.gm.activate_stellar_blast(owner, opportunity['id'], invalid,
                                           reason='undeclared type must not pass original-hit validation')
        except ValueError:
            return
        self.fail('an unchanged real hit completion authorized an undeclared type and spent native Swift')

    def test_known_map_radius_keeps_exact_two_metres_and_self_benefit(self):
        self.radiate()
        WORLD.observe_location(self.engine,self.owner,
            {'kind':'grid','cell':(2,2),'map_id':'one-map'},reason='actual aura map')
        WORLD.observe_location(self.engine,self.ally,
            {'kind':'grid','cell':(4,2),'map_id':'one-map'},reason='actual two-metre boundary')
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine,self.ally,'불꽃')[0],10)
        WORLD.observe_location(self.engine,self.ally,
            {'kind':'grid','cell':(5,2),'map_id':'one-map'},reason='outside actual aura')
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine,self.ally,'불꽃')[0],0)
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine,self.owner,'불꽃')[0],10)

    def test_explicit_declared_custom_type_remains_a_native_radiation_choice(self):
        self.rules=deepcopy(self.base_rules)
        name='수정'
        matrix=dict.fromkeys(TYPES.CORE_TYPES+(name,),1)
        self.rules.ruleset.profile['type_extensions']={name:{
            'source_id':TYPES.STELLAR_SOURCE,'reason':'explicit complete GM type declaration',
            'attack_vs':dict(matrix),'defense_vs':dict(matrix)}}
        self.assertEqual(TYPES.validate_types(self.rules,[name]),[name])
        _fixture.StellarTeraBlastTests.setUp(self)
        self.engine.gm.set_types(self.foe,[name],reason='actual declared-type enemy')
        opportunity=self.native_hit()
        self.assertEqual(opportunity['types'],[name])
        self.engine.gm.activate_stellar_blast(self.owner,opportunity['id'],name,
                                            reason='choose the actually hit declared type')
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.engine.export_state())))
        owner=WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertEqual(STELLAR.active_radiation(loaded,owner)['radiated_type'],name)

    def test_personal_stellar_and_typeless_settings_keep_their_legal_type_domain(self):
        from engine import Rules
        import personal_type_settings as PERSONAL
        personal=Rules(str(ROOT),ruleset='personal-stellar-typeless')
        for name in ('스텔라',PERSONAL.TYPELESS):
            with self.subTest(type=name):
                self.rules=copy(personal);self.rules.rulings=deepcopy(personal.rulings)
                _fixture.StellarTeraBlastTests.setUp(self)
                self.engine.gm.set_types(self.foe,[name],reason='actual user-authorized non-Tera type')
                opportunity=self.native_hit()
                self.assertEqual(opportunity['types'],[name])
                self.engine.gm.activate_stellar_blast(self.owner,opportunity['id'],name,
                                                    reason='actual legal personal type choice')
                self.assertEqual(STELLAR.active_radiation(self.engine,self.owner)['radiated_type'],name)
                self.assertEqual(STELLAR.damage_roll_bonus(self.engine,self.ally,name)[0],10)
                self.assertTrue(STELLAR.validate_world(self.engine))

    def test_current_enemy_type_change_does_not_rewrite_the_original_hit_snapshot(self):
        opportunity=self.native_hit()
        self.engine.gm.set_types(self.foe,['물'],reason='separate later legitimate type change')
        self.assertEqual(self.foe.types,['물'])
        self.engine.gm.activate_stellar_blast(self.owner,opportunity['id'],'불꽃',
                                            reason='choose original observed Fire type')
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.engine.export_state())))
        owner=WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertEqual(STELLAR.active_radiation(loaded,owner)['radiated_type'],'불꽃')

    def legacy_schema(self,engine,owner):
        state=owner.spec[STELLAR.STATE]
        for opportunity in state['opportunities']:
            completion=engine._move_completions[opportunity['completion_id']]
            completion.pop(STELLAR.OBSERVATION,None)
            completion.pop(STELLAR.ADMISSIONS,None)
        for row in state['history']:row.pop('encounter_epoch',None)
        if state['active'] is not None:state['active'].pop('encounter_epoch',None)

    def test_legacy_current_hit_can_pay_a_new_admission_without_fabricating_hit_history(self):
        opportunity=self.native_hit()
        self.legacy_schema(self.engine,self.owner)
        completion_id=opportunity['completion_id']
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.engine.export_state())))
        owner=WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertNotIn(STELLAR.OBSERVATION,loaded._move_completions[completion_id])
        receipt=loaded.gm.activate_stellar_blast(owner,opportunity['id'],'불꽃',
            reason='new actual Swift admitted by original same-turn native hit')
        self.assertEqual(owner.budget['swift'],0)
        self.assertNotIn(STELLAR.OBSERVATION,loaded._move_completions[completion_id])
        admission=loaded._move_completions[completion_id][STELLAR.ADMISSIONS][receipt['id']]
        self.assertEqual(admission['activation'],receipt)
        loaded.end_of_turn(owner);loaded.start_round(loaded.everyone)
        loaded.start_of_turn(owner,initiative_count=20)
        restored=Engine.import_state(self.rules,json.loads(json.dumps(loaded.export_state())))
        actual=WORLD.actor_index(restored)[owner.entity_id]
        self.assertEqual(STELLAR.active_radiation(restored,actual)['radiated_type'],'불꽃')
        self.assertEqual(len(actual.spec[STELLAR.STATE]['history']),1)

    def test_legacy_current_paid_radiation_keeps_cold_aura_and_queries_are_read_only(self):
        self.radiate()
        self.legacy_schema(self.engine,self.owner)
        history=deepcopy(self.owner.spec[STELLAR.STATE]['history'])
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.engine.export_state())))
        index=WORLD.actor_index(loaded);owner=index[self.owner.entity_id];ally=index[self.ally.entity_id]
        before=loaded.export_state()
        self.assertEqual(STELLAR.active_radiation(loaded,owner)['radiated_type'],'불꽃')
        self.assertEqual(STELLAR.damage_roll_bonus(loaded,ally,'불꽃')[0],10)
        self.assertEqual(loaded.export_state(),before)
        self.assertEqual(owner.spec[STELLAR.STATE]['history'],history)
        loaded.gm.set_ability(owner,'스텔라버스트',add=False,reason='actual source loss after legacy restore')
        self.assertIsNone(STELLAR.active_radiation(loaded,owner))
        self.assertEqual(owner.spec[STELLAR.STATE]['history'],history)

    def test_legacy_ended_unmarked_history_cannot_follow_edited_pool_into_new_encounter(self):
        self.radiate()
        # A prepared local preview is not a paid native completion witness.
        raw=STELLAR.prepare(self.engine,self.owner,self.rules.move('move/테라버스트-특수'),True)
        self.assertIn(STELLAR.CHOICE,raw)
        self.legacy_schema(self.engine,self.owner)
        history=deepcopy(self.owner.spec[STELLAR.STATE]['history'])
        self.engine.end_of_turn(self.owner);self.engine.end_encounter(self.engine.everyone)
        self.engine.start_round(self.engine.everyone);self.engine.start_of_turn(self.owner,initiative_count=20)
        self.owner.spec[STELLAR.STATE]['encounter_epoch']=self.engine._party_encounter_epoch
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(self.engine.export_state())))
        owner=WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertIsNone(STELLAR.active_radiation(loaded,owner))
        self.assertEqual(owner.spec[STELLAR.STATE]['history'],history)
        self.assertTrue(STELLAR.validate_actor(loaded,owner))

    def test_legacy_marked_paid_completion_proves_aura_across_rounds_but_not_new_encounter(self):
        import test_stellar_r663_optional_source_revision as R663
        helper=R663.StellarR663OptionalSourceRevisionTests();helper.rules=self.rules
        engine,owner,target=helper.world()
        move='move/테라버스트-특수'
        helper.hit(engine,owner,target,move,use_radiated_type=True)
        completion=helper.last(engine);identity=completion['id']
        frozen=deepcopy(completion['move'][STELLAR.CHOICE])
        self.legacy_schema(engine,owner)
        history=deepcopy(owner.spec[STELLAR.STATE]['history'])
        helper.next_turn(engine,owner)
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(engine.export_state())))
        actual=WORLD.actor_index(loaded)[owner.entity_id]
        self.assertEqual(STELLAR.active_radiation(loaded,actual)['radiated_type'],'불꽃')
        self.assertEqual(STELLAR.damage_roll_bonus(loaded,actual,'불꽃')[0],10)
        self.assertEqual(loaded._move_completions[identity]['move'][STELLAR.CHOICE],frozen)
        self.assertEqual(actual.spec[STELLAR.STATE]['history'],history)
        loaded.end_of_turn(actual);loaded.end_encounter(loaded.everyone)
        loaded.start_round(loaded.everyone);loaded.start_of_turn(actual,initiative_count=20)
        actual.spec[STELLAR.STATE]['encounter_epoch']=loaded._party_encounter_epoch
        self.assertIsNone(STELLAR.active_radiation(loaded,actual))

    def test_legacy_marked_paid_accuracy_wait_keeps_type_bonus_and_cost_on_cold_resume(self):
        import math
        from engine import Combatant
        from builder import build_pokemon
        import combat_move_reactions as CMR
        import passive_events as PE
        import test_stellar_r663_optional_source_revision as R663
        import test_actual_damage_type_revision as DAMAGE
        helper=R663.StellarR663OptionalSourceRevisionTests();helper.rules=self.rules
        engine,owner,target=helper.world();move='move/테라버스트-물리'
        responder=Combatant(engine.r,build_pokemon(engine.r,'꼬렛',20,
            name='legacy paid frame responder',side='party',pos=(9,2),abilities=[],moves=[CMR.GUARD]))
        engine.gm.add_combatant(responder);CMR.arm(engine,responder,CMR.GUARD)
        key=PE.subscribe_policy(engine,owner,'marked-legacy-stellar-checkpoint',{
            'schema':1,'id':'test-only-marked-legacy-stellar','variants':[{
                'rule_id':'ability/스텔라버스트',
                'source':{'file':'input/db/abilities.csv','sha256':
                    '87efebd17b0a5fe09c9db060a16a8844cf41be53d65eb35716cf62f80a177fae'},
                'values':{'effects':[]},'when':{'$input':'apply_test_effect'},
                'inputs':{'apply_test_effect':{'type':'boolean','authority':'gm',
                    'question':'Test-only transport checkpoint; decline the effect'}}}]},event='accuracy_resolved')
        with self.assertRaises(PE.PassiveEventPending):
            helper.hit(engine,owner,target,move,use_radiated_type=True)
        event_id=engine._passive_pending;completion=helper.last(engine);identity=completion['id']
        self.assertTrue(completion['started']);self.assertIs(completion['native_action_frame']['actor'],owner)
        frozen=deepcopy(completion['move'][STELLAR.CHOICE]);self.legacy_schema(engine,owner)
        paid=deepcopy((owner.budget,owner.move_uses));history=deepcopy(owner.spec[STELLAR.STATE]['history'])
        hp=target.hp;rng=engine.rng.getstate()
        loaded=Engine.import_state(self.rules,json.loads(json.dumps(engine.export_state())))
        owner,target=(WORLD.actor_index(loaded)[c.entity_id] for c in (owner,target))
        self.assertEqual(STELLAR.damage_roll_bonus(loaded,owner,'불꽃')[0],10)
        expected=math.floor(DAMAGE.ActualDamageTypeRevisionTests().expected(
            loaded,owner,target,move,8,bonus=10)*loaded.type_multiplier('불꽃',target)[0])
        with patch.object(Engine,'d20',side_effect=AssertionError('paid native accuracy must not reroll')):
            PE.choose(loaded,event_id,owner,key,{'decisions':{'apply_test_effect':{
                'value':False,'reason':'resume only the original paid transport'}}})
        self.assertEqual(loaded._move_completions[identity]['results'][target.entity_id]['dealt'],expected)
        self.assertEqual(target.hp,hp-expected)
        self.assertEqual((owner.budget,owner.move_uses),paid);self.assertEqual(loaded.rng.getstate(),rng)
        self.assertEqual(loaded._move_completions[identity]['move'][STELLAR.CHOICE],frozen)
        self.assertEqual(owner.spec[STELLAR.STATE]['history'],history)
        self.assertIsNone(loaded._passive_pending)
        self.assertTrue(loaded.validate_state()['valid'])

    def test_activation_epoch_cannot_replace_its_original_native_encounter(self):
        self.radiate()
        state=self.owner.spec[STELLAR.STATE]
        state['active']['encounter_epoch']+=1
        with self.assertRaisesRegex(ValueError,'different native encounter'):
            STELLAR.validate_actor(self.engine,self.owner)

    def test_valid_same_map_aura_and_source_loss_preserve_historical_world(self):
        self.radiate()
        before = deepcopy(self.owner.spec[STELLAR.STATE]['history'])
        self.engine.gm.set_ability(self.owner, '스텔라버스트', add=False, reason='actual ending of effective source')
        self.assertIsNone(STELLAR.active_radiation(self.engine, self.owner))
        self.assertEqual(STELLAR.damage_roll_bonus(self.engine, self.ally, '불꽃')[0], 0)
        loaded = Engine.import_state(self.rules, json.loads(json.dumps(self.engine.export_state())))
        owner = WORLD.actor_index(loaded)[self.owner.entity_id]
        self.assertEqual(owner.spec[STELLAR.STATE]['history'], before)
        self.assertIsNone(STELLAR.active_radiation(loaded, owner))


if __name__ == '__main__':
    unittest.main()
