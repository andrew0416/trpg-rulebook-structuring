"""F-50 repair: Survival also counts as an Education skill (ch03:130, core-1.05:1598).

Every consumer that asks for "an Education skill" shares skill_modifiers.EDUCATION_SKILLS:
the CSV Blessings Fount of Knowledge (class-data R36) and Ancient Wisdom (R3), the GM's
Pokemon Education assignment and PokeScholar template (ch05:162, 181-184), and the Researcher
Novice Education qualification behind every Field of Study feature (ch04:2066).
Survival stays a physical (Body) skill for category consumers. The same campaign
Education decision gates its native Pokemon pool and backgrounds, with the existing
explicit individual exceptions (Q48; ch05:162 and ch11:257).
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tools")]

from engine import Combatant, Engine, Rules
from builder import build_pokemon, build_trainer
from state_codec import dump_engine, load_engine
import blessing_skill_rules as B
import crafting_activities as CA
import downtime as D
import pokemon_intelligence as I
import pokemon_skill_profiles as P
import researcher_features as RF
import researcher_fields as RFS
import skill_modifiers as S
import state_fields as F
import test_book_researcher_fields_crafting as CRAFT
from test_category2_blessing_skill_rules_ten import trainer as blessing_trainer

NAMED = ("general education", "medical education", "occult education", "pokemon education", "technology education")
NAMED_KO = ("일반 지식", "의학", "오컬트학", "포켓몬학", "기술학")


class SharedEducationSetTests(unittest.TestCase):
    def test_one_education_set_adds_survival_and_survival_stays_a_body_skill(self):
        line = (ROOT / "input/ch03-skills-edges-feats.md").read_text(encoding="utf-8-sig").splitlines()[129]
        self.assertIn("육체 카테고리의 스킬로 계산함에도 불구하고, 생존은 교육 스킬로도 간주됩니다", line)
        policy = json.loads((ROOT / "data/skill-check-policy.json").read_text(encoding="utf-8-sig"))
        self.assertEqual(S.EDUCATION_SKILLS, frozenset(NAMED + ("survival",)))
        self.assertTrue(S.EDUCATION_SKILLS <= set(policy["skills"]))
        # The reviewed Instruction list (ch03:516-518) already named the same six skills.
        self.assertEqual(set(policy["procedural_edges"]["edge/설명"]["education_skills"]), S.EDUCATION_SKILLS)
        self.assertEqual(policy["skills"]["survival"]["category"], "physical")
        self.assertEqual({policy["skills"][sid]["category"] for sid in NAMED}, {"mental"})


class BlessingSurvivalEducationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="fantasy")

    def setUp(self):
        self.e = Engine(self.rules, seed=916)
        self.a = blessing_trainer(self.rules, "trainer/f50-blessing-a", "F50 Blessing A")
        self.b = blessing_trainer(self.rules, "trainer/f50-blessing-b", "F50 Blessing B")
        self.e.everyone = [self.a, self.b]
        self.e.gm.everyone = self.e.everyone

    def grant(self, gift, patron, actor=None):
        actor = self.a if actor is None else actor
        actor.spec.setdefault("gifts", []).append(gift)
        actor.spec.setdefault("gift_patrons", {})[gift] = patron
        return actor

    def confirm(self, gift, configuration, actor=None):
        return self.e.confirm_blessing_gift(self.a if actor is None else actor, gift,
                                            reason="GM approves this exact acquired CSV Blessing",
                                            configuration=configuration)

    def state(self, actor=None):
        actor = self.a if actor is None else actor
        return deepcopy(actor.spec), self.e.rng.getstate(), list(self.e.log_lines)

    def test_fount_of_knowledge_takes_survival_rerolls_its_ones_and_survives_gm_and_json_restore(self):
        self.grant(B.FOUNT_OF_KNOWLEDGE, "유크시")
        self.confirm(B.FOUNT_OF_KNOWLEDGE, {"education_skills": ["생존", "기술학"]})
        record = self.a.spec[B.CONFIGURATION][B.FOUNT_OF_KNOWLEDGE]
        self.assertEqual(record["values"]["education_skills"], ["survival", "technology education"])
        self.e.rng.seed(1)
        self.assertEqual(self.e.skill_roll(self.a, "생존", fixed=[1, 2, 1]).faces, (2, 2, 5))
        self.assertEqual(self.e.skill_roll(self.a, "의학", fixed=[1, 2, 1]).faces, (1, 2, 1))
        saved = deepcopy(self.a.spec)
        self.e.gm.snapshot("f50-fount")
        del self.a.spec[B.CONFIGURATION][B.FOUNT_OF_KNOWLEDGE]
        self.e.gm.restore("f50-fount", reason="restore the approved Fount choices")
        self.assertEqual(self.a.spec, saved)
        self.e.rng.seed(1)
        self.assertEqual(self.e.skill_roll(self.a, "생존", fixed=[1, 2, 1]).faces, (2, 2, 5))
        payload = json.loads(json.dumps(dump_engine(self.e), ensure_ascii=False))
        loaded = load_engine(self.rules, payload)
        restored = next(x for x in loaded.everyone if x.entity_id == self.a.entity_id)
        self.assertEqual(restored.spec[B.CONFIGURATION], saved[B.CONFIGURATION])
        loaded.rng.seed(1)
        self.assertEqual(loaded.skill_roll(restored, "생존", fixed=[1, 2, 1]).faces, (2, 2, 5))

    def test_fount_still_refuses_non_education_duplicate_and_short_choices_before_writing(self):
        self.grant(B.FOUNT_OF_KNOWLEDGE, "유크시")
        for choice in (["육상", "기술학"], ["통찰", "생존"], ["생존", "Survival"], ["생존"]):
            with self.subTest(choice=choice):
                before = self.state()
                with self.assertRaises(ValueError):
                    self.confirm(B.FOUNT_OF_KNOWLEDGE, {"education_skills": choice})
                self.assertEqual(self.state(), before)
                self.assertNotIn(B.CONFIGURATION, self.a.spec)

    def test_ancient_wisdom_messiah_adds_a_die_to_survival_only_on_an_occult_topic(self):
        self.grant(B.ANCIENT_WISDOM, "뮤")
        self.confirm(B.ANCIENT_WISDOM, {"role": "messiah"})
        occult = self.e.skill_roll(self.a, "생존", fixed=[2] * 4,
                                   skill_context={"purpose": "occult_topic", "reason": "actual occult survival task"})
        ordinary = self.e.skill_roll(self.a, "생존", fixed=[2] * 3)
        athletics = self.e.skill_roll(self.a, "육상", fixed=[2] * 2,
                                      skill_context={"purpose": "occult_topic", "reason": "not an Education skill"})
        self.assertEqual((len(occult.faces), len(ordinary.faces), len(athletics.faces)), (4, 3, 2))
        before = self.state()
        with self.assertRaises(ValueError):
            self.e.skill_roll(self.a, "생존", fixed=[2] * 4, skill_context={"purpose": "occult_topic"})
        self.assertEqual(self.state(), before)
        # The Contractor's +2d6 stays an Occult Education effect; Survival never consumes it.
        self.grant(B.ANCIENT_WISDOM, "뮤", self.b)
        self.confirm(B.ANCIENT_WISDOM, {"role": "contractor"}, self.b)
        self.e.activate_blessing_skill_rule(self.b, B.ANCIENT_WISDOM, reason="Contractor invokes ancient knowledge")
        survival = self.e.skill_roll(self.b, "생존", fixed=[2] * 3,
                                     skill_context={"purpose": "occult_topic", "reason": "actual occult survival task"})
        self.assertEqual(len(survival.faces), 3)
        self.assertEqual(self.b.spec[B.STATE]["activations"][B.ANCIENT_WISDOM]["status"], "pending")

    def test_paragon_body_category_still_includes_survival_and_mind_category_does_not(self):
        self.grant(B.PARAGON, "뮤")
        self.confirm(B.PARAGON, {"role": "messiah", "category": "physical"})
        self.grant(B.PARAGON, "뮤", self.b)
        self.confirm(B.PARAGON, {"role": "messiah", "category": "mental"}, self.b)
        self.assertEqual(self.e.skill_roll(self.a, "생존", fixed=[1] * 3).modifier, 2)
        self.assertEqual(self.e.skill_roll(self.b, "생존", fixed=[1] * 3).modifier, 0)
        self.assertEqual(self.e.skill_roll(self.b, "기술학", fixed=[1] * 3).modifier, 2)


class PokemonSurvivalEducationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="core")

    def setUp(self):
        self.e = Engine(self.rules, seed=542)
        self.t = Combatant(self.rules, build_trainer(self.rules, "F50 GM campaign actor", 10, {k: 10 for k in F.STATS}))
        self.e.gm.add_combatant(self.t, reason="actual campaign trainer")
        self.p = self.pokemon()

    def pokemon(self):
        c = Combatant(self.rules, build_pokemon(self.rules, "이상해씨", 20, moves=["move/몸통박치기"], abilities=[]))
        self.e.gm.add_combatant(c, reason="observed actual individual")
        return c

    def campaign(self, education, **options):
        I.configure(self.e, self.t, portrayal="F50 campaign", discussed_with=["GM", "player"], social=options.pop("social", education),
                    education=education, reason="campaign discussion", **options)

    def roll(self, c, skill, dice, modifier=0, engine=None):
        result = (self.e if engine is None else engine).skill_roll(c, skill, fixed=[2] * dice)
        self.assertEqual((result.rank, result.modifier, result.total), (dice, modifier, 2 * dice + modifier))

    def reimport_evolved(self, c):
        spec = deepcopy(c.spec)
        self.assertTrue(D.evolve(self.rules, spec, "이상해풀"))
        fresh = Combatant(self.rules, spec)
        self.e.everyone[:] = [fresh if x is c else x for x in self.e.everyone]
        if self.e.gm.everyone is not self.e.everyone:
            self.e.gm.everyone[:] = [fresh if x is c else x for x in self.e.gm.everyone]
        return fresh, next(i for i, x in enumerate(spec["stat_history"]) if x["event"] == "evolution")

    def test_scholar_takes_survival_4d6_evolves_it_and_survives_gm_and_json_restore(self):
        self.campaign(True)
        self.e.gm.choose_pokemon_skill_template(self.p, "scholar", education_skill="생존", reason="GM chooses a Survival scholar")
        self.assertEqual(self.p.spec[P.FIELD]["primary"], "survival")
        self.roll(self.p, "생존", 4)
        c, index = self.reimport_evolved(self.p)
        self.e.gm.evolve_pokemon_skill_template(c, history_index=index, primary_increase="modifier", reason="observed evolution")
        self.roll(c, "생존", 4, 2)
        saved = deepcopy(c.spec)
        self.e.gm.snapshot("f50-scholar")
        self.e.gm.adjust_pokemon_skill_template(c, {"생존": "2d6"}, reason="GM changes the Education pool")
        self.roll(c, "생존", 2)
        self.e.gm.restore("f50-scholar")
        self.assertEqual(c.spec, saved)
        self.roll(c, "생존", 4, 2)
        restored = Engine.import_state(self.rules, self.e.export_state())
        loaded = next(x for x in restored.everyone if x.entity_id == c.entity_id)
        self.assertEqual(loaded.spec, saved)
        self.roll(loaded, "생존", 4, 2, engine=restored)

    def test_gm_assignment_and_individual_exception_name_survival_as_education(self):
        self.campaign(True)
        I.assign(self.e, self.t, target=self.p, skills={"생존": "4d6"}, reason="GM assigns an Education skill")
        self.roll(self.p, "생존", 4)
        other = self.pokemon()
        self.campaign(False, exceptions={other.spec["id"]: {"skills": ["생존"], "reason": "individual sapient Pokemon agreed by group"}})
        I.assign(self.e, self.t, target=other, skills={"생존": "3d6+1"}, reason="excepted individual Education")
        self.roll(other, "생존", 3, 1)

    def test_survival_as_new_education_is_refused_without_permission_and_others_stay_refused_atomically(self):
        self.campaign(False)
        before = deepcopy(self.p.spec)
        rng = self.e.rng.getstate()
        with self.assertRaisesRegex(ValueError, "eligibility"):
            I.assign(self.e, self.t, target=self.p, skills={"생존": "4d6"}, reason="feral campaign")
        with self.assertRaisesRegex(ValueError, "permission"):
            self.e.gm.choose_pokemon_skill_template(self.p, "scholar", education_skill="생존", reason="feral campaign")
        self.campaign(True)
        for skill in ("육상", "통찰"):
            with self.subTest(skill=skill):
                with self.assertRaisesRegex(ValueError, "Education"):
                    self.e.gm.choose_pokemon_skill_template(self.p, "scholar", education_skill=skill, reason="not an Education skill")
                with self.assertRaisesRegex(ValueError, "distinct campaign social or education"):
                    I.assign(self.e, self.t, target=self.p, skills={skill: "4d6"}, reason="not an Education skill")
        with self.assertRaisesRegex(ValueError, "distinct campaign social or education"):
            I.assign(self.e, self.t, target=self.p, skills={"생존": "4d6", "Survival": "3d6"}, reason="duplicate aliases")
        self.assertEqual(self.p.spec, before)
        self.assertEqual(self.e.rng.getstate(), rng)

    def test_species_native_survival_respects_education_denial_atomically(self):
        # Catalog pools also exist for every other Education and social skill; values
        # alone cannot exempt Survival from the explicit Education decision.
        self.campaign(False, social=True)
        before = deepcopy(self.p.spec), self.e.rng.getstate(), list(self.e.log_lines)
        for skill in ("생존", "Survival", "의학"):
            with self.subTest(skill=skill):
                with self.assertRaisesRegex(ValueError, "does not authorize"):
                    self.e.skill_roll(self.p, skill)
                self.assertEqual((self.p.spec, self.e.rng.getstate(), self.e.log_lines), before)
        for raised, lowered in ((["생존"], ["육상"]), (["육상"], ["Survival"]),
                                (["육상", "생존"], ["곡예", "은신"])):
            with self.subTest(raised=raised, lowered=lowered):
                with self.assertRaisesRegex(ValueError, "permission"):
                    self.e.gm.set_pokemon_skill_background(self.p, "Denied scout", raised=raised, lowered=lowered,
                                                           reason="Education denied by the campaign")
                self.assertEqual((self.p.spec, self.e.rng.getstate(), self.e.log_lines), before)
        self.assertNotIn(P.BACKGROUND, self.p.spec)
        self.roll(self.p, "육상", 3, 2)

    def test_species_native_survival_education_permission_allows_roll_and_background(self):
        self.campaign(True, social=False)
        self.roll(self.p, "Survival", 2)
        with self.assertRaisesRegex(ValueError, "does not authorize"):
            self.e.skill_roll(self.p, "매력")
        self.e.gm.set_pokemon_skill_background(self.p, "Educated scout", raised=["생존"], lowered=["육상"],
                                               reason="GM chosen individual background")
        self.roll(self.p, "생존", 3)
        self.roll(self.p, "육상", 2, 2)
        saved = deepcopy(self.p.spec)
        restored = Engine.import_state(self.rules, self.e.export_state())
        loaded = next(x for x in restored.everyone if x.entity_id == self.p.entity_id)
        self.assertEqual(loaded.spec, saved)
        self.roll(loaded, "Survival", 3, engine=restored)

    def test_species_native_survival_individual_exception_is_scoped_to_actor_and_skill(self):
        other = self.pokemon()
        self.campaign(False, exceptions={self.p.spec["id"]: {
            "skills": ["Survival"], "reason": "GM authorizes this individual Education skill"}})
        self.roll(self.p, "생존", 2)
        for actor, skill in ((other, "생존"), (self.p, "의학"), (self.p, "매력")):
            with self.subTest(actor=actor.entity_id, skill=skill):
                before = deepcopy(actor.spec), self.e.rng.getstate(), list(self.e.log_lines)
                with self.assertRaisesRegex(ValueError, "does not authorize"):
                    self.e.skill_roll(actor, skill)
                self.assertEqual((actor.spec, self.e.rng.getstate(), self.e.log_lines), before)
        before = deepcopy(other.spec), self.e.rng.getstate(), list(self.e.log_lines)
        with self.assertRaisesRegex(ValueError, "permission"):
            self.e.gm.set_pokemon_skill_background(other, "Unapproved scout", raised=["생존"], lowered=["육상"],
                                                   reason="No exception for this individual")
        self.assertEqual((other.spec, self.e.rng.getstate(), self.e.log_lines), before)
        self.e.gm.set_pokemon_skill_background(self.p, "Excepted scout", raised=["생존"], lowered=["육상"],
                                               reason="Existing individual exception authorizes Survival")
        self.roll(self.p, "Survival", 3)
        restored = Engine.import_state(self.rules, self.e.export_state())
        loaded = next(x for x in restored.everyone if x.entity_id == self.p.entity_id)
        self.roll(loaded, "생존", 3, engine=restored)
        restored_other = next(x for x in restored.everyone if x.entity_id == other.entity_id)
        with self.assertRaisesRegex(ValueError, "does not authorize"):
            restored.skill_roll(restored_other, "생존")


class ResearcherSurvivalEducationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = Rules(ROOT, ruleset="core")

    setUp = CRAFT.ResearcherFieldsCraftingTests.setUp
    setup = CRAFT.ResearcherFieldsCraftingTests.setup
    trainer = CRAFT.ResearcherFieldsCraftingTests.trainer
    pokemon = CRAFT.ResearcherFieldsCraftingTests.pokemon
    rejected = CRAFT.ResearcherFieldsCraftingTests.rejected
    valid = CRAFT.ResearcherFieldsCraftingTests.valid
    restore = CRAFT.ResearcherFieldsCraftingTests.restore

    def researcher(self, name, pos, survival, fields, **extra):
        skills = dict.fromkeys(NAMED_KO, 2)
        skills["생존"] = survival
        return self.trainer(name, pos, skills=skills, fields=fields, **extra)

    def test_survival_only_researchers_qualify_for_climatology_botany_and_top_tier_berries(self):
        climatologist = self.researcher("F50 climatologist", (6, 6), 3, [["climatology", "botany"]], feats=[RFS.CLIMATOLOGY])
        sid = RFS.activate_climatology(self.e, climatologist)
        self.assertEqual((sid, climatologist.abilities), (RFS.CLIMATOLOGY_PREFIX + climatologist.entity_id, ["방진"]))
        botanist = self.researcher("F50 botanist", (3, 3), 4, [["botany", "climatology"]],
                                   feats=[RFS.SEED_BAG, RFS.TOP_TIER], feat_ranks={RFS.SEED_BAG: 1})
        donor = self.pokemon("이상해씨", 12, "F50 donor", pos=(4, 3), owner=botanist, moves=["move/수면가루"])
        out = RFS.seed_bag(self.e, botanist, donor, "move/수면가루", seconds=600, reason="actual harvest")
        self.assertEqual((out["move"], botanist.moves), ("move/수면가루", ["move/수면가루"]))
        self.assertEqual(RFS.qualify(self.e, botanist, RFS.TOP_TIER)["english"], "Top Tier Berries")
        self.assertEqual(CA._top_tier(self.e, botanist), 4)
        caretaker = self.researcher("F50 caretaker", (8, 8), 3, [["pokemon_caretaking", "paleontology"]])
        self.assertEqual(set(RF.researcher(self.e, caretaker, "포켓몬 관리")), {"pokemon_caretaking", "paleontology"})
        self.valid()

    def test_researcher_without_any_novice_education_is_refused_before_any_change(self):
        body = self.researcher("F50 no education", (6, 6), 2, [["climatology", "botany"]], feats=[RFS.CLIMATOLOGY])
        body.spec["skills"].update({"육상": 6, "통찰": 6})
        self.rejected(lambda: RF.researcher(self.e, body, "climatology"), "Novice Education")
        self.rejected(lambda: RFS.activate_climatology(self.e, body), "Novice Education")
        self.assertEqual(body.abilities, [])
        named = self.researcher("F50 named education", (8, 8), 2, [["climatology", "botany"]], feats=[RFS.CLIMATOLOGY])
        named.spec["skills"]["포켓몬학"] = 3
        self.rejected(lambda: RFS.activate_climatology(self.e, named), "Climatology requires its printed skill rank")

    def test_survival_only_climatology_grant_survives_gm_and_json_restore(self):
        self.t = self.researcher("F50 restored climatologist", (6, 6), 3, [["climatology", "botany"]], feats=[RFS.CLIMATOLOGY])
        sid = RFS.activate_climatology(self.e, self.t)
        saved = deepcopy(self.t.spec)
        self.e.gm.snapshot("f50-climatology")
        self.t.spec["feats"].remove(RFS.CLIMATOLOGY)
        RFS.release_climatology(self.e, self.t)
        self.assertEqual(self.t.abilities, [])
        self.e.gm.restore("f50-climatology", reason="restore the qualified Researcher")
        self.assertEqual(self.t.spec, saved)
        self.valid()
        self.restore("t")
        self.assertEqual(self.t.abilities, ["방진"])
        self.assertEqual(RFS.activate_climatology(self.e, self.t), sid)


if __name__ == "__main__":
    unittest.main()
