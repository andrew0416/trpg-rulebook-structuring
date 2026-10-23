"""Q03: actual CSV gift provenance, contextual bonuses, and persistence."""
from pathlib import Path
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'input').is_dir():ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from state_codec import dump_engine,load_engine
from ruleset import RuleFilter
import blessing_skill_features as B

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='fantasy')
 def fixture(self,gift,approved=True):
  e=Engine(self.rules,19)
  a=Combatant(self.rules,dict(id='trainer/purpose',name='purpose',kind='trainer',level=20,
    stats=dict(hp=10,atk=5,**{'def':5},spa=5,spd=5,spe=5),
    skills={'직감':'초보','매력':'초보','집중':'초보'},gifts=[gift]))
  e.everyone=e.gm.everyone=[a]
  a.spec['gift_patrons']={gift:{B.CSV_COMPASSION:'뮤',B.COMPASSION:'뮤',B.TRUTH:'레시라무',B.IDEALS:'제크로무'}[gift]}
  if approved:e.confirm_blessing_gift(a,gift,reason='GM approves actual acquisition')
  return e,a
 def roll(self,e,a,skill,purpose):
  return e.skill_roll(a,skill,fixed=[2]*3,mods=2,
      skill_context={'purpose':purpose,'reason':'actual purpose observed by GM'})
 def test_all_csv_gifts_only_apply_to_named_skill_and_purpose(self):
  for gift in (B.CSV_COMPASSION,B.TRUTH,B.IDEALS):
   e,a=self.fixture(gift);skills,purposes,_=B.PURPOSE_BONUSES[gift]
   for skill in ('직감','매력','집중'):
    for purpose in ('understand_emotions','comfort','detect_lies','discern_beliefs','singing'):
     with self.subTest(gift=gift,skill=skill,purpose=purpose):
      self.assertEqual(self.roll(e,a,skill,purpose).total,8+(3 if skill in skills and purpose in purposes else 0))
 def test_approval_and_context_fail_before_rng_and_state_mutation(self):
  for gift in (B.CSV_COMPASSION,B.TRUTH,B.IDEALS):
   e,a=self.fixture(gift,False);before=json.dumps(a.spec,sort_keys=True);rng=e.rng.getstate()
   with self.assertRaises(ValueError):self.roll(e,a,'직감',B.PURPOSE_BONUSES[gift][1][0])
   self.assertEqual(before,json.dumps(a.spec,sort_keys=True));self.assertEqual(rng,e.rng.getstate())
   e.confirm_blessing_gift(a,gift,reason='permission')
   with self.assertRaises(ValueError):e.skill_roll(a,'직감',skill_context={'purpose':B.PURPOSE_BONUSES[gift][1][0]})
   self.assertEqual(rng,e.rng.getstate())
 def test_native_codec_and_snapshot_preserve_then_removal_stops_bonus(self):
  for gift in (B.CSV_COMPASSION,B.TRUTH,B.IDEALS):
   e,a=self.fixture(gift);purpose=B.PURPOSE_BONUSES[gift][1][0]
   e.gm.snapshot('acquired');a.spec['gifts']=[]
   self.assertEqual(self.roll(e,a,'직감',purpose).total,8)
   e.gm.restore('acquired',reason='restore acquisition')
   self.assertEqual(self.roll(e,a,'직감',purpose).total,11)
   n=load_engine(self.rules,json.loads(json.dumps(dump_engine(e))));b=n.everyone[0]
   self.assertEqual(self.roll(n,b,'직감',purpose).total,11)
   b.spec['gifts']=[];self.assertEqual(self.roll(n,b,'직감',purpose).total,8)
 def test_source_exclusion_cannot_reuse_another_version(self):
  for gift in (B.CSV_COMPASSION,B.TRUTH,B.IDEALS):
   e,a=self.fixture(gift)
   self.rules.ruleset=RuleFilter({'sources':['core','errata','fantasy','blessings'],'exclude_units':[gift]});self.rules._apply_ruleset()
   try:
    with self.assertRaises(ValueError):self.roll(e,a,'직감',B.PURPOSE_BONUSES[gift][1][0])
   finally:
    self.rules.ruleset=RuleFilter({'sources':['core','errata','fantasy','blessings']});self.rules._apply_ruleset()
 def test_duplicate_compassion_representation_cannot_stack(self):
  e,a=self.fixture(B.COMPASSION);a.spec['gifts'].append(B.CSV_COMPASSION)
  e.confirm_blessing_gift(a,B.CSV_COMPASSION,reason='duplicate source')
  with self.assertRaises(ValueError):self.roll(e,a,'직감','comfort')

if __name__=='__main__':unittest.main()
