"""Live allegiance is not ownership; absent observations grant no foe action."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from native_scenario_fixture import assert_rejected_unchanged
import test_book_trickster_full as TRICK
import test_book_rider_csv_full as RIDER
import trickster as T
import conquerors_march as CM
import class_passive_combat as CP
import action_points as AP
import world_entities as W


class AllegianceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=Rules(ROOT,ruleset='core')
        cls.rider_rules=Rules(ROOT,ruleset='all')

    def trickster(self):
        case=TRICK.TricksterFullTests();case.rules=self.rules;case.setUp()
        self.addCleanup(case.doCleanups)
        case.family()
        return case

    def observe_side(self,actor,value):
        if value=='absent':
            del actor.side
            actor.spec.pop('side',None)
        else:
            actor.side=value
            actor.spec['side']=value

    def test_actual_status_hits_offer_flourish_only_for_known_different_sides(self):
        for role in ('source','target'):
            for side in ('absent',None,'party','enemy'):
                with self.subTest(role=role,side=side):
                    case=self.trickster()
                    actor=case.p if role=='source' else case.foe
                    self.observe_side(actor,side)
                    expected=side=='enemy' if role=='target' else side=='party'
                    row=case.use('move/애교부리기',face=20)
                    self.assertEqual(case.foe.entity_id in row.get('trickster_accuracy',{}),expected)
                    self.assertEqual(T.flourish_applies(case.e,case.p,case.foe,row['move']),expected)
                    if side=='absent':self.assertFalse(hasattr(actor,'side'))

    def test_unknown_target_cannot_fund_hit_escape_or_nonfoe_encore(self):
        case=self.trickster()
        self.observe_side(case.foe,'absent')
        case.source_condition('독')
        row=case.use('move/애교부리기',face=20)
        case.reject(lambda:case.e.stacked_deck(case.t,case.p,case.foe,row['id'],'독'),
                    'actual completed hit on a foe')
        case.reject(lambda:case.e.escape_artist(case.t,case.p,case.foe,'move/애교부리기',(2,3)),
                    'adjacent foe')
        case.reject(lambda:case.e.encore_performance(case.t,case.p,row['id'],'standard'),
                    'not targeting foes')
        self.assertFalse(hasattr(case.foe,'side'))

    def test_actual_self_encore_needs_no_side_observation(self):
        case=self.trickster()
        self.observe_side(case.p,'absent')
        row=case.use('move/웅크리기',target=case.p)
        before=case.p.stages['spa']
        case.e.encore_performance(case.t,case.p,row['id'],'stage',stat='spa')
        self.assertEqual(case.p.stages['spa'],before+1)
        self.assertFalse(hasattr(case.p,'side'))

    def test_actual_mounted_hit_without_known_foe_never_offers_or_pays_reprisal(self):
        for role,side in (('attacker','absent'),('attacker',None),
                          ('mount','absent'),('mount',None),('attacker','party')):
            with self.subTest(role=role,side=side):
                case=RIDER.RiderFullTests();case.rules=self.rider_rules;case.setUp()
                self.addCleanup(case.tearDown)
                case.setup(feature=CM.REPRISAL)
                case.answer('rider_reprisal',{'use':True,'options':{'set_damage':True}})
                self.observe_side(case.enemy if role=='attacker' else case.p,side)
                case.combat(case.enemy)
                before=(case.enemy.hp,case.p.hp,AP.available(case.a))
                with patch.object(Engine,'d20',return_value=15):
                    case.e.use_move_on(case.enemy,case.p,'move/몸통박치기',case.e.everyone,set_damage=True)
                self.assertLess(case.p.hp,before[1])
                self.assertEqual((case.enemy.hp,AP.available(case.a)),(before[0],before[2]))
                self.assertFalse(any(row.get('rider_reprisal') for row in case.e._move_completions.values()))

    def test_wild_registration_is_legal_but_explicit_owner_must_already_resolve(self):
        engine=Engine(self.rules,seed=86)
        wild=Combatant(self.rules,build_pokemon(self.rules,'Pikachu',20,abilities=[],wild=True))
        engine.gm.add_combatant(wild,reason='actual unowned wild recipient')
        self.assertIs(W.actor_index(engine)[wild.entity_id],wild)
        assert_rejected_unchanged(engine,lambda:CP._owner(engine,wild),
                                  reason_pattern='actual trainer owner identity')
        pending=Combatant(self.rules,build_pokemon(self.rules,'Pikachu',20,abilities=[],
            extra={'trainer_id':'trainer/not-registered'}))
        before=deepcopy(pending.spec)
        assert_rejected_unchanged(engine,lambda:engine.gm.add_combatant(pending,
            reason='deliberately unresolved explicit owner'),reason_pattern='actual trainer owner identity')
        self.assertNotIn(pending.entity_id,W.actor_index(engine))
        self.assertEqual(pending.spec,before)


if __name__=='__main__':unittest.main()
