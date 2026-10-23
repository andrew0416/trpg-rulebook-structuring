"""Full Type Sync state group: legal types and actual GM-authored consumers."""
from pathlib import Path
from copy import deepcopy
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_trainer,build_pokemon
import type_sync as S,state_grants as G,move_state as M,pokemon_teaching as T,downtime as D
from state_codec import StateCodecError

class TypeSyncTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,510)
  self.a=Combatant(self.r,build_trainer(self.r,'GM-reviewed teacher',20,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
   skills={'매력':5,'포켓몬학':3},extra={'feats':[T.MENTOR,T.MOVE_TUTOR,T.EGG_TUTOR]}))
  self.e.gm.add_combatant(self.a)
  T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='actual class skill selections')
  self.p=self.pokemon()
 def pokemon(self):
  p=Combatant(self.r,build_pokemon(self.r,'이상해씨',10,moves=['move/몸통박치기'],abilities=['심록'],
    extra={'trainer_id':self.a.entity_id,'tutor_points':8}))
  self.e.gm.add_combatant(p);return p
 def args(self,p=None,**kw):
  p=p or self.p
  result=dict(application_id='water-sync',chosen_type='물',mode='replace',replace_type='풀',
   capabilities=list(dict.fromkeys(list(p.spec.get('capabilities',[]))+['아가미','물줄기'])),
   abilities=['불굴의방패'],level_up=[{'level':1,'move_id':'move/몸통박치기'},{'level':11,'move_id':'move/물대포'}],
   learning={'exceptions':{}},decisions={'learning':'GM reviewed aquatic anatomy and finds no additional machine/tutor exceptions.',
    'capabilities':'GM removes no existing non-elemental capabilities and adds gills and fountain for the new Water type.',
    'abilities':'GM replaces the lost Grass-expressive ability with the reviewed defensive ability.',
    'level_up':'GM keeps early Tackle and substitutes Water Gun for the new Water-oriented progression, considering frequency and power.'},
   reason='GM observes completed Type Sync; activation costs are a separate procedure')
  result.update(kw);return result
 def sync(self,p=None,**kw):
  p=p or self.p;return self.e.gm.observe_type_sync(p,**self.args(p,**kw))
 def restore(self,e=None):
  e=e or self.e;n=Engine.import_state(e.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
  return n,next(c for c in n.everyone if c.entity_id==self.p.entity_id)
 def before(self):return deepcopy((self.p.spec,self.p.types,self.p.moves,self.p.abilities,self.e.elapsed_seconds,self.e.rng.getstate()))
 def test_all_legal_type_paths_and_illegal_third_type_or_unselected_replacement(self):
  cases=[(['풀'],'add',None,['풀','물']),(['풀'],'replace','풀',['물']),
         (['풀','독'],'replace','풀',['물','독']),(['풀','물'],'retain_chosen',None,['물']),
         (['풀','물'],'replace','풀',['물'])]
  for before,mode,old,after in cases:
   p=self.pokemon();self.e.gm.set_types(p,before,reason='actual original individual types')
   self.sync(p,mode=mode,replace_type=old);self.assertEqual(p.spec['types'],after);self.assertEqual(p.types,after)
  for mode,old in [('add',None),('replace','전기'),('retain_chosen',None)]:
   before=self.before()
   with self.assertRaises(ValueError):self.sync(mode=mode,replace_type=old)
   self.assertEqual(self.before(),before)
  with self.assertRaises(ValueError):self.e.gm.observe_type_sync(self.a,**self.args())
 def test_permanent_change_is_individual_owned_preserves_temporary_sources_and_boundaries(self):
  other=self.pokemon();catalog=deepcopy(self.r.learnset_links)
  G.type_operation(self.p,'add',['고스트'],'other/ghost')
  G.grant(self.p,'capabilities','텔레파시','other/telepathy','fixture')
  self.sync()
  self.assertEqual(self.p.types,['물','독','고스트']);self.assertEqual(other.types,['풀','독'])
  self.assertIn('텔레파시',G.effective_capabilities(self.p));self.assertIn('아가미',G.effective_capabilities(self.p))
  self.assertEqual(self.p.stages['def'],1);self.assertEqual(self.p.abilities,['불굴의방패'])
  self.e.start_round(self.e.everyone);self.e.start_of_turn(self.p,initiative_count=20);self.e.end_of_turn(self.p)
  self.e.end_encounter(self.e.everyone);self.e.end_scene()
  self.assertEqual(self.p.types,['물','독','고스트']);self.assertEqual(self.r.learnset_links,catalog)
  G.remove_owned(self.e,self.p,'other/ghost');self.assertEqual(self.p.types,['물','독'])
  self.assertEqual(self.e.type_multiplier('불꽃',self.p)[0],.5)
 def test_all_gm_choices_are_required_and_failed_ability_registration_is_atomic(self):
  before=self.before()
  args=self.args();args['decisions'].pop('capabilities')
  with self.assertRaises(ValueError):self.e.gm.observe_type_sync(self.p,**args)
  self.assertEqual(self.before(),before)
  with self.assertRaises(ValueError):self.sync(abilities=['unresolved nonexistent ability'])
  self.assertEqual(self.before(),before)
  with self.assertRaises(ValueError):self.sync(level_up=[{'level':11,'move_id':'unresolved move'}])
  self.assertEqual(self.before(),before)
 def test_gm_can_remove_lost_type_capabilities_and_keep_ability_by_explicit_exception(self):
  self.e.gm.set_types(self.p,['불꽃','독'],reason='actual original Fire typing')
  G.set_baseline(self.p,'capabilities',['불쏘시개','따끈따끈','텔레파시'])
  decisions=self.args()['decisions'];decisions['capabilities']='GM removes both lost-element capabilities, keeps unrelated telepathy, and grants aquatic capabilities.'
  decisions['abilities']='GM explicitly permits the original ability to remain as a narrative exception.'
  self.sync(replace_type='불꽃',capabilities=['텔레파시','아가미','물줄기'],abilities=['심록'],decisions=decisions)
  self.assertNotIn('불쏘시개',G.effective_capabilities(self.p));self.assertNotIn('따끈따끈',G.effective_capabilities(self.p))
  self.assertEqual(self.p.abilities,['심록']);self.assertIn('텔레파시',G.effective_capabilities(self.p))
 def test_native_tm_compatibility_uses_new_type_and_actual_machine_resources(self):
  self.a.spec['items']['TM55']=1;T.register_machine(self.e,self.a,instance_id='scald',code='TM55')
  with self.assertRaisesRegex(ValueError,'compatible'):T.teach_machine(self.e,self.a,target=self.p,instance_id='scald')
  self.sync()
  self.sync(application_id='electric-sync',chosen_type='전기',replace_type='독')
  self.assertEqual(self.p.types,['물','전기'])
  before=self.p.spec['tutor_points'];T.teach_machine(self.e,self.a,target=self.p,instance_id='scald')
  self.assertIn('move/열탕',self.p.moves);self.assertEqual(self.p.spec['tutor_points'],before-1)
  self.assertEqual(self.e.elapsed_seconds,3600);self.assertEqual(self.a.spec['teaching_machines']['scald']['status'],'consumed')
  self.assertTrue(S.learning_permission(self.r,self.p.spec,'move/파도타기','hm'))
  M.observe_learning(self.e,self.p,'move/파도타기',method='hm',source=T.MACHINES,paid_tp=0,reason='GM observes a completed compatible HM learning result; independent HM payment procedure remains separately reviewed')
  self.assertIn('move/파도타기',self.p.moves)
  self.assertEqual(self.p.spec['move_learning']['move/파도타기']['method'],'hm')
  self.assertEqual(M.describe(self.r,self.p.spec)['classifications']['move/파도타기'],'taught')
 def test_native_tutor_accepts_common_new_type_and_gm_denial_precedes_every_cost(self):
  self.sync()
  before=self.p.spec['tutor_points']
  T.teach_feature(self.e,self.a,target=self.p,move_id='물의파동',feature=T.MOVE_TUTOR,seconds=60,reason='GM observed actual Extended tutoring')
  self.assertIn('move/물의파동',self.p.moves);self.assertEqual(self.p.spec['tutor_points'],before-2)
  self.setUp()
  self.sync(learning={'exceptions':{'move/열탕':{'allowed':False,'reason':'GM rules this individual anatomy cannot project Scald'},
                                     'move/물의파동':{'allowed':False,'reason':'GM rules this individual cannot shape a pulse'}}})
  self.a.spec['items']['TM55']=1;T.register_machine(self.e,self.a,instance_id='blocked',code='TM55')
  before=deepcopy((self.a.spec,self.p.spec,self.e.elapsed_seconds))
  with self.assertRaisesRegex(ValueError,'exception'):T.teach_machine(self.e,self.a,target=self.p,instance_id='blocked')
  with self.assertRaisesRegex(ValueError,'exception'):T.teach_feature(self.e,self.a,target=self.p,move_id='물의파동',feature=T.MOVE_TUTOR,seconds=60,reason='observed attempt')
  self.assertEqual(before,(self.a.spec,self.p.spec,self.e.elapsed_seconds))
 def test_actual_level_up_uses_individual_list_and_retains_old_natural_history(self):
  self.sync();self.assertIn('move/몸통박치기',M.natural_moves(self.r,self.p.spec))
  D.gain_exp_combatant(self.e,self.p,'to next level')
  self.assertEqual(self.p.level,11);self.assertIn('move/물대포',self.p.moves);self.assertEqual(self.p.types,['물','독'])
  self.assertEqual(M.describe(self.r,self.p.spec)['classifications']['move/물대포'],'natural')
  history=self.p.spec[M.HISTORY]['move/물대포'];self.assertEqual(history[-1]['type_sync_id'],'water-sync')
  self.sync(application_id='fire-sync',chosen_type='불꽃',replace_type='물',level_up=[{'level':1,'move_id':'move/몸통박치기'},{'level':12,'move_id':'move/불꽃세례'}])
  self.assertIn('move/물대포',M.natural_moves(self.r,self.p.spec))
  D.gain_exp_combatant(self.e,self.p,'to next level')
  self.assertIn('move/불꽃세례',self.p.moves);self.assertEqual(self.p.types,['불꽃','독'])
 def test_mentor_uses_adapted_future_list_and_keeps_historical_sync_evidence(self):
  self.sync(level_up=[{'level':1,'move_id':'move/몸통박치기'},{'level':18,'move_id':'move/물대포'}])
  T.teach_feature(self.e,self.a,target=self.p,move_id='물대포',feature=T.MENTOR,seconds=60,reason='actual Mentor session')
  self.assertIn('move/물대포',M.natural_moves(self.r,self.p.spec))
  self.assertEqual(self.p.spec['move_learning']['move/물대포']['type_sync_id'],'water-sync')
  self.sync(application_id='fire-sync',chosen_type='불꽃',replace_type='물',level_up=[])
  self.assertIn('move/물대포',M.natural_moves(self.r,self.p.spec))
 def test_snapshot_and_durable_restore_preserve_choices_then_run_growth(self):
  self.sync();self.e.gm.snapshot('synced');D.gain_exp_combatant(self.e,self.p,'to next level')
  self.e.gm.restore('synced');self.assertEqual(self.p.level,10)
  n,p=self.restore();D.gain_exp_combatant(n,p,'to next level')
  self.assertEqual(p.types,['물','독']);self.assertIn('move/물대포',p.moves)
  self.assertEqual(p.spec[S.KEY]['history'][0]['decisions'],self.args()['decisions'])
 def test_replay_corrupt_sources_and_bypassing_permanent_review_are_rejected(self):
  self.sync();before=self.before()
  with self.assertRaisesRegex(ValueError,'already'):self.sync()
  self.assertEqual(self.before(),before)
  with self.assertRaisesRegex(ValueError,'complete reviewed'):self.e.gm.set_types(self.p,['전기'],reason='incomplete retarget')
  self.assertEqual(self.before(),before)
  self.p.spec[S.KEY]['history'][0]['after']['types']=['물','독','고스트']
  with self.assertRaises(StateCodecError):self.e.export_state()
  with self.assertRaises(ValueError):self.e.gm.snapshot('invalid')
  self.setUp();self.sync();self.e.gm.snapshot('valid')
  self.e.gm.snapshots['valid']['combatants'][id(self.p)]['spec'][S.KEY]['history'][0]['source']='wrong-source'
  before=self.before()
  with self.assertRaises(ValueError):self.e.gm.restore('valid')
  self.assertEqual(self.before(),before)

if __name__=='__main__':unittest.main()
