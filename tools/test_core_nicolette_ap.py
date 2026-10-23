"""C11-110: opt-in Nicolette AP calculation through the native live account."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
import action_points as AP
import nicolette_gym as N
import downtime as DT
import state_codec as CODEC
import test_category3_scene_ap as scene_fixture


class NicoletteAPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    def setUp(self):
        scene_fixture.Tests.setUp(self)
        self.e.gm.everyone=self.e.everyone

    def adopt(self,**options):
        args=dict(gm_id='gm/actual-gm',reason='GM adopts Nicolette sample on this actual trainer')
        args.update(options)
        return N.configure_ap(self.e,self.t,**args)

    def raw(self):
        return deepcopy((self.t.spec,self.t.level,self.t.hp,self.t.stats,self.t.modifiers,
            self.t._ap_bound_effects if hasattr(self.t,'_ap_bound_effects') else None,
            self.e.log_lines,self.e.rng.getstate(),self.e.elapsed_seconds))

    def body(self):
        return deepcopy((self.t.level,self.t.spec['level'],self.t.hp,self.t.base_max_hp,
            self.t.stats,self.t.moves,self.t.abilities,self.t.spec.get('xp'),
            self.t.spec.get('skills'),self.t.spec.get('classes'),self.t.spec.get('feats')))

    def reliable(self):return scene_fixture.Tests.reliable(self)

    def test_adoption_changes_only_actual_sample_actor_ap_calculation(self):
        before=self.body();ordinary=AP.maximum(self.t);pokemon=deepcopy(self.p.spec)
        row=self.adopt()
        self.assertEqual(ordinary,10);self.assertEqual(AP.maximum(self.t),13)
        self.assertEqual(self.body(),before);self.assertEqual(self.p.spec,pokemon)
        self.assertEqual(AP.maximum(self.p),0);self.assertNotIn(N.AP_KEY,self.p.spec)
        self.assertEqual(row,dict(actor_id=self.t.entity_id,source=N.AP_SOURCE,
            reference=N.AP_REFERENCE,ap_level=40,bonus_ap=0,gm_id='gm/actual-gm',
            reason='GM adopts Nicolette sample on this actual trainer'))
        row['bonus_ap']=999
        self.assertEqual(AP.maximum(self.t),13)
        view=N.ap_policy(self.t);view['ap_level']=999
        self.assertEqual(N.ap_policy(self.t)['ap_level'],40)

    def test_ap_only_level_floor_bonus_and_replacement_keep_actual_level(self):
        for level,expected in ((1,16),(39,16),(40,16),(44,16),(45,17),(53,18)):
            with self.subTest(actual_level=level):
                self.t.level=self.t.spec['level']=level
                before=self.body();self.adopt(bonus_ap=3)
                self.assertEqual(AP.maximum(self.t),expected);self.assertEqual(self.body(),before)
                self.adopt(bonus_ap=3);self.assertEqual(AP.maximum(self.t),expected)
        self.adopt(ap_level=55,bonus_ap=2)
        self.assertEqual(AP.maximum(self.t),18);self.assertEqual(self.t.level,53)

    def test_native_feature_and_pre_roll_cost_consume_the_sample_maximum(self):
        self.adopt(bonus_ap=2)
        AP.charge(self.t,11);AP.charge(self.t,1,mode='bind',instance_id='other/live-effect')
        self.assertEqual(AP.available(self.t),3)
        out=self.reliable()
        self.assertTrue(out['check'].passed);self.assertEqual(self.t.spec['ap_spent'],13)
        self.assertEqual(AP.available(self.t),1)
        self.e.boost_roll(self.t,self.t,roll_id='sample-last-ap',kind='skill')
        self.assertEqual(self.t.spec['ap_spent'],14);self.assertEqual(AP.available(self.t),0)
        out=self.e.skill_roll(self.t,'육상',fixed=[2,2,2],roll_id='sample-last-ap')
        self.assertEqual(out.total,7);self.assertEqual(self.e._ap_rolls['sample-last-ap']['state'],'resolved')
        before=self.raw()
        with self.assertRaises(ValueError):self.reliable()
        self.assertEqual(self.raw(),before)
        with self.assertRaises(ValueError):self.e.boost_roll(self.t,self.t,roll_id='unfunded',kind='skill')
        self.assertEqual(self.raw(),before);self.assertNotIn('unfunded',self.e._ap_rolls)

    def test_native_binding_scene_and_qualified_rest_share_one_live_account(self):
        self.adopt(bonus_ap=3);handle=self.t.ap_account
        AP.charge(self.t,7);AP.charge(self.t,3,mode='drain')
        AP.charge(self.t,6,mode='bind',instance_id='sample/live-modifier')
        modifier={'type':'damage_roll_mod','value':3};self.t.modifiers.append(modifier)
        result=self.e.adopt_bound_ap_modifier(self.t,'sample/live-modifier',modifier=modifier,
            ending_method='none_specified',source_ref='test_fixture/explicit-existing-modifier')
        self.assertEqual(result.status,'adopted');self.assertEqual(handle.available(),0)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t);self.e.end_of_turn(self.t)
        self.e.end_encounter(round_elapsed_seconds=1)
        self.assertEqual(handle.available(),0);self.assertEqual(N.ap_policy(self.t)['bonus_ap'],3)
        self.e.end_scene();self.assertEqual(handle.available(),7)
        self.assertEqual(self.t.spec['ap_removed'],3)
        self.assertEqual(self.t.spec['ap_bound'],{'sample/live-modifier':6})
        DT.extended_rest(self.e,self.t,3,rest_id='sample-qualified-rest')
        self.assertEqual(handle.available(),7)
        DT.extended_rest(self.e,self.t,1,rest_id='sample-qualified-rest')
        self.assertEqual(handle.available(),10);self.assertEqual(self.t.spec['ap_removed'],0)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.t)
        result=self.e.release_bound_ap(self.t,'sample/live-modifier',event_id='sample-end-modifier')
        self.assertEqual(result.status,'released');self.assertEqual(result.released_ap,6)
        self.assertEqual(handle.available(),16);self.assertFalse(self.t.modifiers)
        self.assertEqual(self.t.level,25);self.assertIn(N.AP_KEY,self.t.spec)

    def test_reconfiguration_neither_refills_nor_erases_existing_commitments(self):
        self.adopt(bonus_ap=7);AP.charge(self.t,10);AP.charge(self.t,3,mode='drain')
        AP.charge(self.t,5,mode='bind',instance_id='live-reservation')
        handle=self.t.ap_account;self.assertEqual(handle.available(),2)
        self.adopt(bonus_ap=5);self.assertEqual(handle.available(),0)
        before=self.raw()
        with self.assertRaises(ValueError):self.adopt(bonus_ap=0)
        self.assertEqual(self.raw(),before);self.assertEqual(handle.maximum(),18)
        self.adopt(bonus_ap=8);self.assertEqual(handle.available(),3)
        self.assertEqual((self.t.spec['ap_spent'],self.t.spec['ap_removed'],self.t.spec['ap_bound']),
            (10,3,{'live-reservation':5}))
        self.assertEqual(self.t.level,25)

    def test_adoption_rejects_unregistered_actors_and_invalid_explicit_gm_inputs(self):
        before=self.raw()
        ghost=Combatant(self.r,{**deepcopy(self.t.spec),'id':'unregistered/actor'})
        for actor in (ghost,self.p):
            with self.subTest(actor=actor.entity_id),self.assertRaises(ValueError):
                N.configure_ap(self.e,actor,gm_id='gm/actual',reason='explicit sample adoption')
            self.assertEqual(self.raw(),before)
        for options in ({'ap_level':39},{'ap_level':True},{'ap_level':40.0},
                {'bonus_ap':-1},{'bonus_ap':True},{'bonus_ap':1.5},{'gm_id':''},{'reason':' '}):
            with self.subTest(options=options),self.assertRaises(ValueError):self.adopt(**options)
            self.assertEqual(self.raw(),before)

    def test_corrupt_foreign_or_changed_source_policy_refuses_native_ap_consumers(self):
        self.adopt(bonus_ap=2);original=deepcopy(self.t.spec[N.AP_KEY])
        for key,value in (('actor_id',self.p.entity_id),('source','gameplay/action-points'),
                ('reference',{}),('ap_level',39),('bonus_ap',True),('gm_id',''),('reason','')):
            self.t.spec[N.AP_KEY]=deepcopy(original);self.t.spec[N.AP_KEY][key]=value
            before=self.raw()
            for operation in (lambda:AP.maximum(self.t),lambda:AP.charge(self.t,1),
                    lambda:AP.end_scene(self.t),lambda:AP.extended_rest(self.t)):
                with self.subTest(field=key),self.assertRaises(ValueError):operation()
                self.assertEqual(self.raw(),before)
        self.t.spec[N.AP_KEY]=deepcopy(original)
        import source_context
        real_source=source_context.verified_source
        def stale(rules,reference,**options):
            if reference==N.AP_REFERENCE:raise ValueError('actual sample source changed')
            return real_source(rules,reference,**options)
        before=self.raw()
        with patch.object(source_context,'verified_source',side_effect=stale):
            for operation in (lambda:self.adopt(),lambda:AP.maximum(self.t),
                    lambda:AP.charge(self.t,1),lambda:AP.end_scene(self.t),lambda:AP.extended_rest(self.t)):
                with self.assertRaises(ValueError):operation()
                self.assertEqual(self.raw(),before)
        reader=self.r._selected_rule
        def replacement(uid,*args,**options):
            return 'gameplay/action-points' if uid==N.AP_SOURCE else reader(uid,*args,**options)
        with patch.object(self.r,'_selected_rule',side_effect=replacement):
            with self.assertRaises(ValueError):AP.maximum(self.t)
        with patch.dict(self.r.rulings.mech,{N.AP_SOURCE:{'sample_level':99}}):
            with self.assertRaises(ValueError):AP.maximum(self.t)
        self.assertEqual(self.raw(),before)

    def test_gm_and_json_restore_preserve_one_actor_policy_and_existing_live_usage(self):
        self.adopt(bonus_ap=2);AP.charge(self.t,11);handle=self.t.ap_account
        self.e.gm.snapshot('sample-ap')
        self.adopt(ap_level=50,bonus_ap=3);AP.charge(self.t,2)
        self.assertEqual(handle.available(),5)
        self.e.gm.restore('sample-ap')
        self.assertEqual((handle.maximum(),handle.available()),(15,4))
        loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
        actors={a.entity_id:a for a in loaded.everyone};actual=actors[self.t.entity_id]
        self.assertEqual((AP.maximum(actual),AP.available(actual)),(15,4))
        self.assertEqual(actual.level,25);self.assertEqual(actual.spec['ap_spent'],11)
        self.assertEqual(N.ap_policy(actual),N.ap_policy(self.t))
        self.assertNotIn(N.AP_KEY,actors[self.p.entity_id].spec)
        loaded.boost_roll(actual,actual,roll_id='restored-sample-cost',kind='skill')
        self.assertEqual(AP.available(actual),3);self.assertEqual(AP.available(self.t),4)

    def test_no_profile_does_not_read_or_require_the_optional_sample_source(self):
        before=self.body()
        with patch.object(N,'_ap_source',side_effect=AssertionError('optional sample not adopted')):
            self.assertEqual(AP.maximum(self.t),10);self.assertEqual(AP.maximum(self.p),0)
            self.assertTrue(self.reliable()['check'].passed)
            self.assertEqual(AP.available(self.t),8)
            self.e.end_scene();self.assertEqual(AP.available(self.t),10)
        self.assertEqual(self.body(),before);self.assertNotIn(N.AP_KEY,self.t.spec)
