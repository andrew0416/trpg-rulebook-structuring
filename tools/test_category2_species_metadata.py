from pathlib import Path
import csv,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"engine")]
from engine import Rules,Combatant
import species_metadata as M,pokemon_entities as P,builder

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset="core")
    def test_all_catalog_sex_values_are_preserved_or_explicitly_unresolved(self):
        with (ROOT/"input/db/pokemon.csv").open(encoding="utf-8-sig",newline="") as f:rows=list(csv.reader(f))
        for record in self.r.species.values():
            if record.get("_source",{}).get("file")!="db/pokemon.csv":continue
            raw=rows[record["_source"]["record_span"][0]-1][34:36]
            view=M.sex_distribution(raw)
            self.assertEqual(view["raw"],raw)
            if view["status"]=="known":self.assertAlmostEqual(view["male"]+view["female"],1)
        self.assertEqual(M.sex_distribution(["87","12"])["status"],"unresolved_source_value")
        self.assertEqual(M.sex_distribution(["0.5","0..5"])["status"],"unresolved_source_value")
        self.assertEqual(M.sex_distribution(["50","50"])["male"],0.5)
    def test_template_distribution_and_measurement_do_not_become_individual_facts(self):
        template=P.species_projection(self.r,"pokemon/이상해씨")
        self.assertEqual(template["template_facts"]["sex_distribution"]["male"],0.875)
        self.assertEqual(template["template_facts"]["catalog_measurements"]["height_m"],0.7)
        c=Combatant(self.r,builder.build_pokemon(self.r,"이상해씨",5))
        actual=P.actor_projection(c)
        self.assertIsNone(actual["gender"])
        self.assertIsNone(actual["height_m"])
    def test_form_rule_tail_survives_extraction_and_runtime_catalog(self):
        sys.path.insert(0,str(ROOT/"tools"))
        from parse_sheets_extra import learnsets
        parsed,_=learnsets(str(ROOT/"input/db"))
        for name in ("후파","굴레에 빠진 후파","굴레를 벗어난 후파"):
            record=next(row for row in parsed if row["species"]==name)
            self.assertIn("고스트다이브→탁쳐서떨구기",record["note"])
            self.assertEqual(self.r.learnsets[name]["note"],record["note"])
            self.assertGreater(len(record["note"]),300)

    def test_custom_species_name_does_not_import_stock_template(self):
        self.assertEqual(M.project(self.r,{"name":"이상해씨","_source":{"file":"custom"}})["sex_distribution"]["status"],"unknown")

if __name__=="__main__":unittest.main(verbosity=2)
