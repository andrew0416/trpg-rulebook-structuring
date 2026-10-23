"""Real grouped transport and fitted saddle consumers, with common owners reused."""
from pathlib import Path
from copy import copy,deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_control_mount as fixture
from engine import Engine
from state_codec import dump_engine,load_engine
from ruleset import RuleFilter,RuleSelection
import equipped_transport_saddle as E,control_mount as M,control_vehicle as V
import world_entities as W,capability_actions as LOAD,items as ITEMS,roll_context as R
import common_checks as C,turn as TURN,source_context


class EquipmentTransportSaddleTests(unittest.TestCase):
 setUpClass=classmethod(fixture.MountTests.setUpClass.__func__)
 add=fixture.MountTests.add
 pokemon=fixture.MountTests.pokemon
 begin=fixture.MountTests.begin
 policy=fixture.MountTests.policy
 auto=fixture.MountTests.auto
 def setUp(self):fixture.MountTests.setUp(self)
 def snap(self):return dump_engine(self.e)
 def ruling_snapshot(self):
  actors=self.e.gm._snapshot_actors(self.e.rulings.log)
  return deepcopy(self.e.rulings.log,{**actors,id(self.e):self.e,id(self.r):self.r})
 def saddle(self,*,mount=None,compatible=True,fit=True,uid='saddle/actual'):
  mount=mount or self.p
  W.register_object(self.e,uid,kind='item_instance',item_rule_id=E.SADDLE,owner_id=mount.entity_id,
    location={'kind':'unknown'},reason='actual saddle',weight_kg=1)
  ITEMS.register_item(self.e,mount,E.SADDLE,source_instance_id=uid)
  if fit:self.e.gm.observe_saddle_fit(mount,uid,compatible=compatible,design_shape='observed saddle tree',observed_shape='observed actual back',reason='individual fit measured')
  return uid
 def boarding(self,*,native=False):
  self.begin(self.a)
  if native:return self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True,fixed=[3]*3)
  return self.e.board_mount(self.a,self.p,self.policy(),gm_mountable=True,roll_options={'fixed':[3]*3})
 def transport_fixture(self,mode='land'):
  self.a.pos=(2,3);self.p.pos=(3,3);self.t.pos=(3,4)
  for c in (self.p,self.t):c.movement=6;c.spec['movement'].update(power=3,swim=6)
  W.register_object(self.e,'transport/body',location={'kind':'grid','cell':(2,3)},reason='actual sled or raft',weight_kg=2)
  W.register_object(self.e,'transport/rope',location={'kind':'grid','cell':(2,3)},reason='actual connecting rope',weight_kg=2)
  value={'id':'observed/equipment-transport','source':E.TRANSPORT,'kinds':['physical_object'],
   'pilot':{'authority':'assigned','requirements':[]},'access':'aboard',
   'body':{'offsets':[[0,0],[1,0],[1,1]],'maximum_occupants':None},
   'movement':{'provider':'declared','mode':mode,'value':6,'maximum':None,'action':'shift','override':None,'check':None},
   'initiative':{'provider':'pilot','value':None,'procedure':None},
   'actions':{'standard':0,'shift':2,'swift':0,'share_with_operator':True},'weapons':[],'concurrent':None}
  self.options={'pokemon':[self.p,self.t],'riders':[self.a],'equipment':['transport/rope'],
   'load_shares':{self.p.entity_id:12,self.t.entity_id:12},'operation':value,'trained':True,'gm_permitted':True,'reason':'actual trained two-Pokemon construction and adopted physical load distribution'}
  return value
 def assemble(self,**changes):
  return self.e.gm.observe_equipment_transport(self.a,'transport/body',**dict(self.options,**changes))
 def move_transport(self,value,*,steps=2,request='actual-transport'):
  origin=W.grid_cell(self.e._physical_objects['transport/body'])
  return self.e.operate_machine(self.a,'transport/body',value,command='move',request_id=request,
   path=[(origin[0]+i,origin[1]) for i in range(steps+1)],body_eligible=True,reason='actual continuous team transport')
 def valid(self,e=None):
  e=e or self.e;result=W.validate_world(e);self.assertTrue(result['valid'],result['issues'])
 def fixed_retention(self):
  original=Engine.skill_roll
  def roll(engine,actor,skill,**options):
   count=R.plan(engine,actor,skill,purpose='actual fixture retention',target=options.get('skill_target'))['dice_count']
   return original(engine,actor,skill,**dict(options,fixed=[3]*count))
  return patch.object(Engine,'skill_roll',new=roll)

 def test_actual_non_mountable_pokemon_gear_body_rider_and_controller_move_together_with_physical_load(self):
  value=self.transport_fixture();self.begin(self.a)
  self.assertFalse(any('탑승' in s or 'Mountable' in s for s in self.p.spec['capabilities']))
  owners=[c.spec.get('trainer_id') for c in (self.p,self.t)];out=self.assemble()
  self.assertEqual(out['physical_mass_kg'],24)
  body=self.e._physical_objects['transport/body'];state=body[E.STATE]
  self.assertIs(state['controller'],self.a);self.assertEqual(state['riders'],[self.a]);self.assertEqual(state['pokemon'],[self.p,self.t])
  self.assertEqual([LOAD.load(c)['weight_kg'] for c in (self.p,self.t)],[12,12])
  self.assertEqual([c.spec.get('trainer_id') for c in (self.p,self.t)],owners)
  moved=self.move_transport(value);self.assertEqual(moved['distance'],2)
  self.assertEqual((W.grid_cell(body),self.a.pos,self.p.pos,self.t.pos),((4,3),(4,3),(5,3),(5,4)))
  self.assertEqual(W.grid_cell(self.e._physical_objects['transport/rope']),(4,3))
  self.assertEqual([getattr(c,M.POOL)['used'] for c in (self.p,self.t)],[2,2]);self.valid()
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'release the existing'):self.assemble()
  self.assertEqual(before,self.snap())

 def test_missing_permission_training_or_actual_observations_is_pending_without_cost(self):
  self.transport_fixture()
  for change in ({'gm_permitted':None},{'gm_permitted':False},{'trained':None},{'trained':False},{'load_shares':None},{'equipment':None},{'operation':None}):
   with self.subTest(change=change):
    before=self.snap();self.assertIsInstance(self.assemble(**change),C.PendingDecision);self.assertEqual(self.snap(),before)
  self.begin(self.p);self.t.pos=(5,5);self.e.approach(self.p,self.t)
  self.assertTrue(self.p._regular_shift_movement_used);self.assertFalse(M.manages(self.e,self.p))
  before=self.snap();self.assertIsInstance(self.assemble(),C.PendingDecision);self.assertEqual(before,self.snap())

 def test_actual_load_footprint_and_distinct_bodies_are_required_before_any_assembly(self):
  value=self.transport_fixture()
  bad=deepcopy(value);bad['body']['offsets']=[[0,0]]
  for change in ({'pokemon':[copy(self.p),self.t]},{'equipment':['missing-rope']},
                 {'load_shares':{self.p.entity_id:1,self.t.entity_id:1}},{'operation':bad},
                 {'pokemon':[self.p,self.p]}):
   with self.subTest(change=change):
    before=self.snap()
    with self.assertRaises(ValueError):self.assemble(**change)
    self.assertEqual(before,self.snap())
  self.p.spec['movement']['power']=1
  with self.assertRaisesRegex(ValueError,'Power limit'):self.assemble()
  self.assertFalse(hasattr(self.p,E.LINK));self.assertNotIn(E.STATE,self.e._physical_objects['transport/body'])

 def test_rider_and_pokemon_turns_and_release_reassembly_preserve_the_same_actual_remainder(self):
  value=self.transport_fixture();self.begin(self.a);self.assemble();self.move_transport(value)
  self.e.end_of_turn(self.a);self.e.start_of_turn(self.p,initiative_count=10)
  remaining=M.shared_movement(self.e,self.p)[2]['remaining'];self.assertEqual(remaining,4)
  self.assertFalse(TURN.movement_permission(self.e,self.p));self.assertFalse(TURN.movement_permission(self.e,self.a))
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'shared machine movement distance exhausted'):self.move_transport(value,steps=5,request='too-far')
  self.assertEqual(before,self.snap())
  self.e.release_equipment_transport(self.a,'transport/body',reason='unhitch current assembly')
  self.assertEqual(LOAD.load(self.p)['weight_kg'],0);self.assertTrue(TURN.movement_permission(self.e,self.p))
  self.assemble();self.assertEqual(M.shared_movement(self.e,self.p)[2]['remaining'],remaining)
  self.assertEqual(V._budget(self.e,'transport/body',value)['distance'],2)
  self.assertEqual(self.p.spec.get('trainer_id'),self.a.entity_id);self.valid()
  # One donor already paid a diagonal on the actual mounted path before assembly.
  self.setUp();value=self.transport_fixture();self.auto()
  self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True)
  self.begin(self.a);self.t.pos=(5,5);prior=self.e.approach(self.a,self.t)
  self.assertEqual((prior['distance'],getattr(self.p,M.POOL)['diagonals']),(1,1))
  self.e.dismount(self.a,destination=(3,4),reason='unhitch actual former mount')
  for uid in ('transport/body','transport/rope'):
   W._set_object_location(self.e._physical_objects[uid],{'kind':'grid','cell':(3,4)})
  value['body']['offsets']=[[0,0],[1,0],[2,1]]
  value['movement']['action']='standard';value['actions'].update(standard=2,shift=0)
  self.assemble()
  out=self.e.operate_machine(self.a,'transport/body',value,command='move',request_id='different-existing-diagonal-phases',
   path=[(3,4),(4,5)],body_eligible=True,reason='actual diagonal with distinct donor phases')
  self.assertEqual(out['distance'],1)
  self.assertEqual([(getattr(c,M.POOL)['used'],getattr(c,M.POOL)['diagonals']) for c in (self.p,self.t)],[(3,2),(1,1)])
  self.assertEqual([c._diagonal_steps for c in (self.p,self.t)],[2,1])
  self.e.release_equipment_transport(self.a,'transport/body',reason='release preserves donor phases');self.assemble()
  self.p.movement=3;before=self.snap()
  with self.assertRaisesRegex(ValueError,'Pokemon shared movement distance exhausted'):
   self.move_transport(value,steps=1,request='exhausted-actual-donor')
  self.assertEqual(before,self.snap());self.valid()

 def test_raft_uses_current_swim_and_load_limits_and_does_not_sum_pokemon_speed(self):
  value=self.transport_fixture('swim');self.begin(self.a);self.assemble()
  self.e.gm.add_condition(self.t,'구속',reason='actual transport donor cannot move');before=self.snap()
  with self.assertRaisesRegex(ValueError,'current movement permission required'):self.move_transport(value,steps=1)
  self.assertEqual(before,self.snap());self.e.gm.remove_condition(self.t,'구속',reason='actual donor released')
  self.t.spec['movement']['swim']=1
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'Pokemon shared movement distance exhausted'):self.move_transport(value,steps=2)
  self.assertEqual(before,self.snap());out=self.move_transport(value,steps=1)
  self.assertEqual(out['distance'],1);self.assertEqual(out['remaining'],0)

 def test_controller_is_separate_from_ownership_and_current_gear_or_formation_loss_requires_release(self):
  value=self.transport_fixture();self.begin(self.a);self.assemble()
  with self.assertRaisesRegex(ValueError,'authority'):
   self.e.machine_context(self.p,'transport/body',value,body_eligible=True,reason='Pokemon owner relation is not controller')
  body=self.e._physical_objects['transport/body'];rope=self.e._physical_objects['transport/rope']
  for disabled in (body,rope):
   disabled['disabled']=True;before=self.snap()
   with self.assertRaisesRegex(ValueError,'disabled'):self.move_transport(value)
   self.assertEqual(before,self.snap());self.e.release_equipment_transport(self.a,'transport/body',reason='release disabled actual assembly')
   self.assertEqual(LOAD.load(self.p)['weight_kg'],0);disabled.pop('disabled');self.assemble()
  self.p.pos=(4,3);before=self.snap()
  with self.assertRaisesRegex(ValueError,'formation changed'):self.move_transport(value,request='after-displacement')
  self.assertEqual(before,self.snap());self.e.release_equipment_transport(self.a,body['id'],reason='release displaced assembly')
  self.assertFalse(hasattr(self.p,E.LINK));self.valid()

 def test_gm_and_cold_restore_keep_actual_body_gear_actor_aliases_and_donor_remainders(self):
  value=self.transport_fixture();self.begin(self.a);self.assemble();self.move_transport(value)
  saved=self.snap();snapshot=self.e.gm.snapshot()
  self.e.release_equipment_transport(self.a,'transport/body',reason='after checkpoint');self.e.gm.restore(snapshot)
  cold=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)))
  for engine in (self.e,cold):
   index=W.actor_index(engine);body=engine._physical_objects['transport/body'];state=body[E.STATE]
   self.assertIs(state['equipment'][0],engine._physical_objects['transport/rope'])
   for uid in (self.a.entity_id,self.p.entity_id,self.t.entity_id):self.assertIs(getattr(index[uid],E.LINK),body)
   self.assertIs(state['controller'],index[self.a.entity_id]);self.assertIs(state['pokemon'][0],index[self.p.entity_id])
   self.assertEqual(M.shared_movement(engine,index[self.p.entity_id])[2]['remaining'],4);self.valid(engine)

 def test_real_gm_record_then_fault_restores_saddle_and_transport_graph_and_both_logs(self):
  self.saddle(fit=False);original=type(self.e.gm)._rec
  def fail(gm,what,*args,**kwargs):
   result=original(gm,what,*args,**kwargs)
   if what in ('saddle fit','equipment transport'):raise ValueError('after actual GM record')
   return result
  before=self.snap();logs=self.ruling_snapshot()
  with patch.object(type(self.e.gm),'_rec',new=fail):
   with self.assertRaisesRegex(ValueError,'after actual GM record'):
    self.e.gm.observe_saddle_fit(self.p,'saddle/actual',compatible=True,design_shape='tree',observed_shape='back',reason='actual fit')
  self.assertEqual(before,self.snap());self.assertEqual(logs,self.e.rulings.log)
  value=self.transport_fixture();before=self.snap();logs=self.ruling_snapshot()
  with patch.object(type(self.e.gm),'_rec',new=fail):
   with self.assertRaisesRegex(ValueError,'after actual GM record'):self.assemble()
  self.assertEqual(before,self.snap());self.assertEqual(logs,self.e.rulings.log)

 def test_post_movement_fault_restores_actual_crew_rope_and_both_movement_owners(self):
  value=self.transport_fixture();self.begin(self.a);self.assemble();before=self.snap();original=E.moved
  def fail(*args):original(*args);raise ValueError('after actual donor movement')
  with patch.object(E,'moved',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'after actual donor movement'):self.move_transport(value)
  self.assertEqual(before,self.snap());self.valid()

 def test_native_and_declared_boarding_consume_only_the_actual_equipped_fitted_saddle_bonus(self):
  for native in (True,False):
   with self.subTest(native=native):
    self.setUp();self.saddle();out=self.boarding(native=native)
    self.assertTrue(out['passed']);self.assertEqual(out['check'].total,12)
    self.assertEqual(self.a.budget['standard'],0);self.assertIs(W.mount_relation(W.actor_index(self.e),self.a),self.p)
    self.assertEqual(self.e.skill_roll(self.a,'곡예',fixed=[3]*3).total,9)

 def test_saddle_missing_or_incompatible_fit_is_not_a_species_whitelist_or_inventory_bonus(self):
  uid=self.saddle(fit=False);before=self.snap()
  self.assertIsInstance(self.e.gm.observe_saddle_fit(self.p,uid,reason='fit unknown'),C.PendingDecision)
  self.assertEqual(before,self.snap());self.assertFalse(self.boarding()['passed'])
  self.e.gm.observe_saddle_fit(self.p,uid,compatible=False,design_shape='wrong tree',observed_shape='actual back',reason='does not fit')
  self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),0)
  self.e.gm.observe_saddle_fit(self.p,uid,compatible=True,design_shape='custom saddle',observed_shape='actual non-Mountable fish body',reason='GM observed a suitable individual shape')
  self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),3)
  self.p.spec['height_m']=99;self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),0)

 def test_actual_attack_damage_retention_gets_saddle_plus_owned_bonus_but_other_events_do_not(self):
  self.saddle();self.auto();self.begin(self.a)
  self.assertTrue(self.e.pokemon_activity(self.a,'mounting',target=self.p,phase='mount',gm_mountable=True)['automatic'])
  with self.fixed_retention():self.e.take_damage(self.a,(self.a.base_max_hp+3)//4)
  history=self.a.custom_conditions['mount_retention_history'][-1]
  self.assertEqual((history['event'],history['bonus'],history['passed']),('damage',6,True))
  for event in ('forced_move','confusion','manual'):
   out=self.e.retain_mount(self.a,event=event,roll_options={'fixed':[3]*3})
   self.assertEqual(out['bonus'],3);self.assertTrue(out['passed'])
  self.setUp();self.saddle();self.assertTrue(self.boarding()['passed'])
  with self.fixed_retention():self.e.take_damage(self.p,(self.p.base_max_hp+3)//4)
  history=self.a.custom_conditions['mount_retention_history'][-1]
  self.assertEqual((history['event'],history['bonus'],history['passed']),('damage',3,True))

 def test_unequip_and_disabled_saddle_withdraw_bonus_and_fitted_source_restores(self):
  uid=self.saddle();self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),3)
  saved=self.snap();snapshot=self.e.gm.snapshot();ITEMS.unregister_item(self.e,self.p,E.SADDLE)
  self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),0);self.e.gm.restore(snapshot)
  self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),3)
  cold=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));index=W.actor_index(cold)
  self.assertEqual(E.saddle_bonus(cold,index[self.a.entity_id],index[self.p.entity_id],'boarding'),3)
  import field_effects as FIELD
  for identity,bonus in (('move/매직룸',0),('move/원더룸',3)):
   FIELD.install(self.e,self.a,self.r.move_mech(identity)[0]['effects_exec'][0],identity)
   self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),bonus)
  self.e._physical_objects[uid]['disabled']=True;self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),0)

 def test_catalogue_and_real_purchase_use_the_source_price_without_unconditional_skill_effects(self):
  import campaign_rewards as REWARDS
  for identity in E.SADDLES:
   effects,header=self.r.item_effects(identity)
   self.assertEqual(effects,[]);self.assertEqual(header['price'],2000)
  self.a.spec['money']=3000
  receipt=REWARDS.purchase(self.e,self.a,event_id='actual-saddle-sale',merchant='observed saddle maker',items={E.SADDLE:1},reason='actual saddle sale')
  self.assertEqual(self.a.spec['money'],1000);self.assertEqual(self.a.spec['items'].get(E.SADDLE),1)
  self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),0)

 def test_selected_version_custom_procedure_and_warm_source_are_rechecked_before_consumption(self):
  value=self.transport_fixture();custom=deepcopy(value);custom['source']='custom/transport'
  before=self.snap()
  with self.assertRaises(ValueError):self.assemble(operation=custom)
  self.assertEqual(before,self.snap())
  self.saddle();self.assertEqual(E.saddle_bonus(self.e,self.a,self.p,'boarding'),3)
  original=self.r.ruleset;selection=self.r.selection
  try:
   self.r.ruleset=RuleFilter({'unit_versions':{E.SADDLE:'changed-version'}})
   self.r.selection=RuleSelection(self.r.ruleset,list(selection.units.values()))
   with self.assertRaisesRegex(ValueError,'version'):E.saddle_bonus(self.e,self.a,self.p,'boarding')
  finally:self.r.ruleset=original;self.r.selection=selection
  with patch.object(source_context,'verified_source',side_effect=ValueError('source changed after warm read')):
   with self.assertRaisesRegex(ValueError,'source changed'):E.saddle_bonus(self.e,self.a,self.p,'boarding')
   with self.assertRaisesRegex(ValueError,'source changed'):self.assemble()


if __name__=='__main__':unittest.main()
