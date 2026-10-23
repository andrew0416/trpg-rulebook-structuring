"""Actual template state, native consumer boundary, and graph round trips."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "data").is_dir() or not (ROOT / "output").is_dir():
    ROOT = Path(r"D:\trpg-rulebook-structuring\ptk-structure-experiment")
sys.path[:0] = [str(ROOT / "engine")]
from engine import Rules, Engine, Combatant
import builder, state_fields as S, actor_templates as T, effects_ext as EXT

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset="core")
    def setUp(self):
        self.e = Engine(self.r, 992)
        self.trainer = Combatant(self.r, builder.build_trainer(self.r,"observer",5,{s:5 for s in S.STATS},pos=(1,1)))
        self.p = Combatant(self.r, builder.build_pokemon(self.r,"꼬렛",10,pos=(2,1)))
        self.p.side = "wild"
        self.e.everyone = self.e.gm.everyone = [self.trainer,self.p]
    def configure(self,kind="boss",bars=3):
        return self.e.gm.set_encounter_template(self.p,kind=kind,total_bars=bars,
             action_slots=[{"id":"a","initiative":20},{"id":"b","initiative":15}],
             reason="GM observes selected encounter template",
             member_count_or_band="25_to_40" if kind=="swarm" else None)
    def test_boss_bar_count_and_actions_are_independent(self):
        self.configure()
        state=deepcopy(self.p.spec["encounter_template"]);state["hp_bars"]["spent"]=2
        state["bar_transition_receipts"]=[{"source_id":"C11-126","bar":0},{"source_id":"C11-126","bar":1}]
        self.e.gm.record_encounter_template(self.p,state=state,reason="GM confirmed prior damage",request_id="observed-1")
        view=T.projection(self.p)
        self.assertEqual((view["remaining_bars"],view["action_count"]),(1,2))
        self.assertFalse(view["capture_immune"])
        self.assertEqual(view["current_hp"],self.p.hp)
        revision=self.p._state_revision
        self.e.gm.record_encounter_template(self.p,state=state,reason="GM confirmed prior damage",request_id="observed-1")
        self.assertEqual(self.p._state_revision,revision)
        self.e.gm.set_hp(self.p,value=10,reason="confirmed current bar")
        self.assertEqual(T.projection(self.p)["current_hp"],10)
    def test_swarm_size_and_current_multiplier_not_synonyms(self):
        self.configure("swarm")
        state=deepcopy(self.p.spec["encounter_template"]);state["hp_bars"]["spent"]=1
        with self.assertRaises(ValueError):
            T.record(self.e,self.p,state=state,reason="inconsistent input",request_id="bad")
        self.assertEqual(T.projection(self.p)["remaining_bars"],3)
        state["multiplier"]=2
        T.record(self.e,self.p,state=state,reason="observed bar loss",request_id="valid")
        self.assertEqual(T.projection(self.p)["member_count_or_band"],"25_to_40")
        self.assertEqual(T.projection(self.p)["multiplier"],2)
        with self.assertRaises(ValueError): self.e.gm.set_injuries(self.p,value=1,reason="invalid injury")
        EXT.h_injury(self.e,self.p,self.p,{"value":1,"target":"self"},{})
        self.assertEqual(self.p.injuries,0)
    def test_all_swarm_bars_can_be_exhausted(self):
        self.configure("swarm")
        self.e.gm.set_hp(self.p,value=0,reason="GM observes the final bar exhausted")
        state=deepcopy(self.p.spec["encounter_template"])
        state["hp_bars"]["spent"]=3;state["multiplier"]=0
        T.record(self.e,self.p,state=state,reason="final bar lost",request_id="defeat")
        view=T.projection(self.p)
        self.assertEqual(view["remaining_bars"],0)
        self.assertIsNone(view["current_capacity"])
        self.assertTrue(self.p.fainted)
        self.e.validate_state()

    def test_native_capture_immunity_and_supported_boss_transitions(self):
        self.configure()
        self.trainer.spec["items"]={"몬스터볼":1}
        before_rng=self.e.rng.getstate();hp=self.p.hp
        self.assertFalse(self.e.throw_ball(self.trainer,self.p))
        self.assertEqual(self.trainer.spec["items"],{"몬스터볼":1})
        self.assertEqual((self.p.hp,self.e.rng.getstate()),(hp,before_rng))
        self.e.take_damage(self.p,1)
        self.e.lose_hp(self.p,1)
        self.assertEqual(self.p.hp,hp-2)
        self.e.start_round([self.trainer,self.p])
        self.assertEqual(T.projection(self.p)["transition_automation"],"native_boss_transition")
        self.e.start_of_turn(self.trainer,initiative_count=25)
        before=T.projection(self.p)
        with patch.object(Engine,"d20",return_value=20):
            self.assertTrue(self.e.use_move(self.trainer,self.p,"struggle",situational=100,set_damage=True))
        after=T.projection(self.p)
        self.assertTrue(after["remaining_bars"]<before["remaining_bars"] or self.p.hp<before["current_hp"])
        self.assertEqual(self.trainer.budget["standard"],0)
        # Full bar/overflow policy remains covered by the native BossTransitionTests.
        self.assertTrue(self.e.validate_state()["valid"])
    def test_slot_binding_validation_and_roundtrip(self):
        self.configure()
        state=deepcopy(self.p.spec["encounter_template"])
        state["condition_bindings"]={"마비":{"source_id":"C11-130","slot_id":"missing","variant":"ordinary"}}
        with self.assertRaises(ValueError): T.record(self.e,self.p,state=state,reason="bad slot",request_id="bad")
        state["condition_bindings"]["마비"]["slot_id"]="b"
        T.record(self.e,self.p,state=state,reason="GM observes bound condition",request_id="condition")
        loaded=Engine.import_state(self.r,self.e.export_state())
        target=next(c for c in loaded.everyone if c.entity_id==self.p.entity_id)
        self.assertEqual(T.projection(target),T.projection(self.p))
        loaded.validate_state()
    def test_multipart_real_parts_share_parent_not_hp_or_location(self):
        spec=builder.build_pokemon(self.r,"꼬렛",10,pos=(7,8))
        spec["abilities"]=[]  # Imported part; feature acquisition belongs to category 6.
        q=Combatant(self.r,spec)
        self.e.gm.add_combatant(q)
        self.e.gm.set_multipart_entity(parent_id="multipart-1",part_ids=[self.p.entity_id,q.entity_id],reason="GM observes two parts")
        self.e.gm.set_hp(q,value=3,reason="only this part was injured")
        self.e.gm.snapshot("parts")
        view=T.multipart_projection(self.e,"multipart-1")
        self.assertEqual([x["hp"] for x in view["parts"]],[self.p.hp,3])
        self.assertNotEqual(view["parts"][0]["location"],view["parts"][1]["location"])
        self.e.validate_state()
        loaded=Engine.import_state(self.r,self.e.export_state())
        self.assertEqual(T.multipart_projection(loaded,"multipart-1"),view)
        self.e.gm.set_hp(q,value=20,reason="temporary edit")
        self.e.gm.restore("parts")
        self.assertEqual(T.multipart_projection(self.e,"multipart-1"),view)
        before=deepcopy(self.e._physical_objects)
        with self.assertRaises(ValueError): T.multipart(self.e,parent_id="multipart-2",part_ids=[q.entity_id,self.p.entity_id],reason="duplicate membership")
        self.assertEqual(self.e._physical_objects,before)

    def test_swarm_single_identity_and_all_five_source_size_bands_survive_restore(self):
        expected={1:"less_than_a_dozen",2:"15_to_25",3:"25_to_40",4:"40_to_60",5:"60_plus"}
        for bars,band in expected.items():
            with self.subTest(bars=bars):
                self.setUp()
                view=self.configure("swarm",bars)
                self.assertEqual((view["entity_id"],view["initial_size_band"],view["current_size_band"]),(self.p.entity_id,band,band))
                self.assertEqual(len(self.e.gm.everyone),2)
                self.assertEqual(view["current_hp"],self.p.hp)
                state=deepcopy(self.p.spec["encounter_template"])
                state["hp_bars"]["spent"]=1;state["multiplier"]=bars-1
                if bars==1:self.e.gm.set_hp(self.p,value=0,reason="observed final bar")
                self.e.gm.record_encounter_template(self.p,state=state,reason="observed lost bar",request_id="bar:1")
                self.e.gm.snapshot("swarm")
                loaded=Engine.import_state(self.r,self.e.export_state())
                self.e.gm.restore("swarm")
                for engine in (self.e,loaded):
                    actor=next(c for c in engine.gm.everyone if c.entity_id==self.p.entity_id)
                    view=T.projection(actor)
                    self.assertEqual((view["initial_size_band"],view["current_size_band"]),(band,expected.get(bars-1)))
                    self.assertEqual(view["member_count_or_band"],"25_to_40")
                    self.assertEqual(view["transition_automation"],"native_swarm_transition")
                    self.assertTrue(engine.validate_state()["valid"])

    def test_actual_multipart_parts_keep_species_stats_moves_abilities_and_native_initiative(self):
        spec=builder.build_pokemon(self.r,"꼬렛",10,pos=(7,8),abilities=[],
                                  extra={"id":"pokemon/independent-part"})
        q=Combatant(self.r,spec);self.e.gm.add_combatant(q)
        self.e.gm.set_stat(q,"spe",value=self.p.stats["spe"]+5,reason="GM selected distinct part stats")
        self.e.gm.set_move(q,"move/불꽃세례",True,reason="GM selected this part's independent move")
        self.e.gm.set_multipart_entity(parent_id="actual-parts",part_ids=[self.p.entity_id,q.entity_id],reason="GM selected independent parts")
        order=self.e.initiative([self.p,q])
        self.assertEqual(order,[q,self.p])
        self.assertNotEqual(self.e.initiative_value(self.p).value,self.e.initiative_value(q).value)
        baseline=self.p.hp
        self.e.take_damage(q,3)
        self.assertEqual(self.p.hp,baseline)
        view=T.multipart_projection(self.e,"actual-parts")
        for part,actor in zip(view["parts"],(self.p,q)):
            self.assertEqual(part["moves"],actor.moves)
            self.assertEqual(part["abilities"],actor.abilities)
            self.assertEqual(actor.spec["species"],self.p.spec["species"])
        self.assertIn("move/불꽃세례",view["parts"][1]["moves"])
        self.assertNotIn("move/불꽃세례",view["parts"][0]["moves"])
        self.assertEqual(view["parts"][1]["abilities"],[])
        loaded=Engine.import_state(self.r,self.e.export_state())
        self.assertEqual(T.multipart_projection(loaded,"actual-parts"),view)
        restored={c.entity_id:c for c in loaded.everyone}
        self.assertEqual([c.entity_id for c in loaded.initiative([restored[self.p.entity_id],restored[q.entity_id]])],
                         [q.entity_id,self.p.entity_id])
        self.assertEqual(restored[q.entity_id].stats["spe"],q.stats["spe"])

    def test_template_and_multipart_late_publication_failures_preserve_graph_and_rng(self):
        before=self.e.export_state();original=self.p.spec
        with patch.object(type(self.e.gm),"_rec",side_effect=ValueError("injected late publication")):
            with self.assertRaisesRegex(ValueError,"late publication"):self.configure("swarm")
        self.assertEqual(before,self.e.export_state());self.assertIs(self.p.spec,original)
        self.configure("swarm")
        state=deepcopy(self.p.spec["encounter_template"]);state["hp_bars"]["spent"]=1;state["multiplier"]=2
        before=self.e.export_state()
        with patch.object(type(self.e.gm),"_rec",side_effect=ValueError("injected late publication")):
            with self.assertRaisesRegex(ValueError,"late publication"):
                self.e.gm.record_encounter_template(self.p,state=state,reason="observed bar loss",request_id="not-published")
        self.assertEqual(before,self.e.export_state());self.assertIs(self.p.spec,original)
        spec=builder.build_pokemon(self.r,"꼬렛",10,abilities=[],extra={"id":"pokemon/rollback-part"})
        q=Combatant(self.r,spec);self.e.gm.add_combatant(q);before=self.e.export_state()
        with patch.object(type(self.e.gm),"_rec",side_effect=ValueError("injected late publication")):
            with self.assertRaisesRegex(ValueError,"late publication"):
                self.e.gm.set_multipart_entity(parent_id="not-published",part_ids=[self.p.entity_id,q.entity_id],reason="actual multipart observation")
        self.assertEqual(before,self.e.export_state());self.assertNotIn("multipart_parent_id",q.spec)

if __name__=="__main__": unittest.main(verbosity=2)
