"""Fashion derived-save consistency attacks; no hostile-host authentication claim."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Engine
import condition_recovery as RECOVERY
import combat_state_lifecycle as COMBAT
import fashion_items as FASHION
import frequency as FREQUENCY
import items as ITEMS
import state_grants as GRANTS
import world_entities as WORLD
import test_fashion_save_receipt_authority as FIX


class AdversarialFashion06Tests(unittest.TestCase):
    setUpClass=classmethod(FIX.FashionSaveReceiptTests.setUpClass.__func__)
    private_rules=FIX.FashionSaveReceiptTests.private_rules
    fashion=FIX.FashionSaveReceiptTests.fashion
    core_fashion=FIX.FashionSaveReceiptTests.core_fashion

    def reject_inconsistent_rearm(self,engine,wearer,quota,label):
        # The native issuance and first native consumption happened normally.
        # Only derived saved fields are inconsistent; original payment stays put.
        self.assertIs(engine.rulings,engine.r.rulings)
        before=deepcopy(wearer.spec['frequency_state']['activations'])
        self.assertEqual(before,quota)
        try:
            payload=json.loads(json.dumps(engine.export_state(),ensure_ascii=False))
            loaded=Engine.import_state(engine.r,payload)
            actual=WORLD.actor_index(loaded)[wearer.entity_id]
            result=RECOVERY.saving_check(loaded,actual,None,8,fixed=5)
        except ValueError:
            self.assertEqual(wearer.spec['frequency_state']['activations'],quota)
            return
        self.fail(label+' was accepted; another native save received Fashion bonus '+
                  str(result['fashion_bonus'])+' despite unchanged native quota '+repr(quota))

    def test_duplicate_core_issuance_with_fresh_sequence_cannot_repeat_one_scene_activation(self):
        engine,wearer,_=self.core_fashion()
        pending=deepcopy(wearer.spec['fashion_next_save'])
        original=deepcopy(pending['activation_receipt'])
        quota=deepcopy(wearer.spec['frequency_state']['activations'])
        self.assertEqual(quota['fashion:item/기막힌-패션']['used'],1)
        self.assertEqual(RECOVERY.saving_check(engine,wearer,None,8,fixed=5)['fashion_bonus'],4)
        # Rewriting a sequence ID is not a second actual activation. Keep the
        # original source/instance/wearer/scene/round/time and payment unchanged.
        duplicate=deepcopy(original)
        duplicate['activation_id']='fashion-save:'+wearer.entity_id+':2'
        wearer.spec[FASHION.STATE]['history'].append(deepcopy(duplicate))
        pending['activation_receipt']=duplicate
        wearer.spec['fashion_next_save']=pending
        self.assertEqual(wearer.spec[FASHION.STATE]['history'][0],original)
        self.assertEqual(len(wearer.spec['fashion_save_history']),1)
        self.reject_inconsistent_rearm(engine,wearer,quota,'same-scene counterfeit second issuance')

    def test_id_removal_and_future_scene_cannot_downgrade_consumed_modern_receipt(self):
        for clock in ('scene','round'):
            with self.subTest(clock=clock):
                engine,wearer,_=self.core_fashion()
                pending=deepcopy(wearer.spec['fashion_next_save'])
                issuance=deepcopy(wearer.spec[FASHION.STATE]['history'])
                quota=deepcopy(wearer.spec['frequency_state']['activations'])
                self.assertEqual(RECOVERY.saving_check(engine,wearer,None,8,fixed=5)['fashion_bonus'],4)
                pending['activation_receipt'].pop('activation_id')
                current=FREQUENCY.state(wearer)['scene'] if clock=='scene' else engine.round_no
                pending['activation_receipt'][clock]=current+1
                wearer.spec['fashion_next_save']=pending
                self.assertEqual(wearer.spec[FASHION.STATE]['history'],issuance)
                self.assertEqual(len(wearer.spec['fashion_save_history']),1)
                self.reject_inconsistent_rearm(engine,wearer,quota,'future-'+clock+' legacy downgrade')

    def test_legitimate_new_scene_second_core_issuance_remains_valid(self):
        engine,wearer,other=self.core_fashion()
        self.assertEqual(RECOVERY.saving_check(engine,wearer,None,8,fixed=5)['fashion_bonus'],4)
        first=deepcopy(wearer.spec[FASHION.STATE]['history'][0])
        engine.end_of_turn(wearer)
        engine.end_scene([wearer,other])
        ITEMS.register_item(engine,wearer,'item/기막힌-패션',source_instance_id='core-save-fashion')
        engine.start_round([wearer,other]);engine.start_of_turn(wearer,initiative_count=20)
        second=engine.activate_fashion_item(wearer,'item/기막힌-패션',instance_id='core-save-fashion')
        self.assertEqual(second['activation_id'],'fashion-save:'+wearer.entity_id+':2')
        self.assertGreater(second['scene'],first['scene'])
        loaded=Engine.import_state(engine.r,json.loads(json.dumps(engine.export_state(),ensure_ascii=False)))
        actual=WORLD.actor_index(loaded)[wearer.entity_id]
        self.assertEqual(RECOVERY.saving_check(loaded,actual,None,8,fixed=5)['fashion_bonus'],4)
        self.assertEqual(RECOVERY.saving_check(loaded,actual,None,8,fixed=5)['fashion_bonus'],0)
        self.assertEqual(len(actual.spec['fashion_save_history']),2)

    def family_world(self, family):
        if family=='core':
            engine,wearer,other=self.core_fashion()
            return engine,wearer,'item/기막힌-패션','core-save-fashion'
        fixture,instance,_=self.fashion()
        ITEMS.unregister_item(fixture.e,fixture.p,'item/근사한-패션-1')
        return fixture.e,fixture.p,'item/근사한-패션-1',instance

    def test_no_id_rearm_in_actual_later_scene_cannot_follow_modern_issuance(self):
        for family in ('core','homebrew'):
            with self.subTest(family=family):
                engine,wearer,item,instance=self.family_world(family)
                pending=deepcopy(wearer.spec['fashion_next_save'])
                self.assertEqual(RECOVERY.saving_check(engine,wearer,None,8,fixed=5)['fashion_bonus'],4)
                issuance=deepcopy(wearer.spec[FASHION.STATE]['history'])
                quota=deepcopy(wearer.spec['frequency_state']['activations'])
                participants=COMBAT.members(engine)
                before_scene=FREQUENCY.state(wearer)['scene']
                self.assertIn(wearer,participants)
                engine.end_of_turn(wearer)
                engine.end_scene(participants)
                self.assertEqual(FREQUENCY.state(wearer)['scene'],before_scene+1)
                pending['activation_receipt'].pop('activation_id')
                pending['activation_receipt']['scene']=FREQUENCY.state(wearer)['scene']
                wearer.spec['fashion_next_save']=pending
                self.assertEqual(wearer.spec[FASHION.STATE]['history'],issuance)
                self.assertEqual(wearer.spec['frequency_state']['activations'],quota)
                with self.assertRaisesRegex(ValueError,'retained activation identity'):
                    FASHION.consume_save_bonus(engine,wearer)
                self.assertEqual(wearer.spec['fashion_next_save'],pending)
                self.reject_inconsistent_rearm(engine,wearer,quota,'actual-next-scene no-ID rearm')

    def test_consumed_legacy_history_coexists_with_later_modern_pending_in_both_families(self):
        for family in ('core','homebrew'):
            with self.subTest(family=family):
                engine,wearer,item,instance=self.family_world(family)
                # Exact pre-modern issuer schema, retaining the genuine old owner.
                wearer.spec['fashion_next_save']['activation_receipt'].pop('activation_id')
                wearer.spec.pop(FASHION.STATE)
                if family=='homebrew':
                    original=engine._physical_objects[instance][FASHION.STATE]
                    original['scene_activation'].pop('activation_id')
                    original['history'][0].pop('activation_id')
                self.assertEqual(RECOVERY.saving_check(engine,wearer,None,8,fixed=5)['fashion_bonus'],4)
                old=deepcopy(wearer.spec['fashion_save_history'][0])
                self.assertNotIn('activation_id',old['activation_receipt'])
                participants=COMBAT.members(engine)
                before_scene=FREQUENCY.state(wearer)['scene']
                self.assertIn(wearer,participants)
                engine.end_of_turn(wearer)
                engine.end_scene(participants)
                self.assertEqual(FREQUENCY.state(wearer)['scene'],before_scene+1)
                ITEMS.register_item(engine,wearer,item,source_instance_id=instance,
                                    as_held=wearer.kind=='pokemon')
                engine.start_round(participants)
                engine.start_of_turn(wearer,initiative_count=20)
                engine.activate_fashion_item(wearer,item,instance_id=instance)
                self.assertIn('activation_id',wearer.spec['fashion_next_save']['activation_receipt'])
                loaded=Engine.import_state(engine.r,json.loads(json.dumps(engine.export_state(),ensure_ascii=False)))
                actual=WORLD.actor_index(loaded)[wearer.entity_id]
                self.assertEqual(actual.spec['fashion_save_history'][0],old)
                self.assertEqual(RECOVERY.saving_check(loaded,actual,None,8,fixed=5)['fashion_bonus'],4)
                self.assertEqual(RECOVERY.saving_check(loaded,actual,None,8,fixed=5)['fashion_bonus'],0)
                self.assertEqual(len(actual.spec['fashion_save_history']),2)

    def test_issued_homebrew_bonus_survives_trusted_terminal_item_observation(self):
        fixture,instance,issued=self.fashion()
        ITEMS.unregister_item(fixture.e,fixture.p,'item/근사한-패션-1')
        # Explicit trusted completed destruction boundary, not evidence of an
        # attack, destruction action cost, or permission to destroy others' items.
        def destroyed(engine,actor):
            return WORLD.finish_physical_use(engine,engine._physical_objects[instance],
                'destroyed',{'source':'gm/fashion-lifetime-observation',
                             'by_actor_id':actor.entity_id,'at':engine.elapsed_seconds})
        GRANTS.transition(fixture.e,fixture.p,destroyed)
        loaded=Engine.import_state(fixture.rules,json.loads(json.dumps(fixture.e.export_state(),ensure_ascii=False)))
        actual=WORLD.actor_index(loaded)[fixture.p.entity_id]
        self.assertIn('destroyed',loaded._physical_objects[instance])
        self.assertEqual(loaded._physical_objects[instance][FASHION.STATE]['history'],[issued])
        self.assertEqual(RECOVERY.saving_check(loaded,actual,None,8,fixed=5)['fashion_bonus'],4)
        self.assertEqual(RECOVERY.saving_check(loaded,actual,None,8,fixed=5)['fashion_bonus'],0)


if __name__=='__main__':unittest.main()