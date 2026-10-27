"""Independent CSV49 and preserved Book Pokemaniac on actual native turns.

Builders and GM registration establish the observed sheets, not certification
of general character creation. Feature ownership is acquired, except the one
explicit Book initial-declaration compatibility case. No budget is injected.
"""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import csv
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon,species_lookup
from grid import Grid
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import common_checks as C
import pokemon_activities as P
import pokemon_entities as ENTITIES
import trainer_feature_acquisition as T
import hobbyist as H
import state_codec as CODEC
import world_entities as W
import skill_feature_actions as SF

POKEMON_ABILITY='단순'  # Builder/registration accepts a display name, resolved by its existing owner.
POKEMON_ABILITY_SOURCE='ability/단순'


class PokemaniacSourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

 def setUp(self):self.world()

 def trainer(self,name,*,rank=4,level=20,initial=False,pos=(1,1)):
  extra={'exp_bank':100}
  if initial:extra['feats']=[P.MANIAC]
  actor=Combatant(self.rules,build_trainer(self.rules,name,level,
   dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),moves=[],abilities=[],
   skills=dict.fromkeys(self.rules.skill_policy['skills'],rank),pos=pos,extra=extra))
  self.e.gm.add_combatant(actor,reason='actual Pokemaniac observer sheet')
  prepare_body(self.e,actor,size='중형',offsets=[(0,0)],reason='observed one-cell trainer body')
  return actor

 def world(self,*,rank=4,target_level=23,initial=False,nature='차분'):
  self.e=Engine(self.rules,seed=490897)
  self.e.grid=Grid(8,8)
  self.a=self.trainer('Pokemaniac observer',rank=rank,initial=initial)
  self.p=Combatant(self.rules,build_pokemon(self.rules,'잉어킹',target_level,
   nature=nature,moves=[],abilities=[POKEMON_ABILITY],wild=True,pos=(3,1)))
  self.e.gm.add_combatant(self.p,reason='actual registered observed Pokemon')
  prepare_body(self.e,self.p,size=self.p.spec['size'],offsets=[(0,0)],reason='observed one-cell Pokemon body')

 def acquire(self,edition='local_csv',*,selection=None,request='actual/pokemaniac'):
  return T.acquire_static(self.e,self.a,P.MANIAC,acquisition_request_id=request,
   selection={'edition':edition} if selection is None else selection)

 def begin(self):
  if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
  if self.e.round_start_seconds is not None:self.e.end_round()
  self.e.start_round(self.e.everyone)
  self.e.start_of_turn(self.a,initiative_count=20)
  self.assertTrue(self.e.encounter_active)
  self.assertIs(self.e._active_turn_actor,self.a)
  self.assertEqual(self.a.budget['standard'],1)

 def observe(self,**options):
  values={'special':False,'original_species':self.p.spec['species'],'changes':[],
   'reason':'GM explicitly observes this individual and selected original species'}
  values.update(options)
  return self.e.pokemon_activity(self.a,'observe_pokemon_origin',target=self.p,**values)

 def use(self,**options):
  return self.e.pokemon_activity(self.a,'pokemaniac',target=self.p,**options)

 def pending(self,operation,*,no_standard_diagnostic=False):
  before=self.e.export_state()
  result=operation()
  self.assertIsInstance(result,C.PendingDecision)
  after=self.e.export_state()
  if no_standard_diagnostic:
   # Native TURN.spend deliberately logs a refused payment. Compare the whole
   # codec graph after allowing only that exact diagnostic, never gameplay.
   def log_items(state):
    engine=state['nodes'][state['root']['$ref']]
    attrs=dict(state['nodes'][engine['attrs']['$ref']]['items'])
    return state['nodes'][attrs['log_lines']['$ref']]['items']
   old,new=log_items(before),log_items(after)
   self.assertEqual(new[:-1],old)
   self.assertEqual(new[-1],f'    {self.a.name}: 기본 행동이 남지 않음 → 포켓몬 전문활동 불가  => [combat/action-economy]')
   new[:]=old  # Detached exported data only; retain the actual engine log.
  self.assertEqual(after,before)
  return result

 def reject(self,operation,reason):
  return assert_rejected_unchanged(self.e,operation,reason_pattern=reason)

 def ordinary_info(self):
  return {'level':self.p.level,'types':list(self.p.types),'nature':self.p.spec['nature'],
   'abilities':list(self.p.abilities)}

 def valid(self):
  result=self.e.validate_state()
  self.assertTrue(result['valid'],result['issues'])

 def restore(self):
  ids=(self.a.entity_id,self.p.entity_id)
  self.e=CODEC.load_engine(self.rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
  self.a,self.p=[W.actor_index(self.e)[uid] for uid in ids]

 def test_exact_sources_and_acquired_csv_source_receipt(self):
  with (ROOT/'input/db/feats.csv').open(encoding='utf-8-sig',newline='') as file:row=list(csv.reader(file))[48]
  self.assertEqual(row[0],'포켓몬매니아')
  self.assertEqual(self.rules.selection.resolve_name(POKEMON_ABILITY,('ability/',)),POKEMON_ABILITY_SOURCE)
  self.assertEqual(self.rules._selected_rule(POKEMON_ABILITY_SOURCE),POKEMON_ABILITY_SOURCE)
  self.assertEqual(self.p.spec['state_grants']['ability_receipts'][POKEMON_ABILITY],'ability:'+POKEMON_ABILITY)
  self.assertIn('단순',self.rules.learnsets['잉어킹']['abilities']['기본 특성'])
  self.assertIn('(대상의 레벨 - 사용자의 레벨)÷5(올림) +10',row[4])
  self.assertIn('특별한 포켓몬 여부, 원종 포켓몬과 변경된 점',row[4])
  record=self.acquire()
  self.assertEqual(record['snapshot']['selection'],{'edition':'local_csv'})
  self.assertEqual(record['snapshot']['source']['clause_id'],P.MANIAC_CSV)
  self.assertEqual(T.STATIC_FEATURES[P.MANIAC]['source_choices'],['core','local_csv'])
  self.assertEqual(self.acquire()['integrity'],record['integrity'])
  self.reject(lambda:self.acquire('core'),'replay')
  self.valid()

 def test_both_sources_require_printed_adept_and_invalid_selection_is_atomic(self):
  for edition in ('core','local_csv'):
   with self.subTest(edition=edition):
    self.world(rank=3)
    self.reject(lambda:self.acquire(edition),'skill prerequisites')
  self.world()
  for selection in ({'edition':'other'},{'edition':'local_csv','special':True},{},'local_csv'):
   with self.subTest(selection=selection):
    self.reject(lambda:self.acquire(selection=selection),'edition selection')

 def test_selected_csv_exclusion_does_not_change_book_source(self):
  before=self.e.export_state()
  self.rules.ruleset.exclude_units.add(P.MANIAC_CSV)
  try:
   with self.assertRaisesRegex(ValueError,'selection_profile_changed_rebuild_required'):self.acquire()
   with self.assertRaisesRegex(CODEC.StateCodecError,'selection_profile_changed_rebuild_required'):self.e.export_state()
  finally:self.rules.ruleset.exclude_units.discard(P.MANIAC_CSV)
  self.assertEqual(self.e.export_state(),before)
  # Rebuild admission before constructing the native world for this profile.
  self.rules=Rules(ROOT,ruleset='core')
  self.rules.ruleset.exclude_units.add(P.MANIAC_CSV)
  self.rules._apply_ruleset()
  self.world()
  self.reject(self.acquire,'Excluded|excluded')
  record=self.acquire('core')
  self.assertEqual(record['snapshot']['source']['clause_id'],P.MANIAC_BOOK)
  self.begin()
  self.assertEqual(self.use(fixed=[2,2,3,3])['check'].dc,10)

 def test_acquired_book_keeps_dc10_four_fields_without_origin_observation(self):
  self.acquire('core');self.begin()
  result=self.use(fixed=[2,2,3,3])
  self.assertTrue(result['check'].passed)
  self.assertEqual(result['check'].dc,10)
  self.assertEqual(result['information'],self.ordinary_info())
  self.assertEqual(self.a.budget['standard'],0)
  self.assertTrue(self.a.took_standard)
  self.valid()

 def test_initial_declared_book_keeps_legacy_behavior_without_csv_disclosure(self):
  self.world(initial=True);self.observe(special=True,changes=['GM observed unusual coloration'])
  self.assertEqual(T.static_acquisitions(self.a,P.MANIAC,active=True),[])
  self.begin();result=self.use(fixed=[2,2,3,3])
  self.assertEqual(result['check'].dc,10)
  self.assertEqual(result['information'],self.ordinary_info())
  self.assertEqual(set(result['information']),{'level','types','nature','abilities'})

 def test_default_native_acquisition_is_book_and_legacy_snapshot_remains_qualified(self):
  record=T.acquire_static(self.e,self.a,P.MANIAC,acquisition_request_id='actual/default-book')
  self.assertIsNone(record['snapshot']['selection'])
  self.assertEqual(record['snapshot']['source']['edition'],'core')
  legacy={key:deepcopy(record['snapshot'][key]) for key in ('skills','parents')}
  self.assertEqual(H.general_qualification(self.a,P.MANIAC,legacy,None)['status'],'qualified')
  self.begin();self.assertEqual(self.use(fixed=[2,2,3,3])['check'].dc,10)

 def test_csv_dc_uses_explicit_signed_ceiling_not_floor_or_clamp(self):
  for level,dc in ((14,9),(15,9),(16,10),(20,10),(21,11),(25,11),(26,12)):
   with self.subTest(level=level):
    self.world(target_level=level);self.acquire();self.observe();self.begin()
    result=self.use(fixed=[6,6,6,6])
    self.assertEqual(result['check'].dc,dc)
    self.assertEqual(result['information'],dict(self.ordinary_info(),special=False,original_species_changes=[]))
    self.assertEqual(self.a.budget['standard'],0)

 def test_csv_success_discloses_only_explicit_special_and_original_changes(self):
  self.acquire()
  row=self.observe(special=True,original_species='잉어킹',changes=['GM observed distinctive scales','GM observed changed habitat'])
  self.assertEqual(row['original_species'],species_lookup(self.rules,'잉어킹')['id'])
  self.assertEqual(row['original_reference'],species_lookup(self.rules,'잉어킹'))
  self.begin();result=self.use(fixed=[3,3,3,3])
  self.assertTrue(result['check'].passed)
  self.assertEqual(result['check'].dc,11)
  self.assertEqual(result['information'],dict(self.ordinary_info(),special=True,original_species_changes=row['changes']))
  self.assertNotIn('original_reference',result['information'])
  self.assertEqual(self.a.budget['standard'],0)
  self.valid()

 def test_no_species_marker_or_ordinary_sheet_supplies_missing_gm_origin(self):
  self.acquire();self.begin()
  self.pending(lambda:self.use(fixed=[6,6,6,6]))
  self.assertNotIn('pokemon_origin_observation',self.p.spec)
  self.assertNotIn('origin_observation',ENTITIES.actor_projection(self.p,viewer='player'))

 def test_missing_nature_unknown_special_or_missing_changes_cannot_spend_or_roll(self):
  self.world(nature=None);self.acquire();self.observe();self.begin()
  self.pending(lambda:self.use(fixed=[6,6,6,6]))
  self.world();self.acquire()
  for options,reason in (({'special':None},'special'),({'changes':None},'changes'),({'changes':'unobserved'},'changes')):
   with self.subTest(options=options):self.reject(lambda:self.observe(**options),reason)
  before=self.e.export_state()
  with self.assertRaisesRegex(KeyError,'종 없음'):self.observe(original_species='not-an-actual-species')
  self.assertEqual(self.e.export_state(),before)
  self.begin();self.pending(lambda:self.use(fixed=[6,6,6,6]))

 def test_csv_failed_check_discloses_nothing_and_spends_real_standard(self):
  self.acquire();self.observe(special=True,changes=['GM secret observed difference']);self.begin()
  rng=self.e.rng.getstate();result=self.use(fixed=[1,1,1,1])
  self.assertFalse(result['check'].passed);self.assertIsNone(result['information'])
  self.assertEqual(result['check'].dc,11)
  self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(self.e.rng.getstate(),rng)
  self.pending(self.use,no_standard_diagnostic=True)

 def test_unacquired_wrong_target_unregistered_and_invalid_dice_are_atomic(self):
  self.begin();self.reject(lambda:self.use(fixed=[6]*4),'acquired feature')
  self.acquire();self.observe()
  self.reject(lambda:self.e.pokemon_activity(self.a,'pokemaniac',target=self.a,fixed=[6]*4),'Pokemon target')
  foreign=Combatant(self.rules,build_pokemon(self.rules,'잉어킹',23,nature='차분',moves=[],abilities=[POKEMON_ABILITY]))
  self.reject(lambda:self.e.pokemon_activity(self.a,'pokemaniac',target=foreign,fixed=[6]*4),'actual registered')
  self.reject(lambda:self.use(fixed=[7]*4),'d6')
  self.assertEqual(self.a.budget['standard'],1)

 def test_changed_individual_facts_need_explicit_renewed_observation(self):
  self.acquire();first=self.observe();self.begin()
  self.e.gm.set_types(self.p,['물','노말'],reason='actual GM observed changed individual typing')
  self.pending(lambda:self.use(fixed=[6]*4))
  renewed=self.observe(special=True,changes=['GM explicitly observed additional Normal type'])
  self.assertEqual(renewed['revision'],first['revision']+1)
  self.assertTrue(self.use(fixed=[6]*4)['information']['special'])

 def test_changed_selected_original_template_stays_pending_until_reobserved(self):
  self.acquire();row=self.observe();self.begin()
  uid=row['original_species'];original=self.rules.species[uid]
  self.rules.species[uid]=dict(deepcopy(original),name='GM explicitly revised selected species definition')
  try:self.pending(lambda:self.use(fixed=[6]*4))
  finally:self.rules.species[uid]=original
  self.assertTrue(self.use(fixed=[6]*4)['check'].passed)

 def test_late_roll_failure_rolls_back_native_action_rng_and_gm_observations(self):
  self.acquire();self.observe();self.begin();before=self.e.export_state()
  native=Engine.skill_roll
  def late(engine,*args,**options):
   native(engine,*args,**options);engine.rng.random();raise RuntimeError('late native Pokemaniac check failure')
  with patch.object(Engine,'skill_roll',late):
   with self.assertRaisesRegex(RuntimeError,'late native'):self.use(fixed=[3]*4)
  self.assertEqual(self.e.export_state(),before)

 def test_actual_skill_feature_basis_keeps_source_and_observed_origin(self):
  self.acquire();self.observe(special=True,changes=['GM observed scales'])
  T.acquire_static(self.e,self.a,SF.MONKEY,acquisition_request_id='actual/native-skill-monkey')
  self.begin()
  result=self.use(fixed=[3]*4,roll_id='actual/pokemaniac-skill',feature=SF.MONKEY,feature_options={'decision':lambda first:False})
  self.assertTrue(result['check'].passed)
  basis=self.e._skill_sequences['pokemon-activity:actual/pokemaniac-skill']['basis']
  self.assertEqual(basis['context'][2]['clause_id'],P.MANIAC_CSV)
  self.assertEqual(basis['context'][3],result['information'])
  self.assertEqual(basis['context'][4],self.p.spec['pokemon_origin_observation'])
  self.begin();self.observe(special=False,changes=[])
  self.reject(lambda:self.use(fixed=[3]*4,roll_id='actual/pokemaniac-skill',feature=SF.MONKEY,feature_options={'decision':lambda first:False}),'finalized|consumed')

 def test_actual_help_observes_csv_dc_and_final_disclosure_after_native_interrupt(self):
  self.acquire();self.observe()
  helper=self.trainer('actual helper',rank=4,pos=(2,1))
  T.acquire_static(self.e,helper,SF.HELP,acquisition_request_id='actual/help-feature')
  self.begin();seen=[]
  def accept(first):seen.append(first.total);return True
  self.e.offer_let_me_help(helper,self.a,request_id='actual/pokemaniac-help',payment='next',decision=accept,reroll_faces=[6]*4)
  result=self.use(fixed=[1]*4,roll_id='actual/pokemaniac-helped')
  self.assertEqual(seen,[4]);self.assertEqual(result['check'].dc,11)
  self.assertTrue(result['check'].passed)
  self.assertFalse(result['information']['special'])
  self.assertEqual(self.a.budget['standard'],0)
  self.assertEqual(helper._action_history.count('full'),1)
  self.valid()

 def test_hobbyist_actual_child_selection_keeps_direct_skill_substitution(self):
  self.world(rank=3)
  H.acquire(self.e,self.a,request_id='actual/hobbyist',selection={'edition':'core','edges':[
   {'id':'edge/숙련-스킬','choice':'일반 지식'},
   {'id':'edge/전문-스킬','choice':'일반 지식'},
   {'id':'edge/숙련-스킬','choice':'통찰'}]})
  H.acquire(self.e,self.a,H.DILETTANTE,rank=1,request_id='actual/dilettante-pokemaniac',selection={
   'edition':'core','edge':{'id':'edge/브리더','options':{},'substitute':'통찰'},
   'feature':{'id':P.MANIAC,'options':{'selection':{'edition':'local_csv'}},'substitute':'통찰'}})
  self.assertTrue(H.skill_waived(self.a,P.MANIAC))
  self.assertEqual(H.direct_skill(self.a,P.MANIAC,'포켓몬학'),'통찰')
  self.observe();self.begin();result=self.use(fixed=[3]*4)
  self.assertEqual(result['check'].dc,11)
  self.assertTrue(result['check'].passed)
  self.assertIn('special',result['information'])
  self.valid()

 def test_json_and_gm_restore_preserve_source_observation_and_spent_native_action(self):
  self.acquire();self.observe(special=True,changes=['GM observed distinctive scales']);self.begin()
  result=self.use(fixed=[3]*4);self.e.gm.snapshot('actual/spent')
  self.e.gm.restore('actual/spent')
  self.a,self.p=[W.actor_index(self.e)[uid] for uid in (self.a.entity_id,self.p.entity_id)]
  self.pending(self.use,no_standard_diagnostic=True);self.restore()
  self.assertEqual(T.static_acquisitions(self.a,P.MANIAC,active=True)[0][1]['snapshot']['source']['clause_id'],P.MANIAC_CSV)
  self.assertTrue(self.p.spec['pokemon_origin_observation']['special'])
  self.assertEqual(self.a.budget['standard'],0);self.pending(self.use,no_standard_diagnostic=True)
  self.begin();self.assertEqual(self.use(fixed=[3]*4)['information'],result['information'])
  self.valid()

 def test_cold_restore_rejects_source_receipt_and_target_identity_tampering(self):
  self.acquire();self.observe();self.begin()
  state=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
  # Native codec dictionaries are graph nodes with key/value item pairs.
  # Follow their existing references, as the native codec tamper tests do.
  def mappings(payload):return [node['items'] for node in payload['nodes'].values() if node['kind']=='dict']
  def referenced(payload,pairs,key):
   reference=next(value for field,value in pairs if field==key)
   return payload['nodes'][reference['$ref']]['items']
  corrupt=deepcopy(state)
  records=[pairs for pairs in mappings(corrupt) if ['feature_id',P.MANIAC] in pairs and 'snapshot' in dict(pairs)]
  self.assertEqual(len(records),1)
  snapshot=referenced(corrupt,records[0],'snapshot')
  selection=referenced(corrupt,snapshot,'selection')
  self.assertEqual(selection,[['edition','local_csv']])
  selection[0][1]='core'
  with self.assertRaisesRegex(ValueError,'integrity|source'):CODEC.load_engine(self.rules,corrupt)
  corrupt=deepcopy(state)
  observations=[pairs for pairs in mappings(corrupt) if ['source','gm/pokemon-origin-observation'] in pairs]
  self.assertEqual(len(observations),1)
  identity=next(pair for pair in observations[0] if pair[0]=='pokemon_id')
  self.assertEqual(identity[1],self.p.entity_id);identity[1]=self.a.entity_id
  with self.assertRaisesRegex(ValueError,'origin observation identity'):CODEC.load_engine(self.rules,corrupt)

 def test_native_withdrawal_removes_csv_authority_and_cannot_fall_back_to_book(self):
  self.acquire();self.observe()
  self.e.retrain_trainer_source(self.a,P.MANIAC,request_id='actual/withdraw-pokemaniac',
   reason='actual source retirement',gm_decision={'allowed':True,'reason':'GM approves actual feat retraining'},
   retained_dependencies={})
  self.assertEqual(T.static_acquisitions(self.a,P.MANIAC,active=True),[])
  self.assertTrue(T.static_acquisitions(self.a,P.MANIAC,active=False))
  self.assertNotIn(P.MANIAC,self.a.spec.get('feats',[]))
  self.begin();self.reject(lambda:self.use(fixed=[6]*4),'acquired feature')
  self.restore();self.reject(lambda:self.use(fixed=[6]*4),'acquired feature')
  self.valid()


if __name__=='__main__':unittest.main(verbosity=2)
