"""C10-083: actual maternal consciousness gates attacks, never pouch custody."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon,build_trainer,STATS
import test_core_marsupial as FIXTURE
from native_scenario_fixture import assert_rejected_unchanged
import marsupial_state as M
import body_modes as BODY
import setup_move_state as SETUP
import effects_ext as EXT
import state_codec as CODEC
import world_entities as W
import turn as TURN
import pokemon_party as PARTY


class MarsupialConsciousSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.r=Rules(ROOT,ruleset='core')

    setUp=FIXTURE.MarsupialTests.setUp
    policy=FIXTURE.MarsupialTests.policy
    egg=FIXTURE.MarsupialTests.egg
    hatch=FIXTURE.MarsupialTests.hatch
    born=FIXTURE.MarsupialTests.born
    snap=FIXTURE.MarsupialTests.snap
    valid=FIXTURE.MarsupialTests.valid

    def begin_enemy(self):
        self.e.start_round([self.a,self.mother,self.enemy])
        self.e.start_of_turn(self.enemy,initiative_count=20)

    def protection(self,baby,expected):
        attack=self.r.move('move/몸통박치기');mm,_=self.r.move_mech(attack['id'])
        self.assertEqual(M.protected_from_attacks(baby,engine=self.e),expected)
        self.assertEqual(M.projection(baby,engine=self.e)['protected_from_attacks'],expected)
        self.assertEqual(BODY.targetable(baby,engine=self.e),not expected)
        self.assertEqual(SETUP.targetable(baby,engine=self.e),not expected)
        self.assertEqual(M.attack_blocked(self.enemy,baby,attack,engine=self.e),expected)
        self.assertEqual(EXT.blocks_hit(self.e,self.enemy,baby,attack,mm),M.SOURCE if expected else None)

    def faint_mother(self):
        self.e.lose_hp(self.mother,self.mother.hp,source='actual maternal faint crossing')
        self.assertTrue(self.mother.fainted)

    def reload(self,baby):
        ids=[c.entity_id for c in (self.a,self.mother,self.father,self.enemy,baby)]
        self.e=CODEC.load_engine(self.r,json.loads(self.snap()))
        index=W.actor_index(self.e)
        self.a,self.mother,self.father,self.enemy,baby=[index[uid] for uid in ids]
        self.valid()
        return baby

    def test_conscious_mother_blocks_native_attack_before_action_frequency_or_rng(self):
        baby=self.born();self.begin_enemy();self.protection(baby,True)
        assert_rejected_unchanged(self.e,
            lambda:self.e.use_move(self.enemy,baby,'move/몸통박치기',situational=100,set_damage=True),
            reason_pattern='pouch')
        self.assertEqual(self.enemy.budget['standard'],1)
        self.assertTrue(M.in_pouch(baby));self.assertFalse(TURN.can_act(self.e,baby))
        self.valid()

    def test_actual_faint_allows_normal_paid_damage_without_releasing_the_pouch(self):
        baby=self.born();history=deepcopy(baby.spec[M.KEY]);custody=M.custody(self.e,baby)
        self.begin_enemy();self.faint_mother();self.protection(baby,False)
        hp=baby.hp
        with patch.object(Engine,'d20',return_value=12), patch.object(Engine,'roll_damage',autospec=True,side_effect=Engine.roll_damage) as damage:
            self.e.use_move(self.enemy,baby,'move/몸통박치기',situational=100,set_damage=True)
        self.assertEqual(damage.call_count,1);self.assertLess(baby.hp,hp)
        self.assertEqual(self.enemy.budget['standard'],0)
        self.assertEqual(baby.spec[M.KEY],history)
        self.assertEqual(M.custody(self.e,baby),custody)
        self.assertFalse(baby.on_field);self.assertFalse(TURN.can_act(self.e,baby))
        self.assertEqual(W.effective_location(self.e,baby),W.location_of(self.mother))
        self.valid()

    def test_positive_hp_ordinary_healing_keeps_faint_gate_until_actual_revive(self):
        baby=self.born();self.faint_mother();self.protection(baby,False)
        self.e.heal(self.mother,10,source_kind='ordinary_item')
        self.assertGreater(self.mother.hp,0);self.assertTrue(self.mother.fainted)
        self.protection(baby,False)
        self.assertTrue(self.e.revive(self.mother,20));self.assertFalse(self.mother.fainted)
        self.protection(baby,True)
        self.assertTrue(M.in_pouch(baby));self.assertFalse(TURN.can_act(self.e,baby))
        self.valid()

    def test_cold_restore_and_gm_restore_use_current_maternal_state_not_a_saved_shield(self):
        baby=self.born();self.begin_enemy();self.e.gm.snapshot('conscious-mother');original=self.e
        self.faint_mother();baby=self.reload(baby);self.protection(baby,False)
        hp=baby.hp
        self.e.use_move(self.enemy,baby,'move/몸통박치기',situational=100,set_damage=True)
        self.assertLess(baby.hp,hp)
        self.e=original
        self.e.gm.restore('conscious-mother',reason='restore actual pre-faint maternal world')
        index=W.actor_index(self.e);baby=index[baby.entity_id];self.mother=index[self.mother.entity_id]
        self.enemy=index[self.enemy.entity_id];self.protection(baby,True)
        assert_rejected_unchanged(self.e,
            lambda:self.e.use_move(self.enemy,baby,'move/몸통박치기',situational=100,set_damage=True),
            reason_pattern='pouch')
        self.valid()

    def test_fainting_an_unrelated_kangaskhan_does_not_supply_the_maternal_condition(self):
        baby=self.born()
        other=Combatant(self.r,build_pokemon(self.r,'캥카',30,name='unrelated actual mother',
            moves=[],abilities=[],pos=(9,3),extra={'gender':'female'}))
        self.e.everyone.append(other)
        self.e.lose_hp(other,other.hp,source='actual unrelated faint crossing')
        self.assertTrue(other.fainted);self.assertFalse(self.mother.fainted)
        self.protection(baby,True)
        self.faint_mother();self.e.revive(other,20);self.protection(baby,False)
        self.assertEqual(baby.spec[M.KEY]['mother_id'],self.mother.entity_id)
        self.valid()

    def test_paid_press_on_preserves_conscious_protection_at_nonpositive_hp_across_owners(self):
        import taskmaster as T,training_features as F,trainer_feature_acquisition as A
        import action_points as AP
        baby=self.born()
        owner=Combatant(self.r,build_trainer(self.r,'actual maternal Taskmaster',20,
            dict.fromkeys(STATS,10),skills={'협박':6,'명령':6},pos=(2,2),extra={'feats':[F.BRUTAL]}))
        self.e.gm.add_combatant(owner,pos=(2,2),side='party',reason='actual new maternal owner')
        PARTY.configure(self.e,owner,mode='unlimited',reason='actual maternal owner roster',roster=[])
        PARTY.transfer(self.e,self.a,target=self.mother,new_owner=owner,
            reason='actual mother gift; baby keeps its own trainer',request_id='maternal-owner')
        self.e.gm.observe_loyalty(self.mother,6,reason='actual willing trained mother')
        A.acquire_static(self.e,owner,T.CLASS,acquisition_request_id='maternal/taskmaster')
        A.acquire_static(self.e,owner,T.PRESS,acquisition_request_id='maternal/press-on')
        self.e.rulings.add_answer('taskmaster',3,reason='actual chosen completed training',scope='permanent')
        self.e.rulings.add_answer('press_on',True,reason='actual maternal faint reaction choice',scope='permanent')
        self.e.train_pokemon(owner,[(self.mother,[F.BRUTAL])],minutes=30,
            reason='actual maternal Brutal Training',request_id='maternal-training',safe=True)
        self.e.gm.set_injuries(self.mother,value=8,reason='observed current maternal injuries')
        self.e.gm.set_hp(self.mother,value=1,reason='observed current maternal HP')
        self.e.start_round([owner,self.mother,self.enemy]);self.e.start_of_turn(self.enemy,initiative_count=20)
        before=AP.available(owner)
        self.e.lose_hp(self.mother,2,source='actual maternal setting crossing',loss_kind='hp_setting')
        self.assertEqual(self.mother.hp,-1);self.assertFalse(self.mother.fainted)
        self.assertEqual(AP.available(owner),before-1);self.protection(baby,True)
        self.assertEqual((self.mother.spec['trainer_id'],baby.spec['trainer_id']),
                         (owner.entity_id,self.a.entity_id))
        threshold=-(self.mother.base_max_hp*3//10)
        self.e.lose_hp(self.mother,self.mother.hp-threshold,
            source='actual maternal native faint threshold',loss_kind='hp_setting')
        self.assertTrue(self.mother.fainted);self.protection(baby,False)
        self.assertTrue(M.in_pouch(baby));self.valid()

    def test_unknown_actual_mother_has_no_protection_but_native_baby_still_cannot_act(self):
        self.mother.spec.pop('gender');policy=self.policy()
        policy['requirements']=[r for r in policy['requirements'] if r['id']!='mother-fact']
        baby=self.hatch(self.egg(policy=policy));self.assertIsNone(baby.spec[M.KEY]['mother_id'])
        self.begin_enemy();self.protection(baby,False)
        hp=baby.hp
        self.e.use_move(self.enemy,baby,'move/몸통박치기',situational=100,set_damage=True)
        self.assertLess(baby.hp,hp);self.assertFalse(TURN.can_act(self.e,baby))
        self.assertIsNone(M.custody(self.e,baby));self.valid()

    def test_actual_world_is_required_for_pouch_attack_checks_and_support_remains_reachable(self):
        baby=self.born();other=Engine(self.r)
        for fn in (lambda:BODY.targetable(baby),lambda:SETUP.targetable(baby),lambda:M.projection(baby)):
            with self.assertRaisesRegex(ValueError,'actual world'):fn()
        with self.assertRaisesRegex(ValueError,'registered actor'):
            BODY.targetable(baby,engine=other)
        self.assertTrue(BODY.targetable(baby,attack=False))
        heal=self.r.move('move/치유파동')
        self.assertFalse(M.attack_blocked(self.enemy,baby,heal,engine=self.e))
        self.e.gm.set_move(self.enemy,heal['id'],True,reason='actual known external healing support')
        self.begin_enemy();self.e.lose_hp(baby,2,source='observed nonattack loss');hp=baby.hp
        self.e.use_move(self.enemy,baby,heal['id'])
        self.assertGreater(baby.hp,hp);self.protection(baby,True);self.valid()

    def test_mapped_legacy_burst_selects_vulnerable_pouch_body_and_applies_its_actual_effect(self):
        import body_state as B
        baby=self.born();mid='move/울음소리'
        B.observe(self.e,self.mother,[(0,0),(1,0)],reason='actual observed maternal occupied cells')
        B.observe(self.e,baby,[(0,0)],reason='actual observed baby body inside maternal pouch cell')
        self.e.gm.set_move(self.enemy,mid,True,reason='actual known Growl area attack')
        W.observe_location(self.e,self.enemy,{'kind':'grid','cell':[3,2]},reason='actual observed attacker adjacent to the maternal pouch')
        self.begin_enemy();move=self.r.move(mid)
        self.assertTrue(M.target_present(baby,engine=self.e));self.assertFalse(baby.on_field)
        self.assertNotIn(baby,self.e.targets_in_range(self.enemy,move,self.e.everyone,self.mother))
        self.faint_mother()
        self.assertIn(baby,self.e.targets_in_range(self.enemy,move,self.e.everyone,baby))
        self.assertFalse(M.target_present(self.father,engine=self.e))
        before=baby.stages['atk']
        self.e.use_move_on(self.enemy,baby,mid,self.e.everyone)
        self.assertEqual(baby.stages['atk'],before-1)
        self.assertEqual(self.enemy.budget['standard'],0);self.assertEqual(self.enemy.move_uses[mid],1)
        self.assertFalse(baby.on_field);self.assertTrue(M.in_pouch(baby));self.valid()

    def test_mapped_aimed_area_selects_actual_pouch_geometry_only_after_maternal_faint(self):
        import body_state as B,area_targets as AREA
        baby=self.born();mid='move/스피드스타'
        B.observe(self.e,self.mother,[(0,0),(1,0)],reason='actual observed maternal occupied cells')
        B.observe(self.e,baby,[(0,0)],reason='actual observed baby body inside maternal pouch cell')
        self.e.gm.set_move(self.enemy,mid,True,reason='actual known aimed Swift area attack')
        self.begin_enemy();move=AREA.bind(self.e,self.enemy,self.r.move(mid),self.mother.pos)
        self.assertNotIn(baby,self.e.targets_in_range(self.enemy,move,self.e.everyone,self.mother))
        self.faint_mother()
        self.assertIn(baby,self.e.targets_in_range(self.enemy,move,self.e.everyone,baby))
        hp=baby.hp
        self.e.use_move_on(self.enemy,baby,mid,self.e.everyone,aim=self.mother.pos,set_damage=True)
        self.assertLess(baby.hp,hp);self.assertEqual(self.enemy.budget['standard'],0)
        self.assertEqual(self.enemy.move_uses[mid],1);self.assertFalse(baby.on_field);self.valid()

    def test_actual_mapless_frame_derives_pouch_position_but_never_invents_contact_or_area_targets(self):
        import mapless_space as SPACE
        baby=self.born();mid='move/스피드스타'
        self.e.gm.set_move(self.enemy,mid,True,reason='actual known mapless Swift area attack')
        self.e.grid=None
        placements={c.entity_id:'room' for c in (self.a,self.mother,self.father,self.enemy)}
        frame=self.e.gm.observe_mapless_scene(scene_id='maternal-room',places={'room':'actual room'},
            placements=placements,contacts=[],reason='observed actual people and mother with baby in pouch')
        self.assertEqual(frame['positions'][baby.entity_id],frame['positions'][self.mother.entity_id])
        self.assertFalse(self.e.adjacent(self.enemy,baby))
        self.e.gm.observe_mapless_targets(self.enemy,event_id='pouch-area',move_id=mid,
            landmark_id='room',target_ids=[baby.entity_id],reason='GM observes only the actual pouch baby inside this area')
        self.begin_enemy();move=self.r.move(mid)
        self.assertEqual(self.e.targets_in_range(self.enemy,move,self.e.everyone,baby),[])
        self.faint_mother();baby=self.reload(baby)
        self.assertEqual(self.e.targets_in_range(self.enemy,move,self.e.everyone,baby),[baby])
        self.assertFalse(self.e.adjacent(self.enemy,baby))
        self.assertEqual(self.e.targets_in_range(self.enemy,self.r.move('move/몸통박치기'),self.e.everyone,baby),[])
        hp=baby.hp
        self.e.use_move_on(self.enemy,baby,mid,self.e.everyone,set_damage=True)
        self.assertLess(baby.hp,hp);self.assertEqual(self.enemy.budget['standard'],0)
        self.assertEqual(self.enemy.move_uses[mid],1);self.assertTrue(SPACE.active(self.e))
        self.assertTrue(M.in_pouch(baby));self.assertFalse(baby.on_field);self.valid()


if __name__=='__main__':unittest.main()
