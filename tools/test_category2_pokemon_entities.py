"""Native egg producers, independent identities, and private individual facts."""
from pathlib import Path
from copy import deepcopy
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"engine"),str(ROOT/"tools")]
from engine import Engine, Combatant
import builder, pokemon_entities as P, state_fields as F
import test_category3_pokemon_activities as _fixture_test_category3_pokemon_activities

class Tests(_fixture_test_category3_pokemon_activities.PokemonActivityTests):
    # Reuse a legal real-producer fixture; only tests below are selected by main.
    def test_egg_identity_owner_and_durable_unknown_facts(self):
        self.own("breeder")
        self.act("breed",pair=[self.p,self.q],task_id="egg1",phase="check",compatible=True,fixed=[3]*4)
        self.act("breed",pair=[self.p,self.q],task_id="egg1",phase="finish")
        row=self.a.spec["eggs"][0]
        import world_entities as W
        before=deepcopy(getattr(self.e,'_physical_objects',{}))
        with self.assertRaisesRegex(ValueError,'identity collides'):
            W.register_object(self.e,row['entity_id'],location={'kind':'unknown'},reason='duplicate egg identity')
        self.assertEqual(getattr(self.e,'_physical_objects',{}),before)
        self.assertNotEqual(row["entity_id"],row["id"])
        self.assertEqual(self.e.entity_identity(row["entity_id"],kind="egg")["owner_id"],self.a.entity_id)
        self.assertIsNone(row["species"])
        self.assertFalse(P.egg_projection(self.e,row["entity_id"])["combatant"])
        self.assertEqual(P.egg_projection(self.e,row["entity_id"])["hatch_timing"]["status"],"pending")
        second=Combatant(self.e.r,builder.build_trainer(self.e.r,"other",5,{s:5 for s in F.STATS},pos=(8,8)))
        self.e.gm.add_combatant(second)
        reference=row
        receipt=self.e.gm.transfer_egg(self.a,second,row["entity_id"],reason="GM confirms egg gift",request_id="gift-1")
        self.assertIs(second.spec["eggs"][0],reference)
        self.assertEqual(self.e.entity_identity(row["entity_id"],kind="egg")["owner_id"],second.entity_id)
        self.assertEqual(self.a.spec["eggs"],[])
        self.assertEqual(self.e.gm.transfer_egg(self.a,second,row["entity_id"],reason="GM confirms egg gift",request_id="gift-1"),receipt)
        before=self.e.export_state()
        with self.assertRaisesRegex(ValueError,'changed input'):
            self.e.gm.transfer_egg(self.a,second,row['entity_id'],reason='changed intent',request_id='gift-1')
        self.assertEqual(self.e.export_state(),before)
        self.e.validate_state()
        loaded=Engine.import_state(self.e.r,self.e.export_state())
        self.assertEqual(P.egg_projection(loaded,row["entity_id"]),P.egg_projection(self.e,row["entity_id"]))
        index=W.actor_index(loaded);before=loaded.export_state()
        replay=loaded.gm.transfer_egg(index[self.a.entity_id],index[second.entity_id],row['entity_id'],reason='GM confirms egg gift',request_id='gift-1')
        self.assertEqual(replay,receipt);self.assertEqual(loaded.export_state(),before)
    def test_fossil_hatch_reference_survives_name_change(self):
        details=self.fossil_egg()
        import world_entities as W
        uid=next(iter(P.fossil_index(self.e)))
        before=deepcopy(getattr(self.e,'_physical_objects',{}))
        with self.assertRaisesRegex(ValueError,'identity collides'):
            W.register_object(self.e,uid,location={'kind':'unknown'},reason='duplicate fossil identity')
        self.assertEqual(getattr(self.e,'_physical_objects',{}),before)
        for uid, (owner, _) in P.fossil_index(self.e).items():
            self.assertEqual(self.e.entity_identity(uid,kind="fossil")["owner_id"],owner.entity_id)
        result=self.act("hatch_fossil",egg_id="fossil/f1",name="same name",ready=True,reason="GM observed readiness",details=details)
        child=result["pokemon"];egg=self.a.spec["eggs"][0]
        self.assertEqual(egg["pokemon_id"],child.entity_id)
        child.name="renamed child"
        self.assertEqual(egg["pokemon_id"],child.entity_id)
        self.assertEqual(child.location,self.a.location)
        self.e.validate_state()
        loaded=Engine.import_state(self.e.r,self.e.export_state())
        self.assertEqual(P.egg_projection(loaded,egg["entity_id"])["pokemon_id"],child.entity_id)
    def test_species_values_are_not_observed_individual_facts(self):
        self.p.spec["loyalty"]=3
        player=self.e.gm.describe_actor(self.p)
        gm=self.e.gm.describe_actor(self.p,viewer="gm")
        self.assertNotIn("loyalty",player)
        self.assertEqual(gm["loyalty"],3)
        self.assertIsNone(player["height_m"])
        self.assertIsNone(player["gender"])
        self.p.spec["loyalty"]=7
        with self.assertRaises(ValueError): F.validate_actor(self.p)
    def test_egg_catalog_placeholder_is_not_ordinary_species_stats(self):
        if "pokemon/알" not in self.e.r.species:self.skipTest("selected catalog has no egg placeholder")
        self.assertEqual(P.species_projection(self.e.r,"pokemon/알")["record_kind"],"egg_catalog_placeholder")
        with self.assertRaises(ValueError):builder.build_pokemon(self.e.r,"알",1)
        with self.assertRaises(ValueError):
            Combatant(self.e.r,{"kind":"pokemon","name":"unhatched","level":1,"stats":{s:0 for s in F.STATS}})

if __name__=="__main__":
    names=[name for name in Tests.__dict__ if name.startswith("test_")]
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Tests(name) for name in names))
    sys.exit(not result.wasSuccessful())
