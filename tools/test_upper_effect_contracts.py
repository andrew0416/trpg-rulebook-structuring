"""Native counterexamples for lossless controls, source lifetime and suffix boundaries."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import effects as FX
import effects_ext as EXT
import effect_contracts as CONTRACTS
import effect_lifetimes as LIFE
import combat_timing as TIME
import common_checks as C
import maneuver_grants as MG

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT)
 def setUp(self):
  self.r.rulings.hooks={key:[] for key in self.r.rulings.hooks}
  self.e=Engine(self.r,42)
  def actor(name,side):return Combatant(self.r,dict(id='pokemon/'+name,name=name,kind='pokemon',side=side,pos=(0,0) if side=='party' else (1,0),level=30,stats=dict(hp=100,atk=20,**{'def':20},spa=20,spd=20,spe=10),skills={'전투':4,'육상':4,'곡예':4},movement={'land':6},moves=['move/배리어러시','move/블록','move/문어굳히기','move/괴력']))
  self.a=actor('A','party');self.b=actor('B','wild');self.e.everyone=[self.a,self.b];self.e.gm.everyone=self.e.everyone
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def apply(self,effects,source='move/배리어러시',**ctx):
  return FX.run_effects(self.e,self.a,self.b,effects,dict(hit=True,attacker=self.a,target=self.b,engine=self.e,**ctx),source)
 def boundary(self,count):
  self.e.end_of_turn(self.a);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(count)
 def state(self):
  value=(self.e.rng.getstate(),self.a.budget,self.a.move_uses,self.a.hp,self.b.hp,self.a.stages,self.b.stages,self.a.custom_conditions,self.b.custom_conditions)
  memo={id(self.a):self.a,id(self.b):self.b,id(self.e):self.e,id(self.r):self.r}
  def opaque(x):
   if type(x) is object:memo[id(x)]=x
   elif isinstance(x,dict):
    for y in x.values():opaque(y)
   elif isinstance(x,(list,tuple)):
    for y in x:opaque(y)
  opaque(value)
  return deepcopy(value,memo)
 def test_native_move_installs_dr_and_expires_at_next_same_count(self):
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)):
   self.assertGreater(self.e.use_move(self.a,self.b,'move/배리어러시',set_damage=True),0)
  self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),5);self.assertEqual(self.a.budget['standard'],0)
  self.boundary(21);self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),5)
  self.e.at_initiative_count(20);self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),0)
 def test_native_block_expires_before_users_next_start_saves(self):
  with patch.object(self.e,'accuracy_check',return_value=(True,10,False)):
   self.e.use_move(self.a,self.b,'move/블록')
  self.assertTrue({'구속','수렁'}<=self.b.conditions)
  self.e.end_of_turn(self.a);self.assertIn('수렁',self.b.conditions)
  self.e.start_of_turn(self.b,initiative_count=10);self.e.end_of_turn(self.b);self.assertIn('수렁',self.b.conditions)
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  self.assertFalse({'구속','수렁'} & self.b.conditions)
 def test_native_repeat_without_grapple_producer_blocks_before_damage_cost_rng(self):
  before=self.state()
  with self.assertRaises(CONTRACTS.EffectContractError):self.e.use_move(self.a,self.b,'move/문어굳히기')
  self.assertEqual(before,self.state())
 def test_independent_sources_overlap_without_expiry_reversing_baseline(self):
  self.a.damage_reduction=7
  self.apply([dict(type='damage_reduction',value=5,target='self',duration='1라운드')])
  self.apply([dict(type='damage_reduction',value=10,target='self',duration='2라운드')],source='move/파워풀에지')
  self.assertEqual(EXT.defense_hook(self.e,self.b,self.a,dict(type='노말',**{'class':'물리'}),{},'def')[1],22)
  self.boundary(20);self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),10);self.assertEqual(self.a.damage_reduction,7)
 def test_same_source_reapplication_has_independent_expiry(self):
  effect=dict(type='damage_reduction',value=5,target='self',duration='1라운드')
  self.apply([effect]);self.boundary(21);self.apply([effect]);self.e.at_initiative_count(20)
  self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),5)
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(21);self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),0)
 def test_status_sources_transfer_expiry_ownership(self):
  self.apply([dict(type='apply_status',status='수렁',target='target',duration='1라운드')],source='move/블록')
  self.apply([dict(type='apply_status',status='수렁',target='target',duration='2라운드')],source='move/앵커샷')
  self.boundary(20);self.assertIn('수렁',self.b.conditions)
  self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(20);self.assertNotIn('수렁',self.b.conditions)
 def test_independent_external_status_reapplication_survives_expiry(self):
  self.apply([dict(type='apply_status',status='수렁',target='target',duration='1라운드')],source='move/블록')
  self.e.apply_status(self.b,'수렁');self.boundary(20);self.assertIn('수렁',self.b.conditions)
 def test_timed_evasion_reaches_native_evasion_not_permanent_aggregate(self):
  before=self.a.evasion('물리');self.apply([dict(type='evasion_mod',value=2,target='self',until="end of user's next turn")],source='move/튀어오르기')
  self.assertEqual(self.a.evasion('물리'),before+2);self.assertEqual(self.a.evasion_mod,0)
  self.boundary(20);self.e.start_of_turn(self.a,initiative_count=20);self.assertEqual(self.a.evasion('물리'),before+2)
  self.e.end_of_turn(self.a);self.assertEqual(self.a.evasion('물리'),before)
 def test_timed_save_reaches_actual_save_dc(self):
  before=EXT.save_dc(self.e,self.a,'잠듦',16)
  self.apply([dict(type='save_mod',value=2,target='self',duration='1라운드')],source='move/손에손잡기')
  self.assertEqual(EXT.save_dc(self.e,self.a,'잠듦',16),before-2);self.boundary(20);self.assertEqual(EXT.save_dc(self.e,self.a,'잠듦',16),before)
 def test_encounter_end_clears_only_encounter_lifetimes(self):
  self.apply([dict(type='damage_reduction',value=5,target='self',duration='1라운드')])
  self.apply([dict(type='damage_reduction',value=3,target='self',until='scene_end')],source='move/가드셰어')
  self.e.end_encounter(self.e.everyone);self.assertEqual(LIFE.numeric(self.a,'damage_reduction'),3)
 def test_ambiguous_turn_and_known_unsupported_repeat_are_distinct(self):
  a=CONTRACTS.inspect(self.e,self.a,self.b,dict(type='apply_status',status='수렁',until='next turn'),'move/블록')
  b=CONTRACTS.inspect(self.e,self.a,self.b,dict(type='stage_change',stat='def',delta=-1,repeat='each turn end while grappled'),'move/문어굳히기')
  self.assertEqual((a.category,b.category),('unresolved_source','unsupported_execution'))
 def test_scope_and_extra_target_are_never_silently_narrowed(self):
  for extra in [dict(target='self_and_allies'),dict(scope='all enemies'),dict(target='self',on='target')]:
   with self.subTest(extra=extra):
    before=self.state();result=self.apply([dict(type='stage_change',stat='atk',delta=1,**extra)])
    self.assertEqual(result,(0,1));self.assertEqual(before,self.state())
 def test_known_unsupported_fields_reject_before_native_item_inventory_and_cost(self):
  self.a.spec['items']={'상처약':1};self.a.hp-=10
  original=self.r.item_effects
  with patch.object(self.r,'item_effects',side_effect=lambda name:( [dict(type='heal',amount=20,target='target',repeat='forever')],dict(id='item/상처약',category='약')) if name=='상처약' else original(name)):
   before=self.state()
   with self.assertRaises(CONTRACTS.EffectContractError):self.e.use_item(self.a,'상처약',self.a)
   self.assertEqual(self.a.spec['items']['상처약'],1);self.assertEqual(before,self.state())
 def test_unknown_predicate_halts_suffix_false_predicate_does_not(self):
  first=dict(type='stage_change',stat='atk',delta=1,**{'if':'target is ally OR maybe unknown'})
  second=dict(type='stage_change',stat='def',delta=1)
  result=self.apply([first,second]);self.assertEqual(result,(0,1));self.assertEqual(self.b.stages['def'],0)
  self.assertEqual([x.status for x in result.outcomes],['condition_unknown','deferred_suffix'])
  false=self.apply([dict(first,**{'if':'target is ally'}),second]);self.assertEqual(false,(1,0));self.assertEqual(self.b.stages['def'],1)
 def test_missing_natural_observation_is_unknown_not_false(self):
  result=self.apply([dict(type='stage_change',stat='atk',delta=1,on_natural_roll_min=15)])
  self.assertEqual(result.pending[0].status,'condition_unknown')
 def test_unsupported_head_never_applies_suffix(self):
  result=self.apply([dict(type='not_an_effect'),dict(type='stage_change',stat='def',delta=1)])
  self.assertEqual(result,(0,1));self.assertEqual(self.b.stages['def'],0);self.assertEqual(result.outcomes[-1].status,'deferred_suffix')
 def test_hook_replacement_new_condition_is_rechecked(self):
  self.e.rulings.add_hook('before_effect',lambda e,ctx:dict(e,**{'if':'target is ally'}),'test condition replacement')
  result=self.apply([dict(type='stage_change',stat='atk',delta=1)])
  self.assertEqual(result,(0,0));self.assertEqual(self.b.stages['atk'],0)
 def test_receipt_binds_actor_target_payload_and_occurrence(self):
  effect=dict(type='stage_change',stat='atk',delta=1);occ,token=CONTRACTS.issue_receipt(self.e,'move/배리어러시',self.a,self.b,effect,0)
  self.assertTrue(CONTRACTS.validate_receipt(self.e,token,'move/배리어러시',occ,self.a,self.b,effect))
  for actor,target,data in [(self.b,self.b,effect),(self.a,self.a,effect),(self.a,self.b,dict(effect,delta=2))]:
   with self.assertRaises(ValueError):CONTRACTS.validate_receipt(self.e,token,'move/배리어러시',occ,actor,target,data)
 def pending_batch(self):
  effect=next(x for x in self.r.move_mech('move/괴력')[0]['effects_exec'] if x['type']=='free_maneuver')
  return self.apply([effect,dict(type='stage_change',stat='def',delta=1)],source='move/괴력')
 def test_actual_child_decline_resumes_suffix_once_without_parent_replay(self):
  batch=self.pending_batch();pending=batch.pending[0].reason;before=list(self.a._action_history)
  self.assertEqual(self.b.stages['def'],0);result=MG.resolve(self.e,self.a,pending.grant_id,accept=False)
  self.assertEqual(self.b.stages['def'],1);self.assertFalse(batch.pending);self.assertEqual(self.a._action_history,before)
  MG.resolve(self.e,self.a,pending.grant_id);self.assertEqual(self.b.stages['def'],1)
  with self.assertRaises(ValueError):FX.resume_effects(self.e,batch.outcomes[0].receipt)
 def test_resume_requires_actual_predecessor_completion(self):
  batch=self.pending_batch()
  with self.assertRaises(ValueError):FX.resume_effects(self.e,batch.outcomes[0].receipt)
  self.assertEqual(self.b.stages['def'],0)
 def test_suffix_payload_and_context_are_frozen_with_real_actor_refs(self):
  nested={'selection':[1]};effect=next(x for x in self.r.move_mech('move/괴력')[0]['effects_exec'] if x['type']=='free_maneuver')
  suffix=dict(type='stage_change',stat='def',delta=1);batch=self.apply([effect,suffix],source='move/괴력',test_context=nested)
  suffix['delta']=6;nested['selection'].append(2)
  row=self.e._effect_dispatch_receipts[batch.outcomes[-1].receipt]
  self.assertEqual(row['effects'][0]['delta'],1);self.assertEqual(row['context']['test_context'],{'selection':[1]});self.assertIs(row['context']['attacker'],self.a)
 def test_changed_source_selection_rejects_suffix(self):
  batch=self.pending_batch();token=batch.outcomes[0].receipt;CONTRACTS.finish(self.e,token,'completed')
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda uid:uid+'/changed' if uid=='move/괴력' else original(uid)):
   with self.assertRaises(ValueError):FX.resume_effects(self.e,token)
  self.assertEqual(self.b.stages['def'],0)
 def test_snapshot_restores_pending_suffix_aliases_and_engine_identity(self):
  batch=self.pending_batch();pending=batch.pending[0].reason;self.e.gm.snapshot('pending')
  MG.resolve(self.e,self.a,pending.grant_id,accept=False);self.assertEqual(self.b.stages['def'],1)
  self.e.gm.restore('pending');self.assertEqual(self.b.stages['def'],0)
  row=next(x for x in self.e._effect_dispatch_receipts.values() if x.get('status')=='deferred_suffix')
  self.assertIs(row['context']['engine'],self.e);self.assertIs(row['actor'],self.a)
  MG.resolve(self.e,self.a,pending.grant_id,accept=False);self.assertEqual(self.b.stages['def'],1)
 def test_unsupported_extra_move_producers_are_preflight_not_false_completion(self):
  for kind in ('ally_struggle','copy_move','random_move','repeat_last_move','zone'):
   self.assertEqual(CONTRACTS.inspect(self.e,self.a,self.b,{'type':kind},'move/괴력').category,'unsupported_execution')

 def test_unknown_never_miss_exception_rejects_before_move_cost_and_at_accuracy(self):
  self.a.registry.append(dict(type='never_miss',except_='unused'))
  self.a.registry[-1]={'type':'never_miss','except':'some unknown condition'}
  before=self.state()
  with self.assertRaises(CONTRACTS.EffectContractError):self.e.use_move(self.a,self.b,'move/배리어러시')
  self.assertEqual(before,self.state())
  with self.assertRaises(CONTRACTS.EffectContractError):self.e.accuracy_check(self.a,self.b,self.r.move('move/배리어러시'),fixed_roll=2)
 def test_never_miss_only_false_exception_authorizes_hit(self):
  effect={'type':'never_miss','except':'target is ally'}
  self.assertTrue(CONTRACTS.never_miss_allowed(self.e,self.a,self.b,effect,{}))
  self.b.side=self.a.side;self.assertFalse(CONTRACTS.never_miss_allowed(self.e,self.a,self.b,effect,{}))

 def test_known_unsupported_trigger_never_consumes_frequency(self):
  import frequency as FREQ
  self.a.ability_triggers=[dict(name='test source',spec={'event':'turn_end'},frequency='장면 x1',effects=[dict(type='damage_reduction',value=5,**{'while':'unresolved source'})])]
  before=deepcopy(self.a.counters)
  FX.fire_event(self.e,self.a,{'event':'turn_end'})
  self.assertEqual(self.a.counters,before);self.assertEqual(self.a.damage_reduction,0)

 def test_required_suffix_blocks_actual_time_scene_and_new_action(self):
  import turn as TURN
  self.pending_batch();before=self.state()
  for action in (lambda:self.e.advance_time(1,[self.a]),lambda:self.e.end_scene(self.e.everyone),lambda:self.e.end_encounter(self.e.everyone),lambda:self.e.use_move(self.a,self.b,'move/배리어러시')):
   with self.assertRaises(ValueError):action()
  with self.assertRaises(ValueError):TURN.spend(self.e,self.a,'swift','unrelated action')
  self.assertEqual(before,self.state())
 def test_stale_suffix_cannot_apply_after_external_boundary_change(self):
  batch=self.pending_batch();token=batch.outcomes[0].receipt;CONTRACTS.finish(self.e,token,'completed')
  self.e.elapsed_seconds+=1
  with self.assertRaisesRegex(ValueError,'boundary'):FX.resume_effects(self.e,token)
  self.assertEqual(self.b.stages['def'],0)
 def test_selected_source_payload_change_rejects_continuation(self):
  batch=self.pending_batch();token=batch.outcomes[0].receipt;CONTRACTS.finish(self.e,token,'completed')
  original=self.r.move_mech
  with patch.object(self.r,'move_mech',side_effect=lambda uid:({'effects_exec':[{'type':'reset_stages'}]},'changed') if uid=='move/괴력' else original(uid)):
   with self.assertRaisesRegex(ValueError,'profile'):FX.resume_effects(self.e,token)
  self.assertEqual(self.b.stages['def'],0)

if __name__=='__main__':unittest.main(verbosity=2)
