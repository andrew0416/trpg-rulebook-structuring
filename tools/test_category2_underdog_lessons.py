"""Native Underdog Lessons, final-form teaching and scoped HM interpretation."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from unittest.mock import patch
import json,re,unittest
import test_category2_progression_state as _fixture_test_category2_progression_state
from builder import build_pokemon,species_lookup
from engine import Rules
import underdog_edges as U,underdog_lessons as L,pokemon_teaching as T
import learning_grant as LEARN,move_state as M,state_grants as G,downtime as D
from state_codec import dump_engine,load_engine


class UnderdogLessonsTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(Path(__file__).resolve().parents[1],ruleset='all')
 add=_fixture_test_category2_progression_state.ProgressionStateTests.add
 snap=_fixture_test_category2_progression_state.ProgressionStateTests.snap
 restored=_fixture_test_category2_progression_state.ProgressionStateTests.restored
 def setUp(self):
  _fixture_test_category2_progression_state.ProgressionStateTests.setUp(self);self.p=self.pokemon();self.strength()
 def pokemon(self,species='잉어킹',level=35):
  return self.add(build_pokemon(self.r,species,level,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':12}))
 def strength(self):
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=U.STRENGTH,safe=True)
 def teach(self,move='물기',species='갸라도스',**options):
  return self.e.pokemon_activity(self.a,'teach_edge',target=self.p,edge=L.SOURCE,lesson={'species':species,'move_id':move},safe=True,**options)
 def machine(self,code):
  self.a.spec.setdefault('items',{})[code]=self.a.spec.get('items',{}).get(code,0)+1
  instance='actual/'+code
  self.e.pokemon_activity(self.a,'register_machine',instance_id=instance,code=code)
  return instance
 def hm_decision(self,instance,value):
  out=self.e.hm_teaching_policy(self.a,target=self.p,instance_id=instance)
  self.assertEqual(out['status'],'PolicyInputsRequired')
  return {'value':value,'reason':'explicit host interpretation of this actual HM source','scope':out['decision_scope']}
 def test_actual_entry_uses_common_learning_hour_receipt_and_natural_slots(self):
  before=self.e.elapsed_seconds
  with patch.object(LEARN,'learn_moves',wraps=LEARN.learn_moves) as shared:out=self.teach()
  self.assertTrue(any(c.kwargs.get('method')=='underdog_lessons' for c in shared.call_args_list))
  state=M.describe(self.r,self.p.spec)
  self.assertEqual((out['definition_origin']['record'],self.p.spec['tutor_points'],self.e.elapsed_seconds-before),(31,10,3600))
  self.assertEqual((state['classifications']['move/물기'],state['taught_count']),('natural',0))
  self.assertEqual(L.active_final(self.r,self.p.spec),'pokemon/갸라도스')
 def test_actual_strength_receipt_balance_and_owner_required_before_cost(self):
  for kind in ('missing','balance','owner'):
   self.setUp()
   if kind=='missing':self.p=self.pokemon()
   elif kind=='balance':self.p.spec['tutor_points']=0
   else:self.p.spec['trainer_id']=self.p.entity_id
   before=self.snap()
   with self.assertRaises(ValueError):self.teach()
   self.assertEqual(self.snap(),before)
 def test_wrong_final_intermediate_tutor_only_or_future_level_move_refuse(self):
  future=next(mid for mid in L.candidates(self.r,'갸라도스',100) if mid not in L.candidates(self.r,'갸라도스',35))
  for move,species in [('물기','리자몽'),('튀어오르기','잉어킹'),('냉동빔','갸라도스'),(future,'갸라도스')]:
   before=self.snap()
   with self.assertRaises(ValueError):self.teach(move,species)
   self.assertEqual(self.snap(),before)
 def test_duplicate_and_fourth_acquisition_do_not_repay_hour_or_tp(self):
  pool=L.candidates(self.r,'갸라도스',35);self.assertGreaterEqual(len(pool),4)
  self.teach(pool[0]);before=self.snap()
  with self.assertRaises(ValueError):self.teach(pool[0])
  self.assertEqual(self.snap(),before)
  self.teach(pool[1]);self.teach(pool[2]);before=self.snap()
  with self.assertRaisesRegex(ValueError,'three'):self.teach(pool[3])
  self.assertEqual(self.snap(),before)
  self.assertEqual(len([row for row in L.records(self.p.spec) if row['status']=='active']),3)
 def test_branched_final_choice_is_fixed_across_all_acquisitions(self):
  self.p=self.pokemon('이브이');self.strength()
  water=L.candidates(self.r,'샤미드',35);electric=L.candidates(self.r,'쥬피썬더',35)
  self.teach(water[0],'샤미드');before=self.snap()
  with self.assertRaisesRegex(ValueError,'same final'):self.teach(electric[0],'쥬피썬더')
  self.assertEqual(self.snap(),before);self.teach(water[1],'샤미드')
 def test_intermediate_branch_cannot_choose_unrelated_family_terminal(self):
  self.p=self.pokemon('카스쿤');self.strength();before=self.snap()
  with self.assertRaises(ValueError):self.teach(L.candidates(self.r,'뷰티플라이',35)[0],'뷰티플라이')
  self.assertEqual(self.snap(),before)
  self.teach(L.candidates(self.r,'독케일',35)[0],'독케일')
 def test_tm_final_form_permission_reaches_actual_item_consumption_and_taught_slot(self):
  instance=self.machine('TM13');before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance)
  self.assertEqual(self.snap(),before);self.teach();balance=self.p.spec['tutor_points']
  out=self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance)
  self.assertEqual((out['point_cost'],self.p.spec['tutor_points'],self.a.spec['items']['TM13']),(1,balance-1,0))
  self.assertEqual(M.describe(self.r,self.p.spec)['classifications']['move/냉동빔'],'taught')
 def test_hm_permission_requires_scoped_cost_and_keeps_real_instance_daily_limit(self):
  self.teach();instance=self.machine('HM3');before=self.snap()
  with self.assertRaisesRegex(ValueError,'explicit scoped'):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance)
  self.assertEqual(self.snap(),before);decision=self.hm_decision(instance,1);balance=self.p.spec['tutor_points'];seconds=self.e.elapsed_seconds
  out=self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=decision)
  self.assertEqual((out['point_cost'],self.p.spec['tutor_points'],self.e.elapsed_seconds-seconds),(1,balance-1,3600))
  record=self.a.spec['teaching_machines'][instance]
  self.assertEqual((self.a.spec['items']['HM3'],record['status'],record['used_day']),(1,'owned',self.a.spec.get('frequency_state',{}).get('day',0)))
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'already used today'):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=decision)
  self.assertEqual(self.snap(),before);self.restored()
  self.p=self.pokemon();self.strength();self.teach();decision=self.hm_decision(instance,1);before=self.snap()
  with self.assertRaisesRegex(ValueError,'already used today'):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=decision)
  self.assertEqual(self.snap(),before)
  for actor in self.e.everyone:D.new_day(actor)
  balance=self.p.spec['tutor_points']
  self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=decision)
  self.assertEqual((self.p.spec['tutor_points'],self.a.spec['items']['HM3']),(balance-1,1))
  self.restored()
 def test_explicit_zero_hm_cost_preserves_taught_slot_and_roundtrip(self):
  self.teach();instance=self.machine('HM3');balance=self.p.spec['tutor_points']
  out=self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=self.hm_decision(instance,0))
  self.assertEqual((out['point_cost'],self.p.spec['tutor_points']),(0,balance))
  self.assertEqual(M.describe(self.r,self.p.spec)['taught_count'],1);self.restored()
 def test_hm_decision_cannot_be_reused_for_another_target_or_tm(self):
  self.teach();instance=self.machine('HM3');decision=self.hm_decision(instance,1)
  self.p=self.pokemon();self.strength();self.teach();before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=decision)
  self.assertEqual(self.snap(),before);tm=self.machine('TM13');before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=tm,hm_decision=decision)
  self.assertEqual(self.snap(),before)
 def test_hm_tampered_cost_receipt_cannot_be_saved(self):
  self.teach();instance=self.machine('HM3')
  self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance,hm_decision=self.hm_decision(instance,1))
  self.p.spec['move_learning']['move/파도타기']['hm_cost_policy']['values']['point_cost']=0
  with self.assertRaises(ValueError):dump_engine(self.e)
 def test_final_tutor_permission_keeps_actual_mentor_cost_frequency_and_slots(self):
  self.teach();self.a.spec['feats']=[T.MENTOR,T.MOVE_TUTOR];self.a.spec['skills'].update({'매력':5,'포켓몬학':3})
  T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='actual selected teaching skills')
  final=self.r.learnsets['갸라도스'];base=self.r.learnsets['잉어킹']
  own={self.r.move_id(re.sub(r'\s*\(N\)','',str(x),flags=re.I)) for x in base.get('tutor',[])}
  mid=next(self.r.move_id(re.sub(r'\s*\(N\)','',str(x),flags=re.I)) for x in final.get('tutor',[]) if self.r.move_id(re.sub(r'\s*\(N\)','',str(x),flags=re.I)) not in own and self.r.move_id(re.sub(r'\s*\(N\)','',str(x),flags=re.I)) not in M.known(self.r,self.p.spec))
  balance=self.p.spec['tutor_points']
  out=T.teach_feature(self.e,self.a,target=self.p,move_id=mid,feature=T.MOVE_TUTOR,seconds=60,reason='observed Extended tutoring')
  self.assertEqual((out['point_cost'],self.p.spec['tutor_points'],out['classification']),(2,balance-2,'taught'))
 def test_actual_level_growth_keeps_historically_natural_lesson(self):
  self.teach();D.gain_exp_combatant(self.e,self.p,'to next level',stat_choices={36:'spe'})
  self.assertEqual(M.describe(self.r,self.p.spec)['classifications']['move/물기'],'natural');self.restored()
 def test_strength_loss_refunds_once_withdraws_compatibility_and_keeps_learned_move(self):
  self.teach();balance=self.p.spec['tutor_points'];G.replace_baseline(self.e,self.p,'capabilities',[])
  self.assertEqual((self.p.spec['tutor_points'],L.records(self.p.spec)[0]['status']),(balance+2,'refunded'))
  self.assertIsNone(L.active_final(self.r,self.p.spec))
  self.assertEqual(M.describe(self.r,self.p.spec)['classifications']['move/물기'],'natural')
  G.transition(self.e,self.p,lambda e,c:None);self.assertEqual(self.p.spec['tutor_points'],balance+2);self.restored()
  instance=self.machine('TM13');before=self.snap()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'teach_machine',target=self.p,instance_id=instance)
  self.assertEqual(self.snap(),before)
 def test_json_and_gm_restore_keep_active_lesson_and_source(self):
  self.teach();saved=self.e.gm.snapshot();identity=self.p.entity_id
  G.replace_baseline(self.e,self.p,'capabilities',[]);self.e.gm.restore(saved)
  self.p=next(a for a in self.e.gm.everyone if a.entity_id==identity)
  self.assertEqual(L.active_final(self.r,self.p.spec),'pokemon/갸라도스')
  self.restored();self.assertEqual(L.records(self.p.spec)[0]['definition_origin']['record'],31)
 def test_late_common_hour_failure_restores_moves_receipts_tp_clock_and_rng(self):
  import activity_jobs as J
  before=self.snap();native=J.run_fixed
  def fail(*args,**kw):native(*args,**kw);raise ValueError('late actual lesson job failure')
  with patch.object(J,'run_fixed',side_effect=fail):
   with self.assertRaisesRegex(ValueError,'late actual lesson'):self.teach()
  self.assertEqual(self.snap(),before)
 def test_full_total_slots_refuse_natural_lesson_before_hour_or_payment(self):
  moves=['몸통박치기','냉동빔','화염방사','번개','파도타기','하이드로펌프']
  LEARN.learn_moves(self.r,self.p.spec,candidates=moves,selected=moves,method='feature',source='combat/struggle',reason='observed six permanent application grants')
  G.set_baseline(self.p,'moves',self.p.spec['moves']);M.validate_spec(self.r,self.p.spec,require_routes=True);before=self.snap()
  with self.assertRaises(ValueError):self.teach()
  self.assertEqual(self.snap(),before)
 def test_tampered_final_origin_or_strength_provenance_refuses_save(self):
  self.teach();row=L.records(self.p.spec)[0];row['strength_receipt']=len(self.p.spec['learned_poke_edges'])+1
  with self.assertRaises(ValueError):dump_engine(self.e)
 def test_external_json_teaching_uses_native_lesson_and_durable_replay(self):
  path='input/'+self.r.selection.units[L.SOURCE]['source']['file']
  document={'schema':1,'id':'actual-lesson-author','variants':[{'rule_id':L.SOURCE,
   'source':{'file':path,'sha256':sha256((Path(self.r.root)/path).read_bytes()).hexdigest()},
   'inputs':{'final':{'type':'string','authority':'context','question':'Actual final evolution'},
             'move':{'type':'string','authority':'context','question':'Selected level-up Move'}},
   'values':{'teaching_operation':{'kind':'edge','edge':L.SOURCE,'safe':True,
    'lesson':{'species':{'$input':'final'},'move_id':{'$input':'move'}}}}}]}
  args={'context':{'final':'갸라도스','move':'물기'},'request_id':'actual-lesson/json'}
  out=self.e.execute_source_policy_teaching(self.a,self.p,document,**args)
  self.assertEqual(out['status'],'PolicyTeachingCompleted');self.assertFalse(out['replayed'])
  loaded=self.restored();teacher=next(a for a in loaded.gm.everyone if a.entity_id==self.a.entity_id);target=next(a for a in loaded.gm.everyone if a.entity_id==self.p.entity_id)
  before=dump_engine(loaded);again=loaded.execute_source_policy_teaching(teacher,target,document,**args)
  self.assertTrue(again['replayed']);self.assertEqual(dump_engine(loaded),before)


if __name__=='__main__':unittest.main()

