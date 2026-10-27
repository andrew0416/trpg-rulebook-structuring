"""Whole Walk It Off through actual acquisition, elapsed action and recovery."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import common_checks as C,frequency as F,injury_recovery as I,state_codec as CODEC
import trainer_feature_acquisition as T,walk_it_off as WALK,world_entities as W


class WalkItOffTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.scene()
 def scene(self,**policy):
  self.e=Engine(self.rules,seed=14343,**policy);self.e.grid=Grid(12,10)
  self.a=self.actor('walker','trainer',(1,1));self.b=self.actor('other','trainer',(3,1));self.p=self.actor('pokemon','pokemon',(5,1))
 def actor(self,name,kind,pos):
  spec={'id':kind+'/'+name,'name':name,'kind':kind,'level':30,'size':'중형','weight_kg':30,
   'stats':{'hp':23,'atk':20,'def':20,'spa':20,'spd':20,'spe':20},
   'skills':{'육상':4,'집중':3,'곡예':3,'전투':3},'moves':['move/몸통박치기'],
   'abilities':[],'types':['노말'],'classes':[],'feats':[],'edges':[],'items':{},'exp_bank':100,'movement':{'land':6},'movement_basis':'current'}
  a=Combatant(self.rules,spec);self.e.gm.add_combatant(a,pos=pos,side='party',reason='actual Walk It Off participant')
  prepare_body(self.e,a,size='중형',offsets=[(0,0)],reason='actual complete one-cell body');return a
 def acquire(self,actor=None,selection=None,request='walk/acquire'):
  return T.acquire_static(self.e,actor or self.a,WALK.FEATURE,acquisition_request_id=request,selection=selection)
 def use(self,actor=None,**options):
  return self.e.walk_it_off(actor or self.a,duration_minutes=options.pop('duration_minutes',2),reason=options.pop('reason','GM observed two-minute recovery'),**options)
 def injure(self,n,actor=None):self.e.gm.set_injuries(actor or self.a,value=n,reason='actual observed Injury count')
 def hp(self,n,actor=None):self.e.gm.set_hp(actor or self.a,value=n,reason='actual observed HP')
 def reject(self,operation,reason):return assert_rejected_unchanged(self.e,operation,reason_pattern=reason)
 def valid(self):
  result=self.e.validate_state();self.assertTrue(result['valid'],result['issues'])
 def restore(self):
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.b,self.p=[W.actor_index(self.e)[x] for x in ('trainer/walker','trainer/other','pokemon/pokemon')]

 def test_both_printed_skills_actual_trainer_and_independent_hp_stat_acquisition(self):
  self.e.gm.set_skill(self.a,'육상',3,reason='observed Novice Athletics')
  self.reject(self.acquire,'Adept Athletics')
  self.e.gm.set_skill(self.a,'육상',4,reason='actual Adept Athletics');self.e.gm.set_skill(self.a,'집중',2,reason='observed Untrained Focus')
  self.reject(self.acquire,'Novice Focus');self.e.gm.set_skill(self.a,'집중',3,reason='actual Novice Focus')
  self.reject(lambda:self.acquire(self.p),'Trainer|trainer')
  hp,maximum=self.a.stats['hp'],self.a.base_max_hp;receipt=self.acquire()
  self.assertEqual((self.a.stats['hp'],self.a.base_max_hp),(hp+1,maximum+3))
  self.assertEqual(self.a.spec['stats']['hp'],hp);self.assertEqual(self.a.spec['feats'],[WALK.FEATURE])
  self.assertEqual(receipt,self.acquire());self.assertEqual(len(WALK.records(self.a,active=True)),1)
  self.reject(lambda:self.acquire(request='walk/another'),'already acquired')
  self.reject(lambda:T.acquire_static(self.e,self.b,WALK.FEATURE,acquisition_request_id='rank',rank=2),'not Ranked')
  self.restore();self.assertEqual(self.a.stats['hp'],hp+1);self.valid()

 def test_core_selected_source_actual_extended_time_true_maximum_floor_and_self_only(self):
  self.acquire();self.injure(4);self.hp(1);other=(self.b.hp,self.b.injuries);maximum=self.a.base_max_hp
  self.assertNotEqual(maximum%4,0);before=self.e.elapsed_seconds;row=self.use()
  self.assertEqual((row['removed'],self.a.injuries,row['requested'],row['gained']),(1,3,maximum//4,maximum//4))
  self.assertEqual((self.a.hp,self.e.elapsed_seconds-before),(1+maximum//4,120));self.assertEqual(other,(self.b.hp,self.b.injuries))
  self.assertEqual(self.a._action_history[-1],'extended');self.assertEqual(I.healed_today(self.a),0)
  self.assertEqual(row['source']['edition'],'core');self.assertEqual(row['source']['interpretation']['pages'],[63]);self.valid()

 def test_csv43_source_is_selected_actual_acquisition_and_native_recovery(self):
  receipt=self.acquire(selection={'edition':'local_csv'});self.injure(1);self.hp(10)
  row=self.e.manual_feat(self.a,'기분전환',adjustment={'duration_minutes':1,'reason':'GM actual one-minute CSV recovery'})
  self.assertEqual(receipt['snapshot']['source']['record'],43);self.assertEqual(row['source'],receipt['snapshot']['source'])
  self.assertEqual((row['removed'],self.a.injuries,self.e.elapsed_seconds),(1,0,60));self.assertEqual(I.healed_today(self.a),0)
  self.restore();self.valid();self.reject(self.use,'daily use exhausted')

 def test_translation_source_selection_and_no_invented_or_changed_acquisition_edition(self):
  self.reject(lambda:self.acquire(selection={'edition':'playtest-invented'}),'source')
  self.reject(lambda:self.acquire(selection={'edition':'local_csv','record':999}),'source selection')
  self.acquire(selection={'edition':'local_translation'});self.hp(1);row=self.use()
  self.assertEqual(row['source']['edition'],'local_translation');self.assertNotIn('interpretation',row['source'])
  self.reject(lambda:self.acquire(selection={'edition':'core'}),'replay cannot change');self.valid()

 def test_daily_frequency_survives_codec_and_scene_but_new_day_allows_next_use(self):
  self.acquire();self.injure(2);self.hp(1);self.use();self.restore();self.reject(self.use,'daily use exhausted')
  self.e.end_encounter();self.reject(self.use,'daily use exhausted')
  F.new_day(self.a);row=self.use();self.assertEqual((row['removed'],self.a.injuries),(1,0));self.assertEqual(len(self.a.spec[WALK.KEY]),2);self.valid()

 def test_exempt_removal_after_spent_ordinary_pool_does_not_refund_or_consume_it(self):
  self.acquire();self.injure(6)
  for _ in range(3):self.assertEqual(self.e.recover_injury(self.a,source='trainer_ap',duration_minutes=1,reason='actual ordinary AP recovery')['recovered'],1)
  self.assertEqual((self.a.injuries,I.healed_today(self.a)),(3,3));before=self.a.spec['ap_removed'];row=self.use()
  self.assertEqual((row['removed'],self.a.injuries,I.healed_today(self.a),self.a.spec['ap_removed']),(1,2,3,before))
  self.assertIs(self.e.recover_injury(self.a,source='trainer_ap',duration_minutes=1,reason='ordinary pool remains exhausted'),False)
  self.assertEqual(self.a.spec[I.EXEMPT][-1]['source'],WALK.FEATURE);self.valid()

 def test_exempt_use_first_leaves_all_three_ordinary_injury_recoveries(self):
  self.acquire();self.injure(4);self.use();self.assertEqual(I.healed_today(self.a),0)
  for _ in range(3):self.assertEqual(self.e.recover_injury(self.a,source='trainer_ap',duration_minutes=1,reason='actual ordinary AP recovery')['recovered'],1)
  self.assertEqual((self.a.injuries,I.healed_today(self.a)),(0,3));self.valid()

 def test_zero_injuries_still_heals_and_full_or_above_ceiling_never_loses_hp(self):
  self.acquire();self.hp(1);row=self.use();self.assertEqual((row['removed'],self.a.injuries),(0,0));self.assertEqual(row['gained'],self.a.base_max_hp//4)
  F.new_day(self.a);self.injure(4);self.hp(self.a.base_max_hp);before=self.a.hp;row=self.use()
  self.assertEqual((row['removed'],self.a.injuries,row['gained'],self.a.hp),(1,3,0,before));self.valid()

 def test_healing_clamps_to_ceiling_after_own_injury_removal(self):
  self.acquire();self.injure(4);base=self.a.base_max_hp;self.hp(base*7//10-1);row=self.use()
  self.assertEqual((self.a.injuries,self.a.hp,row['gained']),(3,base*7//10,1));self.assertGreater(row['requested'],1);self.valid()

 def test_missing_duration_or_reason_stays_pending_and_malformed_inputs_are_atomic(self):
  self.acquire();before=self.e.export_state()
  for options in ({},{'duration_minutes':1},{'reason':'GM duration not supplied'}):
   self.assertIsInstance(self.e.walk_it_off(self.a,**options),C.PendingDecision);self.assertEqual(self.e.export_state(),before)
  for minutes in (0,-1,True,1.5):self.reject(lambda minutes=minutes:self.use(duration_minutes=minutes),'duration minutes')
  self.reject(lambda:self.use(reason=''),'duration reason')

 def test_real_encounter_and_nonacting_user_reject_without_time_or_daily_payment(self):
  self.acquire();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
  self.reject(self.use,'cannot run during an encounter');self.e.end_of_turn(self.a);self.e.end_round();self.e.end_encounter()
  self.e.apply_status(self.a,'잠듦');self.reject(self.use,'Extended action unavailable');self.e.cure_status(self.a,'잠듦')
  self.use();self.valid()

 def test_missing_forged_ownership_foreign_actor_and_other_target_are_not_authority(self):
  self.reject(self.use,'actual acquired')
  self.a.spec['feats'].append(WALK.FEATURE);self.reject(self.use,'actual acquired');self.a.spec['feats'].remove(WALK.FEATURE)
  self.acquire();foreign=Combatant(self.rules,deepcopy(self.a.spec));self.reject(lambda:self.use(foreign),'actual|registered|world')
  self.reject(lambda:self.e.manual_feat(self.a,WALK.FEATURE,self.b,adjustment={'duration_minutes':1,'reason':'invalid other recipient'}),'only its actual user')

 def test_failure_after_elapsed_job_or_injury_removal_rolls_back_entire_native_state(self):
  self.acquire();self.injure(2);self.hp(1)
  with patch.object(I,'heal_exempt',side_effect=ValueError('injected injury failure')):self.reject(self.use,'injected injury failure')
  with patch.object(Engine,'heal',side_effect=ValueError('injected HP failure')):self.reject(self.use,'injected HP failure')
  row=self.use();self.assertEqual(row['removed'],1);self.valid()

 def test_actual_respiration_injuries_keep_their_protected_floor(self):
  self.acquire();self.e.observe_breathing(self.a,air_available=False,medium='airless',reason='actual deprivation',timing_policy='completed_round_after_grace')
  self.e.advance_time(70,[self.a]);self.assertGreater(self.a.injuries,0);row=self.use(duration_minutes=1)
  self.assertEqual(row['removed'],0);self.assertEqual(row['injuries_before'],row['injuries_after']);self.assertEqual(I.healed_today(self.a),0)
  self.assertEqual(I.exempt_remaining(self.a,WALK.FEATURE,1),1);self.valid()

 def test_native_restore_rejects_changed_use_job_quota_and_hp_tag(self):
  self.acquire();self.injure(2);self.hp(1);self.use();self.restore();snapshot=self.e.gm.snapshot('walk')
  self.a.spec[WALK.KEY][-1]['removed']=0;self.assertFalse(self.e.validate_state()['valid']);self.e.gm.restore(snapshot)
  self.a.spec['frequency_state']['activations'][WALK.FEATURE]['used']=0;self.assertFalse(self.e.validate_state()['valid']);self.e.gm.restore(snapshot)
  row=self.a.spec[WALK.KEY][-1];self.e._activity_jobs['jobs'][row['job_id']]['source']='feat/other';self.assertFalse(self.e.validate_state()['valid']);self.e.gm.restore(snapshot)
  self.a.spec.pop('frequency_state')
  with self.assertRaisesRegex(ValueError,'Daily calendar missing'):WALK.validate(self.e)
  self.assertNotIn('frequency_state',self.a.spec);self.e.gm.restore(snapshot)
  sid='feature:'+self.a.entity_id+':'+WALK.FEATURE;self.a.spec['state_grants']['stat_sources']['hp']['sources'].pop(sid)
  self.assertFalse(self.e.validate_state()['valid'])

 def test_actual_retraining_removes_only_owned_hp_tag_not_past_healing_or_use_evidence(self):
  original=self.a.stats['hp'];self.acquire();self.injure(2);self.hp(1);row=self.use()
  hp,injuries=self.a.hp,self.a.injuries;bank=self.a.spec['exp_bank']
  result=self.e.retrain_trainer_source(self.a,WALK.FEATURE,request_id='walk/retrain',
   reason='actual Trainer elects retraining',gm_decision={'allowed':True,'reason':'GM reviewed narrative and prerequisites'},retained_dependencies={})
  self.assertEqual((self.a.stats['hp'],self.a.hp,self.a.injuries),(original,hp,injuries))
  self.assertEqual(self.a.spec['exp_bank'],bank-result['xp_paid']);self.assertNotIn(WALK.FEATURE,self.a.spec['feats'])
  self.assertEqual(self.a.spec[WALK.KEY],[row]);self.assertEqual(len(WALK.records(self.a)),1);self.assertEqual(WALK.records(self.a,active=True),[])
  self.restore();self.valid();self.reject(self.use,'actual acquired')

 def test_actual_optional_session_refresh_permits_one_whole_use_without_refilling_ordinary_pool(self):
  self.scene(session_frequency=True,defer_session_refresh=False);self.e.begin_session('walk/session1')
  self.acquire();self.injure(4);self.hp(self.a.base_max_hp);first=self.use()
  self.assertEqual((first['removed'],first['gained'],first['exempt_cap']),(1,0,1));self.reject(self.use,'daily use exhausted')
  self.assertEqual(self.e.begin_session('walk/session1'),'unchanged');self.reject(self.use,'daily use exhausted')
  self.restore();self.assertEqual(self.e.begin_session('walk/session2'),'refreshed');second=self.use()
  self.assertEqual((second['removed'],second['exempt_cap'],self.a.injuries,I.healed_today(self.a)),(1,2,2,0))
  self.reject(self.use,'daily use exhausted');self.reject(lambda:self.e.begin_session('walk/session1'),'past session ID')
  F.new_day(self.a);self.reject(self.use,'daily use exhausted');self.valid()
  self.e.begin_session('walk/session3');third=self.use();self.assertEqual((third['removed'],third['exempt_cap']),(1,1));self.valid()

 def test_session_source_cap_cannot_be_inflated_or_its_exempt_ledger_duplicated(self):
  self.scene(session_frequency=True,defer_session_refresh=False);self.e.begin_session('walk/session1')
  self.acquire();self.injure(2);self.use();self.restore();snapshot=self.e.gm.snapshot('walk session')
  row=self.a.spec[WALK.KEY][-1];row['exempt_cap']=100;row['integrity']=WALK._seal(row)
  self.assertFalse(self.e.validate_state()['valid']);self.e.gm.restore(snapshot)
  duplicate=deepcopy(self.a.spec[I.EXEMPT][-1]);duplicate['daily_cap']=2;self.a.spec[I.EXEMPT].append(duplicate)
  self.assertFalse(self.e.validate_state()['valid']);self.e.gm.restore(snapshot);self.valid()


if __name__=='__main__':unittest.main()
