"""Real Engine.use_item throws consume stock and source one family immunity."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_category2_body_modes as FIX
import test_category2_medicine_stock as STOCK_FIX
from builder import build_trainer
import pester_balls as P,capability_actions as CAP,common_checks as C
import consumption_execution as PAID,state_codec as CODEC


class Tests(unittest.TestCase):
 setUpClass=classmethod(FIX.Tests.setUpClass.__func__)
 setUp=FIX.Tests.setUp
 add=FIX.Tests.add
 pokemon=FIX.Tests.pokemon
 restored=FIX.Tests.restored
 begin=FIX.Tests.begin
 held=STOCK_FIX.MedicineStockTests.held

 def ready(self,source='item/오물탄-잠듦',target=None):
  self.a.spec['skills'].update({'육상':2,'곡예':4})
  self.a.spec['items']={uid:8 for uid in P.SOURCES}
  self.a.pos=(1,3);self.t.pos=(3,3);self.p.pos=(3,6)
  self.begin(self.a)
  return source,target or self.t

 def use(self,source='item/오물탄-잠듦',target=None,natural=20,**options):
  return self.e.use_item(self.a,source,target or self.t,fixed_accuracy=natural,**options)

 def snap(self):
  return deepcopy((self.a.spec,self.a.budget,self.t.spec,self.t.conditions,
   self.e.rng.getstate(),self.e.log_lines,getattr(self.e,'_physical_objects',{})),{id(self.r):self.r})

 def elapse(self,seconds):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  self.e.end_encounter(self.e.everyone,round_elapsed_seconds=0)
  self.e.advance_time(seconds)

 def test_all_six_actual_variants_status_sources_price_and_unselected_kind(self):
  for source,status in P.VARIANTS.items():
   with self.subTest(source=source):
    self.setUp();self.ready(source)
    out=self.use(source,accepted=False)
    self.assertTrue(out['hit']);self.assertTrue(out['status_applied'])
    self.assertIn(status,self.t.conditions);self.assertEqual(self.a.spec['items'][source],7)
    self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.r.item_effects(source)[1]['price'],350)
    origin=self.t.spec[P.KEY]['episodes'][0]['origin']
    self.assertEqual((origin['source'],origin['status']),(source,status))
    self.assertTrue(P.projection(self.e,self.t)['immune'])
    receipt=PAID.validate(self.a)[origin['payment_id']]
    self.assertEqual(receipt['outcome'],'applied');self.assertEqual(receipt['target_id'],self.t.entity_id)
  self.setUp();self.ready();before=self.snap()
  self.assertIsInstance(self.use('item/오물탄-1'),C.PendingDecision)
  self.assertEqual(self.snap(),before)

 def test_actual_ball_accuracy_boundaries_miss_and_native_throwing_masteries(self):
  self.ready();need=6+self.t.evasion('변화')
  for natural,hit in ((1,False),(need-1,False),(need,True),(20,True)):
   with self.subTest(natural=natural):
    if P.KEY in self.t.spec:self.elapse(3600)
    self.e.cure_status(self.t,'잠듦');self.begin(self.a)
    out=self.use(natural=natural)
    self.assertEqual(out['hit'],hit,self.e.log_lines[-8:]);self.assertEqual(out['immunity_started'],hit)
    self.assertEqual('잠듦' in self.t.conditions,hit)
  self.setUp();self.ready();maximum=CAP.throwing_range(self.e,self.a,category='poke_ball')
  self.t.pos=(self.a.pos[0]+maximum+1,3);before=self.snap()
  with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before)
  self.a.spec['edges']=['edge/투척-마스터리']
  self.assertEqual(CAP.throwing_range(self.e,self.a,category='poke_ball'),maximum+2)
  self.assertTrue(self.use()['hit'])

 def test_status_immunity_still_starts_shared_hour_and_followups_do_not_refresh(self):
  self.ready();self.e.gm.set_ability(self.t,'불면',reason='native sleep immunity')
  out=self.use();self.assertTrue(out['hit']);self.assertFalse(out['status_applied']);self.assertTrue(out['immunity_started'])
  self.assertNotIn('잠듦',self.t.conditions);self.elapse(3599)
  self.begin(self.a);at=self.e.elapsed_seconds
  other=self.use('item/오물탄-화상')
  self.assertTrue(other['family_immune_before']);self.assertFalse(other['status_applied']);self.assertFalse(other['immunity_started'])
  self.assertNotIn('화상',self.t.conditions);self.assertEqual(len(self.t.spec[P.KEY]['episodes']),1)
  self.e.end_of_turn(self.a);self.e.end_encounter(self.e.everyone,round_elapsed_seconds=0)
  self.e.advance_time(1)
  self.assertEqual(self.e.elapsed_seconds,at+1);self.assertFalse(P.projection(self.e,self.t)['immune'])
  self.begin(self.a);out=self.use('item/오물탄-화상')
  self.assertTrue(out['status_applied']);self.assertTrue(out['immunity_started'])
  self.assertEqual(len(self.t.spec[P.KEY]['episodes']),2)

 def test_owned_pokemon_and_trainer_targets_need_no_capture_eligibility(self):
  self.ready();self.assertEqual(self.t.spec['trainer_id'],self.a.entity_id)
  self.assertTrue(self.use()['hit']);self.assertFalse(self.t.captured)
  trainer=self.add(build_trainer(self.r,'other trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={},extra={'items':{},'edges':[]}))
  trainer.pos=(4,3);self.begin(self.a)
  self.assertTrue(self.use('item/오물탄-혼란',trainer)['status_applied'])
  self.assertIn('혼란',trainer.conditions)

 def test_exact_physical_stock_and_both_restore_paths_keep_immunity(self):
  self.ready();self.held(self.a,'item/오물탄-잠듦','pester-physical')
  out=self.use(held_selection='pester-physical');self.assertEqual(out['payment']['kind'],'held_instance')
  self.assertEqual(self.a.spec['items']['item/오물탄-잠듦'],8)
  self.assertIn('consumed',self.e._physical_objects['pester-physical'])
  self.e.gm.snapshot('pester-hit');loaded=self.restored();index={c.entity_id:c for c in loaded.everyone}
  target=index[self.t.entity_id];P.validate_world(loaded,index)
  self.assertEqual(P.projection(loaded,target),P.projection(self.e,self.t))
  self.assertIn('consumed',loaded._physical_objects['pester-physical'])
  self.elapse(3600);self.assertFalse(P.projection(self.e,self.t)['immune'])
  self.e.gm.restore('pester-hit');self.assertTrue(P.projection(self.e,self.t)['immune'])
  self.begin(self.a);before=self.snap()
  with self.assertRaises(ValueError):self.use(held_selection='pester-physical')
  self.assertEqual(self.snap(),before)

 def test_uncertain_hour_is_pending_without_cost_and_actual_observation_survives_restore(self):
  self.ready();self.use();self.elapse(3595)
  self.e.unresolved_time_intervals.append({'round':55,'known_seconds':0})
  self.assertEqual(P.projection(self.e,self.t)['elapsed_bounds'],[3595,3605])
  self.assertIsNone(P.projection(self.e,self.t)['immune']);self.begin(self.a);before=self.snap()
  self.assertIsInstance(self.use('item/오물탄-화상'),C.PendingDecision)
  self.assertEqual(self.snap(),before)
  with self.assertRaises(ValueError):P.observe_elapsed(self.e,self.t,3606,reason='outside known bound')
  P.observe_elapsed(self.e,self.t,3600,reason='GM observes six seconds of the unresolved interval')
  self.assertFalse(P.projection(self.e,self.t)['immune'])
  loaded=self.restored();index={c.entity_id:c for c in loaded.everyone};P.validate_world(loaded,index)
  self.assertFalse(P.projection(loaded,index[self.t.entity_id])['immune'])
  out=self.use('item/오물탄-화상');self.assertTrue(out['status_applied'])

 def test_invalid_request_range_stock_source_and_post_status_failure_are_atomic(self):
  self.ready()
  for options in ({'free':True},{'count':2},{'duration_minutes':1},{'selected_move':'move/몸통'},{'natural':0}):
   with self.subTest(options=options):
    before=self.snap()
    with self.assertRaises(ValueError):self.use(**options)
    self.assertEqual(self.snap(),before)
  old=self.a.spec['items']['item/오물탄-잠듦'];self.a.spec['items']['item/오물탄-잠듦']=0;before=self.snap()
  with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before);self.a.spec['items']['item/오물탄-잠듦']=old
  grid=self.e.grid;self.e.grid=None;before=self.snap()
  self.assertIsInstance(self.use(),C.PendingDecision);self.assertEqual(self.snap(),before);self.e.grid=grid
  original=self.r.item_effects
  def changed(source):
   effects,header=original(source)
   if source=='item/오물탄-잠듦':header=dict(header,price=349)
   return effects,header
  before=self.snap()
  with patch.object(self.r,'item_effects',side_effect=changed):
   with self.assertRaises(ValueError):self.use()
  self.assertEqual(self.snap(),before)
  self.held(self.a,'item/오물탄-잠듦','atomic-ball');before=self.snap()
  original_apply=type(self.e).apply_status
  def failed(e,c,*args,**kw):
   original_apply(e,c,*args,**kw)
   raise RuntimeError('failure after actual status mutation inside transaction')
  original_d20=type(self.e).d20
  def rolled(e):
   original_d20(e)
   return 20
  with patch.object(type(self.e),'apply_status',new=failed),patch.object(type(self.e),'d20',new=rolled):
   with self.assertRaises(RuntimeError):self.use(natural=None,held_selection='atomic-ball')
  self.assertEqual(self.snap(),before);self.assertNotIn(P.KEY,self.t.spec)
  self.assertTrue(self.use(held_selection='atomic-ball')['hit'])

 def test_recipient_source_clock_and_paid_hit_tampering_are_rejected(self):
  self.ready();self.use();episode=self.t.spec[P.KEY]['episodes'][0]
  original=deepcopy(episode)
  for field,value in (('source','item/오물탄-화상'),('natural',1),('target_id',self.a.entity_id),('at',1)):
   episode['origin'][field]=value
   with self.assertRaises(ValueError):P.validate_actor(self.t)
   episode.clear();episode.update(deepcopy(original))
  receipt=PAID.validate(self.a)[episode['origin']['payment_id']];receipt['outcome']='no_effect'
  with self.assertRaises(ValueError):P.validate_world(self.e,{c.entity_id:c for c in self.e.everyone})
  receipt['outcome']='applied';episode['origin']['unknown_index']=999
  episode['origin']['sha256']=P.TX.request_fingerprint({k:v for k,v in episode['origin'].items() if k!='sha256'})
  with self.assertRaises(ValueError):P.projection(self.e,self.t)


class IntegratedHooks(unittest.TestCase):
 # Public-use linkage and both validation hooks on the stable composed runtime.
 setUpClass=classmethod(FIX.Tests.setUpClass.__func__)
 setUp=FIX.Tests.setUp
 add=FIX.Tests.add
 pokemon=FIX.Tests.pokemon
 begin=FIX.Tests.begin
 ready=Tests.ready
 use=Tests.use
 def test_export_rejects_actor_and_world_tampering_through_native_hooks(self):
  self.ready();out=self.use();origin=self.t.spec[P.KEY]['episodes'][0]['origin']
  self.assertTrue(out['hit']);self.assertTrue(out['status_applied']);self.assertTrue(out['immunity_started'])
  self.assertIn('잠듦',self.t.conditions);self.assertEqual(self.a.spec['items'][out['source']],7)
  self.assertEqual(self.a.budget['standard'],0)
  receipt=PAID.validate(self.a)[origin['payment_id']]
  self.assertIs(receipt['item_stock'],out['payment'])
  self.assertEqual((receipt['target_id'],receipt['outcome']),(self.t.entity_id,'applied'))
  self.assertIn({'kind':P.KEY,'id':self.t.spec[P.KEY]['episodes'][0]['id']},receipt['results'])
  self.assertTrue(P.projection(self.e,self.t)['immune']);self.e.export_state()
  old=origin['source'];origin['source']='item/오물탄-독'
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  origin['source']=old;receipt=PAID.validate(self.a)[origin['payment_id']]
  receipt['outcome']='no_effect'
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()


if __name__=='__main__':unittest.main()
