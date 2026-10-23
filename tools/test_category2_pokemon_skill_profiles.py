"""Native state proofs for optional Pokemon templates and skill backgrounds."""
from pathlib import Path
from copy import deepcopy
import sys, unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from engine import Rules, Engine, Combatant
from builder import build_trainer, build_pokemon
import pokemon_intelligence as I
import pokemon_skill_profiles as P
import downtime as D
import state_fields as F

EXPECTED = {
    "cutesy": {"협박": (1,0), "교활": (3,2), "직감": (2,2), "매력": (4,3), "명령": (2,0)},
    "taskmaster": {"협박": (4,3), "교활": (2,2), "직감": (2,0), "매력": (1,0), "명령": (3,2)},
    "trickster": {"협박": (1,0), "교활": (4,3), "직감": (3,2), "매력": (2,2), "명령": (2,0)},
    "scholar": {"의학": (4,0)}
}
class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = Rules(str(ROOT), ruleset="core")
    def setUp(self):
        self.e = Engine(self.r, seed=542)
        self.t = Combatant(self.r, build_trainer(self.r, "GM campaign actor", 10, {k:10 for k in F.STATS}))
        self.e.gm.add_combatant(self.t, reason="actual campaign trainer")
        I.configure(self.e, self.t, portrayal="chosen social Pokemon", discussed_with=["GM","player"], social=True, education=True, reason="campaign discussion")
    def pokemon(self, species="이상해씨", level=20, **kw):
        c = Combatant(self.r, build_pokemon(self.r, species, level, moves=["move/몸통박치기"], abilities=[], **kw))
        self.e.gm.add_combatant(c, reason="observed actual individual")
        return c
    def choose(self, c, template, **kw):
        if template == "scholar": kw.setdefault("education_skill", "의학")
        return self.e.gm.choose_pokemon_skill_template(c, template, reason="explicit GM optional template", **kw)
    def roll(self, c, skill, dice, modifier):
        result = self.e.skill_roll(c, skill, fixed=[2]*dice)
        self.assertEqual((result.rank, result.modifier, result.total), (dice,modifier,2*dice+modifier))
    def reimport_evolved(self, c):
        spec = deepcopy(c.spec)
        self.assertTrue(D.evolve(self.r, spec, "이상해풀"))
        fresh = Combatant(self.r, spec)
        self.assertEqual(fresh.entity_id, c.entity_id)
        self.e.everyone[:] = [fresh if x is c else x for x in self.e.everyone]
        if self.e.gm.everyone is not self.e.everyone:
            self.e.gm.everyone[:] = [fresh if x is c else x for x in self.e.gm.everyone]
        return fresh, next(i for i,x in enumerate(spec["stat_history"]) if x["event"]=="evolution")

    def test_all_four_gm_templates_feed_independent_native_pool_answers(self):
        for template, values in EXPECTED.items():
            with self.subTest(template=template):
                c = self.pokemon()
                # An imported individual may omit an optional pool; catalog values
                # themselves are explicit species data and must not be erased.
                c.spec["skills"].pop("매력")
                before = deepcopy(c.spec)
                self.assertNotIn("pokemon_skill_profile", before)
                with self.assertRaisesRegex(ValueError, "unassigned"):
                    self.e.skill_roll(c, "매력")
                self.choose(c, template)
                for skill, (dice, modifier) in values.items(): self.roll(c, skill, dice, modifier)
                self.assertEqual(c.spec["nature"], before["nature"])
                self.assertEqual(c.spec.get("personality"), before.get("personality"))
                self.assertEqual(c.entity_id, before["id"])

    def test_each_template_evolution_branch_consumes_real_observation_once(self):
        for template in EXPECTED:
            for mode in ("die", "modifier"):
                with self.subTest(template=template, mode=mode):
                    c = self.pokemon(); self.choose(c, template)
                    before = deepcopy(c.spec)
                    with self.assertRaisesRegex(ValueError, "actual evolution"):
                        self.e.gm.evolve_pokemon_skill_template(c, history_index=0, primary_increase=mode, reason="no evolution yet")
                    self.assertEqual(c.spec, before)
                    c, index = self.reimport_evolved(c)
                    primary = {"cutesy":"매력","taskmaster":"협박","trickster":"교활","scholar":"의학"}[template]
                    second = None if template=="scholar" else "명령"
                    kwargs = dict(history_index=index, primary_increase=mode, other_skill=second, reason="GM resolves actual evolution choice")
                    self.e.gm.evolve_pokemon_skill_template(c, **kwargs)
                    dice, modifier = EXPECTED[template][primary]
                    self.roll(c, primary, dice+int(mode=="die"), modifier+2*int(mode=="modifier"))
                    if second:
                        dice, modifier = EXPECTED[template][second]
                        self.roll(c, second, dice+int(mode=="modifier"), modifier+2*int(mode=="die"))
                    after = deepcopy(c.spec)
                    self.assertTrue(self.e.gm.evolve_pokemon_skill_template(c, **kwargs)["already_applied"])
                    self.assertEqual(c.spec, after)
                    kwargs["primary_increase"] = "modifier" if mode=="die" else "die"
                    with self.assertRaisesRegex(ValueError, "different recorded"):
                        self.e.gm.evolve_pokemon_skill_template(c, **kwargs)
                    self.assertEqual(c.spec, after)

    def test_trickster_translation_correction_is_visible_and_never_raises_intimidate_by_default(self):
        c = self.pokemon(); self.choose(c, "trickster"); c, index = self.reimport_evolved(c)
        correction = c.spec[P.FIELD]["source_correction"]
        self.assertEqual((correction["original_label"], correction["effective_skill"]), ("협박","guile"))
        self.e.gm.evolve_pokemon_skill_template(c, history_index=index, primary_increase="die", other_skill="명령", reason="Core201 Guile correction")
        self.roll(c,"교활",5,3);self.roll(c,"협박",1,0)

    def test_gm_species_adjustments_do_not_select_templates_from_species_name(self):
        for species, template, changes in [("입치트","taskmaster",{"협박":"4d6+3","교활":"4d6+3"}), ("파비코리","cutesy",{"매력":"4d6+3","직감":"4d6+3"})]:
            c=self.pokemon(species)
            self.assertNotIn(P.FIELD,c.spec)
            self.choose(c,template,adjustments=changes)
            for skill in changes:self.roll(c,skill,4,3)
            self.e.gm.adjust_pokemon_skill_template(c,{"명령":"7d6+2"},reason="explicit individual variation")
            self.roll(c,"명령",7,2)
            self.assertTrue(c.spec[P.FIELD]["adjustment_history"])

    def test_template_permission_and_invalid_choices_are_atomic(self):
        c=self.pokemon();before=deepcopy(c.spec);rng=self.e.rng.getstate()
        for template, options in [("absent",{}),("scholar",{"education_skill":"매력"}),("cutesy",{"adjustments":{"매력":"bad"}}),("taskmaster",{"adjustments":{"매력":"4d6","Charm":"3d6"}})]:
            with self.assertRaises(ValueError):self.choose(c,template,**options)
            self.assertEqual(c.spec,before)
        I.configure(self.e,self.t,portrayal="feral",discussed_with=["GM"],social=False,education=False,reason="declared campaign")
        with self.assertRaisesRegex(ValueError,"permission"):self.choose(c,"cutesy")
        self.assertEqual(c.spec,before);self.assertEqual(self.e.rng.getstate(),rng)

    def test_one_two_three_background_pairs_change_one_die_and_keep_species_constants(self):
        ups=["육상","곡예","전투"];downs=["은신","통찰","집중"]
        for count in (1,2,3):
            c=self.pokemon(extra={"skills":{name:"3d6+2" for name in ups+downs}})
            before=deepcopy(c.spec)
            self.e.gm.set_pokemon_skill_background(c,"Named individual",raised=ups[:count],lowered=downs[:count],reason="GM chosen individual background")
            for skill in ups[:count]:self.roll(c,skill,4,2)
            for skill in downs[:count]:self.roll(c,skill,2,2)
            for skill in ups[count:]+downs[count:]:self.roll(c,skill,3,2)
            self.assertEqual(c.spec[P.BACKGROUND]["name"],"Named individual")
            self.assertEqual(c.spec["species"],before["species"])
            after=deepcopy(c.spec)
            with self.assertRaisesRegex(ValueError,"already recorded"):
                self.e.gm.set_pokemon_skill_background(c,"Stacked",raised=[ups[0]],lowered=[downs[0]],reason="cannot stack backgrounds")
            self.assertEqual(c.spec,after)

    def test_background_bad_balance_unknown_alias_overlap_and_underflow_are_atomic(self):
        c=self.pokemon(extra={"skills":{"육상":"1d6+2","은신":"3d6+1","전투":"3d6"}})
        before=deepcopy(c.spec)
        cases=[([],[]),(["은신"],["육상"]),(["은신","Stealth"],["전투","육상"]),(["은신"],["은신"]),(["은신","전투"],["육상"]),(["없는스킬"],["전투"])]
        for raised, lowered in cases:
            with self.assertRaises(ValueError):self.e.gm.set_pokemon_skill_background(c,"Invalid",raised=raised,lowered=lowered,reason="invalid background")
            self.assertEqual(c.spec,before)

    def test_template_background_and_evolution_roundtrip_actual_gm_and_durable_state(self):
        c=self.pokemon();self.choose(c,"cutesy");c,index=self.reimport_evolved(c)
        self.e.gm.evolve_pokemon_skill_template(c,history_index=index,primary_increase="die",other_skill="명령",reason="observed evolution")
        self.e.gm.set_pokemon_skill_background(c,"Scout",raised=["은신"],lowered=["육상"],reason="individual background")
        saved=deepcopy(c.spec);self.e.gm.snapshot("profiles")
        self.e.gm.adjust_pokemon_skill_template(c,{"매력":"2d6"},reason="GM changes choice")
        self.e.gm.restore("profiles");self.assertEqual(c.spec,saved);self.roll(c,"매력",5,3)
        restored=Engine.import_state(self.r,self.e.export_state());loaded=next(x for x in restored.everyone if x.entity_id==c.entity_id)
        self.assertEqual(loaded.spec,saved)
        self.assertEqual(restored.skill_roll(loaded,"매력",fixed=[2]*5).total,13)
        self.assertTrue(restored.gm.evolve_pokemon_skill_template(loaded,history_index=index,primary_increase="die",other_skill="명령",reason="retry after restore")["already_applied"])

    def test_corrupt_source_choice_history_or_background_is_rejected_on_real_export(self):
        c=self.pokemon();self.choose(c,"trickster");c,index=self.reimport_evolved(c)
        self.e.gm.evolve_pokemon_skill_template(c,history_index=index,primary_increase="die",other_skill="명령",reason="observed evolution")
        self.e.gm.set_pokemon_skill_background(c,"Scout",raised=["은신"],lowered=["육상"],reason="individual background")
        valid=deepcopy(c.spec)
        for change in (lambda:c.spec[P.FIELD].update(source="wrong"),lambda:c.spec[P.FIELD].update(primary="intimidate"),lambda:c.spec[P.FIELD]["evolutions"][0]["applied_pools"].update(guile="9d6+3"),lambda:c.spec[P.BACKGROUND]["after"].update(stealth="6d6")):
            change()
            with self.assertRaises(ValueError):self.e.export_state()
            c.spec=deepcopy(valid)
        before=deepcopy(c.spec)
        with self.assertRaises(ValueError):F.base_patch(c,{"skills":{"매력":"success"}},reason="bad pool")
        self.assertEqual(c.spec,before)

    def test_full_porygon_line_catalog_technology_is_available_under_feral_policy(self):
        I.configure(self.e,self.t,portrayal="feral",discussed_with=["GM"],social=False,education=False,reason="chosen policy")
        for species,dice,modifier in [("폴리곤",3,0),("폴리곤2",4,1),("폴리곤Z",5,3)]:
            c=self.pokemon(species);self.roll(c,"기술학",dice,modifier)
            with self.assertRaises(ValueError):self.choose(c,"scholar")

if __name__=="__main__":unittest.main()
