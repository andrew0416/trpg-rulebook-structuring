"""C10-021: real d10 warmth consumed by native egg and fossil births."""
from pathlib import Path
from copy import deepcopy
from random import Random
from unittest.mock import patch
import json,unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'output').is_dir():ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
from engine import Rules,Combatant,Engine
from builder import build_pokemon,build_trainer
from state_codec import dump_engine,load_engine
import test_foundation_egg_creation as eggs
import test_foundation_fossil_creation as fossils
import csv_item_capability_contracts as CAP,creation_egg as CREATION
import state_grants as G,world_entities as W,pokemon_entities as P,downtime as D


class CoreEggWarmerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    add=eggs.EggTests.add
    policy=eggs.EggTests.policy
    choices=eggs.EggTests.choices
    create=eggs.EggTests.create
    hatch=eggs.EggTests.hatch
    def setUp(self):
        eggs.EggTests.setUp(self)
        self.p=self.add(build_pokemon(self.r,'피카츄',5,moves=[],abilities=[],
            extra={'trainer_id':self.a.entity_id,'capabilities':['알 부화기','알부화기']}))
    def egg(self,seconds,request_id='egg'):
        policy=self.policy();policy['work_seconds']=0;policy['hatch']['seconds']=seconds
        row=self.create(policy,request_id=request_id)
        return P.egg_index(self.e)[row['entity_id']][1]
    def warm(self,egg,face=None,actor=None):
        return CAP.heat_egg(self.e,self.p if actor is None else actor,egg['entity_id'],source=CAP.EGG_WARMER,fixed_d10=face)
    def test_one_rolling_24h_shared_variant_clock_and_exact_two_hour_native_birth(self):
        row=self.egg(90000);other=self.egg(90000,'other');original=deepcopy(row[CREATION.CONTRACT])
        self.assertEqual(self.warm(row,1)['seconds'],0)
        D.new_day(self.p);self.e.advance_time(86399,[])
        saved=json.loads(json.dumps(dump_engine(self.e)))
        self.e=load_engine(self.r,saved);index=W.actor_index(self.e)
        self.a,self.p=index[self.a.entity_id],index[self.p.entity_id]
        row=P.egg_index(self.e)[row['entity_id']][1];before=dump_engine(self.e)
        for source,fixed in ((CAP.EGG_WARMER,{'fixed_d10':2}),(CAP.EGG_HATCHER,{'fixed_d2':2})):
            with self.assertRaisesRegex(ValueError,'24-hour'):CAP.heat_egg(self.e,self.p,row['entity_id'],source=source,**fixed)
            self.assertEqual(dump_engine(self.e),before)
        self.e.advance_time(1,[])
        with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(row,ready=None)
        receipt=self.warm(row,2);self.assertEqual(receipt['seconds'],7200)
        child=self.hatch(row,ready=None)['pokemon']
        self.assertEqual(child.spec['egg_entity_id'],row['entity_id'])
        self.assertEqual(row[CREATION.CONTRACT],original)
        self.assertEqual(row['produced_at'],0)
        with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(other,ready=None)
        self.assertEqual(P.egg_index(self.e)[other['entity_id']][1].get(CAP.HEAT),None)
        self.assertTrue(self.e.validate_state()['valid'])
    def test_real_d10_and_ten_hour_boundary_are_consumed_by_actual_hatch(self):
        row=self.egg(36000);original=self.e.rng.getstate();expected=Random();expected.setstate(original)
        expected_face=expected.randint(1,10)
        with patch.object(CAP.POOLS,'die',wraps=CAP.POOLS.die) as die:
            receipt=self.warm(row)
        die.assert_called_once();self.assertEqual(die.call_args.args[1],10)
        self.assertEqual(die.call_args.kwargs,{'fixed':None})
        self.assertEqual(receipt['d10'],expected_face)
        self.assertEqual(self.e.rng.getstate(),expected.getstate())
        second=self.add(build_pokemon(self.r,'피카츄',5,moves=[],abilities=[],extra={'capabilities':[CAP.EGG_WARMER]}))
        target=self.egg(36001,'ten-hour-boundary');self.warm(target,10,actor=second)
        with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(target,ready=None)
        self.e.advance_time(1,[])
        self.assertEqual(self.hatch(target,ready=None)['pokemon'].spec['egg_entity_id'],target['entity_id'])
        self.assertTrue(self.e.validate_state()['valid'])
    def test_unknown_timing_preserves_warmth_after_capability_loss_transfer_and_restore(self):
        row=self.egg(None);original=deepcopy(row[CREATION.CONTRACT]);self.warm(row,10)
        self.assertIsNone(CREATION.hatch_remaining(self.e,row))
        self.assertNotIn('hatch_remaining_seconds',row)
        self.p.spec['capabilities']=[]
        self.p.spec[CAP.STATE]['receipts']=[]
        receiver=self.add(build_trainer(self.r,'actual recipient',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'edges':[]}))
        self.e.gm.transfer_egg(self.a,receiver,row['entity_id'],reason='actual warmed egg gift',request_id='gift')
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))));index=W.actor_index(self.e)
        self.a=index[receiver.entity_id];self.p=index[self.p.entity_id];row=P.egg_index(self.e)[row['entity_id']][1]
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'readiness'):self.hatch(row,ready=None)
        self.assertEqual(dump_engine(self.e),before)
        child=self.hatch(row,ready=True)['pokemon']
        self.assertEqual(child.spec['egg_entity_id'],row['entity_id']);self.assertEqual(row[CREATION.CONTRACT],original)
        self.assertEqual(CAP.egg_heat_seconds(self.e,row),36000)
        self.assertEqual(child.spec['move_learning']['move/뿌리박기']['teacher_id'],original['plan']['provider_id'])
    def test_source_live_capability_actual_pokemon_and_die_inputs_before_use(self):
        row=self.egg(7200)
        for fixed in (True,False,0,11,2.0):
            before=dump_engine(self.e)
            with self.assertRaises(ValueError):self.warm(row,fixed)
            self.assertEqual(dump_engine(self.e),before)
        for actor in (self.a,deepcopy(self.p)):
            before=dump_engine(self.e)
            with self.assertRaises(ValueError):self.warm(row,2,actor=actor)
            self.assertEqual(dump_engine(self.e),before)
        self.p.spec['capabilities']=['알부화기'];before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'actual capability'):self.warm(row,2)
        self.assertEqual(dump_engine(self.e),before)
        G.grant(self.p,'capabilities','알 부화기','test/live-warmer','capability')
        self.warm(row,2);G.revoke(self.p,'test/live-warmer',engine=self.e)
        self.hatch(row,ready=None)
    def test_homebrew_stays_d2_one_day_and_uses_same_native_hatch_consumer(self):
        row=self.egg(86400);receipt=CAP.heat_egg(self.e,self.p,row['entity_id'],fixed_d2=2)
        self.assertEqual((receipt['d2'],receipt['seconds'],receipt['reduced_seconds']),(2,86400,86400))
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'24-hour'):self.warm(row,10)
        self.assertEqual(dump_engine(self.e),before)
        self.assertEqual(self.hatch(row,ready=None)['pokemon'].spec['egg_entity_id'],row['entity_id'])


class CoreFossilWarmerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    add=fossils.FossilTests.add
    policy=fossils.FossilTests.policy
    restore=fossils.FossilTests.restore
    details=fossils.FossilTests.details
    hatch=fossils.FossilTests.hatch
    def test_fossil_egg_validates_warmth_before_contract_return_and_hatches_same_origin(self):
        fossils.FossilTests.setUp(self)
        policy=self.policy();policy['hatch']['seconds']=7200
        row=self.restore(policy)['egg'];actual=P.egg_index(self.e)[row['entity_id']][1]
        self.assertNotIn(CREATION.CONTRACT,actual)
        heater=self.add(build_pokemon(self.r,'피카츄',5,moves=[],abilities=[],extra={'capabilities':['알 부화기']}))
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(row,ready=None)
        self.assertEqual(dump_engine(self.e),before)
        CAP.heat_egg(self.e,heater,row['entity_id'],source=CAP.EGG_WARMER,fixed_d10=2)
        original=deepcopy(actual[CAP.HEAT][0]);actual[CAP.HEAT][0]['seconds']+=3600
        self.assertFalse(self.e.validate_state()['valid']);actual[CAP.HEAT][0]=original
        heater.spec['capabilities']=[]
        child=self.hatch(row,ready=None)['pokemon']
        self.assertEqual(child.spec['fossil_entity_id'],self.fossil['entity_id'])
        self.assertEqual(child.spec['egg_entity_id'],row['entity_id'])
        self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
