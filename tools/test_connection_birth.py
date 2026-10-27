"""Actual native birth Connection gains, after final source abilities and owner projection."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_foundation_egg_creation as EGG
import test_book_researcher_fields_pokemon as RFIX
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
import advanced_connection as C,creation_egg as E,move_state as M,world_entities as W,state_codec as CODEC
import researcher_fields as RF
FULL=['튀어오르기','몸통박치기','바둥바둥','돌진','전광석화','방어']

class ConnectionBirthTests(unittest.TestCase):
 setUpClass=classmethod(EGG.EggTests.setUpClass.__func__)
 add=EGG.EggTests.add
 policy=EGG.EggTests.policy
 def setUp(self):
  EGG.EggTests.setUp(self)
  previous=self.r.rulings;self.r.rulings=deepcopy(previous);self.e.rulings=self.r.rulings
  self.addCleanup(setattr,self.r,'rulings',previous)
  self.parents=[self.add(build_pokemon(self.r,'치라미',5,moves=[],abilities=['헬퍼'],extra={'trainer_id':self.a.entity_id,'gender':gender})) for gender in ('female','male')]
  self.helper=self.r.move_id('도우미')
 def create(self,full=False):
  policy=self.policy();policy['hatch']['known_moves']='observed' if full else 'natural_and_inherited'
  return self.e.create_declared_egg(self.a,self.parents,policy,request_id='connection-birth',compatible=True,species='치라미',inheritance_moves=[],reason='actual Connection Basic Ability egg')
 def hatch(self,row,full=False):
  return self.e.hatch_declared_egg(self.a,row['entity_id'],name='Connection child',ready=True,reason='actual observed birth',choices={'gender':'female','nature':'노력','abilities':['헬퍼'],'moves':FULL if full else [],'inheritance_moves':[],'special_appearance':False})['pokemon']
 def test_actual_declared_birth_learns_basic_connection_after_owner_projection_and_restores(self):
  row=self.create();child=self.hatch(row)
  self.assertIn(self.helper,child.spec['moves']);self.assertEqual(child.spec['move_learning'][self.helper]['paid_tp'],0)
  self.assertEqual(child.spec['tutor_points'],1);self.assertEqual(child.spec['trainer_id'],self.a.entity_id)
  self.assertEqual(E.lineage(self.e,child)['outputs'],[child.entity_id])
  for parent in self.parents:self.assertNotIn(self.helper,parent.spec['moves'])
  self.e.gm.snapshot('birth');self.e.gm.restore('birth')
  loaded=CODEC.load_engine(self.r,json.loads(json.dumps(CODEC.dump_engine(self.e))))
  c=W.actor_index(loaded)[child.entity_id]
  assert_rejected_unchanged(loaded,lambda:loaded.gm.set_move(c,self.helper,add=False),reason_pattern='cannot be forgotten')
 def test_full_birth_without_choice_rolls_back_and_immediate_edge_uses_actual_child_identity(self):
  row=self.create(True)
  assert_rejected_unchanged(self.e,lambda:self.hatch(row,True),reason_pattern='explicit forgotten Move or immediate Advanced Connection')
  def choice(prompt):
   if prompt.get('type')==C.PROMPT:return {'actor_id':prompt['actor_id'],'ability':prompt['ability'],'advanced_connection':True}
  self.r.rulings.provider=choice;start=self.e.elapsed_seconds
  child=self.hatch(row,True)
  self.assertEqual((child.spec['tutor_points'],self.e.elapsed_seconds),(0,start))
  self.assertEqual(M.describe(self.r,child.spec)['slot_count'],6)
  self.assertEqual(C.records(child.spec)[0]['trainer_id'],self.a.entity_id)
 def test_late_connection_birth_failure_preserves_egg_receipt_rosters_clock_and_owner(self):
  row=self.create();native=C.birth
  def fail(*args,**kwargs):native(*args,**kwargs);raise ValueError('late Connection birth failure')
  with patch.object(C,'birth',side_effect=fail):
   assert_rejected_unchanged(self.e,lambda:self.hatch(row),reason_pattern='late Connection birth failure')
  child=self.hatch(row);self.assertIn(self.helper,child.spec['moves'])

class ConnectionSpecialBirthTests(unittest.TestCase):
 setUpClass=classmethod(RFIX.ResearcherFieldsPokemonTests.setUpClass.__func__)
 setUp=RFIX.ResearcherFieldsPokemonTests.setUp
 setup=RFIX.ResearcherFieldsPokemonTests.setup
 trainer=RFIX.ResearcherFieldsPokemonTests.trainer
 pokemon=RFIX.ResearcherFieldsPokemonTests.pokemon
 fossil=RFIX.ResearcherFieldsPokemonTests.fossil
 hatch=RFIX.ResearcherFieldsPokemonTests.hatch
 valid=RFIX.ResearcherFieldsPokemonTests.valid
 restore=RFIX.ResearcherFieldsPokemonTests.restore
 def test_fossil_restoration_second_basic_connection_ability_is_included_at_final_birth(self):
  egg=self.fossil('푸린','connection-second-basic',feature=True)
  child=self.hatch(egg,'second Basic child')
  self.assertEqual(child.spec['abilities'],['헤롱헤롱바디','자장가'])
  sing=self.rules.move_id('노래하기');self.assertIn(sing,child.spec['moves'])
  self.assertEqual(child.spec['move_learning'][sing]['connection_ability'],'ability/자장가')
  self.assertEqual(child.spec['tutor_points'],0)
  assert_rejected_unchanged(self.e,lambda:self.e.gm.set_move(child,sing,add=False),reason_pattern='cannot be forgotten')
 def test_playing_god_birth_hook_sees_final_upgrade_moves_and_registered_owner(self):
  self.t.spec['items']['화학 세트']=1
  upgrades=[{'kind':'shiny_contest','contest_stat':'근사함'},{'kind':'inheritance_move','move':'move/저주'},*({'kind':'base_stat','stat':x} for x in ('spa','spa','hp','def'))]
  row=RF.playing_god(self.e,self.t,species='코일',nature='겁쟁이',ability='옹골참',gender='무성',upgrades=upgrades,seconds=3600,reason='actual synthesis',request_id='connection-hook-order')
  self.e.advance_time(86400,[self.t]);seen=[];native=C.birth
  def observe(engine,child,egg,*,reason):
   self.assertIs(W.actor_index(engine)[child.entity_id],child)
   self.assertEqual(child.spec['trainer_id'],self.t.entity_id)
   self.assertNotIn('move/저주',child.spec['moves']);self.assertIn('move/저주',child.spec['inheritance_moves'])
   self.assertEqual(child.spec['vitamin_bonus'],{'spa':2,'hp':1,'def':1})
   seen.append(list(child.spec['abilities']));return native(engine,child,egg,reason=reason)
  with patch.object(C,'birth',side_effect=observe):
   child=RF.hatch_artificial(self.e,self.t,row['egg_entity_id'],name='Coil',reason='actual hatch')['pokemon']
  self.assertEqual(seen,[['옹골참']]);self.assertNotIn(C.PROTECTION,child.spec)
  self.valid()

if __name__=='__main__':unittest.main()
