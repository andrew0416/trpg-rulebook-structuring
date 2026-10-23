"""Exact bonus-weather templates and source-admitted durable GM definitions."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
from state_codec import StateCodecError
import weather_templates as W

class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.r=Rules(ROOT,ruleset='homebrew');cls.core=Rules(ROOT,ruleset='core')
 def setUp(self):self.e=Engine(self.r,seed=67005)
 def design(self,identity='weather-template/custom-light',**overrides):
  options={'name':'GM light storm','base_type':'물','boost_types':['불꽃','풀'],'reduce_type':'전기','reason':'GM chooses a Water Move type with Fire and Grass boosts and Electric reduction'}
  options.update(overrides);return W.define(self.e,identity,**options)
 def restore(self):return Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
 def test_nine_exact_source_samples_are_typed_immutable_and_not_moves(self):
  expected=[
   ('산성비','Acid Rain',('독','강철'),'땅'),('유성우','Starshower',('노말','강철'),'격투'),
   ('열번개','Heat Lightning',('전기','불꽃'),'땅'),('백야','Midnight Sun',('악','고스트'),'페어리'),
   ('태풍','Typhoon',('비행','물'),'전기'),('군집지령','Hive Order',('벌레','풀'),'불꽃'),
   ('고공','Thin Air',('에스퍼','격투'),'고스트'),('마법안개','Mystic Mist',('페어리','드래곤'),'강철'),
   ('마녀의시간','Witching Hour',('고스트','페어리'),'악')]
  samples=W.catalog(self.r)
  self.assertEqual([(r.name,r.english_name,r.boost_types,r.reduce_type) for r in samples],expected)
  for r in samples:
   self.assertIsInstance(r,W.WeatherTemplate);self.assertEqual(r.source_id,'hb-weather-1')
   with self.assertRaises(FrozenInstanceError):r.reduce_type='물'
   row=r.to_dict();self.assertFalse(row['creates_native_move']);self.assertNotIn('base_type',row)
   self.assertEqual(row['source']['lines'],[69,84]);self.assertNotIn(r.id,self.r.moves)
   for absent in ('frequency','ac','range','duration','lifetime','move_type'):self.assertNotIn(absent,row)
 def test_catalog_and_inspection_copies_do_not_mutate_canonical_data(self):
  sample=W.catalog(self.r)[0];row=sample.to_dict();row['boost_types'][0]='물';row['source']['lines'][0]=0
  again=W.definition(self.e,sample.id)
  self.assertEqual(again['boost_types'],['독','강철']);self.assertEqual(again['source']['lines'],[69,84])
  row=self.design();row['boost_types'][0]='얼음';row['reason']='changed detached return'
  inspected=W.definition(self.e,row['id']);self.assertEqual(inspected['boost_types'],['불꽃','풀'])
  inspected['source']['file']='changed';self.assertTrue(W.validate(self.e))
 def test_explicit_base_not_first_boost_drives_no_shared_weakness_branch(self):
  self.assertFalse(W.weaknesses(self.r,'불꽃')&W.weaknesses(self.r,'풀'))
  row=self.design();self.assertEqual(row['base_type'],'물');self.assertNotIn('전기',W.weaknesses(self.r,'불꽃'))
  self.assertEqual(json.loads(json.dumps(row,ensure_ascii=False)),row)
  before=deepcopy(self.e._weather_templates)
  with self.assertRaises(ValueError):self.design('weather-template/bad',reduce_type='물')
  self.assertEqual(self.e._weather_templates,before)
 def test_shared_weakness_does_not_invent_extra_source_constraint(self):
  self.assertIn('땅',W.weaknesses(self.r,'독')&W.weaknesses(self.r,'강철'))
  row=self.design('weather-template/shared',base_type='노말',boost_types=['독','강철'],reduce_type='페어리',
                  reason='GM explicitly selects Fairy reduction; source constrains only the no-shared branch')
  self.assertEqual(row['reduce_type'],'페어리');self.assertTrue(W.validate(self.e))
 def test_missing_base_invalid_types_boost_count_and_reason_reject_before_mutation(self):
  cases=[{'base_type':'Water'},{'base_type':None},{'boost_types':['물']},
         {'boost_types':['물','전기','불꽃']},{'boost_types':['물','물']},
         {'boost_types':['물','unknown']},{'boost_types':('물','전기')},
         {'reduce_type':'unknown'},{'reason':''},{'reason':'  '}]
  for values in cases:
   with self.subTest(values=values):
    with self.assertRaises(ValueError):self.design(**values)
    self.assertFalse(hasattr(self.e,W.KEY))
  with self.assertRaises(TypeError):
   W.define(self.e,'weather-template/missing',name='missing base',boost_types=['물','전기'],reduce_type='땅',reason='GM choice')
 def test_source_admission_rejects_core_alias_and_excluded_runtime_source(self):
  with self.assertRaises(ValueError):W.catalog(self.core)
  with self.assertRaises(ValueError):W.define(Engine(self.core), 'weather-template/custom',name='core blocked',
    base_type='물',boost_types=['불꽃','풀'],reduce_type='전기',reason='GM choice')
  with self.assertRaises(ValueError):self.design(source_id='hb-weather')
  old=self.r.selection.excluded.get(W.SOURCE)
  self.r.selection.excluded[W.SOURCE]='exclude_units'
  try:
   with self.assertRaises(ValueError):W.catalog(self.r)
  finally:
   if old is None:self.r.selection.excluded.pop(W.SOURCE)
   else:self.r.selection.excluded[W.SOURCE]=old
  self.assertFalse(hasattr(self.e,W.KEY))
 def test_source_metadata_tampering_and_closed_definition_fields_are_rejected(self):
  source=self.r.selection.units[W.SOURCE]['source'];old=deepcopy(source)
  try:
   source['file']='ch05-pokemon.md'
   with self.assertRaises(ValueError):W.catalog(self.r)
  finally:source.clear();source.update(old)
  row=self.design();row['frequency']='하루 x2'
  with self.assertRaises(ValueError):W.validate_definition(self.r,row)
  for key,value in [('source_id','hb-weather'),('source_sha256','0'*64),('source',{'file':'hb-weather.md'}),('creates_native_move',True)]:
   row=W.definition(self.e,'weather-template/custom-light');row[key]=value
   with self.subTest(key=key):
    with self.assertRaises(ValueError):W.validate_definition(self.r,row)
 def test_definition_identity_is_immutable_and_no_runtime_weather_is_created(self):
  moves=set(self.r.moves);row=self.design();before=deepcopy(self.e._weather_templates)
  with self.assertRaises(ValueError):self.design()
  with self.assertRaises(ValueError):self.design('weather-template/산성비')
  self.assertEqual(before,self.e._weather_templates);self.assertEqual(set(self.r.moves),moves)
  self.assertIsNone(self.e.weather);self.assertIsNone(self.e.weather_rounds)
  self.assertFalse(hasattr(self.e,'_weather_state'));self.assertNotIn(row['id'],self.r.selection.units)
 def test_native_json_and_gm_snapshot_restore_preserve_definitions(self):
  first=self.design();self.e.gm.snapshot('weather-design')
  self.design('weather-template/later',name='later explicit design')
  self.e.gm.restore('weather-design',reason='return to inspected first weather design')
  self.assertEqual(set(self.e._weather_templates['definitions']),{first['id']})
  n=self.restore();self.assertEqual(n._weather_templates,self.e._weather_templates)
  self.assertEqual(W.definition(n,first['id']),first);self.assertTrue(W.validate(n))
 def test_digest_state_envelope_and_invalid_restored_source_are_rejected(self):
  self.design();baseline=deepcopy(self.e._weather_templates)
  for mutate in (
   lambda s:s['definitions']['weather-template/custom-light']['definition'].__setitem__('reason','unrecorded new rationale'),
   lambda s:s.__setitem__('version',True),
   lambda s:s['definitions']['weather-template/custom-light'].__setitem__('definition_sha256','wrong'),
   lambda s:s['definitions'].__setitem__('weather-template/other',s['definitions'].pop('weather-template/custom-light'))):
   self.e._weather_templates=deepcopy(baseline);mutate(self.e._weather_templates)
   with self.assertRaises(ValueError):W.validate(self.e)
   with self.assertRaises(StateCodecError):self.e.export_state()
   self.assertIn('weather_template_state',{issue['code'] for issue in self.e.validate_state()['issues']})
  self.e._weather_templates=None
  with self.assertRaises(ValueError):W.validate(self.e)
  with self.assertRaises(StateCodecError):self.e.export_state()
  self.e._weather_templates=deepcopy(baseline);self.e.gm.snapshot('invalid-candidate')
  saved=self.e.gm.snapshots['invalid-candidate']['engine'][W.KEY]
  row=saved['definitions']['weather-template/custom-light']['definition'];row['source']['file']='ch05-pokemon.md'
  saved['definitions']['weather-template/custom-light']['definition_sha256']=W.signature(row)
  with self.assertRaises(ValueError):self.e.gm.restore('invalid-candidate')
  self.assertEqual(self.e._weather_templates,baseline);self.assertTrue(W.validate(self.e))
