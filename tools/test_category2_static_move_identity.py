"""Exact learned Static Move identity and native activation boundaries."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
import csv,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from grid import Grid
import frequency as FREQ
import encounter
import ptk_structure as EXTRACT

class StaticMoveIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')
    def setUp(self):
        self.e=Engine(self.r,91);self.e.grid=Grid(8,8)
        self.a=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,name='static owner',
            moves=['move/조이기','move/몸통박치기'],extra={'pos':(2,2),'side':'party'}))
        self.b=Combatant(self.r,build_pokemon(self.r,'이상해씨',20,name='target',
            moves=['move/몸통박치기'],extra={'pos':(3,2),'side':'opponent'}))
        self.e.gm.add_combatant(self.a);self.e.gm.add_combatant(self.b)
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)

    def test_exact_static_source_survives_extraction_while_other_inserted_rows_stay_excluded(self):
        source=ROOT/'input/db/moves.csv'
        with source.open(encoding='utf-8-sig',newline='') as f:cells=list(csv.reader(f))[446]
        self.assertEqual(sha256(json.dumps(cells,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
                         '8397df88c5fb59d01b022b4d8157eadc56391585d803fa011795105fa2d54123')
        records,failed=EXTRACT.parse_moves(str(source))
        static=[row for row in records if row['class']=='항상']
        self.assertEqual([row['id'] for row in static],['move/조이기'])
        row=static[0]
        self.assertEqual((row['name'],row['eng'],row['effect'],row['frequency']),
                         (cells[0],cells[22],cells[7],cells[4]))
        self.assertEqual(row['_source']['record_span'],[447,447])
        saved=json.loads((ROOT/'output/entities/moves.json').read_text(encoding='utf-8'))
        self.assertEqual([r for r in saved if r['id']==row['id']],[row])
        self.assertTrue(any(r.get('reason')=='inserted_other_kind' for r in failed))
        self.assertFalse(any(r.get('id')==row['id'] for r in failed))
        self.assertEqual(self.r.move_id('조이기'),row['id'])
        self.assertEqual(self.r._selected_rule(row['id']),row['id'])

    def test_learned_static_move_restores_and_is_excluded_from_active_choices(self):
        self.assertIn('move/조이기',self.a.moves)
        before=deepcopy(self.a.spec)
        self.assertFalse(FREQ.move_allowed(self.e,self.a,'move/조이기')[0])
        self.assertEqual(self.a.spec,before)
        active=encounter.usable_moves(self.e,self.a)
        self.assertNotIn('move/조이기',active);self.assertIn('move/몸통박치기',active)
        saved=json.loads(json.dumps(self.e.export_state(),ensure_ascii=False))
        restored=Engine.import_state(Rules(ROOT,ruleset='core'),saved)
        actor=next(c for c in restored.everyone if c.entity_id==self.a.entity_id)
        self.assertIn('move/조이기',actor.moves)
        self.assertNotIn('move/조이기',encounter.usable_moves(restored,actor))

    def test_static_move_cannot_execute_through_single_free_or_multi_target_entrypoints(self):
        before=self.e.export_state()
        for kind in ('single','free','multi'):
            with self.subTest(entrypoint=kind):
                with self.assertRaisesRegex(ValueError,'static learned Move'):
                    if kind=='multi':self.e.use_move_on(self.a,self.b,'move/조이기',self.e.everyone)
                    else:self.e.use_move(self.a,self.b,'move/조이기',set_damage=True,
                                        count_use=kind!='free',free_action=kind=='free')
                self.assertEqual(self.e.export_state(),before)

if __name__=='__main__':unittest.main()
