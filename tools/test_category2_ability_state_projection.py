"""Exact producer/consumer/lifetime checks for the 15 reviewed ability-state rows."""
from copy import deepcopy
from pathlib import Path
import json,random,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]

from builder import build_pokemon
from engine import Combatant,Engine,Rules
from grid import Grid
import ability_state_projection as P
import downtime as D
import effects as FX
import form_allocations as FORMS
import growth_milestones as MILESTONES
import temporary_hp as TEMP


ROWS={
 'C2CSV-ABILITY-R0037','C2CSV-ABILITY-R0041','C2CSV-ABILITY-R0050',
 'C2CSV-ABILITY-R0111','C2CSV-ABILITY-R0135','C2CSV-ABILITY-R0178',
 'C2CSV-ABILITY-R0180','C2CSV-ABILITY-R0223','C2CSV-ABILITY-R0248',
 'C2CSV-ABILITY-R0266','C2CSV-ABILITY-R0286','C2CSV-ABILITY-R0325',
 'C2CSV-ABILITY-R0335','C2CSV-ABILITY-R0443','C2CSV-ABILITY-R0655',
}


class AbilityStateProjectionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(ROOT,ruleset='all')

 def engine(self,seed=101):
  e=Engine(self.r,seed);e.grid=Grid(30,30);return e

 def actor(self,e,ability,*,name=None,level=30,species='이상해씨',moves=(),pos=(2,2),types=None):
  extra={'abilities':[ability],'pos':pos,'side':'party'}
  if types is not None:extra['types']=list(types)
  spec=build_pokemon(self.r,species,level,name=name or ability,moves=list(moves) or ['move/몸통박치기'],extra=extra)
  c=Combatant(self.r,spec);e.gm.add_combatant(c);return c

 def forms(self,e,c,names,source):
  base=deepcopy(c.spec['stats']);other=deepcopy(base)
  donor=next(k for k in ('def','spd','spe','spa','atk') if other[k]>1)
  recipient=next(k for k in ('atk','spa','spe','spd','def') if k!=donor)
  other[donor]-=1;other[recipient]+=1
  values={names[0]:base,**{name:deepcopy(other) for name in names[1:]}}
  e.configure_form_allocations(c,values,active=names[0],source=source)
  return values

 def fact(self,label):return {'source':'test/observation','reason':'actual '+label}

 def test_policy_is_exactly_the_fifteen_reviewed_rows(self):
  policy=self.r.ability_state_projection_policy
  self.assertEqual({row['row_id'] for row in policy['sources'].values()},ROWS)
  self.assertEqual(len(policy['sources']),15)
  self.assertTrue(all(len(row['source_row_sha256'])==64 for row in policy['sources'].values()))

 def test_type_projections_use_weather_choice_field_fact_and_scene_restoration(self):
  forecast_e=self.engine();forecast=self.actor(forecast_e,'ability/기분파')
  forecast_e.gm.set_weather('sunny',rounds=5,reason='actual sun')
  self.assertEqual(forecast.types,['불꽃'])
  forecast_e.gm.set_weather(None,reason='weather ended')
  self.assertEqual(forecast.types,['노말'])

  multi_e=self.engine();multi=self.actor(multi_e,'ability/멀티타입')
  multi_e.activate_ability_state(multi,'ability/멀티타입',choice='전기',reason='actual free choice')
  self.assertEqual(multi.types,['전기'])

  mimic_e=self.engine();mimic=self.actor(mimic_e,'ability/의태');baseline=list(mimic.types)
  observation={'environment':'숲','fact':self.fact('forest')}
  before=mimic_e.export_state()
  with self.assertRaises(ValueError):
   mimic_e.activate_ability_state(mimic,'ability/의태',choice='불꽃',observation=observation,reason='invalid field choice')
  self.assertEqual(mimic_e.export_state(),before)
  mimic_e.activate_ability_state(mimic,'ability/의태',choice='풀',observation=observation,reason='actual forest choice')
  self.assertEqual(mimic.types,['풀'])
  mimic_e.end_scene([mimic]);self.assertEqual(mimic.types,baseline)
  for e in (forecast_e,multi_e,mimic_e):self.assertTrue(e.validate_state()['valid'])

 def test_style_season_and_leafy_choices_replace_only_their_owned_grants(self):
  e=self.engine()
  trim=self.actor(e,'ability/기막힌손질',name='trim')
  salon={'location':'미용실','fact':self.fact('salon')}
  e.activate_ability_state(trim,'ability/기막힌손질',choice='가부키컷',observation=salon,reason='actual haircut',seconds=60)
  self.assertEqual(trim.form,'가부키컷');self.assertIn('ability/정신력-playtest',trim.abilities)
  e.activate_ability_state(trim,'ability/기막힌손질',choice='퀸컷',observation=salon,reason='new haircut',seconds=60)
  self.assertNotIn('ability/정신력-playtest',trim.abilities);self.assertIn('ability/위협',trim.abilities)

  seasonal=self.actor(e,'ability/사시사철',name='seasonal')
  e.activate_ability_state(seasonal,'ability/사시사철',choice='봄',observation={'season':'봄','fact':self.fact('spring')},reason='season observed')
  self.assertIn('ability/도주-playtest',seasonal.abilities)
  e.activate_ability_state(seasonal,'ability/사시사철',choice='겨울',observation={'season':'겨울','fact':self.fact('winter')},reason='season changed')
  self.assertNotIn('ability/도주-playtest',seasonal.abilities);self.assertIn('ability/두꺼운지방',seasonal.abilities)

  leafy=self.actor(e,'ability/잎사귀망토',name='leafy')
  choices=list(P.definition(self.r,'ability/잎사귀망토')['choices'])
  first=P.definition(self.r,'ability/잎사귀망토')['choices'][choices[0]]['abilities']
  second=P.definition(self.r,'ability/잎사귀망토')['choices'][choices[-1]]['abilities']
  e.activate_ability_state(leafy,'ability/잎사귀망토',choice=choices[0],reason='first pair')
  self.assertTrue(set(first)<=set(leafy.abilities))
  e.activate_ability_state(leafy,'ability/잎사귀망토',choice=choices[-1],reason='reactivated pair')
  self.assertTrue(set(second)<=set(leafy.abilities));self.assertFalse((set(first)-set(second))&set(leafy.abilities))
  self.assertTrue(e.validate_state()['valid'])

 def test_hunger_switch_consumes_pending_choices_at_actual_turn_start(self):
  e=self.engine();full=self.actor(e,'ability/꼬르륵스위치',name='full',pos=(2,2));hungry=self.actor(e,'ability/꼬르륵스위치',name='hungry',pos=(3,2))
  e.choose_ability_state(full,'ability/꼬르륵스위치','배부른 모양',reason='turn choice')
  e.choose_ability_state(hungry,'ability/꼬르륵스위치','배고픈 모양',reason='turn choice')
  e.start_round(e.everyone);e.start_of_turn(full,initiative_count=20)
  self.assertEqual((full.form,full.accuracy_stage),('배부른 모양',2))
  e.end_of_turn(full);e.start_of_turn(hungry,initiative_count=19)
  move=self.r.move('move/몸통박치기')
  self.assertEqual(hungry.form,'배고픈 모양')
  self.assertEqual(FX.passive_damage_mods(e,hungry,full,move,{'attacker':hungry,'target':full})[1],5)
  self.assertTrue(e.validate_state()['valid'])

 def test_shields_down_uses_real_hp_boundaries_and_preserves_form_allocations(self):
  e=self.engine();c=self.actor(e,'ability/리밋실드');forms=self.forms(e,c,('유성','코어'),'ability/리밋실드')
  e.start_round(e.everyone);e.start_of_turn(c,initiative_count=20)
  c.hp=c.base_max_hp//2+1;e.take_damage(c,2)
  self.assertEqual(c.form,'코어');self.assertEqual(c.spec['stats'],forms['코어'])
  e.heal(c,c.base_max_hp,source_kind='move');self.assertEqual(c.form,'코어')
  e.end_of_turn(c);e.end_encounter(e.everyone)
  self.assertEqual(c.form,'유성');self.assertEqual(c.spec['stats'],forms['유성'])
  self.assertTrue(e.validate_state()['valid'])

 def test_stance_change_has_actual_move_trigger_and_manual_full_action(self):
  e=self.engine(5);blade=self.actor(e,'ability/배틀스위치',moves=['move/몸통박치기'],pos=(2,2));target=self.actor(e,'ability/멀티타입',name='target',pos=(3,2))
  base=deepcopy(blade.spec['stats']);e.start_round(e.everyone);e.start_of_turn(blade,initiative_count=20)
  e.use_move(blade,target,'move/몸통박치기')
  self.assertEqual(blade.form,'블레이드폼');self.assertEqual(blade.spec['stats']['atk'],base['def']);self.assertEqual(blade.stages,{k:0 for k in blade.stages})

  manual_e=self.engine();manual=self.actor(manual_e,'ability/배틀스위치')
  manual_e.start_round(manual_e.everyone);manual_e.start_of_turn(manual,initiative_count=20)
  manual_e.activate_ability_state(manual,'ability/배틀스위치',choice='블레이드폼',reason='authored full action')
  before=manual_e.export_state()
  with self.assertRaises(ValueError):manual_e.activate_ability_state(manual,'ability/배틀스위치',choice='실드폼',reason='second full action')
  self.assertEqual(manual_e.export_state(),before)
  self.assertTrue(e.validate_state()['valid']);self.assertTrue(manual_e.validate_state()['valid'])

 def test_creation_patterns_feed_the_actual_natural_ability_pool_consumer(self):
  e=self.engine(77);serpent=self.actor(e,'ability/뱀무늬-playtest',species='아보크')
  expected_rng=random.Random();expected_rng.setstate(e.rng.getstate())
  choices=list(P.definition(self.r,'ability/뱀무늬-playtest')['choices']);expected=choices[expected_rng.randrange(6)]
  row=e.initialize_ability_state(serpent,'ability/뱀무늬-playtest',reason='native creation roll')
  self.assertEqual(row['choice'],expected);self.assertEqual(e.rng.getstate(),expected_rng.getstate())
  payload=P.definition(self.r,'ability/뱀무늬-playtest')['choices'][expected]['ability_pools']
  actual=MILESTONES.natural_abilities(self.r,serpent.spec,pools=('숨겨진 특성','대단한 특성'))
  self.assertEqual(actual,[*payload['숨겨진 특성'],*payload['대단한 특성']])

  quill=self.actor(e,'ability/연대감',species='시비꼬')
  e.initialize_ability_state(quill,'ability/연대감',choice='옐로우 페더',reason='observed creation color')
  self.assertEqual(MILESTONES.natural_abilities(self.r,quill.spec,pools=('숨겨진 특성','대단한 특성')),['ability/포악','ability/이판사판-playtest'])
  self.assertTrue(e.validate_state()['valid'])

 def test_power_construct_and_schooling_share_form_temp_hp_and_lock_consumers(self):
  power_e=self.engine();power=self.actor(power_e,'ability/스웜체인지',species='지가르데 50%폼')
  perfect=build_pokemon(self.r,'지가르데 퍼펙트폼',power.level,moves=['move/몸통박치기'],abilities=['ability/스웜체인지'])
  declarations={name:{key:deepcopy(spec['initial_allocation'][key]) for key in ('species_base','investment')}
                for name,spec in (('50%폼',power.spec),('퍼펙트폼',perfect))}
  power_e.configure_growth_forms(power,declarations,active='50%폼',source='ability/스웜체인지')
  original_max=power.base_max_hp;perfect_max=Combatant(self.r,perfect).base_max_hp
  power_e.start_round(power_e.everyone);power_e.start_of_turn(power,initiative_count=20);power.hp=power.base_max_hp//2-1
  power_e.activate_ability_state(power,'ability/스웜체인지',choice='퍼펙트폼',reason='below-half daily swift')
  self.assertEqual((power.form,power.temp_hp,power.base_max_hp),('퍼펙트폼',perfect_max//2,original_max))
  before=power.temp_hp;self.assertEqual(TEMP.grant(power_e,power,before+10),0);self.assertEqual(power.temp_hp,before)
  power_e.end_scene([power]);self.assertEqual(power.form,'50%폼');self.assertFalse(P.temp_hp_blocked(power))

  school_e=self.engine();school=self.actor(school_e,'ability/어군');forms=self.forms(school_e,school,('단독의모습','군집의모습'),'ability/어군')
  school_e.start_round(school_e.everyone);school_e.start_of_turn(school,initiative_count=20)
  school_e.activate_ability_state(school,'ability/어군',choice='군집의모습',reason='daily schooling')
  self.assertEqual(school.temp_hp,school.base_max_hp//2);self.assertEqual(school.spec['stats'],forms['군집의모습'])
  school_e.take_damage(school,school.temp_hp+school.base_max_hp//2+1)
  self.assertEqual((school.form,school.temp_hp),('단독의모습',0));self.assertEqual(school.spec['stats'],forms['단독의모습']);self.assertFalse(P.temp_hp_blocked(school))
  self.assertTrue(power_e.validate_state()['valid']);self.assertTrue(school_e.validate_state()['valid'])

 def test_quick_cloak_breaks_on_real_super_effective_hit_and_commits_on_native_evolution(self):
  e=self.engine(1);cloak=self.actor(e,'ability/신속도롱이',species='도롱충이',pos=(3,2))
  material={'materials':['나뭇잎'],'fact':self.fact('nearby leaves')}
  baseline=list(cloak.types);e.activate_ability_state(cloak,'ability/신속도롱이',choice='초목도롱이',observation=material,reason='built cloak')
  self.assertEqual(cloak.types,list(dict.fromkeys([*baseline,'풀'])));self.assertEqual(cloak.form,'초목도롱이')
  attacker=self.actor(e,'ability/멀티타입',name='fire attacker',moves=['move/불꽃세례'],pos=(2,2))
  e.start_round(e.everyone);e.start_of_turn(attacker,initiative_count=20);e.use_move(attacker,cloak,'move/불꽃세례')
  self.assertNotIn('ability/신속도롱이',cloak.spec.get(P.KEY,{}));self.assertEqual(cloak.types,baseline);self.assertIsNone(cloak.form)

  evolve_e=self.engine();worm=self.actor(evolve_e,'ability/신속도롱이',species='도롱충이',level=20)
  material={'materials':['모래'],'fact':self.fact('nearby sand')}
  evolve_e.activate_ability_state(worm,'ability/신속도롱이',choice='모래땅도롱이',observation=material,reason='built sandy cloak')
  out=D.evolve_combatant(evolve_e,worm,'도롱마담 모래땅도롱')
  self.assertTrue(out['evolved']);self.assertNotIn('ability/신속도롱이',worm.spec.get(P.KEY,{}));self.assertIn('땅',worm.spec['types'])
  self.assertEqual(worm.spec['ability_state_permanent_history'][-1]['source'],'ability/신속도롱이')
  self.assertTrue(e.validate_state()['valid']);self.assertTrue(evolve_e.validate_state()['valid'])

 def test_poltergeist_form_hook_grants_exact_ability_and_level_gated_move(self):
  e=self.engine();young=self.actor(e,'ability/폴터가이스트-playtest',level=39,name='young');adult=self.actor(e,'ability/폴터가이스트-playtest',level=40,name='adult')
  FORMS.switch(e,young,'히트로토무');FORMS.switch(e,adult,'히트로토무')
  self.assertIn('ability/타오르는불꽃-playtest',young.abilities);self.assertNotIn('move/오버히트',young.moves)
  self.assertIn('ability/타오르는불꽃-playtest',adult.abilities);self.assertIn('move/오버히트',adult.moves)
  FORMS.switch(e,adult,'워시로토무')
  self.assertNotIn('ability/타오르는불꽃-playtest',adult.abilities);self.assertNotIn('move/오버히트',adult.moves)
  self.assertIn('ability/저수',adult.abilities);self.assertIn('move/하이드로펌프',adult.moves)
  self.assertTrue(e.validate_state()['valid'])

 def test_projection_round_trip_and_corruption_validation(self):
  e=self.engine();c=self.actor(e,'ability/멀티타입');e.activate_ability_state(c,'ability/멀티타입',choice='페어리',reason='saved selection')
  saved=json.loads(json.dumps(e.export_state(),ensure_ascii=False));n=Engine.import_state(Rules(ROOT,ruleset='all'),saved)
  restored=n.everyone[0];self.assertEqual(restored.types,['페어리']);self.assertTrue(n.validate_state()['valid'])
  restored.spec[P.KEY]['ability/멀티타입']['payload']['types']=['불꽃']
  with self.assertRaises(Exception):n.export_state()


if __name__=='__main__':unittest.main()
