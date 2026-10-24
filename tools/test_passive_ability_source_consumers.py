"""Passive immunity follows actual selected ability ownership across ID/name storage."""
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from engine import Engine,Rules
import native_scenario_fixture as NATIVE
import ability_transitions as ABILITIES
import state_codec as CODEC
import world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]
POWDER='move/독가루'


class PassiveAbilitySourceConsumerTests(unittest.TestCase):
    def world(self):
        def row(key,pos,side):
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':30,
                'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),20),
                'moves':[POWDER,'move/위액'],'abilities':[],'pos':pos,'side':side},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual source-owned immunity actor'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=7553,grid={'width':12,'height':8},
            actors=[row('attacker',(2,2),'party'),row('holder',(3,2),'foe')])
        self.a,self.b=actors['attacker'],actors['holder']

    def test_exact_id_and_display_name_protection_use_actual_target_owner_and_native_suppression(self):
        for label in ('ability/방진','방진'):
            with self.subTest(stored=label):
                self.world();self.e.gm.set_ability(self.b,label,reason='actual Overcoat owner')
                self.assertTrue(ABILITIES.active(self.b,'ability/방진'))
                move=self.e.r.move(POWDER)
                self.assertFalse(self.e.accuracy_check(self.a,self.b,move,fixed_roll=20)[0])
                self.assertTrue(self.e.accuracy_check(self.b,self.a,move,fixed_roll=20)[0])
                self.e.gm.choose_ability_transition(self.a,self.b,'move/위액',ability='ability/방진',reason='actual selected source suppression')
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
                with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.a,self.b,'move/위액')
                self.assertFalse(ABILITIES.active(self.b,'ability/방진'))
                self.assertTrue(self.e.accuracy_check(self.a,self.b,move,fixed_roll=20)[0])
                ids=(self.a.entity_id,self.b.entity_id)
                self.e=CODEC.load_engine(Rules(ROOT,ruleset='all'),json.loads(json.dumps(CODEC.dump_engine(self.e))))
                index=WORLD.actor_index(self.e);self.a,self.b=[index[uid] for uid in ids]
                self.assertFalse(ABILITIES.active(self.b,'ability/방진'))
                self.assertTrue(self.e.accuracy_check(self.a,self.b,self.e.r.move(POWDER),fixed_roll=20)[0])
                self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
