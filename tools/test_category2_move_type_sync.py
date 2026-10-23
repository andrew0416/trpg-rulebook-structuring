"""Direct contract tests for C11-053..055 permanent Move Sync."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

# Seed every staged replacement before engine.py promotes its own directory.
import move_type_sync as SYNC
import pokemon_move_edges as _STAGED_POKEMON_MOVE_EDGES
import class_move_grants as CLASS_MOVES
import move_state as MOVES
import gm_state as _STAGED_GM_STATE
from engine import Rules,Engine,Combatant
from builder import build_pokemon


class MoveTypeSyncTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

 def setUp(self):
  self.e=Engine(self.r,seed=53055)
  self.p=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,moves=['move/냉동빔'],abilities=['심록'],extra={'tutor_points':8}))
  self.t=Combatant(self.r,build_pokemon(self.r,'꼬부기',20,moves=['move/몸통박치기'],abilities=['급류'],side='wild'))
  self.e.gm.add_combatant(self.p);self.e.gm.add_combatant(self.t)

 def changed(self,**overrides):
  args={'application_id':'fire-beam','move_id':'move/냉동빔','chosen_type':'불꽃','new_name':'화염광선',
        'effect_decision':{'mode':'replace','reason':'Cold rider follows the new elemental expression.',
                           'effects_exec':[{'type':'apply_status','status':'화상','target':'target','on_natural_roll_min':19}]},
        'feasibility_review':'Range, accuracy, damage class, and target stay printed.',
        'power_review':'Burn replaces freeze at the same natural-roll threshold.',
        'reason':'GM observes completed Move Sync; feature payment remains separate.'}
  args.update(overrides);return args

 def preserved(self,**overrides):
  args={'application_id':'spirit-bolt','move_id':'move/10만볼트','chosen_type':'고스트','new_name':'스피릿볼트',
        'effect_decision':{'mode':'preserve','reason':'Paralysis is still appropriate for this spectral shock.','effects_exec':None},
        'feasibility_review':'The renamed Move keeps its printed range, class, accuracy, and targets.',
        'power_review':'No effect or damage-base change is introduced.',
        'reason':'GM observes completed Move Sync after the prior synced Move was forgotten.'}
  args.update(overrides);return args

 def test_source_policy_and_three_clause_boundary(self):
  source=(ROOT/'input/ch11-running-the-game.md').read_text(encoding='utf-8').splitlines()
  self.assertIn('기술 타입을 영구적으로 변경',source[1526])
  self.assertIn('각 GM의 몫',source[1529])
  self.assertIn('기술의 이름을 변경',source[1531])
  policy=SYNC.policy(self.r)
  self.assertEqual(policy['clauses'],['C11-053','C11-054','C11-055'])

 def test_type_name_and_changed_effect_are_consumed_by_actual_move(self):
  receipt=self.e.gm.observe_move_type_sync(self.p,**self.changed())
  self.assertEqual((receipt['base_type'],receipt['synced_type'],receipt['base_name'],receipt['synced_name']),
                   ('얼음','불꽃','냉동빔','화염광선'))
  move=_STAGED_POKEMON_MOVE_EDGES.prepare(self.e,self.p,self.r.move('move/냉동빔'))
  self.assertEqual((move['id'],move['type'],move['name']),('move/냉동빔','불꽃','화염광선'))
  move,mechanics=CLASS_MOVES.prepare_curse(self.e,self.p,self.t,move,self.r.move_mech(move['id'])[0])
  self.assertEqual(mechanics['effects_exec'],[{'type':'apply_status','status':'화상','target':'target','on_natural_roll_min':19}])
  self.e.d20=lambda:19
  dealt=self.e.use_move(self.p,self.t,'move/냉동빔',set_damage=True)
  self.assertGreater(dealt,0);self.assertIn('화상',self.t.conditions,msg='\n'.join(self.e.log_lines));self.assertNotIn('얼음',self.t.conditions)
  self.assertTrue(any('화염광선' in line for line in self.e.log_lines))

 def test_preserve_decision_keeps_printed_effect_but_uses_new_type_and_name(self):
  self.p.spec['moves']=['move/10만볼트'];self.p.moves=['move/10만볼트']
  self.e.gm.observe_move_type_sync(self.p,**self.preserved())
  move=_STAGED_POKEMON_MOVE_EDGES.prepare(self.e,self.p,self.r.move('move/10만볼트'))
  move,mechanics=CLASS_MOVES.prepare_curse(self.e,self.p,self.t,move,self.r.move_mech(move['id'])[0])
  self.assertEqual((move['type'],move['name']),('고스트','스피릿볼트'))
  self.assertEqual(mechanics['effects_exec'],self.r.move_mech(move['id'])[0]['effects_exec'])
  self.e.d20=lambda:19
  self.e.use_move(self.p,self.t,'move/10만볼트',set_damage=True)
  self.assertIn('마비',self.t.conditions)

 def test_one_active_sync_is_atomic_and_forgetting_closes_its_lifetime(self):
  self.e.gm.observe_move_type_sync(self.p,**self.changed())
  before=deepcopy(self.p.spec)
  with self.assertRaisesRegex(ValueError,'forget the active'):
   self.e.gm.observe_move_type_sync(self.p,**self.preserved())
  self.assertEqual(self.p.spec,before)
  MOVES.observe_learning(self.e,self.p,'move/10만볼트',method='tutor',source='feat/기술-가르침',paid_tp=2,
                         replace='move/냉동빔',reason='observed completed replacement tutoring')
  first=self.p.spec[SYNC.KEY]['history'][0]
  self.assertEqual(first['status'],'forgotten');self.assertEqual(first['forgotten_reason'],'observed completed replacement tutoring')
  self.assertNotIn('move/냉동빔',self.p.moves)
  second=self.e.gm.observe_move_type_sync(self.p,**self.preserved())
  self.assertEqual(second['status'],'active');self.assertEqual(SYNC.active(self.r,self.p.spec)['id'],'spirit-bolt')

 def test_snapshot_durable_restore_and_corruption_validation(self):
  self.e.gm.observe_move_type_sync(self.p,**self.changed())
  self.e.gm.snapshot('synced');self.e.gm.restore('synced')
  blob=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
  restored=Engine.import_state(self.r,blob)
  actor=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
  move=_STAGED_POKEMON_MOVE_EDGES.prepare(restored,actor,self.r.move('move/냉동빔'))
  self.assertEqual((move['type'],move['name']),('불꽃','화염광선'))
  actor.spec[SYNC.KEY]['history'][0]['synced_name']='냉동빔'
  with self.assertRaisesRegex(ValueError,'projection changed'):MOVES.validate_actor(actor)

 def test_invalid_or_structurally_different_effect_decisions_do_not_commit(self):
  before=deepcopy(self.p.spec)
  bad=self.changed(effect_decision={'mode':'replace','reason':'unsafe structural change',
      'effects_exec':[{'type':'set_weather','weather':'sunny','rounds':5}]})
  with self.assertRaisesRegex(ValueError,'effect kind'):self.e.gm.observe_move_type_sync(self.p,**bad)
  self.assertEqual(self.p.spec,before)
  missing=self.changed(application_id='missing-review',power_review='')
  with self.assertRaisesRegex(ValueError,'power review'):self.e.gm.observe_move_type_sync(self.p,**missing)
  self.assertEqual(self.p.spec,before)


if __name__=='__main__':unittest.main()
