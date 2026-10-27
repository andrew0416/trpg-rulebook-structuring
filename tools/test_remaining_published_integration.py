"""Source-restored owners at modern Connection, birth and initiative boundaries."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Combatant
from builder import build_pokemon
import test_book_enduring_soul_csv as ENDURING_FIXTURE
import test_study_books as BOOK_FIXTURE
import test_book_fashionista_csv_full as STALL_FIXTURE
import test_category2_feature_ability_lessons as LESSON_FIXTURE
import advanced_connection as CONNECTION
import endure as ENDURE
import study_books as BOOKS
import growth_milestones as GROWTH
import move_state as MOVES
import initiative
import researcher_fields as RESEARCHER
import feature_ability_lessons as LESSONS
import state_codec as CODEC
import world_entities as WORLD
import gameplay_validation as GAMEPLAY
from ruleset import RuleFilter,RuleSelection


class RemainingPublishedIntegrationTests(unittest.TestCase):
 def fixture(self,cls,attribute,profile):
  # Borrow real producers without inheriting/recollecting another test suite.
  case=cls();setattr(case,attribute,Rules(ROOT,ruleset=profile));case.setUp()
  self.addCleanup(case.doCleanups)
  return case

 def test_books_prerequisite_adapter_fills_only_reviewed_metadata_and_rejects_conflicts(self):
  policy=deepcopy(RESEARCHER._data)
  owned={'reviewed_sources':('core_en','local_csv','may2015'),
         'csv_records':(RESEARCHER.BREADTH,RESEARCHER.BOOKWORM,RESEARCHER.WELL_READ),
         'clauses':('general',),'features':(RESEARCHER.BREADTH,RESEARCHER.BOOKWORM,RESEARCHER.WELL_READ)}
  for field,keys in owned.items():
   for key in keys:policy[field].pop(key)
  retained=deepcopy(policy);RESEARCHER._install_book_prerequisites(policy)
  for field,entries in retained.items():
   if field not in owned:self.assertEqual(policy[field],entries)
   else:
    for key,value in entries.items():self.assertEqual(policy[field][key],value)
  for field,keys in owned.items():
   for key in keys:self.assertEqual(policy[field][key],RESEARCHER._data[field][key])
  conflicting=deepcopy(policy);conflicting['csv_records'][RESEARCHER.BOOKWORM]=323
  with self.assertRaisesRegex(ValueError,'metadata changed'):
   RESEARCHER._install_book_prerequisites(conflicting)
  conflicting=deepcopy(policy)
  conflicting['features'][RESEARCHER.BREADTH]['prerequisites']['skills'][0][1]=3.0
  with self.assertRaisesRegex(ValueError,'metadata changed'):
   RESEARCHER._install_book_prerequisites(conflicting)
  # Exercise the real already-authenticated originals, not a made-up source body.
  RESEARCHER._book_prerequisite_sources(Rules(ROOT,ruleset='core'))

 def test_books_world_validation_is_read_only_without_books_and_after_paid_study_and_codec_restore(self):
  for studied in (False,True):
   with self.subTest(studied=studied):
    h=self.fixture(BOOK_FIXTURE.StudyBooksTests,'rules','core')
    if studied:
     ap=BOOK_FIXTURE.AP.available(h.t);start=h.e.elapsed_seconds
     identity,studies=h.book('study_manual')
     self.assertEqual((BOOK_FIXTURE.AP.available(h.t),h.e.elapsed_seconds),(ap-2,start+3600))
     self.assertEqual([row['rank'] for row in studies],[1,2])
     self.assertEqual(h.t.spec[BOOKS.KEY]['studies'],studies)
    else:self.assertNotIn(BOOKS.KEY,h.t.spec)
    spec=deepcopy(h.t.spec);rng=h.e.rng.getstate();payload=h.e.export_state()
    self.assertEqual(h.t.spec,spec);self.assertEqual(h.e.rng.getstate(),rng)
    loaded=CODEC.load_engine(h.rules,json.loads(json.dumps(payload,ensure_ascii=False)))
    for engine in (h.e,loaded):
     before=engine.export_state();rng=engine.rng.getstate()
     reader=WORLD.actor_index(engine)[h.t.entity_id]
     report=engine.validate_state()
     self.assertTrue(report['valid'],report);self.assertEqual(report['issues'],[])
     self.assertEqual(WORLD.validate_world(engine),report)
     self.assertEqual(engine.export_state(),before);self.assertEqual(engine.rng.getstate(),rng)
     self.assertEqual(reader.spec,spec)
     if studied:
      self.assertEqual(engine._physical_objects[identity][BOOKS.OBJECT]['book'],'study_manual')
      self.assertTrue(BOOKS.active(reader,'study_manual',2))
     else:self.assertNotIn(BOOKS.KEY,reader.spec)

 def test_books_world_issues_reject_tampered_paid_study_and_physical_binding_before_restore_commit(self):
  h=self.fixture(BOOK_FIXTURE.StudyBooksTests,'rules','core')
  identity,studies=h.book('study_manual',rank=1)
  checkpoint=h.e.gm.snapshot('actual-paid-book-world-boundary')
  baseline=h.e.export_state();rng=h.e.rng.getstate()
  cases=(('receipt','Book study receipt changed'),('physical','study text and physical Book differ'))
  for damage,message in cases:
   with self.subTest(damage=damage):
    damaged=CODEC.load_engine(h.rules,deepcopy(baseline))
    reader=WORLD.actor_index(damaged)[h.t.entity_id]
    row=reader.spec[BOOKS.KEY]['studies'][0];obj=damaged._physical_objects[identity]
    if damage=='receipt':row['reason']='tampered actual paid Book receipt'
    else:obj[BOOKS.OBJECT]['book']='joy_cooking'
    # The additive Book callback must not suppress an independent World guard.
    obj['owner_id']='trainer/unresolved-book-owner'
    state=deepcopy((reader.spec,obj));bad_rng=damaged.rng.getstate()
    report=damaged.validate_state();self.assertFalse(report['valid'])
    self.assertIn({'code':'study_books','entity_id':None,'message':message},report['issues'])
    self.assertIn({'code':'dangling_object_owner_id','entity_id':identity,
                   'message':'Object relationship does not resolve.'},report['issues'])
    self.assertEqual((reader.spec,obj),state);self.assertEqual(damaged.rng.getstate(),bad_rng)
    supplied=deepcopy(baseline)
    dictionaries=[node['items'] for node in supplied['nodes'].values() if node['kind']=='dict']
    encoded_object,=[items for items in dictionaries if ['id',identity] in items]
    if damage=='receipt':
     encoded_record,=[items for items in dictionaries if ['source_id',studies[0]['source_id']] in items]
     field,value='reason','tampered actual paid Book receipt'
    else:
     ref=dict(encoded_object)[BOOKS.OBJECT]['$ref']
     encoded_record=supplied['nodes'][ref]['items'];field,value='book','joy_cooking'
    next(pair for pair in encoded_record if pair[0]==field)[1]=value
    next(pair for pair in encoded_object if pair[0]=='owner_id')[1]='trainer/unresolved-book-owner'
    untouched=deepcopy(supplied)
    with self.assertRaisesRegex(CODEC.StateCodecError,'world reference integrity:.*study_books') as error:
     CODEC.load_engine(h.rules,supplied)
    self.assertIn(message,str(error.exception));self.assertIn('dangling_object_owner_id',str(error.exception))
    self.assertEqual(supplied,untouched)
    snap=h.e.gm.snapshots[checkpoint]
    saved_row=snap['combatants'][id(h.t)]['spec'][BOOKS.KEY]['studies'][0]
    saved_obj=snap['engine']['_physical_objects'][identity]
    try:
     if damage=='receipt':saved_row['reason']='tampered actual paid Book receipt'
     else:saved_obj[BOOKS.OBJECT]['book']='joy_cooking'
     saved_obj['owner_id']='trainer/unresolved-book-owner'
     with self.assertRaisesRegex(GAMEPLAY.WorldIntegrityError,'world reference integrity:.*study_books') as error:
      h.e.gm.restore(checkpoint,reason='reject actual Book checkpoint corruption')
     self.assertIn(message,str(error.exception));self.assertIn('dangling_object_owner_id',str(error.exception))
    finally:
     saved_row['reason']=studies[0]['reason'];saved_obj[BOOKS.OBJECT]['book']='study_manual'
     saved_obj['owner_id']=h.t.entity_id
    self.assertIs(WORLD.actor_index(h.e)[h.t.entity_id],h.t)
    self.assertEqual(h.e.export_state(),baseline);self.assertEqual(h.e.rng.getstate(),rng)

 def test_vim_actual_lesson_has_one_modern_connection_protection_before_and_after_restore(self):
  for already_known in (False,True):
   for advanced in (False,True):
    with self.subTest(already_known=already_known,advanced=advanced):
     h=self.fixture(ENDURING_FIXTURE.EnduringSoulCsvTests,'r','all')
     h.vim()
     mid=h.r._selected_rule(ENDURE.SOURCES[0]);ability=h.r._selected_rule(ENDURE.VIGOR[0])
     if already_known:h.e.gm.set_move(h.p,mid,reason='actual previously learned Endure')
     h.teach(advanced_connection=advanced)
     protection=h.p.spec[CONNECTION.PROTECTION][mid]
     self.assertEqual((protection['ability'],protection['source'],protection['acquisitions']),
                      (ability,CONNECTION.KEYWORD,1))
     logs=[row for row in h.p.spec['move_learning_log'] if row.get('move_id')==mid and row.get('source')==ability]
     self.assertEqual(len(logs),1)
     self.assertEqual(h.p.spec['tutor_points'],2 if advanced else 3)
     edges=CONNECTION.records(h.p.spec)
     self.assertEqual(len(edges),1 if advanced else 0)
     if advanced:self.assertEqual(edges[0]['training_source'],CONNECTION.KEYWORD)
     before=deepcopy(h.p.spec[CONNECTION.PROTECTION]);h.restore()
     self.assertEqual(h.p.spec[CONNECTION.PROTECTION],before)
     h.reject(lambda:h.e.gm.set_move(h.p,mid,add=False,reason='attempted loss of permanent Connection'),
              'cannot be forgotten')
     h.valid()

 def test_vim_legacy_five_rows_are_preserved_and_adapter_result_funds_actual_lesson(self):
  h=self.fixture(ENDURING_FIXTURE.EnduringSoulCsvTests,'r','all');h.vim()
  declared=json.loads((ROOT/LESSONS.POLICY).read_text(encoding='utf8'))
  loaded=LESSONS._policy(h.r)
  legacy={uid:deepcopy(loaded[uid]) for uid in LESSONS.LEGACY_SOURCES}
  before=deepcopy(legacy)
  adapted=LESSONS._vim_rules(h.r,legacy,declared['source_files'])
  self.assertEqual(legacy,before);self.assertEqual(set(adapted),set(LESSONS.SOURCES))
  for uid in LESSONS.LEGACY_SOURCES:self.assertIs(adapted[uid],legacy[uid])
  # Same source-validated cache the production loader publishes; all original
  # source reads and real lesson/payment/Connection producers remain active.
  h.r._feature_ability_lessons=adapted
  row=h.teach()
  lesson=h.p.spec['state_grants']['sources'][row['payment']['sources'][0]]['ability_lesson']
  self.assertEqual(lesson['connection_move'],ENDURE.SOURCES[0])
  self.assertEqual(h.p.spec['tutor_points'],3)
  self.assertEqual(h.p.spec[CONNECTION.PROTECTION][ENDURE.SOURCES[0]]['acquisitions'],1)
  h.restore();h.valid()

 def test_vim_declared_conflicts_rule_set_and_live_effect_source_reject_before_payment(self):
  h=self.fixture(ENDURING_FIXTURE.EnduringSoulCsvTests,'r','all');h.vim()
  declared=json.loads((ROOT/LESSONS.POLICY).read_text(encoding='utf8'))
  rows=LESSONS._policy(h.r);pins=declared['source_files']
  self.assertIs(LESSONS._vim_rules(h.r,rows,pins),rows)
  for field,value in (('point_cost',1),('own_pokemon',False),('parent','class/연구원'),
                      ('lines',[824,827]),('effects',[]),('abilities',[])):
   with self.subTest(field=field):
    changed=deepcopy(rows);changed[LESSONS.VIM][field]=value
    with self.assertRaisesRegex(ValueError,'reviewed declaration'):
     LESSONS._vim_rules(h.r,changed,pins)
  unrelated=deepcopy(rows);unrelated['feat/not-a-lesson']={}
  with self.assertRaisesRegex(ValueError,'unsupported Ability lesson policy'):
   LESSONS._vim_rules(h.r,unrelated,pins)
  wrong_pin=dict(pins);wrong_pin['input/ch04-trainer-classes.md']='0'*64
  with self.assertRaisesRegex(ValueError,'source binding'):
   LESSONS._vim_rules(h.r,rows,wrong_pin)
  actual=h.r.feat_effects
  def changed_effects(uid):
   effects,header=actual(uid)
   return ([],header) if uid==LESSONS.VIM else (effects,header)
  vars(h.r).pop('_feature_ability_lessons',None)
  with patch.object(h.r,'feat_effects',side_effect=changed_effects):
   h.reject(lambda:h.teach(),'extracted declaration')
  self.assertEqual(h.p.spec['tutor_points'],5);h.valid()

 def test_other_actual_lesson_does_not_admit_excluded_or_unhandled_vim_selection(self):
  for profile in ({'exclude_units':[LESSONS.VIM]},
                  {'unit_versions':{LESSONS.VIM:'reviewed-version-not-supported-by-reader'}}):
   with self.subTest(profile=profile):
    h=LESSON_FIXTURE.FeatureAbilityLessonTests();h.rules=Rules(ROOT,ruleset='all')
    # Existing public selection API, as used by foundation selection tests:
    # rebuild the catalog against a new RuleFilter rather than mutating a
    # frozen selection or adding an invented profile/permission interface.
    catalog=list(h.rules.selection.units.values())
    h.rules.ruleset=RuleFilter(profile)
    h.rules.selection=RuleSelection(h.rules.ruleset,catalog)
    with self.assertRaises(ValueError):h.rules.feat_effects(LESSONS.VIM)
    h.fixture('feat/댄스-연습')
    result=h.teach('ability/마이페이스')
    self.assertEqual((result['source'],result['point_cost'],h.pupil.spec['tutor_points']),
                     ('feat/댄스-연습',2,3))
    self.assertEqual(h.engine.elapsed_seconds,45)
    with self.assertRaises(ValueError):h.rules.feat_effects(LESSONS.VIM)

 def test_daycare_policyless_native_birth_offers_ten_but_never_grants_inheritance_at_birth(self):
  h=self.fixture(BOOK_FIXTURE.StudyBooksTests,'rules','core')
  h.book('daycare');h.t.spec['edges'].append('edge/브리더')
  mother=h.pokemon('actual mother');mother.spec['gender']='female'
  father=Combatant(h.rules,build_pokemon(h.rules,'치코리타',10,name='actual father',moves=[],abilities=[],
      extra={'trainer_id':h.t.entity_id,'gender':'male'}))
  h.e.gm.add_combatant(father,pos=(2,0),side='party',reason='actual compatible father')
  inherited='move/뿌리박기'
  for parent in (mother,father):h.e.gm.set_move(parent,inherited,reason='actual known parental inheritance Move')
  value=json.loads((ROOT/'data/examples/egg-creation.json').read_text(encoding='utf8'))[0]
  value['species']['parents']=[0]
  value['inheritance'].update(kind='declared',moves=[inherited])
  self.assertNotIn('tutoring_policy',value['inheritance'])
  value['hatch']['level']=10
  egg=h.e.create_declared_egg(h.t,[mother,father],value,request_id='boundary/daycare-policyless',
      compatible=True,species='치코리타',inheritance_moves=[inherited],reason='actual paid Daycare egg')
  choices={'gender':'female','nature':'노력','abilities':[],'moves':[],
           'special_appearance':False,'inheritance_moves':[inherited]}
  child=h.e.hatch_declared_egg(h.t,egg['entity_id'],name='native policyless child',ready=True,
      reason='actual observed hatch',choices=choices)['pokemon']
  self.assertNotIn('inheritance_tutoring_policy',child.spec)
  self.assertEqual(BOOKS.first_inheritance_level(child,20),10)
  self.assertIn('inheritance:10',child.spec[GROWTH.KEY]);self.assertNotIn('inheritance:20',child.spec[GROWTH.KEY])
  self.assertNotIn(inherited,MOVES.known(h.rules,child.spec))
  h.e.choose_growth_inheritance(child,10,inherited,reason='actual attained inheritance slot choice')
  self.assertIn(inherited,MOVES.known(h.rules,child.spec))
  child,=h.restore(child)
  self.assertEqual(child.spec[GROWTH.KEY]['inheritance:10']['selection']['choice'],inherited)
  self.assertEqual(BOOKS.first_inheritance_level(child,20),10)
  self.assertTrue(h.e.validate_state()['valid'])

 def test_stall_native_queue_reorders_without_replacing_resolved_numeric_initiative(self):
  h=self.fixture(STALL_FIXTURE.FashionistaCSVFullTests,'rules','core')
  actors=[h.p,h.q,h.t];plain={}
  self.assertEqual(initiative.order(h.e,actors,resolved_values=plain),[h.p,h.t,h.q])
  h.hold(h.p,'boundary/full-incense','item/만복향로')
  values={}
  self.assertEqual(initiative.order(h.e,actors,resolved_values=values),[h.t,h.q,h.p])
  self.assertEqual(values,plain)
  h.restore();restored={}
  self.assertEqual(initiative.order(h.e,[h.p,h.q,h.t],resolved_values=restored),[h.t,h.q,h.p])
  self.assertEqual(restored,plain);h.valid()


if __name__=='__main__':unittest.main()
