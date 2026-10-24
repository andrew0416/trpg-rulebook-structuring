"""FAN208/209: native Master grants authorize actual metal weapon bond/recall."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest

import acquired_features as ACQUIRED
import capability_actions as CAP
import items as ITEMS
import native_scenario_fixture as NATIVE
import optional_weapon_framework as FW
import state_codec as CODEC
import state_grants as G
import world_entities as W

ROOT=Path(__file__).resolve().parents[1]
GRANTED=('무기 부름','무한의 강제')


class MasterOfWeaponsSourceRevisionTests(unittest.TestCase):
    def world(self,*,master=True,extra=None):
        def actor(key,pos,side,owned=False):
            observations={'skills':{'전투':3,'육상':5,'집중':5},
                'movement':{'land':6,'power':3},'movement_basis':'current'}
            if owned:
                observations.update(feats=[FW.STEELHEART]+([FW.MASTER] if master else []),
                    edges=['edge/원소-교감'],edge_choices={'edge/원소-교감':'강철'})
                observations.update(extra or {})
            sheet={'name':key,'level':40,'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),
                   'moves':['move/몸통박치기'],'abilities':[],'pos':pos,'side':side,'extra':observations}
            return {'key':key,'kind':'trainer','sheet':sheet,
                    'body':{'size':'중형','offsets':[(0,0)],'reason':'actual observed master and physical weapon holder'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=208209,
            grid={'width':30,'height':12},actors=[actor('master',(2,2),'party',True),
                                                  actor('holder',(4,2),'opponent')])
        self.a,self.h=(actors[key] for key in ('master','holder'))

    def source(self):return 'feature:'+self.a.entity_id+':'+FW.MASTER

    def weapon(self,uid='master/weapon',*,metal=True):
        W.register_object(self.e,uid,owner_id=self.a.entity_id,weight_kg=1,
                          location={'kind':'unknown'},reason='actual owned physical weapon')
        FW.observe_weapon(self.e,self.a,uid,name=uid,kind='소형 근접무기',grade='좋음',
                          arcane=False,metal=metal,moves=[],reason='observed actual material and weapon form')
        return uid

    def turn(self):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def restore(self):
        identities=[c.entity_id for c in (self.a,self.h)]
        self.e=CODEC.load_engine(self.e.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=W.actor_index(self.e);self.a,self.h=(index[key] for key in identities)

    def assert_grants(self):
        row=self.a.spec[G.KEY]['sources'][self.source()]
        self.assertEqual((row['kind'],row['rule_id'],row['owner_id'],row['lifetime']),
                         ('feature',FW.MASTER,self.a.entity_id,'while_owned'))
        self.assertCountEqual(row['grants']['capabilities'],GRANTED)
        # This is the live native consumer, rather than a declaration assertion.
        for name in GRANTED:self.assertEqual(G.effective_capabilities(self.a).count(name),1)
        self.assertEqual(ACQUIRED.owned_rule_count(self.a,FW.MASTER),1)
        self.assertNotIn(FW.CALL,self.a.spec['feats'])
        self.assertNotIn('feat/무한의-강제',self.a.spec['feats'])
        self.assertTrue(FW.owns(self.a,FW.CALL))

    def test_real_registered_master_grants_both_capabilities_and_restored_native_bond_recall(self):
        self.world();self.assert_grants();before=deepcopy(self.a.spec[G.KEY])
        ITEMS.register_feats(self.e,self.a)
        self.assertEqual(self.a.spec[G.KEY],before)
        uid=self.weapon();count=len(self.e._physical_objects)
        receipt=FW.bond(self.e,self.a,uid,family='steelheart')
        self.assertEqual((receipt['source'],receipt['instance_id']),(FW.CALL,uid))
        W.register_object(self.e,uid,location={'kind':'grid','cell':(12,2)},reason='actual unheld bonded weapon ten metres away')
        self.e.gm.snapshot('natural-master');self.e.gm.restore('natural-master');self.restore()
        self.assert_grants();self.turn();rng=self.e.rng.getstate()
        result=FW.recall(self.e,self.a,family='steelheart')
        self.assertTrue(result['recalled']);self.assertEqual(result['instance_id'],uid)
        self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(len(self.e._physical_objects),count)
        self.assertEqual(self.e._physical_objects[uid]['equipped_by'],self.a.entity_id)
        self.restore();self.assert_grants();self.assertTrue(self.e.validate_state()['valid'])

    def test_extended_bond_replacement_material_range_and_receiver_failures_keep_native_state(self):
        self.world();first=self.weapon('master/old');second=self.weapon('master/new')
        FW.bond(self.e,self.a,first,family='steelheart')
        FW.bond(self.e,self.a,second,family='steelheart')
        self.assertEqual(self.a.spec[FW.BONDS]['steelheart']['instance_id'],second)
        wrong=self.weapon('master/nonmetal',metal=False)
        NATIVE.assert_rejected_unchanged(self.e,lambda:FW.bond(self.e,self.a,wrong,family='steelheart'),
                                         reason_pattern='requires a metal weapon')
        W.register_object(self.e,second,location={'kind':'grid','cell':(13,2)},reason='actual weapon eleven metres away')
        self.turn()
        NATIVE.assert_rejected_unchanged(self.e,lambda:FW.recall(self.e,self.a,family='steelheart'),
                                         reason_pattern='beyond ten metres')
        W.register_object(self.e,second,location={'kind':'grid','cell':(12,2)},reason='actual weapon at ten metre boundary')
        with patch.object(FW,'equip',side_effect=ValueError('actual recall receiver failed')):
            NATIVE.assert_rejected_unchanged(self.e,lambda:FW.recall(self.e,self.a,family='steelheart'),
                                             reason_pattern='actual recall receiver failed')
        self.assertEqual(self.a.budget['shift'],1)
        self.assertTrue(self.e.validate_state()['valid'])

    def test_actual_unwilling_holder_loses_ties_then_is_disarmed_on_paid_success_without_copy(self):
        for skill in ('육상','집중'):
            with self.subTest(skill=skill):
                self.world();uid=self.weapon();FW.bond(self.e,self.a,uid,family='steelheart')
                CAP.set_carried(self.e,self.h,[{'id':uid,'weight_kg':1}],'actual unwilling holder carries the bond weapon')
                FW.equip(self.e,self.h,uid);count=len(self.e._physical_objects)
                self.turn();rng=self.e.rng.getstate()
                result=FW.recall(self.e,self.a,family='steelheart',unwilling=True,skill=skill,
                    challenger_options={'fixed':[2]*5},defender_options={'fixed':[2]*5})
                self.assertFalse(result['recalled']);self.assertEqual(self.a.budget['shift'],0)
                self.assertEqual(self.e._physical_objects[uid]['equipped_by'],self.h.entity_id)
                self.assertEqual(self.e.rng.getstate(),rng)
                self.turn()
                result=FW.recall(self.e,self.a,family='steelheart',unwilling=True,skill=skill,
                    challenger_options={'fixed':[6]*5},defender_options={'fixed':[1]*5})
                self.assertTrue(result['recalled']);self.assertTrue(result['opposed'])
                self.assertEqual(self.a.budget['shift'],0)
                self.assertEqual(self.e._physical_objects[uid]['equipped_by'],self.a.entity_id)
                self.assertFalse(self.h.custom_conditions.get('equipped_weapons'))
                self.assertFalse(self.h.spec['_carried_load']['objects'])
                self.assertEqual(len(self.e._physical_objects),count)
                self.assertTrue(self.e.validate_state()['valid'])

    def test_call_feat_feature_and_capability_strings_do_not_establish_master_grant_authority(self):
        for extra in ({'feats':[FW.STEELHEART,FW.CALL]},
                      {'features':['무기 부름']},
                      {'capabilities':list(GRANTED)},
                      {'features':[FW.MASTER],'capabilities':list(GRANTED)}):
            with self.subTest(extra=extra):
                self.world(master=False,extra=extra);uid=self.weapon()
                self.assertFalse(FW.owns(self.a,FW.CALL))
                NATIVE.assert_rejected_unchanged(self.e,lambda:FW.bond(self.e,self.a,uid,family='steelheart'),
                                                 reason_pattern='actual acquired weapon feature required')
                NATIVE.assert_rejected_unchanged(self.e,lambda:FW.recall(self.e,self.a,family='steelheart'),
                                                 reason_pattern='actual acquired weapon feature required')

    def test_withdrawn_master_source_does_not_borrow_other_owner_or_independent_capability_authority(self):
        for baseline in (False,True):
            with self.subTest(baseline=baseline):
                self.world(extra={'capabilities':list(GRANTED)} if baseline else None)
                self.assert_grants();uid=self.weapon()
                G.revoke(self.a,self.source(),engine=self.e)
                self.assertEqual(set(G.effective_capabilities(self.a)).intersection(GRANTED),
                                 set(GRANTED) if baseline else set())
                self.assertFalse(FW.owns(self.a,FW.CALL))
                NATIVE.assert_rejected_unchanged(self.e,lambda:FW.bond(self.e,self.a,uid,family='steelheart'),
                                                 reason_pattern='actual acquired weapon feature required')
                other='fixture:other-master-capability'
                for name in GRANTED:
                    G.grant(self.a,'capabilities',name,other,'feature',owner_id=self.h.entity_id,
                            lifetime='while_owned',rule_id=FW.MASTER)
                self.assertCountEqual(set(G.effective_capabilities(self.a)).intersection(GRANTED),GRANTED)
                self.restore();self.assertFalse(FW.owns(self.a,FW.CALL))
                NATIVE.assert_rejected_unchanged(self.e,lambda:FW.bond(self.e,self.a,uid,family='steelheart'),
                                                 reason_pattern='actual acquired weapon feature required')
                ITEMS.register_feats(self.e,self.a);self.assert_grants()
                FW.bond(self.e,self.a,uid,family='steelheart')
                self.assertTrue(self.e.validate_state()['valid'])

    def test_selected_master_and_current_ownership_remain_required_despite_retained_grants(self):
        self.world();self.assert_grants();uid=self.weapon()
        original=self.e.r._selected_rule;before=self.e.export_state()
        def changed(rule,*args,**options):
            return 'other/master-source' if rule==FW.MASTER else original(rule,*args,**options)
        with patch.object(self.e.r,'_selected_rule',changed):
            with self.assertRaisesRegex(ValueError,'selected acquisition source'):
                FW.bond(self.e,self.a,uid,family='steelheart')
        self.assertEqual(self.e.export_state(),before)
        self.a.spec['feats'].remove(FW.MASTER)
        self.assertCountEqual(set(G.effective_capabilities(self.a)).intersection(GRANTED),GRANTED)
        self.assertFalse(FW.owns(self.a,FW.CALL))
        NATIVE.assert_rejected_unchanged(self.e,lambda:FW.bond(self.e,self.a,uid,family='steelheart'),
                                         reason_pattern='actual acquired weapon feature required')


if __name__=='__main__':unittest.main()
