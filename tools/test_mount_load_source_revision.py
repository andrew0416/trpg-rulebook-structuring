"""Native Mountable average loads, actual GM significance and changed-world scope."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_control_mount as _fixture
from builder import build_pokemon,build_trainer
from state_codec import load_engine
from native_scenario_fixture import assert_rejected_unchanged
import control_mount as M,capability_actions as LOAD,world_entities as W,roll_context as R


class MountLoadSourceRevisionTests(unittest.TestCase):
 setUpClass=classmethod(_fixture.MountTests.setUpClass.__func__)
 add=_fixture.MountTests.add
 pokemon=_fixture.MountTests.pokemon
 begin=_fixture.MountTests.begin
 policy=_fixture.MountTests.policy
 snap=_fixture.MountTests.snap

 def world(self,weights=(60,60),*,board=True):
  _fixture.MountTests.setUp(self);self.p.pos=(0,8)
  self.p=self.add(build_pokemon(self.r,'날쌩마',5,extra={'trainer_id':self.a.entity_id}));self.p.pos=(2,3)
  self.e.gm.observe_loyalty(self.p,6,reason='actual Rapidash mount obedience')
  self.a.spec['edges'].append('edge/탑승-기량')
  self.e.gm.observe_trainer_weight(self.a,weights[0],unit='kg',reason='actual first trainer mass')
  self.riders=[self.a];self.value=self.policy(1)
  for index,weight in enumerate(weights[1:],1):
   rider=self.add(build_trainer(self.r,'actual rider '+str(index),20,
      dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'곡예':3},
      extra={'edges':['edge/탑승-기량'],'weight_kg':weight}))
   rider.pos=(1,3+index);self.riders.append(rider)
  if board:
   for rider in self.riders:self.assertTrue(self.e.board_mount(rider,self.p,self.value,gm_mountable=True)['passed'])
  self.assertIn('탑승 2',self.p.spec['capabilities'])

 def choice(self,significant,*,objects=None,riders=None,reason='GM judges this exact extra weight in its actual context'):
  return {'significant':significant,'reason':reason,
      'scope':M.mountable_load_scope(self.p,objects=objects,riders=riders,
          policy=self.value if riders is not None else None)}

 def cargo(self,objects,significant):
  choice=self.choice(significant,objects=objects)
  result=self.e.gm.set_carried_objects(self.p,objects,choice['reason'],mountable_load=choice)
  return choice,result

 def test_native_71_and_60_kg_trainers_share_observed_average_allowance_without_a_judgment(self):
  self.world((60,71))
  self.assertLess(LOAD.limits(self.p)['staggering'],131)
  self.assertEqual(LOAD.load(self.p),{'band':'normal','weight_kg':0,'penalty':0})
  self.assertNotIn('mountable_load',self.p.spec.get('_carried_load',{}))
  self.assertEqual([c.spec['weight_kg'] for c in self.riders],[60,71])
  self.begin(self.a);self.t.pos=(6,3);out=self.e.approach(self.a,self.t)
  self.assertGreater(out['distance'],0)
  self.assertTrue(all(c.pos==self.p.pos for c in self.riders))
  loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)))
  index=W.actor_index(loaded);mount=index[self.p.entity_id]
  self.assertEqual(LOAD.load(mount),{'band':'normal','weight_kg':0,'penalty':0})
  self.assertEqual([c.entity_id for c in getattr(mount,M.RIDERS)],[c.entity_id for c in self.riders])
  self.assertEqual(getattr(mount,M.POOL)['used'],getattr(self.p,M.POOL)['used'])

 def test_insignificant_cargo_keeps_rider_exemption_but_significant_cargo_uses_actual_power(self):
  self.world();objects=[{'id':'object/mount-small-bag','weight_kg':1}]
  assert_rejected_unchanged(self.e,lambda:self.e.gm.set_carried_objects(self.p,objects,'unjudged actual bag'),reason_pattern='significance judgment')
  choice,current=self.cargo(objects,False)
  self.assertEqual(current,{'band':'normal','weight_kg':1,'penalty':0})
  self.assertEqual(self.e._physical_objects[objects[0]['id']]['carrier_id'],self.p.entity_id)
  self.assertEqual(self.p.spec['_carried_load']['mountable_load'],choice)
  significant=self.choice(True)
  assert_rejected_unchanged(self.e,lambda:self.e.gm.set_carried_objects(self.p,objects,significant['reason'],mountable_load=significant),reason_pattern='Power limit')
  huge=[{'id':'object/mount-huge-cargo','weight_kg':1000}];insignificant=self.choice(False,objects=huge)
  assert_rejected_unchanged(self.e,lambda:self.e.gm.set_carried_objects(self.p,huge,insignificant['reason'],mountable_load=insignificant),reason_pattern='Power limit')
  self.world((60,));choice,current=self.cargo(objects,True)
  self.assertEqual((current['weight_kg'],current['band']),(61,'staggering'))
  self.assertEqual(current['penalty'],LOAD.policy(self.p)['staggering']['speed_stages'])
  self.assertEqual(LOAD.movement_limit(self.p,10),1)
  self.assertFalse(LOAD.action_permission(self.e,self.p,'standard'))
  self.assertIs(getattr(self.p,M.RIDERS)[0],self.a)

 def test_excess_rider_boarding_requires_scoped_choice_and_rejects_bad_or_unrelated_choices_before_payment(self):
  self.world((71,),board=False)
  assert_rejected_unchanged(self.e,lambda:self.e.board_mount(self.a,self.p,self.value,gm_mountable=True),reason_pattern='significance judgment')
  choice=self.choice(False,riders=self.riders)
  wrong=deepcopy(choice);wrong['scope']['riders'][0]['weight_kg']=70
  assert_rejected_unchanged(self.e,lambda:self.e.board_mount(self.a,self.p,self.value,gm_mountable=True,mountable_load=wrong),reason_pattern='scope changed')
  wrong=deepcopy(choice);wrong['significant']='false'
  assert_rejected_unchanged(self.e,lambda:self.e.board_mount(self.a,self.p,self.value,gm_mountable=True,mountable_load=wrong),reason_pattern='explicit Mountable')
  self.assertTrue(self.e.board_mount(self.a,self.p,self.value,gm_mountable=True,mountable_load=choice)['passed'])
  self.assertEqual(LOAD.load(self.p)['weight_kg'],0)
  self.assertEqual(self.p.spec['_carried_load']['mountable_load'],choice)
  self.world((60,),board=False);contradictory=self.choice(False,riders=self.riders)
  assert_rejected_unchanged(self.e,lambda:self.e.board_mount(self.a,self.p,self.value,gm_mountable=True,mountable_load=contradictory),reason_pattern='additional actual weight')
  unrelated=self.policy(0)
  assert_rejected_unchanged(self.e,lambda:self.e.board_mount(self.a,self.p,unrelated,gm_mountable=True,mountable_load=contradictory),reason_pattern='actual Mountable exception')

 def test_changed_actual_body_and_source_cannot_reuse_past_significance_after_restore(self):
  self.world((71,),board=False);choice=self.choice(False,riders=self.riders)
  self.e.board_mount(self.a,self.p,self.value,gm_mountable=True,mountable_load=choice)
  saved=self.e.gm.snapshot();encoded=self.snap()
  loaded=load_engine(self.r,json.loads(json.dumps(encoded,ensure_ascii=False)))
  mount=W.actor_index(loaded)[self.p.entity_id]
  self.assertEqual(mount.spec['_carried_load']['mountable_load'],choice);self.assertEqual(LOAD.load(mount)['weight_kg'],0)
  self.e.gm.observe_trainer_weight(self.a,72,unit='kg',reason='actual body mass changed after admission')
  self.assertEqual(self.p.spec['_carried_load']['mountable_load'],choice)
  with self.assertRaisesRegex(ValueError,'scope changed'):LOAD.load(self.p)
  assert_rejected_unchanged(self.e,lambda:self.e.gm.set_carried_objects(self.p,[],choice['reason'],mountable_load=choice),reason_pattern='scope changed')
  refreshed=self.choice(False)
  self.e.gm.set_carried_objects(self.p,[],refreshed['reason'],mountable_load=refreshed)
  self.assertEqual(LOAD.load(self.p)['weight_kg'],0)
  self.e.gm.set_footprint(self.p,[(0,0),(0,1),(0,2)],reason='actual changed mount body footprint')
  with self.assertRaisesRegex(ValueError,'scope changed'):LOAD.load(self.p)
  refreshed=self.choice(False)
  self.e.gm.set_carried_objects(self.p,[],refreshed['reason'],mountable_load=refreshed)
  original=Path.read_bytes;source=Path(refreshed['scope']['source']['source']['file']).name
  def changed(path):
   raw=original(path)
   return raw+b'\nchanged Mountable source\n' if path.name==source else raw
  before=self.snap()
  with patch.object(Path,'read_bytes',changed):
   with self.assertRaisesRegex(ValueError,'source changed'):LOAD.load(self.p)
  self.assertEqual(self.snap(),before)
  self.e.gm.restore(saved)
  self.assertEqual(self.p.spec['_carried_load']['mountable_load'],choice)
  self.assertEqual(LOAD.load(self.p)['weight_kg'],0)

 def test_dismount_and_failed_retention_persist_while_changed_remaining_load_waits_for_its_own_judgment(self):
  for failure in (False,True):
   with self.subTest(failed_retention=failure):
    self.world();objects=[{'id':'object/mount-retained-bag','weight_kg':1}]
    choice,_=self.cargo(objects,False);other=self.riders[1];self.begin(self.a)
    if failure:
     count=R.plan(self.e,other,'곡예',purpose='mount retention:manual',target=self.p)['dice_count']
     out=self.e.retain_mount(other,event='manual',roll_options={'fixed':[1]*count})
     self.assertFalse(out['passed']);self.assertEqual(other.custom_conditions['mount_retention_history'][-1]['event'],'manual')
    else:self.e.dismount(other,reason='actual second trainer dismounted')
    self.assertNotIn('mount_id',other.spec);self.assertIs(getattr(self.p,M.RIDERS)[0],self.a)
    self.assertEqual(self.p.spec['_carried_load']['mountable_load'],choice)
    self.assertTrue(self.e.validate_state()['valid'])
    with self.assertRaisesRegex(ValueError,'scope changed'):LOAD.load(self.p)
    assert_rejected_unchanged(self.e,lambda:self.e.approach(self.a,self.t),reason_pattern='scope changed')
    refreshed=self.choice(False)
    self.e.gm.set_carried_objects(self.p,objects,refreshed['reason'],mountable_load=refreshed)
    self.assertEqual(LOAD.load(self.p)['weight_kg'],1)
    self.t.pos=(6,3);out=self.e.approach(self.a,self.t);self.assertGreater(out['distance'],0)
    self.e.gm.set_carried_objects(self.p,[],'actual bag released after mounted travel')
    self.assertEqual(LOAD.load(self.p)['weight_kg'],0)
    self.assertEqual(self.p.spec['_carried_load']['mountable_load'],refreshed)


if __name__=='__main__':unittest.main()
