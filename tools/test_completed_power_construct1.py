"""R0248: actual Zygarde form investments through the native public API."""
from copy import deepcopy
from pathlib import Path
import json, sys, unittest

ROOT=Path(r'D:/trpg-rulebook-structuring/ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
import form_allocations as FORMS, temporary_hp as TEMP, state_grants as GRANTS

SOURCE='ability/스웜체인지'
PERFECT='퍼펙트폼'

class PowerConstructTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='all')

 def fixture(self,form='50%폼',*,configure=True):
  e=Engine(self.r,101);e.grid=Grid(30,30)
  base=build_pokemon(self.r,'지가르데 '+form,30,abilities=[SOURCE],moves=['move/몸통박치기'],pos=(2,2))
  perfect=build_pokemon(self.r,'지가르데 퍼펙트폼',30,abilities=[SOURCE],moves=['move/몸통박치기'])
  c=Combatant(self.r,base);e.gm.add_combatant(c)
  declarations={name:{key:deepcopy(spec['initial_allocation'][key]) for key in ('species_base','investment')}
                for name,spec in ((form,base),(PERFECT,perfect))}
  if configure:e.configure_growth_forms(c,declarations,active=form,source=SOURCE)
  return e,c,declarations,perfect

 def start(self,e,c):e.start_round(e.everyone);e.start_of_turn(c,initiative_count=20)

 def activate(self,e,c):return e.activate_ability_state(c,SOURCE,choice=PERFECT,reason='authored below-half daily swift')

 def test_actual_10_and_50_forms_keep_real_hp_and_use_perfect_temp_hp(self):
  for original in ('10%폼','50%폼'):
   with self.subTest(original=original):
    e,c,declarations,perfect=self.fixture(original)
    original_max=c.base_max_hp
    perfect_max=Combatant(self.r,perfect).base_max_hp
    self.assertNotEqual(c.stats['hp'],perfect['stats']['hp'])
    self.assertNotEqual(original_max,perfect_max)
    self.start(e,c);c.hp=(original_max-1)//2
    prior_hp=c.hp;self.activate(e,c)
    self.assertEqual((c.form,c.hp,c.base_max_hp,c.max_hp),(PERFECT,prior_hp,original_max,original_max))
    self.assertEqual(c.spec['stats'],perfect['stats'])
    self.assertEqual(c.temp_hp,perfect_max//2)
    before=c.temp_hp
    self.assertEqual(TEMP.grant(e,c,before+10,provenance={'source':'other/source'}),0)
    self.assertEqual(c.temp_hp,before)
    e.take_damage(c,before+1)
    self.assertEqual((c.hp,c.temp_hp),(prior_hp-1,0))
    e.heal(c,perfect_max,source_kind='move')
    self.assertEqual((c.hp,c.base_max_hp),(original_max,original_max))
    e.end_scene([c])
    self.assertEqual((c.form,c.hp,c.base_max_hp),(original,original_max,original_max))
    self.assertGreater(TEMP.grant(e,c,3),0)
    self.assertTrue(e.validate_state()['valid'])

 def test_half_boundary_daily_limit_and_scene_restore_are_atomic(self):
  e,c,_,_=self.fixture();self.start(e,c);maximum=c.base_max_hp
  c.hp=(maximum+1)//2;before=e.export_state()
  with self.assertRaisesRegex(ValueError,'below half'):self.activate(e,c)
  self.assertEqual(e.export_state(),before)
  c.hp=(maximum-1)//2;self.activate(e,c)
  quota=c.spec['frequency_state']['activations'][SOURCE]
  self.assertEqual((quota['kind'],quota['used']),('daily',1))
  e.end_scene([c]);self.assertEqual(c.form,'50%폼')
  before=e.export_state()
  with self.assertRaises(ValueError):self.activate(e,c)
  self.assertEqual(e.export_state(),before)
  self.assertTrue(e.validate_state()['valid'])

 def test_restore_keeps_original_hp_authority_and_shared_stat_sources(self):
  e,c,_,perfect=self.fixture('10%폼');self.start(e,c)
  GRANTS._source(c,'test/shared-hp','feature',rule_id='combat/struggle')
  GRANTS.stat(c,'hp',2,'test/shared-hp')
  original_max=c.base_max_hp;c.hp=(original_max-1)//2
  perfect_max=Combatant(self.r,perfect).base_max_hp+6
  self.activate(e,c)
  self.assertEqual((c.base_max_hp,c.temp_hp),(original_max,perfect_max//2))
  saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False))
  loaded=Engine.import_state(self.r,saved);restored=loaded.everyone[0]
  self.assertEqual((restored.hp,restored.base_max_hp,restored.temp_hp),(c.hp,original_max,perfect_max//2))
  loaded.take_damage(restored,restored.temp_hp+1)
  self.assertEqual(restored.hp,c.hp-1)
  loaded.end_scene([restored]);self.assertEqual((restored.form,restored.base_max_hp),('10%폼',original_max))
  self.assertTrue(loaded.validate_state()['valid'])
  forged=Engine.import_state(self.r,saved)
  forged.everyone[0].spec['ability_state_projection'][SOURCE]['prior_form']='unknown'
  with self.assertRaises(ValueError):forged.export_state()

 def test_each_forms_bst_is_checked_and_other_sources_keep_shared_hp(self):
  e,c,declarations,_=self.fixture(configure=False);before=e.export_state()
  bad=deepcopy(declarations)
  # Preserve total investment while putting a lower base stat above HP.
  values=bad[PERFECT]['investment'];values.update(dict.fromkeys(values,0));values['spe']=40
  with self.assertRaisesRegex(ValueError,'base relations'):
   e.configure_growth_forms(c,bad,active='50%폼',source=SOURCE)
  self.assertEqual(e.export_state(),before)
  forms={name:{stat:row['species_base'][stat]+row['investment'][stat] for stat in row['species_base']}
         for name,row in declarations.items()}
  with self.assertRaisesRegex(ValueError,'shared HP'):
   e.configure_form_allocations(c,forms,active='50%폼',source='combat/struggle')
  self.assertEqual(e.export_state(),before)
  e.configure_form_allocations(c,forms,active='50%폼',source=SOURCE)
  self.start(e,c);c.hp=(c.base_max_hp-1)//2;before=e.export_state()
  with self.assertRaisesRegex(ValueError,'checked BST'):self.activate(e,c)
  self.assertEqual(e.export_state(),before)

 def test_actual_forms_keep_checked_bst_through_existing_growth_paths(self):
  import downtime as D, growth_stats as GROWTH
  e,c,declarations,_=self.fixture('10%폼')
  before=c.spec['form_growth_allocations']['budget']
  migration=GROWTH.evolution_forms(self.r,c.spec,declarations,points=before)
  self.assertNotEqual(migration['forms']['10%폼']['hp'],migration['forms'][PERFECT]['hp'])
  D.gain_exp_combatant(e,c,'to next level')
  self.assertEqual(c.level,31)
  for plan in c.spec['form_growth_allocations']['plans'].values():
   self.assertEqual(sum(plan['investment'].values()),before+1)
  self.start(e,c);original_max=c.base_max_hp;c.hp=(original_max-1)//2;self.activate(e,c)
  self.assertEqual(c.base_max_hp,original_max)
  e.growth_stat_projection(c);self.assertTrue(e.validate_state()['valid'])

 def test_shared_schooling_daily_and_mimicry_scene_quota_consumers(self):
  for source,kind in (('ability/어군','daily'),('ability/의태','scene')):
   with self.subTest(source=source):
    e=Engine(self.r,101);e.grid=Grid(30,30)
    c=Combatant(self.r,build_pokemon(self.r,'이상해씨',30,abilities=[source],moves=['move/몸통박치기']))
    e.gm.add_combatant(c)
    if kind=='daily':
     base=deepcopy(c.spec['stats']);other=dict(base,atk=base['atk']+1)
     e.configure_form_allocations(c,{'단독의모습':base,'군집의모습':other},active='단독의모습',source=source)
     kwargs={'choice':'군집의모습'}
    else:
     kwargs={'choice':'풀','observation':{'environment':'숲','fact':{'source':'test/forest','reason':'actual forest'}}}
    def activate():return e.activate_ability_state(c,source,reason='authored native quota consumer',**kwargs)
    activate();self.assertEqual(c.spec['frequency_state']['activations'][source]['kind'],kind)
    before=e.export_state()
    with self.assertRaisesRegex(ValueError,'frequency exhausted'):activate()
    self.assertEqual(e.export_state(),before)
    e.end_scene([c]);before=e.export_state()
    if kind=='daily':
     with self.assertRaisesRegex(ValueError,'frequency exhausted'):activate()
     self.assertEqual(e.export_state(),before)
    else:
     activate();self.assertEqual(c.types,['풀'])
    self.assertTrue(e.validate_state()['valid'])

 def test_updated_original_power_fixture_and_unchanged_schooling_body(self):
  import test_category2_ability_state_projection as original
  original.ROOT=ROOT
  case=original.AbilityStateProjectionTests('test_power_construct_and_schooling_share_form_temp_hp_and_lock_consumers')
  case.r=self.r
  case.test_power_construct_and_schooling_share_form_temp_hp_and_lock_consumers()

if __name__=='__main__':unittest.main()
