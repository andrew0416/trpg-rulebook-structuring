"""Actual Helping Hand producer and independently consumed roll benefits."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_event_effects as _fixture_test_category2_event_effects
import roll_effects as R,effect_instances as E,state_codec as CODEC,effects as FX

class RollComponentTests(unittest.TestCase):
 setUpClass=classmethod(_fixture_test_category2_event_effects.EventEffectTests.setUpClass.__func__)
 setUp=_fixture_test_category2_event_effects.EventEffectTests.setUp
 add=_fixture_test_category2_event_effects.EventEffectTests.add
 held=_fixture_test_category2_event_effects.EventEffectTests.held
 row=_fixture_test_category2_event_effects.EventEffectTests.row
 restored=_fixture_test_category2_event_effects.EventEffectTests.restored
 known=_fixture_test_category2_event_effects.EventEffectTests.known
 valid=_fixture_test_category2_event_effects.EventEffectTests.valid
 snap=_fixture_test_category2_event_effects.EventEffectTests.snap
 def grant(self,holder=None,issuer=None):
  holder=holder or self.p;issuer=issuer or self.a
  self.known(issuer,'도우미');self.known(holder,'메가톤펀치','울음소리','스피드스타','각지기')
  issuer.pos=(1,0);holder.pos=(0,0);self.other.pos=(2,0)
  self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(issuer)
  before=issuer.move_uses.get('move/도우미',0)
  self.e.use_move(issuer,holder,'move/도우미')
  self.assertEqual(issuer.move_uses['move/도우미'],before+1);self.assertEqual(issuer.budget['standard'],0)
  row=R.live(holder)[0];self.assertEqual(row[E.KEY]['applied_by_actor_id'],issuer.entity_id)
  self.assertIsNone(holder.next_attack)
  self.e.end_of_turn(issuer)
  self.assertEqual(R.remaining(row),{'accuracy','damage'})
  return row
 def test_native_grant_and_actual_hit_consume_both_components_for_both_actor_kinds(self):
  for role in ['trainer','pokemon']:
   with self.subTest(role=role):
    self.setUp();holder,issuer=(self.a,self.p) if role=='trainer' else (self.p,self.a)
    row=self.grant(holder,issuer);self.e.start_of_turn(holder)
    with patch.object(type(self.e),'d20',new=lambda engine:18):self.e.use_move(holder,self.other,'move/메가톤펀치',set_damage=True)
    self.assertFalse(R.live(holder));closed=R.closed(holder)[-1]
    self.assertEqual((closed['id'],closed[E.KEY]['state']),(row['id'],'consumed'))
    self.assertEqual([x['component'] for x in closed['applications']],['accuracy','damage'])
    self.assertEqual(holder.move_uses['move/메가톤펀치'],1);self.valid()
 def test_missed_actual_move_spends_accuracy_but_keeps_damage(self):
  row=self.grant();self.e.start_of_turn(self.p)
  with patch.object(type(self.e),'d20',new=lambda engine:1):self.e.use_move(self.p,self.other,'move/메가톤펀치',set_damage=True)
  self.assertEqual(R.remaining(row),{'damage'});self.assertEqual(row['applications'][0]['natural'],1)
  move=self.r.move('move/메가톤펀치');baseline=self.e.roll_damage(self.p,self.other,move,set_damage=True)
  self.assertFalse(R.live(self.p));plain=self.e.roll_damage(self.p,self.other,move,set_damage=True)
  self.assertGreater(plain,1);self.assertEqual(baseline-plain,10);self.valid()
 def test_accuracy_bonus_changes_outcome_once_and_does_not_clear_damage(self):
  move=self.r.move('move/메가톤펀치')
  first=next(n for n in range(2,20) if self.e.accuracy_check(self.p,self.other,move,fixed_roll=n)[0]);self.assertGreater(first,2)
  row=self.grant();face=first-1
  self.assertTrue(self.e.accuracy_check(self.p,self.other,move,fixed_roll=face)[0])
  self.assertFalse(self.e.accuracy_check(self.p,self.other,move,fixed_roll=face)[0])
  self.assertEqual(R.remaining(row),{'damage'});self.assertEqual(len(row['applications']),1)
 def test_damage_first_retains_accuracy_and_no_check_move_consumes_neither(self):
  row=self.grant();self.e.start_of_turn(self.p)
  self.e.use_move(self.p,self.p,'move/각지기')
  self.assertEqual(R.remaining(row),{'accuracy','damage'})
  self.e.roll_damage(self.p,self.other,self.r.move('move/메가톤펀치'),set_damage=True)
  self.assertEqual(R.remaining(row),{'accuracy'})
  self.e.accuracy_check(self.p,self.other,self.r.move('move/울음소리'),fixed_roll=1)
  self.assertFalse(R.live(self.p));self.assertEqual([x['component'] for x in R.closed(self.p)[-1]['applications']],['damage','accuracy']);self.valid()
 def test_round_end_and_partial_encounter_end_expire_unused_components_not_turn_end(self):
  for partial in [False,True]:
   with self.subTest(partial=partial):
    self.setUp();row=self.grant();self.e.start_of_turn(self.p)
    self.e.accuracy_check(self.p,self.other,self.r.move('move/울음소리'),fixed_roll=1)
    self.e.end_of_turn(self.p);self.assertEqual(R.remaining(row),{'damage'})
    if partial:self.e.end_encounter()
    else:self.e.end_round()
    self.assertFalse(R.live(self.p));closed=R.closed(self.p)[-1]
    self.assertEqual(closed[E.KEY]['state'],'expired');self.assertEqual(closed[E.KEY]['end_event']['kind'],'encounter_end' if partial else 'round_end');self.valid()
 def test_gm_and_durable_restore_keep_the_consumed_component_and_native_expiry(self):
  row=self.grant();self.e.accuracy_check(self.p,self.other,self.r.move('move/울음소리'),fixed_roll=1)
  saved=self.e.gm.snapshot('half-spent');loaded=self.restored()
  for engine in [self.e,loaded]:
   actors={c.entity_id:c for c in engine.gm.everyone};holder=actors[self.p.entity_id];target=actors[self.other.entity_id]
   self.assertEqual(R.remaining(R.live(holder)[0]),{'damage'})
   engine.roll_damage(holder,target,self.r.move('move/메가톤펀치'),set_damage=True)
   self.assertFalse(R.live(holder));self.assertEqual(R.closed(holder)[-1]['id'],row['id']);self.assertTrue(engine.validate_state()['valid'])
  self.e.gm.restore(saved);self.assertEqual(R.remaining(R.live(self.p)[0]),{'damage'})
  self.e.end_round();self.assertFalse(R.live(self.p));self.valid()
 def test_actual_area_accuracy_reuses_only_its_one_roll_for_two_targets(self):
  from grid import Grid
  self.e.grid=Grid(8,8);row=self.grant();self.a.pos=(2,1)
  self.e.start_of_turn(self.p);observed=[];original=type(self.e).accuracy_check
  def accuracy(engine,actor,target,move,*args,**kw):
   result=original(engine,actor,target,move,*args,**kw);observed.append((target.entity_id,result));return result
  with patch.object(type(self.e),'d20',new=lambda engine:18),patch.object(type(self.e),'accuracy_check',new=accuracy):self.e.use_move_on(self.p,self.other,'move/스피드스타',[self.p,self.other,self.a])
  self.assertEqual({x[0] for x in observed},{self.other.entity_id,self.a.entity_id})
  closed=R.closed(self.p)[-1];event=next(x for x in closed['applications'] if x['component']=='accuracy')
  self.assertEqual(set(event['target_ids']),{self.other.entity_id,self.a.entity_id});self.assertEqual(len(closed['applications']),2);self.valid()
 def test_unsupported_recast_and_forged_shared_roll_fail_before_cost_or_rng(self):
  row=self.grant();self.e.start_of_turn(self.p);self.known(self.p,'도우미');before=self.snap()
  with self.assertRaisesRegex(ValueError,'composition'):self.e.use_move(self.p,self.p,'move/도우미')
  self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'authority'):self.e.accuracy_check(self.p,self.other,self.r.move('move/메가톤펀치'),shared_roll={})
  self.assertEqual(before,self.snap());self.assertEqual(R.remaining(row),{'accuracy','damage'})
 def test_malformed_payload_and_round_reject_saves_before_state_replacement(self):
  row=self.grant();good=deepcopy(row)
  for change in ['amount','round']:
   row.clear();row.update(deepcopy(good))
   if change=='amount':row['effect']['components']['accuracy']['amount']=True
   else:row['round_end_deadline']=True
   with self.assertRaises(ValueError):self.e.gm.snapshot()
   with self.assertRaises(ValueError):CODEC.dump_engine(self.e)
  with patch.object(E,'validate_actor',return_value=True),patch.object(E,'validate_world',return_value=True):
   bad=self.e.gm.snapshot('malformed-roll');payload=json.loads(json.dumps(CODEC.dump_engine(self.e)))
  row.clear();row.update(good);before=self.snap()
  with self.assertRaises(ValueError):self.e.gm.restore(bad)
  with self.assertRaises(ValueError):CODEC.load_engine(self.r,payload)
  self.assertEqual(before,self.snap());self.valid()
 def test_legacy_scalar_survives_storage_but_needs_origin_before_consumption(self):
  self.known(self.p,'메가톤펀치');self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.p)
  self.p.next_attack={'accuracy':2,'damage':10}
  loaded=self.restored();clone=next(c for c in loaded.gm.everyone if c.entity_id==self.p.entity_id)
  for engine,holder in [(self.e,self.p),(loaded,clone)]:
   target=next(c for c in engine.gm.everyone if c.entity_id==self.other.entity_id);before=(engine.rng.getstate(),deepcopy(holder.next_attack),deepcopy(holder.budget),deepcopy(holder.move_uses))
   with self.assertRaisesRegex(ValueError,'reconciliation'):engine.accuracy_check(holder,target,self.r.move('move/메가톤펀치'))
   with self.assertRaisesRegex(ValueError,'reconciliation'):engine.roll_damage(holder,target,self.r.move('move/메가톤펀치'))
   with self.assertRaisesRegex(ValueError,'reconciliation'):engine.use_move(holder,target,'move/메가톤펀치')
   self.assertEqual((engine.rng.getstate(),holder.next_attack,holder.budget,holder.move_uses),before)

 def test_actual_ball_accuracy_consumes_only_accuracy_and_legacy_rejection_preserves_ball(self):
  from builder import build_pokemon
  wild=self.add(build_pokemon(self.r,'잉어킹',5,moves=[],abilities=[]));wild.side='wild';wild.spec['side']='wild';wild.pos=(2,0)
  self.a.spec.setdefault('items',{})['몬스터볼']=2
  row=self.grant(self.a,self.p);self.e.start_of_turn(self.a)
  self.assertFalse(self.e.throw_ball(self.a,wild,fixed_accuracy=1))
  self.assertEqual(R.remaining(row),{'damage'});self.assertEqual(row['applications'][0]['move_id'],'ball')
  self.assertEqual(self.a.spec['items']['몬스터볼'],1)
  self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.gm.everyone);self.e.start_of_turn(self.a)
  self.a.next_attack={'accuracy':2};before=self.snap()
  with self.assertRaisesRegex(ValueError,'reconciliation'):self.e.throw_ball(self.a,wild,fixed_accuracy=1)
  self.assertEqual(before,self.snap())

if __name__=='__main__':unittest.main()
