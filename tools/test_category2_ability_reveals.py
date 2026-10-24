"""Exact native information projections for Anticipation and Playtest Frisk."""
from copy import deepcopy
from pathlib import Path
import csv,json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

# Cache both overlay modules before engine.py promotes its canonical directory.
import ability_reveals as REVEALS
import manual_effects as _STAGED_MANUAL_EFFECTS
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
from state_codec import dump_engine,load_engine


class AbilityRevealTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.core=Rules(str(ROOT),ruleset='core')
  cls.playtest=Rules(str(ROOT),ruleset='playtest')

 def pokemon(self,rules,name,*,moves=(),abilities=(),pos=(0,0),nature='용감',item=None,side='party'):
  return Combatant(rules,build_pokemon(rules,name,20,moves=list(moves),abilities=list(abilities),
   pos=pos,nature=nature,item=item,side=side))

 def world(self,rules,user,*targets):
  engine=Engine(rules,seed=314)
  for actor in (user,*targets):engine.gm.add_combatant(actor)
  engine.start_round([user,*targets]);engine.start_of_turn(user)
  return engine

 def end_encounter(self,engine,user):
  engine.end_of_turn(user)
  engine.end_encounter(engine.everyone,round_elapsed_seconds=0)

 def test_exact_source_rows_and_reviewed_registry_shape_are_bound(self):
  with (ROOT/'input/db/abilities.csv').open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.reader(stream))
  self.assertEqual(rows[313],['위험예지','임의 - 신속 행동','대상이 위험예지를 가진 포켓몬에게 효과가 굉장한 기술을 알고있는지 간파합니다. 같은 대상에게는 인카운터마다 한번씩만 쓸수 있으며, 그 대상이 그러한 기술을 알고있는지의 여부만 알려줍니다.','','다수의 포켓몬 또는 트레이너','','대상 - 다수의 포켓몬 또는 트레이너\n대상이 위험예지를 가진 포켓몬에게 효과가 굉장한 기술을 알고있는지 간파합니다. 같은 대상에게는 인카운터마다 한번씩만 쓸수 있으며, 그 대상이 그러한 기술을 알고있는지의 여부만 알려줍니다.','Anticipation'])
  self.assertEqual(rows[414],['통찰 [Playtest]','임의 - 신속 행동','대상은 타입, 특성, 성격, 레벨, 가지고 있다면 현재 착용중인 소지 도구의 이름을 밝힙니다.','','인접한 단일 포켓몬','2-16 Playtest','키워드 - 2-16 Playtest\n대상 - 인접한 단일 포켓몬\n대상은 타입, 특성, 성격, 레벨, 가지고 있다면 현재 착용중인 소지 도구의 이름을 밝힙니다.','Frisk'])
  self.assertEqual(REVEALS.registration(self.core,'위험예지')['source_id'],'ability/위험예지')
  self.assertEqual(REVEALS.registration(self.playtest,'통찰 [Playtest]')['source_id'],'ability/통찰-playtest')
  with self.assertRaises(Exception):REVEALS.registration(self.core,'통찰 [Playtest]')

 def test_anticipation_reveals_only_boolean_for_many_targets_and_pays_one_swift(self):
  user=self.pokemon(self.core,'이상해씨',abilities=['위험예지'])
  strong=self.pokemon(self.core,'파이리',moves=['move/화염방사'],pos=(1,0),side='wild')
  neutral=self.pokemon(self.core,'파이리',moves=['move/몸통박치기'],pos=(2,0),side='wild')
  engine=self.world(self.core,user,strong,neutral)
  result=engine.activate_ability(user,'위험예지',[strong,neutral])
  self.assertEqual(result,{'source':'ability/위험예지','actor_id':user.entity_id,
   'encounter_epoch':1,'reveals':[{'target_id':strong.entity_id,'knows_super_effective_move':True},
   {'target_id':neutral.entity_id,'knows_super_effective_move':False}]})
  self.assertNotIn('move/화염방사',json.dumps(result,ensure_ascii=False))
  self.assertEqual(user.budget['swift'],0)
  self.assertEqual(user.spec[REVEALS.HISTORY]['ability/위험예지'],
   {'encounter_epoch':1,'target_ids':[strong.entity_id,neutral.entity_id]})
  self.assertTrue(engine.validate_state()['valid'],engine.validate_state())

 def test_anticipation_same_target_rejects_atomically_then_new_encounter_resets_scope(self):
  user=self.pokemon(self.core,'이상해씨',abilities=['위험예지'])
  target=self.pokemon(self.core,'파이리',moves=['move/화염방사'],pos=(1,0),side='wild')
  engine=self.world(self.core,user,target);engine.activate_ability(user,'위험예지',target)
  before=(deepcopy(user.budget),deepcopy(user.spec[REVEALS.HISTORY]),list(engine.log_lines))
  with self.assertRaisesRegex(ValueError,'already revealed'):engine.activate_ability(user,'위험예지',target)
  self.assertEqual(before,(user.budget,user.spec[REVEALS.HISTORY],engine.log_lines))
  self.end_encounter(engine,user);engine.start_round([user,target]);engine.start_of_turn(user)
  result=engine.activate_ability(user,'위험예지',target)
  self.assertEqual(result['encounter_epoch'],2)
  self.assertEqual(user.spec[REVEALS.HISTORY]['ability/위험예지'],
   {'encounter_epoch':2,'target_ids':[target.entity_id]})

 def test_anticipation_history_survives_json_and_tamper_fails_persistence(self):
  user=self.pokemon(self.core,'이상해씨',abilities=['위험예지'])
  target=self.pokemon(self.core,'파이리',moves=['move/화염방사'],pos=(1,0),side='wild')
  engine=self.world(self.core,user,target);engine.activate_ability(user,'위험예지',target)
  loaded=load_engine(self.core,json.loads(json.dumps(dump_engine(engine),ensure_ascii=False)))
  actors={actor.entity_id:actor for actor in loaded.everyone};loaded_user=actors[user.entity_id];loaded_target=actors[target.entity_id]
  self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state())
  with self.assertRaisesRegex(ValueError,'already revealed'):
   loaded.activate_ability(loaded_user,'위험예지',loaded_target)
  loaded_user.spec[REVEALS.HISTORY]['ability/위험예지']['encounter_epoch']=99
  self.assertFalse(loaded.validate_state()['valid'])
  with self.assertRaises(Exception):dump_engine(loaded)

 def test_frisk_reveals_exact_current_fields_and_one_actual_held_name(self):
  user=self.pokemon(self.playtest,'피카츄',abilities=['통찰 [Playtest]'])
  target=self.pokemon(self.playtest,'파이리',abilities=['맹화'],pos=(1,0),nature='용감',item='초코바',side='wild')
  engine=self.world(self.playtest,user,target)
  result=engine.activate_ability(user,'통찰 [Playtest]',target)
  self.assertEqual(result,{'source':'ability/통찰-playtest','actor_id':user.entity_id,'reveal':{
   'target_id':target.entity_id,'types':['불꽃'],'abilities':['맹화'],'nature':'용감','level':20,
   'held_item_names':['초코바']}})
  self.assertEqual(set(result['reveal']),{'target_id','types','abilities','nature','level','held_item_names'})
  self.assertEqual(user.budget['swift'],0)
  self.assertNotIn(REVEALS.HISTORY,user.spec)
  self.assertTrue(engine.validate_state()['valid'],engine.validate_state())

 def test_frisk_range_target_and_missing_identity_fail_before_cost(self):
  for mode in ('far','trainer','nature'):
   with self.subTest(mode=mode):
    user=self.pokemon(self.playtest,'피카츄',abilities=['통찰 [Playtest]'])
    if mode=='trainer':
     spec=build_trainer(self.playtest,'trainer target',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),pos=(1,0))
     target=Combatant(self.playtest,spec)
    else:
     target=self.pokemon(self.playtest,'파이리',pos=((3,0) if mode=='far' else (1,0)),nature='용감',side='wild')
    engine=self.world(self.playtest,user,target)
    if mode=='nature':target.spec['nature']=None
    before=(deepcopy(user.budget),list(engine.log_lines),deepcopy(user.spec))
    with self.assertRaises(ValueError):engine.activate_ability(user,'통찰 [Playtest]',target)
    self.assertEqual(before,(user.budget,engine.log_lines,user.spec))

 def test_missing_or_suppressed_ability_and_duplicate_targets_fail_before_cost(self):
  for mode in ('missing','suppressed','duplicate'):
   with self.subTest(mode=mode):
    abilities=[] if mode=='missing' else ['위험예지']
    user=self.pokemon(self.core,'이상해씨',abilities=abilities)
    target=self.pokemon(self.core,'파이리',moves=['move/화염방사'],pos=(1,0),side='wild')
    engine=self.world(self.core,user,target)
    if mode=='suppressed':user.abilities_suppressed=True
    before=(deepcopy(user.budget),deepcopy(user.spec),list(engine.log_lines))
    with self.assertRaises(ValueError):engine.activate_ability(user,'위험예지',[target,target] if mode=='duplicate' else target)
    self.assertEqual(before,(user.budget,user.spec,engine.log_lines))

 def test_frisk_trainer_owner_reveals_adjacent_pokemon_and_pays_native_swift(self):
  rules=self.playtest
  user=Combatant(rules,build_trainer(rules,'Frisk owner',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
   pos=(0,0),extra={'abilities':['통찰 [Playtest]']}))
  target=self.pokemon(rules,'파이리',abilities=['맹화'],pos=(1,0),nature='용감',item='초코바',side='wild')
  engine=self.world(rules,user,target)
  engine.gm.snapshot('trainer Frisk');result=engine.activate_ability(user,'통찰 [Playtest]',target)
  self.assertEqual(result['reveal'],{'target_id':target.entity_id,'types':['불꽃'],'abilities':['맹화'],
   'nature':'용감','level':20,'held_item_names':['초코바']})
  self.assertEqual(user.budget['swift'],0)
  engine.gm.restore('trainer Frisk',reason='restore actual trainer ability before activation')
  loaded=load_engine(rules,json.loads(json.dumps(dump_engine(engine),ensure_ascii=False)))
  actors={c.entity_id:c for c in loaded.everyone}
  self.assertEqual(loaded.activate_ability(actors[user.entity_id],'통찰 [Playtest]',actors[target.entity_id]),result)
  self.assertEqual(actors[user.entity_id].budget['swift'],0)
  self.assertTrue(loaded.validate_state()['valid'],loaded.validate_state())

 def test_anticipation_trainer_owner_still_rejects_before_action(self):
  from native_scenario_fixture import assert_rejected_unchanged
  user=Combatant(self.core,build_trainer(self.core,'Anticipation trainer',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
   pos=(0,0),extra={'abilities':['위험예지']}))
  target=self.pokemon(self.core,'파이리',moves=['move/화염방사'],pos=(1,0))
  engine=self.world(self.core,user,target)
  assert_rejected_unchanged(engine,lambda:engine.activate_ability(user,'위험예지',target),reason_pattern='actual active reveal ability')


if __name__=='__main__':unittest.main(verbosity=2)
