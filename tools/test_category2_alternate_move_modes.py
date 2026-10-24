"""Direct contract tests for the reviewed alternate-type Move family."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest

STAGE=Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]

# Seed all staged replacements before engine.py promotes its canonical folder.
import alternate_move_modes as ALTERNATE
import effects as _STAGED_EFFECTS
import effect_contracts as _STAGED_EFFECT_CONTRACTS
import event_effects as _STAGED_EVENT_EFFECTS
import effects_ext as _STAGED_EFFECTS_EXT
import gm_state as _STAGED_GM_STATE
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid


class AlternateMoveModeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')

 def setUp(self):
  self.e=Engine(self.r,seed=49214)
  self.e.grid=Grid(30,30)
  self.p=Combatant(self.r,build_pokemon(self.r,'파이어-가라르',30,
      moves=['move/타오르는분노','move/천둥차기'],abilities=['심록']))
  self.t=Combatant(self.r,build_pokemon(self.r,'이상해씨',25,
      moves=['move/몸통박치기'],abilities=['심록'],side='wild'))
  self.p.pos=(1,1);self.t.pos=(2,1)
  self.e.gm.add_combatant(self.p);self.e.gm.add_combatant(self.t)
  self.e.start_round([self.p,self.t]);self.e.start_of_turn(self.p,initiative_count=20)

 def _observed_types(self):
  seen=[];original=self.e.type_multiplier
  def observe(move_type,target):
   seen.append(move_type);return original(move_type,target)
  self.e.type_multiplier=observe
  return seen

 def test_exact_completed_sources_and_shared_policy(self):
  registry=json.loads((ROOT/'data/verification/category2-csv-abilities-moves-status.json').read_text(encoding='utf-8'))
  ids={'C2CSV-MOVE-R0049','C2CSV-MOVE-R0214','C2CSV-MOVE-R0673'}
  rows={row['row_id']:row for row in registry['rows'] if row['row_id'] in ids}
  self.assertEqual(set(rows),ids)
  self.assertTrue(all(rows[key]['category2_status']=='implemented' for key in {'C2CSV-MOVE-R0049','C2CSV-MOVE-R0214'}))
  policy=ALTERNATE.policy(self.r)
  self.assertEqual({row['clause_id'] for row in policy['moves'].values()},ids)
  self.assertEqual(policy['moves']['move/타오르는분노']['source_row_sha256'],rows['C2CSV-MOVE-R0049']['source_row_sha256'])
  self.assertEqual(policy['moves']['move/천둥차기']['source_row_sha256'],rows['C2CSV-MOVE-R0214']['source_row_sha256'])
  self.assertEqual(policy['moves']['move/얼어붙는시선']['source_row_sha256'],rows['C2CSV-MOVE-R0673']['source_row_sha256'])

 def test_default_printed_type_and_secondary_effect_are_preserved(self):
  seen=self._observed_types();self.e.d20=lambda:17
  dealt=self.e.use_move(self.p,self.t,'move/타오르는분노',set_damage=True)
  self.assertGreater(dealt,0);self.assertIn('악',seen);self.assertNotIn('불꽃',seen)
  self.assertIn('풀죽음',self.t.conditions,msg='\n'.join(self.e.log_lines))
  self.assertEqual(ALTERNATE.status(self.p,'move/타오르는분노'),[])

 def test_selected_alternate_type_is_consumed_by_a_miss(self):
  receipt=self.e.gm.choose_alternate_move_type(self.p,'move/타오르는분노','불꽃',reason='player selects the optional Fire mode')
  self.e.d20=lambda:1
  dealt=self.e.use_move(self.p,self.t,'move/타오르는분노')
  self.assertEqual(dealt,0)
  status=ALTERNATE.status(self.p,'move/타오르는분노')
  self.assertEqual((status[0]['id'],status[0]['status'],status[0]['use']['actual_type']),(receipt['id'],'used','불꽃'))
  self.assertTrue(any('타입 선택 사용: 악 → 불꽃' in line for line in self.e.log_lines))
  with self.assertRaisesRegex(ValueError,'already selected or used'):
   self.e.gm.choose_alternate_move_type(self.p,'move/타오르는분노','불꽃',reason='illegal second use')

 def test_thunderous_kick_uses_electric_and_keeps_defense_loss(self):
  self.e.gm.choose_alternate_move_type(self.p,'move/천둥차기','전기',reason='player selects the optional Electric mode')
  seen=self._observed_types();self.e.d20=lambda:10
  before=self.t.stages['def'];dealt=self.e.use_move_on(self.p,self.t,'move/천둥차기',self.e.everyone)
  self.assertGreater(dealt,0);self.assertIn('전기',seen)
  self.assertEqual(self.t.stages['def'],before-1,msg='\n'.join(self.e.log_lines))

 def test_independent_per_move_scene_budget_and_scene_expiry(self):
  self.e.gm.choose_alternate_move_type(self.p,'move/타오르는분노','불꽃',reason='first optional mode')
  self.e.gm.choose_alternate_move_type(self.p,'move/천둥차기','전기',reason='independent optional mode')
  self.e.d20=lambda:1;self.e.use_move(self.p,self.t,'move/타오르는분노')
  self.assertEqual(self.p.move_uses.get('move/타오르는분노'),1)
  self.assertIsNone(ALTERNATE.history(self.p)[1]['use'])
  self.e.end_of_turn(self.p)
  self.e.end_scene([self.p,self.t])
  self.assertEqual(ALTERNATE.status(self.p,'move/천둥차기')[0]['status'],'expired')
  fresh=self.e.gm.choose_alternate_move_type(self.p,'move/타오르는분노','불꽃',reason='new scene refresh')
  self.assertEqual(fresh['scene'],1)

 def test_snapshot_json_restore_and_tamper_rejection(self):
  self.e.gm.choose_alternate_move_type(self.p,'move/타오르는분노','불꽃',reason='durable pending choice')
  self.e.gm.snapshot('alternate-pending');self.e.gm.restore('alternate-pending')
  blob=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
  restored=Engine.import_state(self.r,blob)
  actor=next(c for c in restored.everyone if c.entity_id==self.p.entity_id)
  target=next(c for c in restored.everyone if c.entity_id==self.t.entity_id)
  restored.d20=lambda:1;restored.use_move(actor,target,'move/타오르는분노')
  self.assertEqual(ALTERNATE.status(actor,'move/타오르는분노')[0]['status'],'used')
  actor.spec[ALTERNATE.KEY]['history'][0]['source_row_sha256']='tampered'
  with self.assertRaisesRegex(ValueError,'provenance changed'):ALTERNATE.validate_actor(actor)

 def test_invalid_choice_is_atomic(self):
  before=deepcopy(self.p.spec)
  with self.assertRaisesRegex(ValueError,'differs from the source'):
   self.e.gm.choose_alternate_move_type(self.p,'move/타오르는분노','전기',reason='wrong alternate')
  self.assertEqual(self.p.spec,before)
  stranger=Combatant(self.r,build_pokemon(self.r,'꼬부기',20,moves=['move/몸통박치기'],abilities=['급류'],side='wild'))
  self.e.gm.add_combatant(stranger);before=deepcopy(stranger.spec)
  with self.assertRaisesRegex(ValueError,'currently know'):
   self.e.gm.choose_alternate_move_type(stranger,'move/타오르는분노','불꽃',reason='unlearned Move')
  self.assertEqual(stranger.spec,before)


if __name__=='__main__':unittest.main()
