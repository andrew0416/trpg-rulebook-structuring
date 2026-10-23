"""C06-027: admitted native payloads share one AP reservation and real endings.

The application declaration exercises the general AP contract, not the legal
acquisition or interpretation of a separate source feature.
"""
from copy import copy,deepcopy
from hashlib import sha256
from pathlib import Path
import sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_trainer
from state_codec import dump_engine,load_engine
import action_points as AP
import effects as FX
import effect_lifetimes as LIFE
import combat_timing as TIMING


class GeneralAPContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def setUp(self):
        self.r=copy(self.rules);self.r.ruleset=deepcopy(self.rules.ruleset)
        self.r.selection=copy(self.rules.selection);self.r.selection.filter=self.r.ruleset
        self.e=Engine(self.r,17)
        def trainer(name):
            return Combatant(self.r,build_trainer(self.r,name,10,
                {key:20 for key in ('hp','atk','def','spa','spd','spe')},abilities=[]))
        self.a,self.b=trainer('AP owner'),trainer('actual recipient')
        self.e.everyone=self.e.gm.everyone=[self.a,self.b]
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        source='input/ch06-gameplay.md'
        self.row={'rule_id':'gameplay/action-points',
                  'source':{'file':source,'sha256':sha256((ROOT/source).read_bytes()).hexdigest()},
                  'inputs':{},'values':{}}
        self.doc={'schema':1,'id':'general-AP-native-contract','variants':[self.row]}

    def activate(self,effects=None,*,ending='none_specified',instance='AP/bundle',request='AP/activate'):
        self.row['values']={'action':'free','ap':{'mode':'bind','amount':2,
            'instance_id':instance,'ending_method':ending},'effects':effects or [
            {'type':'damage_roll_mod','value':4,'target':'self'},
            {'type':'accuracy_mod','value':2,'target':'target'}]}
        return self.e.execute_source_policy_action(self.a,self.b,self.doc,request_id=request)

    def damage(self):
        return FX.passive_damage_mods(self.e,self.a,self.b,{'type':'노말','class':'물리'},
                                     {'attacker':self.a,'target':self.b})[1]

    def end(self,event='AP/end'):
        return self.e.release_bound_ap(self.a,'AP/bundle',event_id=event)

    def test_native_bundle_owns_actual_payloads_and_free_release_keeps_siblings(self):
        sibling={'type':'damage_roll_mod','value':3};self.a.modifiers.append(sibling)
        result=self.activate()
        self.assertEqual(result['status'],'PolicyActionCompleted')
        self.assertEqual(self.a.spec['ap_bound'],{'AP/bundle':2})
        self.assertEqual((AP.available(self.a),self.damage(),LIFE.numeric(self.b,'accuracy_modifier')),(5,7,2))
        budget=dict(self.a.budget);rng=self.e.rng.getstate()
        released=self.end()
        self.assertEqual((released.status,released.released_ap,released.performed_free_action),('released',2,True))
        self.assertEqual((AP.available(self.a),self.damage(),LIFE.numeric(self.b,'accuracy_modifier')),(7,3,0))
        self.assertIs(self.a.modifiers[0],sibling)
        self.assertEqual(self.a.budget,budget);self.assertEqual(self.e.rng.getstate(),rng)
        self.assertEqual(self.a._action_history,['free','free'])

    def test_source_ending_cannot_bypass_default_own_turn_free_action(self):
        self.activate();before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'own-turn Free Action'):
            self.e.end_effects(self.b,source='gameplay/action-points')
        self.assertEqual(dump_engine(self.e),before)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b)
        before=dump_engine(self.e)
        self.assertEqual(self.end().reason,'own_open_turn_required')
        self.assertEqual(dump_engine(self.e),before)

    def test_native_scene_and_qualified_rest_preserve_bound_effect_and_one_pool(self):
        import downtime as DT
        self.activate();AP.charge(self.a,1);AP.charge(self.a,1,mode='drain')
        self.assertEqual(AP.available(self.a),3)
        FX.run_effects(self.e,self.a,self.b,[{'type':'accuracy_mod','value':-1,'until':'scene_end'}],
                       {'hit':True},'gm/ordinary-stage-expiry')
        self.assertEqual(LIFE.numeric(self.b,'accuracy_modifier'),1)
        self.e.end_of_turn(self.a);self.e.end_scene(round_elapsed_seconds=1)
        self.assertEqual((AP.available(self.a),self.a.spec['ap_removed'],self.damage()),(4,1,4))
        self.assertEqual(LIFE.numeric(self.b,'accuracy_modifier'),2)
        self.assertFalse(any(row['source']=='gm/ordinary-stage-expiry' for row in TIMING.records(self.b)))
        DT.extended_rest(self.e,self.a,4,rest_id='AP/qualified-rest')
        self.assertEqual((AP.available(self.a),self.a.spec['ap_removed']),(5,0))
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
        self.assertEqual(self.end().released_ap,2);self.assertEqual(AP.available(self.a),7)

    def test_specified_native_boundaries_refund_only_after_last_component(self):
        self.activate([
            {'type':'accuracy_mod','value':2,'target':'target',
             'until':{'event':'turn_end','owner':'target'}},
            {'type':'damage_roll_mod','value':4,'target':'self','until':{'event':'scene_end'}}],ending='specified')
        self.assertEqual(self.end().reason,'specified_end_method_requires_its_own_path')
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.b);self.e.end_of_turn(self.b)
        self.assertEqual(LIFE.numeric(self.b,'accuracy_modifier'),0)
        self.assertEqual((AP.available(self.a),self.damage()),(5,4))
        self.e.end_scene(round_elapsed_seconds=1)
        self.assertEqual((AP.available(self.a),self.damage()),(7,0))
        self.assertEqual(self.a._ap_bound_effects['AP/bundle']['end_event']['kind'],'scene_end')

    def test_existing_source_termination_ends_payload_then_exact_reservation(self):
        self.activate([
            {'type':'type_change','add_type':'불꽃','target':'target','until':{'event':'scene_end'}},
            {'type':'damage_roll_mod','value':4,'target':'self','until':{'event':'scene_end'}}],ending='specified')
        self.assertIn('불꽃',self.b.types)
        self.assertEqual(self.e.end_effects(self.b,source='gameplay/action-points'),1)
        self.assertNotIn('불꽃',self.b.types);self.assertEqual(AP.available(self.a),5)
        self.assertEqual(self.e.end_effects(self.a,source='gameplay/action-points'),1)
        self.assertEqual((AP.available(self.a),self.damage()),(7,0))
        self.assertEqual(self.e.end_effects(self.a,source='gameplay/action-points'),0)
        self.assertEqual(AP.available(self.a),7)

    def test_failed_component_or_unknown_ending_never_pays_or_leaves_partial_effect(self):
        for ending,effects in [
            ('unknown',[{'type':'accuracy_mod','value':2}]),
            ('specified',[{'type':'accuracy_mod','value':2}]),
            ('none_specified',[{'type':'heal','amount':20}]),
            ('none_specified',[{'type':'accuracy_mod','value':2,'until':'scene_end'}]),
            ('none_specified',[{'type':'damage_roll_mod','value':4},
                               {'type':'type_change','add_type':'not-a-type'}])]:
            with self.subTest(ending=ending,effects=effects):
                before=dump_engine(self.e)
                with self.assertRaises(ValueError):self.activate(effects,ending=ending)
                self.assertEqual(dump_engine(self.e),before)

    def test_native_activation_failure_after_first_payload_is_atomic(self):
        from unittest.mock import patch
        import effect_lifetimes
        original=effect_lifetimes.install;calls=[]
        def fail_second(*args,**kwargs):
            calls.append(1)
            if len(calls)==2:raise ValueError('injected second native payload failure')
            return original(*args,**kwargs)
        before=dump_engine(self.e)
        with patch.object(effect_lifetimes,'install',fail_second),self.assertRaises(ValueError):self.activate()
        self.assertEqual(len(calls),2);self.assertEqual(dump_engine(self.e),before)

    def test_manual_termination_failure_rolls_back_free_action_effects_and_AP(self):
        from unittest.mock import patch
        import state_grants
        self.activate();before=dump_engine(self.e)
        with patch.object(state_grants.ActiveEffects,'remove',side_effect=ValueError('injected owned removal failure')):
            with self.assertRaises(ValueError):self.end()
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(self.end().status,'released')

    def test_actual_holder_and_modifier_aliases_hold_before_free_action_or_refund(self):
        self.activate([
            {'type':'damage_roll_mod','value':4,'target':'self'},
            {'type':'accuracy_mod','value':2,'target':'target'},
            {'type':'apply_status','status':'둔화','target':'target'},
            {'type':'type_change','add_type':'불꽃','target':'target'},
            {'type':'initiative','delta':3,'target':'target'}])
        import state_codec as CODEC
        def graph():
            # Public dump rejects the deliberately invalid native payload.
            # Encode its actual graph without accepting it as a valid save.
            encoder=CODEC._Encoder(self.e);root=encoder.value(self.e)
            return root,encoder.nodes
        numeric,status,types,initiative=TIMING.records(self.b)
        missing=object()
        for record,key,value in [
            (numeric,'accuracy_modifier',99),
            (status,'statuses',['잠듦']),
            (status,'owned_statuses',{'잠듦'}),
            (types,'type_operation',{'mode':'set','values':['물'],'fallback':None}),
            (initiative,'initiative_operation',{'operation':'replace','value':0,'priority':0}),
            (numeric,'forbidden_actions',['all']),
            (numeric,'stat_exchange',{'pairs':[['atk','def']],'boundaries':['scene_end']}),
            (numeric,'catalog_move_lock',{'keyword':'all'}),
            (numeric,'timing_text','scene_end'),
            (numeric,'scene_end',True),
            (numeric,'manual_end',False),
            (types,'grant_source','different/native/source')]:
            with self.subTest(key=key):
                original=record.get(key,missing);record[key]=value;before=graph()
                try:result=self.end();self.assertEqual(result.status,'pending')
                except ValueError:pass  # Existing native world validation may reject it first.
                self.assertEqual(graph(),before)
                if original is missing:record.pop(key)
                else:record[key]=original
        modifier=self.a.modifiers[0]
        FX.apply_passives(self.e,self.b,[modifier]);before=dump_engine(self.e)
        result=self.end();self.assertEqual(result.status,'pending')
        self.assertIn('shared bound modifier',result.reason);self.assertEqual(dump_engine(self.e),before)
        self.b.modifiers.remove(modifier)
        record=TIMING.records(self.b)[0];self.a.custom_conditions[TIMING.KEY].append(record)
        before=dump_engine(self.e)
        self.assertEqual(self.end().status,'pending');self.assertEqual(dump_engine(self.e),before)
        self.a.custom_conditions[TIMING.KEY][:]=[row for row in TIMING.records(self.a) if row is not record]
        self.assertEqual(self.end().status,'released');self.assertEqual(AP.available(self.a),7)
        self.assertNotIn('둔화',self.b.conditions);self.assertNotIn('불꽃',self.b.types)
        self.assertFalse(TIMING.records(self.b))

    def test_different_bindings_duplicate_releases_and_activation_replays_cannot_refund_twice(self):
        self.activate();first=self.a._ap_bound_effects['AP/bundle']
        self.activate(instance='AP/other',request='AP/activate-other')
        self.assertEqual(AP.available(self.a),3)
        self.assertEqual(self.end().released_ap,2);self.assertEqual(AP.available(self.a),5)
        self.assertEqual(self.end().reason,'effect_already_ended')
        self.assertEqual(self.e.release_bound_ap(self.a,'AP/other',event_id='AP/end').reason,'event_id_already_used')
        self.assertEqual(self.e.release_bound_ap(self.a,'AP/other',event_id='AP/end-other').released_ap,2)
        self.assertEqual(AP.available(self.a),7)
        self.row['values']['ap']['instance_id']='AP/bundle'
        self.assertTrue(self.e.execute_source_policy_action(self.a,self.b,self.doc,request_id='AP/activate')['replayed'])
        self.assertFalse(TIMING.records(self.a));self.assertFalse(TIMING.records(self.b))
        self.assertNotIn('owner',first);self.assertNotIn('components',first)

    def test_league_and_action_conditions_hold_new_bundle_release(self):
        self.activate()
        for condition in ('잠듦','얼음'):
            with self.subTest(condition=condition):
                self.a.conditions.add(condition);before=dump_engine(self.e)
                self.assertEqual(self.end().reason,'free_action_blocked_by_condition')
                self.assertEqual(dump_engine(self.e),before);self.a.conditions.remove(condition)
        self.e._league_runtime={'active':True};before=dump_engine(self.e)
        self.assertEqual(self.end().status,'pending');self.assertEqual(dump_engine(self.e),before)

    def test_native_records_and_one_reservation_survive_existing_json_restore(self):
        self.activate();loaded=load_engine(self.r,dump_engine(self.e))
        owner,target=loaded.everyone
        parts=owner._ap_bound_effects['AP/bundle']['components']
        self.assertIs(parts[0]['holder'],owner)
        self.assertTrue(any(parts[0]['record']is record for record in TIMING.records(owner)))
        self.assertIs(parts[1]['holder'],target)
        self.assertEqual(loaded.release_bound_ap(owner,'AP/bundle',event_id='AP/restored-end').released_ap,2)
        self.assertEqual(AP.available(owner),7);self.assertFalse(owner.modifiers)
        self.assertEqual(LIFE.numeric(target,'accuracy_modifier'),0)


if __name__=='__main__':unittest.main()
