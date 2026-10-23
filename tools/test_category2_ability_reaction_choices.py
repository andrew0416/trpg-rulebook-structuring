"""Independent post-return action, lifetime, and native-receipt boundaries."""
from copy import deepcopy
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
import test_category2_perish_body as FIXTURE
import ability_reaction_choices as REACTION
import perish_body as PB
import action_resources as RESOURCES
import initiative_interrupts as INIT
import turn as TURN
import state_grants as G
import passive_events as PASSIVE
import heavy_injury_adapter as HEAVY


class AbilityReactionChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        FIXTURE.PerishBodyTests.setUpClass();cls.r=FIXTURE.PerishBodyTests.r
    setUp=FIXTURE.PerishBodyTests.setUp
    actor=FIXTURE.PerishBodyTests.actor
    watch=FIXTURE.PerishBodyTests.watch
    offer=FIXTURE.PerishBodyTests.offer
    choose=FIXTURE.PerishBodyTests.choose
    count=FIXTURE.PerishBodyTests.count
    fresh=FIXTURE.PerishBodyTests.fresh

    def test_off_turn_payment_reserves_upcoming_standard_without_advancing_owner_clock(self):
        event=self.offer();serial=self.t.custom_conditions.get('combat_turn_serial',0)
        self.choose(event)
        self.assertEqual(RESOURCES.pending(self.t),{'standard':1})
        self.assertEqual(self.t.custom_conditions.get('combat_turn_serial',0),serial)
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        self.assertEqual(self.t.budget,{'standard':0,'shift':1,'swift':1})
        self.assertEqual(RESOURCES.pending(self.t),{})
        self.assertEqual(self.count(self.t)['applications'][-1]['remaining'],2)
        self.fresh()

    def test_closed_owner_unused_budget_is_not_current_payment(self):
        self.e.end_of_turn(self.a);self.e.start_round(self.e.everyone)
        self.e.start_of_turn(self.t,initiative_count=30);self.e.end_of_turn(self.t)
        stale=deepcopy(self.t.budget)
        self.e.start_of_turn(self.a,initiative_count=20)
        event=self.offer();self.choose(event)
        self.assertEqual(self.t.budget,stale)
        self.assertEqual(RESOURCES.pending(self.t),{'standard':1})
        self.assertEqual(REACTION._offer(self.e,event)[1]['attempt']['payment']['payment'],'next')

    def nested_attack(self,*,spent):
        self.e.end_of_turn(self.a);self.e.start_of_turn(self.t,initiative_count=10)
        if spent:self.assertTrue(TURN.spend(self.e,self.t,'standard','actual prior Standard'))
        trigger={'kind':'turn','actor_id':self.t.entity_id,
                 'serial':self.t.custom_conditions['combat_turn_serial'],'round':self.e.round_no}
        q=INIT.queue(self.e,[{'id':'nested-attack','actor_id':self.a.entity_id,
            'source':'homebrew/declared-reaction','priority':10,'mode':'reaction',
            'payment':'next','budget':{'standard':1},'clock':'none'}],trigger=trigger)
        INIT.begin(self.e,q['window_id'],'nested-attack')
        event=self.offer();self.choose(event)
        self.assertIs(self.e._active_turn_actor,self.a)
        INIT.finish(self.e)
        self.assertIs(self.e._active_turn_actor,self.t)
        return event

    def test_actual_suspended_owner_pays_available_current_standard(self):
        event=self.nested_attack(spent=False)
        self.assertEqual(self.t.budget['standard'],0)
        self.assertEqual(RESOURCES.pending(self.t),{})
        self.assertEqual(REACTION._offer(self.e,event)[1]['attempt']['payment']['payment'],'current')
        self.fresh()

    def test_suspended_owner_with_spent_standard_reserves_next_owner_turn(self):
        event=self.nested_attack(spent=True)
        self.assertEqual(self.t.budget['standard'],0)
        self.assertEqual(RESOURCES.pending(self.t),{'standard':1})
        self.assertEqual(REACTION._offer(self.e,event)[1]['attempt']['payment']['payment'],'next')
        self.fresh()

    def test_later_actual_action_closes_optional_offer_without_payment(self):
        event=self.offer();self.assertTrue(TURN.spend(self.e,self.a,'shift','actual later action'))
        self.assertEqual(self.e.pending_ability_reactions(),[])
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event)
        self.assertEqual(self.e.export_state(),before)

    def test_source_withdrawal_rejects_activation_and_explicit_decline_remains_free(self):
        event=self.offer();G.replace_baseline(self.e,self.t,'abilities',[])
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(event)
        self.assertEqual(self.e.export_state(),before)
        self.choose(event,use=False)
        self.assertEqual(RESOURCES.pending(self.t),{})
        self.assertNotIn(PB.KEY,self.t.spec)

    def test_defense_child_return_is_used_instead_of_parent_hit_assertion(self):
        G.replace_baseline(self.e,self.t,'abilities',['멸망의바디','회피'])
        self.watch()
        self.e.watch_move_defense(self.t,[{'actor_id':self.t.entity_id,'source':'ability/회피'}],
                                  reason='actual defender routing before Reaction')
        with self.assertRaises(PASSIVE.PassiveEventPending):
            self.e.use_move(self.a,self.t,'move/몸통박치기',set_damage=True)
        parent=self.e._passive_pending
        self.e.choose_move_defense(parent,self.t,use=False,reason='decline Dodge')
        offer=self.e.pending_ability_reactions()[0];event=offer['event_id']
        self.assertNotEqual(event,parent)
        self.assertEqual(self.e._passive_events[event]['defense_parent'],parent)
        before=self.e.export_state()
        with self.assertRaises(ValueError):self.choose(parent)
        self.assertEqual(self.e.export_state(),before)
        self.choose(event);self.fresh()

    def test_late_adapter_failure_rolls_back_action_frequency_frame_and_both_counts(self):
        event=self.offer();before=self.e.export_state();native=PB.activate
        def fail(engine,owner,plan):
            native(engine,owner,plan)
            raise ValueError('late adapter failure after both grants')
        with patch.object(PB,'activate',side_effect=fail):
            with self.assertRaisesRegex(ValueError,'late adapter failure'):self.choose(event)
        self.assertEqual(self.e.export_state(),before)
        self.choose(event)
        self.assertEqual(len(self.t._action_history),1)

    def test_cold_cache_normalization_preserves_policy_and_source_memo_override_detection(self):
        import custom_condition_effects as CUSTOM, state_codec as CODEC
        cold=FIXTURE.Rules(ROOT,ruleset='core')
        clean=CODEC.rules_fingerprint(cold)
        CUSTOM.by_name(cold,PB.NAME)
        self.assertEqual(CODEC.rules_fingerprint(cold),clean)
        saved=deepcopy(cold._custom_condition_policy)
        cold._custom_condition_policy['sources']['move/멸망의노래']['raw']['value']=4
        self.assertNotEqual(CODEC.rules_fingerprint(cold),clean)
        cold._custom_condition_policy=saved
        cold._custom_condition_source_records.add(('input/db/moves.csv',539,'0'*64))
        self.assertNotEqual(CODEC.rules_fingerprint(cold),clean)

    def test_unresolved_heavy_attack_does_not_offer_after_external_acknowledgement(self):
        self.t.injuries=5;self.watch()
        with self.assertRaises(HEAVY.HeavyPending):
            self.e.use_move(self.a,self.t,'move/몸통박치기',set_damage=True)
        self.assertEqual(self.e.pending_ability_reactions(),[])
        packet=self.e._heavy_events[self.e._heavy_pending]
        HEAVY.acknowledge_ruling(self.e,packet['event_id'],self.t,
            expected_current_state=HEAVY.observe(self.t),ruling='explicit GM observation',
            disposition=HEAVY.ContinuationDisposition.CANCELLED_BY_RULING,
            continuation_reason='abandoned caller is not resumed')
        self.assertEqual(self.e.pending_ability_reactions(),[])
        self.assertNotIn(PB.KEY,self.t.spec)


if __name__=='__main__':unittest.main()
