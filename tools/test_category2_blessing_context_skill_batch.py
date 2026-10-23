"""Direct native checks for four source-distinct CSV contextual skill Gifts."""
from copy import deepcopy
from pathlib import Path
import csv
import hashlib
import json
import os
import tempfile
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from state_codec import dump_engine,load_engine
import blessing_skill_features as B
from tools.report_category2_progress import collect as collect_category2, SOURCES as PROGRESS_SOURCES


class BlessingContextSkillBatchTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='fantasy')
 def setUp(self):
  self.e=Engine(self.r,seed=916)
  self.a=Combatant(self.r,{'id':'trainer/csv-gifts','name':'CSV Gifts','kind':'trainer','level':20,
   'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
   'skills':{'생존':'초보','통찰':'초보','오컬트학':'초보','기술학':'초보','매력':'초보'}})
  self.e.everyone=[self.a];self.e.gm.everyone=self.e.everyone
 def own(self,gift):
  self.a.spec.setdefault('gifts',[]).append(gift)
  patrons={'gift/마이너-기프트-구름-읽기':'토네로스','gift/마이너-기프트-벌컨의-직감':'히드런',
   'gift/마이너-기프트-창조주의-손':'레지기가스','gift/마이너-기프트-사보타지-직감':'미싱노 (네트워크 보안의 새로운 신)'}
  self.a.spec.setdefault('gift_patrons',{})[gift]=patrons[gift]
  self.e.confirm_blessing_gift(self.a,gift,reason='GM approves this actual acquired CSV Gift')
 def roll(self,skill,purpose=None,**options):
  if purpose is not None:options['skill_context']={'purpose':purpose,'reason':'GM identifies this actual bounded purpose'}
  return self.e.skill_roll(self.a,skill,fixed=[1]*3,**options)
 def test_saved_source_cells_and_data_policy_are_exact(self):
  policy=json.loads((ROOT/'data/blessing-context-skill-policy.json').read_text(encoding='utf-8'))
  self.assertEqual(hashlib.sha256((ROOT/policy['source_file']).read_bytes()).hexdigest(),policy['source_file_sha256'])
  registry=json.loads((ROOT/'data/verification/category2-class-csv-clause-status.json').read_text(encoding='utf-8'))
  indexed={row['id']:row for row in registry['rows']}
  with (ROOT/policy['source_file']).open(encoding='utf-8-sig',newline='') as handle:rows=list(csv.reader(handle))
  for rule in policy['rules']:
   source=indexed[rule['clause_id']];actual=[rows[rule['record']-1][column-1] for column in source['columns']]
   digest=hashlib.sha256(json.dumps(actual,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
   self.assertEqual(digest,rule['cell_sha256']);self.assertEqual(digest,source['cell_sha256'])
   self.assertTrue(source['include_category2']);self.assertEqual(source['status'],'implemented')
   self.assertEqual(source['full_md_equivalence'],'not_proven_distinct_source_variant_preserved')
   self.assertIsNone(source['dedupe_target'])
 def test_report_collect_adds_exactly_four_actual_denominator_completions(self):
  clause_ids={row['clause_id'] for row in B._CONTEXT_POLICY['rules']}
  with tempfile.TemporaryDirectory(prefix='csv-blessing-report-') as tmp:
   shadow=Path(tmp)
   plan_path=ROOT/'data/verification/category2-edge-work-plan.json'
   plan=json.loads(plan_path.read_text(encoding='utf-8'))
   files={p for p in (ROOT/'input').rglob('*') if p.is_file()}
   files.update(ROOT/'data/verification'/name for _,name,_ in PROGRESS_SOURCES)
   files.update((plan_path,ROOT/'data/verification/category2-scope-freeze.json'))
   files.update(ROOT/proof['log'] for route in plan['post_foundation_reuse']['itemized_audit']['routes'].values() for proof in route['evidence'])
   for source in sorted(files):
    target=shadow/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
    try:os.link(source,target)
    except OSError:target.write_bytes(source.read_bytes())
   registry_path=shadow/'data/verification/category2-class-csv-clause-status.json'
   registry_path.unlink()
   registry=json.loads((ROOT/'data/verification/category2-class-csv-clause-status.json').read_text(encoding='utf-8'))
   found=set()
   for row in registry['rows']:
    if row['id'] in clause_ids:
     self.assertIsNone(row['dedupe_target']);self.assertTrue(row['include_category2'])
     row['status']='incomplete';found.add(row['id'])
   self.assertEqual(found,clause_ids)
   # Replay the historical transition in this private fixture, independent of publication.
   registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   before=collect_category2(shadow)
   self.assertEqual(before['validation_errors'],[])
   self.assertTrue(before['denominator_frozen']);self.assertEqual(before['denominator'],2352)
   for row in registry['rows']:
    if row['id'] in clause_ids:row['status']='implemented'
   registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
   after=collect_category2(shadow)
  self.assertEqual(after['validation_errors'],[]);self.assertTrue(after['denominator_frozen'])
  self.assertEqual(after['denominator'],before['denominator'])
  self.assertEqual(after['included_clause_ids'],before['included_clause_ids'])
  self.assertEqual(after['completed_clause_count']-before['completed_clause_count'],4)
 def test_four_gifts_use_one_context_policy_and_exact_positive_negative_matrix(self):
  cases={
   'gift/마이너-기프트-구름-읽기':[( '생존','predict_weather_from_clouds',3),('통찰','predict_weather_from_clouds',0),('생존',None,0)],
   'gift/마이너-기프트-벌컨의-직감':[( '통찰','mountain_region',3),('생존','volcanic_region',3),('매력','mountain_region',0),('생존',None,0)],
   'gift/마이너-기프트-창조주의-손':[( '오컬트학',None,3),('기술학','identify_crafting_material_use',3),('생존','identify_crafted_object_use',3),('매력',None,0)],
   'gift/마이너-기프트-사보타지-직감':[( '기술학','destroy_modern_device',3),('기술학','sabotage_modern_device',3),('기술학','interfere_modern_device',3),('생존','destroy_modern_device',0),('기술학',None,0)]}
  for gift,matrix in cases.items():
   with self.subTest(gift=gift):
    self.setUp();self.own(gift)
    for skill,purpose,bonus in matrix:
     result=self.roll(skill,purpose,mods=2)
     self.assertEqual(result.modifier,2+bonus,(gift,skill,purpose))
 def test_actual_acquisition_approval_removal_and_duplicate_alias_gate_every_consumer(self):
  gift='gift/마이너-기프트-구름-읽기';before=self.e.rng.getstate()
  with self.assertRaises(ValueError):self.e.confirm_blessing_gift(self.a,gift,reason='not acquired')
  self.assertEqual(self.e.rng.getstate(),before);self.a.spec['gifts']=[gift]
  with self.assertRaises(ValueError):self.roll('생존','predict_weather_from_clouds')
  self.e.confirm_blessing_gift(self.a,gift,reason='actual approval')
  self.assertEqual(self.roll('생존','predict_weather_from_clouds').modifier,3)
  self.a.spec['gifts'].append('마이너 기프트 구름 읽기')
  with self.assertRaises(ValueError):self.roll('생존','predict_weather_from_clouds')
  self.a.spec['gifts']=[gift];self.a.spec['gifts'].clear()
  self.assertEqual(self.roll('생존','predict_weather_from_clouds').modifier,0)
 def test_native_json_restore_keeps_approval_and_source_while_unrelated_gifts_do_not_stack(self):
  gifts=['gift/마이너-기프트-구름-읽기','gift/마이너-기프트-벌컨의-직감']
  for gift in gifts:self.own(gift)
  saved=dump_engine(self.e);loaded=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));actor=loaded.everyone[0]
  self.assertEqual(loaded.skill_roll(actor,'생존',fixed=[1]*3,skill_context={'purpose':'predict_weather_from_clouds','reason':'actual clouds'}).modifier,3)
  self.assertEqual(loaded.skill_roll(actor,'생존',fixed=[1]*3,skill_context={'purpose':'mountain_region','reason':'actual mountain'}).modifier,3)
  self.assertEqual(loaded.skill_roll(actor,'생존',fixed=[1]*3).modifier,0)
  actor.spec['gifts'].remove(gifts[0])
  self.assertEqual(loaded.skill_roll(actor,'생존',fixed=[1]*3,skill_context={'purpose':'predict_weather_from_clouds','reason':'actual clouds'}).modifier,0)


if __name__=='__main__':unittest.main()
