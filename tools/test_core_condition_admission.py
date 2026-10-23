"""Actual Trapped admission at paid recall/switch and source switch effects."""
from pathlib import Path
from copy import deepcopy
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'data').exists():ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_reuse_partial_party as FIX
from state_codec import dump_engine,load_engine
import effects_ext as EXT

class RecallTests(unittest.TestCase):
    setUpClass=classmethod(FIX.Tests.setUpClass.__func__)
    setup_world=FIX.Tests.setup_world
    switch=FIX.Tests.switch

    def trap(self,actor):
        self.e.gm.add_condition(actor,'수렁',force=False,reason='actual observed Trapped')

    def test_native_single_recall_and_switch_block_before_payment_in_both_formats(self):
        for mode in ('league','full_contact'):
            for switching in (False,True):
                with self.subTest(mode=mode,switching=switching):
                    self.setup_world(mode);self.trap(self.p);before=dump_engine(self.e)
                    with self.assertRaisesRegex(ValueError,'Trapped'):
                        if switching:self.switch()
                        else:self.e.act_on_party(self.a,recall=[self.p],request_id='recall',reason='actual recall')
                    self.assertEqual(dump_engine(self.e),before)
                    self.e.cure_status(self.p,'수렁')
                    if switching:self.switch()
                    else:self.e.act_on_party(self.a,recall=[self.p],request_id='recall',reason='actual recall')
                    self.assertFalse(self.p.on_field)
                    self.assertEqual(self.a.budget['standard' if switching else 'shift'],0)

    def test_pair_recall_rejects_all_if_second_subject_is_trapped(self):
        self.setup_world();self.q.on_field=True;self.trap(self.q);before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'Trapped'):
            self.e.act_on_party(self.a,recall=[self.p,self.q],request_id='pair',reason='actual paired recall')
        self.assertEqual(dump_engine(self.e),before)

    def test_restored_actual_condition_still_blocks_and_cure_allows_exactly_one_payment(self):
        self.setup_world();self.trap(self.p)
        checkpoint=self.e.gm.snapshot()
        self.e.cure_status(self.p,'수렁');self.e.gm.restore(checkpoint)
        self.assertIn('수렁',self.p.conditions)
        self.e=load_engine(self.r,json.loads(json.dumps(dump_engine(self.e))))
        self.a,self.p,self.q,self.z=self.e.everyone
        before=dump_engine(self.e)
        with self.assertRaisesRegex(ValueError,'Trapped'):self.switch()
        self.assertEqual(dump_engine(self.e),before)
        self.e.cure_status(self.p,'수렁');row=self.switch();paid=dump_engine(self.e)
        self.assertEqual(self.switch(),row);self.assertEqual(dump_engine(self.e),paid)

    def test_ghost_pokemon_immunity_flows_through_actual_application_and_recall(self):
        self.setup_world();self.p.types=['고스트'];self.trap(self.p)
        self.assertNotIn('수렁',self.p.conditions)
        self.switch();self.assertFalse(self.p.on_field)

    def test_source_switch_effect_blocks_both_kinds_and_preserves_explicit_bypass(self):
        for kind in ('trainer','pokemon'):
            with self.subTest(kind=kind):
                self.setup_world();subject=self.a if kind=='trainer' else self.p
                self.trap(subject);self.trap(self.z)
                def state():
                    return deepcopy(([(c.on_field,c.hp,c.conditions,getattr(c,'budget',None),c.spec) for c in self.e.everyone],self.e.rng.getstate(),self.e.elapsed_seconds))
                before=state();logs=len(self.e.log_lines)
                self.assertIsNotNone(EXT.h_switch_out(self.e,subject,self.q,{},{}))
                self.assertEqual(state(),before)
                self.assertEqual(len(self.e.log_lines),logs+1)
                self.assertIn('수렁 상태여서',self.e.log_lines[-1])
                EXT.h_switch_out(self.e,subject,self.q,{'ignore_trapped':True},{})
                self.assertFalse(subject.on_field);self.assertIn('수렁',self.z.conditions)

    def test_battle_contest_recall_rolls_back_its_turn_payment(self):
        import test_category2_battle_contest as FIXTURE
        from contest import ContestRules
        fixture=FIXTURE.BattleContestTests()
        fixture.rules=self.r;fixture.contest_rules=ContestRules(str(ROOT),ruleset='core')
        e,contest,trainers,teams,cid=fixture.fixture()
        FIXTURE.BATTLE.begin_round(e,cid)
        outgoing,incoming=teams[0][:2]
        e.start_of_turn(outgoing)
        e.gm.add_condition(outgoing,'수렁',force=False,reason='actual observed Trapped')
        before=dump_engine(e)
        with self.assertRaisesRegex(ValueError,'Trapped'):
            FIXTURE.BATTLE.switch(e,cid,trainers[0],outgoing,incoming)
        self.assertEqual(dump_engine(e),before)

    def test_held_item_recall_rolls_back_actual_item_consumption(self):
        import test_category2_csv_remaining_item_contracts as FIXTURE
        fixture=FIXTURE.RemainingCsvItemContractTests();fixture.r=self.r
        holder=fixture.pokemon('held Trapped subject');attacker=fixture.pokemon('actual attacker')
        e=fixture.fixture(holder,attacker)
        fixture.equip(e,holder,'actual/trapped-button','item/탈출버튼')
        FIXTURE.PHYSICAL.after_attack_damage(e,attacker,holder,self.r.move('move/몸통박치기'),fixture.hit_receipt())
        e.gm.add_condition(holder,'수렁',force=False,reason='actual observed Trapped')
        before=dump_engine(e)
        with self.assertRaisesRegex(ValueError,'Trapped'):
            FIXTURE.PHYSICAL.resolve_pending(e,holder,'eject_button',accept=True)
        self.assertEqual(dump_engine(e),before)

if __name__=='__main__':unittest.main()
