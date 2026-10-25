"""Batch15: fixed AP lifetime and crafting default clauses, actual native paths."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
import action_points as AP
import action_metadata as META
import downtime as DT
import crafting_activities as CRAFT
import combat_precision_features as CPF
import effects as FX
SCOPES={'C3-CORE-034':'6029d4c1139b55193a6be11ed3c3365dfb820e490a9b323e4ba128fbffe6fc84','C3-EX-033':'16370932b142b8e23ab3ea3c515e849d0c43e296b10b0b6fdf76d502d29ac1af'}
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,155)
  self.a=self.actor('trainer/a','trainer');self.p=self.actor('pokemon/p','pokemon');self.b=self.actor('trainer/b','trainer')
  self.a.spec.update(feats=[CPF.PRECISION],edges=['edge/몬스터볼','edge/보석-지식'],items={'몬스터볼 공구함':1},money=400,shards={'빨강':2})
  self.p.spec['trainer_id']=self.a.spec['id'];self.e.everyone=self.e.gm.everyone=[self.a,self.p,self.b]
  self.e.gm.observe_sensory_environment(self.a,self.p,paths={'auditory':True},present=True,reason='actual allied recipient hears the current Pinpoint Order')
 def actor(self,uid,kind):
  return Combatant(self.r,dict(id=uid,name=uid,kind=kind,level=15,stats={s:10 for s in ['hp','atk','def','spa','spd','spe']},skills={'명령':5,'통찰':5,'기술학':4,'오컬트학':3},feats=[],edges=[],items={},movement={'land':5},moves=['move/몸통박치기']))
 def state(self):return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,self.e.encounter_active,self.e.round_no,[(c.spec,c.hp,c.injuries,c.conditions,c.modifiers,getattr(c,'budget',None),getattr(c,'_action_history',None)) for c in self.e.everyone]))
 def turn(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
 def changed_source(self,source):
  original=self.r._selected_rule
  return patch.object(self.r,'_selected_rule',side_effect=lambda uid, *args, **kwargs: uid + '/unreviewed' if uid == source else original(uid, *args, **kwargs))
 def craft(self,**kw):
  options=dict(item='item/몬스터볼-2',minutes=5,reason='GM actual Extended work time');options.update(kw)
  return self.e.pokemon_activity(self.a,'craft_item',**options)
 def adopted(self,ending='none_specified'):
  self.a.spec.update(ap_bound={'bound-A':2,'bound-B':1},ap_removed=1,ap_spent=1)
  first={'type':'damage_roll_mod','value':3};second={'type':'damage_roll_mod','value':3};self.a.modifiers=[first,second]
  result=self.e.adopt_bound_ap_modifier(self.a,'bound-A',modifier=first,ending_method=ending,source_ref='reviewed_import/no_new_feature_activation')
  self.assertEqual(result.status,'adopted');return first,second
 def release(self):return self.e.release_bound_ap(self.a,'bound-A',event_id='end-A')
 def test_fixed_full_source_snapshots_and_hashes(self):
  register=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))
  for uid,sha in SCOPES.items():
   row=next(r for r in register['entries'] if r['id']==uid);self.assertEqual(row['scope_sha256'],sha)
   snap=row['source_snapshot'];anchors=snap.get('source_anchors',[snap['source']] if 'source' in snap else [])
   self.assertTrue(anchors)
   for a in anchors:
    path=ROOT/a['file'];text='\n'.join(path.read_text(encoding='utf-8-sig').splitlines()[a.get('start_line',a.get('start'))-1:a.get('end_line',a.get('end'))])
    self.assertEqual(text,a['excerpt']);self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),a['excerpt_sha256']);self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),a['file_sha256'])
 def test_ap_maximum_level_boundaries_and_pokemon_has_no_trainer_pool(self):
  for level,want in [(0,5),(4,5),(5,6),(14,7),(15,8),(100,25)]:self.a.level=level;self.assertEqual(AP.maximum(self.a),want)
  self.assertEqual(AP.maximum(self.p),0)
 def test_ap_spend_rejects_fractional_negative_overdraft_and_bind_disguise(self):
  for amount in (True,-1,0.5,9):
   before=self.state()
   with self.assertRaises(ValueError):AP.spend(self.a,amount)
   self.assertEqual(before,self.state())
  with self.assertRaises(ValueError):AP.spend(self.a,2,{'frequency':{'raw':'Bind 2 AP'}})
  AP.spend(self.a,2);self.assertEqual(AP.available(self.a),6)
 def test_scene_recovers_spent_for_known_omitted_actors_preserves_bound_and_drain(self):
  self.adopted();self.b.spec['ap_spent']=3;self.turn();self.e.end_scene([self.p])
  self.assertEqual(self.a.spec['ap_spent'],0);self.assertEqual(self.b.spec['ap_spent'],0)
  self.assertEqual(self.a.spec['ap_bound'],{'bound-A':2,'bound-B':1});self.assertEqual(self.a.spec['ap_removed'],1);self.assertEqual(len(self.a.modifiers),2)
 def test_source_change_stops_scene_before_encounter_state_changes(self):
  self.adopted();self.turn();before=self.state()
  with self.changed_source(AP.SOURCE),self.assertRaises(ValueError):self.e.end_scene()
  self.assertEqual(before,self.state())
 def test_ap_free_pokemon_scene_and_rest_do_not_require_unused_ap_source(self):
  self.e.everyone=self.e.gm.everyone=[self.p]
  with self.changed_source(AP.SOURCE):
   self.e.end_scene();DT.rest(self.e,self.p,240);self.assertEqual(AP.maximum(self.p),0)
  self.assertEqual(self.e.elapsed_seconds,14400)
 def test_ap_scene_preflight_is_readonly_even_for_unregistered_actors(self):
  self.a.spec['ap_spent']=1;before=self.state();known=list(self.e._time_actors)
  with self.changed_source(AP.SOURCE),self.assertRaises(ValueError):AP.validate_scene(self.e,[self.a])
  self.assertEqual(before,self.state());self.assertEqual(known,self.e._time_actors)
 def test_invalid_ledger_stops_scene_before_any_actor_refresh(self):
  self.a.spec['ap_spent']=2;self.b.spec['ap_removed']=-1;self.turn();before=self.state()
  with self.assertRaises(ValueError):self.e.end_scene()
  self.assertEqual(before,self.state())
 def test_drain_actual_native_cost_persists_scene_day_until_continuous_rest(self):
  AP.spend(self.a,2,{'frequency':{'raw':'Drain 2 AP'}});self.a.spec['ap_spent']=1
  self.e.end_scene();DT.new_day(self.a);self.assertEqual(self.a.spec['ap_removed'],2)
  DT.rest(self.e,self.a,239,rest_id='r');self.assertEqual(self.a.spec['ap_removed'],2)
  DT.rest(self.e,self.a,1,rest_id='r');self.assertEqual(self.a.spec['ap_removed'],0);self.assertEqual(AP.available(self.a),8)
 def test_rest_does_not_free_bound_or_ordinary_spend(self):
  self.adopted();DT.extended_rest(self.e,self.a,4)
  self.assertEqual(self.a.spec['ap_removed'],0);self.assertEqual(self.a.spec['ap_spent'],1);self.assertEqual(sum(self.a.spec['ap_bound'].values()),3);self.assertEqual(len(self.a.modifiers),2)
 def test_changed_ap_source_rejects_rest_before_clock_or_hp(self):
  self.a.spec['ap_removed']=2;self.a.hp=1;before=self.state()
  with self.changed_source(AP.SOURCE),self.assertRaises(ValueError):DT.extended_rest(self.e,self.a,4)
  self.assertEqual(before,self.state())
 def test_fallback_free_release_removes_one_actual_modifier_and_its_ap_once(self):
  first,second=self.adopted();self.turn();before=AP.available(self.a)
  out=self.release();self.assertEqual(out.status,'released');self.assertEqual(AP.available(self.a),before+2);self.assertIs(self.a.modifiers[0],second)
  self.assertEqual(self.a._action_history,['free']);self.assertEqual(self.release().status,'rejected');self.assertEqual(self.a._action_history,['free'])
 def test_fallback_release_offturn_and_specified_end_are_not_free_overrides(self):
  self.adopted();self.turn();self.e.end_of_turn(self.a);self.e.start_of_turn(self.b);before=self.state()
  self.assertEqual(self.release().status,'rejected');self.assertEqual(before,self.state())
  self.setUp();self.adopted('specified');self.turn();before=self.state();self.assertEqual(self.release().status,'rejected');self.assertEqual(before,self.state())
 def test_actual_pinpoint_reserves_per_target_and_releases_on_its_specified_end(self):
  self.turn();self.assertEqual(self.e.manual_feat(self.a,CPF.PINPOINT,self.p),(1,0));self.assertEqual(AP.available(self.a),6)
  self.a.spec['ap_spent']=1;self.a.spec['ap_removed']=1;self.p.on_field=False;self.e.end_encounter([self.a])
  self.assertEqual(self.a.spec['ap_bound'],{});self.assertEqual(AP.available(self.a),6);self.assertEqual(self.a.spec['ap_spent'],1);self.assertEqual(self.a.spec['ap_removed'],1)
 def test_snapshot_restores_actual_bound_instance_and_spent_drained_ledgers(self):
  self.adopted();self.turn();self.e.gm.snapshot('active');self.release();AP.spend(self.a,1)
  self.e.gm.restore('active');row=self.a._ap_bound_effects['bound-A'];self.assertIs(row['owner'],self.a);self.assertIs(row['modifier'],self.a.modifiers[0]);self.assertEqual(AP.available(self.a),3)
  self.assertEqual(self.release().status,'released');self.assertEqual(AP.available(self.a),5)
 def test_crafting_default_and_specific_metadata_are_distinct(self):
  self.assertEqual(META.resolve_crafting_policy({'feature_kind':'crafting'}),{'action':'extended','frequency':{'kind':'at_will','uses':1}})
  policy=META.resolve_crafting_policy({'feature_kind':'crafting','frequency':{'kind':'daily','uses':2,'raw':'하루 X2 - 기본 행동','action':'standard'}})
  self.assertEqual(policy,{'action':'standard','frequency':{'kind':'daily','uses':2}})
  with self.assertRaises(ValueError):META.resolve_crafting_policy({'name':'looks like crafting'})
 def test_crafting_consumes_actual_equipment_materials_time_and_extended_action(self):
  self.a.spec['crafting_scrap']={'몬스터볼':60};self.craft(scrap_value=60)
  self.assertEqual(self.a.spec['money'],360);self.assertEqual(self.a.spec['crafting_scrap']['몬스터볼'],0);self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1);self.assertEqual(self.e.elapsed_seconds,300);self.assertEqual(self.a._action_history,['extended'])
 def test_default_atwill_crafting_repeats_without_invented_daily_or_ap_cost(self):
  self.craft();self.craft();self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],2);self.assertEqual(self.a.spec['money'],200);self.assertEqual(AP.available(self.a),8)
  self.assertEqual(self.a._action_history,['extended','extended'])
 def test_owned_ingredient_crafting_uses_default_extended_and_not_money(self):
  out=self.e.pokemon_activity(self.a,'craft_gem',color='빨강',gem_type='불꽃',minutes=3,reason='GM actual crafting duration')
  self.assertEqual(out['item'],'불꽃주얼');self.assertEqual(self.a.spec['shards']['빨강'],1);self.assertEqual(self.a.spec['money'],400);self.assertEqual(self.e.elapsed_seconds,180);self.assertEqual(self.a._action_history,['extended'])
 def test_missing_feature_tool_material_and_invalid_duration_never_mutate(self):
  for key,value in [('edges',[]),('items',{}),('money',0)]:
   old=self.a.spec[key];self.a.spec[key]=value;before=self.state()
   with self.assertRaises(ValueError):self.craft()
   self.assertEqual(before,self.state());self.a.spec[key]=old
  before=self.state()
  with self.assertRaises(ValueError):self.craft(minutes=0)
  self.assertEqual(before,self.state())
 def test_crafting_source_change_refuses_before_frequency_time_inventory(self):
  for source in (CRAFT.CRAFTING_SOURCE,'edge/몬스터볼'):
   before=self.state()
   with self.changed_source(source),self.assertRaises(ValueError):self.craft()
   self.assertEqual(before,self.state())
 def test_crafting_active_encounter_sleep_and_faint_rejected_before_cost(self):
  self.turn();before=self.state()
  with self.assertRaises(ValueError):self.craft()
  self.assertEqual(before,self.state());self.e.end_encounter()
  for condition in ('잠듦','얼음'):
   self.a.conditions.add(condition);before=self.state()
   with self.assertRaises(ValueError):self.craft()
   self.assertEqual(before,self.state());self.a.conditions.remove(condition)
  self.a.hp=0;before=self.state()
  with self.assertRaises(ValueError):self.craft()
  self.assertEqual(before,self.state())
 def test_crafting_after_encounter_ignores_expired_combat_budget(self):
  self.turn();self.a.budget['standard']=0;self.e.end_encounter();self.craft()
  self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1);self.assertEqual(self.a._action_history,['extended'])
 def test_crafting_other_actor_time_pending_does_not_spend_extended_action(self):
  self.e.observe_breathing(self.b,air_available=False,medium='airless',reason='actual world observation; injury phase not yet selected')
  before=self.state();known=list(self.e._time_actors)
  with self.assertRaisesRegex(ValueError,'first-injury phase'):self.craft()
  self.assertEqual(before,self.state());self.assertEqual(known,self.e._time_actors)
  self.e.observe_breathing(self.b,air_available=True,medium='air',reason='actual breathing restored')
  self.craft();self.assertEqual(self.a._action_history,['extended']);self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1)
 def test_crafting_snapshot_restores_inventory_clock_and_action_history(self):
  self.e.gm.snapshot('before');before=self.state();self.craft();self.e.gm.restore('before')
  self.assertEqual(before,self.state());self.craft();self.assertEqual(self.a.spec['items']['item/몬스터볼-2'],1)

class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 files=sorted(set([p.relative_to(ROOT).as_posix() for p in (ROOT/'engine').glob('*.py')]+[p.relative_to(ROOT).as_posix() for p in (ROOT/'data').glob('*.json')]+['input/ch03-skills-edges-feats.md','input/ch06-gameplay.md','input/ch07-combat.md','input/ch09-equipment.md','tools/test_category3_batch15_combat.py']))
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'completion_scopes':list(SCOPES),'source_scope_sha256':SCOPES,'results':result.rows,'required_files':files,'input_hashes':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
 (ROOT/'output/category3-batch15-combat-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(not result.wasSuccessful())
