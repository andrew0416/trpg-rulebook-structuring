"""CSV equipment transfer native producer; direct handlers are insufficient evidence."""
from pathlib import Path
from copy import deepcopy
import sys,unittest,json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from builder import build_trainer
import items as I,world_entities as W,state_grants as G,capability_actions as CAP

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def fixture(self,name='바꿔치기',held=('선제공격손톱','예리한손톱'),seed=0,weight=False):
  e=Engine(self.r,seed);mid=self.r.move_id(name)
  actors=[]
  for index,item in enumerate(held):
   actor=Combatant(self.r,build_trainer(self.r,'actor-'+str(index),10,dict(hp=10,atk=10,**{'def':10},spa=10,spd=10,spe=10),abilities=[],moves=[mid],pos=(index,0)))
   actors.append(actor)
  e.everyone=e.gm.everyone=actors
  for index,(actor,item) in enumerate(zip(actors,held)):
   if item is None:continue
   actor.item=item;actor.spec['item']=item;uid='physical/'+str(index)
   W.register_object(e,uid,location={'kind':'unknown'},reason='observed real equipment instance',kind='item_instance',item_rule_id='item/'+item,owner_id=actor.entity_id,**({'weight_kg':1} if weight else {}))
   if weight:
    actor.spec['movement']['power']=4;actor.spec['power_basis']='current'
    CAP.set_carried(e,actor,[{'id':uid,'weight_kg':1}],'actual measured carried equipment')
   I.register_item(e,actor,item,source_instance_id=uid,as_held=True)
  if weight:
   for actor in actors:actor.spec['movement']['power']=4;actor.spec['power_basis']='current'
  return e,*actors,mid
 def execute(self,e,a,b,mid):
  # Actual seeded RNG and complete engine method; no Engine-bound Mock.
  out=e.use_move(a,b,mid)
  self.assertTrue(e._effect_dispatch_receipts)
  for token,row in e._effect_dispatch_receipts.items():
   self.assertIs(row['receipt'],token);self.assertEqual(row['status'],'completed')
  self.assertTrue(e.validate_state()['valid'],e.validate_state()['issues'])
  return out
 def test_native_switcheroo_swaps_effects_instances_and_preserves_live_aliases(self):
  for held in (('선제공격손톱','예리한손톱'),('선제공격손톱','선제공격손톱'),('선제공격손톱',None),(None,'예리한손톱')):
   with self.subTest(held=held):
    e,a,b,mid=self.fixture(held=held);objects=dict(e._physical_objects);specs=(a.spec,b.spec);registries=(getattr(a,'_item_reg',None),getattr(b,'_item_reg',None))
    expected=(b.initiative_bonus,a.initiative_bonus)
    self.execute(e,a,b,mid)
    self.assertEqual((a.item,b.item),held[::-1]);self.assertEqual((a.initiative_bonus,b.initiative_bonus),expected)
    self.assertIs(a.spec,specs[0]);self.assertIs(b.spec,specs[1])
    for index,obj in enumerate(objects.values()):
     uid=next(k for k,v in objects.items() if v is obj);old_index=int(uid.rsplit('/',1)[1]);receiver=(b,a)[old_index]
     self.assertIs(e._physical_objects[uid],obj);self.assertEqual(obj['equipped_by'],receiver.entity_id)
     self.assertEqual(obj['owner_id'],(a,b)[old_index].entity_id)
     self.assertEqual(receiver._item_reg[receiver.item]['instance_id'],uid)
     self.assertEqual(receiver._item_reg[receiver.item]['state_source'],'equipment:'+uid)
    for actor,reg in zip((a,b),registries):
     if reg is not None:self.assertIs(actor._item_reg,reg)
 def test_native_switcheroo_transfers_known_carry_weight_without_changing_legal_owner(self):
  e,a,b,mid=self.fixture(weight=True);self.execute(e,a,b,mid)
  for actor,uid in ((a,'physical/1'),(b,'physical/0')):
   self.assertEqual(actor.spec['_carried_load']['objects'],[{'id':uid,'weight_kg':1}])
   self.assertEqual(e._physical_objects[uid]['carrier_id'],actor.entity_id)
   self.assertEqual(e._physical_objects[uid]['equipped_by'],actor.entity_id)
  self.assertEqual(e._physical_objects['physical/0']['owner_id'],a.entity_id)
 def test_miss_and_no_equipment_never_invent_transfer_or_physical_instances(self):
  e,a,b,mid=self.fixture(seed=2);before=deepcopy((a.item,b.item,e._physical_objects,a.initiative_bonus,b.initiative_bonus))
  e.use_move(a,b,mid)
  self.assertEqual((a.item,b.item,e._physical_objects,a.initiative_bonus,b.initiative_bonus),before)
  self.assertFalse(getattr(e,'_effect_dispatch_receipts',{}))
  e,a,b,mid=self.fixture(held=(None,None));self.execute(e,a,b,mid)
  self.assertEqual((a.item,b.item),(None,None));self.assertFalse(getattr(e,'_physical_objects',{}))
 def test_actual_completed_dispatch_survives_gm_restore_and_codec_then_next_native_swap(self):
  e,a,b,mid=self.fixture();self.execute(e,a,b,mid);first=deepcopy((a.item,b.item,a.initiative_bonus,b.initiative_bonus))
  e.gm.snapshot('after-native-swap')
  e.end_encounter();e.use_move(a,b,mid)
  e.gm.restore('after-native-swap',reason='restore actual completed transfer')
  self.assertEqual((a.item,b.item,a.initiative_bonus,b.initiative_bonus),first)
  loaded=Engine.import_state(self.r,json.loads(json.dumps(e.export_state())))
  index=W.actor_index(loaded);aa=index[a.entity_id];bb=index[b.entity_id]
  self.assertEqual((aa.item,bb.item,aa.initiative_bonus,bb.initiative_bonus),first)
  self.assertIs(aa,loaded.gm.everyone[0])
  for token,row in loaded._effect_dispatch_receipts.items():self.assertIs(row['receipt'],token);self.assertEqual(row['status'],'completed')
  loaded.rng.seed(0);self.execute(loaded,aa,bb,mid)
  self.assertEqual((aa.item,bb.item),('선제공격손톱','예리한손톱'))
 def test_damaging_move_live_receipt_keys_complete_and_arbitrary_objects_are_not_shared(self):
  for name in ('탁쳐서떨구기','도둑질','쪼아대기','탐내기'):
   with self.subTest(move=name):
    e,a,b,mid=self.fixture(name,held=(None,'선제공격손톱'));self.execute(e,a,b,mid)
    self.assertLess(b.hp,b.base_max_hp)
    self.assertIsNone(b.item)
    if name!='탁쳐서떨구기':self.assertEqual(a.item,'선제공격손톱')
    else:self.assertIsNone(a.item);self.assertNotIn('equipped_by',e._physical_objects['physical/1']);self.assertEqual(e._physical_objects['physical/1']['location'],{'kind':'grid','cell':b.pos})
  e,a,b,mid=self.fixture();opaque=object();a.custom_conditions['untrusted_opaque_fixture']=opaque
  G.transition(e,a,lambda staged,actor:actor.spec.update(test_marker=True))
  self.assertIsNot(a.custom_conditions['untrusted_opaque_fixture'],opaque)
  # Such arbitrary runtime objects remain unsupported by the durable codec.
  with self.assertRaises(ValueError):e.export_state()

if __name__=='__main__':unittest.main(verbosity=2)
