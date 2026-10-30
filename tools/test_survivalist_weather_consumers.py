"""U-012 through actual HB Guide and existing native weather consumers."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
import test_csv_survivalist_hb as HB
import book_survivalist_fixture as FIX
import state_grants as GRANTS
import core_weather_abilities as WEATHER
import survivalist_class as SC


class SurvivalistWeatherConsumerTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  from ruleset import RuleFilter
  profile=deepcopy(RuleFilter.load(ROOT,'all').profile)
  profile['exclude_units']=list(profile.get('exclude_units',[]))+['hb-weather']
  selected=RuleFilter(profile,'all-with-core-weather')
  with patch.object(RuleFilter,'load',return_value=selected):
   cls.rules=Rules(ROOT,ruleset='all')

 def test_fixture_selects_core_ambient_weather_with_csv_abilities(self):
  import homebrew_weather as HOME
  self.assertFalse(HOME.enabled(self.rules))

 def scene(self,source):
  fixture=HB.SurvivalistHBTests();fixture.rules=self.rules;fixture.setUp();self.addCleanup(fixture.doCleanups)
  world=fixture.world(terrains=('desert',))
  engine,foe=world['engine'],world['foe']
  GRANTS.grant(foe,'abilities',source,'gm/weather-test/'+source,'gm',rule_id=source)
  GRANTS.reconcile(engine,foe)
  return fixture,world

 def ground(self,e,actor,cover):
  return e.observe_environment('weather-ground',
   {'gravity':1,'pressure':1,'air_available':True,'medium':'air','ground_cover':cover},
   cells=[actor.pos],source=SC.GUIDE,reason='actual observed sand snow or grass surface')

 def test_four_weather_initiative_families_keep_independent_low_hp_and_restore(self):
  variants=(('ability/엽록소-playtest','sunny'),('ability/쓱쓱-playtest','rain'),
            ('ability/모래헤치기-playtest','sandstorm'),('ability/눈치우기','hail'))
  for source,weather in variants:
   with self.subTest(source=source):
    f,w=self.scene(source);e,a,foe=(w[k] for k in ('engine','trainer','foe'))
    e.gm.set_weather(weather,rounds=None,reason='actual source weather')
    base=foe.staged('spe');self.assertEqual(e.initiative_value(foe).value,base*2)
    acquired=list(foe.abilities);FIX.battle(e,a);FIX.audible_order(e,a);f.guide(e,a)
    self.assertEqual(e.initiative_value(foe).value,base)
    e.gm.set_hp(foe,foe.base_max_hp//2-1,reason='independent actual low HP')
    self.assertEqual(e.initiative_value(foe).value,base*2)
    e.gm.set_hp(foe,(foe.base_max_hp+1)//2,reason='no longer strictly below half')
    self.assertEqual(e.initiative_value(foe).value,base)
    loaded,index=FIX.restore(self.rules,e);other=index[foe.entity_id]
    self.assertEqual((loaded.initiative_value(other).value,other.abilities),(base,acquired))
    self.assertTrue(loaded.validate_state()['valid'])
    e.end_encounter(round_elapsed_seconds=10)
    self.assertEqual(e.initiative_value(foe).value,base*2)

 def test_weather_initiative_copies_coalesce_and_suppression_and_revocation_remove_contribution(self):
  for source,copy,weather in (('ability/쓱쓱-playtest','ability/쓱쓱-playtest-2','rain'),
                              ('ability/눈치우기','ability/눈치우기-2','hail')):
   with self.subTest(source=source):
    _,w=self.scene(copy);e,foe=w['engine'],w['foe']
    GRANTS.grant(foe,'abilities',source,'gm/weather-second-copy','gm',rule_id=source)
    GRANTS.reconcile(e,foe)
    e.gm.set_weather(weather,rounds=None,reason='actual duplicate-source weather')
    base=foe.staged('spe')
    self.assertEqual(e.initiative_value(foe).value,base*2)
    e.gm.set_hp(foe,foe.base_max_hp//2-1,reason='both printed predicates true')
    self.assertEqual(e.initiative_value(foe).value,base*2)
    foe.abilities_suppressed=True
    self.assertEqual(e.initiative_value(foe).value,base)
    foe.abilities_suppressed=False
    GRANTS.revoke(foe,'gm/weather-test/'+copy,engine=e)
    GRANTS.revoke(foe,'gm/weather-second-copy',engine=e);GRANTS.reconcile(e,foe)
    self.assertEqual(e.initiative_value(foe).value,base)

 def test_weather_initiative_legacy_projection_requires_its_actual_registration(self):
  source='ability/쓱쓱-playtest'
  _,w=self.scene(source);e,foe=w['engine'],w['foe']
  e.gm.set_weather('rain',rounds=None,reason='actual weather for registration checks')
  row=next(row for row in foe.modifiers if row.get('_rule_id')==source and row.get('type')=='initiative_multiplier')
  original=deepcopy(row);state=foe.spec[GRANTS.KEY]
  token=row[GRANTS.TAG];label=row['_ability']
  base=foe.staged('spe')
  self.assertEqual(e.initiative_value(foe).value,base*2)
  for change in ({GRANTS.TAG:None},{GRANTS.TAG:'missing-weather-registration'},
                 {'_initiative_receipt':'forged-dispatch'}, {'_ability':'unrelated Ability'}, {'value':3}):
   with self.subTest(change=change):
    row.clear();row.update(original);row.update(change)
    result=e.initiative_value(foe)
    self.assertIsNone(result.value);self.assertTrue(result.unresolved)
  row.clear();row.update(original)
  receipt=state['effects'].pop(token)
  result=e.initiative_value(foe)
  self.assertIsNone(result.value);self.assertTrue(result.unresolved)
  state['effects'][token]=receipt
  fields=receipt['rows'];receipt['rows']=[]
  result=e.initiative_value(foe)
  self.assertIsNone(result.value);self.assertTrue(result.unresolved)
  receipt['rows']=fields
  state['ability_receipts'].pop(label)
  result=e.initiative_value(foe)
  self.assertIsNone(result.value);self.assertTrue(result.unresolved)
  state['ability_receipts'][label]=token
  foe.abilities_suppressed=True
  self.assertEqual(e.initiative_value(foe).value,base)
  foe.abilities_suppressed=False
  self.assertEqual(e.initiative_value(foe).value,base*2)
  self.assertTrue(e.validate_state()['valid'])

 def test_veil_evasion_keeps_base_and_terrain_while_guided_attacker_ignores_named_ability(self):
  for source,(weather,surface) in WEATHER.VEILS.items():
   with self.subTest(source=source):
    f,w=self.scene(source);e,a,p,foe=(w[k] for k in ('engine','trainer','partner','foe'))
    self.ground(e,foe,[])
    base=foe.evasion('물리',engine=e)
    self.assertEqual(WEATHER.evasion_contributions(e,foe)[source],1)
    e.gm.set_weather(weather,rounds=None,reason='actual matching weather')
    self.assertEqual(foe.evasion('물리',engine=e),base+1)
    FIX.battle(e,a);FIX.audible_order(e,a);f.guide(e,a)
    self.assertEqual(foe.evasion('물리',engine=e),base)
    self.assertEqual(SC.ignored_ability_evasion(e,p,foe),1)
    e.change_environment('weather-ground',{'ground_cover':[surface]},source=SC.GUIDE,
                         request_id='cover/'+surface,reason='actual independent surface change')
    self.assertEqual(WEATHER.evasion_contributions(e,foe)[source],2)
    self.assertEqual(foe.evasion('물리',engine=e),base+1)
    self.assertEqual(SC.ignored_ability_evasion(e,p,foe),2)
    loaded,index=FIX.restore(self.rules,e)
    self.assertEqual(WEATHER.evasion_contributions(loaded,index[foe.entity_id])[source],2)
    self.assertTrue(loaded.validate_state()['valid'])

 def test_veil_adjacent_weather_immunity_is_sourced_and_suppressed_at_its_enemy_owner(self):
  for source,(weather,_) in WEATHER.VEILS.items():
   with self.subTest(source=source):
    f,w=self.scene(source);e,a,foe=(w[k] for k in ('engine','trainer','foe'))
    friend=Combatant(self.rules,FIX.pokemon_spec(self.rules,None,'enemy-neighbor'))
    e.gm.add_combatant(friend,pos=(8,3),side='wild',reason='actual adjacent foe ally')
    e.gm.set_weather(weather,rounds=None,reason='actual damaging weather')
    self.assertEqual(WEATHER.weather_hp_immunity(e,friend,weather),source)
    FIX.battle(e,a);FIX.audible_order(e,a);f.guide(e,a)
    self.assertIsNone(WEATHER.weather_hp_immunity(e,friend,weather))
    before=friend.hp
    FIX.next_turn(e,a,friend,count=10)
    self.assertEqual(before-friend.hp,e.tick_loss(friend))
    self.assertTrue(e.validate_state()['valid'])

 def test_sun_veil_keeps_unconditional_evasion_but_loses_sunny_grass_and_damage_reduction(self):
  import environmental_effects as ENV
  f,w=self.scene('ability/햇살베일');e,a,p,foe=(w[k] for k in ('engine','trainer','partner','foe'))
  self.ground(e,foe,['grass'])
  base=foe.evasion('물리',engine=e)
  e.gm.set_stat(p,'spa',value=30,reason='actual damage observer stat')
  e.gm.set_stat(foe,'spd',value=1,reason='actual target defense')
  e.gm.set_weather('sunny',rounds=None,reason='actual sunny weather')
  move=self.rules.move('move/냉동빔')
  damage=e.roll_damage(p,foe,move,set_damage=True)
  fall_dr=ENV._fall_defense(e,foe)[1]
  self.assertEqual(foe.evasion('물리',engine=e),base+1)
  FIX.battle(e,a);FIX.audible_order(e,a);f.guide(e,a)
  self.assertEqual(foe.evasion('물리',engine=e),base)
  self.assertEqual(e.roll_damage(p,foe,move,set_damage=True),damage+5)
  self.assertEqual(ENV._fall_defense(e,foe)[1],fall_dr-5)
  self.assertTrue(e.validate_state()['valid'])

 def test_duplicate_weather_rows_use_the_same_selected_source_without_new_ability_instances(self):
  import ability_transitions as A
  for name,ids in WEATHER.WEATHER_VARIANTS.items():
   if len(ids)==1:continue
   with self.subTest(name=name):
    f,w=self.scene(ids[-1]);e,foe=w['engine'],w['foe']
    self.assertEqual(A.ability_id(self.rules,ids[-1]),ids[0])
    self.assertEqual(sum(A.ability_id(self.rules,value)==ids[0] for value in foe.abilities),1)
    self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()