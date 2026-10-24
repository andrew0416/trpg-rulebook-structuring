"""Whole Juggler class through real acquisition, party, physical and native turns."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import assert_rejected_unchanged
import juggler as J,trainer_feature_acquisition as T,party_actions as P,pokemon_party as PARTY
import world_entities as W,state_codec as CODEC,action_points as AP,initiative_schedule as S,initiative_interrupts as I
import coat_effects as COATS,effect_instances as E,combat_timing as TIME,map_terrain as TERRAIN

class JugglerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.setup()
 def setup(self,*,acro=6,guile=6,mode='full_contact',wild=False,opponent_edges=(),opponent_feats=()):
  self.e=Engine(self.rules,seed=831887);self.e.grid=Grid(40,16)
  self.a=self.actor('owner','trainer',(1,1),60,skills={'곡예':acro,'교활':guile,'명령':6,'집중':6,'육상':6})
  self.b=self.actor('opponent','trainer',(15,1),50,side='foe',edges=opponent_edges,feats=opponent_feats)
  self.p=self.actor('outgoing','pokemon',(3,1),30,owner=self.a)
  self.q=self.actor('reserve','pokemon',(4,1),20,owner=self.a,field=False)
  self.z=self.actor('third','pokemon',(5,1),10,owner=self.a,field=False)
  self.t=self.actor('target','pokemon',(6,1),25,owner=None if wild else self.b,side='wild' if wild else 'foe')
  self.u=self.actor('foe-reserve','pokemon',(14,2),15,owner=self.b,side='foe',field=False)
  PARTY.configure(self.e,self.a,mode='standard',reason='actual Juggler roster',roster=[self.p,self.q,self.z],storage={'kind':'center','id':'juggler-center'})
  PARTY.configure(self.e,self.b,mode='standard',reason='actual rival roster',roster=[self.u] if wild else [self.t,self.u],storage={'kind':'center','id':'rival-center'})
  P.configure(self.e,self.a,battle_mode=mode,reason='actual battle rules');P.configure(self.e,self.b,battle_mode=mode,reason='actual battle rules')
  TERRAIN.observe(self.e,[(x,y) for x in range(1,20) for y in (1,2,3)],base='regular',reason='GM observes actual ball landing ground')
 def actor(self,name,kind,pos,speed,*,owner=None,side='party',field=True,skills=None,edges=(),feats=()):
  spec={'id':kind+'/'+name,'name':name,'kind':kind,'level':30,'pos':pos,'size':'중형','weight_kg':20,
   'stats':{'hp':80,'atk':25,'def':20,'spa':25,'spd':20,'spe':speed},'skills':skills or {'곡예':6,'교활':6,'명령':6,'집중':6,'육상':6},
   'moves':['move/몸통박치기','move/물대포','move/아쿠아링','move/트릭',J.LOCK],'abilities':[],'types':['노말'],'items':{},'feats':list(feats),'edges':list(edges),'movement':{'land':6},'movement_basis':'current','loyalty':6}
  if owner:spec['trainer_id']=owner.entity_id
  a=Combatant(self.rules,spec);self.e.gm.add_combatant(a,pos=pos,side=side,reason='actual Juggler participant')
  self.e.gm.set_footprint(a,[(0,0)],reason='observed actual one-cell body')
  if owner:self.e.gm.observe_loyalty(a,6,reason='observed cooperative current-owner command relation')
  a.on_field=field;return a
 def acquire(self,u,actor=None,selection=None):
  a=actor or self.a;return T.acquire_static(self.e,a,u,acquisition_request_id=a.entity_id+'/'+u,selection=selection)
 def family(self,u=J.FIRST,actor=None,selection=None):
  a=actor or self.a
  if u==J.QUICK:
   if not __import__('acquired_features').owned_rule_count(a,u):self.acquire(u,a)
   return
  for parent in J.PARENTS[u]:self.family(parent,a)
  if not J.acquired(a,u):self.acquire(u,a,selection=selection)
 def close(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
 def begin(self,a=None):
  self.close()
  if self.e.round_start_seconds is not None:self.e.end_round()
  self.e.start_round(self.e.everyone);self.e.start_of_turn(a or self.a,initiative_count=60)
 def turn(self,a):self.close();self.e.start_of_turn(a,initiative_count=50)
 def action(self,u=J.QUICK,*,recall=None,send=None,request='switch',**kw):
  return J.act(self.e,self.a,recall=[self.p] if recall is None else recall,send=[(self.q,(4,1) if recall==[] else (3,1))] if send is None else send,request_id=request,reason='actual selected Juggler party action',source_id=u,**kw)
 def reject(self,fn,reason=None):assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.b,self.p,self.q,self.z,self.t,self.u=[W.actor_index(self.e)[u] for u in ('trainer/owner','trainer/opponent','pokemon/outgoing','pokemon/reserve','pokemon/third','pokemon/target','pokemon/foe-reserve')]
 def move(self,p=None,mid='move/물대포',target=None):
  p=p or self.p
  with patch.object(Engine,'d20',return_value=18):self.e.use_move(p,target or self.t,mid,set_damage=True)
  rows=[r for r in getattr(self.e,'_move_completions',{}).values() if r['actor'] is p]
  self.assertTrue(rows,'native Move did not reach completion: '+repr(self.e.log_lines[-12:]))
  self.assertEqual(rows[-1]['phase'],'complete',self.e.log_lines[-12:]);return rows[-1]
 def last_event(self,kind='release',actor=None):return [r for r in J.state(actor or self.a)['events'] if r['kind']==kind][-1]['id']
 def tag_recall(self):return self.action(None,send=[],tag_in=True,request='tag-recall')
 def release(self,p=None,pos=(4,1),request='release'):
  return P.act(self.e,self.a,send=[(p or self.q,pos)],request_id=request,reason='actual next containing-ball release')
 def schedule(self,actors=None):
  self.close()
  if self.e.round_start_seconds is not None:self.e.end_round()
  actors=actors or [self.a,self.b,self.p,self.t]
  S.prepare(self.e,actors,source='gm/juggler-native-schedule')
  self.e.start_round(actors);self.e.start_of_turn(self.a)

 def test_seven_independent_speed_acquisitions_no_auto_children_exact_replay_and_restore(self):
  before=self.a.stats['spe'];self.family(J.CLASS)
  self.assertEqual(self.a.stats['spe'],before+1);self.assertEqual(len(J.records(self.a,active=True)),1);self.assertFalse(J.acquired(self.a,J.BOUNCE))
  for u in J.FEATURES:self.family(u)
  self.assertEqual(self.a.stats['spe'],before+7);self.assertEqual(len(J.records(self.a,active=True)),7)
  self.acquire(J.TAG);self.assertEqual(self.a.stats['spe'],before+7);self.restore();self.valid()

 def test_quick_switch_requires_either_novice_but_juggler_requires_both(self):
  self.setup(acro=3,guile=2);self.family(J.QUICK);self.reject(lambda:self.acquire(J.CLASS),'skill')
  self.setup(acro=2,guile=3);self.family(J.QUICK);self.reject(lambda:self.acquire(J.CLASS),'skill')
  self.setup(acro=2,guile=2);self.reject(lambda:self.acquire(J.QUICK),'skill')
  self.setup(acro=3,guile=3);self.reject(lambda:self.acquire(J.CLASS),'parent');self.family(J.CLASS);self.valid()

 def test_parent_rank_nonranked_and_source_selection_are_actual_acquisition_contracts(self):
  self.setup(acro=3,guile=3);self.family(J.CLASS);self.reject(lambda:self.acquire(J.ROUND),'skill')
  self.setup(acro=4,guile=3);self.family(J.ROUND);self.reject(lambda:self.acquire(J.TAG),'skill')
  self.setup(acro=5,guile=3);self.family(J.TAG);self.reject(lambda:self.acquire(J.FIRST),'skill')
  self.reject(lambda:T.acquire_static(self.e,self.a,J.BOUNCE,rank=2,acquisition_request_id='invented-rank'),'Ranked')
  self.reject(lambda:self.acquire(J.BOUNCE,selection={'edition':'imaginary'}),'source')

 def test_quick_switch_own_turn_one_ap_and_no_standard_or_shift_payment(self):
  self.family(J.CLASS);self.begin();before=AP.available(self.a);budget=deepcopy(self.a.budget)
  r=self.action();self.assertEqual(AP.available(self.a),before-1);self.assertEqual(self.a.budget,budget)
  self.assertEqual(self.action(),r);self.assertEqual(AP.available(self.a),before-1)
  self.assertFalse(self.p.on_field);self.assertTrue(self.q.on_field);self.assertEqual(r['payment']['kind'],'free');self.valid()

 def test_quick_switch_without_class_still_costs_two_ap_and_needs_real_acquisition(self):
  self.begin();self.reject(lambda:self.action(),'acquired');self.close();self.e.end_round();self.e.end_encounter()
  self.family(J.QUICK);self.begin();before=AP.available(self.a);self.action();self.assertEqual(AP.available(self.a),before-2)

 def test_quick_switch_opponent_actual_release_restores_suspended_turn_and_budget(self):
  self.family(J.CLASS);self.begin(self.b)
  P.act(self.e,self.b,send=[(self.u,(13,1))],request_id='rival-send',reason='actual rival ball release')
  before=deepcopy(self.b.budget);self.action(event_id=self.last_event());self.assertIs(self.e._active_turn_actor,self.b)
  self.assertEqual(self.b.budget,before);self.assertFalse(I.frame(self.e));self.valid()

 def test_quick_switch_own_native_faint_trigger_and_recursive_release_rejection(self):
  self.family(J.CLASS);self.family(J.CLASS,self.b);self.begin(self.b)
  self.e.take_damage(self.p,self.p.hp+50)
  self.action(event_id=self.last_event('faint'));self.assertTrue(self.q.on_field);self.valid()
  self.setup();self.family(J.CLASS);self.family(J.CLASS,self.b);self.begin(self.b)
  self.e.gm.set_position(self.b,(14,1),reason='actual rival within eight metre recall beam')
  J.act(self.e,self.b,recall=[self.t],send=[(self.u,(6,1))],source_id=J.QUICK,request_id='rival-quick',reason='actual rival Quick Switch')
  self.reject(lambda:self.action(event_id=self.last_event()),'recursive|trigger|opposing')

 def test_quick_switch_rejects_stale_trigger_and_invalid_party_atomically(self):
  self.family(J.CLASS);self.begin(self.b);P.act(self.e,self.b,send=[(self.u,(13,1))],request_id='rival-send',reason='actual rival release')
  event=self.last_event();self.move(self.b,target=self.u)
  self.reject(lambda:self.action(event_id=event),'immediate')
  self.turn(self.a);self.reject(lambda:self.action(send=[(self.q,(6,1))]),'destination|occupied')

 def test_released_pokemon_only_round_initiative_bonus_and_exact_ordinary_clock(self):
  self.family(J.CLASS);self.begin();spe=self.q.stats['spe'];trainer=self.a.stats['spe'];before=self.e.initiative_value(self.q).value
  self.action();self.assertEqual(self.e.initiative_value(self.q).value,before+10)
  self.assertEqual((self.q.stats['spe'],self.a.stats['spe']),(spe,trainer));self.assertEqual(self.q.turns_taken,0)
  self.begin();self.assertEqual(self.e.initiative_value(self.q).value,before);self.valid()

 def test_native_schedule_replaces_binding_reorders_unspent_bonus_and_no_extra_turn(self):
  self.family(J.CLASS);self.schedule();slot=self.p.entity_id;self.action()
  self.assertIs(getattr(self.e,S.KEY)['slots'][slot]['actor'],self.q)
  order=[s['slot'] for s in getattr(self.e,S.KEY)['steps']]
  self.assertLess(order.index(slot),order.index(self.t.entity_id));self.valid()
  self.close();self.e.start_of_turn(self.b);self.close();self.e.start_of_turn(self.q);self.close()
  self.reject(lambda:self.e.start_of_turn(self.q),'next|consumed|already|turn')

 def test_round_trip_requires_completed_whole_move_then_free_one_ap_and_trapped_exception(self):
  self.family(J.ROUND);self.begin(self.p);self.reject(lambda:self.action(J.ROUND,completion_id='unreturned'),'completed')
  self.e.apply_status(self.p,'수렁');row=self.move();before=AP.available(self.a);budget=deepcopy(self.p.budget)
  self.action(J.ROUND,completion_id=row['id']);self.assertEqual(AP.available(self.a),before-1)
  self.assertEqual(self.p.budget,budget);self.assertEqual(self.p.move_uses['move/물대포'],1);self.assertTrue(self.q.on_field);self.valid()

 def test_round_trip_wrong_actor_or_later_action_cannot_reuse_old_move(self):
  self.family(J.ROUND);self.begin(self.p);row=self.move()
  self.reject(lambda:self.action(J.ROUND,recall=[self.t],completion_id=row['id']),'owned|Move|owner')
  __import__('turn').spend(self.e,self.p,'free','actual intervening Free action')
  self.reject(lambda:self.action(J.ROUND,completion_id=row['id']),'completed')

 def test_round_trip_open_schedule_owner_closes_once_then_rebinds_consumed_slot(self):
  self.family(J.ROUND);self.schedule();self.close();self.e.start_of_turn(self.b);self.close();self.e.start_of_turn(self.p)
  row=self.move();self.action(J.ROUND,completion_id=row['id']);self.assertFalse(self.p.on_field)
  self.close();self.assertIs(getattr(self.e,S.KEY)['slots'][self.p.entity_id]['actor'],self.q)
  self.assertEqual(getattr(self.e,S.KEY)['slots'][self.p.entity_id]['turn'],'closed');self.valid()

 def test_tag_in_captures_before_reset_and_only_next_real_release_consumes_stages(self):
  self.family(J.TAG);self.begin();self.e.change_stage(self.p,'atk',3);self.e.change_stage(self.p,'def',-2)
  self.tag_recall();self.assertEqual((self.p.stages['atk'],self.p.stages['def']),(0,0));self.assertEqual(J.state(self.a)['pending_tag']['stages']['atk'],3)
  self.restore();self.release();self.assertEqual((self.q.stages['atk'],self.q.stages['def']),(3,-2));self.assertNotIn('pending_tag',J.state(self.a))
  self.begin();self.release(self.z,pos=(5,1),request='later');self.assertEqual(self.z.stages['atk'],0);self.valid()

 def test_tag_in_actual_round_trip_recall_no_fake_baton_move_or_duplicate_payment(self):
  self.family(J.TAG);self.begin(self.p);self.e.change_stage(self.p,'spe',2);row=self.move();before=AP.available(self.a)
  self.action(J.ROUND,completion_id=row['id'],tag_in=True);self.assertEqual(AP.available(self.a),before-2)
  self.assertEqual(self.q.stages['spe'],2);self.assertNotIn(COATS.BATON,self.p.move_uses);self.assertEqual(len(self.e._move_completions),1);self.valid()

 def test_tag_in_same_coat_instance_origin_and_future_holder_turn_after_json(self):
  self.family(J.TAG);self.begin(self.p);self.move(mid='move/아쿠아링',target=self.p)
  original=COATS.live(self.p)[0];uid=original['id'];origin=original[E.KEY]['origin_actor_id']
  self.turn(self.a);self.tag_recall();self.restore();self.release();record=COATS.live(self.q)[0]
  self.assertEqual((record['id'],record[E.KEY]['origin_actor_id']),(uid,origin));self.assertEqual(record[E.KEY]['ownership'][-1]['source'],J.TAG)
  self.assertFalse(COATS.live(self.p));self.begin(self.q);self.valid()

 def test_tag_in_same_source_coat_collision_rejects_next_release_without_new_policy(self):
  self.family(J.TAG);self.begin(self.p);self.move(mid='move/아쿠아링',target=self.p)
  self.close();self.e.gm.send_out(self.q,pos=(4,1),reason='actual earlier field entry');self.begin(self.q);self.move(self.q,'move/아쿠아링',self.q)
  self.e.gm.recall(self.q,reason='actual reserve with live Coat');self.turn(self.a);self.tag_recall()
  self.reject(lambda:self.release(),'composition');self.assertIn('pending_tag',J.state(self.a));self.assertFalse(self.q.on_field)

 def test_tag_in_pending_has_no_invented_scene_expiry_and_cannot_be_replaced(self):
  # ch07:237 ends combat stages; the next-release reservation itself remains.
  self.family(J.TAG);self.begin();self.e.change_stage(self.p,'spa',2);self.tag_recall();self.close();self.e.end_round();self.e.end_encounter();self.restore()
  self.assertIn('pending_tag',J.state(self.a));self.begin();self.release();self.assertEqual(self.q.stages['spa'],0);self.valid()

 def test_tag_in_passes_actual_bound_stratagem_issuer_binding_and_native_consumer(self):
  import stat_ace as A,class_passive_combat as CP
  self.family(J.TAG)
  for u in (A.CLASS,A.LINK,A.TRAINING,A.STRATAGEM):T.acquire_static(self.e,self.a,u,branch='atk',acquisition_request_id='actual-stat/'+u)
  self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual Stratagem Order communication')
  self.begin();self.e.change_stage(self.p,'atk',1);A.activate(self.e,self.a,self.p,'atk')
  instance=CP._state(self.p)['sustains'][A.STRATAGEM]['instance'];bindings=AP.ActionPointAccount(self.a).identified_bindings()
  self.begin();self.tag_recall();self.release();self.assertEqual(CP._state(self.q)['sustains'][A.STRATAGEM]['instance'],instance)
  self.assertEqual(AP.ActionPointAccount(self.a).identified_bindings(),bindings);self.assertFalse(CP._state(self.p)['sustains'])
  self.assertEqual(A.stratagem_bonus(self.e,self.q,'critical',self.rules.move('move/몸통박치기')),1);self.restore();self.valid()

 def test_tag_in_lock_on_user_endpoint_moves_and_next_real_attack_consumes_once(self):
  self.family(J.TAG);self.begin(self.p);self.move(mid=J.LOCK,target=self.p);self.assertTrue(J.lock_on(self.e,self.p,self.p))
  self.turn(self.a);self.tag_recall();self.release();self.assertTrue(J.lock_on(self.e,self.q,self.q));self.assertFalse(J.lock_on(self.e,self.p,self.p))
  self.begin(self.q);no_check=self.move(self.q,'move/아쿠아링',self.q)
  self.assertFalse(no_check['juggler_accuracy_required'][self.q.entity_id]);self.assertTrue(J.lock_on(self.e,self.q,self.q));self.restore()
  self.begin(self.q);rng=self.e.rng.getstate()
  with patch.object(Engine,'d20',side_effect=AssertionError('actual consenting Trick has no Accuracy Check')):
   self.e.use_move_on(self.q,self.q,'move/트릭',self.e.everyone,equipment_options={'targets':[self.q,self.a],'consenting':[self.a]})
  trick=list(self.e._move_completions.values())[-1]
  self.assertEqual(trick['juggler_accuracy_required'],{self.q.entity_id:False,self.a.entity_id:False})
  self.assertEqual(self.e.rng.getstate(),rng);self.assertTrue(J.lock_on(self.e,self.q,self.q));self.restore()
  self.begin(self.q)
  with patch.object(Engine,'d20',return_value=2):self.e.use_move(self.q,self.q,'move/물대포',set_damage=True)
  self.assertFalse(J.lock_on(self.e,self.q,self.q));self.valid()

 def test_tag_in_next_legal_same_holder_release_preserves_identity_and_consumes_once(self):
  self.family(J.TAG);self.begin(self.p);self.move(mid='move/아쿠아링',target=self.p)
  uid=COATS.live(self.p)[0]['id'];self.turn(self.a);self.e.change_stage(self.p,'atk',2);self.tag_recall()
  self.close();self.e.end_round();self.restore();self.begin();self.release(self.p,pos=(3,1))
  self.assertEqual(self.p.stages['atk'],2);self.assertEqual(COATS.live(self.p)[0]['id'],uid)
  self.assertNotIn('pending_tag',J.state(self.a));self.assertEqual(J.state(self.a)['tag_history'][-1]['recipient_id'],self.p.entity_id)
  self.begin();self.release(self.q,request='later-other-release');self.assertEqual(self.q.stages['atk'],0);self.assertFalse(COATS.live(self.q));self.restore();self.valid()

 def test_tag_in_lock_on_target_endpoint_preserves_original_user_relation(self):
  self.family(J.TAG);self.begin(self.t);self.move(self.t,J.LOCK,self.p)
  self.turn(self.a);self.tag_recall();self.release();self.assertTrue(J.lock_on(self.e,self.t,self.q));self.assertFalse(J.lock_on(self.e,self.t,self.p));self.restore();self.valid()

 def test_core_emergency_release_two_ap_shift_interrupt_and_suspended_turn_restore(self):
  self.family(J.EMERGENCY);self.begin(self.b);before=AP.available(self.a);budget=deepcopy(self.b.budget)
  self.action(J.EMERGENCY,recall=[]);self.assertEqual(AP.available(self.a),before-2);self.assertIs(self.e._active_turn_actor,self.b);self.assertEqual(self.b.budget,budget)
  self.turn(self.a);self.assertEqual(self.a.budget['shift'],0);self.assertEqual(self.a.budget['standard'],1);self.valid()

 def test_local_csv_emergency_release_one_ap_free_once_per_actual_turn(self):
  self.family(J.CLASS);self.acquire(J.EMERGENCY,selection={'edition':'local_csv'});self.begin(self.b)
  before=AP.available(self.a);self.action(J.EMERGENCY,recall=[]);self.assertEqual(AP.available(self.a),before-1)
  self.reject(lambda:self.action(J.EMERGENCY,recall=[],send=[(self.z,(5,1))],request='repeat'),'frequency')
  self.turn(self.a);self.assertEqual(self.a.budget['shift'],1);self.assertEqual(J.acquired(self.a,J.EMERGENCY)['snapshot']['edition'],'local_csv');self.valid()

 def test_emergency_source_selection_is_immutable_and_insufficient_ap_does_not_release(self):
  self.family(J.EMERGENCY);self.reject(lambda:self.acquire(J.EMERGENCY,selection={'edition':'local_csv'}),'selection')
  self.begin(self.b);AP.spend(self.a,AP.available(self.a));self.reject(lambda:self.action(J.EMERGENCY,recall=[]),'AP');self.assertFalse(self.q.on_field)

 def test_first_blood_current_slot_native_move_consumes_one_pokemon_turn_without_clock(self):
  self.family(J.FIRST);self.schedule([self.a,self.b,self.q,self.t]);self.release()
  serial=self.q.custom_conditions.get('combat_turn_serial',0);event=self.last_event()
  with patch.object(Engine,'d20',return_value=18):J.first_blood(self.e,self.a,self.q,self.t,'move/물대포',event_id=event,request_id='first-current',set_damage=True)
  loan=next(iter(getattr(self.e,I.KEY)['loans'].values()));self.assertEqual(loan['due_round'],self.e.round_no)
  self.assertEqual(self.q.custom_conditions.get('combat_turn_serial',0),serial);self.assertEqual(self.q.move_uses['move/물대포'],1)
  self.close();self.e.start_of_turn(self.b);self.close();I.settle(self.e)
  self.assertEqual(getattr(self.e,S.KEY)['slots'][self.q.entity_id]['turn'],'closed');self.valid()

 def test_first_blood_next_round_uses_league_switch_debt_and_same_owner_command_pool(self):
  self.setup(mode='league');self.family(J.FIRST);self.schedule();P.act(self.e,self.a,recall=[self.p],send=[(self.q,(3,1))],request_id='league-switch',reason='actual voluntary League switch')
  self.assertIs(getattr(self.e,S.KEY)['slots'][self.p.entity_id]['actor'],self.q)
  with patch.object(Engine,'d20',return_value=18):J.first_blood(self.e,self.a,self.q,self.t,'move/물대포',event_id=self.last_event(),request_id='first-next',set_damage=True)
  loan=next(iter(getattr(self.e,I.KEY)['loans'].values()));self.assertEqual(loan['due_round'],self.e.round_no+1);self.assertEqual(loan['trainer_id'],self.a.entity_id);self.restore();self.valid()
  serial=self.q.custom_conditions.get('combat_turn_serial',0)
  self.close();self.e.start_of_turn(self.b);self.close();S.skip_switch_locked(self.e,self.q);self.e.start_of_turn(self.t);self.close();self.e.end_round()
  slots=getattr(self.e,S.KEY)['slots'];actors=[row['actor'] for row in slots.values()]
  S.prepare(self.e,actors,source='gm/juggler-next-round-native-schedule',bindings=[{'slot':key,'actor_id':row['actor'].entity_id,'role':row['role']} for key,row in slots.items()])
  self.e.start_round(actors);self.e.start_of_turn(self.a);self.close();self.e.start_of_turn(self.b);self.close()
  self.e.start_of_turn(self.t);self.close();I.settle(self.e)
  self.assertEqual(self.q.custom_conditions.get('combat_turn_serial',0),serial)
  self.assertEqual(I.command_debts(self.e,self.a),1);self.assertEqual(next(iter(getattr(self.e,I.KEY)['loans'].values()))['status'],'settled')
  self.e.gm.send_out(self.p,pos=(5,2),reason='actual same-owner alternative on the field before its command-pool check')
  self.reject(lambda:P.require_turn(self.e,self.p),'ordinary turn');self.restore();self.valid()

 def test_first_blood_scene_limit_stale_release_wrong_pokemon_and_future_duplicate_reject(self):
  self.family(J.FIRST);self.schedule([self.a,self.b,self.q,self.t]);self.release();event=self.last_event()
  self.reject(lambda:J.first_blood(self.e,self.a,self.z,self.t,'move/물대포',event_id=event,request_id='wrong'),'owned|release')
  with patch.object(Engine,'d20',return_value=18):J.first_blood(self.e,self.a,self.q,self.t,'move/물대포',event_id=event,request_id='first',set_damage=True)
  self.reject(lambda:J.first_blood(self.e,self.a,self.q,self.t,'move/물대포',event_id=event,request_id='repeat'),'frequency|immediate')

 def test_bounce_capture_before_and_after_uses_one_quantity_body_stock_and_function_coordinates(self):
  for timing in ('before','after'):
   with self.subTest(timing=timing):
    self.setup(wild=True);self.family(J.BOUNCE);self.a.spec['items']['몬스터볼']=1;self.begin()
    landing=(6,1) if timing=='before' else (3,1)
    choice={'landing':landing,'direction':(1,0),'timing':timing,'reason':'actual observed first ball impact'}
    self.e.throw_ball(self.a,self.t,bounce=choice,fixed_accuracy=20,fixed_capture=20)
    record=self.a.spec['capture_attempts']['capture-1'];obj=self.e._physical_objects[record['physical_instance_id']]
    self.assertEqual(self.a.spec['items']['몬스터볼'],0);self.assertEqual(len(self.e._physical_objects),1);self.assertTrue(record['bounce_done'])
    order=record['function_order'];self.assertLess(order.index('capture'),order.index('bounce')) if timing=='before' else self.assertLess(order.index('bounce'),order.index('capture'))
    self.assertEqual(record['bounce']['endpoint'],[landing[0]+3,1]);self.assertEqual(record['physical_instance_id'],obj['id']);self.restore();self.valid()

 def test_bounce_missing_landing_unknown_direction_and_wrong_function_target_reject_atomically(self):
  self.setup(wild=True);self.family(J.BOUNCE);self.a.spec['items']['몬스터볼']=1;self.begin()
  for choice in ({'landing':(30,8),'direction':(1,0),'timing':'after','reason':'unknown ground'}, {'landing':(3,1),'direction':(0,0),'timing':'after','reason':'no direction'}, {'landing':(4,1),'direction':(1,0),'timing':'after','reason':'target not endpoint'}):
   self.reject(lambda:self.e.throw_ball(self.a,self.t,bounce=choice,fixed_accuracy=20,fixed_capture=20),'terrain|direction|position')

 def test_bounce_release_before_and_after_keeps_containing_ball_identity_and_pokemon_position(self):
  import capture_specialist as CS
  for timing in ('before','after'):
   with self.subTest(timing=timing):
    self.setup();self.family(J.BOUNCE)
    W.register_object(self.e,'actual-containing-ball',location=W.location_of(self.a),reason='actual owned ball body',kind='item_instance',item_rule_id=__import__('missed_ball_body').ball_rule(self.e,'몬스터볼'),owner_id=self.a.entity_id)
    CS.observe_release_ball(self.e,self.a,self.q,'actual-containing-ball',reason='actual reserve containing ball')
    self.begin();choice={'landing':(6,2),'direction':(1,0),'timing':timing,'reason':'actual observed ground landing before selected release'};pos=(6,2) if timing=='before' else (9,2)
    options={'ball_id':'actual-containing-ball','target_id':None,'curve_ball':False,'bounce':choice}
    row=P.act(self.e,self.a,send=[(self.q,pos)],request_id='bounce-release',reason='actual ball release',release_throw=options)
    ball=self.e._physical_objects['actual-containing-ball'];self.assertEqual(self.q.pos,pos);self.assertNotIn('contained_pokemon',ball);self.assertEqual(row['release_throw']['physical_instance_id'],ball['id'])
    self.assertEqual(W.location_of(ball)['cell'],tuple(row['release_throw']['bounce']['endpoint']));self.valid()

 def test_existing_juggling_show_native_introduction_owner_remains_the_consumer(self):
  import contest_features as CF
  self.family(J.SHOW);self.assertTrue(CF.owned(self.a,J.SHOW));self.assertEqual(CF.introduction_bonus_dice(self.e,self.a,self.p,J.SHOW),3)

 def test_gm_actual_release_consumes_tag_and_grants_only_current_round_pokemon_initiative(self):
  self.family(J.TAG);self.begin();self.e.change_stage(self.p,'atk',2);self.tag_recall()
  self.e.gm.send_out(self.q,pos=(3,1),reason='actual next observed containing-ball release')
  self.assertEqual(self.q.stages['atk'],2);self.assertNotIn('pending_tag',J.state(self.a))
  self.assertEqual(self.e.initiative_value(self.q).value,self.q.stats['spe']+10);self.restore();self.valid()

 def test_real_baton_pass_uses_the_same_stage_stratagem_and_lock_on_receiver_without_tag_acquisition(self):
  self.p.moves.append(COATS.BATON);self.begin(self.p);self.e.change_stage(self.p,'atk',2);self.move(mid=J.LOCK)
  self.begin(self.p);COATS.select_transfer(self.e,self.p,self.q,reason='actual Baton Pass replacement')
  self.move(mid=COATS.BATON,target=self.p)
  self.assertFalse(self.p.on_field);self.assertTrue(self.q.on_field);self.assertEqual(self.q.stages['atk'],2)
  self.assertTrue(J.lock_on(self.e,self.q,self.t));self.assertFalse(J.acquired(self.a,J.TAG));self.assertEqual(self.p.move_uses[COATS.BATON],1);self.valid()

 def test_actual_party_round_trip_tag_in_updates_battle_contest_slot_without_recall_voltage_or_duplicate_action(self):
  import battle_contest as BC
  from contest import ContestEngine,ContestRules
  self.family(J.TAG);v=self.actor('third-foe','pokemon',(14,3),5,owner=self.b,side='foe',field=False)
  PARTY.configure(self.e,self.b,mode='standard',reason='actual equal Battle Contest team',roster=[self.t,self.u,v],storage={'kind':'center','id':'rival-center'})
  c=ContestEngine(ContestRules(ROOT),seed=831)
  intros={a.entity_id:c.contestant_from_combatants(self.e,p,a,'교활',{}) for a,p in ((self.a,self.p),(self.b,self.t))}
  BC.create(self.e,c,[self.a,self.b],[[self.p,self.q,self.z],[self.t,self.u,v]],[[self.p],[self.t]],'근사함',intros,contest_id='juggler-contest',smart_stat_policy='ptu-original-special-defense')
  BC.begin_round(self.e,'juggler-contest');self.e.start_of_turn(self.p,initiative_count=30)
  row=self.move();occurrence=self.a.spec[BC.KEY]['juggler-contest'];occurrence['pokemon'][self.p.entity_id]['excitement']=4
  before=AP.available(self.a);self.action(J.ROUND,completion_id=row['id'],tag_in=True)
  occurrence=self.a.spec[BC.KEY]['juggler-contest'];self.assertEqual(occurrence['sides'][0]['active'],[self.q.entity_id])
  self.assertEqual(occurrence['pokemon'][self.p.entity_id]['excitement'],4);self.assertEqual(AP.available(self.a),before-2)
  self.assertEqual(self.p.budget['standard'],0);BC.validate(self.e,'juggler-contest');self.valid()

 def test_csv132_and136_are_selected_actual_acquisitions_with_independent_speed_and_next_release(self):
  self.family(J.QUICK);before=self.a.stats['spe'];self.acquire(J.CLASS,selection={'edition':'local_csv'})
  self.family(J.ROUND);self.acquire(J.TAG,selection={'edition':'local_csv'})
  self.assertEqual(self.a.stats['spe'],before+3)
  self.assertEqual(J.acquired(self.a)['snapshot']['source']['record'],132)
  self.assertEqual(J.acquired(self.a,J.TAG)['snapshot']['source']['record'],136)
  self.begin();self.e.change_stage(self.p,'def',2);self.tag_recall();self.restore();self.release()
  self.assertEqual(self.q.stages['def'],2);self.assertEqual(self.e.initiative_value(self.q).value,self.q.stats['spe']+10);self.valid()

 def test_bounce_and_actual_csv_curve_share_ball_damage_standard_and_native_capture(self):
  import capture_techniques as CT,capture_specialist as CS
  self.setup(wild=True);self.family(J.BOUNCE)
  CT.acquire(self.e,self.a,CT.CLASS,acquisition_request_id='actual-curve-with-bounce',selected_techniques=[{'technique':'커브볼','source_variant':CS.CSV},{'technique':'작업 도구'}],rank=0,lifecycle_policy=T.LIFECYCLE_WHILE_OWNED)
  self.a.spec['items']['몬스터볼']=1;self.begin();hp=self.t.hp
  choice={'landing':(3,1),'direction':(1,0),'timing':'after','reason':'actual first landing followed by capture impact'}
  self.e.throw_ball(self.a,self.t,curve_ball=True,bounce=choice,fixed_accuracy=20,fixed_capture=20)
  row=self.a.spec['capture_attempts']['capture-1'];self.assertIn('curve_damage',row);self.assertLess(self.t.hp,hp)
  self.assertEqual(self.a.budget['standard'],0);self.assertEqual(self.a._action_history.count('standard'),1)
  self.assertEqual(len(self.e._physical_objects),1);self.assertEqual(self.a.spec['items']['몬스터볼'],0);self.restore();self.valid()

 def test_core_missed_ball_bounce_and_csv_single_bounce_limit_keep_separate_authorities(self):
  import missed_ball_body as B
  for edition in ('core','local_csv'):
   self.setup(wild=True);self.family(J.CLASS);self.acquire(J.BOUNCE,selection={'edition':edition});self.a.spec['items']['몬스터볼']=1;self.begin()
   choice={'landing':(6,1),'direction':(1,0),'timing':'before','reason':'actual original ground impact'}
   self.e.throw_ball(self.a,self.t,bounce=choice,fixed_accuracy=1,fixed_capture=20)
   B.observe_ground(self.e,self.a,attempt_id='capture-1',cell=(7,1),intact=True,reason='actual missed ball observed behind original target')
   J.bounce_missed(self.e,self.a,attempt_id='capture-1')
   if edition=='local_csv':self.reject(lambda:J.bounce_missed(self.e,self.a,attempt_id='capture-1'),'already bounced')
   else:self.assertEqual(J.bounce_missed(self.e,self.a,attempt_id='capture-1')['endpoint'],[13,1])
   self.assertEqual(self.a.spec['items']['몬스터볼'],0);self.assertEqual(len(self.e._physical_objects),1);self.valid()

 def test_tag_snapshot_tamper_rejects_codec_and_naturally_ended_stratagem_is_not_resurrected(self):
  import stat_ace as A,class_passive_combat as CP
  self.family(J.TAG)
  for u in (A.CLASS,A.LINK,A.TRAINING,A.STRATAGEM):T.acquire_static(self.e,self.a,u,branch='atk',acquisition_request_id='expiry-stat/'+u)
  self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual sustained Order communication')
  self.begin();self.e.change_stage(self.p,'atk',2);A.activate(self.e,self.a,self.p,'atk');self.begin();self.tag_recall()
  pending=J.state(self.a)['pending_tag'];pending['stages']['atk']+=1
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  pending['stages']['atk']-=1;self.close();self.e.end_round();self.e.end_encounter();self.restore();self.begin();self.release()
  self.assertEqual(self.q.stages['atk'],0);self.assertFalse((CP._state(self.q) or {}).get('sustains'));self.assertFalse(AP.ActionPointAccount(self.a).identified_bindings());self.valid()

 def test_tag_lock_snapshot_forged_endpoint_and_transfer_history_cannot_restore(self):
  self.family(J.TAG);self.begin(self.p);self.move(mid=J.LOCK);self.turn(self.a);self.tag_recall();self.release();self.restore()
  row=J.state(self.p)['lock_on'][0];old=row['target_id'];row['target_id']=self.z.entity_id
  with self.assertRaises(CODEC.StateCodecError):self.e.export_state()
  row['target_id']=old;self.valid()

 def test_actual_paid_tag_recall_pending_pursuit_restores_and_resumes_once(self):
  import combat_move_reactions as CMR,passive_events as PASS
  self.family(J.TAG);self.b.moves.append(CMR.PURSUIT);self.e.gm.set_position(self.b,(4,2),reason='actual adjacent Pursuit user')
  defender=self.actor('actual-defender','trainer',(3,2),80);self.begin()
  self.e.watch_move_defense(self.p,[{'actor_id':defender.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual optional Pursuit defense')
  CMR.arm(self.e,self.b,CMR.PURSUIT);self.e.change_stage(self.p,'def',2);before=AP.available(self.a)
  with patch.object(Engine,'d20',return_value=15),self.assertRaises(PASS.PassiveEventPending):self.tag_recall()
  event=self.e._passive_pending;self.assertEqual(AP.available(self.a),before-1);self.assertTrue(self.p.on_field);self.assertNotIn('pending_tag',J.state(self.a));self.restore()
  defender=W.actor_index(self.e)[defender.entity_id];self.e.choose_move_defense(event,defender,use=False,reason='actual declined optional interception')
  self.assertFalse(self.p.on_field);self.assertIn('pending_tag',J.state(self.a));self.assertEqual(AP.available(self.a),before-1)
  self.release();self.assertEqual(self.q.stages['def'],2);self.assertEqual(self.b.move_uses[CMR.PURSUIT],1);self.restore();self.valid()

 def test_tag_captured_coat_actual_native_removal_does_not_resurrect_or_block_release(self):
  self.e.gm.set_move(self.a,'move/안개제거',reason='actual learned source Coat-removal Move')
  self.family(J.TAG);self.begin(self.p);self.move(mid='move/아쿠아링',target=self.p)
  coat=COATS.live(self.p)[0]['id'];self.turn(self.a);self.e.change_stage(self.p,'def',2);self.tag_recall()
  self.assertEqual(J.state(self.a)['pending_tag']['coats'],[coat]);self.move(self.a,'move/안개제거',self.a)
  self.assertEqual(self.p.spec[COATS.HISTORY][-1][E.KEY]['end_event']['source'],'move/안개제거');self.restore()
  self.assertFalse(COATS.live(self.p));self.begin();self.release();self.assertFalse(COATS.live(self.q));self.assertEqual(self.q.stages['def'],2);self.restore();self.valid()

 def test_tag_pre_recall_lock_relation_snapshot_excludes_later_actual_move(self):
  self.family(J.TAG);self.begin(self.p);original=self.move(mid=J.LOCK);self.turn(self.a);self.tag_recall()
  captured=deepcopy(J.state(self.a)['pending_tag']['locks']);self.assertEqual([r['completion_id'] for r in captured],[original['id']])
  self.turn(self.t);later=self.move(self.t,J.LOCK,self.a);self.assertNotEqual(later['id'],original['id'])
  self.assertEqual(J.state(self.a)['pending_tag']['locks'],captured);self.begin(self.a);self.release()
  self.assertTrue(J.lock_on(self.e,self.q,self.t));self.assertTrue(J.lock_on(self.e,self.t,self.a));self.restore();self.valid()

 def test_first_blood_actual_paid_move_defense_pending_restores_and_finishes_without_second_payment(self):
  import passive_events as PASS
  self.family(J.FIRST);self.e.gm.set_position(self.b,(6,2),reason='actual adjacent defensive participant')
  self.schedule([self.a,self.b,self.q,self.t]);self.release();before=AP.available(self.a);serial=self.q.custom_conditions.get('combat_turn_serial',0)
  self.e.watch_move_defense(self.t,[{'actor_id':self.b.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual optional First Blood defense')
  with patch.object(Engine,'d20',return_value=18),self.assertRaises(PASS.PassiveEventPending):
   J.first_blood(self.e,self.a,self.q,self.t,'move/물대포',event_id=self.last_event(),request_id='first-pending',set_damage=True)
  event=self.e._passive_pending;self.assertEqual(self.q.budget['standard'],0);self.assertEqual(AP.available(self.a),before);self.restore()
  self.e.choose_move_defense(event,self.b,use=False,reason='actual declined optional defense');self.e.finish_initiative_reaction()
  self.assertIs(self.e._active_turn_actor,self.a);self.assertEqual(self.q.move_uses['move/물대포'],1)
  self.assertEqual(self.q.custom_conditions.get('combat_turn_serial',0),serial);self.assertEqual(AP.available(self.a),before)
  self.assertNotIn('first_request',J.state(self.a));self.restore();self.valid()

 def test_league_native_open_turn_marker_does_not_admit_forged_or_other_custom_state(self):
  import league_runtime as L
  self.begin();actors={'owner':self.a}
  self.assertFalse(any('open-turn marker' in issue for issue in L._interaction_issues(self.e,actors)))
  self.a.custom_conditions['blessing_ignore_turn_open']=1
  self.assertTrue(any('open-turn marker' in issue for issue in L._interaction_issues(self.e,actors)))
  self.a.custom_conditions['blessing_ignore_turn_open']=True;self.a.custom_conditions['unreviewed_effect']=True
  self.assertTrue(any('unsupported custom_conditions' in issue for issue in L._interaction_issues(self.e,actors)))
  self.a.custom_conditions.pop('unreviewed_effect');self.close();self.a.custom_conditions['blessing_ignore_turn_open']=True
  self.assertTrue(any('open-turn marker' in issue for issue in L._interaction_issues(self.e,actors)))
  self.a.custom_conditions.pop('blessing_ignore_turn_open');self.valid()

 def test_integrated_tag_payment_snapshot_alias_and_replay_have_one_native_owner(self):
  import native_switch_transfer as SWITCH
  self.family(J.TAG);self.begin();before=AP.available(self.a)
  result=self.tag_recall();use=self.a.spec[SWITCH.USES][-1]
  self.assertEqual(AP.available(self.a),before-1)
  self.assertIs(self.a.spec[SWITCH.TAG],use)
  self.assertIs(J.state(self.a)['pending_tag'],use['juggler_snapshot'])
  self.assertEqual(result['tag_payment']['consumed_recall'],use['recall_id'])
  self.assertEqual(self.tag_recall(),result);self.assertEqual(AP.available(self.a),before-1)
  self.restore();self.release();self.assertEqual(len(self.a.spec[SWITCH.USES]),1)
  self.assertIs(J.state(self.a)['tag_history'][-1],self.a.spec[SWITCH.USES][-1]['juggler_snapshot'])
  fresh=Rules(ROOT,ruleset='core');loaded=CODEC.load_engine(fresh,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.assertTrue(loaded.validate_state()['valid']);self.valid()

 def test_integrated_direct_party_tag_supports_deferred_same_holder_without_self_transfer(self):
  import native_switch_transfer as SWITCH
  self.family(J.TAG);self.begin();self.e.change_stage(self.p,'atk',3);before=AP.available(self.a)
  P.act(self.e,self.a,recall=[self.p],tag_in=True,request_id='direct-deferred-tag',reason='actual recall and later release')
  self.assertEqual(AP.available(self.a),before-1);self.restore();self.begin()
  self.release(self.p,pos=(3,1),request='same-owner-next-release')
  use=self.a.spec[SWITCH.USES][-1]
  self.assertEqual(use['phase'],'completed');self.assertEqual(use['incoming_id'],self.p.entity_id)
  self.assertEqual(use['transfer']['orders'],[]);self.assertEqual(use['transfer']['coats'],[])
  self.assertEqual(self.p.stages['atk'],3);self.assertNotIn(SWITCH.TAG,self.a.spec);self.valid()

 def test_integrated_prepaid_tag_rejects_unissued_party_context_and_double_selection(self):
  import native_switch_transfer as SWITCH
  self.family(J.TAG);self.begin()
  self.reject(lambda:SWITCH.select_tag_in(self.e,self.a,self.p,reason='forged payment',_prepaid_request='missing'),
      'actual paid party Tag In')
  self.reject(lambda:P.act(self.e,self.a,recall=[self.p],send=[(self.q,(3,1))],tag_in=True,
      feature={'source':None,'tag_in':True},request_id='double-tag',reason='duplicated representation'),'select Tag In once')

 def test_integrated_declared_rank_seven_keeps_actual_juggler_qualification(self):
  from examples.declared_skill_ranks import configure
  configure(self.rules)
  self.e.gm.set_skill(self.a,'곡예',7,reason='declared campaign seventh rank')
  self.e.gm.set_skill(self.a,'교활',7,reason='declared campaign seventh rank')
  self.family(J.FIRST)
  self.assertEqual(J.acquired(self.a,J.CLASS)['snapshot']['skills'],{'곡예':7,'교활':7})
  self.restore();self.valid()

 def test_integrated_tag_preserves_actual_commander_brace_binding_and_release(self):
  import commander as C,commander_orders as O
  self.family(J.TAG)
  T.acquire_static(self.e,self.a,C.CLASS,branch='feat/가디언-지시',acquisition_request_id='tag/commander')
  self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual Brace Order delivery')
  self.begin();original=self.e.use_general_order(self.a,self.p,O.BRACE);bindings=dict(self.a.ap_account.identified_bindings())
  self.begin();before=AP.available(self.a);self.tag_recall();self.release()
  current=O.live(self.e,self.q,O.BRACE)[0]
  self.assertEqual(current['id'],original['id']);self.assertEqual(current['issuer_id'],self.a.entity_id)
  self.assertEqual(dict(self.a.ap_account.identified_bindings()),bindings);self.assertEqual(AP.available(self.a),before-1)
  self.restore();self.turn(self.q);self.assertTrue(self.e.brace_for_impact(self.q));self.assertEqual(O.reduction(self.q),5)
  self.begin();O.release(self.e,self.a,self.q);self.assertFalse(self.a.ap_account.identified_bindings());self.valid()

 def test_integrated_commander_order_pending_and_started_turn_clocks_do_not_restart(self):
  import commander as C,commander_orders as O,native_switch_transfer as SWITCH
  for started in (False,True):
   with self.subTest(started=started):
    self.setup();self.family(J.TAG)
    T.acquire_static(self.e,self.a,C.CLASS,branch='feat/명사수-지시',acquisition_request_id='clock/commander')
    self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual Long Shot delivery')
    self.begin();row=self.e.use_general_order(self.a,self.p,O.LONG)
    if started:self.turn(self.p)
    SWITCH.select_tag_in(self.e,self.a,self.p,reason='actual Tag recall clock')
    self.e.gm.recall(self.p,reason='actual recorded recall');self.e.gm.send_out(self.q,pos=(3,1),reason='actual next release')
    moved=O.live(self.e,self.q,O.LONG)[0];self.assertEqual(moved['id'],row['id'])
    self.assertEqual(moved['turn_owner_id'],self.p.entity_id if started else self.q.entity_id)
    self.restore()
    if started:self.e.end_of_turn(self.p)
    else:self.turn(self.q);self.assertTrue(O.live(self.e,self.q,O.LONG));self.e.end_of_turn(self.q)
    self.assertFalse(O.live(self.e,self.q,O.LONG));self.valid()

 def test_integrated_english_baton_scope_does_not_pass_non_stratagem_commander_order(self):
  import commander as C,commander_orders as O,native_switch_policy as POLICY
  self.family(J.TAG)
  T.acquire_static(self.e,self.a,C.CLASS,branch='feat/명사수-지시',acquisition_request_id='scope/commander')
  self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual Long Shot delivery')
  choices=POLICY.choices(self.e);POLICY.choose(self.e,self.p,'english_1_05_stratagems',
      reason='actual complete English Baton source selected',decision_scope=choices['decision_scope'])
  self.begin();self.e.use_general_order(self.a,self.p,O.LONG);self.begin();self.tag_recall();self.release()
  self.assertFalse(O.live(self.e,self.q,O.LONG));self.valid()

 def mixed_schedule_fixture(self,*,rider_juggler=False,swarm=False,prepare=True):
  import control_mount as M,training_features as TRAIN
  if swarm:self.rules=Rules(ROOT,ruleset='all')
  self.setup(opponent_edges=['edge/탑승-기량'],opponent_feats=[TRAIN.AGILITY,TRAIN.FOCUSED,TRAIN.INSPIRED]);self.family(J.CLASS)
  P.configure(self.e,self.b,battle_mode='full_contact',command_limit=2,gm_id='gm/mixed-schedule',reason='GM explicitly admits the mount and one other Pokemon turn')
  self.acquire(M.RIDER,self.b);self.acquire(M.RIDE_AS_ONE,self.b)
  if rider_juggler:self.family(J.CLASS,self.b)
  if swarm:
   self.swarm_reserve=self.actor('swarm-successor','pokemon',(14,3),10,owner=self.b,side='foe',field=False)
   PARTY.configure(self.e,self.b,mode='standard',reason='actual Swarm replacement roster',roster=[self.t,self.u,self.swarm_reserve],storage={'kind':'center','id':'rival-center'})
  self.e.gm.set_stat(self.u,'spe',value=58 if swarm else 45,reason='actual unused mounted initiative')
  self.e.gm.set_stat(self.q,'spe',value=75 if swarm else 55,reason='actual reserve initiative before Juggler release')
  self.e.gm.send_out(self.u,pos=self.b.pos,reason='actual mount deployment')
  out=self.e.pokemon_activity(self.b,'mounting',target=self.u,phase='mount',gm_mountable=True)
  self.assertTrue(out['passed']);self.assertTrue(out['automatic']);self.assertIsNone(out['check'])
  if swarm:
   self.e.gm.set_stat(self.t,'spe',value=70,reason='actual leading Swarm initiative')
   self.e.gm.set_encounter_template(self.t,kind='swarm',total_bars=3,
     action_slots=[{'id':'native','initiative':70}],member_count_or_band='25_to_40',reason='actual selected Swarm template')
  if not prepare:return
  actors=[self.a,self.b,self.p,self.t,self.u]
  S.prepare(self.e,actors,source='gm/juggler-mounted-swarm-schedule');self.e.start_round(actors)

 def mixed_schedule_view(self):
  state=self.e._initiative_schedule;owner=self.e._active_turn_actor;suspended=I.suspended_owner(self.e)
  return deepcopy({'steps':state['steps'],'cursor':state['cursor'],'history':state.get('change_history'),
   'slots':[(key,row['actor'].entity_id,row['turn']) for key,row in state['slots'].items()],
   'records':[(row['slot'],row['actor'].entity_id,row['outcome']) for row in state['records']],
   'owner':None if owner is None else owner.entity_id,'suspended':None if suspended is None else suspended.entity_id,
   'budget':None if owner is None else owner.budget,
   'closures':[(row['actor'].entity_id,row['sequence']) for row in self.e._turn_closures]})

 def mixed_schedule_restore(self):
  before=self.mixed_schedule_view();owner=self.e._active_turn_actor
  self.e.gm.snapshot('mixed-transformations');self.e.end_of_turn(owner)
  self.e.gm.restore('mixed-transformations',reason='restore the actual open transformed slot')
  self.assertEqual(self.mixed_schedule_view(),before);self.restore()
  self.assertEqual(self.mixed_schedule_view(),before);self.valid()

 def test_party_reorder_then_mounted_exchange_restores_current_and_legacy_prefix(self):
  for legacy in (False,True):
   with self.subTest(legacy_prefix=legacy):
    self.mixed_schedule_fixture();self.e.start_of_turn(self.a)
    if legacy:
     # Actual native producers with only the historical append operation restored.
     with patch.object(S,'record_step_change',side_effect=lambda state,kind,row:state.setdefault(kind,[]).append(row)):
      self.action(request='legacy-before-mounted')
     self.assertNotIn('change_history',self.e._initiative_schedule);self.restore()
    else:self.action(request='party-before-mounted')
    self.close();self.assertEqual(S.status(self.e)['next']['actor_id'],self.q.entity_id)
    self.e.start_of_turn(self.q);self.close()
    self.assertEqual(S.status(self.e)['next']['actor_id'],self.b.entity_id)
    self.e.start_of_turn(self.u)
    state=self.e._initiative_schedule;history=state['change_history']
    self.assertEqual(history['events'][-1]['kind'],'mounted_exchanges')
    self.assertEqual(history['legacy_prefix']['party_orders'],int(legacy))
    self.assertIs(state['slots'][state['open_slot']]['actor'],self.u)
    self.mixed_schedule_restore();self.close()
    self.reject(lambda:self.e.start_of_turn(self.q),'next unconsumed|ordinary turn')
    self.e.start_of_turn(self.b);self.close();self.e.start_of_turn(self.t);self.close();self.e.end_round()
    self.assertEqual([row['actor'].entity_id for row in self.e._turn_closures],
                     [self.a.entity_id,self.q.entity_id,self.u.entity_id,self.b.entity_id,self.t.entity_id])
    self.valid()

 def mounted_then_replacement(self):
  self.mixed_schedule_fixture(rider_juggler=True,prepare=False)
  self.e.gm.set_stat(self.u,'spe',value=80,reason='actual faster mount for first-slot choice')
  reserve=self.actor('rider-reserve','pokemon',(14,3),70,owner=self.b,side='foe',field=False)
  PARTY.configure(self.e,self.b,mode='standard',reason='actual expanded rider party',roster=[self.t,self.u,reserve],storage={'kind':'center','id':'rival-center'})
  actors=[self.a,self.b,self.p,self.t,self.u]
  S.prepare(self.e,actors,source='gm/mounted-before-party-schedule');self.e.start_round(actors)
  self.assertEqual(S.status(self.e)['next']['actor_id'],self.u.entity_id)
  self.e.start_of_turn(self.b);self.e.dismount(self.b,reason='actual rider releases the unused mount before switching it')
  J.act(self.e,self.b,recall=[self.u],send=[(reserve,(14,1))],source_id=J.QUICK,
        request_id='mounted-then-replace',reason='actual own-turn Quick Switch of the unused mount')
  return reserve.entity_id

 def test_same_cursor_mounted_exchange_then_party_replacement_preserves_historical_mount(self):
  reserve_id=self.mounted_then_replacement();state=self.e._initiative_schedule
  self.assertEqual([row['kind'] for row in state['change_history']['events']],['mounted_exchanges','replacements','party_orders'])
  self.assertEqual({row['cursor'] for row in state['change_history']['events']},{0})
  self.assertIs(state['mounted_exchanges'][0]['mount'],self.u)
  self.assertEqual(state['slots'][self.u.entity_id]['actor'].entity_id,reserve_id)
  self.assertIs(self.e._active_turn_actor,self.b);self.mixed_schedule_restore();self.close()
  self.assertEqual(S.status(self.e)['next']['actor_id'],reserve_id)
  self.reject(lambda:self.e.start_of_turn(self.b),'next unconsumed|ordinary turn');self.valid()

 def test_same_cursor_native_gm_release_reorder_precedes_mounted_exchange(self):
  self.mixed_schedule_fixture(rider_juggler=True,prepare=False)
  for actor,speed in ((self.u,80),(self.a,60),(self.b,50),(self.p,20),(self.t,15)):
   self.e.gm.set_stat(actor,'spe',value=speed,reason='actual distinct release-order boundary')
  actors=[self.a,self.b,self.p,self.t,self.u]
  S.prepare(self.e,actors,source='gm/release-before-mounted-schedule');self.e.start_round(actors)
  self.e.gm.recall(self.t,reason='actual GM recall before its unused turn')
  self.e.gm.send_out(self.t,pos=(6,1),reason='actual GM release grants Juggler initiative')
  self.e.start_of_turn(self.b)
  events=self.e._initiative_schedule['change_history']['events']
  self.assertEqual([row['kind'] for row in events],['party_orders','mounted_exchanges'])
  self.assertEqual([row['cursor'] for row in events],[0,0]);self.mixed_schedule_restore()

 def test_swarm_continuations_party_reorder_and_mounted_exchange_replay_in_producer_order(self):
  import swarm_transitions as SWARM,turn as TURN,frequency as F
  self.mixed_schedule_fixture(rider_juggler=True,swarm=True)
  for count in (70,65):
   self.e.start_of_turn(self.t,initiative_count=count)
   self.assertTrue(TURN.spend(self.e,self.t,'standard','actual Swarm action before party reorder'))
   self.e.end_of_turn(self.t)
  serial=self.t.custom_conditions['combat_turn_serial'];turn=F.state(self.t)['turn']
  self.e.start_of_turn(self.a);self.action(request='swarm-party-reorder');self.close()
  self.e.start_of_turn(self.q);self.close();self.e.start_of_turn(self.t,initiative_count=60)
  self.assertTrue(TURN.spend(self.e,self.t,'standard','actual Swarm action after party reorder'));self.e.end_of_turn(self.t)
  self.assertEqual(S.status(self.e)['next']['actor_id'],self.u.entity_id)
  self.e.start_of_turn(self.b);self.mixed_schedule_restore();self.close()
  self.e.start_of_turn(self.t,initiative_count=55)
  self.assertEqual((self.t.custom_conditions['combat_turn_serial'],F.state(self.t)['turn']),(serial,turn))
  self.assertTrue(TURN.spend(self.e,self.t,'standard','actual final Swarm action'));self.e.end_of_turn(self.t)
  self.e.start_of_turn(self.u)
  # A real opposing release opens Quick Switch while the mount owner turn is suspended.
  self.e.gm.recall(self.q,reason='actual opposing recall after its consumed turn')
  self.e.gm.send_out(self.q,pos=(3,1),reason='actual opposing release triggers the rider reaction')
  request='replace-closed-swarm-slot';saved={};finish=J.finish_party_reaction
  reserve=W.actor_index(self.e)[self.swarm_reserve.entity_id];reserve_id=reserve.entity_id
  def save_suspended(e,a,request_id):
   if request_id==request:
    self.assertEqual(I.suspended_owner(e).entity_id,self.u.entity_id)
    saved['payload']=json.loads(json.dumps(CODEC.dump_engine(e),ensure_ascii=False))
   return finish(e,a,request_id)
  with patch.object(J,'finish_party_reaction',side_effect=save_suspended):
   J.act(self.e,self.b,recall=[self.t],send=[(reserve,(6,1))],source_id=J.QUICK,
         event_id=self.last_event('release',self.b),request_id=request,reason='actual reaction replaces the already-consumed Swarm slot')
  self.assertIs(self.e._active_turn_actor,self.u)
  self.e=CODEC.load_engine(self.rules,saved['payload']);index=W.actor_index(self.e)
  self.assertEqual(I.suspended_owner(self.e).entity_id,self.u.entity_id)
  J.finish_party_reaction(self.e,index[self.b.entity_id],request);self.restore()
  state=self.e._initiative_schedule;self.assertEqual(state['slots'][self.t.entity_id]['actor'].entity_id,reserve_id)
  self.assertEqual(state['slots'][self.t.entity_id]['turn'],'closed');self.assertIs(self.e._active_turn_actor,self.u)
  self.close();self.e.end_round()
  row=SWARM.state(self.t);actions=row['round_trigger_receipts'][row['own_turn_key']]['actions']
  self.assertEqual([action['initiative'] for action in actions],[70,65,60,55]);self.assertEqual(row['swarm_points'],0)
  self.assertEqual(sum(row['actor'] is self.t for row in self.e._turn_closures),1);self.valid()

 def test_transformation_chronology_rejects_omission_duplicate_legacy_hiding_and_resigned_binding_reorder(self):
  self.mounted_then_replacement();state=self.e._initiative_schedule;before=self.e.export_state()
  history=deepcopy(state['change_history'])
  rows=[row for kind in S.STEP_CHANGES for row in state.get(kind,[])]
  stamps=[(row,row['change_sequence'],row.get('sha256')) for row in rows]
  def resign():
   data=state['change_history'];previous=data['legacy_sha256']
   for sequence,event in enumerate(data['events']):
    row=state[event['kind']][event['index']];row['change_sequence']=sequence
    if event['kind']=='mounted_exchanges':row['sha256']=S._exchange_sha(row)
    event['sha256']=S._change_hash(state,event,row,previous);previous=event['sha256']
  for change in ('omit','duplicate','prefix','resigned-binding-order','missing-history'):
   with self.subTest(change=change):
    state['change_history']=deepcopy(history)
    try:
     data=state['change_history']
     if change=='omit':data['events'].pop()
     elif change=='duplicate':data['events'].append(deepcopy(data['events'][-1]))
     elif change=='prefix':
      data['legacy_prefix']['mounted_exchanges']=1
      data['legacy_sha256']=S._legacy_change_hash(state,data['legacy_prefix']);resign()
     elif change=='resigned-binding-order':
      data['events'][0],data['events'][1]=data['events'][1],data['events'][0];resign()
     else:state.pop('change_history')
     with self.assertRaises(ValueError):self.e.export_state()
    finally:
     state['change_history']=deepcopy(history)
     for row,sequence,digest in stamps:
      row['change_sequence']=sequence
      if digest is not None:row['sha256']=digest
    self.assertEqual(self.e.export_state(),before)

if __name__=='__main__':unittest.main()
