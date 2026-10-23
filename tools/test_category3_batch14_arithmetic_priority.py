"""Batch14 fixed common arithmetic/precedence with real native boundary witnesses."""
from pathlib import Path
from fractions import Fraction
from copy import deepcopy
from dataclasses import replace
from itertools import permutations
from unittest.mock import patch
from datetime import datetime,timezone
import hashlib,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
import arithmetic as A
import arithmetic_policy as M
import native_rule_policy as P
import root_resolution as R
import downtime as D
import skill_stunts as ST
import turn as TURN
from audit_common_arithmetic_consumers import inventory, classify
SCOPES={'C3-CORE-005':'23212796ce2f325a242d48af9148fd356805ef32065b35efa339533517ebc5e1',
 'C3-CORE-006':'1f94f177efd9fe52bf307ea9ba1a3382bccd07bca6320c14f3829067aeb98fae',
 'C3-CORE-007':'a89d9428bbf58b4151ada0013ca74fb0ff5cbf2f2b6dc41cfec583319ca0ef30'}
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
 def setUp(self):
  self.e=Engine(self.r,142)
  self.a=Combatant(self.r,dict(id='trainer/math',name='A',kind='trainer',level=20,stats=dict(hp=20,atk=8,**{'def':8},spa=8,spd=8,spe=8),skills={'오컬트학':3,'기술학':3,'의학':3},items={'상처약':2,'다우징 로드':1},edges=[],moves=['move/몸통박치기'],pos=(0,0),types=[]))
  self.b=Combatant(self.r,dict(id='pokemon/math',name='B',kind='pokemon',level=20,stats=dict(hp=20,atk=8,**{'def':8},spa=8,spd=8,spe=8),skills={},items={},moves=['move/몸통박치기'],pos=(1,0),types=[]))
  self.e.everyone=self.e.gm.everyone=[self.a,self.b]
 def state(self):
  return deepcopy((self.e.rng.getstate(),self.e.elapsed_seconds,[(x.spec,x.hp,x.stats,x.level,x.move_uses,getattr(x,'budget',None),getattr(x,'_action_history',None),getattr(x,'pending_action_loss',None)) for x in self.e.everyone]))
 def turn(self):self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
 def selected_other(self):
  original=self.r._selected_rule
  return patch.object(self.r,'_selected_rule',side_effect=lambda uid,*args,**kwargs:uid+'/unreviewed' if uid==M.SOURCE else original(uid,*args,**kwargs))
 def approve_stunt(self):
  self.a.spec['edges']=[ST.SOURCE]
  self.e.approve_skill_stunt(self.a,choice_id='dowsing',skill='오컬트학',use='다우징',reason='GM approved this narrow acquired use',approved=True)
 def test_fixed_complete_source_scopes_and_source_excerpts(self):
  register=json.loads((ROOT/'data/verification/category3-register.json').read_text(encoding='utf8'))
  found={}
  for row in register['entries']:
   if row['id'] not in SCOPES:continue
   found[row['id']]=row['scope_sha256']
   for a in row['source_snapshot'].get('source_anchors',row['source_snapshot'].get('anchors',[row['source_snapshot']['source']])):
    text='\n'.join((ROOT/a['file']).read_text(encoding='utf-8-sig').splitlines()[a.get('start_line',a.get('start'))-1:a.get('end_line',a.get('end'))])
    self.assertEqual(text,a['excerpt']);self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),a['excerpt_sha256'])
    self.assertEqual(hashlib.sha256((ROOT/a['file']).read_bytes()).hexdigest(),a['file_sha256'])
  self.assertEqual(found,SCOPES)
 def test_floor_full_signed_decimal_operator_and_exact_intermediates(self):
  for raw,want in [('3.9999',3),('3.5',3),('-0.5',-1),('-3.9999',-4),('0',0)]:self.assertEqual(M.floor(raw),want)
  self.assertEqual(M.product(100,'1.15'),115)
  self.assertEqual(A.evaluate('0.1+0.2',{}),Fraction(3,10))
  self.assertEqual(M.ratio(-83,2),-42);self.assertEqual(-M.ratio(83,2),-41)
  self.assertEqual(M.ceil_ratio(83,2),42)
 def test_declared_percentage_sum_twenty_plus_thirty_is_fifty(self):
  kw=dict(quantity='stat',base_id='actual-stat',stage='one-stage')
  self.assertEqual(M.increase(100,'0.2','0.3',**kw),150)
  self.assertEqual(M.adjustment(3,'0.2','0.3',**kw),4)
  self.assertNotEqual(M.increase(100,'0.2','0.3',**kw),156)
 def test_signed_percentage_reductions_mixed_and_negative_total(self):
  kw=dict(quantity='stat',base_id='actual-stat',stage='one-stage')
  for rates,want in [(('-0.2','-0.3'),50),(('0.3','-0.2'),110),(('-0.6','-0.6'),-20)]:
   self.assertEqual(M.adjustment(100,*rates,**kw),want)
  self.assertEqual(M.adjustment(3,'-0.2','-0.3',**kw),1)
 def test_percentage_contributions_require_same_quantity_base_stage_and_type(self):
  for q,b,s in [('hp','a','one'),('stat','b','one'),('stat','a','two')]:
   c=M.PercentageAdjustment('-0.2',q,b,s,'reviewed source')
   with self.assertRaises(ValueError):M.accumulate_adjustments(100,[c],quantity='stat',base_id='a',stage='one')
  with self.assertRaises(ValueError):M.accumulate_adjustments(100,[1.5],quantity='stat',base_id='a',stage='one')
  with self.assertRaises(ValueError):M.PercentageIncrease('-0.2','stat','a','one','source')
 def test_native_positive_and_negative_stages_consume_additive_policy(self):
  for base in range(1,25):
   self.a.stats['atk']=base
   for stage in range(-6,7):
    self.a.stages['atk']=stage
    self.assertEqual(self.a.staged('atk'),max(1,base*(10+(2*stage if stage>=0 else stage))//10))
  self.a.stats['atk']=8;self.a.stages['atk']=-3
  with patch.object(M,'accumulate_adjustments',wraps=M.accumulate_adjustments) as call:
   self.assertEqual(self.a.staged('atk'),5)
  call.assert_called_once();self.assertEqual(call.call_args.kwargs,dict(quantity='combat_stat',base_id='unstaged_stat',stage='combat_stages'))
 def test_named_fixed_factors_remain_multiplicative_not_percent_pooled(self):
  self.assertEqual(M.product(19,'1.5','0.5'),14)
  amount,_=D.award_exp(self.r,[10],1,significance=2,challenge=1.5);self.assertEqual(amount,30)
  table={str(i):'1.125' for i in range(-6,7)}
  self.assertEqual(M.stage_stat(8,-3,table),9)
 def test_native_move_source_change_rejects_before_standard_frequency_rng(self):
  self.turn();before=self.state()
  with self.selected_other(),self.assertRaises(ValueError):self.e.use_move(self.a,self.b,'move/몸통박치기',set_damage=True)
  self.assertEqual(before,self.state())
 def test_direct_accuracy_and_damage_source_change_do_not_observe_rng(self):
  move=self.r.move('move/몸통박치기');before=self.state()
  with self.selected_other():
   with self.assertRaises(ValueError):self.e.accuracy_check(self.a,self.b,move)
   with self.assertRaises(ValueError):self.e.roll_damage(self.a,self.b,move)
  self.assertEqual(before,self.state())
 def test_turn_cost_rejects_unreviewed_common_gm_override_before_spending(self):
  self.turn();before=self.state()
  with patch.dict(self.r.rulings.mech,{M.SOURCE:{'rounding':{'value':'nearest'}}}),self.assertRaises(ValueError):TURN.spend(self.e,self.a,'standard')
  self.assertEqual(before,self.state())
 def test_actual_level_up_fraction_preserved_with_floor_not_nearest(self):
  c=Combatant(self.r,build_pokemon(self.r,'브케인',5,name='level-floor'));self.e.everyone=self.e.gm.everyone=[c]
  old_max=c.max_hp;c.hp=old_max-1;old_hp=c.hp
  D.gain_exp_combatant(self.e,c,'to next level')
  self.assertEqual(c.level,6);exact=Fraction(old_hp*c.max_hp,old_max)
  self.assertNotEqual(exact.denominator,1);self.assertEqual(c.hp,exact.numerator//exact.denominator)
  self.assertNotEqual(c.hp,round(exact))
 def test_level_up_source_change_rejects_before_spec_hp_or_level_mutation(self):
  before=self.state()
  with self.selected_other(),self.assertRaises(ValueError):D.gain_exp_combatant(self.e,self.b,'to next level')
  self.assertEqual(before,self.state())
 def test_path_dispositions_do_not_hide_unreviewed_numeric_division(self):
  self.assertEqual(classify('source_catalog.py','definition','division',"root / entry['source_file']")[0],'filesystem_or_parser')
  for file,fn,expr in [('source_catalog.py','definition','root / 2'),('unknown.py','definition',"root / entry['source_file']"),('telekinetic_load.py','range_check','min(dx,dy)//3')]:
   self.assertEqual(classify(file,fn,'floor_division' if '//' in expr else 'division',expr)[0],'needs_review')
 def test_finite_current_numeric_consumers_have_no_unreviewed_rounding_sites(self):
  rows,_=inventory()
  self.assertFalse([r for r in rows if r['status'] in ('needs_review','unresolved_legacy_policy')])
  self.assertTrue(any(r['file']=='engine/downtime.py' and r['function']=='_gain_exp_combatant' and r['kind']=='policy_call' and r['expression']=='M.ratio(hp_before * c.base_max_hp, old_max_hp)' for r in rows))
 def test_specific_self_restorative_cost_and_debt_expire_at_correct_boundary(self):
  self.a.hp=1;self.turn();self.e.use_item(self.a,'상처약',self.a)
  self.assertEqual(self.a.hp,21);self.assertEqual(self.a.budget,dict(standard=0,shift=0,swift=1));self.assertIsNone(getattr(self.a,'pending_action_loss',None))
  self.e.end_of_turn(self.a);self.e.start_round([self.a]);self.e.start_of_turn(self.a)
  self.assertEqual(self.a.budget,dict(standard=1,shift=1,swift=1))
 def test_specific_medic_exempts_recipient_debt_without_waiving_user_action(self):
  self.a.spec['edges']=['edge/메딕-훈련'];self.b.hp=1;self.turn();self.e.use_item(self.a,'상처약',self.b)
  self.assertEqual(self.a.budget,dict(standard=0,shift=1,swift=1));self.assertIsNone(getattr(self.b,'pending_action_loss',None));self.assertEqual(self.b.hp,21)
 def test_absent_specific_medic_keeps_general_recipient_debt(self):
  self.b.hp=1;self.turn();self.e.use_item(self.a,'상처약',self.b)
  self.assertEqual(self.b.pending_action_loss,dict(standard=1,swift=1))
 def test_actual_dowsing_exception_is_plus_one_die_without_general_plus_six(self):
  self.approve_stunt();out=self.e.pokemon_activity(self.a,'dowse',outdoors=True,fixed={str(i):1 for i in range(4)})
  self.assertEqual(out['pool'],4);self.assertEqual(out['gained'],{});self.assertEqual(self.e.elapsed_seconds,600)
  self.assertEqual(self.a.spec['dowsing']['uses'],1)
 def test_unowned_specific_exception_cannot_replace_general_rule(self):
  self.approve_stunt();self.a.spec['edges']=[];before=self.state()
  with self.assertRaises(ValueError):self.e.pokemon_activity(self.a,'dowse',outdoors=True)
  self.assertEqual(before,self.state())
 def test_changed_precedence_text_rejects_both_native_consumers_before_mutation(self):
  self.approve_stunt();self.b.hp=1;before=self.state()
  original=Path.read_bytes
  def changed(path):
   content=original(path)
   return content+b'changed precedence' if path.name=='ch06-gameplay.md' else content
  with patch.object(Path,'read_bytes',changed):
   for action in (lambda:self.e.use_item(self.a,'상처약',self.b),lambda:self.e.pokemon_activity(self.a,'dowse',outdoors=True)):
    with self.assertRaises(P.PolicyPending) as exc:action()
    self.assertEqual(exc.exception.code,'stale_policy_source')
    self.assertEqual(before,self.state())
 def test_native_precedence_source_change_rejects_before_item_cost_or_dowsing_time(self):
  self.approve_stunt();self.b.hp=1;before=self.state()
  with self.selected_other():
   with self.assertRaises(P.PolicyPending):self.e.use_item(self.a,'상처약',self.b)
   with self.assertRaises(P.PolicyPending):self.e.pokemon_activity(self.a,'dowse',outdoors=True)
  self.assertEqual(before,self.state())
 def test_common_precedence_gm_override_and_unknown_fact_are_pending(self):
  with patch.dict(self.r.rulings.mech,{P.PRECEDENCE_SOURCE:{'ordering':{'value':'arbitrary'}}}):
   with self.assertRaises(P.PolicyPending):P.evaluate(self.r,'skill_stunt',{'dowsing':True})
  with self.assertRaises(P.PolicyPending):P.evaluate(self.r,'medicine',dict(self_use=None,restorative=True,medic=False))
  with self.assertRaises(TypeError):P.evaluate(self.r,'medicine',dict(self_use='false',restorative=True,medic=False))
 def request(self,cs,edges):
  return R.ResolutionRequest('reviewed-event','batch14','profile','catalog','context',tuple(cs),tuple(edges),(R.CompositionLaw('value','exclusive','reviewed-composition'),),R.TRUE)
 def test_scoped_specific_precedence_is_order_independent_and_not_global(self):
  general=R.Clause('general','value',1);specific=R.Clause('specific','value',2)
  edge=R.Override('general','specific','value',R.TRUE,'reviewed-source')
  for cs in permutations((general,specific)):
   answer=R.resolve(self.request(cs,(edge,)));self.assertEqual(answer.aspects[0].value,2)
  answer=R.resolve(self.request((general,replace(specific,scope=R.FALSE)),(edge,)))
  self.assertEqual(answer.aspects[0].value,1)
 def test_conflicting_specifics_unknown_guards_and_cycles_never_choose_arbitrarily(self):
  g=R.Clause('general','value',1);a=R.Clause('specific-a','value',2);b=R.Clause('specific-b','value',3)
  edge=lambda x,y,guard=R.TRUE:R.Override(x,y,'value',guard,'reviewed-source')
  cases=[((g,a,b),(edge('general','specific-a'),edge('general','specific-b'))),
   ((g,a),(edge('general','specific-a',R.Predicate(R.Truth.UNKNOWN,'unknown actual condition')),)),
   ((g,a),(edge('general','specific-a'),edge('specific-a','general')))]
  for cs,edges in cases:self.assertNotEqual(R.resolve(self.request(cs,edges)).tag,'ModelReady')
 def test_native_receipt_preserves_general_law_specific_source_and_aspect_contributor(self):
  answer=P.evaluate(self.r,'skill_stunt',{'dowsing':True})
  self.assertEqual(answer['precedence_source'],P.PRECEDENCE_SOURCE)
  self.assertEqual(answer['aspects'][0]['contributors'],['stunt.dowsing']);self.assertEqual(answer['aspects'][0]['dominated'],['stunt.normal'])
  self.assertFalse(answer['whole_engine_certified'])

class Result(unittest.TextTestResult):
 def __init__(self,*a,**kw):super().__init__(*a,**kw);self.rows=[]
 def addSuccess(self,t):super().addSuccess(t);self.rows.append({'id':t._testMethodName,'status':'pass'})
 def addFailure(self,t,e):super().addFailure(t,e);self.rows.append({'id':t._testMethodName,'status':'fail'})
 def addError(self,t,e):super().addError(t,e);self.rows.append({'id':t._testMethodName,'status':'error'})
if __name__=='__main__':
 result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
 paths=sorted(set([p.relative_to(ROOT).as_posix() for p in (ROOT/'engine').glob('*.py')]+[p.relative_to(ROOT).as_posix() for p in (ROOT/'data').glob('*.json')]+['tools/test_category3_batch14_arithmetic_priority.py','tools/audit_common_arithmetic_consumers.py','input/ch06-gameplay.md','input/ch07-combat.md','input/ch03-skills-edges-feats.md','input/ch09-equipment.md']))
 report={'generated_at':datetime.now(timezone.utc).isoformat(),'successful':result.wasSuccessful(),'scope':list(SCOPES),'completion_scopes':list(SCOPES),'partial_scopes':[],'source_scope_sha256':SCOPES,'results':result.rows,'input_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
 (ROOT/'output/category3-batch14-arithmetic-priority-tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 raise SystemExit(not result.wasSuccessful())
