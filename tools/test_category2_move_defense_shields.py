"""Actual Shield Move provenance and the two deferred dive policy gates.

These tests do not execute or certify Phantom/Shadow Force disappearance,
return, targeting or duration. Protect uses its existing native effect adapter;
this suite does not certify its separate source-trigger timing contract.
"""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from grid import Grid
import move_defense_reactions as DEFENSE
import world_entities as WORLD


class MoveDefenseShieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')

    def fixture(self):
        engine=Engine(self.rules,seed=545)
        engine.grid=Grid(5,3)
        stats=dict(hp=30,atk=10,**{'def':10},spa=10,spd=10,spe=10)
        def actor(name,pos,side,moves):
            return Combatant(self.rules,{'id':'trainer/'+name,'name':name,'kind':'trainer',
                'size':'중형','level':20,'stats':dict(stats),'skills':{'곡예':4,'육상':4,'집중':3},
                'movement':{'land':6},'movement_basis':'current','moves':moves,'pos':pos,'side':side})
        shield=actor('actual-shield-owner',(1,1),'party',['move/방어'])
        attacker=actor('actual-shield-attacker',(2,1),'opponent',['move/몸통박치기'])
        for participant in (shield,attacker):engine.gm.add_combatant(participant)
        engine.start_round(engine.everyone);engine.start_of_turn(shield)
        engine.use_move(shield,shield,'move/방어',set_damage=True)
        self.assertIsNotNone(shield.shield)
        engine.end_of_turn(shield);engine.start_of_turn(attacker)
        return engine,shield,attacker

    def proof(self,engine,shield):
        proof=shield.shield['_native_shield']
        row=engine._move_completions[proof['completion_id']]
        self.assertEqual(proof,{'completion_id':row['id'],'source_id':'move/방어','actor_id':shield.entity_id})
        self.assertIs(row['actor'],shield)
        self.assertEqual(row['move_id'],'move/방어')
        self.assertEqual(row['phase'],'complete')
        self.assertIn('방패',row['move']['keywords'])
        self.assertEqual(shield.move_uses['move/방어'],1)
        return proof,row

    def test_actual_protect_completion_owns_shield_and_native_attack_consumes_it_once(self):
        engine,shield,attacker=self.fixture();self.proof(engine,shield)
        hp=shield.hp
        self.assertTrue(DEFENSE.shield_allowed(engine,attacker,shield,engine.r.move('move/몸통박치기')))
        dealt=engine.use_move(attacker,shield,'move/몸통박치기',set_damage=True)
        self.assertEqual(dealt,0);self.assertEqual(shield.hp,hp)
        self.assertIsNone(shield.shield)
        row=list(engine._move_completions.values())[-1]
        self.assertFalse(row['results'][shield.entity_id]['hit'])
        self.assertEqual(row['results'][shield.entity_id]['dealt'],0)
        self.assertEqual(attacker.move_uses['move/몸통박치기'],1)

    def test_actual_dive_source_rows_ignore_native_shield_as_policy_query_only(self):
        engine,shield,attacker=self.fixture();self.proof(engine,shield)
        before=engine.export_state()
        for uid,source_row in (('move/고스트다이브',314),('move/섀도다이브',320)):
            with self.subTest(move=uid):
                move=engine.r.move(uid);mechanics,confidence=engine.r.move_mech(uid)
                self.assertEqual(move['_source']['file'],'db/moves.csv')
                self.assertEqual(move['_source']['record_span'],[source_row,source_row])
                self.assertIn('방패 키워드',move['effect'])
                effects=mechanics['effects_exec']
                self.assertTrue(any('shield' in effect.get('unavoidable_by',()) for effect in effects))
                self.assertIn('shield',engine.r.move_defense_policy['prohibited_moves'][uid])
                self.assertFalse(DEFENSE.shield_allowed(engine,attacker,shield,move))
                self.assertEqual(engine.export_state(),before)
        self.assertFalse(engine.r.move_defense_policy['source_specific_disappearance_implemented'])

    def test_changed_completion_owner_or_source_provenance_is_rejected_without_consumption(self):
        engine,shield,attacker=self.fixture();original=deepcopy(shield.shield)
        dive=engine.r.move('move/고스트다이브')
        for key,value in (('completion_id','move-complete:invented'),
                          ('actor_id',attacker.entity_id),('source_id','move/몸통박치기')):
            with self.subTest(changed=key):
                shield.shield=deepcopy(original);shield.shield['_native_shield'][key]=value
                before=deepcopy(shield.shield);rng=engine.rng.getstate()
                with self.assertRaisesRegex(ValueError,'shield source provenance'):
                    DEFENSE.shield_allowed(engine,attacker,shield,dive)
                self.assertEqual(shield.shield,before)
                self.assertEqual(engine.rng.getstate(),rng)
        shield.shield=original

    def test_plain_non_move_shield_does_not_gain_native_move_bypass_provenance(self):
        engine,shield,attacker=self.fixture()
        effect=deepcopy(shield.shield);effect.pop('_native_shield')
        DEFENSE.hold_shield(engine,shield,effect,{'engine':engine})
        self.assertNotIn('_native_shield',shield.shield)
        for uid in ('move/고스트다이브','move/섀도다이브'):
            self.assertTrue(DEFENSE.shield_allowed(engine,attacker,shield,engine.r.move(uid)))

    def test_cold_json_restore_retains_actual_producer_and_ordinary_attack_consumption(self):
        engine,shield,attacker=self.fixture();proof,_=self.proof(engine,shield)
        state=json.loads(json.dumps(engine.export_state(),ensure_ascii=False))
        restored=Engine.import_state(Rules(ROOT,ruleset='core'),state)
        index=WORLD.actor_index(restored)
        shield,attacker=(index[c.entity_id] for c in (shield,attacker))
        self.assertEqual(shield.shield['_native_shield'],proof)
        self.proof(restored,shield)
        self.assertFalse(DEFENSE.shield_allowed(restored,attacker,shield,restored.r.move('move/섀도다이브')))
        hp=shield.hp
        self.assertEqual(restored.use_move(attacker,shield,'move/몸통박치기',set_damage=True),0)
        self.assertEqual(shield.hp,hp);self.assertIsNone(shield.shield)

    def test_gm_snapshot_restore_reinstates_one_actual_shield_without_replaying_producer(self):
        engine,shield,attacker=self.fixture();proof,_=self.proof(engine,shield)
        snapshot=engine.gm.snapshot()
        engine.use_move(attacker,shield,'move/몸통박치기',set_damage=True)
        self.assertIsNone(shield.shield)
        engine.gm.restore(snapshot)
        index=WORLD.actor_index(engine);shield,attacker=(index[c.entity_id] for c in (shield,attacker))
        self.assertEqual(shield.shield['_native_shield'],proof)
        self.proof(engine,shield)
        self.assertEqual(attacker.move_uses.get('move/몸통박치기',0),0)
        self.assertEqual(engine.use_move(attacker,shield,'move/몸통박치기',set_damage=True),0)
        self.assertIsNone(shield.shield)
        self.assertEqual(shield.move_uses['move/방어'],1)


if __name__=='__main__':unittest.main()
