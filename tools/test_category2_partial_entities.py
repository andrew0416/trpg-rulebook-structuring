"""Partial sheets survive native persistence and cannot invent combat facts."""
from pathlib import Path
from copy import deepcopy
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"engine"),str(ROOT/"tools")]
from engine import Rules,Engine,Combatant
from native_scenario_fixture import assert_rejected_unchanged, assert_rejections_unchanged
import builder,state_fields as F,partial_entities as P

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset="core")
    def setUp(self):
        self.e=Engine(self.r,37)
        self.a=Combatant(self.r,builder.build_trainer(self.r,"known",5,{s:5 for s in F.STATS},pos=(2,2)))
        self.e.everyone=self.e.gm.everyone=[self.a]
    def test_npc_unknown_facts_are_not_defaults_and_roundtrip(self):
        v=self.e.gm.observe_partial_entity(name="shopkeeper",actor_kind="trainer",known={"skills":{"기술학":"숙련"}},reason="only required NPC skill is established")
        uid=v["entity_id"]
        self.assertIn("level",v["unknown_fields"])
        self.assertIn("stats",v["unknown_fields"])
        self.assertEqual(v["location"],{"kind":"unknown"})
        self.assertIsNone(P.skill(self.e,uid,"곡예"))
        self.assertEqual(P.skill(self.e,uid,"기술학")[2],4)
        loaded=Engine.import_state(self.r,self.e.export_state())
        self.assertEqual(P.project(loaded,uid),P.project(self.e,uid))
        self.e.validate_state()
    def test_hp_only_part_has_actual_parent_and_observed_hp(self):
        parent=self.e.gm.observe_partial_entity(name="giant body",actor_kind="pokemon",known={"description":"a giant living ecosystem"},reason="GM body observation")
        part=self.e.gm.observe_partial_entity(name="weak seal",actor_kind="object",parent_id=parent["entity_id"],known={"hp":12},reason="GM gave this weak part HP alone")
        uid=part["entity_id"];actual=self.e._partial_entities[uid]
        self.assertFalse(part["destroyed"])
        self.assertIn("max_hp",part["unknown_fields"])
        self.a.spec["observed_part"]=actual
        self.e.gm.snapshot("before break")
        self.e.gm.update_partial_entity(uid,facts={"hp":0},reason="resolved external damage observed")
        self.assertTrue(P.project(self.e,uid)["destroyed"])
        self.assertIs(self.a.spec["observed_part"],actual)
        self.e.gm.restore("before break")
        self.assertEqual(P.project(self.e,uid)["known"]["hp"],12)
        self.assertIs(self.a.spec["observed_part"],self.e._partial_entities[uid])
        loaded=Engine.import_state(self.r,self.e.export_state())
        self.assertIs(loaded.everyone[0].spec["observed_part"],loaded._partial_entities[uid])
        self.assertEqual(loaded._partial_entities[uid]["parent_id"],parent["entity_id"])
    def test_combat_rejection_is_before_resources_rng_or_state_mutation(self):
        v=self.e.gm.observe_partial_entity(name="witness",actor_kind="trainer",reason="NPC has no combat sheet")
        row=self.e._partial_entities[v["entity_id"]]
        before=self.e.rng.getstate();hp=self.a.hp;known=deepcopy(row)
        for action in (lambda:self.e.take_damage(row,5),lambda:self.e.heal(row,5),
                       lambda:self.e.use_move(self.a,row,"struggle"),
                       lambda:self.e.use_move(row,self.a,"struggle"),
                       lambda:self.e.use_move_on(self.a,row,"struggle",[self.a]),
                       lambda:self.e._accuracy_check_native(self.a,row,self.r.move("struggle"))):
            with self.assertRaisesRegex(ValueError,"missing stats are unknown"):action()
        self.assertEqual(self.e.rng.getstate(),before)
        self.assertEqual(self.a.hp,hp)
        self.assertEqual(row,known)
    def test_move_wrappers_reject_partial_before_pending_or_feature_inspection(self):
        parent=self.e.gm.observe_partial_entity(name="witness",actor_kind="trainer",reason="NPC has no combat sheet")
        part=self.e.gm.observe_partial_entity(name="seal",actor_kind="object",parent_id=parent["entity_id"],known={"hp":12},reason="HP-only weak part")
        actions=[]
        for view in (parent,part):
            row=self.e._partial_entities[view["entity_id"]]
            for mid in ("struggle","move/사이코키네시스","move/텔레키네시스"):
                actions.extend((
                    lambda row=row,mid=mid:self.e.use_move(row,self.a,mid),
                    lambda row=row,mid=mid:self.e.use_move(self.a,row,mid),
                    lambda row=row,mid=mid:self.e.use_move_on(row,self.a,mid,[self.a]),
                    lambda row=row,mid=mid:self.e.use_move_on(self.a,row,mid,[self.a]),
                ))
        assert_rejections_unchanged(self.e,actions,reason_pattern="missing stats are unknown")
    def test_public_accuracy_and_setup_gate_both_partial_kinds_before_clock(self):
        from grid import Grid
        import setup_move_state as SETUP
        self.e.grid=Grid(20,12)
        self.assertFalse(hasattr(self.a,"budget"))
        parent=self.e.gm.observe_partial_entity(name="giant",actor_kind="pokemon",reason="observed parent")
        part=self.e.gm.observe_partial_entity(name="seal",actor_kind="object",parent_id=parent["entity_id"],known={"hp":12},reason="HP-only weak part")
        actions=[]
        for view in (parent,part):
            row=self.e._partial_entities[view["entity_id"]]
            actions.extend((
                lambda row=row:self.e.accuracy_check(self.a,row,self.r.move("struggle")),
                lambda row=row:self.e.accuracy_check(row,self.a,self.r.move("struggle")),
                lambda row=row:SETUP.require_targetable(self.e,self.a,row,"struggle"),
                lambda row=row:self.e.use_setup_move_on(self.a,row,"move/공중날기",[self.a]),
            ))
        assert_rejections_unchanged(self.e,actions,reason_pattern="missing stats are unknown")
    def test_rejection_template_detects_fabricated_turn_budget_without_restoring(self):
        self.assertFalse(hasattr(self.a,"budget"))
        def fabricate_then_reject():
            self.a.budget=None
            raise ValueError("fixture rejection")
        with self.assertRaisesRegex(AssertionError,"changed engine state or RNG"):
            assert_rejected_unchanged(self.e,fabricate_then_reject,reason_pattern="^fixture rejection$")
        self.assertTrue(hasattr(self.a,"budget"))
        self.assertIsNone(self.a.budget)
    def test_learned_setup_and_active_gmax_reject_partial_before_clock(self):
        from native_scenario_fixture import prepare_setup_move_scene,prepare_gmax_scene
        import gmax_moves as GMAX
        rules=Rules(str(ROOT),ruleset='all')
        setup,user,parent=prepare_setup_move_scene(rules)
        view=setup.gm.observe_partial_entity(name="seal",actor_kind="object",parent_id=parent.entity_id,
                                               known={"hp":12},reason="actual setup target")
        target=setup._partial_entities[view["entity_id"]]
        assert_rejected_unchanged(setup,
            lambda:setup.use_setup_move_on(user,target,'move/공중날기',setup.everyone,setup_options={}),
            reason_pattern="missing stats are unknown")

        declaration=next(row for row in GMAX.declarations(rules) if row['clause_id']=='C2CSV-MOVE-R1016')
        world,actor,parent,base,move=prepare_gmax_scene(rules,declaration)
        view=world.gm.observe_partial_entity(name="boss seal",actor_kind="object",parent_id=parent.entity_id,
                                             known={"hp":12},reason="actual G-Max target")
        target=world._partial_entities[view["entity_id"]]
        assert_rejected_unchanged(world,
            lambda:world.use_gmax_move_on(actor,target,base,move,[actor,parent]),
            reason_pattern="missing stats are unknown")
    def test_invalid_facts_parents_and_duplicate_actor_ids_are_atomic(self):
        with self.assertRaises(ValueError):self.e.gm.observe_partial_entity(name="bad",actor_kind="object",known={"hp":3},parent_id="missing",reason="bad reference")
        self.assertFalse(getattr(self.e,"_partial_entities",{}))
        v=self.e.gm.observe_partial_entity(name="minimal",actor_kind="trainer",entity_id="npc-one",reason="known identity")
        with self.assertRaises(ValueError):self.e.gm.update_partial_entity(v["entity_id"],facts={"level":True},reason="invalid")
        self.assertEqual(P.project(self.e,"npc-one")["known"],{})
        spec=builder.build_trainer(self.r,"collision",5,{s:5 for s in F.STATS});spec["id"]="npc-one"
        with self.assertRaises(ValueError):self.e.gm.add_combatant(Combatant(self.r,spec))
        self.assertEqual(len(self.e.everyone),1)

if __name__=="__main__":unittest.main(verbosity=2)
