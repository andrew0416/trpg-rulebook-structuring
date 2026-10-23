"""Native check consumers for C3-EX-107 and the entire three-source EX-112."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Engine,Rules,Combatant
from ruleset import RuleFilter,ExcludedRuleSelection
import blessing_skill_features as B
import items,turn

SCOPES={'C3-EX-107':'a59c82952298b821369cc19e364c2203a081d5074e614f5125e9118c42128177',
'C3-EX-112':'3d44af6b8da36de75ce2cec97e9d5d2dff7e5373473dc58f9cf704b7bcf9f31b'}
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='fantasy')
 def setUp(self):
  self.e=Engine(self.rules,seed=404)
  self.a=Combatant(self.rules,{'id':'trainer/gift','name':'Gift','kind':'trainer','level':20,
   'stats':{'hp':10,'atk':5,'def':5,'spa':5,'spd':5,'spe':5},
   'skills':{'통찰':'초보','매력':'초보','교활':'전문','협박':'숙련','직감':'초보','집중':'달인','명령':'초보'}})
  self.e.everyone=[self.a];self.e.gm.everyone=self.e.everyone
 def gift(self,gift):
  self.a.spec.setdefault('gifts',[]).append(gift)
  return self.e.confirm_blessing_gift(self.a,gift,reason='GM confirms this particular acquired Minor Gift')
 def roll(self,skill,*,purpose=None,**kw):
  if purpose is not None:kw['skill_context']={'purpose':purpose,'reason':'GM identifies this actual check purpose'}
  return self.e.skill_roll(self.a,skill,**kw)
 def snapshot(self):return (deepcopy(self.a.spec),deepcopy(getattr(self.a,'_item_reg',{})),self.e.rng.getstate(),list(self.e.log_lines))
 def rejected(self,call):
  before=self.snapshot()
  with self.assertRaises((ValueError,ExcludedRuleSelection)):call()
  self.assertEqual(self.snapshot(),before)
 def test_fixed_full_scope_and_all_original_anchors(self):
  entries=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf-8'))['entries']
  for uid,sha in SCOPES.items():
   row=next(r for r in entries if r['id']==uid);self.assertEqual(row['scope_sha256'],sha)
   for a in row['source_snapshot']['source_anchors']:
    excerpt='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a['start_line']-1:a['end_line']])
    self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),a['excerpt_sha256'])
 def test_sleep_ordinary_check_rejected_before_rng(self):
  self.a.conditions.add('잠듦');self.rejected(lambda:self.roll('통찰'))
 def test_sleep_actual_common_action_uses_grant_without_waking_or_action(self):
  self.gift(B.SLEEP);self.a.conditions.add('잠듦')
  out=self.e.common_action(self.a,'통찰',9,mode='skill',fixed=[3]*3,skill_context={'purpose':'imminent_danger','reason':'collapsing ceiling'})
  self.assertTrue(out.check.passed);self.assertIn('잠듦',self.a.conditions)
  self.assertFalse(getattr(self.a,'_action_history',[]));self.assertFalse(turn.spend(self.e,self.a,'standard','ordinary action'))
 def test_sleep_gift_does_not_allow_other_skills_or_other_perception(self):
  self.gift(B.SLEEP);self.a.conditions.add('잠듦')
  for skill,purpose in [('통찰','distant_object'),('매력','imminent_danger'),('통찰',None)]:
   with self.subTest(skill=skill,purpose=purpose):self.rejected(lambda:self.roll(skill,purpose=purpose))
 def test_gift_requires_owned_gm_permission_and_not_just_context(self):
  self.rejected(lambda:self.e.confirm_blessing_gift(self.a,B.STAGE,reason='no acquisition'))
  self.a.spec['gifts']=[B.STAGE]
  self.rejected(lambda:self.roll('매력',purpose='singing',fixed=[2]*3))
  self.e.confirm_blessing_gift(self.a,B.STAGE,reason='actual approval')
  self.assertEqual(self.roll('매력',purpose='singing',fixed=[2]*3).total,8)
  self.assertTrue(any('마이너 기프트 GM 허가' in str(line) for line in self.e.log_lines))
 def test_gift_rejects_duplicate_alias_and_changed_actor_identity(self):
  self.gift(B.STAGE);self.a.spec['gifts'].append('눈부신 무대')
  self.rejected(lambda:self.roll('매력',purpose='singing',fixed=[2]*3))
  self.a.spec['gifts'].pop();self.a.spec['id']='other'
  self.rejected(lambda:self.roll('매력',purpose='singing',fixed=[2]*3))
 def test_source_selection_is_checked_at_each_consumption(self):
  for gift,skill,purpose in [(B.STAGE,'매력','singing'),(B.COMPASSION,'직감','comfort'),(B.SLEEP,'통찰','imminent_danger')]:
   with self.subTest(gift=gift):
    self.setUp();self.gift(gift)
    if gift==B.SLEEP:self.a.conditions.add('잠듦')
    self.rules.ruleset=RuleFilter({'sources':['core','blessings'],'exclude_units':[B.SOURCES[gift]]});self.rules._apply_ruleset()
    try:self.rejected(lambda:self.roll(skill,purpose=purpose,fixed=[2]*3))
    finally:self.rules.ruleset=RuleFilter({'sources':['core','errata','fantasy','blessings']});self.rules._apply_ruleset()
 def test_stage_highest_of_three_relevant_ranks_floor_and_no_focus_leak(self):
  self.gift(B.STAGE)
  for skill,faces in [('매력',[1]*3),('교활',[1]*5),('협박',[1]*4)]:
   for purpose in ('singing','dancing'):
    with self.subTest(skill=skill,purpose=purpose):
     out=self.roll(skill,purpose=purpose,fixed=faces);self.assertEqual(out.modifier,2)
  self.assertEqual(self.roll('집중',purpose='singing',fixed=[1]*6).modifier,0)
 def test_stage_is_optional_and_does_not_apply_to_generic_social_check(self):
  self.gift(B.STAGE)
  self.assertEqual(self.roll('Charm',fixed=[2]*3).total,6)
  self.assertEqual(self.roll('매력',purpose='comfort',fixed=[2]*3).total,6)
  self.assertEqual(self.roll('Charm',purpose='singing',fixed=[2]*3,mods=3,helper_rank=3).total,12)
 def test_compassion_covers_both_skills_and_both_named_purposes_only(self):
  self.gift(B.COMPASSION)
  for skill in ('매력','직감'):
   for purpose in ('understand_emotions','comfort'):
    self.assertEqual(self.roll(skill,purpose=purpose,fixed=[2]*3).total,9)
  self.assertEqual(self.roll('매력',fixed=[2]*3).total,6)
  self.assertEqual(self.roll('매력',purpose='singing',fixed=[2]*3).total,6)
  self.assertEqual(self.roll('협박',purpose='comfort',fixed=[2]*4).total,8)
 def test_all_six_actual_shards_native_register_roll_unregister(self):
  self.gift(B.ROYAL)
  for colour,skill in B.SHARDS.items():
   with self.subTest(colour=colour):
    name=colour+'조각';self.a.spec.setdefault('items',{})[name]=1
    items.register_item(self.e,self.a,name);self.assertIn(name,self.a._item_reg)
    entry=self.a._item_reg[name];self.assertEqual(entry['slots'],['장신구'])
    rank={'협박':4,'집중':6}.get(skill,3)
    self.assertEqual(self.roll(skill,fixed=[1]*rank).total,rank+2)
    self.assertEqual(self.roll('육상',fixed=[1]*2).total,2)
    self.assertEqual(items.unregister_item(self.e,self.a,name),1)
    self.assertEqual(self.roll(skill,fixed=[1]*rank).total,rank)
 def test_shard_native_accessory_slot_conflict_and_duplicate_not_stacking(self):
  self.gift(B.ROYAL);self.a.spec['items']={'빨강조각':1,'파랑조각':1}
  items.register_item(self.e,self.a,'빨강조각')
  self.assertEqual(items.register_item(self.e,self.a,'파랑조각'),0)
  self.assertEqual(items.register_item(self.e,self.a,'빨강조각'),0)
  self.assertEqual(self.roll('협박',fixed=[1]*4).total,6)
  self.assertEqual(self.roll('교활',fixed=[1]*5).total,5)
 def test_shard_inventory_without_equipment_gives_no_bonus_and_empty_cannot_equip(self):
  self.gift(B.ROYAL);self.a.spec['items']={'빨강조각':1}
  self.assertEqual(self.roll('협박',fixed=[1]*4).total,4)
  self.rejected(lambda:items.register_item(self.e,self.a,'파랑조각'))
  items.register_item(self.e,self.a,'빨강조각');self.a.spec['items']['빨강조각']=0
  self.rejected(lambda:self.roll('협박',fixed=[1]*4))
 def test_sleep_exception_does_not_allow_fainted_dead_or_missing_gift(self):
  self.gift(B.SLEEP);self.a.conditions.add('잠듦')
  self.a.conditions.add('기절');self.rejected(lambda:self.roll('통찰',purpose='imminent_danger',fixed=[2]*3));self.a.conditions.remove('기절')
  for field,value in [('dead',True),('hp',0)]:
   old=getattr(self.a,field);setattr(self.a,field,value)
   self.rejected(lambda:self.roll('통찰',purpose='imminent_danger',fixed=[2]*3));setattr(self.a,field,old)
  self.a.spec['gifts']=[];self.rejected(lambda:self.roll('통찰',purpose='imminent_danger',fixed=[2]*3))

if __name__=='__main__':
 class Result(unittest.TextTestResult):
  def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
  def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
  def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
  def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=[str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'engine').glob('*.py')]
 paths += ['tools/test_category3_blessing_skills.py','input/supp-blessings.md','input/ch03-skills-edges-feats.md','input/ch07-combat.md','data/rulesets.json','data/skill-check-policy.json','output/ruleunits.jsonl','data/items-mech.json']
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'completion_scopes':list(SCOPES),'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-blessing-skills-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 raise SystemExit(not result.wasSuccessful())
