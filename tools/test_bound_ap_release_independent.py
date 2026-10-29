"""Independent restricted Bound AP lifecycle tests; source activation remains zero."""
from pathlib import Path
from pypdf import PdfReader
import copy,hashlib,importlib.util,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import action_points as AP, effects as FX, life, downtime, heavy_injury_adapter as H
CONTRACT=ROOT/'data/verification/common-bound-ap-release-contract.json'
class Independent(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='all')
 def fixture(self,adopt=True,native=False):
  rules=Rules(str(ROOT),ruleset="core") if native else self.rules
  e=Engine(rules,seed=0)
  a=Combatant(rules,dict(name='same',kind='trainer',level=10,stats={s:30 for s in ('hp','atk','def','spa','spd','spe')},moves=['struggle'],abilities=[],types=[]))
  b=Combatant(rules,dict(name='same',kind='trainer',level=10,stats={s:30 for s in ('hp','atk','def','spa','spd','spe')},moves=['struggle'],abilities=[],types=[]))
  e.everyone=e.gm.everyone=[a,b]
  a.spec.update(ap_bound={'A':2,'B':1},ap_spent=1,ap_removed=1)
  m={'type':'damage_roll_mod','value':3,'move_type':'불꽃'};other={'type':'damage_roll_mod','value':2}
  FX.apply_passives(e,a,[m,other])
  if adopt:self.assertEqual(e.adopt_bound_ap_modifier(a,'A',modifier=m,ending_method='none_specified',source_ref='test_fixture/imported; activation not certified').status,'adopted')
  e.start_round([a,b]);e.start_of_turn(a)
  return e,a,b,m,other
 def projection(self,e,a):
  return copy.deepcopy((a.spec,a.modifiers,a.hp,a.temp_hp,a.injuries,a.budget,a._action_history,a.took_standard,a.move_uses,e.elapsed_seconds,e.rng.getstate()))
 def release(self,e,a,event='E'):return e.release_bound_ap(a,'A',event_id=event)
 def test_001_actual_damage_formula_type_filter_and_sibling_effect(self):
  e,a,b,m,o=self.fixture();base=e.r.move('struggle');fire=dict(base,type='불꽃')
  before_fire=e.roll_damage(a,b,fire,set_damage=True);before_normal=e.roll_damage(a,b,base,set_damage=True)
  z=self.release(e,a);self.assertEqual(z.released_ap,2)
  self.assertEqual(before_fire-e.roll_damage(a,b,fire,set_damage=True),3)
  self.assertEqual(before_normal,e.roll_damage(a,b,base,set_damage=True));self.assertIs(a.modifiers[0],o)
 def test_002_free_release_then_real_standard_attack_keeps_budget_authority(self):
  e,a,b,m,o=self.fixture();self.release(e,a);hp=b.hp
  e.use_move(a,b,'struggle',set_damage=True)
  self.assertLess(b.hp,hp);self.assertEqual(a.move_uses['struggle'],1)
  self.assertEqual(a._action_history,['free','standard']);self.assertEqual(a.budget['standard'],0)
 def test_003_real_other_turn_refused_next_own_round_allowed(self):
  e,a,b,m,o=self.fixture();e.end_of_turn(a);e.start_of_turn(b);before=self.projection(e,a)
  self.assertEqual(self.release(e,a).status,'rejected');self.assertEqual(before,self.projection(e,a))
  e.end_of_turn(b);e.end_round();e.start_round([a,b]);e.start_of_turn(a)
  self.assertEqual(self.release(e,a).status,'released');self.assertEqual(e.elapsed_seconds,10)
 def test_004_preadoption_snapshot_removes_new_identity_attribute(self):
  e,a,b,m,o=self.fixture(adopt=False);e.gm.snapshot('pre')
  e.adopt_bound_ap_modifier(a,'A',modifier=m,ending_method='none_specified',source_ref='test_fixture')
  self.release(e,a);e.gm.restore('pre')
  self.assertFalse(hasattr(a,'_ap_bound_effects'));self.assertEqual(AP.available(a),2)
  self.assertEqual(len(a.modifiers),2);self.assertEqual(self.release(e,a).status,'pending')
 def test_005_postrelease_snapshot_stays_ended_and_no_second_refund(self):
  e,a,b,m,o=self.fixture();self.release(e,a);e.gm.snapshot('ended')
  e.gm.restore('ended');before=self.projection(e,a)
  self.assertEqual(self.release(e,a,'new-event').status,'rejected');self.assertEqual(before,self.projection(e,a))
  self.assertEqual(a._ap_bound_effects['A']['state'],'ended')
 def test_006_scene_then_actual_next_turn_preserves_binding_until_free_end(self):
  e,a,b,m,o=self.fixture();e.end_of_turn(a)
  e.end_scene([a,b],round_elapsed_seconds=2)
  self.assertEqual(a.spec['ap_spent'],0);self.assertEqual(a.spec['ap_removed'],1)
  self.assertEqual(AP.available(a),3);self.assertTrue(any(x is m for x in a.modifiers))
  e.start_round([a,b]);e.start_of_turn(a)
  self.assertEqual(self.release(e,a).status,'released');self.assertEqual(AP.available(a),5)
  self.assertEqual(a.spec['ap_bound'],{'B':1})
 def test_007_separate_owners_same_names_instance_and_event_ids(self):
  e,a,b,m,o=self.fixture();b.spec.update(ap_bound={'A':2});other=dict(m);FX.apply_passives(e,b,[other])
  self.assertEqual(e.adopt_bound_ap_modifier(b,'A',modifier=other,ending_method='none_specified',source_ref='test_fixture').status,'adopted')
  self.assertEqual(self.release(e,a).status,'released');self.assertEqual(b.spec['ap_bound'],{'A':2})
  e.end_of_turn(a);e.start_of_turn(b);self.assertEqual(self.release(e,b).status,'released')
  self.assertEqual(a._ap_bound_effects['A']['end_event']['id'],b._ap_bound_effects['A']['end_event']['id'])
 def test_008_public_registration_after_adoption_invalidates_shared_ownership(self):
  e,a,b,m,o=self.fixture();FX.apply_passives(e,b,[m]);before=self.projection(e,a)
  z=self.release(e,a)
  self.assertEqual(z.status,'pending');self.assertEqual(before,self.projection(e,a))
  self.assertTrue(any(x is m for x in a.modifiers));self.assertTrue(any(x is m for x in b.modifiers))
 def test_009_equal_distinct_public_registration_does_not_block(self):
  e,a,b,m,o=self.fixture();equal=dict(m);FX.apply_passives(e,b,[equal])
  self.assertEqual(self.release(e,a).status,'released');self.assertIs(b.modifiers[0],equal)
 def test_010_actual_heavy_pending_stops_release_without_AP_or_effect_mutation(self):
  e,a,b,m,o=self.fixture();b.injuries=5;b.hp=50
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  before=self.projection(e,a)
  with self.assertRaises(H.HeavyPending):self.release(e,a)
  self.assertEqual(before,self.projection(e,a));self.assertTrue(e._heavy_pending)
 def test_011_death_then_GM_positive_HP_still_cannot_release(self):
  e,a,b,m,o=self.fixture();e.gm.set_hp(a,-500);life.sync(e,a);self.assertTrue(a.dead)
  e.gm.set_hp(a,20);self.assertGreater(a.hp,0);self.assertTrue(a.fainted)
  before=self.projection(e,a);self.assertEqual(self.release(e,a).status,'rejected');self.assertEqual(before,self.projection(e,a))
 def test_012_new_scene_does_not_create_missing_lifetime_proof(self):
  e,a,b,m,o=self.fixture(adopt=False);e.end_of_turn(a);e.end_scene([a,b],round_elapsed_seconds=1)
  e.start_round([a,b]);e.start_of_turn(a);before=self.projection(e,a)
  self.assertEqual(self.release(e,a).status,'pending');self.assertEqual(before,self.projection(e,a))
 def test_013_all_source_anchors_exact_hash_excerpt_and_pdf(self):
  j=json.loads(CONTRACT.read_text(encoding='utf8'));self.assertEqual(len(j['source_anchors']),7)
  for a in j['source_anchors']:
   p=ROOT/a['file'];self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),a['file_sha256'])
   ex=PdfReader(str(p)).pages[a['page_index']].extract_text() if 'page_index' in a else '\n'.join(p.read_text(encoding='utf8').splitlines()[a['start']-1:a['end']])
   if 'page_index' in a:self.assertIn(a['excerpt'],ex)
   else:self.assertEqual(ex,a['excerpt'])
   self.assertEqual(hashlib.sha256(a['excerpt'].encode()).hexdigest(),a['excerpt_sha256'])
 def test_014_contract_source_and_author_test_ids_resolve(self):
  j=json.loads(CONTRACT.read_text(encoding='utf8'));ids={a['id'] for a in j['source_anchors']}
  s=importlib.util.spec_from_file_location('bound_author_test_ids',ROOT/'tools/test_bound_ap_release.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
  tests={'BOUND-AP-'+x for x in unittest.defaultTestLoader.getTestCaseNames(m.BoundAPTests)}
  for c in j['clauses']:
   self.assertLessEqual(set(c['source_refs']),ids);self.assertLessEqual(set(c['test_ids']),tests)
   self.assertFalse(c['semantic_closure'])
  independent={'BAP-INDEPENDENT-'+x for x in unittest.defaultTestLoader.getTestCaseNames(Independent)}
  for links in j.get('independent_regressions',{}).values():self.assertLessEqual(set(links),independent)
 def test_015_bind_source_activation_stays_explicitly_unimplemented(self):
  amount,reason=AP.quote({'frequency':{'raw':'Bind 2 AP','ap':2}},[{'type':'cost','ap':2}])
  self.assertIsNone(amount);self.assertIn('수명',reason)
 def test_016_AP84_sentences_address_distinct_compatible_axes(self):
  j=json.loads(CONTRACT.read_text(encoding='utf8'))
  korean=next(a['excerpt'] for a in j['source_anchors'] if a['id']=='BAP-S01')
  pdf=next(a for a in j['source_anchors'] if a['id']=='BAP-S07')
  english=PdfReader(str(ROOT/pdf['file'])).pages[pdf['page_index']].extract_text()
  self.assertIn('액션 포인트가 필요한 재주를 제외하고 특별한 행동을 하는 데에는 액션 포인트가 필요하지 않습니다',korean)
  self.assertIn('not cost any special action to use Action Points except',english)
  self.assertIn('the Action required by the Feature',english)
 def release_all(self,e,a,o):
  self.assertEqual(e.adopt_bound_ap_modifier(a,'B',modifier=o,ending_method='none_specified',source_ref='test_fixture').status,'adopted')
  self.assertEqual(self.release(e,a).status,'released')
  self.assertEqual(e.release_bound_ap(a,'B',event_id='E-B').status,'released')
  for record in a._ap_bound_effects.values():
   self.assertNotIn('owner',record);self.assertNotIn('modifier',record)
   json.dumps(record) # A passive receipt has no runtime actor/effect references.
 def test_017_ended_receipts_allow_real_heavy_target_attack(self):
  e,a,b,m,o=self.fixture(native=True);self.release_all(e,a,o);b.injuries=5;b.hp=50
  self.assert_native_heavy_target_pending(e,a,b)
  self.assertEqual(a.move_uses['struggle'],1);self.assertEqual(a._action_history,['free','free','standard'])
 def assert_native_heavy_target_pending(self,e,a,b):
  # The native turn clock is not the old empty-context automatic-loss certificate.
  before=b.hp
  with self.assertRaises(H.HeavyPending):e.use_move(a,b,'struggle',set_damage=True)
  packet=e._heavy_events[e._heavy_pending]
  self.assertIs(packet['target'],b);self.assertEqual(packet['status'],'pending')
  self.assertEqual(packet['before']['hp'],before);self.assertEqual(packet['observed_after']['hp'],b.hp)
  self.assertEqual(b.hp,before-packet['amount'])
  self.assertIn('attacker:custom_conditions',packet['context_evidence']['failures'])
  self.assertEqual(H.passive_prefix_failures(e,a,b),[])
  self.assertTrue(all(row['state']=='ended' and 'owner' not in row and 'modifier' not in row for row in a._ap_bound_effects.values()))
 def test_018_ended_receipts_allow_real_heavy_actor_standard(self):
  e,a,b,m,o=self.fixture(native=True);self.release_all(e,a,o);a.injuries=5;a.hp=50
  hp=b.hp;e.use_move(a,b,'struggle',set_damage=True)
  self.assertEqual(a.hp,45);self.assertEqual(b.hp,hp-11);self.assertFalse(e._heavy_pending)
  self.assertEqual(a.move_uses['struggle'],1)
 def test_019_active_snapshot_restores_exact_effect_owner_then_ends_again(self):
  e,a,b,m,o=self.fixture();e.gm.snapshot('active');self.release(e,a);e.gm.restore('active')
  record=a._ap_bound_effects['A'];self.assertIs(record['owner'],a)
  self.assertTrue(any(x is record['modifier'] for x in a.modifiers))
  self.assertEqual(AP.available(a),2);self.assertEqual(self.release(e,a).status,'released')
  self.assertNotIn('owner',a._ap_bound_effects['A']);self.assertNotIn('modifier',a._ap_bound_effects['A'])
  self.assertEqual(AP.available(a),4)
 def test_020_ended_snapshot_restore_keeps_heavy_path_and_duplicate_guard(self):
  e,a,b,m,o=self.fixture(native=True);self.release_all(e,a,o);b.injuries=5;b.hp=50
  e.gm.snapshot('ended');self.assert_native_heavy_target_pending(e,a,b);e.gm.restore('ended')
  self.assertFalse(e._heavy_pending);self.assertEqual(b.hp,50)
  before=self.projection(e,a);z=self.release(e,a,'new')
  self.assertEqual(z.reason,'effect_already_ended');self.assertEqual(before,self.projection(e,a))
  self.assert_native_heavy_target_pending(e,a,b)
class Result(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='BAP-INDEPENDENT-'+t._testMethodName,status='pass'))
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='BAP-INDEPENDENT-'+t._testMethodName,status='fail',detail=self._exc_info_to_string(e,t)))
 def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='BAP-INDEPENDENT-'+t._testMethodName,status='error',detail=self._exc_info_to_string(e,t)))
if __name__=='__main__':
 r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Independent))
 paths=list((ROOT/'engine').glob('*.py'))+[Path(__file__),CONTRACT,ROOT/'tools/test_bound_ap_release.py']
 j=json.loads(CONTRACT.read_text(encoding='utf8'));paths += [ROOT/a['file'] for a in j['source_anchors']]
 report=dict(results=r.rows,tests_run=r.testsRun,scope='Imported binding single modifier only; source activation producers=0; no full Bound AP closure.',
             input_hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in set(paths)})
 (ROOT/'output/bound-ap-release-independent-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 sys.exit(not r.wasSuccessful())
