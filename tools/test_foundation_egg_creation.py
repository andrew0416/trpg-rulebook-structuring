"""Actual qualified parents, data-driven egg production and fresh native birth."""
from pathlib import Path
from copy import deepcopy,copy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_policy_training as fixtures
from builder import build_pokemon,build_trainer
import creation_egg as E,pokemon_entities as P,pokemon_party as PARTY,pokemon_progression as PROGRESSION,world_entities as W
import learning_grant as L,move_state as M,activity_jobs as J
from state_codec import dump_engine,load_engine


class EggTests(unittest.TestCase):
 setUpClass=classmethod(fixtures.PolicyTrainingTests.setUpClass.__func__)
 add=fixtures.PolicyTrainingTests.add
 def setUp(self):
  fixtures.PolicyTrainingTests.setUp(self);self.a.spec['edges']=['edge/브리더']
  self.parents=[self.add(build_pokemon(self.r,'이상해씨',5,moves=['move/뿌리박기'],abilities=['심록'],extra={'trainer_id':self.a.entity_id,'gender':'female'})),
    self.add(build_pokemon(self.r,'이상해씨',5,moves=[],abilities=['심록'],extra={'trainer_id':self.a.entity_id,'gender':'male'}))]
 def policy(self,index=0):return json.loads((ROOT/'data/examples/egg-creation.json').read_text(encoding='utf8'))[index]
 def create(self,value=None,**observations):
  return self.e.create_declared_egg(self.a,self.parents,self.policy() if value is None else value,
    **dict({'request_id':'egg','compatible':True,'species':'pokemon/이상해씨','inheritance_moves':['move/뿌리박기'],'reason':'actual observed breeding'},**observations))
 def choices(self):return {'gender':'male','nature':'노력','abilities':['심록'],'moves':[],'special_appearance':False,'inheritance_moves':['move/뿌리박기']}
 def hatch(self,row,**observations):return self.e.hatch_declared_egg(self.a,row['entity_id'],**dict({'name':'child','ready':True,'reason':'observed actual hatch','choices':self.choices()},**observations))
 def snap(self):return dump_engine(self.e)
 def test_declared_parent_knowledge_and_native_learning_produce_a_fresh_child(self):
  before=self.snap();plan=self.e.plan_egg_creation(self.a,self.parents,self.policy(),compatible=True,species='이상해씨',inheritance_moves=['move/뿌리박기'],reason='actual observed parents')
  self.assertEqual(plan['inheritance_candidates'],['move/뿌리박기']);self.assertEqual(before,self.snap())
  row=self.create();self.assertEqual(self.e.elapsed_seconds,120);self.assertFalse(row['hatched'])
  self.assertNotIn('stats',row);self.assertEqual(row['hatch_level'],1)
  result=self.hatch(row);child=result['pokemon'];self.assertEqual(child.level,1);self.assertEqual(child.spec['tutor_points'],1)
  self.assertEqual(child.spec[PROGRESSION.LEVEL_STATE]['origin'],'hatch');self.assertEqual(child.spec[PROGRESSION.LEVEL_STATE]['awards'],[])
  self.assertEqual(L.validate(self.r,child.spec),None);self.assertNotIn('move/뿌리박기',child.spec['moves'])
  self.assertEqual(child.spec['inheritance_moves'],['move/뿌리박기'])
  self.assertNotIn('move/뿌리박기',child.spec.get('move_learning',{}));self.assertTrue(self.e.validate_state()['valid'])
  before=self.snap()
  with self.assertRaises(ValueError):self.hatch(row)
  self.assertEqual(before,self.snap())
 def test_unknown_compatibility_and_parent_information_do_not_mint_an_egg_or_spend_time(self):
  before=self.snap()
  for compatible in (None,False,1):
   with self.assertRaisesRegex(ValueError,'compatible'):self.create(compatible=compatible)
   self.assertEqual(before,self.snap())
  self.parents[0].spec.pop('gender');before=self.snap()
  with self.assertRaisesRegex(ValueError,'mother gender'):self.create()
  self.assertEqual(before,self.snap())
 def test_unqualified_provider_duplicate_copy_and_wrong_species_reject(self):
  before=self.snap()
  for parents in ([self.parents[0],self.parents[0]],[copy(self.parents[0]),self.parents[1]]):
   with self.assertRaises(ValueError):self.e.create_declared_egg(self.a,parents,self.policy(),request_id='bad',compatible=True,species='이상해씨',inheritance_moves=[],reason='actual parents')
   self.assertEqual(before,self.snap())
  with self.assertRaisesRegex(ValueError,'outside'):self.create(species='pokemon/꼬부기')
  self.a.spec['edges']=[];before=self.snap()
  with self.assertRaisesRegex(ValueError,'provider edge'):self.create()
  self.assertEqual(before,self.snap())
 def test_unlearned_species_list_move_and_all_parent_knowledge_are_not_assumed(self):
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'required actual parents'):self.create(inheritance_moves=['move/망각술'])
  with self.assertRaisesRegex(ValueError,'required actual parents'):self.create(self.policy(1))
  self.assertEqual(before,self.snap())
  self.e.gm.set_move(self.parents[1],'move/뿌리박기',True,reason='observed father also knows this move')
  row=self.create(self.policy(1));self.assertEqual(row['hatch_level'],3)
  before=self.snap()
  with self.assertRaisesRegex(ValueError,'waiting time'):self.hatch(row)
  self.assertEqual(before,self.snap());self.e.advance_time(90,[self.a,*self.parents])
  child=self.hatch(row,ready=None)['pokemon'];self.assertEqual((child.level,child.spec['tutor_points']),(3,2))
 def test_altering_only_birth_values_changes_native_stats_and_budgets_without_fake_levelup_awards(self):
  value=self.policy();value['hatch'].update(level=10,tutor_points=4);row=self.create(value)
  child=self.hatch(row)['pokemon'];self.assertEqual((child.level,child.spec['tutor_points']),(10,4))
  self.assertEqual(child.spec[PROGRESSION.LEVEL_STATE]['awards'],[]);self.assertTrue(child.spec['initial_allocation'])
 def test_late_creation_failure_rolls_back_work_parent_state_and_rng(self):
  before=self.snap()
  with patch.object(P,'prepare_egg',side_effect=ValueError('late egg construction')):
   with self.assertRaisesRegex(ValueError,'late egg construction'):self.create()
  self.assertEqual(before,self.snap());self.create();self.assertEqual(self.e.elapsed_seconds,120)
 def test_late_birth_placement_failure_rolls_back_child_egg_and_roster(self):
  row=self.create();before=self.snap()
  with patch.object(PARTY,'finish_hatch',side_effect=ValueError('late birth placement')):
   with self.assertRaisesRegex(ValueError,'late birth placement'):self.hatch(row)
  self.assertEqual(before,self.snap());self.hatch(row)
 def test_missing_hatch_choices_readiness_and_unqualified_known_moves_are_explicit(self):
  row=self.create();before=self.snap()
  for ready in (None,False,1):
   with self.assertRaisesRegex(ValueError,'readiness'):self.hatch(row,ready=ready)
   self.assertEqual(before,self.snap())
  value=self.choices();value.pop('gender')
  with self.assertRaises(ValueError):self.hatch(row,choices=value)
  value=self.choices();value['moves']=['move/망각술']
  with self.assertRaisesRegex(ValueError,'outside'):self.hatch(row,choices=value)
  value=self.choices();value['inheritance_moves']=[]
  with self.assertRaisesRegex(ValueError,'inheritance differs'):self.hatch(row,choices=value)
  self.assertEqual(before,self.snap())
 def test_transfer_json_restore_and_request_replay_preserve_actual_parentage_and_source(self):
  row=self.create();other=self.add(build_trainer(self.r,'receiver',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),skills={'명령':3},extra={'edges':[]}))
  self.e.gm.transfer_egg(self.a,other,row['entity_id'],reason='real egg gift',request_id='gift')
  loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)));actors=W.actor_index(loaded);before=dump_engine(loaded)
  out=loaded.create_declared_egg(actors[self.a.entity_id],[actors[p.entity_id] for p in self.parents],self.policy(),request_id='egg',compatible=True,species='pokemon/이상해씨',inheritance_moves=['move/뿌리박기'],reason='actual observed breeding')
  self.assertEqual(out['entity_id'],row['entity_id']);self.assertEqual(out['owner_id'],other.entity_id);self.assertEqual(before,dump_engine(loaded))
  child=loaded.hatch_declared_egg(actors[other.entity_id],row['entity_id'],name='gift child',ready=True,reason='actual recipient observes readiness',choices=self.choices())['pokemon']
  self.assertEqual(child.spec['trainer_id'],other.entity_id);self.assertEqual(child.spec['inheritance_moves'],['move/뿌리박기'])
  self.assertNotIn('move/뿌리박기',child.spec['moves'])
 def test_changed_parentage_inheritance_birth_level_and_gm_snapshot_are_checked(self):
  row=self.create();actual=P.egg_index(self.e)[row['entity_id']][1];snapshot=self.e.gm.snapshot()
  for key,value in (('parents',list(reversed(actual['parents']))),('inheritance_moves',[]),('hatch_level',10)):
   original=deepcopy(actual[key]);actual[key]=value
   self.assertFalse(self.e.validate_state()['valid']);actual[key]=original
  self.hatch(row);self.e.gm.restore(snapshot);self.assertFalse(P.egg_index(self.e)[row['entity_id']][1]['hatched'])
  child=self.hatch(row)['pokemon'];self.assertEqual(child.level,1)
 def test_separate_native_rosters_keep_returned_child_identity_and_rollback(self):
  self.e.everyone=list(self.e.gm.everyone);engine_roster=self.e.everyone;gm_roster=self.e.gm.everyone
  row=self.create();before=self.snap()
  with patch.object(PARTY,'finish_hatch',side_effect=ValueError('late roster placement')):
   with self.assertRaisesRegex(ValueError,'late roster placement'):self.hatch(row)
  self.assertEqual(before,self.snap());self.assertIs(self.e.everyone,engine_roster);self.assertIs(self.e.gm.everyone,gm_roster)
  child=self.hatch(row)['pokemon']
  self.assertIs(self.e.everyone,engine_roster);self.assertIs(self.e.gm.everyone,gm_roster)
  self.assertIs(next(c for c in engine_roster if c.entity_id==child.entity_id),child)
  self.assertIs(next(c for c in gm_roster if c.entity_id==child.entity_id),child)
  self.assertIs(W.actor_index(self.e)[child.entity_id],child);self.assertTrue(self.e.validate_state()['valid'])
 def test_observed_birth_facts_remain_with_the_actual_child_after_restore(self):
  selected_nature=next(name for name,row in self.r.mech('pokemon/natures')['by_name'].items() if row['up']!=row['down'])
  birth_fields=('species','gender','nature','abilities','moves')
  parent_facts=deepcopy([{field:p.spec.get(field) for field in birth_fields} for p in self.parents]);children=[]
  for index,(gender,special,nature) in enumerate((('female',True,selected_nature),('male',False,'노력'))):
   with self.subTest(gender=gender,special=special):
    row=self.create(request_id='observed-birth-'+str(index))
    self.assertIsNone(row['gm_hatch_details']);self.assertNotIn('pokemon_id',row)
    selected=self.choices();selected.update(gender=gender,nature=nature,special_appearance=special)
    if index==0:
     before=self.snap()
     for field in ('gender','nature','abilities','special_appearance'):
      incomplete=deepcopy(selected);incomplete.pop(field)
      with self.assertRaises(ValueError):self.hatch(row,choices=incomplete)
      self.assertEqual(before,self.snap())
     pending=self.e.gm.snapshot()
    child=self.hatch(row,choices=selected,reason='GM confirms the observed birth facts')['pokemon']
    if index==0:
     old_child_id=child.entity_id;self.e.gm.restore(pending)
     self.assertNotIn(old_child_id,W.actor_index(self.e))
     self.assertIsNone(P.egg_index(self.e)[row['entity_id']][1]['gm_hatch_details'])
     child=self.hatch(row,choices=selected,reason='GM confirms the observed birth facts')['pokemon']
    child.name='renamed observed child '+str(index)
    actual=P.egg_index(self.e)[row['entity_id']][1]
    self.assertEqual(actual['gm_hatch_details'],selected)
    self.assertEqual(actual['pokemon_id'],child.entity_id)
    self.assertEqual(child.spec['egg_entity_id'],row['entity_id'])
    self.assertEqual((child.spec['gender'],child.spec['nature'],child.spec['special_appearance']),(gender,nature,special))
    self.assertEqual(child.abilities,selected['abilities'])
    children.append((row['entity_id'],child.entity_id,deepcopy(selected)))
    selected['abilities'].clear();self.assertEqual(actual['gm_hatch_details']['abilities'],['심록'])
  loaded=load_engine(self.r,json.loads(json.dumps(self.snap(),ensure_ascii=False)));actors=W.actor_index(loaded)
  for egg_id,child_id,selected in children:
   child=actors[child_id];actual=P.egg_index(loaded)[egg_id][1]
   self.assertEqual(actual['gm_hatch_details'],selected);self.assertEqual(actual['pokemon_id'],child_id)
   self.assertEqual((child.spec['gender'],child.spec['nature'],child.spec['special_appearance']),(selected['gender'],selected['nature'],selected['special_appearance']))
   self.assertEqual(child.abilities,selected['abilities'])
  self.assertNotEqual(children[0][1],children[1][1])
  self.assertEqual(parent_facts,[{field:p.spec.get(field) for field in birth_fields} for p in self.parents])
  self.assertTrue(loaded.validate_state()['valid'])
 def test_changed_request_rejects_and_historical_parent_knowledge_survives_later_changes(self):
  row=self.create();before=self.snap();changed=self.policy();changed['hatch']['level']=2
  with self.assertRaises(ValueError):self.create(changed)
  self.assertEqual(before,self.snap())
  self.e.gm.set_move(self.parents[0],'move/뿌리박기',False,reason='parent forgot the move after egg production')
  child=self.hatch(row)['pokemon'];self.assertIn('move/뿌리박기',child.spec['inheritance_moves'])
  self.assertNotIn('move/뿌리박기',child.spec['moves'])
  self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
