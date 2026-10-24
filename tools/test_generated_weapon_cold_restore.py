"""Cold restoration derives native weapons; it never imports arbitrary rule bodies."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import unittest
from engine import Engine,Rules
import native_scenario_fixture as NATIVE
import state_codec as CODEC
import turn as TURN
import ruleset as SELECTION
import skill_modifiers as SKILL
import world_entities as WORLD
from examples.declared_skill_ranks import configure

ROOT=Path(__file__).resolve().parents[1]


class GeneratedWeaponColdRestoreTests(unittest.TestCase):
    def world(self):
        rules=Rules(ROOT,ruleset='all');configure(rules)
        def row(key,pos,side):
            return {'key':key,'kind':'trainer','sheet':{'name':key,'level':40,
                'stats':dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),
                'moves':['move/몸통박치기'],'abilities':[],'pos':pos,'side':side,
                'skills':{'전투':7},'extra':{'movement':{'land':6},'movement_basis':'current'}},
                'body':{'size':'중형','offsets':[(0,0)],'reason':'actual cold-restore weapon body'}}
        with patch.object(NATIVE,'Rules',return_value=rules):
            e,actors=NATIVE.prepare_scene(ROOT,ruleset='all',seed=7581,grid={'width':12,'height':8},
                actors=[row('wielder',(2,2),'party'),row('foe',(3,2),'foe')])
        a,b=actors['wielder'],actors['foe']
        ids=[]
        for slot in ('주요손','반대손'):
            ids.append(TURN.equip_weapon(e,a,{'name':'same named cold baton','kind':'소형 근접무기',
                'grade':'간단','moves':[],'slot':slot}))
        return e,a,b,ids

    def fresh(self):
        rules=Rules(ROOT,ruleset='all');configure(rules);return rules

    def rules_state(self,rules):
        return (CODEC.rules_fingerprint(rules),set(rules.moves),set(rules.moves_mech),
                deepcopy(rules.selection.units),deepcopy(rules.selection.dependencies),
                deepcopy(rules.selection.names),deepcopy(rules._runtime_weapon_declarations))

    def test_actual_fresh_rules_reconstructs_both_sources_and_executes_without_reequip_events(self):
        e,a,b,ids=self.world();payload=json.loads(json.dumps(CODEC.dump_engine(e),sort_keys=True))
        original=(deepcopy(a.custom_conditions['equipped_weapons']),list(a.moves),e.elapsed_seconds,
                  list(getattr(a,'_action_history',[])),list(e.log_lines),deepcopy(e._physical_objects))
        fresh=self.fresh();before=self.rules_state(fresh)
        restored=CODEC.load_engine(fresh,payload);index=WORLD.actor_index(restored);user,foe=index[a.entity_id],index[b.entity_id]
        self.assertEqual(self.rules_state(fresh),before)
        self.assertEqual(CODEC.rules_fingerprint(restored.r),payload['rules'])
        self.assertEqual((user.custom_conditions['equipped_weapons'],user.moves,restored.elapsed_seconds,
                          list(getattr(user,'_action_history',[])),restored.log_lines,restored._physical_objects),original)
        self.assertEqual(restored.r.selection.names['same named cold baton 발버둥'],ids)
        self.assertEqual(SKILL.rank(restored.r,user,'전투')[2],7)
        restored.start_round(restored.everyone);restored.start_of_turn(user,initiative_count=20);hp=foe.hp
        with patch.object(Engine,'d20',return_value=18):restored.use_move(user,foe,ids[0],weapon_id=ids[0],set_damage=True)
        self.assertLess(foe.hp,hp);self.assertEqual(user.move_uses[ids[0]],1);self.assertEqual(user.budget['standard'],0)
        self.assertTrue(restored.validate_state()['valid'])

    def test_forged_native_definition_or_identity_is_rejected_without_mutating_supplied_rules_or_payload(self):
        e,_,_,_=self.world();payload=json.loads(json.dumps(CODEC.dump_engine(e)))
        for change in ('body','identity','kind','duplicate'):
            with self.subTest(change=change):
                bad=deepcopy(payload);rows=bad['rules']['generated_weapons']
                if change=='body':rows[0]['definition']={'damage_base':999,'source':'weapon'}
                elif change=='identity':rows[0]['id']='move/몸통박치기'
                elif change=='kind':rows[0]['weapon']['kind']='unregistered invented weapon kind'
                else:rows.append(deepcopy(rows[0]))
                fresh=self.fresh();before=self.rules_state(fresh);unchanged=deepcopy(bad)
                with self.assertRaises(CODEC.StateCodecError):CODEC.load_engine(fresh,bad)
                self.assertEqual(self.rules_state(fresh),before);self.assertEqual(bad,unchanged)

    def test_late_second_source_admission_failure_leaves_no_partial_catalog_on_caller(self):
        e,_,_,_=self.world();payload=json.loads(json.dumps(CODEC.dump_engine(e)))
        fresh=self.fresh();before=self.rules_state(fresh);unchanged=deepcopy(payload);seen=[]
        native=SELECTION.require_runtime_weapon
        def fail(rules,uid):
            result=native(rules,uid);seen.append(uid)
            if len(seen)==2:raise ValueError('second generated source receiver failed')
            return result
        with patch.object(SELECTION,'require_runtime_weapon',side_effect=fail):
            with self.assertRaisesRegex(CODEC.StateCodecError,'second generated source receiver failed'):
                CODEC.load_engine(fresh,payload)
        self.assertEqual(len(seen),2);self.assertEqual(self.rules_state(fresh),before)
        self.assertEqual(payload,unchanged)

    def test_selected_weapon_parent_exclusion_cannot_be_bypassed_by_saved_declarations(self):
        e,_,_,_=self.world();payload=json.loads(json.dumps(CODEC.dump_engine(e)));fresh=self.fresh()
        profile=deepcopy(fresh.ruleset.profile);profile['exclude_units']=['ch09-equipment/장비/무기']
        fresh.ruleset=SELECTION.RuleFilter(profile,'weapon parent excluded');fresh._apply_ruleset()
        before=self.rules_state(fresh)
        with self.assertRaises(CODEC.StateCodecError):CODEC.load_engine(fresh,payload)
        self.assertEqual(self.rules_state(fresh),before)


if __name__=='__main__':unittest.main()
