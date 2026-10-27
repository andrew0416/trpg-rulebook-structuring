"""Exact-source move capacity and dynamic grant integration."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import move_state as M
import state_grants as G
import state_codec as C
import effects as FX
import effects_ext as EXT
import pokemon_teaching as T

class CompleteMoveSlotTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='playtest')
 def setUp(self):self.e=Engine(self.r,seed=534)
 def add(self,moves=(),abilities=()):
  c=Combatant(self.r,build_pokemon(self.r,'브케인',5,moves=list(moves),abilities=list(abilities)))
  self.e.gm.add_combatant(c,pos=(1,1),side='party',reason='actual selected current sheet');return c
 def state(self,c):return deepcopy((c.spec,c.moves,c.abilities,self.e.rng.getstate()))
 def test_giver_exact_duplicate_sources_native_registration_and_safe_last_owner_end(self):
  for spelling in ('기부자','ability/기부자','ability/기부자-2'):
   with self.subTest(spelling=spelling):
    c=self.add(abilities=[spelling]);self.assertEqual(M.describe(self.r,c.spec)['taught'],None)
    for name in ('화염방사','열풍','10만볼트','냉동빔'):
     M.observe_learning(self.e,c,name,method='tutor',source='feat/기술-가르침',paid_tp=2,reason='observed paid Tutor result')
    self.assertEqual((M.describe(self.r,c.spec)['taught_count'],M.describe(self.r,c.spec)['total']),(4,6))
    G.grant(c,'abilities',spelling,'independent:ability','fixture');G.reconcile(self.e,c)
    self.e.gm.set_ability(c,spelling,add=False,reason='permanent source ends, independent source remains')
    before=self.state(c)
    with self.assertRaisesRegex(ValueError,'TM/Tutor'):G.revoke(c,'independent:ability',engine=self.e)
    self.assertEqual(self.state(c),before)
    self.e.gm.set_move(c,'move/냉동빔',add=False,reason='explicit chosen forgotten taught move');G.revoke(c,'independent:ability',engine=self.e)
    self.assertEqual(M.describe(self.r,c.spec)['taught'],3)
  e=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  for c in e.everyone:self.assertEqual(M.describe(self.r,c.spec)['taught_count'],3)

 def test_original_csv_giver_fourth_native_tutor_pays_cost_and_keeps_total_six_limit(self):
  import frequency as F
  teacher=Combatant(self.r,build_trainer(self.r,'Actual Tutor',20,
   {'hp':10,'atk':10,'def':10,'spa':10,'spd':10,'spe':10},abilities=[],
   extra={'skills':{'매력':5,'포켓몬학':3},'feats':[T.MENTOR,T.MOVE_TUTOR]}))
  pupil=Combatant(self.r,build_pokemon(self.r,'브케인',50,moves=[],abilities=[],extra={'tutor_points':8}))
  self.e.gm.add_combatant(teacher,pos=(0,0),side='party',reason='actual acquired Tutor')
  self.e.gm.add_combatant(pupil,pos=(0,1),side='party',reason='actual target with eight Tutor Points')
  T.select_mentor_skills(self.e,teacher,['매력','포켓몬학'],reason='actual selected Mentor skills')
  def teach(name):return T.teach_feature(self.e,teacher,target=pupil,move_id=name,
   feature=T.MOVE_TUTOR,seconds=60,reason='actual completed one-minute Tutor activity')
  for name in ('누르기','열풍','진흙뿌리기'):
   self.assertEqual(teach(name)['classification'],'taught')
   F.new_day(teacher);F.new_day(pupil)
  self.assertEqual(pupil.spec['tutor_points'],2);self.assertEqual(self.e.elapsed_seconds,180)
  def before():return deepcopy((teacher.spec,pupil.spec,pupil.moves,self.e.elapsed_seconds,self.e.rng.getstate()))
  state=before()
  with self.assertRaisesRegex(ValueError,'TM/Tutor'):teach('잠꼬대')
  self.assertEqual(before(),state)
  self.e.gm.set_ability(pupil,'ability/기부자',reason='actual original CSV40 acquired ability')
  # Connection keyword (official PTU 1.05 p.310): gaining Giver learns its Present.
  self.assertEqual(M.describe(self.r,pupil.spec)['classifications']['move/프레젠트'],'granted')
  self.assertEqual(teach('잠꼬대')['classification'],'taught')
  self.assertEqual(pupil.spec['tutor_points'],0);self.assertEqual(self.e.elapsed_seconds,240)
  self.assertEqual((M.describe(self.r,pupil.spec)['taught_count'],M.describe(self.r,pupil.spec)['taught']),(4,None))
  receipt=pupil.spec['move_learning']['move/잠꼬대']
  self.assertEqual(receipt['teacher_id'],teacher.entity_id);self.assertEqual(receipt['paid_tp'],2)
  for mid in ('move/몸통박치기',):self.e.gm.set_move(pupil,mid,reason='actual independent natural learned move')
  self.assertEqual(M.describe(self.r,pupil.spec)['slot_count'],6);state=before()
  with self.assertRaisesRegex(ValueError,'exceed sourced capacity'):self.e.gm.set_move(pupil,'move/연막',reason='invalid seventh permanent move')
  self.assertEqual(before(),state)
  self.e.gm.snapshot('csv-giver-six')
  self.e.gm.set_move(pupil,'move/잠꼬대',add=False,reason='actual explicit forgetting')
  self.e.gm.restore('csv-giver-six')
  restored=C.load_engine(self.r,json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False)))
  current=next(c for c in restored.everyone if c.entity_id==pupil.entity_id)
  self.assertEqual((M.describe(self.r,current.spec)['taught_count'],M.describe(self.r,current.spec)['slot_count']),(4,6))
  self.assertEqual(current.spec['move_learning']['move/잠꼬대']['teacher_id'],teacher.entity_id)
  self.assertEqual((current.spec['tutor_points'],restored.elapsed_seconds),(0,240))

 def test_original_csv_giver_profile_exclusion_and_changed_duplicate_refuse_before_state(self):
  from ruleset import ExcludedRuleSelection
  core=Rules(str(ROOT),ruleset='core')
  with self.assertRaises(ExcludedRuleSelection):M.ability_registration(core,'ability/기부자')
  c=self.add(abilities=['ability/기부자']);state=self.state(c)
  original=Path.read_text
  def altered(path,*args,**kwargs):
   body=original(path,*args,**kwargs)
   if path.name=='abilities.json' and path.parent.name=='entities':
    rows=json.loads(body)
    next(x for x in rows if x['id']=='ability/기부자')['effect']='changed source'
    return json.dumps(rows,ensure_ascii=False)
   return body
  with patch.object(Path,'read_text',altered):
   with self.assertRaisesRegex(ValueError,'source equivalence changed'):M.describe(self.r,c.spec)
  self.assertEqual(self.state(c),state)
 def test_atomic_move_batch_checks_last_member_before_record_or_list_mutation(self):
  c=self.add();before=self.state(c)
  with self.assertRaisesRegex(ValueError,'unresolved'):G.grant_moves(c,['move/화염방사','없는기술'],'whole','feature')
  self.assertEqual(self.state(c),before)
  G.grant_moves(c,['화염방사','사이코키네시스'],'whole','feature')
  self.assertEqual(c.moves.count('move/화염방사'),1)
  G.grant_moves(c,['화염방사','사이코키네시스'],'whole','feature')
  self.assertEqual(c.moves.count('move/사이코키네시스'),1)
  G.revoke(c,'whole',engine=self.e);self.assertNotIn('move/화염방사',c.moves)
 def test_actual_ability_permission_activation_cost_end_and_shared_learned_source(self):
  import move_permissions as P
  from encounter import usable_moves
  name='달마모드 [Playtest]';uid='ability/달마모드-playtest-2'
  c=self.add(moves=['move/화염방사']);self.e.gm.set_ability(c,uid,reason='actual exact selected ability')
  self.assertNotIn('move/사이코키네시스',c.moves)
  before_form=c.form;self.e.activate_form_ability(c,uid)
  self.assertEqual(c.form,'달마모드');self.assertIn('move/사이코키네시스',usable_moves(self.e,c))
  self.assertEqual(M.describe(self.r,c.spec)['slot_count'],1)
  self.assertEqual(M.describe(self.r,c.spec)['effective_classifications']['move/사이코키네시스'],'permission')
  before=self.state(c)
  with self.assertRaisesRegex(ValueError,'frequency'):self.e.activate_form_ability(c,uid)
  self.assertEqual(self.state(c),before)
  saved=C.dump_engine(self.e);restored=C.load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)));q=restored.everyone[0]
  self.assertIn('move/사이코키네시스',q.moves);restored.end_scene([q])
  self.assertNotIn('move/사이코키네시스',q.moves);self.assertIn('move/화염방사',q.moves);self.assertEqual(q.form,before_form)
  self.e.gm.set_ability(c,uid,add=False,reason='actual ability source ends during its form')
  self.assertNotIn('move/사이코키네시스',c.moves);self.assertIn('move/화염방사',c.moves);self.assertEqual(c.form,before_form)
 def test_six_learned_slots_allow_permission_but_raw_source_cannot_bypass_activation(self):
  import move_permissions as P
  mids=[self.r.move_id(n) for n in ('몸통박치기','울음소리','덩굴채찍','씨뿌리기','잎날가르기','성장')]
  c=Combatant(self.r,build_pokemon(self.r,'이상해씨',50,moves=mids,abilities=['눈덮인달마']))
  self.e.gm.add_combatant(c,pos=(1,1),side='party',reason='full current list')
  effects=[x for x in self.r.ability_effects['눈덮인달마'] if x.get('type')=='grant_move'];before=self.state(c)
  with self.assertRaisesRegex(ValueError,'activation'):EXT.h_grant_move(self.e,c,c,effects[0],{'source_id':'ability/눈덮인달마'})
  self.assertEqual(self.state(c),before)
  self.e.activate_form_ability(c,'눈덮인달마');self.assertEqual(M.describe(self.r,c.spec)['slot_count'],6)
  self.assertIn('move/냉동펀치',c.moves);self.assertIn('move/불꽃펀치',c.moves)
  G.grant_moves(c,['냉동펀치'],'second-permission','effect',mode='permission')
  self.e.end_scene([c]);self.assertIn('move/냉동펀치',c.moves);self.assertNotIn('move/불꽃펀치',c.moves)
  G.revoke(c,'second-permission',engine=self.e);self.assertNotIn('move/냉동펀치',c.moves)

 def test_both_original_csv_form_sources_use_native_moves_costs_and_scene_restore(self):
  for uid,permanent,borrowed in (
   ('ability/눈덮인달마','move/냉동펀치','move/불꽃펀치'),
   ('ability/달마모드-playtest','move/사이코키네시스','move/화염방사')):
   with self.subTest(source=uid):
    self.e=Engine(self.r,seed=534)
    c=self.add(moves=[permanent],abilities=[uid]);original_form=c.form
    target=Combatant(self.r,build_pokemon(self.r,'잠만보',50,moves=[],abilities=[]))
    self.e.gm.add_combatant(target,pos=(1,2),side='enemy',reason='actual native move target')
    self.e.begin_encounter([c,target]);self.e.start_round([c,target]);self.e.start_of_turn(c)
    swift=c.budget['swift'];standard=c.budget['standard']
    result=self.e.activate_form_ability(c,uid)
    self.assertEqual(result['source'],uid);self.assertEqual(c.budget['swift'],swift-1)
    self.assertEqual(c.budget['standard'],standard);self.assertEqual(c.form,'달마모드')
    self.assertEqual(M.describe(self.r,c.spec)['slot_count'],1)
    self.assertNotIn(borrowed,M.owned_list(c.spec,'moves',c.moves))
    self.e.use_move(c,target,borrowed)
    self.assertEqual(c.move_uses.get(borrowed),1);self.assertEqual(c.budget['standard'],standard-1)
    self.e.gm.snapshot('csv-form-active')
    saved=json.loads(json.dumps(C.dump_engine(self.e),ensure_ascii=False))
    self.e.end_scene([c,target]);self.assertEqual(c.form,original_form);self.assertNotIn(borrowed,c.moves)
    self.e.gm.restore('csv-form-active',reason='restore actual source permission')
    current=next(a for a in self.e.everyone if a.entity_id==c.entity_id)
    self.assertEqual(current.form,'달마모드');self.assertIn(borrowed,current.moves)
    restored=C.load_engine(self.r,saved);q=next(a for a in restored.everyone if a.entity_id==c.entity_id)
    self.assertEqual(q.move_uses.get(borrowed),1);self.assertEqual(q.budget['swift'],swift-1)
    restored.end_scene(restored.everyone)
    self.assertEqual(q.form,original_form);self.assertNotIn(borrowed,q.moves);self.assertIn(permanent,q.moves)

 def test_original_csv_form_sources_reject_changed_source_and_late_failure_atomically(self):
  import move_permissions as P
  for uid in ('ability/눈덮인달마','ability/달마모드-playtest'):
   with self.subTest(source=uid):
    self.e=Engine(self.r,seed=534);c=self.add(abilities=[uid])
    self.e.begin_encounter([c]);self.e.start_round([c]);self.e.start_of_turn(c)
    def before():return deepcopy((c.spec,c.moves,c.budget,c.form,self.e.rng.getstate()))
    state=before();changed=P.policies(self.r);changed[uid]['definition']['effect']='changed source'
    with patch.object(P,'policies',return_value=changed):
     with self.assertRaisesRegex(ValueError,'source changed'):self.e.activate_form_ability(c,uid)
    self.assertEqual(before(),state)
    original=EXT.h_grant_move
    def fail_after_grant(*args,**kwargs):
     original(*args,**kwargs)
     raise RuntimeError('after native permission grant')
    with patch.object(EXT,'h_grant_move',side_effect=fail_after_grant):
     with self.assertRaisesRegex(RuntimeError,'after native permission'):self.e.activate_form_ability(c,uid)
    self.assertEqual(before(),state)
    self.assertNotIn('_form_permission_activation',c.custom_conditions)
    self.e.activate_form_ability(c,uid);self.assertEqual(c.form,'달마모드')

if __name__=='__main__':unittest.main()
