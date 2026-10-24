"""One shared source-owned operation group, exercised through actual producers."""
from pathlib import Path
from copy import deepcopy
import json,random,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
from grid import Grid
import ability_transitions as A,state_grants as G,combat_timing as TIME
from state_codec import StateCodecError
SHIELD='불굴의방패';SWORD='불요의검'
MOVES=['move/위액','move/코어퍼니셔','move/고민씨','move/심플빔','move/역할','move/스킬스왑','move/베껴그리기','move/잠자기']

class AbilityTransitionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,530);self.e.grid=Grid(30,30)
  self.a=self.actor('user',[],(2,2),'party')
  self.t=self.actor('target',[SHIELD,SWORD],(3,2),'opponent',pokemon=True)
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
 def actor(self,name,abilities,pos,side,*,pokemon=False):
  extra={'abilities':abilities,'size':'중형','pos':pos,'side':side}
  spec=build_pokemon(self.r,'이상해씨',10,name=name,moves=['move/몸통박치기'],extra=extra) if pokemon else build_trainer(self.r,name,10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra=dict(extra,moves=MOVES))
  c=Combatant(self.r,spec);self.e.gm.add_combatant(c);return c
 def select(self,source,ability=None,allies=(),target=None):
  return self.e.gm.choose_ability_transition(self.a,target or self.t,source,ability=ability,allies=allies,reason='actual player selection')
 def use(self,source):
  self.e.use_move(self.a,self.t,source)
  self.assertFalse(getattr(self.e,'_effect_dispatch_receipts',{}) and any(x.get('status') in ['awaiting_input','execution_failed','unsupported_execution'] for x in self.e._effect_dispatch_receipts.values()))
 def live(self,c):return [x for x in TIME.records(c) if A.TAG in x]
 def test_selected_suppression_preserves_other_ability_and_baseline_until_encounter_end(self):
  self.select('move/위액',SHIELD);before=deepcopy(self.t.spec['abilities']);self.use('move/위액')
  self.assertNotIn(SHIELD,self.t.abilities);self.assertIn(SWORD,self.t.abilities)
  self.assertEqual(self.t.spec['abilities'],before);self.assertEqual(self.t.stages['def'],0);self.assertEqual(self.t.stages['atk'],1)
  self.assertIn('ability/'+SHIELD,A.known(self.t));self.assertFalse(self.t.abilities_suppressed)
  self.e.end_of_turn(self.a);self.assertNotIn(SHIELD,self.t.abilities)
  self.e.end_encounter(self.e.everyone);self.assertIn(SHIELD,self.t.abilities)
 def test_both_replacement_sources_change_only_selected_identity_and_run_real_passives(self):
  for source,new in [('move/고민씨','불면'),('move/심플빔','단순')]:
   with self.subTest(source=source):
    self.setUp();self.select(source,SHIELD);self.use(source)
    self.assertEqual(set(self.t.abilities),{new,SWORD});self.assertEqual(self.t.stages['def'],0)
    if new=='단순':
     self.e.change_stage(self.t,'atk',1);self.assertEqual(self.t.stages['atk'],3)
     self.e.change_stage(self.t,'def',-1);self.assertEqual(self.t.stages['def'],-2)
    else:
     self.assertFalse(self.e.apply_status(self.t,'잠듦'));self.assertNotIn('잠듦',self.t.conditions)
     self.t.moves.append('move/잠자기');before=deepcopy((self.t.spec,getattr(self.t,"budget",None),self.e.rng.getstate()))
     with self.assertRaisesRegex(ValueError,'Insomnia'):self.e.use_move(self.t,self.t,'move/잠자기')
     self.assertEqual((self.t.spec,getattr(self.t,"budget",None),self.e.rng.getstate()),before)
    self.e.end_encounter(self.e.everyone);self.assertEqual(set(self.t.abilities),{SHIELD,SWORD})
 def test_missing_or_stale_choice_rejects_before_action_frequency_rng_or_effect(self):
  before=deepcopy((self.a.spec,self.a.budget,self.t.spec,self.e.rng.getstate()))
  with self.assertRaises(ValueError):self.e.use_move(self.a,self.t,'move/위액')
  self.assertEqual((self.a.spec,self.a.budget,self.t.spec,self.e.rng.getstate()),before)
  self.select('move/위액',SHIELD);G.replace_baseline(self.e,self.t,'abilities',[SWORD])
  before=deepcopy((self.a.spec,self.a.budget,self.t.spec,self.e.rng.getstate()))
  with self.assertRaises(ValueError):self.e.use_move(self.a,self.t,'move/위액')
  self.assertEqual((self.a.spec,self.a.budget,self.t.spec,self.e.rng.getstate()),before)
 def test_native_core_enforcer_area_selects_one_per_hit_target(self):
  other=self.actor('second target',[SHIELD,SWORD],(4,2),'opponent',pokemon=True)
  self.select('move/코어퍼니셔',SHIELD);self.select('move/코어퍼니셔',SWORD,target=other)
  self.e.use_move_on(self.a,self.t,'move/코어퍼니셔',self.e.everyone)
  self.assertNotIn(SHIELD,self.t.abilities);self.assertIn(SWORD,self.t.abilities)
  self.assertNotIn(SWORD,other.abilities);self.assertIn(SHIELD,other.abilities)
  self.assertEqual(len(self.live(self.t)),1);self.assertEqual(len(self.live(other)),1)
 def test_role_play_uses_random_donor_then_ends_on_recipient_faint_or_recall(self):
  for event in ['faint','recall']:
   with self.subTest(event=event):
    self.setUp();expected=random.Random();expected.setstate(self.e.rng.getstate())
    chosen=A.known(self.t)[expected.randrange(2)];self.use('move/역할')
    self.assertIn(chosen,A.known(self.a));self.assertEqual(self.e.rng.getstate(),expected.getstate())
    record=self.live(self.a)[0];self.assertIs(record['ability_origin'],self.t)
    if event=='faint':self.a.hp=0;self.e.check_fainted(self.a)
    else:self.e.gm.recall(self.a,reason='actual recall')
    self.assertEqual(self.a.abilities,[]);self.assertEqual(self.live(self.a),[])
    self.assertEqual(set(self.t.abilities),{SHIELD,SWORD})
 def test_skill_swap_each_participant_restores_only_its_own_side(self):
  for event in ['faint','recall']:
   with self.subTest(event=event):
    self.setUp();G.replace_baseline(self.e,self.a,'abilities',['인분'])
    self.select('move/스킬스왑','인분');self.use('move/스킬스왑')
    copied=self.a.abilities[0];self.assertIn('인분',self.t.abilities);self.assertNotIn(copied,self.t.abilities)
    if event=='faint':self.a.hp=0;self.e.check_fainted(self.a)
    else:self.e.gm.recall(self.a,reason='actual recall')
    self.assertEqual(self.a.abilities,['인분']);self.assertIn('인분',self.t.abilities);self.assertNotIn(copied,self.t.abilities)
    self.e.end_encounter(self.e.everyone);self.assertEqual(set(self.t.abilities),{SHIELD,SWORD})
 def test_trace_and_exact_alchemy_equivalents_share_copy_lifetime_and_scene_cost(self):
  for ability in ['트레이스','화학의힘','ability/화학의힘-2']:
   with self.subTest(ability=ability):
    self.setUp();G.replace_baseline(self.e,self.a,'abilities',[ability])
    reg=A.registration(self.r,ability);self.select(reg['source_id'],SHIELD)
    self.e.activate_ability(self.a,ability,self.t)
    self.assertIn(SHIELD,self.a.abilities);self.assertEqual(self.a.stages['def'],1)
    self.select(reg['source_id'],SHIELD)
    before=deepcopy((self.a.spec,self.e.rng.getstate()))
    with self.assertRaisesRegex(ValueError,'frequency'):self.e.activate_ability(self.a,ability,self.t)
    self.assertEqual((self.a.spec,self.e.rng.getstate()),before)
    self.e.gm.recall(self.a,reason='Trace does not end on recall');self.assertIn(SHIELD,self.a.abilities)
    self.a.hp=0;self.e.check_fainted(self.a);self.assertNotIn(SHIELD,self.a.abilities)
 def test_copy_keeps_origin_snapshot_and_an_independent_same_ability_source(self):
  G.replace_baseline(self.e,self.a,'abilities',['트레이스'])
  G.grant(self.a,'abilities',SHIELD,'other/shield','test');G.reconcile(self.e,self.a)
  self.select('ability/트레이스',SHIELD);self.e.activate_ability(self.a,'트레이스',self.t)
  G.replace_baseline(self.e,self.t,'abilities',[SWORD]);self.assertIn(SHIELD,self.a.abilities)
  self.e.end_encounter(self.e.everyone);self.assertIn(SHIELD,self.a.abilities);self.assertEqual(self.a.stages['def'],1)
  G.revoke(self.a,'other/shield',engine=self.e);self.assertNotIn(SHIELD,self.a.abilities)
 def test_doodle_copies_to_user_and_explicit_in_range_allies_only(self):
  ally=self.actor('selected ally',[],(2,3),'party');unselected=self.actor('unselected ally',[],(2,4),'party')
  self.select('move/베껴그리기',SHIELD,allies=[ally]);self.use('move/베껴그리기')
  for c in [self.a,ally]:self.assertIn(SHIELD,c.abilities);self.assertEqual(c.stages['def'],1)
  self.assertEqual(unselected.abilities,[])
  self.e.gm.recall(ally,reason='Doodle persists through recall');self.assertIn(SHIELD,ally.abilities)
  self.e.end_encounter(self.e.everyone)
  for c in [self.a,ally]:self.assertEqual(c.abilities,[])
 def test_doodle_stale_out_of_range_ally_is_atomic_before_cost(self):
  ally=self.actor('far ally',[],(20,20),'party')
  self.select('move/베껴그리기',SHIELD,allies=[ally]);before=deepcopy((self.a.spec,self.a.budget,self.e.rng.getstate()))
  with self.assertRaisesRegex(ValueError,'6 meters'):self.e.use_move(self.a,self.t,'move/베껴그리기')
  self.assertEqual((self.a.spec,self.a.budget,self.e.rng.getstate()),before);self.assertEqual(ally.abilities,[])
 def test_protected_multitype_is_not_copied_replaced_or_suppressed(self):
  for source in ['move/위액','move/고민씨','move/심플빔','move/역할']:
   with self.subTest(source=source):
    self.setUp();G.replace_baseline(self.e,self.t,'abilities',['멀티타입']);self.use(source)
    self.assertEqual(self.t.abilities,['멀티타입']);self.assertEqual(self.a.abilities,[])
    self.assertEqual(self.live(self.a)+self.live(self.t),[])

 def test_native_suppression_moves_keep_multitype_usable_after_hit_and_restore(self):
  for source in ('move/위액','move/코어퍼니셔'):
   with self.subTest(source=source):
    self.setUp();G.replace_baseline(self.e,self.t,'abilities',['멀티타입',SHIELD])
    self.select(source,'멀티타입');self.e.rng.seed(0)
    if source=='move/코어퍼니셔':self.e.use_move_on(self.a,self.t,source,self.e.everyone)
    else:self.use(source)
    self.assertFalse(self.t.abilities_suppressed);self.assertEqual(self.live(self.t),[])
    self.assertTrue(A.active(self.t,'ability/멀티타입'));self.assertIn(SHIELD,self.t.abilities)
    self.assertEqual(self.a.move_uses[source],1)
    self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=19)
    self.e.activate_ability_state(self.t,'ability/멀티타입',choice='불꽃',reason='protected ability after native hit')
    self.assertEqual(self.t.types,['불꽃'])
    self.e.gm.snapshot('protected Multitype');self.e.gm.restore('protected Multitype',reason='restore protected projection')
    restored=Engine.import_state(self.r,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
    target=next(c for c in restored.everyone if c.entity_id==self.t.entity_id)
    restored.activate_ability_state(target,'ability/멀티타입',choice='전기',reason='protected ability after restore')
    self.assertEqual(target.types,['전기']);self.assertTrue(restored.validate_state()['valid'])
 def test_snapshot_and_fresh_engine_restore_preserve_origins_then_end_natively(self):
  self.select('move/심플빔',SHIELD);self.use('move/심플빔');self.e.gm.snapshot('temporary ability')
  self.e.end_encounter(self.e.everyone);self.e.gm.restore('temporary ability')
  saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
  n=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
  target=next(x for x in n.everyone if x.entity_id==self.t.entity_id)
  n.change_stage(target,'spe',1);self.assertEqual(target.stages['spe'],2)
  self.assertIn('단순',target.abilities)
  n.end_encounter(n.everyone);self.assertEqual(set(target.abilities),{SHIELD,SWORD})
 def test_corrupt_lifetime_or_projection_rejects_save_and_snapshot(self):
  self.select('move/위액',SHIELD);self.use('move/위액')
  self.live(self.t)[0]['ends'].append('recall')
  with self.assertRaises(StateCodecError):self.e.export_state()
  with self.assertRaises(ValueError):self.e.gm.snapshot('corrupt lifetime')
 def test_overlapping_suppression_sources_do_not_restore_too_soon(self):
  self.select('move/위액',SHIELD);self.use('move/위액')
  second=self.actor('second caster',[],(2,3),'party');self.e.end_of_turn(self.a);self.e.start_of_turn(second,initiative_count=19)
  self.e.gm.choose_ability_transition(second,self.t,'move/위액',ability=SHIELD,reason='same known ability independent source')
  self.e.use_move(second,self.t,'move/위액')
  self.assertEqual(len(self.live(self.t)),2)
  TIME.expire(self.e,self.t,self.live(self.t)[0]);self.assertNotIn(SHIELD,self.t.abilities)
  TIME.expire(self.e,self.t,self.live(self.t)[0]);self.assertIn(SHIELD,self.t.abilities);self.assertEqual(self.t.stages['def'],1)

 def test_native_miss_spends_activation_without_changing_target_ability(self):
  self.select('move/고민씨',SHIELD);self.e.rng.seed(31)
  self.e.use_move(self.a,self.t,'move/고민씨')
  self.assertEqual(set(self.t.abilities),{SHIELD,SWORD});self.assertEqual(self.live(self.t),[])
  self.assertEqual(self.a.move_uses['move/고민씨'],1)
 def test_consistently_corrupted_operation_still_fails_source_contract_validation(self):
  self.select('move/위액',SHIELD);self.use('move/위액')
  record=self.live(self.t)[0];operation={'kind':'replace','remove':['ability/'+SHIELD],'add':['ability/단순']}
  record[A.TAG]=operation
  self.t.spec[G.KEY]['sources'][record['grant_source']]['ability_operation']=deepcopy(operation)
  G.materialize(self.t,'abilities');G.reconcile(self.e,self.t)
  with self.assertRaises(StateCodecError):self.e.export_state()

 def test_all_nine_sources_restore_into_fresh_rules_and_end_through_native_events(self):
  sources=[*MOVES[:-1],'ability/트레이스','ability/화학의힘']
  for source in sources:
   with self.subTest(source=source):
    self.setUp()
    if source.startswith('ability/'):G.replace_baseline(self.e,self.a,'abilities',[source])
    if source=='move/스킬스왑':G.replace_baseline(self.e,self.a,'abilities',['인분'])
    baseline={c.entity_id:list(c.abilities) for c in self.e.everyone}
    if source=='move/스킬스왑':self.select(source,'인분')
    elif source!='move/역할':self.select(source,SHIELD)
    if source.startswith('ability/'):self.e.activate_ability(self.a,source,self.t)
    elif source=='move/코어퍼니셔':self.e.use_move_on(self.a,self.t,source,self.e.everyone)
    else:self.use(source)
    saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
    n=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
    a=next(c for c in n.everyone if c.entity_id==self.a.entity_id)
    t=next(c for c in n.everyone if c.entity_id==self.t.entity_id)
    self.assertEqual(a.abilities,self.a.abilities);self.assertEqual(t.abilities,self.t.abilities)
    for c in n.everyone:
     for record in self.live(c):self.assertIs(record['ability_producer'],a);self.assertIs(record['ability_origin'],t)
    if source in ('move/역할','move/스킬스왑'):
     n.gm.recall(a,reason='actual recall after fresh restore')
     self.assertEqual(a.abilities,baseline[a.entity_id])
     if source=='move/스킬스왑':self.assertIn('인분',t.abilities)
    elif source.startswith('ability/'):
     a.hp=0;n.check_fainted(a);self.assertEqual(a.abilities,baseline[a.entity_id])
    n.end_encounter(n.everyone)
    for c in n.everyone:self.assertEqual(c.abilities,baseline[c.entity_id]);self.assertEqual(self.live(c),[])

if __name__=='__main__':unittest.main()
