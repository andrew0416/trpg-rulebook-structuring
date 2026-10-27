"""Complete KR/EN marking scopes on paid native hits and existing consumers."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools'),str(ROOT/'examples')]
import test_book_type_ace_reactions as F
import declared_skill_ranks as DECLARED
from engine import Engine,Rules
import attack_damage_history as DAMAGE
import combat_timing as TIME
import frequency as FREQUENCY
import gm_state as GM
import passive_events as EVENTS
import physics_maneuvers as MANEUVERS
import state_codec as CODEC
import type_ace as TA
import world_entities as WORLD


class CloseQuartersMarkingSourceTests(unittest.TestCase):
    setUpClass=classmethod(F.TypeAceReactionTests.setUpClass.__func__)
    setUp=F.TypeAceReactionTests.setUp
    setup=F.TypeAceReactionTests.setup
    add=F.TypeAceReactionTests.add
    acquire=F.TypeAceReactionTests.acquire
    family=F.TypeAceReactionTests.family
    known=F.TypeAceReactionTests.known
    native=F.TypeAceReactionTests.native
    selected=F.TypeAceReactionTests.selected
    completed=F.TypeAceReactionTests.completed
    combat=F.TypeAceReactionTests.combat
    communication=F.TypeAceReactionTests.communication
    answer=F.TypeAceReactionTests.answer
    rejected=F.TypeAceReactionTests.rejected
    valid=F.TypeAceReactionTests.valid

    def choice(self,actor,value,*,targets=()):
        scope=TA.close_quarters_source_choices(self.e.r)['decision_scope']
        return TA.choose_close_quarters_source(self.e,actor,
            dict(value=value,reason='explicit complete source for this actual owner',scope=scope),
            active_targets=tuple(p.entity_id for p in targets))

    def pair(self,variant='korean_one_foe_per_marker',*,unequal=False):
        if unequal:DECLARED.configure(self.rules)
        self.family('격투','Close Quarters Mastery','Face Me Whelp','Smashing Punishment','Brawler')
        self.u=self.add('second actual marking owner','trainer',(1,4),classes=[],feats=[],exp_bank=100,
            type_link_skills={'격투':'전투'})
        if unequal:self.e.gm.set_skill(self.u,'전투',9,reason='actual declared ordinary Legendary rank')
        self.v=self.add('second actual marker','pokemon',(4,3),trainer_id=self.u.entity_id,types=['격투'])
        self.w=self.add('second actual owned partner','pokemon',(8,9),trainer_id=self.u.entity_id,types=['격투'])
        for p in (self.v,self.w):self.e.gm.observe_loyalty(p,6,reason='actual willing owned Pokemon')
        self.acquire(branch='격투',actor=self.u)
        for feature in ('Close Quarters Mastery','Face Me Whelp','Smashing Punishment'):
            self.acquire(feature,'격투',actor=self.u)
        self.choice(self.t,variant);self.choice(self.u,variant)
        self.e.gm.set_position(self.p,(3,2),reason='actual first adjacent marker')
        self.e.gm.set_position(self.q,(5,2),reason='actual third party melee target')
        self.communication()
        self.e.gm.observe_sensory_environment(self.u,self.v,paths={'auditory':True},present=True,
            reason='actual second owner Order delivery')
        self.combat(self.t)
        TA.activate(self.e,self.t,self.p,'Close Quarters Mastery')
        self.start(self.u,29)
        TA.activate(self.e,self.u,self.v,'Close Quarters Mastery')
        self.start(self.p,28)

    def start(self,actor,count):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.start_of_turn(actor,initiative_count=count)

    def next_round(self,actor,count):
        if self.e._active_turn_actor is not None:self.e.end_of_turn(self.e._active_turn_actor)
        self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.start_of_turn(actor,initiative_count=count)

    def both(self):
        self.native(self.p,self.b,'move/태권당수')
        self.start(self.v,27)
        self.native(self.v,self.b,'move/태권당수')
        self.assertEqual(set(TA.markers(self.e,self.b)),{self.p,self.v})

    def mark_rows(self,target):
        return [r for r in TIME.records(target) if r.get('ace_marker') is not None]

    def cold(self):
        identities={k:getattr(self,k).entity_id for k in ('t','p','q','b','u','v','w') if hasattr(self,k)}
        rules=Rules(ROOT,ruleset='core')
        self.e=CODEC.load_engine(rules,json.loads(json.dumps(self.e.export_state(),ensure_ascii=False)))
        index=WORLD.actor_index(self.e)
        for key,identity in identities.items():setattr(self,key,index[identity])

    def test_korean_two_markers_one_foe_cap_pair_refresh_and_independent_native_expiry(self):
        self.pair();self.both()
        other=self.add('actual second foe','pokemon',(3,3),side='foe')
        self.next_round(self.p,29)
        hp=other.hp
        self.native(self.p,other,'move/태권당수')
        self.assertLess(other.hp,hp)
        self.assertFalse(TA.markers(self.e,other))
        self.assertEqual(self.p.budget['standard'],0)
        self.pair();self.both()
        rows={r['ace_marker'].entity_id:deepcopy(r['count_deadline']) for r in self.mark_rows(self.b)}
        self.next_round(self.p,29)
        self.native(self.p,self.b,'move/태권당수')
        refreshed={r['ace_marker'].entity_id:r for r in self.mark_rows(self.b)}
        self.assertEqual(tuple(refreshed[self.v.entity_id]['count_deadline']),tuple(rows[self.v.entity_id]))
        self.assertEqual(tuple(refreshed[self.p.entity_id]['count_deadline']),(self.e.round_no+1,29))
        self.e.end_of_turn(self.p);self.e.at_initiative_count(27)
        self.assertEqual(TA.markers(self.e,self.b),[self.p])
        self.e.end_round();self.e.start_round(self.e.everyone);self.e.at_initiative_count(29)
        self.assertFalse(TA.markers(self.e,self.b));self.valid()

    def test_english_one_marker_multiple_foes_and_historical_korean_cap_survives_choice_change(self):
        self.pair('english_one_marker_per_foe')
        self.native(self.p,self.b,'move/태권당수')
        other=self.add('second actual English foe','pokemon',(3,3),side='foe')
        self.next_round(self.p,29);self.native(self.p,other,'move/태권당수')
        self.start(self.v,29);self.native(self.v,self.b,'move/태권당수')
        self.assertEqual(TA.markers(self.e,self.b),[self.p])
        self.assertEqual(TA.markers(self.e,other),[self.p])
        self.valid()
        self.pair();self.native(self.p,self.b,'move/태권당수')
        original=deepcopy(self.mark_rows(self.b)[0][TA.CQM_CHOICE])
        original_event=self.mark_rows(self.b)[0]['ace_mark_event']
        self.choice(self.t,'english_one_marker_per_foe')
        self.next_round(self.p,29)
        self.rejected(lambda:self.native(self.p,self.b,'move/태권당수'),'current source adoption')
        self.choice(self.t,'english_one_marker_per_foe',targets=(self.p,))
        other=self.add('new actual foe after source choice','pokemon',(3,3),side='foe')
        self.e.gm.snapshot('current-source-before-refused-target')
        self.native(self.p,other,'move/태권당수')
        self.assertFalse(TA.markers(self.e,other))
        self.assertEqual(self.mark_rows(self.b)[0][TA.CQM_CHOICE],original)
        self.e.gm.restore('current-source-before-refused-target',reason='restore actual budget before alternate same-pair refresh')
        self.native(self.p,self.b,'move/태권당수')
        self.assertEqual(self.mark_rows(self.b)[0][TA.CQM_CHOICE]['choice']['value'],'english_one_marker_per_foe')
        self.assertEqual(self.e._passive_events[original_event]['close_quarters_hit']['sustain'][TA.CQM_CHOICE],original)
        other=WORLD.actor_index(self.e)[other.entity_id]
        self.next_round(self.p,30);self.native(self.p,other,'move/태권당수')
        self.assertEqual(TA.markers(self.e,other),[self.p])
        self.cold()
        self.assertEqual(self.e._passive_events[original_event]['close_quarters_hit']['sustain'][TA.CQM_CHOICE],original)
        self.valid()

    def test_face_me_each_distinct_real_marker_uses_own_rank_adjacency_and_whole_target_set(self):
        self.pair(unequal=True);self.both()
        self.e.end_of_turn(self.v)
        self.e.gm.snapshot('two-real-markers')
        for target_name,move,expected_accuracy,expected_damage in (
                ('q','move/몸통박치기',-7,-20),
                ('p','move/몸통박치기',-4,-10),
                ('q','move/지진',0,0)):
            with self.subTest(target=target_name,move=move):
                self.e.gm.restore('two-real-markers',reason='restore actual independent grants and budgets')
                self.start(self.b,26);acc=[];damage=[]
                original_accuracy=TA.accuracy;original_damage=TA.damage_bonus
                def accuracy(*args):
                    result=original_accuracy(*args)
                    if args[1] is self.b:acc.append(result)
                    return result
                def bonus(*args):
                    result=original_damage(*args)
                    if args[1] is self.b:damage.append(result)
                    return result
                with patch.object(TA,'accuracy',side_effect=accuracy),patch.object(TA,'damage_bonus',side_effect=bonus):
                    self.native(self.b,getattr(self,target_name),move,face=19)
                self.assertTrue(acc);self.assertEqual(set(acc),{expected_accuracy})
                self.assertTrue(damage);self.assertEqual(set(damage),{expected_damage})
                if move=='move/지진':
                    self.assertTrue({self.p,self.v}<=set(self.completed(self.b)['targets']))
                self.assertEqual(TA.rank(self.e,self.u,'격투'),9)
                self.valid()
        self.e.gm.restore('two-real-markers',reason='restore actual markers for adjacency control')
        self.e.gm.set_position(self.v,(9,8),reason='second marker is no longer adjacent')
        self.start(self.b,26)
        move=self.e.r.move('move/몸통박치기')
        self.assertEqual(TA.accuracy(self.e,self.b,self.q,move,{}),-3)
        self.assertEqual(TA.damage_bonus(self.e,self.b,self.q,move,1),-10)

    def test_actual_disengage_leaves_one_or_both_markers_with_independent_smashing_payments(self):
        self.pair();self.both();self.e.end_of_turn(self.v)
        self.e.gm.set_position(self.q,(9,10),reason='actual third party clears the one-marker departure destination')
        self.answer('type_ace_choice',True)
        self.e.gm.snapshot('actual-marked-departure')
        for destination,expected in (((5,2),('p',)),((5,1),('p','v'))):
            with self.subTest(destination=destination):
                self.e.gm.restore('actual-marked-departure',reason='actual alternate departure geometry')
                self.start(self.b,26);before=len(DAMAGE.records(self.b))
                with patch.object(Engine,'d20',return_value=1):TA.disengage(self.e,self.b,[destination])
                self.assertEqual(tuple(self.b.pos),destination)
                attacks=[r for r in self.e._move_completions.values() if r['move_id']=='struggle' and r['phase']=='complete']
                self.assertEqual({r['actor'] for r in attacks},{getattr(self,k) for k in expected})
                self.assertEqual(len(DAMAGE.records(self.b))-before,len(expected))
                for marker_name,owner_name in (('p','t'),('v','u')):
                    owner=getattr(self,owner_name)
                    used=FREQUENCY.state(owner)['activations'].get(TA.uid('Smashing Punishment'),{}).get('used',0)
                    self.assertEqual(used,int(marker_name in expected))
                for attack in attacks:
                    self.assertEqual(attack['move']['type'],'격투')
                    self.assertTrue(all(r['hit'] for r in attack['results'].values()))
                    actual=[e for e in self.e._passive_events.values() if e.get('completion_id')==attack['id']]
                    self.assertTrue(actual);self.assertTrue(all(e['critical'] for e in actual))
                self.valid()

    def test_korean_real_multi_hit_choice_keeps_completed_cost_damage_and_original_source_after_restore(self):
        self.pair();self.e.gm.set_position(self.b,(4,2),reason='actual first Burst foe')
        other=self.add('second actual Burst foe','pokemon',(3,3),side='foe')
        hp={p.entity_id:p.hp for p in (self.b,other)}
        self.selected('Brawler','struggle')
        row=self.completed();completion=row['id']
        self.assertEqual(self.p.budget['standard'],0)
        self.assertTrue(all(p.hp<hp[p.entity_id] for p in (self.b,other)))
        self.assertFalse(TA.markers(self.e,self.b));self.assertFalse(TA.markers(self.e,other))
        pending=TA.pending_close_quarters_marks(self.e,self.p)
        self.assertEqual(pending,[{'completion_id':completion,'targets':[p.entity_id for p in row['targets'] if p.side=='foe']}])
        self.rejected(lambda:TA.resolve_close_quarters_mark(self.e,self.p,completion,target=self.q),'actual completed eligible')
        other_id=other.entity_id;self.choice(self.t,'english_one_marker_per_foe',targets=(self.p,))
        self.cold();other=WORLD.actor_index(self.e)[other_id]
        self.e.gm.snapshot('actual-choice-before-selection')
        before=(self.p.budget.copy(),deepcopy(self.t._action_history),self.e.rng.getstate(),other.hp,len(self.e._move_completions))
        result=TA.resolve_close_quarters_mark(self.e,self.p,completion,target=other)
        self.assertEqual(result['status'],'selected')
        self.assertEqual(TA.markers(self.e,other),[self.p]);self.assertFalse(TA.markers(self.e,self.b))
        self.assertEqual((self.p.budget.copy(),self.t._action_history,self.e.rng.getstate(),other.hp,len(self.e._move_completions)),before)
        mark=self.mark_rows(other)[0]
        self.assertEqual(mark[TA.CQM_CHOICE]['choice']['value'],'korean_one_foe_per_marker')
        facts=next(e['close_quarters_hit'] for e in self.e._passive_events.values() if e['id']==mark['ace_mark_event'])
        self.assertEqual(tuple(mark['count_deadline']),(facts['round']+1,facts['count']))
        self.rejected(lambda:TA.resolve_close_quarters_mark(self.e,self.p,completion,target=self.b),'already resolved')
        self.e.gm.restore('actual-choice-before-selection',reason='restore completed attack and unresolved target choice')
        self.assertEqual(len(TA.pending_close_quarters_marks(self.e,self.p)),1)
        self.e.end_of_turn(self.p);self.e.end_round();self.e.start_round(self.e.everyone)
        self.e.at_initiative_count(facts['count'])
        self.assertFalse(TA.pending_close_quarters_marks(self.e,self.p))
        self.rejected(lambda:TA.resolve_close_quarters_mark(self.e,self.p,completion,target=self.b),'expired')
        self.valid()

    def test_existing_outgoing_target_refreshes_on_real_burst_without_first_recipient_choice(self):
        self.pair();self.native(self.p,self.b,'move/태권당수')
        other=self.add('second actual Burst foe','pokemon',(3,3),side='foe')
        self.next_round(self.p,29);self.selected('Brawler','struggle')
        self.assertEqual(TA.markers(self.e,self.b),[self.p])
        self.assertFalse(TA.markers(self.e,other))
        self.assertFalse(TA.pending_close_quarters_marks(self.e,self.p))
        self.assertEqual(tuple(self.mark_rows(self.b)[0]['count_deadline']),(self.e.round_no+1,29))
        self.valid()

    def test_legacy_unbound_history_stays_incoming_exclusive_and_current_adoption_precedes_all_costs(self):
        self.pair('english_one_marker_per_foe');self.native(self.p,self.b,'move/태권당수')
        # Exact pre-repair schema projection of an actual paid hit: only the new
        # source metadata/seal is absent. Actor/recipient/result/deadline stay real.
        mark=self.mark_rows(self.b)[0];event=self.e._passive_events[mark['ace_mark_event']]
        mark.pop(TA.CQM_CHOICE);event['close_quarters_hit']['sustain'].pop(TA.CQM_CHOICE)
        event.pop('intent_fingerprint',None);EVENTS._bind_intent(self.e,event)
        source=self.p.spec['_class_passive_combat']['sustains'][TA.uid('Close Quarters Mastery')]
        source.pop(TA.CQM_CHOICE);self.t.spec.pop(TA.CQM_CHOICE)
        self.next_round(self.p,29)
        self.rejected(lambda:self.native(self.p,self.b,'move/태권당수'),'source choice')
        self.rejected(lambda:self.selected('Brawler','struggle'),'source choice')
        self.rejected(lambda:MANEUVERS.trip(self.e,self.p,self.b,challenger_skill='전투',
            defender_skill='전투',fixed_accuracy=10,challenger_options={'fixed':[6]*6},
            defender_options={'fixed':[1]*6}),'source choice')
        facts=deepcopy(event['close_quarters_hit'])
        before=(deepcopy(CODEC.dump_engine(self.e)),self.e.rng.getstate(),deepcopy(self.e.rulings.log))
        original_rec=GM.GMState._rec
        def fail_receipt(gm,*args,**kwargs):
            result=original_rec(gm,*args,**kwargs)
            if args[0]=='접근전의 달인 출처 선택':raise RuntimeError('actual original GM receipt failed')
            return result
        with patch.object(GM.GMState,'_rec',fail_receipt),self.assertRaisesRegex(RuntimeError,'original GM receipt'):
            self.choice(self.t,'korean_one_foe_per_marker',targets=(self.p,))
        self.assertEqual((CODEC.dump_engine(self.e),self.e.rng.getstate(),self.e.rulings.log),before)
        self.choice(self.t,'korean_one_foe_per_marker',targets=(self.p,))
        self.choice(self.u,'korean_one_foe_per_marker',targets=(self.v,))
        self.start(self.v,29);self.native(self.v,self.b,'move/태권당수')
        self.assertEqual(TA.markers(self.e,self.b),[self.p])
        self.assertEqual(event['close_quarters_hit'],facts)
        self.assertNotIn(TA.CQM_CHOICE,self.mark_rows(self.b)[0])
        self.cold();self.valid()


if __name__=='__main__':unittest.main()
