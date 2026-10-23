"""Actual selected Ice Jet effect emission, local state and weather consumption."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
import test_category2_optional_catalog_nine as _fixture_test_category2_optional_catalog_nine
import weather_state as W
import effects as FX
import field_effects as FIELD
import items as ITEMS
import state_grants as GRANTS

ROOT=Path(__file__).resolve().parents[1]

class LocalSnowTests(_fixture_test_category2_optional_catalog_nine.OptionalCatalogNineTests):
 def emit(self,e,a):
  e.gm.set_ability(a,'아이스제트',reason='actual selected source for local Snow emission')
  effect=json.loads((ROOT/'data/abilities-llm.json').read_text(encoding='utf-8'))['abilities']['아이스제트'][0]
  e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  e.apply_effect(a,a,deepcopy(effect),20,True,0,'ability/아이스제트')
  return effect

 def test_actual_ice_jet_effect_emission_is_local_hail_not_slow_terrain(self):
  e,a,near,far=self.fixture()
  e.gm.set_ability(a,'아이스제트',reason='actual selected source for local Snow emission')
  effect=json.loads((ROOT/'data/abilities-llm.json').read_text(encoding='utf-8'))['abilities']['아이스제트'][0]
  self.assertEqual(effect,{'type':'create_terrain','terrain':'snow (설경)','shape':'burst 2','until':"end of user's next round"})
  e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  slow=deepcopy(e.grid.slow);e.gm.set_weather('rain',rounds=5,reason='independent actual global weather')
  batch=e.apply_effect(a,a,deepcopy(effect),20,True,0,'ability/아이스제트')
  self.assertEqual(batch[1],0)
  self.assertEqual(e.grid.slow,slow)
  self.assertEqual(e.weather,'rain')
  active=W.effective_state(e,near)['active']
  self.assertEqual(active['weather'],'hail');self.assertEqual(active['source_id'],'ability/아이스제트')
  self.assertTrue(FX.weather_matches(e,'snow',near));self.assertTrue(FX.weather_matches(e,'hail',near))
  self.assertFalse(FX.weather_matches(e,'hail',far));self.assertTrue(FX.weather_matches(e,'rain',far))
  self.assertTrue(e.validate_state()['valid'])
  e=self.restored(e);a=next(c for c in e.everyone if c.entity_id==a.entity_id)
  near=next(c for c in e.everyone if c.entity_id==near.entity_id)
  self.assertEqual(W.effective_state(e,near)['active']['weather'],'hail')
  e.end_of_turn(a)
  self.assertEqual(W.effective_state(e,near)['active']['weather'],'hail')
  e.end_round();e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  self.assertEqual(W.effective_state(e,near)['active']['weather'],'hail')
  e.end_of_turn(a)
  self.assertEqual(W.effective_state(e,near)['active']['weather'],'hail')
  e.end_round()
  self.assertEqual(W.effective_state(e,near)['active']['weather'],'rain')
  self.assertTrue(e.validate_state()['valid']);self.restored(e)

 def test_local_snow_refreshes_actual_forecast_traits_capture_and_environment_on_movement_and_end(self):
  from builder import build_pokemon
  from engine import Combatant
  import environment_derive as ED
  e,a,_,_=self.fixture()
  pokemon=[]
  for name,pos in (('snow-inside',(3,3)),('snow-outside',(8,3))):
   c=Combatant(self.r,build_pokemon(self.r,'캐스퐁',30,name=name,moves=['move/몸통박치기'],
       extra={'abilities':['ability/기분파'],'pos':pos,'side':'party'}))
   e.gm.add_combatant(c);pokemon.append(c)
  near,far=pokemon
  GRANTS.grant(near,'capabilities','날씨 형상','test:source:weathershape','actual granted capability reader')
  declaration=json.loads((ROOT/'data/examples/environment-derive.json').read_text(encoding='utf-8'))
  e.observe_environment('snow-test-region',dict(gravity=1,pressure=1,air_available=True,medium='air'),
      source=declaration['source'],reason='actual full-body weather comparison region')
  e.bind_environment(near,declaration,reason='actual actor environmental baseline')
  e.gm.set_weather('rain',rounds=5,reason='actual independent global rain')
  self.assertEqual(near.types,['물']);self.assertEqual(far.types,['물'])
  self.emit(e,a)
  self.assertEqual(near.types,['얼음']);self.assertEqual(far.types,['물'])
  view=e.capability_traits(near)['weathershape_appearance']
  self.assertEqual((view['weather'],view['appearance'],view['weather_source']),('hail','light blue','ability/아이스제트'))
  self.assertEqual(ED.context(e,near)['weather'],'hail')
  self.assertEqual(ITEMS.ball_modifier(e,'헤일-볼',a,near)[0],4)
  self.assertEqual(ITEMS.ball_modifier(e,'헤일-볼',a,far)[0],0)
  e.gm.set_position(near,(8,4),reason='actual movement outside the fixed original Snow area')
  self.assertEqual(near.types,['물']);self.assertEqual(ITEMS.ball_modifier(e,'헤일-볼',a,near)[0],0)
  self.assertEqual(ED.context(e,near)['weather'],'rain')
  e.gm.set_position(near,(3,3),reason='actual return into original Snow area')
  self.assertEqual(near.types,['얼음']);self.assertEqual(ITEMS.ball_modifier(e,'헤일-볼',a,near)[0],4)
  self.assertTrue(e.validate_state()['valid']);self.restored(e)
  e.end_scene(e.everyone)
  self.assertFalse(FIELD.validate_local(e));self.assertEqual(near.types,['물'])
  self.assertEqual(e.capability_traits(near)['weathershape_appearance']['appearance'],'blue and grey')
  self.assertEqual(ITEMS.ball_modifier(e,'헤일-볼',a,near)[0],0)
  self.assertTrue(e.validate_state()['valid']);self.restored(e)

 def test_local_snow_exact_source_geometry_deadline_and_effect_receipt_reject_forgery(self):
  from state_codec import StateCodecError
  e,a,near,far=self.fixture();self.emit(e,a)
  state=getattr(e,FIELD.LOCAL_KEY);key=next(iter(state['receipts']))
  before=deepcopy(state['receipts'][key])
  self.assertEqual(before['expires_round'],e.round_no+1)
  self.assertEqual(before['cells'],[list(p) for p in sorted(e.grid.burst((2,2),2))])
  self.assertEqual(before['source_id'],'ability/아이스제트')
  self.assertEqual(before['effect_occurrence'],before['request_id'])
  for change in (lambda r:r.update(expires_round=r['round']),lambda r:r.update(source_id='ability/곰팡이군주'),
                 lambda r:r['cells'].append([29,14]),lambda r:r.update(effect_occurrence='fabricated')):
   row=deepcopy(before);change(row);row['seal']=FIELD._local_seal(row);state['receipts'][key]=row
   self.assertFalse(e.validate_state()['valid'])
   with self.assertRaises(StateCodecError):e.export_state()
   state['receipts'][key]=deepcopy(before)
  self.assertTrue(e.validate_state()['valid']);self.restored(e)

 def test_chilly_reception_raw_snow_and_explicit_natural_weather_keep_original_five_round_source(self):
  import homebrew_weather as HOME
  e,a,_,_=self.fixture()
  effect=json.loads((ROOT/'data/moves-llm.json').read_text(encoding='utf-8'))['moves']['썰렁개그']['effects'][0]
  self.assertEqual(effect,{'type':'set_weather','weather':'snow','rounds':5})
  self.assertIsNone(HOME.definition(self.r,'move/썰렁개그'))
  e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
  e.apply_effect(a,a,deepcopy(effect),20,True,0,'move/썰렁개그')
  active=e._weather_state['active']
  self.assertEqual((e.weather,active['source_id'],active['duration']),('hail','move/썰렁개그',5))
  self.assertIsNone(active.get('policy'))
  self.assertTrue(FX.weather_matches(e,'snow',a));self.assertTrue(FX.weather_matches(e,'hail',a))
  self.assertTrue(e.validate_state()['valid']);self.restored(e)
  e.gm.observe_natural_weather('actual selected Snow',treat_as='snow',reason='explicit source equivalent')
  self.assertEqual((e.weather,e._weather_state['active']['origin']),('hail','natural'))
  self.assertEqual(e._weather_state['natural']['equivalent'],'hail')
  e.gm.observe_natural_weather('white clouds only',treat_as=None,reason='no mechanical equivalent')
  self.assertIsNone(e.weather)
  self.assertTrue(e.validate_state()['valid']);self.restored(e)




 def test_actual_registration_inside_live_snow_and_failed_add_preserve_identity_and_atomicity(self):
  from builder import build_pokemon
  from engine import Combatant
  from ruleset import UnresolvedRuleSelection
  e,a,_,_=self.fixture()
  e.gm.set_weather('rain',rounds=5,reason='independent actual global rain')
  self.emit(e,a)
  newcomer=Combatant(self.r,build_pokemon(self.r,'캐스퐁',30,name='actual-new-forecast',
      moves=['move/몸통박치기'],extra={'abilities':['ability/기분파'],'pos':(3,3),'side':'party'}))
  e.gm.add_combatant(newcomer)
  self.assertEqual(newcomer.types,['얼음'])
  self.assertEqual(sum(c is newcomer for c in e.everyone),1)
  self.assertEqual(sum(c is newcomer for c in e.gm.everyone),1)
  self.assertEqual(W.effective_state(e,newcomer)['active']['weather'],'hail')
  self.assertTrue(e.validate_state()['valid']);self.restored(e)
  rejected=Combatant(self.r,build_pokemon(self.r,'캐스퐁',30,name='actual-failed-forecast',
      moves=['move/몸통박치기'],extra={'abilities':['ability/기분파'],'pos':(3,4),'side':'party'}))
  rejected.abilities.append('ability/__missing_native_registration_source__')
  rejected.spec['abilities']=list(rejected.abilities)
  before=e.export_state();rng=e.rng.getstate()
  actor_before=deepcopy(vars(rejected),{id(self.r):self.r})
  with self.assertRaises(UnresolvedRuleSelection):e.gm.add_combatant(rejected)
  self.assertEqual(e.export_state(),before)
  self.assertEqual(e.rng.getstate(),rng)
  self.assertEqual(vars(rejected),actor_before)
  self.assertFalse(any(c is rejected for c in e.everyone))
  self.assertFalse(any(c is rejected for c in e.gm.everyone))
  foreign=deepcopy(newcomer,{id(self.r):self.r})
  with self.assertRaises(ValueError):FIELD.local_weather_for(e,foreign)

if __name__=='__main__':unittest.main()
