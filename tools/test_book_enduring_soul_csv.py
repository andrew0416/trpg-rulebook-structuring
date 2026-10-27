"""Only Enduring Soul's actual CSV differences and touched Book boundaries."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch

import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
from engine import Combatant
from builder import build_pokemon,build_trainer
from grid import Grid
import test_category2_static_trainer_modifiers as FIX
import breather as B,trainer_feature_acquisition as T,temporary_hp as HP
import state_fields as FIELDS,state_codec as CODEC,world_entities as W,frequency as F
import trainer_retraining as RETRAIN
import endure as ENDURE,enduring_soul as NOTYET,initiative_interrupts as INTERRUPTS
import ability_transitions as AB,move_state as MOVES,state_grants as GRANTS
from native_scenario_fixture import assert_rejected_unchanged


@contextmanager
def observe_actual_heavy_hold(test):
 import heavy_standard_adapter as STANDARD,heavy_injury_adapter as HEAVY
 actual=STANDARD.hold;contexts=[]
 def record(engine,token,packet,reason):
  context=packet.get('context_evidence',{})
  contexts.append({key:deepcopy(context.get(key,[])) for key in ('failures','native_suffix_failures')})
  return actual(engine,token,packet,reason)
 with patch.object(STANDARD,'hold',record):
  try:yield
  except HEAVY.HeavyPending:test.fail(str(contexts))


class EnduringSoulCsvTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')
 encounter=FIX.StaticTrainerModifierTests.encounter
 def setUp(self):
  old=self.r.rulings;self.r.rulings=deepcopy(old);self.addCleanup(setattr,self.r,'rulings',old)
  self.e,self.a,self.p,self.foreign=self.encounter(classes=['class/불굴의-투지'])
  self.e.gm.observe_loyalty(self.p,6,reason='observed cooperative current-owner Move relationship')
  self.e.grid=Grid(12,8)
  FIELDS.base_patch(self.a,{'skills':{'육상':5,'집중':3}},reason='actual Enduring Soul skill sheet')
 def acquire(self,uid=B.STAYING,edition='local_csv'):
  return T.acquire_static(self.e,self.a,uid,acquisition_request_id='enduring/'+uid,
      selection=None if edition=='core' else {'edition':edition})
 def begin(self,actor=None):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  if self.e.round_start_seconds is not None:self.e.end_round()
  self.e.start_round(self.e.everyone);self.e.start_of_turn(actor or self.p)
 def take(self,*,actor=None,request='breather/one',staying=True,clear=False,shrug=False,heal=True,**options):
  actor=actor or self.p
  kwargs={'request_id':request,'save_dc':1,'save_reason':'explicit GM permission save and failed-attempt cost',
      'save_cost':'full','fixed_save':20}
  if staying:
   choice={'trainer_id':self.a.entity_id,'reset_stages':False}
   if B.feature_edition(self.e,self.a,B.STAYING)=='local_csv':choice['clear_temp_hp']=clear
   kwargs['staying_power']=choice
  else:kwargs.update(path=[actor.pos],retreat_reason='actual Stuck permits no retreat from the adjacent opponent')
  if shrug:kwargs['shrug_off']={'trainer_id':self.a.entity_id,'heal_injury':heal}
  kwargs.update(options)
  return self.e.take_breather(actor,**kwargs)
 def valid(self):
  report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
 def reject(self,fn,reason):assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def answer(self,key,value):
  self.e.rulings.answers=[r for r in self.e.rulings.answers if r['key']!=key]
  self.e.rulings.add_answer(key,value,reason='actual chosen source action',scope='scene')
 def restore(self):
  saved=CODEC.dump_engine(self.e);self.e=CODEC.load_engine(self.r,saved);index=W.actor_index(self.e)
  self.a,self.p,self.foreign=[index[c.entity_id] for c in (self.a,self.p,self.foreign)]
 def vim(self,edition='core'):
  FIELDS.base_patch(self.a,{'skills':{'육상':6,'집중':3}},reason='actual Master Athletics qualification')
  for uid in (B.STAYING,B.SHRUG,B.VIM):self.acquire(uid,edition)
  self.p.spec['tutor_points']=5
 def teach(self,**options):
  return self.e.pokemon_activity(self.a,'teach_feature_ability',target=self.p,feature=B.VIM,
      ability=self.r._selected_rule(ENDURE.VIGOR[0]),seconds=45,reason='actual completed Vim lesson',**options)
 def not_yet(self,move='move/몸통박치기',target=None,edition='core'):
  self.acquire(B.NOT_YET,edition);self.e.gm.set_move(self.p,move,reason='actual learned Interrupt choice')
  self.answer('not_yet',{'move_id':move,'target_id':(target or self.foreign).entity_id})
  self.begin(self.foreign)
 def use(self,actor,target,move,**options):
  self.e.gm.set_move(actor,move,reason='actual complete known Move list')
  with patch.object(Engine,'d20',return_value=10):return self.e.use_move_on(actor,target,move,self.e.everyone,**options)
 def latest(self,actor,move):
  return next(row for row in reversed(list(self.e._move_completions.values())) if row['actor'] is actor and row['move_id']==move)

 def test_actual_csv_acquisition_seals_source_and_rejects_changed_replay(self):
  row=self.acquire();self.assertEqual(row['snapshot']['source']['clause_id'],'C2CSV/input/db/feats.csv:R126:main')
  self.assertEqual(self.acquire()['integrity'],row['integrity'])
  self.reject(lambda:self.acquire(edition='core'),'replay')
  self.reject(lambda:self.acquire(B.SHRUG,'invented'),'source')
  self.assertNotIn(B.SHRUG,self.a.spec['feats']);self.valid()

 def test_base_class_explicit_book_and_csv_choices_keep_bsr_but_only_csv_adds_scaled_hp(self):
  for edition in ('core','local_csv'):
   with self.subTest(edition=edition):
    self.e,self.a,self.p,self.foreign=self.encounter()
    FIELDS.base_patch(self.a,{'skills':{'육상':3,'집중':3}},reason='actual Novice class prerequisites')
    before=self.p.stats['hp'];self.acquire(B.CLASS,edition)
    self.assertEqual(self.p.stats['hp'],before+(1+self.p.level//10 if edition=='local_csv' else 0))
    import pokemon_stat_edges as STAT
    self.assertEqual(STAT.levelup_provider(self.r,self.p.spec,(self.e,self.p))['source'],B.CLASS)
    self.restore();self.assertEqual(B.class_edition(self.a),edition);self.valid()

 def test_base_class_requires_both_novice_skills_and_seals_its_actual_source(self):
  self.e,self.a,self.p,self.foreign=self.encounter()
  FIELDS.base_patch(self.a,{'skills':{'육상':3,'집중':2}},reason='actual missing Novice Focus')
  self.reject(lambda:self.acquire(B.CLASS,'core'),'Novice Athletics and Focus')
  FIELDS.base_patch(self.a,{'skills':{'육상':3,'집중':3}},reason='actual earned Novice Focus')
  self.acquire(B.CLASS,'core');self.reject(lambda:self.acquire(B.CLASS,'local_csv'),'replay');self.valid()

 def test_csv_breather_preserves_selected_stages_and_temp_hp_without_trip_vulnerable_or_retreat(self):
  self.acquire();self.begin();self.e.change_stage(self.p,'atk',2);HP.grant(self.e,self.p,20)
  self.e.apply_status(self.p,'난동');self.e.apply_status(self.p,'혼란');before=self.p.pos
  result=self.take();self.assertTrue(result['completed'])
  self.assertEqual((self.p.pos,self.p.stages['atk'],self.p.temp_hp),(before,2,20))
  self.assertFalse({'넘어짐','취약','난동','혼란'} & self.p.conditions)
  self.assertEqual(self.p.budget,{'standard':0,'shift':0,'swift':1});self.valid()

 def test_csv_clear_reset_choice_and_current_class_skill_sum_grant_use_existing_nonstacking_hp(self):
  self.acquire();self.begin();self.e.change_stage(self.p,'def',3);HP.grant(self.e,self.p,20)
  result=self.take(clear=True,staying_power={'trainer_id':self.a.entity_id,'reset_stages':True,'clear_temp_hp':True})
  self.assertTrue(result['completed']);self.assertEqual(self.p.stages['def'],0);self.assertEqual(self.p.temp_hp,8)
  self.assertEqual(F.state(self.a)['activations'][B.STAYING]['used'],1)
  self.begin();self.reject(lambda:self.take(request='again'),'Scene use exhausted');self.valid()

 def test_book_staying_retains_vulnerability_clears_hp_and_does_not_receive_csv_bonus(self):
  self.acquire(edition='core');self.begin();HP.grant(self.e,self.p,20)
  self.assertTrue(self.take()['completed']);self.assertIn('취약',self.p.conditions)
  self.assertNotIn('넘어짐',self.p.conditions);self.assertEqual(self.p.temp_hp,0)
  self.reject(lambda:self.take(request='invalid-choice',staying_power={'trainer_id':self.a.entity_id,'reset_stages':False,'clear_temp_hp':False}),'Book has no such choice')
  self.valid()

 def test_csv_shrug_swift_breather_heals_one_injury_and_replay_never_reawards(self):
  self.acquire();self.acquire(B.SHRUG);self.e.gm.set_injuries(self.p,2,reason='actual witnessed Injuries');self.begin()
  result=self.take(shrug=True);self.assertTrue(result['completed']);self.assertEqual(result['removed_injuries'],1)
  self.assertEqual(self.p.injuries,1);self.assertEqual(self.p.budget,{'standard':1,'shift':1,'swift':0})
  saved=CODEC.dump_engine(self.e);self.assertEqual(self.take(shrug=True),result)
  self.assertEqual(CODEC.dump_engine(self.e),saved)
  self.e=CODEC.load_engine(self.r,saved);index=W.actor_index(self.e)
  self.a,self.p,self.foreign=[index[c.entity_id] for c in (self.a,self.p,self.foreign)]
  self.assertEqual(self.take(shrug=True),result)
  self.reject(lambda:self.take(request='daily-again',shrug=True),'daily use exhausted');self.valid()

 def test_book_shrug_independent_shift_and_csv_shrug_are_not_interchangeable(self):
  self.acquire(edition='core');self.acquire(B.SHRUG,'core');self.e.gm.set_injuries(self.p,2,reason='actual witnessed Injuries');self.begin()
  self.e.apply_status(self.p,'잠듦')
  self.reject(lambda:B.shrug_off(self.e,self.p,request_id='book/sleep-rejected',trainer_id=self.a.entity_id),'Shift action unavailable')
  self.e.cure_status(self.p,'잠듦')
  row=B.shrug_off(self.e,self.p,request_id='book/shift',trainer_id=self.a.entity_id)
  self.assertEqual((row['removed_injuries'],self.p.injuries),(1,1))
  self.assertEqual(self.p.budget,{'standard':1,'shift':0,'swift':1});self.valid()

 def test_book_shrug_free_when_taking_breather_reuses_daily_pokemon_quota(self):
  self.acquire(edition='core');self.acquire(B.SHRUG,'core');self.e.gm.set_injuries(self.p,2,reason='actual witnessed Injuries');self.begin()
  self.assertTrue(self.take(shrug=True)['completed']);self.assertEqual(self.p.injuries,1)
  self.assertEqual(self.p.budget,{'standard':0,'shift':0,'swift':1})
  self.reject(lambda:B.shrug_off(self.e,self.p,request_id='shift/second',trainer_id=self.a.entity_id),'daily use exhausted');self.valid()

 def test_csv_shrug_injury_healing_is_optional_and_failed_breather_does_not_heal(self):
  self.acquire();self.acquire(B.SHRUG);self.e.gm.set_injuries(self.p,2,reason='actual witnessed Injuries');self.begin()
  self.assertTrue(self.take(shrug=True,heal=False)['completed']);self.assertEqual(self.p.injuries,2)
  self.assertEqual(F.state(self.p)['activations'][B.SHRUG]['used'],1);self.valid()

 def test_missing_receipt_foreign_target_and_csv_only_choices_reject_unchanged(self):
  self.begin();self.reject(lambda:self.take(staying_power={'trainer_id':self.a.entity_id,'reset_stages':False,'clear_temp_hp':False}),'actual acquired')
  self.acquire();self.acquire(B.SHRUG)
  self.reject(lambda:self.take(actor=self.foreign,shrug=True),'actual owner Pokemon')
  self.reject(lambda:self.take(staying_power={'trainer_id':self.a.entity_id,'reset_stages':False}),'explicit temporary-HP')
  self.reject(lambda:B.shrug_off(self.e,self.p,request_id='csv/shift',trainer_id=self.a.entity_id),'Swift Breather')
  self.valid()

 def test_csv_shrug_failed_save_spends_swift_once_but_not_injury_or_temp_hp_bonus(self):
  self.acquire();self.acquire(B.SHRUG);self.e.gm.set_injuries(self.p,2,reason='actual witnessed Injuries');self.begin()
  row=self.take(shrug=True,save_dc=20,fixed_save=1)
  self.assertFalse(row['completed']);self.assertEqual(self.p.injuries,2);self.assertEqual(self.p.temp_hp,0)
  self.assertEqual(self.p.budget,{'standard':1,'shift':1,'swift':0})
  self.assertEqual(F.state(self.p)['activations'][B.SHRUG]['used'],1);self.valid()

 def test_csv_shrug_each_actual_pokemon_daily_quota_is_independent_and_new_day_reopens(self):
  self.acquire();self.acquire(B.SHRUG)
  second=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.e.gm.add_combatant(second,pos=(1,2),side='party',reason='actual second owned Pokemon')
  self.e.apply_status(self.p,'구속');self.begin();self.assertTrue(self.take(staying=False,shrug=True)['completed'])
  self.e.apply_status(second,'구속');self.begin(second)
  self.assertTrue(self.take(actor=second,request='second/daily',staying=False,shrug=True)['completed'])
  self.assertEqual([F.state(p)['activations'][B.SHRUG]['used'] for p in (self.p,second)],[1,1])
  self.e.end_of_turn(second);self.e.end_round();self.e.end_scene();self.e.advance_time(86400,self.e.everyone)
  for actor in self.e.everyone:__import__('downtime').new_day(actor)
  self.e.apply_status(self.p,'구속');self.begin()
  self.assertTrue(self.take(request='new-day/daily',staying=False,shrug=True)['completed']);self.valid()

 def test_csv_source_roundtrips_and_native_withdrawal_preserve_parent_contract_and_stop_future_permission(self):
  self.e=Engine(self.r,seed=126127);self.e.grid=Grid(12,8)
  self.a=Combatant(self.r,build_trainer(self.r,'actual retraining owner',30,
      dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),abilities=[],skills={'육상':5,'집중':3},
      extra={'classes':['class/불굴의-투지'],'feats':[],'edges':[],'exp_bank':30}))
  self.p=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id}))
  self.foreign=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,moves=[],abilities=[]))
  for actor,pos in ((self.a,(0,0)),(self.p,(1,0)),(self.foreign,(2,0))):
   self.e.gm.add_combatant(actor,pos=pos,side='party',reason='actual Enduring Soul source withdrawal participants')
  self.acquire();self.acquire(B.SHRUG)
  saved=CODEC.dump_engine(self.e);self.e=CODEC.load_engine(self.r,saved);index=W.actor_index(self.e)
  self.a,self.p,self.foreign=[index[c.entity_id] for c in (self.a,self.p,self.foreign)]
  self.assertEqual([B.feature_edition(self.e,self.a,f) for f in (B.STAYING,B.SHRUG)],['local_csv','local_csv'])
  self.e.gm.snapshot('before-source-withdrawal')
  def decisions(feature):
   sources={uid:RETRAIN.owned_source(self.e,self.a,uid) for uid in RETRAIN._owned(self.a)}
   retained={source:[] for uid,source in sources.items() if uid!=feature}
   for child,parents in RETRAIN._native_dependencies(self.e,self.a,RETRAIN._owned(self.a)).items():
    if child!=feature:retained[sources[child]]=[sources[parent] for parent in parents]
   return dict(request_id='enduring/retrain/'+feature,reason='actual chosen source withdrawal',
       gm_decision={'allowed':True,'reason':'GM reviewed retained actual prerequisites'},retained_dependencies=retained)
  parent_decisions=decisions(B.STAYING)
  self.reject(lambda:self.e.retrain_trainer_source(self.a,B.STAYING,**parent_decisions),'depend|prerequisite')
  self.e.retrain_trainer_source(self.a,B.SHRUG,**decisions(B.SHRUG))
  self.reject(lambda:B.shrug_owner(self.e,self.p,{'trainer_id':self.a.entity_id,'heal_injury':True}),'actual acquired')
  self.e.retrain_trainer_source(self.a,B.STAYING,**decisions(B.STAYING))
  self.reject(lambda:B.staying_owner(self.e,self.p,{'trainer_id':self.a.entity_id,'reset_stages':False,'clear_temp_hp':False}),'actual acquired')
  self.e.gm.restore('before-source-withdrawal')
  self.assertEqual([B.feature_edition(self.e,self.a,f) for f in (B.STAYING,B.SHRUG)],['local_csv','local_csv']);self.valid()

 def test_csv_swift_breather_requires_its_actual_trainer_free_activation_before_cost(self):
  self.acquire();self.acquire(B.SHRUG);self.e.apply_status(self.a,'잠듦');self.e.apply_status(self.p,'구속');self.begin()
  self.reject(lambda:self.take(staying=False,shrug=True),'Trainer Free Action unavailable');self.valid()

 def test_book_static_shrug_breather_free_action_belongs_to_the_actual_pokemon_not_sleeping_trainer(self):
  self.acquire(edition='core');self.acquire(B.SHRUG,'core')
  self.e.apply_status(self.a,'잠듦');self.e.apply_status(self.p,'구속')
  self.e.gm.set_injuries(self.p,2,reason='actual witnessed Injuries');self.begin()
  self.assertTrue(self.take(staying=False,shrug=True)['completed']);self.assertEqual(self.p.injuries,1);self.valid()

 def test_vim_book_and_csv_use_actual_sealed_acquisition_tp_job_and_permanent_connection(self):
  self.vim('local_csv');row=self.teach()
  self.assertEqual((row['point_cost'],self.p.spec['tutor_points'],self.e.elapsed_seconds),(2,3,45))
  self.assertTrue(AB.active(self.p,ENDURE.VIGOR[0]));self.assertIn(ENDURE.SOURCES[0],self.p.moves)
  payment=GRANTS.state(self.p)['payments'][row['payment']['group_id']]
  source=GRANTS.state(self.p)['sources'][payment['children'][0]]
  self.assertEqual(source['ability_lesson']['connection_move'],ENDURE.SOURCES[0])
  self.assertEqual(self.p.spec['move_learning'][ENDURE.SOURCES[0]]['source'],ENDURE.VIGOR[0])
  self.e.gm.snapshot('vim-completed');self.restore();self.valid()
  self.reject(lambda:self.teach(),'already has')
  sources={uid:RETRAIN.owned_source(self.e,self.a,uid) for uid in RETRAIN._owned(self.a)}
  retained={source:[] for uid,source in sources.items() if uid!=B.VIM}
  for child,parents in RETRAIN._native_dependencies(self.e,self.a,RETRAIN._owned(self.a)).items():
   if child!=B.VIM:retained[sources[child]]=[sources[parent] for parent in parents]
  self.reject(lambda:self.e.retrain_trainer_source(self.a,B.VIM,request_id='vim/irreversible-retraining',
      reason='actual attempted withdrawal after permanent teaching',
      gm_decision={'allowed':True,'reason':'GM reviewed the retained actual prerequisites'},
      retained_dependencies=retained),'irreversible')
  self.reject(lambda:self.e.gm.set_move(self.p,ENDURE.SOURCES[0],add=False,reason='attempt to forget Connection'),'cannot be forgotten')
  import grant_payments as PAYMENTS
  PAYMENTS.refund(self.e,self.p,[row['payment']['sources'][0]],request_id='explicit-ended-vim-Ability',
      reason='actual source-ended Ability without TP refund',refund_mode='none')
  self.assertFalse(AB.active(self.p,ENDURE.VIGOR[0]));self.restore()
  self.reject(lambda:self.e.gm.set_move(self.p,ENDURE.SOURCES[0],add=False,reason='Connection still cannot be forgotten'),'cannot be forgotten')

 def test_vim_actual_master_owner_and_tp_restrictions_and_late_failure_are_atomic(self):
  self.acquire();self.acquire(B.SHRUG)
  self.reject(lambda:self.acquire(B.VIM),'Master')
  FIELDS.base_patch(self.a,{'skills':{'육상':6,'집중':3}},reason='actual Master Athletics')
  self.acquire(B.VIM,'core');self.p.spec['tutor_points']=5
  self.p.spec['tutor_points']=1;self.reject(lambda:self.teach(),'two actual Tutor Points')
  self.p.spec['tutor_points']=5
  with patch('endure.learn_connection',side_effect=ValueError('late native Connection failure')):
   self.reject(lambda:self.teach(),'late native Connection failure')
  self.assertEqual(self.e.elapsed_seconds,0);self.assertFalse(AB.active(self.p,ENDURE.VIGOR[0]));self.valid()

 def test_vim_six_move_connection_requires_explicit_replacement_or_immediate_real_edge(self):
  self.vim()
  choices=('move/몸통박치기','move/울음소리','move/덩굴채찍','move/성장','move/잎날가르기','move/달콤한향기')
  for mid in choices:self.e.gm.set_move(self.p,mid,reason='actual known six-Move sheet')
  self.reject(lambda:self.teach(),'slot|six|6|capacity|known')
  self.teach(connection_replace=choices[0]);self.assertNotIn(choices[0],self.p.moves)
  self.assertEqual(len(MOVES.known(self.r,self.p.spec)),6);self.assertEqual(self.p.spec['tutor_points'],3);self.valid()

 def test_vim_immediate_advanced_connection_reuses_one_tp_investment_without_an_extra_hour(self):
  self.vim()
  for mid in ('move/몸통박치기','move/울음소리','move/덩굴채찍','move/성장','move/잎날가르기','move/달콤한향기'):
   self.e.gm.set_move(self.p,mid,reason='actual six-Move sheet')
  self.teach(advanced_connection=True)
  self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(2,45))
  self.assertEqual(len(MOVES.known(self.r,self.p.spec)),7)
  import advanced_connection as CONNECTION
  self.assertEqual(CONNECTION.exemptions(self.r,self.p.spec),{ENDURE.SOURCES[0]:CONNECTION.SOURCE+':'+ENDURE.VIGOR[0]})
  self.restore();self.valid()

 def test_vigor_actual_endure_heals_after_one_hp_and_only_massive_injury_is_prevented(self):
  self.vim();self.teach();FIELDS.base_patch(self.foreign,{'stats':dict(self.foreign.spec['stats'],atk=500)},reason='actual lethal attacker Attack')
  self.e.gm.set_hp(self.p,value=5,reason='actual wounded Pokemon');self.answer('endure',True);self.answer('vigor',True)
  self.begin(self.foreign);self.use(self.foreign,self.p,'move/몸통박치기',set_damage=True)
  receipt=self.latest(self.foreign,'move/몸통박치기')['endure'][self.p.entity_id]
  self.assertEqual(self.p.hp,1+self.e.tick(self.p));self.assertTrue(receipt['vigor']['prevented_massive_injury'])
  self.assertEqual(F.state(self.p)['activations'][ENDURE.VIGOR[0]]['used'],1)
  self.assertEqual(self.p.move_uses[ENDURE.SOURCES[0]],1);self.assertEqual(self.p._action_history,['free','free'])
  self.restore();self.valid()
  self.e.lose_hp(self.p,self.p.hp,source='condition/독');self.assertTrue(self.p.fainted)

 def test_vigor_decline_keeps_ordinary_endure_massive_injury_and_no_tick(self):
  self.vim();self.teach();FIELDS.base_patch(self.foreign,{'stats':dict(self.foreign.spec['stats'],atk=500)},reason='actual massive attacking Move')
  self.e.gm.set_hp(self.p,value=5,reason='actual wounded Pokemon');self.answer('endure',True);self.answer('vigor',False)
  self.begin(self.foreign);before=self.p.injuries;self.use(self.foreign,self.p,'move/몸통박치기',set_damage=True)
  self.assertEqual(self.p.hp,1);self.assertEqual(self.p.injuries,before+1)
  self.assertNotIn(ENDURE.VIGOR[0],F.state(self.p)['activations']);self.valid()

 def test_vigor_counter_actual_hp_loss_uses_the_same_endure_completion(self):
  self.vim();self.teach();import combat_move_reactions as REACT
  self.e.gm.set_hp(self.p,value=5,reason='actual wounded attacking Pokemon');self.e.gm.set_move(self.foreign,REACT.COUNTER,reason='actual Counter')
  self.answer('endure',True);self.answer('vigor',True);self.begin(self.p);REACT.arm(self.e,self.foreign,REACT.COUNTER)
  self.use(self.p,self.foreign,'move/몸통박치기',set_damage=True)
  self.assertEqual(self.p.hp,1+self.e.tick(self.p));self.assertEqual(self.foreign.move_uses[REACT.COUNTER],1);self.valid()

 def test_vigor_homebrew_is_explicit_and_uses_minus_half_not_ordinary_minus_quarter(self):
  self.r=Rules(ROOT,ruleset='homebrew');self.setUp();self.vim();self.teach()
  self.assertTrue(AB.active(self.p,ENDURE.VIGOR[1]));self.assertIn(ENDURE.SOURCES[1],self.p.moves)
  import enduring_awareness as AWARE,condition_recovery as RECOVERY
  defenders=[self.p]
  for i in (1,2):
   pupil=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,moves=[],abilities=[],
       extra={'trainer_id':self.a.entity_id,'tutor_points':5}))
   self.e.gm.add_combatant(pupil,pos=(1,i),side='party',reason='actual additional owned Vim pupil')
   self.e.pokemon_activity(self.a,'teach_feature_ability',target=pupil,feature=B.VIM,
       ability=ENDURE.VIGOR[1],seconds=45,reason='actual completed defensive Vigor lesson')
   defenders.append(pupil)
  self.a.spec['feats'].append(AWARE.AWARENESS)
  evidence=self.e.gm.confirm_awareness(self.a,[{'pokemon':p,'ability':ENDURE.VIGOR[1],
      'defensive_reason':'actual Vigor Defensive keyword and Endure HP protection'} for p in defenders],
      reason='actual three owned Pokemon each learned the selected Defensive Vigor source')
  self.assertEqual([r['ability_id'] for r in evidence['defenders']],[ENDURE.VIGOR[1]]*3)
  self.restore();save=RECOVERY.saving_check(self.e,self.p,None,11,fixed=9)
  self.assertEqual((save['natural'],save['dc'],save['passed']),(9,9,True))
  self.e.gm.set_hp(self.p,value=5,reason='actual wounded Pokemon')
  # A fixed table damage ruling is not an activation grant: the actual attack,
  # native hit, Endure completion and Vigor quota still have to run.
  damage=5+self.p.base_max_hp//3
  self.e.rule_hook('before_damage',lambda value,ctx:damage,reason='fixed actual attack damage between quarter and half')
  self.answer('endure',True);self.answer('vigor',True);self.begin(self.foreign)
  self.use(self.foreign,self.p,'move/몸통박치기',set_damage=True)
  self.assertEqual(self.p.hp,1+self.e.tick(self.p));self.assertEqual(self.p.move_uses[ENDURE.SOURCES[1]],1)
  self.valid()

 def test_not_yet_occurs_inside_the_actual_native_incoming_move_and_restores_its_continuation(self):
  self.not_yet();self.e.gm.set_hp(self.p,value=5,reason='actual wounded Pokemon')
  FIELDS.base_patch(self.foreign,{'stats':dict(self.foreign.spec['stats'],atk=25)},reason='actual attacking Move strength')
  with patch.object(Engine,'d20',return_value=10):self.use(self.foreign,self.p,'move/몸통박치기',set_damage=True)
  self.assertEqual(self.latest(self.p,'move/몸통박치기')['phase'],'complete')
  self.assertEqual(self.latest(self.foreign,'move/몸통박치기')['phase'],'complete')
  self.assertIs(self.e._active_turn_actor,self.foreign);self.assertIn('기절',self.p.conditions);self.valid()

 def test_not_yet_actual_pre_faint_injury_native_move_completion_then_faint_and_normal_turn_cost(self):
  self.not_yet();before=self.p.injuries;target_hp=self.foreign.hp
  with patch.object(Engine,'d20',return_value=10):self.e.lose_hp(self.p,self.p.hp,source='condition/독')
  proof=self.latest(self.p,'move/몸통박치기')['not_yet_trigger']
  self.assertEqual(self.p.injuries,proof['injuries_before']+1);self.assertGreaterEqual(proof['injuries_before'],before)
  self.assertIn('기절',self.p.conditions)
  self.assertLess(self.foreign.hp,target_hp);self.assertIs(self.e._active_turn_actor,self.foreign)
  self.assertEqual(self.p.pending_action_loss,NOTYET.LOSS)
  row=self.latest(self.p,'move/몸통박치기');self.assertEqual(row['phase'],'complete');self.assertIn('not_yet_trigger',row)
  self.restore();self.e.heal(self.p,self.p.base_max_hp,source_kind='move');self.begin(self.p)
  self.assertEqual(self.p.budget,dict.fromkeys(NOTYET.LOSS,0));self.assertIsNone(self.p.pending_action_loss)
  self.valid()

 def test_not_yet_native_healing_move_still_faints_after_completing_at_positive_hp(self):
  self.not_yet('move/hp회복',target=self.p,edition='local_csv')
  self.e.lose_hp(self.p,self.p.hp,source='condition/독')
  self.assertGreater(self.p.hp,0);self.assertIn('기절',self.p.conditions)
  self.assertEqual(self.latest(self.p,'move/hp회복')['phase'],'complete');self.valid()

 def test_not_yet_rejects_all_three_banned_moves_and_unknown_choice_without_any_cost(self):
  self.not_yet()
  for mid in sorted(NOTYET.BANNED):
   self.e.gm.set_move(self.p,mid,reason='actual known but explicitly forbidden Move')
   self.answer('not_yet',{'move_id':mid,'target_id':self.foreign.entity_id})
   self.reject(lambda:self.e.lose_hp(self.p,self.p.hp,source='condition/독'),'never Explosion')
  self.answer('not_yet',{'move_id':'move/화염방사','target_id':self.foreign.entity_id})
  self.reject(lambda:self.e.lose_hp(self.p,self.p.hp,source='condition/독'),'actual known');self.valid()

 def test_not_yet_minus_true_max_is_inclusive_but_below_it_never_offers(self):
  for below in (False,True):
   with self.subTest(below=below):
    self.setUp();self.not_yet()
    with patch.object(Engine,'d20',return_value=10),observe_actual_heavy_hold(self):
     self.e.lose_hp(self.p,self.p.hp+self.p.base_max_hp+int(below),source='condition/독')
    if below:
     self.assertNotIn(B.NOT_YET,F.state(self.a)['activations']);self.assertNotIn(INTERRUPTS.KEY,vars(self.e))
    else:
     self.assertEqual(self.latest(self.p,'move/몸통박치기')['not_yet_trigger']['hp'],-self.p.base_max_hp)
     event=next(row for row in self.e._heavy_events.values() if row['kind']=='action_taken')
     self.assertEqual(event['status'],'applied');self.assertTrue(event['continuation_reified'])
     self.assertEqual(self.p.hp,-self.p.base_max_hp-event['heavy_consequence']['amount'])
     self.assertEqual(self.p.pending_action_loss,NOTYET.LOSS)
    self.valid()

 def test_not_yet_scene_once_sleeping_owner_and_injury_death_do_not_grant_extra_moves(self):
  self.not_yet();self.e.apply_status(self.a,'잠듦')
  self.e.lose_hp(self.p,self.p.hp,source='condition/독');self.assertNotIn(B.NOT_YET,F.state(self.a)['activations'])
  self.e.cure_status(self.a,'잠듦');self.e.heal(self.p,self.p.base_max_hp,source_kind='move')
  with patch.object(Engine,'d20',return_value=10),observe_actual_heavy_hold(self):self.e.lose_hp(self.p,self.p.hp,source='condition/독')
  self.assertEqual(F.state(self.a)['activations'][B.NOT_YET]['used'],1)
  event=next(row for row in self.e._heavy_events.values() if row['kind']=='action_taken')
  self.assertEqual(event['status'],'applied');self.assertTrue(event['continuation_reified'])
  self.assertEqual(self.p.hp,-event['heavy_consequence']['amount'])
  count=len(self.e._move_completions);self.e.heal(self.p,self.p.base_max_hp,source_kind='move')
  self.e.lose_hp(self.p,self.p.hp,source='condition/독');self.assertEqual(len(self.e._move_completions),count);self.valid()

 def test_not_yet_actual_injury_death_precedes_move_and_late_native_failure_rolls_back(self):
  self.not_yet();self.e.death_enabled=True;self.e.gm.set_injuries(self.p,7,reason='actual seven Injuries before the two HP-marker Injuries')
  with patch.object(Engine,'use_move_on',side_effect=ValueError('late actual Interrupt failure')):
   self.e.lose_hp(self.p,self.p.hp,source='condition/독')
  self.assertTrue(self.p.dead);self.assertEqual(F.state(self.a)['activations'][B.NOT_YET]['used'],1)
  self.assertFalse(getattr(self.e,'_move_completions',{}));self.valid()

 def test_not_yet_late_native_move_failure_and_cold_trigger_forgery_are_atomic(self):
  self.not_yet()
  with patch.object(Engine,'use_move_on',side_effect=ValueError('late actual Interrupt failure')):
   self.reject(lambda:self.e.lose_hp(self.p,self.p.hp,source='condition/독'),'late actual Interrupt failure')
  raw={'id':'forged','actor_id':self.p.entity_id,'source':B.NOT_YET,'priority':0,
       'mode':'reaction','payment':'next','clock':'none','budget':dict(NOTYET.LOSS),'move_id':'move/몸통박치기'}
  self.reject(lambda:INTERRUPTS.queue(self.e,[raw],trigger={'kind':'pre_faint','actor_id':self.p.entity_id,'request_id':'forged'}),'actual live LIFE')
  self.restore();self.reject(lambda:INTERRUPTS.queue(self.e,[raw],trigger={'kind':'pre_faint','actor_id':self.p.entity_id,'request_id':'forged'}),'actual live LIFE');self.valid()


if __name__=='__main__':unittest.main()
