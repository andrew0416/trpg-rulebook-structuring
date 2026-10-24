"""Seven Channeler members through actual acquisitions, native actions and lifecycle owners."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from channeler_fixture import ChannelerScene,Rules,Engine,C,T,W,F,AP,COMM
import combat_timing as TIME,coat_effects as COATS,combat_stage_sources as CS
import state_grants as G,class_passive_combat as P,native_scenario_fixture as N

class ChannelerTests(ChannelerScene,unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def test_seven_independent_actual_acquisitions_template_receipts(self):
  self.acquire();self.assertEqual(len(C.records(self.a,active=True)),1)
  self.reject(lambda:self.e.imprint_channel(self.a,self.p),'acquired')
  for uid in list(C.FEATURES)[1:]:self.family(uid)
  self.assertEqual(len(C.records(self.a,active=True)),7)
  self.assertEqual(len(__import__('acquired_features').class_instances(self.a)),1)
  self.assertEqual(T.STATIC_FEATURES[C.CLASS]['class_template'],C.CLASS)
  self.restore();self.valid()
 def test_actual_mystic_parent_and_rank_prerequisites(self):
  self.setup(mystic=False);self.reject(self.acquire,'Mystic|parent')
  self.setup(rank=3);self.reject(lambda:self.acquire(C.SENSES),'parent')
  self.acquire();self.reject(lambda:self.acquire(C.CONDUIT),'rank')
  self.e.gm.set_skill(self.a,'직감',4,reason='actual trained Adept Intuition');self.acquire(C.CONDUIT)
  self.reject(lambda:self.acquire(C.PAIN),'rank')
  self.e.gm.set_skill(self.a,'직감',5,reason='actual trained Expert Intuition');self.acquire(C.PAIN)
  self.reject(lambda:self.acquire(C.SOOTHE),'rank')
  self.e.gm.set_skill(self.a,'직감',6,reason='actual trained Master Intuition');self.acquire(C.SOOTHE);self.valid()
 def test_selected_source_and_unacquired_named_feature_cannot_activate(self):
  self.begin();self.reject(lambda:self.e.manual_feat(self.a,C.CLASS,self.p),'acquired')
  self.acquire();self.e.manual_feat(self.a,C.CLASS,self.p);self.assertTrue(C.connected(self.e,self.a,self.p))
  self.reject(lambda:self.e.manual_feat(self.a,C.PAIN,self.p),'actual damaging attack')
 def test_hostile_dc14_failure_dc15_success_not_same_as_enemy_side(self):
  self.setup(rank=3);self.acquire();hostile=self.add('hostile','pokemon',(5,5),disposition='적대적')
  self.begin();out=self.e.channel_pokemon(self.a,hostile,roll_options={'fixed':[4,5,5]});self.assertEqual(out['status'],'failed')
  self.assertFalse(C.connected(self.e,self.a,hostile));self.next_round()
  self.e.channel_pokemon(self.a,hostile,roll_options={'fixed':[5,5,5]});self.assertTrue(C.connected(self.e,self.a,hostile))
  self.next_round();self.e.channel_pokemon(self.a,self.b);self.assertTrue(C.connected(self.e,self.a,self.b));self.valid()
 def test_limit_exact20_and_both_movement_endings(self):
  self.setup(rank=3);self.channel(self.p,self.q,self.r);self.next_round()
  self.reject(lambda:self.e.channel_pokemon(self.a,self.b),'limit')
  self.e.stop_channeling(self.a,self.r);self.e.gm.set_position(self.p,(22,2),reason='exact twenty metres');self.assertTrue(C.connected(self.e,self.a,self.p))
  self.e.gm.set_position(self.p,(23,2),reason='over twenty metres');self.assertFalse(C.connected(self.e,self.a,self.p))
  self.e.gm.set_position(self.a,(30,20),reason='Channeler moves beyond other target');self.assertFalse(C.connected(self.e,self.a,self.q));self.valid()
 def test_invalid_target_unknown_distance_duplicate_and_league_atomic(self):
  self.acquire();self.begin();self.reject(lambda:self.e.channel_pokemon(self.a,self.a),'Pokemon')
  self.e.channel_pokemon(self.a,self.p);self.reject(lambda:self.e.channel_pokemon(self.a,self.p),'already')
  self.e.gm.set_position(self.q,(40,2),reason='observed too far');self.reject(lambda:self.e.channel_pokemon(self.a,self.q),'twenty')
  with patch.object(self.e,'_league_runtime',{},create=True):
   with self.assertRaisesRegex(ValueError,'League'):self.e.channel_pokemon(self.a,self.r)
 def test_owner_faint_ends_every_link_and_each_imprint_once(self):
  self.family(C.SENSES);self.channel(self.p,self.q);self.next_round();self.e.imprint_channel(self.a,self.p);self.next_round();self.e.imprint_channel(self.a,self.q)
  before=AP.available(self.a);self.e.gm.faint(self.a,reason='actual owner faint');self.assertEqual(AP.available(self.a),before+2)
  self.assertFalse(C.participants(self.e,self.a));self.assertFalse(C.imprints(self.p));COMM.boundary(self.e,'reconcile');self.assertEqual(AP.available(self.a),before+2);self.valid()
 def test_actual_information_unknown_truth_both_directions_and_hour(self):
  self.channel(self.p);facts=self.e.channel_knowledge(self.a,self.p);self.assertIsNone(facts['intentions']);self.assertIsNone(facts['past_hour'])
  self.e.observe_channel_information(self.p,intentions='protect',emotions='calm',motivations='friendship',memories=[{'at':0,'text':'a vague meeting'}],reason='GM observed actual world facts')
  result=self.e.communicate_channel(self.p,self.a,['intentions','emotions'],request_id='truth');self.assertEqual(result['message']['information']['intentions'],'protect')
  self.e.observe_channel_information(self.a,intentions='help',reason='actual trainer intent');self.assertEqual(self.e.communicate_channel(self.a,self.p,['intentions'],request_id='back')['message']['information'],{'intentions':'help'})
  self.assertEqual(self.e.channel_knowledge(self.a,self.p)['past_hour'][0]['text'],'a vague meeting');self.restore();self.valid()
 def test_knowledge_reads_native_temporary_ability_and_current_moves(self):
  self.channel(self.p);self.e.gm.set_move(self.p,'move/역할',reason='actual learned Role Play');self.e.gm.set_ability(self.q,'인분',reason='actual donor ability')
  self.next_round(self.p);self.use(self.p,self.q,'move/역할');facts=self.e.channel_knowledge(self.a,self.p)
  self.assertIn('인분',facts['abilities']);self.assertIn('move/역할',facts['moves']);self.restore();self.valid()
 def test_imprints_individual_ap_distance_and_release_rechecks(self):
  self.family(C.SENSES);self.channel(self.p,self.q);self.next_round();before=AP.available(self.a)
  self.e.imprint_channel(self.a,self.p);self.next_round();self.e.imprint_channel(self.a,self.q);self.assertEqual(AP.available(self.a),before-2)
  self.e.gm.set_position(self.p,(40,2),reason='distant imprint');self.assertTrue(C.connected(self.e,self.a,self.p))
  self.e.release_channel_imprint(self.a,self.p);self.assertFalse(C.connected(self.e,self.a,self.p));self.assertTrue(C.connected(self.e,self.a,self.q));self.assertEqual(AP.available(self.a),before-1)
  self.reject(lambda:self.e.release_channel_imprint(self.a,self.p),'imprint');self.restore();self.valid()
 def test_focus_once_even_after_stop_release_and_json_restore(self):
  self.family(C.SENSES);self.channel(self.p,self.q);self.next_round();self.e.imprint_channel(self.a,self.p);self.next_round();self.e.imprint_channel(self.a,self.q)
  self.e.focus_channel_senses(self.a,self.p);self.e.stop_channeling(self.a,self.p);self.restore()
  self.reject(lambda:self.e.focus_channel_senses(self.a,self.q),'one selected');self.next_round();self.e.focus_channel_senses(self.a,self.q);self.valid()
 def test_sensory_facts_become_unknown_when_target_context_moves(self):
  self.family(C.SENSES);self.channel(self.p);self.next_round();self.e.imprint_channel(self.a,self.p);self.e.focus_channel_senses(self.a,self.p)
  self.e.observe_channel_information(self.p,senses={'visual':'actual tree','auditory':'actual birds'},reason='actual sensed world');self.assertEqual(self.e.read_channel_senses(self.a)['status'],'observed')
  self.e.gm.set_position(self.p,(4,4),reason='new sensory location');self.assertEqual(self.e.read_channel_senses(self.a)['status'],'unknown')
 def test_noncombat_focus_changes_after_actual_ten_seconds(self):
  self.family(C.SENSES);self.channel(self.p,self.q);self.next_round();self.e.imprint_channel(self.a,self.p);self.next_round();self.e.imprint_channel(self.a,self.q)
  self.e.end_of_turn(self.a);self.e.end_encounter();self.e.focus_channel_senses(self.a,self.p)
  self.reject(lambda:self.e.focus_channel_senses(self.a,self.q),'one selected');self.e.advance_time(seconds=10);self.e.focus_channel_senses(self.a,self.q);self.restore();self.valid()
 def test_sync_native_hit_miss_foe_counters_and_actual_accuracy_evasion(self):
  self.family(C.SYNC);self.channel(self.p,self.q);self.next_round();self.e.synchronize_channel(self.a);self.turn(self.p,40)
  self.use(self.p,self.b);self.assertEqual(C.synchronized_bonus(self.e,self.q,self.b),1);self.assertEqual(C.synchronized_bonus(self.e,self.q,self.z),0)
  baseline=self.q.evasion('물리',engine=self.e,attacker=self.z);self.assertEqual(self.q.evasion('물리',engine=self.e,attacker=self.b),baseline+1)
  self.turn(self.q,30);result=self.use(self.q,self.b,face=1);self.assertEqual(C.synchronized_bonus(self.e,self.p,self.b),1)
  self.valid()
 def test_sync_status_hit_and_full_round_boundary(self):
  self.family(C.SYNC);self.channel(self.p,self.q);self.e.gm.set_move(self.p,'move/울음소리',reason='actual known status attack')
  self.next_round();self.e.synchronize_channel(self.a);self.turn(self.p,40);self.use(self.p,self.b,'move/울음소리');self.assertEqual(C.synchronized_bonus(self.e,self.q,self.b),1)
  self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(51);self.assertEqual(C.synchronized_bonus(self.e,self.q,self.b),1)
  self.e.at_initiative_count(50);self.assertEqual(C.synchronized_bonus(self.e,self.q,self.b),0);self.valid()
 def test_sync_allies_do_not_count_scene_three_and_replay(self):
  self.family(C.SYNC);self.channel(self.p,self.q)
  for n in range(3):
   self.next_round();self.e.synchronize_channel(self.a)
   if n==0:
    self.turn(self.p,40);self.use(self.p,self.q);self.assertEqual(C.synchronized_bonus(self.e,self.p,self.q),0)
  self.next_round();self.reject(lambda:self.e.synchronize_channel(self.a),'frequency')
 def spirit_setup(self,stat):
  self.family(C.SPIRIT);self.channel(self.p,self.q);self.e.gm.set_stat(self.q,stat,value=40,reason='observed unique donor highest stat');self.next_round()
  before=AP.available(self.a);self.e.boost_channel_spirit(self.a,self.p,self.q,stat=stat);self.assertEqual(AP.available(self.a),before-2)
 def test_spirit_five_highest_branches_real_damage_dr_initiative(self):
  for stat,kind,move in [('atk','damage','move/몸통박치기'),('spa','damage','move/물대포'),('def','reduction','move/몸통박치기'),('spd','reduction','move/물대포'),('spe','initiative',None)]:
   with self.subTest(stat=stat):
    self.setup();self.spirit_setup(stat);m=self.rules.move(move) if move else None;self.assertEqual(C.spirit_bonus(self.e,self.p,kind,m),6)
    if kind=='damage':self.assertEqual(P.damage_roll_modifier(self.e,self.p,self.b,m,1),6)
    elif kind=='reduction':self.assertEqual(P.damage_reduction(self.e,self.b,self.p,m,1,False),6)
    else:self.assertEqual(self.e.initiative_value(self.p).value,self.p.staged('spe')+6)
    self.valid()
 def test_spirit_nonowned_tie_self_target_slot_and_donor_snapshot(self):
  self.family(C.SPIRIT);self.channel(self.p,self.q);self.next_round();self.assertNotIn('trainer_id',self.p.spec)
  self.reject(lambda:self.e.boost_channel_spirit(self.a,self.p,self.p),'tie');self.e.boost_channel_spirit(self.a,self.p,self.p,stat='atk')
  self.reject(lambda:self.e.boost_channel_spirit(self.a,self.p,self.q,stat='atk'),'Stratagem')
  self.e.gm.set_stat(self.p,'spe',value=90,reason='later stat change does not reselect donor');self.assertEqual(C.spirit_bonus(self.e,self.p,'damage',self.rules.move('move/몸통박치기')),6)
  self.restore();self.valid()
 def test_spirit_current_rank_link_stop_retention_and_individual_release(self):
  self.spirit_setup('atk');self.e.stop_channeling(self.a,self.p);self.e.gm.set_skill(self.a,'직감',5,reason='actual later rank')
  self.assertEqual(C.spirit_bonus(self.e,self.p,'damage',self.rules.move('move/몸통박치기')),5);before=AP.available(self.a)
  P.release(self.e,self.a,self.p,C.SPIRIT);self.assertEqual(AP.available(self.a),before+2);self.assertEqual(C.spirit_bonus(self.e,self.p,'damage',self.rules.move('move/몸통박치기')),0)
 def test_spirit_encounter_end_releases_bindings(self):
  self.spirit_setup('def');before=AP.available(self.a);self.e.end_of_turn(self.a);self.e.end_encounter();self.assertEqual(AP.available(self.a),before+2);self.assertIsNone(P._active(self.e,self.p,C.SPIRIT));self.valid()
 def test_conduit_swaps_all_one_stat_preserves_other_stages_and_sources(self):
  self.family(C.CONDUIT);self.channel(self.p,self.q);self.e.gm.set_stage(self.p,'atk',value=3,reason='actual stages');self.e.gm.set_stage(self.q,'atk',value=-2,reason='actual stages');self.e.gm.set_stage(self.p,'def',value=2,reason='independent stages')
  self.next_round();before=AP.available(self.a);self.e.channel_power_conduit(self.a,self.p,self.q,mode='stages',stat='atk')
  self.assertEqual((self.p.stages['atk'],self.q.stages['atk'],self.p.stages['def']),(-2,3,2));self.assertEqual(AP.available(self.a),before-2);self.restore();self.valid()
 def test_conduit_one_coat_identity_payload_lifetime_and_new_holder_tick(self):
  self.family(C.CONDUIT);self.channel(self.p,self.q);self.next_round(self.p);self.use(self.p,self.p,'move/아쿠아링');record=deepcopy(COATS.live(self.p)[0])
  self.next_round();self.e.channel_power_conduit(self.a,self.p,self.q,mode='coat',coat_id=record['id']);self.assertFalse(COATS.live(self.p));moved=COATS.live(self.q)[0]
  self.assertEqual((moved['id'],moved['effect'],moved['effect_instance']['origin_actor_id']),(record['id'],record['effect'],record['effect_instance']['origin_actor_id']))
  self.e.gm.set_hp(self.q,value=1,reason='injured new Coat holder');self.next_round(self.q);self.assertEqual(self.q.hp,1+self.e.tick(self.q));self.restore();self.valid()
 def test_conduit_bad_identity_and_late_second_assignment_atomic(self):
  self.family(C.CONDUIT);self.channel(self.p,self.q);self.next_round();self.reject(lambda:self.e.channel_power_conduit(self.a,self.p,self.p,mode='stages',stat='atk'),'distinct')
  self.reject(lambda:self.e.channel_power_conduit(self.a,self.p,self.q,mode='coat',coat_id='invented'),'actual')
  original=CS.commit_assignment;calls=[]
  def fail_second(actor,plan):
   calls.append(actor.entity_id)
   if len(calls)==2:raise ValueError('late assignment failure')
   return original(actor,plan)
  with patch.object(CS,'commit_assignment',fail_second):self.reject(lambda:self.e.channel_power_conduit(self.a,self.p,self.q,mode='stages',stat='atk'),'late assignment')
 def conduit_moves(self):
  self.family(C.CONDUIT);self.channel(self.p,self.q);self.e.gm.set_move(self.p,'move/똬리틀기',reason='known donor Scene Move');self.e.gm.set_move(self.q,'move/판별',reason='known recipient Scene Move')
  COMM.permission(self.e,self.p,self.a,C.CONDUIT,True,reason='actual willing donor');self.next_round(self.q);self.use(self.q,self.q,'move/판별');self.next_round()
 def test_conduit_actual_scene_use_recovery_without_donor_move_activation(self):
  self.conduit_moves();last=deepcopy(F.state(self.p)['moves']);before=AP.available(self.a)
  self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/판별')
  self.assertEqual(self.p.move_uses['move/똬리틀기'],1);self.assertEqual(self.q.move_uses['move/판별'],0);self.assertEqual(F.state(self.p)['moves'],last);self.assertEqual(AP.available(self.a),before-2)
  self.assertEqual(F.state(self.p)['move_forfeitures'][-1]['source'],C.CONDUIT);self.restore();self.valid()
  # Actual use remains an observation when ordinary restoration clears the repeat lock.
  self.assertTrue(F.scene_move_was_used(self.q,'move/판별'));self.assertFalse(F.scene_move_was_used(self.p,'move/똬리틀기'))
 def test_conduit_forfeiture_ignores_use_interval_and_suppression(self):
  self.conduit_moves();self.next_round(self.p);self.use(self.p,self.p,'move/똬리틀기');last=deepcopy(F.state(self.p)['moves']['move/똬리틀기']);self.turn(self.a,20)
  self.assertFalse(F.move_allowed(self.e,self.p,'move/똬리틀기')[0]);self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/판별')
  self.assertEqual(F.state(self.p)['moves']['move/똬리틀기'],last);self.assertEqual(self.p.move_uses['move/똬리틀기'],2)
 def test_conduit_unwilling_unused_daily_recipient_and_recipient_scene_cap(self):
  self.conduit_moves();COMM.permission(self.e,self.p,self.a,C.CONDUIT,False,reason='actual donor declines')
  self.reject(lambda:self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/판별'),'willing')
  COMM.permission(self.e,self.p,self.a,C.CONDUIT,True,reason='actual donor agrees');self.reject(lambda:self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/칼춤'),'Scene|used')
  self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/판별');self.next_round(self.q);self.use(self.q,self.q,'move/판별');self.next_round()
  self.reject(lambda:self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/판별'),'once per Scene')
 def test_pain_actual_attack_damage_divided_after_selected_resist_reduction(self):
  self.ready_pain();self.e.gm.set_types(self.q,['바위'],reason='selected actual Normal resistance');before=self.q.hp
  result,rows=self.damage();amount=rows[-1][3];self.assertEqual(self.q.hp,before-max(0,amount-6)//2);self.assertEqual(self.p.hp,1-max(0,amount-6)//2)
  self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],1);self.assertEqual(self.b.move_uses['move/몸통박치기'],1);self.valid()
 def test_pain_excludes_unchosen_resistance_and_preserves_temporary_hp_owner(self):
  self.ready_pain();self.e.gm.set_types(self.r,['고스트'],reason='unchosen immunity');self.e.gm.set_temp_hp(self.p,3,reason='actual temporary HP');before=self.q.hp
  _,rows=self.damage();loss=rows[-1][3]//2;self.assertEqual(self.q.hp,before-loss);self.assertEqual(self.p.hp,1-max(0,loss-3));self.assertEqual(self.p.temp_hp,max(0,3-loss));self.valid()
 def test_pain_actual_capped_damage_shared_with_would_faint(self):
  self.ready_pain();self.p.damage_cap={'value':12};before=self.q.hp
  self.damage();self.assertEqual(self.q.hp,before-6);self.assertEqual(self.p.hp,-5)
 def test_pain_replaces_secondary_target_effect_but_keeps_hit_and_move_cost(self):
  self.ready_pain();before=self.p.stages.copy();self.damage(move='move/진흙뿌리기')
  self.assertEqual(self.p.stages,before);self.assertEqual(self.b.move_uses['move/진흙뿌리기'],1)
  result=self.latest()['results'][self.p.entity_id];self.assertTrue(result['hit']);self.assertEqual(result['dealt'],0)
 def test_pain_decline_nonfaint_plain_loss_do_not_spend(self):
  self.family(C.PAIN);self.channel(self.p,self.q);self.decision('pain_dampening',False);self.damage();self.assertNotIn(C.PAIN,F.state(self.a)['activations'])
  self.e.lose_hp(self.q,1,source='actual ordinary loss');self.assertNotIn(C.PAIN,F.state(self.a)['activations'])
  self.e.gm.set_hp(self.p,value=1,reason='actual low HP');self.damage();self.assertNotIn(C.PAIN,F.state(self.a)['activations'])
 def test_pain_must_include_trigger_unique_live_targets_atomic(self):
  self.ready_pain();self.next_round(self.b)
  for selected in ([self.q.entity_id],[self.p.entity_id,self.p.entity_id],[self.p.entity_id,self.b.entity_id]):
   self.decision('pain_dampening',selected);self.reject(lambda:self.use(self.b,self.p),'triggering|distinct|Channeled')
 def test_pain_late_loss_failure_rolls_back_all_recipients_rng_and_frequency(self):
  self.ready_pain();self.next_round(self.b);original=Engine._lose_hp
  def fail_second(e,target,*args,**kwargs):
   if target.entity_id==self.q.entity_id:raise ValueError('late loss failure')
   return original(e,target,*args,**kwargs)
  with patch.object(Engine,'_lose_hp',fail_second):self.reject(lambda:self.use(self.b,self.p),'late loss')
 def test_pain_no_recursive_offer_and_scene_twice(self):
  self.ready_pain();self.damage();self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],1)
  self.e.gm.revive(self.p,hp=1,reason='actual revive');self.damage();self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],2)
  self.e.gm.revive(self.p,hp=1,reason='actual revive again');before=self.q.hp;self.damage();self.assertEqual(self.q.hp,before);self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],2)
 def test_endure_already_chosen_prevents_would_faint_without_consuming_pain(self):
  self.ready_pain();self.e.gm.set_move(self.p,'move/버티기',reason='actual learned Endure');self.decision('endure',True);self.damage()
  self.assertEqual(self.p.hp,1);self.assertNotIn(C.PAIN,F.state(self.a)['activations']);self.assertEqual(self.p.move_uses['move/버티기'],1);self.valid()
 def test_soothing_five_points_ticks_zero_recipient_and_current_max(self):
  self.family(C.SOOTHE);self.channel(self.p,self.q,self.r);self.e.gm.set_hp(self.p,value=1,reason='actual injury');self.e.gm.set_hp(self.q,value=1,reason='actual injury');self.next_round()
  self.e.soothe_channel(self.a,{self.p.entity_id:3,self.q.entity_id:2,self.r.entity_id:0});self.assertEqual(self.p.hp,1+3*self.e.tick(self.p));self.assertEqual(self.q.hp,1+2*self.e.tick(self.q));self.valid()
 def test_soothing_single_five_daily_twice_and_invalid_allocations_atomic(self):
  self.family(C.SOOTHE);self.channel(self.p);self.next_round()
  for allocation in ({self.p.entity_id:6},{self.p.entity_id:4},{self.p.entity_id:5.0},{self.p.entity_id:-1,self.q.entity_id:6},{self.b.entity_id:5}):self.reject(lambda a=allocation:self.e.soothe_channel(self.a,a),'five|Channeled')
  for _ in range(2):self.e.soothe_channel(self.a,{self.p.entity_id:5});self.next_round()
  self.reject(lambda:self.e.soothe_channel(self.a,{self.p.entity_id:5}),'frequency')
 def test_soothing_late_heal_failure_restores_every_recipient_and_cost(self):
  self.family(C.SOOTHE);self.channel(self.p,self.q);self.next_round();import life;original=life.heal
  def second(e,target,*args,**kwargs):
   if target.entity_id==self.q.entity_id:raise ValueError('late heal failure')
   return original(e,target,*args,**kwargs)
  with patch.object(life,'heal',second):self.reject(lambda:self.e.soothe_channel(self.a,{self.p.entity_id:2,self.q.entity_id:3}),'late heal')

 def test_actual_low_loyalty_melee_intercept_between_channeled_allies(self):
  self.e.gm.set_position(self.q,(10,10),reason='distinct old participant');self.q=self.add('actual owned reactor','pokemon',(3,5),owner=self.a)
  self.channel(self.p,self.q);self.e.gm.observe_loyalty(self.q,1,reason='actual low loyalty');self.e.gm.set_position(self.q,(3,5),reason='native interception start')
  self.next_round(self.b);self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual Intercept choice')
  import passive_events as EVENTS
  with self.assertRaises(EVENTS.PassiveEventPending):self.use(self.b,self.p)
  event=self.e._passive_pending;before=self.p.hp
  self.e.choose_move_defense(event,self.q,use=True,options={'path':[(3,5),(3,4),(3,3),(3,2)],'skill':'육상','mode':'land','shove_destination':[3,1],'roll_options':{'fixed':[6]*4}},reason='actual Intercept')
  self.assertEqual(self.p.hp,before);self.assertLess(self.q.hp,self.q.base_max_hp);self.assertEqual(self.q._action_history,['full']);self.valid()
 def test_actual_low_loyalty_ranged_intercept_and_unlinked_rejection(self):
  self.e.gm.set_position(self.q,(10,10),reason='distinct old participant');self.q=self.add('actual owned reactor','pokemon',(3,5),owner=self.a)
  self.channel(self.p,self.q);self.e.gm.observe_loyalty(self.q,1,reason='actual low loyalty')
  self.e.gm.set_position(self.b,(2,5),reason='actual ranged attacker');self.e.gm.set_position(self.p,(6,5),reason='actual ranged target');self.e.gm.set_position(self.q,(4,7),reason='actual reactor')
  self.next_round(self.b);self.e.watch_move_defense(self.p,[{'actor_id':self.q.entity_id,'source':'maneuver/원거리-가로채기'}],reason='actual ranged defense')
  import passive_events as EVENTS
  with self.assertRaises(EVENTS.PassiveEventPending):self.use(self.b,self.p,'move/물대포')
  event=self.e._passive_pending;before=self.p.hp
  self.e.choose_move_defense(event,self.q,use=True,options={'path':[(4,7),(4,6),(4,5)],'skill':'육상','mode':'land','roll_options':{'fixed':[6]*4}},reason='actual ranged Intercept')
  self.assertEqual(self.p.hp,before);self.assertEqual(self.q.pos,(4,5));self.valid()
 def test_retraining_imprint_and_class_prerequisite_dependency(self):
  self.family(C.SENSES);self.channel(self.p);self.next_round();self.e.imprint_channel(self.a,self.p);before=AP.available(self.a)
  import trainer_retraining as R
  def decisions(uid):
   sources={x:R.owned_source(self.e,self.a,x) for x in R._owned(self.a)}
   deps={source:[] for x,source in sources.items() if x!=uid}
   for child,parents in R._native_dependencies(self.e,self.a,R._owned(self.a)).items():
    if child!=uid:deps[sources[child]]=[sources[x] for x in parents]
   return {'request_id':'retrain:'+uid,'reason':'actual retraining','gm_decision':{'allowed':True,'reason':'GM reviewed'},'retained_dependencies':deps}
  declared=decisions(C.CLASS);self.reject(lambda:self.e.retrain_trainer_source(self.a,C.CLASS,**declared),'prerequisite|retained|source')
  self.e.retrain_trainer_source(self.a,C.SENSES,**decisions(C.SENSES));self.assertEqual(AP.available(self.a),before+1);self.assertIsNone(C.acquired(self.a,C.SENSES));self.assertTrue(C.connected(self.e,self.a,self.p));self.restore();self.valid()
 def test_pain_delayed_native_attack_uses_actual_landing_producer(self):
  self.ready_pain();self.e.gm.set_move(self.b,'move/미래예지',reason='actual learned delayed attack');self.next_round(self.b);self.use(self.b,self.p,'move/미래예지')
  self.assertEqual(len(self.e.delayed),1);before=self.q.hp;self.turn(self.p,30);self.e.end_of_turn(self.p)
  self.assertEqual(len(self.e.delayed),0);self.assertLess(self.q.hp,before);self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],1);self.valid()
 def test_pain_actual_normal_skin_type_used_for_selected_immunity(self):
  # Historical test identity retained; this uses the reviewed native alternate-Type Move mode.
  self.ready_pain();self.e.gm.set_types(self.q,['땅'],reason='chosen actual Electric immunity');self.e.gm.set_move(self.b,'move/천둥차기',reason='actual known alternate-Type Move');before=self.q.hp
  self.e.gm.choose_alternate_move_type(self.b,'move/천둥차기','전기',reason='actual optional source Type chosen')
  _,rows=self.damage(move='move/천둥차기');self.assertEqual(rows[-1][4]['actual_damage_type'],'전기');self.assertEqual(self.q.hp,before-max(0,rows[-1][3]-6)//2)
 def test_pain_then_actual_keep_fighting_on_distributed_hp_loss(self):
  import cheerleader as CH,keep_fighting as KEEP,moment_of_action as M
  owner=self.add('actual cheer owner','trainer',(1,1),skills={'매력':6,'명령':3});self.e.gm.set_position(self.p,(10,10),reason='distinct old participant')
  self.p=self.add('actual owned recipient','pokemon',(3,2),owner=owner);self.ready_pain()
  for uid in (M.TRAINING,*KEEP.FAMILY[:5],KEEP.FEATURE):T.acquire_static(self.e,owner,uid,acquisition_request_id='keep:'+uid)
  self.decision('keep_fighting',True);before=self.q.hp;self.damage();self.assertLess(self.q.hp,before);self.assertEqual(self.p.hp,1)
  self.assertEqual(KEEP._uses(owner)[0]['origin']['source'],C.PAIN);self.assertEqual(len(KEEP._uses(owner)),1);self.valid()

 def test_conduit_other_recovery_and_daily_forfeiture_keep_actual_use_distinct(self):
  self.conduit_moves();self.channel(self.r);self.e.gm.set_move(self.r,'move/판별',reason='actual recipient Scene Move')
  self.e.gm.set_move(self.q,'move/칼춤',add=False,reason='replace known Move');self.e.gm.set_move(self.q,'move/똬리틀기',reason='actual Scene x2 Move')
  self.next_round(self.r);self.use(self.r,self.r,'move/판별');self.next_round(self.q);self.use(self.q,self.q,'move/똬리틀기');self.next_round()
  COMM.permission(self.e,self.q,self.a,C.CONDUIT,True,reason='actual second willing donor')
  self.e.channel_power_conduit(self.a,self.q,self.r,mode='move',give_move='move/똬리틀기',restore_move='move/판별')
  self.assertEqual(self.q.move_uses['move/똬리틀기'],2);F.restore_scene_use(self.e,self.q,'move/똬리틀기');self.assertEqual(self.q.move_uses['move/똬리틀기'],1)
  self.next_round();self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/똬리틀기');self.assertEqual(self.q.move_uses['move/똬리틀기'],0)
  self.e.gm.set_move(self.r,'move/칼춤',add=False,reason='replace known Move');self.e.gm.set_move(self.r,'move/hp회복',reason='actual Daily Move')
  COMM.permission(self.e,self.r,self.a,C.CONDUIT,True,reason='actual willing Daily donor');self.next_round(self.p);self.use(self.p,self.p,'move/똬리틀기');self.next_round()
  old=deepcopy(F.state(self.r)['moves']);self.e.channel_power_conduit(self.a,self.r,self.p,mode='move',give_move='move/hp회복',restore_move='move/똬리틀기')
  self.assertEqual(self.r.move_uses['move/hp회복'],1);self.assertEqual(F.state(self.r)['moves'],old)
  self.e.end_of_turn(self.a);self.e.end_encounter();import downtime as D
  D.new_day(self.r);D.extended_rest(self.e,self.r,4);self.assertEqual(self.r.move_uses.get('move/hp회복',0),0);self.restore();self.valid()
  # Full restoration clears quota and repeat locks, while this Scene's actual-use observation remains.
  self.setup();self.conduit_moves();__import__('effects_ext').h_full_restore(self.e,self.a,self.q,{'restore_frequencies':True},{})
  self.assertEqual(self.q.move_uses,{});self.assertTrue(F.scene_move_was_used(self.q,'move/판별'))
  self.channel(self.r);self.e.gm.set_move(self.r,'move/판별',reason='actual third Scene recipient');self.next_round(self.r);self.use(self.r,self.r,'move/판별');self.next_round()
  COMM.permission(self.e,self.q,self.a,C.CONDUIT,True,reason='actual restored donor willing');self.e.channel_power_conduit(self.a,self.q,self.r,mode='move',give_move='move/판별',restore_move='move/판별')
  self.next_round();self.e.channel_power_conduit(self.a,self.p,self.q,mode='move',give_move='move/똬리틀기',restore_move='move/판별');self.assertEqual(self.q.move_uses['move/판별'],0);self.valid()

 def test_pain_paired_gambit_and_already_paid_press_on_native_threshold(self):
  import taskmaster as TASK,training_features as TRAIN
  def prepare(press=False):
   self.setup();self.e.death_enabled=False
   owner=self.add('actual taskmaster','trainer',(0,1),skills={'협박':6,'명령':6},features=[TRAIN.BRUTAL])
   self.e.gm.set_position(self.p,(10,10),reason='distinct old participant');self.p=self.add('actual taskmaster recipient','pokemon',(3,2),owner=owner)
   self.e.gm.observe_loyalty(self.p,6,reason='actual willing training partner')
   for uid in (TASK.CLASS,TASK.QUICK,TASK.SAVAGE,TASK.PAIN,TASK.DESPERATE,TASK.GAMBIT):T.acquire_static(self.e,owner,uid,acquisition_request_id='paired:'+uid)
   if press:
    T.acquire_static(self.e,owner,TASK.PRESS,acquisition_request_id='paired:'+TASK.PRESS);self.decision('taskmaster',1)
    self.e.train_pokemon(owner,[(self.p,[TRAIN.BRUTAL])],minutes=30,reason='actual completed Hardened training',request_id='paired-training',safe=True)
   self.ready_pain();return owner
  for side in ('incoming','counter'):
   with self.subTest(replaced=side):
    owner=prepare()
    if side=='counter':
     self.e.gm.set_hp(self.p,value=self.p.base_max_hp,reason='actual positive incoming recipient');self.channel(self.b);self.e.gm.set_hp(self.b,value=1,reason='actual would-faint counter recipient');self.decision('pain_dampening',[self.b.entity_id,self.q.entity_id])
    self.decision('deadly_gambit',{'move':'move/몸통박치기','roll_effects':False,'options':{'set_damage':True}})
    before_q=self.q.hp;physical=[];original=Engine._take_damage
    def observe(e,target,amount):physical.append(target.entity_id);return original(e,target,amount)
    with patch.object(Engine,'_take_damage',observe):_,damage=self.damage()
    replaced=self.p if side=='incoming' else self.b;ordinary=self.b if side=='incoming' else self.p
    amount=next(row[3] for row in damage if row[1]==replaced.entity_id)
    self.assertEqual(physical,[ordinary.entity_id]);self.assertEqual(self.q.hp,before_q-amount//2)
    self.assertEqual(self.p.move_uses['move/몸통박치기'],1);self.assertEqual(self.b.move_uses['move/몸통박치기'],1)
    self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],1);self.assertEqual(F.state(owner)['activations'][TASK.GAMBIT]['used'],1)
    self.assertIsNone(getattr(self.e,'_taskmaster_gambit',None));self.restore();self.valid()
  owner=prepare(press=True);self.decision('deadly_gambit',False);self.decision('press_on',True)
  self.e.lose_hp(self.p,2,source='actual preceding non-attack loss');self.assertTrue(TASK.conscious(self.p));self.assertLess(self.p.hp,0)
  before=self.q.hp;self.damage();self.assertEqual(self.q.hp,before);self.assertNotIn(C.PAIN,F.state(self.a)['activations'])
  self.e.gm.set_hp(self.p,value=-(self.p.base_max_hp*30//100)+1,reason='actual paid-Press-On HP immediately above its faint threshold')
  before=self.q.hp;self.damage();self.assertLess(self.q.hp,before);self.assertEqual(F.state(self.a)['activations'][C.PAIN]['used'],1);self.valid()

if __name__=='__main__':unittest.main()
