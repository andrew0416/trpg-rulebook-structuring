"""C09-069: actual four-egg containment consumed by native hatching."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json, unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'output').is_dir():ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
from engine import Rules
from builder import build_trainer, build_pokemon
from state_codec import dump_engine, load_engine
import test_foundation_egg_creation as eggs
import test_foundation_fossil_creation as fossils
import physical_incubator as INC, creation_egg as E, pokemon_entities as P
import world_entities as W, state_grants as G, pokemon_party as PARTY
import csv_item_capability_contracts as CAP


class PhysicalIncubatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    add=eggs.EggTests.add
    policy=eggs.EggTests.policy
    choices=eggs.EggTests.choices
    create=eggs.EggTests.create
    hatch=eggs.EggTests.hatch
    def setUp(self):
        eggs.EggTests.setUp(self)
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[1,1]},reason='actual incubator user')
        self.box('box')
    def box(self,identity,item=INC.ITEM):
        W.register_object(self.e,identity,kind='item_instance',item_rule_id=item,owner_id=self.a.entity_id,
            location={'kind':'grid','cell':[1,1]},reason='actual individual physical box')
        if item==INC.ITEM:INC.observe_empty(self.e,self.a,identity,reason='actual empty egg chamber inspected')
        return self.e._physical_objects[identity]
    def egg(self,seconds=86400,identity='egg'):
        value=self.policy();value['work_seconds']=0;value['hatch']['seconds']=seconds
        row=self.create(value,request_id=identity)
        return P.egg_index(self.e)[row['entity_id']][1]
    def store(self,row,box='box'):
        return INC.store(self.e,self.a,box,row['entity_id'],reason='actual egg placed in this box')
    def remove(self,row):
        return INC.remove(self.e,self.a,row['entity_id'],reason='actual egg removed into owner possession')
    def restore(self):
        identity=self.a.entity_id
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
        self.a=W.actor_index(self.e)[identity]
        self.parents=[W.actor_index(self.e)[p.entity_id] for p in self.parents]
    def test_four_actual_eggs_each_box_and_fifth_duplicate_or_foreign_body_reject_atomically(self):
        rows=[self.egg(identity='egg'+str(n)) for n in range(5)]
        for row in rows[:4]:self.store(row)
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'four'):self.store(rows[4])
        self.assertEqual(dump_engine(self.e),before)
        self.box('other')
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'already'):self.store(rows[0],'other')
        self.assertEqual(dump_engine(self.e),before)
        self.remove(rows[0]);self.store(rows[4]);self.store(rows[0],'other')
        self.box('csv',item='item/부화기-1');before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'actual.*Incubator'):INC.observe_empty(self.e,self.a,'csv',reason='separate CSV body')
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(INC.describe(self.e,'box'),{'source':INC.ITEM,'capacity':4,'hatch_rate':2,'price':2500,'egg_ids':[row['entity_id'] for row in rows[1:]]})
        self.assertTrue(self.e.validate_state()['valid'])
    def test_exact_double_speed_uses_original_native_declared_birth_and_frees_slot(self):
        row=self.egg();outside=self.egg(identity='outside');original=deepcopy(row[E.CONTRACT])
        self.store(row);self.e.advance_time(43199,[])
        self.assertEqual(E.hatch_remaining(self.e,row),2)
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(row,ready=None)
        self.assertEqual(dump_engine(self.e),before)
        self.e.advance_time(1,[])
        child=self.hatch(row,ready=None)['pokemon']
        self.assertEqual(child.spec['egg_entity_id'],row['entity_id'])
        self.assertEqual(child.spec['move_learning']['move/뿌리박기']['teacher_id'],self.a.entity_id)
        self.assertEqual(row[E.CONTRACT],original);self.assertEqual(row['produced_at'],0)
        self.assertEqual(E.hatch_remaining(self.e,outside),43200)
        self.assertEqual(INC.describe(self.e,'box')['egg_ids'],[])
        self.assertIsNone(P.egg_projection(self.e,row['entity_id'])['protected_by'])
        self.assertTrue(self.e.validate_state()['valid'])
    def test_one_day_inside_is_two_days_total_and_only_real_contained_intervals_accelerate(self):
        row=self.egg(10*86400);self.e.advance_time(3600,[]);self.store(row)
        self.e.advance_time(86400,[])
        self.assertEqual(E.hatch_remaining(self.e,row),10*86400-3600-2*86400)
        self.remove(row);self.e.advance_time(300,[]);self.box('second');self.store(row,'second')
        self.e.advance_time(7,[]);self.remove(row)
        self.assertEqual(INC.extra_seconds(self.e,row),86407)
        self.assertEqual(E.hatch_remaining(self.e,row),10*86400-self.e.elapsed_seconds-86407)
        self.assertTrue(self.e.validate_state()['valid'])
    def test_carrier_location_and_physical_access_survive_restore_and_ownership_transfer(self):
        row=self.egg(0);self.store(row)
        import capability_actions as C
        C.set_carried(self.e,self.a,[{'id':'box','weight_kg':1}],reason='actual box with eggs lifted')
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[5,5]},reason='actual carrier walked')
        self.assertEqual(W.effective_location(self.e,row)['cell'],(5,5))
        self.assertEqual(P.egg_projection(self.e,row['entity_id'])['physical_location']['cell'],(5,5))
        receiver=self.add(build_trainer(self.r,'recipient',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'edges':[]}))
        W.observe_location(self.e,receiver,{'kind':'grid','cell':[9,9]},reason='actual remote recipient')
        self.e.gm.transfer_egg(self.a,receiver,row['entity_id'],reason='egg ownership gift; still inside actual box',request_id='gift')
        self.e.advance_time(123,[]);self.restore()
        row=P.egg_index(self.e)[row['entity_id']][1];receiver=W.actor_index(self.e)[receiver.entity_id]
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'physically'):INC.remove(self.e,receiver,row['entity_id'],reason='cannot reach held box')
        with self.assertRaisesRegex(ValueError,'physically'):self.e.hatch_declared_egg(receiver,row['entity_id'],name='remote',reason='remote hatch',choices=self.choices())
        with self.assertRaisesRegex(ValueError,'physically'):self.e.gm.transfer_egg(receiver,self.a,row['entity_id'],reason='remote registry cannot move egg',request_id='remote')
        self.assertEqual(dump_engine(self.e),before)
        C.set_carried(self.e,self.a,[],reason='actual box released')
        W.observe_location(self.e,self.e._physical_objects['box'],{'kind':'grid','cell':[9,9]},reason='box delivered to recipient')
        INC.remove(self.e,receiver,row['entity_id'],reason='actual recipient opens delivered box')
        self.assertEqual(INC.extra_seconds(self.e,row),123)
        self.assertIsNone(P.egg_projection(self.e,row['entity_id'])['protected_by'])
        self.assertTrue(self.e.validate_state()['valid'])
    def test_unknown_hatch_timing_keeps_incubation_and_existing_warmer_warmth_separate(self):
        row=self.egg(None);self.store(row);self.e.advance_time(500,[])
        heater=self.add(build_pokemon(self.r,'피카츄',5,moves=[],abilities=[],extra={'capabilities':['알 부화기']}))
        CAP.heat_egg(self.e,heater,row['entity_id'],source=CAP.EGG_WARMER,fixed_d10=2)
        self.assertIsNone(E.hatch_remaining(self.e,row));self.remove(row);self.restore()
        row=P.egg_index(self.e)[row['entity_id']][1]
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'readiness'):self.hatch(row,ready=None)
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(INC.extra_seconds(self.e,row),500)
        self.assertEqual(CAP.egg_heat_seconds(self.e,row),7200)
        self.assertEqual(self.hatch(row,ready=True)['pokemon'].spec['egg_entity_id'],row['entity_id'])
    def test_real_warmer_contribution_adds_once_to_two_times_real_inside_elapsed(self):
        row=self.egg(7400);self.store(row)
        heater=self.add(build_pokemon(self.r,'피카츄',5,moves=[],abilities=[],extra={'capabilities':['알 부화기']}))
        CAP.heat_egg(self.e,heater,row['entity_id'],source=CAP.EGG_WARMER,fixed_d10=2)
        self.e.advance_time(99,[]);self.assertEqual(E.hatch_remaining(self.e,row),2)
        self.e.advance_time(1,[]);self.hatch(row,ready=None)
        self.assertEqual(INC.extra_seconds(self.e,row),100)
        self.assertEqual(CAP.egg_heat_seconds(self.e,row),7200)
    def test_actual_body_destruction_releases_protection_at_physical_location_and_stops_acceleration(self):
        row=self.egg(10000);self.store(row);self.e.advance_time(20,[])
        def destroy(e,a):
            W.finish_physical_use(e,e._physical_objects['box'],'destroyed',{'source':'gm/actual-break','by_actor_id':a.entity_id,'at':e.elapsed_seconds})
        G.transition(self.e,self.a,destroy)
        self.assertIsNone(P.egg_projection(self.e,row['entity_id'])['protected_by'])
        self.assertEqual(W.effective_location(self.e,row)['cell'],(1,1))
        self.e.advance_time(30,[])
        self.assertEqual(INC.extra_seconds(self.e,row),20)
        self.assertEqual(E.hatch_remaining(self.e,row),9930)
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[8,8]},reason='owner walked away from released egg')
        receiver=self.add(build_trainer(self.r,'recipient',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'edges':[]}))
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'physically'):self.e.gm.transfer_egg(self.a,receiver,row['entity_id'],reason='cannot move remote released egg',request_id='bad')
        self.assertEqual(dump_engine(self.e),before)
        self.restore();self.assertTrue(self.e.validate_state()['valid'])
    def test_new_interval_and_removal_late_failures_are_atomic_and_native_birth_failure_keeps_slot(self):
        row=self.egg(4)
        W.register_object(self.e,'unobserved-box',kind='item_instance',item_rule_id=INC.ITEM,
            location={'kind':'grid','cell':[1,1]},reason='actual empty chamber not yet observed')
        actual_rec=type(self.e.gm)._rec
        cases=(
            ('empty',lambda:None,lambda:INC.observe_empty(self.e,self.a,'unobserved-box',reason='actual empty observation')),
            ('store',lambda:None,lambda:self.store(row)),
            ('remove',lambda:self.store(row),lambda:self.remove(row)),
            ('released location',lambda:self.remove(row),lambda:INC.observe_released_location(self.e,self.a,row['entity_id'],{'kind':'grid','cell':[2,1]},reason='actual released egg observation')))
        for label,prepare,operation in cases:
            with self.subTest(boundary=label):
                prepare();before=dump_engine(self.e)
                ruling_alias=self.e.rulings.log;log_alias=self.e.log_lines;spec_alias=self.a.spec
                body_alias=self.e._physical_objects['box'];empty_alias=self.e._physical_objects['unobserved-box']
                history_alias=row.get(INC.HISTORY)
                rulings=deepcopy(ruling_alias);logs=deepcopy(log_alias);recorded=[]
                def record_then_fail(gm,*args,**kwargs):
                    actual_rec(gm,*args,**kwargs)
                    recorded.append((len(gm.e.rulings.log),len(gm.e.log_lines)))
                    raise ValueError('late actual container GM record')
                with patch.object(type(self.e.gm),'_rec',autospec=True,side_effect=record_then_fail):
                    with self.assertRaisesRegex(ValueError,'late actual container'):operation()
                self.assertEqual(recorded,[(len(rulings)+1,len(logs)+1)])
                self.assertEqual(dump_engine(self.e),before)
                self.assertEqual(self.e.rulings.log,rulings);self.assertEqual(self.e.log_lines,logs)
                self.assertIs(self.e.rulings.log,ruling_alias);self.assertIs(self.e.log_lines,log_alias)
                self.assertIs(self.a.spec,spec_alias);self.assertIs(P.egg_index(self.e)[row['entity_id']][1],row)
                self.assertIs(self.e._physical_objects['box'],body_alias)
                self.assertIs(self.e._physical_objects['unobserved-box'],empty_alias)
                self.assertIs(row.get(INC.HISTORY),history_alias)
        self.store(row);self.e.advance_time(2,[]);before=dump_engine(self.e)
        with patch.object(PARTY,'finish_hatch',side_effect=ValueError('late native birth')):
            with self.assertRaisesRegex(ValueError,'late native birth'):self.hatch(row,ready=None)
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(INC.describe(self.e,'box')['egg_ids'],[row['entity_id']])
        self.hatch(row,ready=None)
    def test_changed_history_missing_body_and_capacity_are_rejected_by_actual_world_restore(self):
        row=self.egg();self.store(row);identity=row['entity_id']
        def incubation_state():
            current=P.egg_index(self.e)[identity][1]
            return deepcopy({'egg_fields':{key:current[key] for key in (INC.HISTORY,INC.LOCATION,E.CONTRACT) if key in current},
                'box_state':self.e._physical_objects['box'][INC.KEY],
                'members':INC.describe(self.e,'box')['egg_ids'],
                'hatch_remaining':E.hatch_remaining(self.e,current),
                'incubator_seconds':INC.extra_seconds(self.e,current),
                'physical_location':W.effective_location(self.e,current)})
        saved=incubation_state()
        actual=deepcopy(row[INC.HISTORY])
        row[INC.HISTORY][0]['started_at']=1
        self.assertFalse(self.e.validate_state()['valid']);row[INC.HISTORY]=actual
        state=deepcopy(self.e._physical_objects['box'][INC.KEY])
        self.e._physical_objects['box'][INC.KEY]['capacity']=5
        self.assertFalse(self.e.validate_state()['valid']);self.e._physical_objects['box'][INC.KEY]=state
        missing=self.e._physical_objects.pop('box')
        self.assertFalse(self.e.validate_state()['valid']);self.e._physical_objects['box']=missing
        self.restore();self.assertTrue(self.e.validate_state()['valid'])
        self.assertEqual(incubation_state(),saved)
    def test_unknown_body_release_location_stays_unknown_until_explicit_real_egg_observation(self):
        row=self.egg();self.store(row)
        W.observe_location(self.e,self.e._physical_objects['box'],{'kind':'unknown'},reason='actual box location currently unobserved')
        G.transition(self.e,self.a,lambda e,a:W.finish_physical_use(e,e._physical_objects['box'],'destroyed',{'source':'gm/observed-break','by_actor_id':a.entity_id}))
        self.assertEqual(W.effective_location(self.e,row),{'kind':'unknown'})
        self.box('replacement');before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'physically'):self.store(row,'replacement')
        self.assertEqual(dump_engine(self.e),before)
        INC.observe_released_location(self.e,self.a,row['entity_id'],{'kind':'grid','cell':[1,1]},reason='GM observed the same intact egg beside the broken box')
        self.store(row,'replacement')
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'contained'):INC.observe_released_location(self.e,self.a,row['entity_id'],{'kind':'grid','cell':[4,4]},reason='cannot move contained egg independently')
        self.assertEqual(dump_engine(self.e),before)
        self.assertTrue(self.e.validate_state()['valid'])
    def test_actual_identity_empty_observation_source_and_remote_hold_are_required_before_storage(self):
        row=self.egg();before=dump_engine(self.e)
        with self.assertRaises(ValueError):INC.store(self.e,deepcopy(self.a),'box',row['entity_id'],reason='forged actor')
        with self.assertRaises(ValueError):INC.store(self.e,self.a,'box','unregistered-egg',reason='fake egg id')
        with self.assertRaises(ValueError):INC.observe_empty(self.e,self.a,'box',reason='cannot reset known history')
        self.assertEqual(dump_engine(self.e),before)
        original=self.r._selected_rule
        with patch.object(self.r,'_selected_rule',side_effect=lambda uid: 'item/부화기-1' if uid==INC.ITEM else original(uid)):
            with self.assertRaisesRegex(ValueError,'selected'):self.store(row)
        self.assertEqual(dump_engine(self.e),before)
        box=self.e._physical_objects['box'];box['telekinetic_holder_id']=self.a.entity_id
        with self.assertRaisesRegex(ValueError,'remote-held'):self.store(row)
        box.pop('telekinetic_holder_id');self.assertEqual(dump_engine(self.e),before)


class PhysicalFossilIncubatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    add=fossils.FossilTests.add
    policy=fossils.FossilTests.policy
    restore=fossils.FossilTests.restore
    details=fossils.FossilTests.details
    hatch=fossils.FossilTests.hatch
    def test_native_restored_fossil_egg_hatches_at_double_speed_and_retains_original_lineage(self):
        fossils.FossilTests.setUp(self)
        W.observe_location(self.e,self.a,{'kind':'grid','cell':[1,1]},reason='actual fossil caretaker')
        W.register_object(self.e,'box',kind='item_instance',item_rule_id=INC.ITEM,location={'kind':'grid','cell':[1,1]},reason='actual physical incubator')
        INC.observe_empty(self.e,self.a,'box',reason='empty actual egg chamber')
        policy=self.policy();policy['hatch']['seconds']=100
        row=self.restore(policy)['egg'];actual=P.egg_index(self.e)[row['entity_id']][1]
        self.assertNotIn(E.CONTRACT,actual)
        INC.store(self.e,self.a,'box',row['entity_id'],reason='actual restored fossil egg placed')
        self.e.advance_time(49,[])
        with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(row,ready=None)
        self.e.advance_time(1,[]);child=self.hatch(row,ready=None)['pokemon']
        self.assertEqual(child.spec['fossil_entity_id'],self.fossil['entity_id'])
        self.assertEqual(child.spec['egg_entity_id'],row['entity_id'])
        self.assertEqual(INC.describe(self.e,'box')['egg_ids'],[])
        self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
