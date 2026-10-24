"""All four typed bypass CSV identities retain their actual native source and type."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from engine import Engine,Rules
from ruleset import RuleFilter
import native_scenario_fixture as NATIVE
import ability_transitions as ABILITIES
import effects_ext as EXT
import state_codec as CODEC
import typed_defensive_bypass as TYPED
import world_entities as WORLD

ROOT=Path(__file__).resolve().parents[1]
SOURCES=(('ability/터보블레이즈-playtest','move/불꽃세례',411),
         ('ability/터보블레이즈-playtest-2','move/불꽃세례',504),
         ('ability/테라볼티지-playtest','move/전기쇼크',412),
         ('ability/테라볼티지-playtest-2','move/전기쇼크',501))
TACKLE='move/몸통박치기'


class ExactTypedBypassTests(unittest.TestCase):
    def world(self):
        def row(key,pos,side):
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':40,
                'stats':{'hp':100,'atk':30,'def':5,'spa':30,'spd':5,'spe':10},
                'moves':[TACKLE,'move/불꽃세례','move/전기쇼크','move/위액'],'abilities':[],
                'pos':pos,'side':side,'extra':{'movement':{'land':6},'movement_basis':'current'}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual typed-bypass combatant'}}
        self.e,actors=NATIVE.prepare_scene(ROOT,ruleset='playtest',seed=75411,grid={'width':12,'height':8},
            actors=[row('user',(2,2),'party'),row('target',(3,2),'foe')])
        self.a,self.b=actors['user'],actors['target']
        self.e.gm.set_types(self.b,['드래곤'],reason='actual resistant target type')
        self.e.gm.set_ability(self.b,'조가비갑옷/전투무장',reason='actual Defensive Shell Armor')

    def restore(self):
        ids=(self.a.entity_id,self.b.entity_id)
        self.e=CODEC.load_engine(Rules(ROOT,ruleset='playtest'),json.loads(json.dumps(CODEC.dump_engine(self.e))))
        index=WORLD.actor_index(self.e);self.a,self.b=[index[uid] for uid in ids]

    def test_four_exact_sources_drive_real_limited_critical_bypass_and_resistance_then_restore(self):
        for source,move,record in SOURCES:
            with self.subTest(source=source):
                self.world();self.e.gm.set_ability(self.a,source,reason='actual exact CSV source choice')
                self.assertEqual(ABILITIES.ability_id(self.e.r,source),source)
                self.assertEqual(self.e.r.selection.units[source]['source']['record_span'],[record,record])
                self.assertIn(source,self.a.spec['state_grants']['ability_receipts'])
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
                self.assertTrue(self.e.accuracy_check(self.a,self.b,self.e.r.move(move),fixed_roll=20)[2])
                self.assertFalse(self.e.accuracy_check(self.a,self.b,self.e.r.move(TACKLE),fixed_roll=20)[2])
                seen=[];native=EXT.effectiveness_hook
                def observe(*args,**kwargs):
                    result=native(*args,**kwargs);seen.append(result);return result
                hp=self.b.hp
                with patch.object(EXT,'effectiveness_hook',side_effect=observe),patch.object(Engine,'d20',return_value=20):
                    self.e.use_move(self.a,self.b,move,set_damage=True)
                self.assertLess(self.b.hp,hp);self.assertTrue(seen);self.assertEqual(set(seen),{1.0})
                self.assertEqual(self.a.move_uses[move],1);self.assertEqual(self.a.budget['standard'],0)
                self.restore();self.assertTrue(ABILITIES.active(self.a,source))
                self.assertTrue(self.e.accuracy_check(self.a,self.b,self.e.r.move(move),fixed_roll=20)[2])
                self.assertFalse(self.e.accuracy_check(self.a,self.b,self.e.r.move(TACKLE),fixed_roll=20)[2])

    def test_ambiguous_names_and_excluded_exact_source_do_not_grant_or_relabel_sibling(self):
        for source,move,_ in SOURCES:
            with self.subTest(source=source):
                self.world();label=TYPED.definition(self.e.r,source)['definition']['name']
                NATIVE.assert_rejected_unchanged(self.e,lambda:self.e.gm.set_ability(self.a,label,reason='ambiguous row'),
                    reason_pattern='Unresolved|unresolved|source|playtest')
                profile=deepcopy(self.e.r.ruleset.profile);profile['exclude_units']=[source]
                self.e.r.ruleset=RuleFilter(profile,'exact typed source exclusion');self.e.r._apply_ruleset()
                NATIVE.assert_rejected_unchanged(self.e,lambda:self.e.gm.set_ability(self.a,source,reason='excluded row'),
                    reason_pattern='Excluded|excluded|exclude')
                sibling=next(uid for uid,mid,_ in SOURCES if mid==move and uid!=source)
                self.e.gm.set_ability(self.a,sibling,reason='independently selected retained sibling source')
                self.assertTrue(ABILITIES.active(self.a,sibling));self.assertNotIn(source,self.a.abilities)
                self.assertIn(source,self.e.r.selection.units);self.assertIn(sibling,self.e.r.selection.units)

    def test_actual_suppression_and_withdrawal_remove_only_owned_source_effect(self):
        for source,move,_ in SOURCES:
            with self.subTest(source=source):
                self.world();self.e.gm.set_ability(self.a,source,reason='actual typed source')
                self.e.gm.choose_ability_transition(self.b,self.a,'move/위액',ability=source,reason='actual selected ability suppression')
                self.e.start_round(self.e.everyone);self.e.start_of_turn(self.b,initiative_count=20)
                with patch.object(Engine,'d20',return_value=18):self.e.use_move(self.b,self.a,'move/위액')
                self.assertFalse(ABILITIES.active(self.a,source));self.assertIn(source,self.a.spec['abilities'])
                self.assertFalse(self.e.accuracy_check(self.a,self.b,self.e.r.move(move),fixed_roll=20)[2])
                self.restore();self.assertFalse(ABILITIES.active(self.a,source))
                self.e.gm.set_ability(self.a,source,add=False,reason='actual permanent source withdrawal')
                self.assertNotIn(source,self.a.spec['abilities'])
                self.assertFalse(any(effect.get('_rule_id')==source for effect in self.a.registry))

    def test_typed_resistance_conversion_never_overrides_immunity_or_weakness(self):
        self.world();source='ability/테라볼티지-playtest-2';self.e.gm.set_ability(self.a,source,reason='actual exact source')
        self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a,initiative_count=20)
        for types,expected in ((['땅'],0),(['물'],1.5),(['드래곤'],1.0)):
            self.e.gm.set_types(self.b,types,reason='actual observed target typing')
            move=self.e.r.move('move/전기쇼크');raw=self.e.type_multiplier('전기',self.b)[0]
            result=EXT.effectiveness_hook(self.e,self.a,self.b,move,self.e.r.move_mech(move['id'])[0],raw,
                {'actual_damage_type':'전기','attacker':self.a,'target':self.b,'hit':True,'crit':False,'move':move,'engine':self.e})
            self.assertEqual(result,expected)


if __name__=='__main__':unittest.main()
