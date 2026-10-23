"""C11-048 uses the existing creation, natural offers and learning boundary."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer
import example_species as X,move_state as M,pokemon_teaching as T,downtime as D,learning_grant as L
import state_codec as CODEC,state_grants as G

PACIFIST='pokemon/example/pacifist-chimecho'
BIRTH=['move/희망사항','move/빛의장막','move/리플렉터']

class PacifistChimechoTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,seed=1308)
  self.a=self.add(build_trainer(self.r,'actual teacher',35,dict.fromkeys(('hp','atk','def','spa','spd','spe'),10),
   abilities=[],extra={'skills':{'매력':5,'포켓몬학':3},'feats':[T.MENTOR,T.MOVE_TUTOR,T.EGG_TUTOR],
    'items':{'TM6':1,'TM3':1,'TM70':1,'TM4':1},'edges':['edge/브리더']}))
  T.select_mentor_skills(self.e,self.a,['매력','포켓몬학'],reason='actual selected teaching skills')
 def add(self,spec):
  actor=Combatant(self.r,spec);self.e.gm.add_combatant(actor);return actor
 def pokemon(self,level=35,**extra):
  return self.add(build_pokemon(self.r,PACIFIST,level,abilities=[],extra={'trainer_id':self.a.entity_id,'tutor_points':8,**extra}))
 def before(self):return deepcopy(([(c.spec,c.moves,c.abilities) for c in self.e.everyone],self.e.elapsed_seconds,self.e.rng.getstate(),self.e.log_lines))
 def teach(self,p,name,feature=T.MOVE_TUTOR):
  return T.teach_feature(self.e,self.a,target=p,move_id=name,feature=feature,seconds=60,reason='actual Extended teaching')

 def test_birth_three_and_stock_species_are_independent(self):
  stock=deepcopy((self.r.species['pokemon/치렁'],self.r.learnsets['치렁'],self.r.learnset_links['치렁']))
  p=self.pokemon(1);other=self.pokemon(10)
  self.assertEqual(p.moves,BIRTH+['struggle']);self.assertEqual(other.moves,p.moves)
  self.assertEqual(p.spec['source'],'core_example')
  self.assertEqual(p.spec['example_definition']['definition_id'],PACIFIST)
  ordinary=build_pokemon(self.r,'치렁',10,moves=['move/염동력'],abilities=[])
  self.assertIn('move/염동력',ordinary['moves'])
  self.assertIn('move/염동력',M.current_natural_evidence(self.r,ordinary))
  self.assertNotIn('move/염동력',M.current_natural_evidence(self.r,other.spec))
  self.assertEqual(stock,(self.r.species['pokemon/치렁'],self.r.learnsets['치렁'],self.r.learnset_links['치렁']))

 def test_selected_damage_status_and_target_semantics_keep_benign_status(self):
  for name in ['염동력','맹독','뽐내기','전기자석파','도발','트집','울음소리','플래시','하품','트릭','스킬스왑','위액','회복봉인','모래바람']:
   with self.subTest(harmful=name):self.assertTrue(X.harmful_move(self.r,self.r.move_id(name)))
  for name in ['희망사항','빛의장막','리플렉터','치료방울','치유파동','명상','잠자기','대타출동','웅크리기','치유소원','역할','쾌청','비바라기','중력','트릭룸']:
   with self.subTest(benign=name):self.assertFalse(X.harmful_move(self.r,self.r.move_id(name)))
  # The same selected identity changes classification with its actual effect,
  # even when neither a damaging class nor a recognizable offensive name exists.
  for effect,expected in [({'type':'hp_loss','value':1,'target':'target'},True),
    ({'type':'stage_change','stat':'def','delta':-1,'target':'target'},True),
    ({'type':'apply_status','status':'잠듦','target':'self'},False),
    ({'type':'hp_loss','value':1,'target':'self'},False)]:
   with self.subTest(effect=effect),patch.object(self.r,'move_mech',return_value=({'effects_exec':[effect]},'authored')):
    self.assertEqual(X.harmful_move(self.r,'move/희망사항'),expected)
  with patch.object(self.r,'move_mech',return_value=({'effects_exec':[{'type':'opaque_callback','target':'self','then':[{'type':'apply_status','status':'혼란'}]}]},'authored')):
   with self.assertRaisesRegex(ValueError,'reviewed effect harm'):X.harmful_move(self.r,'move/희망사항')
  with self.assertRaisesRegex(ValueError,'reviewed custom-condition harm'):X.harmful_move(self.r,'move/텔레키네시스')

 def test_native_level_growth_skips_harmful_offers_and_learns_healing(self):
  for level,forbidden in [(3,'move/울음소리'),(9,'move/염동력'),(12,'move/하품')]:
   with self.subTest(level=level):
    p=self.pokemon(level);old=deepcopy(p.spec);D.gain_exp_combatant(self.e,p,'to next level')
    self.assertEqual(p.level,level+1);self.assertNotIn(forbidden,p.moves)
    self.assertEqual(sum(p.spec['stats'].values()),sum(old['stats'].values())+1)
    self.assertNotIn(forbidden,p.spec.get(M.HISTORY,{}))
  p=self.pokemon(26);D.gain_exp_combatant(self.e,p,'to next level')
  self.assertIn('move/치료방울',p.moves)
  self.assertEqual(p.spec['move_learning']['move/치료방울']['method'],'level_up')

 def test_actual_offensive_machines_reject_without_payment_time_or_inventory(self):
  p=self.pokemon()
  for code in ['TM6','TM3','TM70']:
   with self.subTest(code=code):
    T.register_machine(self.e,self.a,instance_id=code,code=code);before=self.before()
    with self.assertRaisesRegex(ValueError,'pacifist'):T.teach_machine(self.e,self.a,target=p,instance_id=code)
    self.assertEqual(self.before(),before)
  T.register_machine(self.e,self.a,instance_id='safe',code='TM4')
  out=T.teach_machine(self.e,self.a,target=p,instance_id='safe')
  self.assertEqual(out['move'],'move/명상');self.assertIn('move/명상',p.moves)
  self.assertEqual((p.spec['tutor_points'],self.e.elapsed_seconds),(7,3600))
  self.assertEqual(self.a.spec['teaching_machines']['safe']['status'],'consumed')

 def test_actual_tutor_and_mentor_reject_harm_then_healing_tutor_succeeds(self):
  p=self.pokemon()
  for name,feature in [('시그널빔',T.MOVE_TUTOR),('텔레키네시스',T.MOVE_TUTOR),('트릭',T.MOVE_TUTOR),('스킬스왑',T.MOVE_TUTOR),('하품',T.MENTOR)]:
   with self.subTest(name=name):
    before=self.before()
    with self.assertRaises(ValueError):self.teach(p,name,feature)
    self.assertEqual(self.before(),before)
  self.teach(p,'치료방울')
  self.assertIn('move/치료방울',p.moves)
  self.assertEqual((p.spec['tutor_points'],self.e.elapsed_seconds),(6,60))
  # Role Play copies onto the user; Skill Swap removes another's ability.
  self.setUp();p=self.pokemon();self.teach(p,'역할')
  self.assertIn('move/역할',p.moves)

 def test_native_initial_extra_gm_and_learning_observation_cannot_bypass(self):
  with self.assertRaisesRegex(ValueError,'pacifist'):
   build_pokemon(self.r,PACIFIST,35,abilities=[],extra={'moves':BIRTH+['move/맹독','struggle']})
  p=self.pokemon();before=self.before()
  with self.assertRaisesRegex(ValueError,'pacifist'):self.e.gm.set_move(p,'move/맹독',True,reason='observed learning')
  self.assertEqual(self.before(),before)
  for method in ['tm','tutor','feature']:
   with self.subTest(method=method):
    kw={'application_id':'actual-vm'} if method=='vm' else {}
    source=M.VM_SOURCE if method=='vm' else T.MOVES
    with self.assertRaisesRegex(ValueError,'pacifist'):
     M.observe_learning(self.e,p,'맹독',method=method,source=source,reason='actual observed acquisition',**kw)
    self.assertEqual(self.before(),before)
  polygon=Rules(ROOT,ruleset='polygon');vm_engine=Engine(polygon,seed=1308)
  vm_actor=Combatant(polygon,build_pokemon(polygon,PACIFIST,35,abilities=[]));vm_engine.gm.add_combatant(vm_actor)
  vm_before=deepcopy((vm_actor.spec,vm_actor.moves,vm_engine.elapsed_seconds))
  with self.assertRaisesRegex(ValueError,'pacifist'):
   M.observe_vm_learning(vm_engine,vm_actor,'맹독',application_id='actual-vm',reason='selected native VM acquisition')
  self.assertEqual(vm_before,(vm_actor.spec,vm_actor.moves,vm_engine.elapsed_seconds))
  for name in ['위액','회복봉인','모래바람']:
   with self.subTest(observed_harm=name):
    before=self.before()
    with self.assertRaisesRegex(ValueError,'pacifist'):
     M.observe_learning(self.e,p,name,method='feature',source=T.MOVES,reason='actual observed native effect learning')
    self.assertEqual(self.before(),before)
  for name in ['쾌청','비바라기']:
   M.observe_learning(self.e,p,name,method='feature',source=T.MOVES,reason='actual observed neutral weather learning')
   self.assertIn(self.r.move_id(name),p.moves)
  G.overlay(p,'move display',moves=['move/맹독','struggle'])
  self.assertNotIn('move/맹독',M.owned_list(p.spec,'moves',p.moves))
  M.validate_actor(p)  # A display/permission is not a learned Move.

 def test_common_permanent_grant_rejects_harm_for_every_native_method(self):
  p=self.pokemon()
  for method in ['level_up','evolution','egg','tm','hm','tutor','mentor','mentor_csv','vm','n_tutor']:
   with self.subTest(method=method):
    before=deepcopy(p.spec)
    with self.assertRaisesRegex(ValueError,'pacifist'):
     L.learn_moves(self.r,p.spec,candidates=['move/맹독'],selected=['move/맹독'],method=method,
      source='pokemon/level-up',reason='native grant admission boundary')
    self.assertEqual(p.spec,before)

 def test_actual_declared_inherited_birth_cannot_add_toxic(self):
  parents=[self.add(build_pokemon(self.r,'치렁',35,moves=[],abilities=[],extra={'trainer_id':self.a.entity_id,'gender':gender})) for gender in ['female','male']]
  self.e.gm.set_move(parents[0],'맹독',True,reason='actual observed parent knowledge')
  declaration=json.loads((ROOT/'data/examples/egg-creation.json').read_text(encoding='utf8'))[0]
  declaration['species']['allowed']=[PACIFIST]
  row=self.e.create_declared_egg(self.a,parents,declaration,request_id='pacifist-egg',compatible=True,species=PACIFIST,
   inheritance_moves=['move/맹독'],reason='GM adopts actual example child species')
  choices={'gender':'female','nature':'노력','abilities':[],'moves':BIRTH+['move/맹독'],'inheritance_moves':['move/맹독'],'special_appearance':False}
  before=self.before()
  with self.assertRaisesRegex(ValueError,'pacifist'):
   self.e.hatch_declared_egg(self.a,row['entity_id'],name='child',ready=True,reason='actual observed hatch',choices=choices)
  self.assertEqual(self.before(),before)
  self.assertFalse(row['hatched'])

 def test_source_provenance_and_saved_learned_state_are_enforced(self):
  p=self.pokemon();self.teach(p,'치료방울');self.e.gm.snapshot('pacifist')
  saved=json.loads(json.dumps(CODEC.dump_engine(self.e),ensure_ascii=False))
  fresh=Rules(ROOT,ruleset='core');restored=CODEC.load_engine(fresh,saved)
  q=next(c for c in restored.everyone if c.entity_id==p.entity_id)
  self.assertEqual(q.spec,p.spec);self.assertIn('move/치료방울',q.moves)
  with self.assertRaisesRegex(ValueError,'pacifist'):restored.gm.set_move(q,'맹독',True,reason='restored acquisition')
  original=self.r._selected_rule
  with patch.object(self.r,'_selected_rule',side_effect=lambda key:X.SOURCE+'/disabled' if key==X.SOURCE else original(key)):
   with self.assertRaises(ValueError):build_pokemon(self.r,PACIFIST,1)
  for mutation in ['provenance','harmful']:
   with self.subTest(mutation=mutation):
    p.spec=deepcopy(q.spec)
    if mutation=='provenance':p.spec['example_definition']['definition_id']='pokemon/치렁'
    else:p.spec['moves'].append('move/맹독');p.moves.append('move/맹독')
    with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
  self.e.gm.restore('pacifist');self.assertIn('move/치료방울',p.moves);self.assertNotIn('move/맹독',p.moves)

if __name__=='__main__':unittest.main()
