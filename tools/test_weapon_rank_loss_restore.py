"""An equipped physical source survives rank loss; live use permission does not."""
import json
import unittest
from engine import Rules
from tools import test_living_weapon_caps_shield_source_revision as FIXTURE
import living_weapon as LIVING
import state_codec as CODEC
import world_entities as WORLD


class WeaponRankLossRestoreTests(unittest.TestCase):
    def test_low_rank_physical_loadout_restores_without_regranting_borrowed_move(self):
        for variant in ('korean_all_equipped','english_own_living_weapon'):
            with self.subTest(variant=variant):
                f=FIXTURE.LivingWeaponCapsShieldSourceRevisionTests()
                f.world(species='단칼빙');f.equip(variant);other=f.external(FIXTURE.WOUND)
                f.e.gm.set_skill(f.a,'전투',3,reason='actual observed donor Skill loss')
                LIVING.refresh(f.e,f.p)
                self.assertNotIn(FIXTURE.WOUND,f.p.moves)
                self.assertIn(other,f.a.custom_conditions['equipped_weapons'])
                state=json.loads(json.dumps(CODEC.dump_engine(f.e)))
                restored=CODEC.load_engine(Rules(FIXTURE.ROOT,ruleset='core'),state)
                index=WORLD.actor_index(restored);owner,blade=index[f.a.entity_id],index[f.p.entity_id]
                self.assertIn(other,owner.custom_conditions['equipped_weapons'])
                self.assertNotIn(FIXTURE.WOUND,blade.moves)
                self.assertTrue(restored.validate_state()['valid'])
                restored.gm.set_skill(owner,'전투',4,reason='actual observed donor qualification recovery')
                LIVING.refresh(restored,blade)
                self.assertIn(FIXTURE.WOUND,blade.moves)


if __name__=='__main__':unittest.main()
