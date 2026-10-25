"""Whole general Press through actual no-choice acquisition and native actions."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv,hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged,assert_rejections_unchanged
import trainer_feature_acquisition as A,taskmaster as T,state_codec as CODEC
import world_entities as W,combat_timing as TIMING,action_points as AP,temporary_hp as TEMP,pokemon_entities as P


class PressTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')
 def setUp(self):
  old=self.rules.rulings;self.rules.rulings=deepcopy(old);self.addCleanup(setattr,self.rules,'rulings',old)
  self.e=Engine(self.rules,seed=643647);self.e.grid=Grid(8,8)
  self.a=self.actor('press-trainer','trainer',(0,1))
  self.b=self.actor('other-trainer','trainer',(3,1))
  self.p=self.actor('pressed','pokemon',(1,1),owner=self.a)
  self.q=self.actor('unpressed','pokemon',(1,2),owner=self.a)
  self.foreign=self.actor('foreign','pokemon',(3,2),owner=self.b)
 def actor(self,name,kind,pos,owner=None):
  spec={'id':kind+'/'+name,'name':name,'kind':kind,'level':20,'size':'중형','weight_kg':30,
   'stats':{'hp':23,'atk':15,'def':15,'spa':15,'spd':15,'spe':15},
   'skills':{'협박':5,'명령':3,'직감':3,'육상':3},'moves':['move/몸통박치기'],
   'abilities':[],'types':['노말'],'classes':[],'feats':[],'edges':[],'items':{},'exp_bank':100,
   'movement':{'land':6},'movement_basis':'current'}
  if owner:spec.update(trainer_id=owner.entity_id,trainer=owner.name)
  c=Combatant(self.rules,spec);self.e.gm.add_combatant(c,pos=pos,side='party',reason='actual general Press participant')
  prepare_body(self.e,c,size='중형',offsets=[(0,0)],reason='actual complete medium body')
  if owner:self.e.gm.observe_loyalty(c,6,reason='actual observed willing Pokemon')
  return c
 def acquire(self,actor=None,**options):
  return A.acquire_static(self.e,actor or self.a,T.PRESS_ACTION,
   acquisition_request_id=options.pop('request','press/acquire'),**options)
 def use(self,*,actor=None,target=None,**options):
  options.setdefault('stats',['atk','spe'])
  return self.e.manual_feat(actor or self.a,T.PRESS_ACTION,target or self.p,adjustment=options)
 def combat(self):
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def reject(self,fn,reason):return assert_rejected_unchanged(self.e,fn,reason_pattern=reason)
 def valid(self):
  report=self.e.validate_state();self.assertTrue(report['valid'],report['issues'])
 def restore(self):
  ids=[x.entity_id for x in (self.a,self.b,self.p,self.q,self.foreign)]
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  index=W.actor_index(self.e);self.a,self.b,self.p,self.q,self.foreign=[index[x] for x in ids]
 def skill(self,skill='명령',*,actor=None,target=None,purpose='pokemon_obedience'):
  return self.e.skill_check(actor or self.a,skill,8,fixed=[2,2,2],
   skill_context=None if purpose is None else {'purpose':purpose,'reason':'GM observes this actual '+purpose+' skill check'},skill_target=target or self.p)

 def test_saved_core_and_retained_csv_bind_the_same_full_press_contract_without_false_dedupe(self):
  contract=json.loads((ROOT/'data/press-source-contract.json').read_text(encoding='utf-8'))
  source=ROOT/'input/db/feats.csv'
  self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),contract['retained_csv']['file_sha256'])
  with source.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
  self.assertEqual(rows[4],contract['retained_csv']['cells'])
  self.assertEqual(contract['retained_csv']['id'],'C2CSV/input/db/feats.csv:R5:main')
  self.assertIsNone(contract['retained_csv']['dedupe_target'])
  self.assertEqual(contract['source']['span'],[643,647]);self.assertEqual(contract['english']['pages'],[59])
  self.assertEqual(contract['mandatory_unanswered_questions'],[])

 def test_general_acquisition_needs_adept_intimidate_not_taskmaster_and_replays_actual_receipt(self):
  self.e.gm.set_skill(self.a,'협박',3,reason='observed below Adept Intimidate')
  self.reject(self.acquire,'Adept 협박')
  self.e.gm.set_skill(self.a,'협박',4,reason='observed actual Adept Intimidate')
  receipt=self.acquire();self.assertEqual(receipt['source']['span'],[643,647])
  self.assertEqual(receipt['source']['clause_id'],'input/ch03-skills-edges-feats.md:643-647')
  self.assertEqual(receipt['snapshot']['skill'],'협박');self.assertEqual(receipt['snapshot']['rank'],4)
  self.assertEqual(self.a.spec['feats'],[T.PRESS_ACTION]);self.assertEqual(self.a.spec['classes'],[])
  self.assertEqual(self.acquire(),receipt)
  self.e.gm.set_skill(self.a,'협박',2,reason='later rank cannot rewrite acquisition-time evidence')
  self.assertEqual(self.acquire(),receipt);self.restore();self.assertEqual(self.acquire(),receipt);self.valid()

 def test_acquisition_rejects_nontrainer_duplicates_and_invented_choices_without_changes(self):
  self.reject(lambda:self.acquire(self.p),'trainer')
  assert_rejections_unchanged(self.e,[lambda:self.acquire(selection={'edition':'invented'}),
   lambda:self.acquire(branch='atk'),lambda:self.acquire(rank=1)],
   reason_pattern=['no optional acquisition selection','no acquired branch','not Ranked'])
  self.acquire();self.reject(lambda:self.acquire(request='press/duplicate'),'already acquired');self.valid()

 def test_native_press_uses_true_maximum_hp_cures_only_sleep_raises_two_distinct_stats_and_keeps_loyalty_observed(self):
  self.acquire();self.e.gm.set_injuries(self.p,value=2,reason='actual lowered maximum HP ceiling')
  self.e.gm.set_hp(self.p,value=self.p.max_hp,reason='actual current HP at injured ceiling')
  self.assertNotEqual(self.p.base_max_hp,self.p.max_hp)
  TEMP.grant(self.e,self.p,9,provenance={'source':'actual prior temporary HP'})
  self.e.apply_status(self.p,'잠듦');self.e.apply_status(self.p,'독')
  self.combat();before=self.p.hp;stages=deepcopy(self.p.stages);ap=AP.available(self.a);loyalty=P.loyalty_projection(self.p,viewer='gm',engine=self.e)
  result=self.use();self.assertEqual(result['source'],T.PRESS_ACTION)
  cost=self.p.base_max_hp//6
  self.assertEqual(self.p.hp,before-max(0,cost-9));self.assertEqual(self.p.temp_hp,max(0,9-cost))
  self.assertEqual(before+9-self.p.hp-self.p.temp_hp,cost)
  self.assertNotIn('잠듦',self.p.conditions);self.assertIn('독',self.p.conditions)
  self.assertEqual((self.p.stages['atk'],self.p.stages['spe']),(stages['atk']+1,stages['spe']+1))
  self.assertTrue(all(self.p.stages[x]==stages[x] for x in ('def','spa','spd')))
  self.assertEqual((self.a.budget['standard'],self.a.budget['swift']),(0,1))
  self.assertEqual(AP.available(self.a),ap);self.assertEqual(P.loyalty_projection(self.p,viewer='gm',engine=self.e),loyalty)
  self.assertFalse(TIMING.records(self.a));self.valid()

 def test_optional_bonus_reaches_any_actual_skill_check_only_for_this_pokemon_obeying_this_trainer(self):
  self.acquire();self.combat();self.use(obedience=True)
  self.assertEqual(self.skill(),(True,8));self.assertEqual(self.skill('직감'),(True,8))
  self.assertEqual(self.skill(target=self.q),(False,6))
  self.assertEqual(self.skill(actor=self.b),(False,6))
  self.assertEqual(self.skill(purpose='singing'),(False,6));self.assertEqual(self.skill(purpose=None),(False,6))
  assert_rejections_unchanged(self.e,[
   lambda:self.e.skill_check(self.a,'명령',8,fixed=[2,2,2],skill_context={'purpose':'invented','reason':'GM observed actual unknown purpose'},skill_target=self.p),
   lambda:self.e.skill_check(self.a,'명령',8,fixed=[2,2,2],skill_context={'purpose':'pokemon_obedience'},skill_target=self.p)],
   reason_pattern='known GM skill purpose and reason required')
  self.assertEqual(self.skill(),(True,8));self.assertEqual(len(TIMING.records(self.a)),1);self.valid()

 def test_declining_optional_bonus_still_performs_all_press_effects(self):
  self.acquire();self.combat();before=self.p.hp;self.use(obedience=False)
  self.assertEqual(self.p.hp,before-self.p.base_max_hp//6)
  self.assertEqual((self.p.stages['atk'],self.p.stages['spe']),(1,1))
  self.assertEqual(self.skill(),(False,6));self.assertFalse(TIMING.records(self.a));self.valid()

 def test_bonus_survives_turn_end_and_codec_then_expires_at_actual_round_end(self):
  self.acquire();self.combat();self.use(obedience=True);self.e.end_of_turn(self.a)
  self.assertEqual(self.skill(),(True,8));self.restore();self.assertEqual(self.skill('직감'),(True,8))
  self.e.end_round();self.assertEqual(self.skill(),(False,6));self.assertFalse(TIMING.records(self.a));self.valid()

 def test_at_will_repeats_in_successive_rounds_with_standard_cost_and_current_half_rank(self):
  self.acquire();self.combat();self.use(obedience=True)
  self.reject(self.use,'Standard action permission')
  self.e.end_of_turn(self.a);self.e.end_round();self.e.gm.set_skill(self.a,'협박',6,reason='actual current Master rank')
  self.combat();self.use(stats=['def','spd'],obedience=True)
  self.assertEqual((self.p.stages['def'],self.p.stages['spd']),(1,1));self.assertEqual(self.skill(),(True,9))
  self.assertEqual(self.a.budget['standard'],0);self.valid()

 def test_invalid_targets_choices_missing_acquisition_and_turn_permission_are_atomic(self):
  self.combat();self.reject(self.use,'actual Press and Adept Intimidate')
  self.acquire()
  assert_rejections_unchanged(self.e,[lambda:self.use(stats=['atk','atk']),lambda:self.use(stats=['hp','def']),
   lambda:self.use(stats=['atk']),lambda:self.use(obedience=1),lambda:self.use(target=self.foreign),
   lambda:self.use(target=self.b)],reason_pattern=['two distinct','two distinct','two distinct',
   'explicit Press obedience choice','different trainer','Pokemon target'])
  self.e.gm.set_hp(self.q,value=0,reason='actual fainted own Pokemon')
  self.reject(lambda:self.use(target=self.q),'conscious Press target')
  self.e.end_of_turn(self.a);self.reject(self.use,'Standard action permission');self.valid()

 def test_late_native_effect_failure_rolls_back_hp_cure_stages_action_and_rng(self):
  self.acquire();self.e.apply_status(self.p,'잠듦');self.combat()
  original=Engine.change_stage
  def fail(e,c,stat,amount,*args,**kwargs):
   result=original(e,c,stat,amount,*args,**kwargs)
   if stat=='spe':raise ValueError('late actual Press stage failure')
   return result
  with patch.object(Engine,'change_stage',fail):self.reject(lambda:self.use(obedience=True),'late actual Press stage failure')
  self.valid()


if __name__=='__main__':unittest.main()
