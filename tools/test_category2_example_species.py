"""Source-derived examples share creation, learning, growth and persistence."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer,allocation_base
import example_species as X,move_state as M,pokemon_teaching as T,downtime as D,state_grants as G
from state_codec import StateCodecError

AUDINO='pokemon/example/muscle-audino'
MANECTRIC='pokemon/example/raikou-bred-manectric'
CATERPIE='pokemon/example/giant-caterpie'

class ExampleSpeciesTests(unittest.TestCase):
 def test_excluded_optional_machine_does_not_break_profile_initialization(self):
  from ruleset import ExcludedRuleSelection
  rules=Rules(ROOT,ruleset='no-ohko')
  self.assertIn(AUDINO,rules.species)
  with self.assertRaises(ExcludedRuleSelection):rules.move_id('move/절대영도')
  self.assertTrue(rules.learnsets[rules.species[AUDINO]['name']]['tm'])

 def test_unresolved_machine_is_not_treated_as_an_excluded_alternative(self):
  from ruleset import UnresolvedRuleSelection
  machines=json.loads((ROOT/'data/pokemon-machines.json').read_text(encoding='utf-8'))['machines']
  name=next(row['move_name'] for row in machines.values() if row['kind']=='TM')
  original=Rules.move_id
  def unresolved(rules,identity):
   if identity==name:raise UnresolvedRuleSelection(identity,['unreviewed-machine-identity'])
   return original(rules,identity)
  with patch.object(Rules,'move_id',unresolved):
   with self.assertRaisesRegex(UnresolvedRuleSelection,'unreviewed-machine-identity'):
    Rules(ROOT,ruleset='core')

 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):self.e=Engine(self.r,520)
 def pokemon(self,uid,level=10,**kw):
  if uid==MANECTRIC:kw.setdefault('abilities',['축전']);kw.setdefault('moves',['move/물기'])
  p=Combatant(self.r,build_pokemon(self.r,uid,level,**kw));self.e.gm.add_combatant(p);return p
 def test_common_templates_preserve_stock_and_independent_instances(self):
  stock={k:deepcopy(self.r.species[k]) for k in ['pokemon/다부니','pokemon/썬더볼트','pokemon/캐터피','pokemon/라이코']}
  a=self.pokemon(AUDINO);other=self.pokemon(AUDINO);m=self.pokemon(MANECTRIC);c=self.pokemon(CATERPIE)
  self.assertEqual(self.r.species[AUDINO]['base_stats'],{'hp':10,'atk':12,'def':6,'spa':6,'spd':6,'spe':5})
  self.assertEqual(a.types,['격투']);self.assertEqual(a.spec['movement']['power'],5)
  self.assertEqual(self.e.type_multiplier('비행',a)[0],1.5)
  self.assertEqual(m.spec['movement'],self.r.species['pokemon/썬더볼트']['movement'])
  self.assertEqual(m.spec['types'],['전기']);self.assertEqual(m.abilities,['축전'])
  default=Combatant(self.r,build_pokemon(self.r,MANECTRIC,10));self.e.gm.add_combatant(default)
  self.assertEqual(default.abilities,[])
  offered=default.spec['growth_milestone_choices']['ability:creation']
  self.assertIsNone(offered['selection'])
  self.assertEqual(offered['offered']['stage'],{'kind':'creation','level':10,'species':MANECTRIC})
  candidates=offered['offered']['options']
  self.assertTrue(candidates)
  self.assertTrue(set(candidates)<=set(self.r.learnsets['라이코부모썬더볼트']['abilities']['기본 특성']))
  for name in candidates:self.assertTrue(self.r.selection.resolve_name(name,('ability/',)))
  for p in [a,m,c]:self.assertEqual(p.spec['example_definition']['rule_id'],X.SOURCE)
  G.type_operation(a,'add',['고스트'],'test/independent')
  self.assertEqual(other.types,['격투'])
  self.assertEqual(stock,{k:self.r.species[k] for k in stock})
 def test_all_fighting_tms_use_existing_machine_consumer_without_natural_expansion(self):
  a=self.pokemon(AUDINO,moves=['move/막치기'],extra={'tutor_points':8})
  standard=build_pokemon(self.r,'다부니',10,moves=['move/막치기'])
  machines=json.loads((ROOT/'data/pokemon-machines.json').read_text(encoding='utf-8'))['machines']
  new=[]
  for code,row in machines.items():
   mid=self.r.move_id(row['move_name'])
   if row['kind']=='TM' and mid and self.r.move(mid)['type']=='격투':
    self.assertEqual(T._machine_move(self.r,a.spec,code,row),mid)
    try:T._machine_move(self.r,standard,code,row)
    except ValueError:new.append((code,row,mid))
  self.assertTrue(new)
  self.assertEqual(set(M.current_natural_evidence(self.r,a.spec)),set(M.current_natural_evidence(self.r,standard)))
  code,row,mid=new[0]
  owner=Combatant(self.r,build_trainer(self.r,'machine owner',10,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),extra={'items':{code:1}}))
  self.e.gm.add_combatant(owner);a.spec['trainer_id']=owner.entity_id;T.register_machine(self.e,owner,instance_id='fighting-tm',code=code)
  before=a.spec['tutor_points'];T.teach_machine(self.e,owner,target=a,instance_id='fighting-tm')
  self.assertIn(mid,a.moves);self.assertEqual(a.spec['tutor_points'],before-1)
  self.assertEqual(self.e.elapsed_seconds,3600)
  self.assertEqual(owner.spec['teaching_machines']['fighting-tm']['status'],'consumed')
 def test_raikou_union_covers_both_natural_lists_and_ability_pools_only(self):
  sp=self.r.species[MANECTRIC];ls=self.r.learnsets[sp['name']]
  natural=set()
  pools={}
  for sid in ['pokemon/썬더볼트','pokemon/라이코']:
   natural.update(M.current_natural_evidence(self.r,{'species':sid,'level':100}))
   for slot,names in self.r.learnsets[self.r.species[sid]['name']]['abilities'].items():pools.setdefault(slot,set()).update(names)
  self.assertEqual(set(M.current_natural_evidence(self.r,{'species':MANECTRIC,'level':100})),natural)
  self.assertEqual({slot:set(names) for slot,names in ls['abilities'].items()},pools)
  self.assertEqual(ls['tm'],self.r.learnsets['썬더볼트']['tm'])
  self.assertIn('move/물기',natural)
  self.assertIn('pokemon/라이코',self.r.example_species[MANECTRIC]['natural_and_ability_sources'])
  self.assertNotIn('pokemon/라이츄',self.r.example_species[MANECTRIC]['natural_and_ability_sources'])
 def test_raikou_natural_move_is_acquired_by_actual_level_up(self):
  p=self.pokemon(MANECTRIC,7)
  self.assertNotIn('move/전기쇼크',p.moves)
  D.gain_exp_combatant(self.e,p,'to next level')
  self.assertEqual(p.level,8);self.assertIn('move/전기쇼크',p.moves)
  self.assertEqual(M.describe(self.r,p.spec)['classifications']['move/전기쇼크'],'natural')
  self.assertEqual(p.spec[M.HISTORY]['move/전기쇼크'][-1]['species_id'],MANECTRIC)
 def test_giant_size_six_birth_moves_and_native_evolution_prohibition(self):
  p=self.pokemon(CATERPIE,30)
  self.assertEqual(self.r.species[CATERPIE]['base_stats'],{'hp':11,'atk':9,'def':10,'spa':8,'spd':8,'spe':11})
  self.assertEqual(p.spec['size'],self.r.species['pokemon/뿔카노']['size'])
  self.assertEqual(p.spec['weight_class'],self.r.species['pokemon/캐터피']['weight_class'])
  self.assertEqual({k:p.spec['movement'][k] for k in ['land','power','high_jump','long_jump']},{'land':9,'power':4,'high_jump':3,'long_jump':3})
  expected={'move/몸통박치기','move/실뿜기','move/벌레먹기','move/난동부리기','move/누르기','move/메가혼'}
  self.assertEqual(set(p.moves)-{'struggle'},expected)
  self.assertTrue(expected<=M.natural_moves(self.r,p.spec))
  self.assertEqual(D.evolution_options(self.r,p.spec),[])
  before=deepcopy(p.spec);self.assertFalse(D.evolve_combatant(self.e,p,'단데기')['evolved']);self.assertEqual(p.spec,before)
  self.assertEqual(p.spec['evolutions_remaining'],0)
  with self.assertRaisesRegex(ValueError,'complete initial'):build_pokemon(self.r,CATERPIE,1,moves=['몸통박치기'])
  self.assertEqual(set(build_pokemon(self.r,CATERPIE,1,moves=[self.r.move(x)['name'] for x in expected])['moves'])-{'struggle'},expected)
 def test_all_templates_reuse_level_growth_with_derived_base_and_preserve_moves(self):
  for uid in [AUDINO,MANECTRIC,CATERPIE]:
   p=self.pokemon(uid);before=deepcopy(p.spec)
   D.gain_exp_combatant(self.e,p,'to next level')
   self.assertEqual(p.level,11)
   self.assertEqual(sum(p.spec['stats'].values()),sum(before['stats'].values())+1)
   self.assertEqual(allocation_base(self.r,p.spec),self.r.species[uid]['base_stats'])
   self.assertTrue(set(before['moves'])<=set(p.moves))
   self.assertEqual(p.spec['example_definition'],before['example_definition'])
 def test_snapshot_and_fresh_rules_durable_restore_keep_all_three_then_grow(self):
  actors=[self.pokemon(x) for x in [AUDINO,MANECTRIC,CATERPIE]]
  self.e.gm.snapshot('examples')
  G.type_operation(actors[0],'add',['고스트'],'test/temporary')
  self.e.gm.restore('examples');self.assertEqual(actors[0].types,['격투'])
  saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
  fresh=Rules(ROOT,ruleset='core');n=Engine.import_state(fresh,saved)
  self.assertEqual({p.entity_id for p in n.everyone},{p.entity_id for p in actors})
  for p in n.everyone:
   source=next(x for x in actors if x.entity_id==p.entity_id)
   self.assertEqual(p.spec,source.spec)
   D.gain_exp_combatant(n,p,'to next level');self.assertEqual(p.level,11)
  giant=next(p for p in n.everyone if p.spec['species']==CATERPIE)
  self.assertFalse(D.evolve_combatant(n,giant,'단데기')['evolved'])
 def test_provenance_and_disabled_source_cannot_silently_create_or_save_examples(self):
  p=self.pokemon(AUDINO);p.spec['example_definition']['definition_id']=CATERPIE
  with self.assertRaises(StateCodecError):self.e.export_state()
  with self.assertRaises(ValueError):self.e.gm.snapshot('bad-provenance')
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda key:X.SOURCE+'/disabled' if key==X.SOURCE else original(key)):
   with self.assertRaises(ValueError):build_pokemon(self.r,AUDINO,10)

 def test_fresh_policy_fingerprint_still_rejects_actual_policy_mutation(self):
  p=self.pokemon(CATERPIE);saved=self.e.export_state()
  fresh=Rules(ROOT,ruleset='core')
  import lifetime_consumables as LIFETIME
  LIFETIME.definitions(fresh)['rare_candy']['maximum']+=1
  with self.assertRaises(StateCodecError):Engine.import_state(fresh,saved)

 def test_cache_load_order_and_partial_cultivation_do_not_change_fingerprint(self):
  from state_codec import rules_fingerprint
  import move_capabilities as CAP,coat_effects as COAT,roll_effects as ROLL,cultivation_state as CULT
  cold=Rules(ROOT,ruleset='core');before=rules_fingerprint(cold)
  self.assertNotIn('_cultivation_state_policies',vars(cold))
  CAP.policy(cold);COAT.policy(cold);ROLL.policy(cold);CULT.policy(cold,'cultivation')
  self.assertEqual(rules_fingerprint(cold),before)
  CULT.policy(cold,'planter');self.assertEqual(rules_fingerprint(cold),before)
  CAP.policy(cold)['scope_note']='actual changed policy'
  self.assertNotEqual(rules_fingerprint(cold),before)

if __name__=='__main__':unittest.main()
