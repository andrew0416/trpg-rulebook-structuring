"""Source clauses for species/individual boundaries and native basic-state consumers."""
from pathlib import Path
from copy import deepcopy
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine')]
from engine import Engine, Rules, Combatant
import builder, pokemon_entities as P, state_fields as F
import movement_actions as MOVE, state_grants as GRANTS

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(str(ROOT),ruleset='core')
    def setUp(self):
        self.e=Engine(self.r,331)
        self.p=Combatant(self.r,builder.build_pokemon(self.r,'이상해씨',5,pos=(1,1)))
        self.a=Combatant(self.r,builder.build_trainer(self.r,'트레이너',5,{s:8 for s in F.STATS},pos=(2,1)))
        self.e.everyone=self.e.gm.everyone=[self.a,self.p]
    def loaded(self):
        loaded=Engine.import_state(self.r,self.e.export_state())
        return loaded,{c.entity_id:c for c in loaded.everyone}
    def test_species_template_remains_shared_reference_while_individuals_differ(self):
        other=Combatant(self.r,builder.build_pokemon(self.r,'이상해씨',5,name='another',abilities=['심록']))
        self.e.gm.add_combatant(other)
        self.assertNotEqual(self.p.entity_id,other.entity_id)
        self.assertEqual(self.p.spec['species'],other.spec['species'])
        template=P.species_projection(self.r,self.p.spec['species'])
        self.assertEqual(template['record_kind'],'species_template')
        self.assertIsNone(template['individual_identity'])
        before=deepcopy(self.r.species[self.p.spec['species']])
        F.base_patch(self.p,{'name':'별명'},reason='player nickname')
        self.assertEqual(self.r.species[self.p.spec['species']],before)
        loaded,actors=self.loaded()
        self.assertEqual(actors[self.p.entity_id].spec['species'],actors[other.entity_id].spec['species'])
        self.assertEqual(loaded.gm.describe_actor(actors[self.p.entity_id])['name'],'별명')
    def test_default_trainer_has_no_type_and_explicit_source_grant_is_reversible(self):
        self.assertEqual(self.a.types,[])
        self.assertEqual(self.a.spec['types'],[])
        self.assertEqual(self.e.type_multiplier('격투',self.a)[0],1)
        F.base_patch(self.a,{'types':['노말']},reason='explicit GM type grant')
        self.assertEqual(self.e.type_multiplier('격투',self.a)[0],1.5)
        F.base_patch(self.a,{'types':[]},reason='GM ends type grant')
        loaded,actors=self.loaded()
        self.assertEqual(actors[self.a.entity_id].types,[])
        self.assertEqual(loaded.type_multiplier('격투',actors[self.a.entity_id])[0],1)
    def test_gm_measurements_do_not_rewrite_catalog_or_other_individual(self):
        before=P.species_projection(self.r,self.p.spec['species'])['template_facts']['catalog_measurements']
        self.assertEqual(before['height_m'],0.7)
        self.assertIsNone(self.e.gm.describe_actor(self.p)['height_m'])
        self.e.gm.observe_actor_measurements(self.p,{'height_m':0.9,'weight_kg':8.2},reason='GM confirms individual size',request_id='measured')
        self.assertEqual(P.species_projection(self.r,self.p.spec['species'])['template_facts']['catalog_measurements'],before)
        self.e.gm.snapshot('measurements')
        self.e.gm.observe_actor_measurements(self.p,{'height_m':None},reason='correction')
        self.e.gm.restore('measurements')
        loaded,actors=self.loaded()
        view=loaded.gm.describe_actor(actors[self.p.entity_id])
        self.assertEqual((view['height_m'],view['weight_kg']),(0.9,8.2))
        before=deepcopy(self.p.spec)
        with self.assertRaises(ValueError):self.e.gm.observe_actor_measurements(self.p,{'height_m':-1},reason='invalid')
        self.assertEqual(self.p.spec,before)
    def test_species_movement_and_special_capability_sources_are_distinct(self):
        sp=builder.species_lookup(self.r,'이상해씨')
        self.assertEqual(MOVE.capabilities(self.e,self.p)['land'],sp['movement']['land'])
        baseline=list(GRANTS.effective_capabilities(self.p))
        GRANTS.grant(self.p,'capabilities','암흑시야','gm/sight','gm',lifetime='until revoked')
        self.assertIn('암흑시야',GRANTS.effective_capabilities(self.p))
        self.assertEqual(MOVE.capabilities(self.e,self.p)['land'],sp['movement']['land'])
        loaded,actors=self.loaded()
        self.assertIn('암흑시야',GRANTS.effective_capabilities(actors[self.p.entity_id]))
        GRANTS.revoke(self.p,'gm/sight',engine=self.e)
        self.assertEqual(GRANTS.effective_capabilities(self.p),baseline)
    def test_native_pokemon_and_trainer_skill_consumers_read_their_own_sheet(self):
        plan=self.e._prepare_skill_roll(self.p,'육상')
        self.assertEqual((plan[-1]['dice_count'],plan[-1]['modifier']),(3,2))  # Bulbasaur source3d6+2
        n=plan[-1]['dice_count'];modifier=plan[-1]['modifier']
        result=self.e.skill_roll(self.p,'육상',fixed=[2]*n)
        self.assertEqual(result.total,8)
        self.assertEqual(self.e.skill_roll(self.a,'육상',fixed=[3,3]).total,6)
        loaded,actors=self.loaded()
        self.assertEqual(loaded.skill_roll(actors[self.p.entity_id],'육상',fixed=[2]*n).total,result.total)
    def test_charmander_source_base_statistics_are_not_allocated_runtime_values(self):
        template=builder.species_lookup(self.r,'파이리')
        expected={'hp':4,'atk':5,'def':4,'spa':6,'spd':5,'spe':7}
        self.assertEqual(template['base_stats'],expected)
        spec=builder.build_pokemon(self.r,'파이리',5,abilities=['맹화'])
        self.assertEqual(spec['stat_history'][0]['base'],expected)
        self.assertNotEqual(spec['stats'],expected)
        self.assertEqual(template['base_stats'],expected)
        actual=Combatant(self.r,spec)
        self.e.gm.add_combatant(actual)
        self.assertEqual(self.e.gm.describe_actor(actual)['species_id'],template['id'])
        loaded,actors=self.loaded()
        self.assertEqual(actors[actual.entity_id].spec['stat_history'][0]['base'],expected)
        self.assertEqual(loaded.r.species[actors[actual.entity_id].spec['species']]['base_stats'],expected)
    def test_pokemon_hp_formula_and_actual_hp_are_separate_and_durable(self):
        F.base_patch(self.p,{'stats':{s:8 for s in F.STATS}},reason='explicit imported final stats')
        self.e.gm.set_hp(self.p,value=39,reason='GM confirms full HP')
        self.assertEqual((self.p.base_max_hp,self.p.max_hp,self.p.hp),(39,39,39))
        self.e.take_damage(self.p,5)
        self.assertEqual((self.p.stats['hp'],self.p.hp),(8,34))
        F.base_patch(self.p,{'level':6},reason='confirmed level')
        self.assertEqual((self.p.max_hp,self.p.hp),(40,34))
        loaded,actors=self.loaded()
        self.assertEqual((actors[self.p.entity_id].max_hp,actors[self.p.entity_id].hp),(40,34))

if __name__=='__main__':unittest.main(verbosity=2)
