"""Actual child-contest execution; explicit table policies are test inputs only."""
from copy import deepcopy
from pathlib import Path
import json
import unittest
from unittest.mock import patch
from contest import ContestEngine, ContestRules, Contestant
from native_rule_policy import PolicyPending
from state_codec import dump_contest, load_contest, StateCodecError

ROOT=Path(__file__).resolve().parents[1]
OCCURRENCE='festival/test'


class Pause(Exception):
    pass


class FestivalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules=ContestRules(ROOT, ruleset='core')
        effects={}
        for mid in cls.rules._moves:
            try:stat,effect=cls.rules.move_contest(mid)
            except (ValueError,KeyError):continue
            effects.setdefault(effect,mid)
        cls.move=effects['신뢰']
        cls.safe=effects['안전한 선택']
        cls.safe_moves=[]
        for mid in cls.rules._moves:
            try:stat,effect=cls.rules.move_contest(mid)
            except (ValueError,KeyError):continue
            if effect=='안전한 선택':cls.safe_moves.append(mid)
        assert len(cls.safe_moves)>=2
        cls.stat=cls.rules.move_contest(cls.move)[0]

    def fixture(self,n=5,tied=False):
        host=ContestEngine(self.rules,seed=530)
        actors=[Contestant(str(i),{self.stat:3},[self.move,*self.safe_moves[:2]],'매력',1,'귀여움') for i in range(n)]
        for i,c in enumerate(actors):
            c.appeal=0 if tied else 1000*i
            c.fumble=2
        return host,actors

    def policy(self,**kw):
        return dict(scope=OCCURRENCE,reason='Explicit test table interpretation; no global source ruling',
                    introduction=kw.get('introduction','repeat'),stat_dice=kw.get('stat_dice','reset'),
                    excitement=kw.get('excitement','reset'),last_move=kw.get('last_move','reset'))

    def play(self,host,actors,chooser=None,*,variant='standard',policy=None,decisions=None):
        return host.run(actors,None if variant=='super' else self.stat,
                        chooser or (lambda *args:(self.move,0)),variant='festival',
                        contest_id=OCCURRENCE,festival_variant=variant,
                        festival_policy=self.policy() if policy is None else policy,
                        festival_decisions=decisions)

    def restore(self,host,actors):
        return load_contest(self.rules,json.loads(json.dumps(dump_contest(host,actors))))

    def test_actual_standard_super_all_rosters_carry_score_eliminate_one_and_finish_at_three(self):
        for n in (3,4,5):
            for variant in ('standard','super'):
                with self.subTest(n=n,variant=variant):
                    host,actors=self.fixture(n);calls=[]
                    def choose(c,r,a,k):
                        calls.append((len(host._festival_run['survivors']),c.name,r,k))
                        return self.move,0
                    result=self.play(host,actors,choose,variant=variant)
                    state=host._festival_run
                    self.assertEqual([len(x['participants']) for x in state['history']],list(range(n,2,-1)))
                    self.assertEqual(len(calls),sum(k*k for k in range(3,n+1)))
                    self.assertEqual(state['eliminated'],tuple(actors[:n-3]))
                    self.assertEqual(state['winner'],actors[-1])
                    self.assertEqual(set(result),set(actors[-3:]))
                    for row in state['history']:
                        self.assertTrue(all(row['scores'][c]>=1000*int(c.name)-2 for c in row['participants']))
                    before=(host.rng.getstate(),list(host.log_lines),len(host._performance_observations))
                    self.assertEqual(self.play(host,actors,variant=variant),result)
                    self.assertEqual(before,(host.rng.getstate(),host.log_lines,len(host._performance_observations)))
                    self.restore(host,actors)

    def test_invalid_policy_scope_and_changed_contract_refuse_without_rng_or_replay(self):
        host,actors=self.fixture();before=host.rng.getstate()
        with self.assertRaises(ValueError):
            host.run(actors,self.stat,lambda *a:(self.move,0),variant='festival',contest_id=OCCURRENCE,
                     festival_policy=dict(scope=OCCURRENCE,reason='bad test policy',stat_dice='invalid'))
        self.assertIsNone(host._festival_run)
        self.assertEqual(before,host.rng.getstate())
        bad=self.policy();bad['scope']='other'
        with self.assertRaises(ValueError):self.play(host,actors,policy=bad)
        with self.assertRaises(Pause):self.play(host,actors,lambda *a:(_ for _ in ()).throw(Pause()))
        frozen=(host.rng.getstate(),len(host.log_lines))
        with self.assertRaises(ValueError):self.play(host,actors,policy=self.policy(excitement='carry'))
        with self.assertRaises(ValueError):host.run(actors,self.stat,lambda *a:(self.move,0))
        self.assertEqual(frozen,(host.rng.getstate(),len(host.log_lines)))

    def test_both_explicit_resource_interpretations_use_actual_next_child(self):
        for carry in (False,True):
            with self.subTest(carry=carry):
                host,actors=self.fixture(4)
                chosen=self.policy(introduction='retain' if carry else 'repeat',
                    stat_dice='carry' if carry else 'reset',excitement='carry' if carry else 'reset',
                    last_move='carry' if carry else 'reset')
                def choose(c,r,a,k):
                    if len(host._festival_run['survivors'])==3:
                        self.assertEqual(c.last_move is not None,carry)
                        self.assertEqual(c.excitement,3 if carry else 0)
                        if carry:self.assertLessEqual(c.stat_dice.get(self.stat,0),1)
                        else:self.assertGreaterEqual(c.stat_dice[self.stat],3)
                        raise Pause()
                    return self.move,1 if r<=3 else 0
                with self.assertRaises(Pause):self.play(host,actors,choose,policy=chosen)
                self.assertEqual(len(host._festival_run['history']),1)
                self.restore(host,actors)

    def test_json_and_gm_resume_preserve_eliminated_actors_and_actual_child_cursor(self):
        host,actors=self.fixture();calls=[]
        def choose(c,r,a,k):
            if len(host._festival_run['history'])==1 and len(calls)>27:raise Pause()
            calls.append(c.name);return self.move,0
        with self.assertRaises(Pause):self.play(host,actors,choose)
        host.snapshot('middle')
        saved=[(c.appeal,c.fumble,c.been_center,dict(c.stat_dice)) for c in actors]
        loaded,parts=self.restore(host,actors)
        expected=self.play(loaded,parts)
        self.play(host,actors)
        self.assertEqual([c.name for c in expected],[c.name for c in host._festival_run['result']])
        self.assertEqual(host.log_lines,loaded.log_lines)
        self.assertEqual(host.rng.getstate(),loaded.rng.getstate())
        actors[0].appeal+=100
        host.restore('middle',reason='Restore all original Festival actors')
        self.assertEqual(saved,[(c.appeal,c.fumble,c.been_center,c.stat_dice) for c in actors])
        self.restore(host,actors)

    def test_tied_elimination_requires_exact_observation_scope_without_child_replay(self):
        host,actors=self.fixture(4,True)
        # All-zero public dice give the same score to every actual child performer.
        calls=[]
        def choose(c,r,*a):
            calls.append((c.name,r));return self.safe_moves[(r-1)%2],0
        with patch.object(ContestEngine,'d6',lambda self,n:[1]*n):
            with self.assertRaises(PolicyPending) as pending:self.play(host,actors,choose)
            obligation=pending.exception.obligations[0]
            self.assertEqual(obligation['key'],'1:eliminate')
            self.assertEqual(host._festival_run['phase'],'adjudication')
            loaded,parts=self.restore(host,actors)
            before=(len(loaded._performance_observations),loaded.rng.getstate(),list(loaded.log_lines))
            bad={'value':'foreign','reason':'test','scope':obligation['scope']}
            with self.assertRaises(ValueError):self.play(loaded,parts,decisions={'1:eliminate':bad})
            self.assertEqual(before,(len(loaded._performance_observations),loaded.rng.getstate(),loaded.log_lines))
            picked=obligation['choices'][0]
            good={'value':picked,'reason':'Explicit test tie decision','scope':obligation['scope']}
            try:self.play(loaded,parts,choose,decisions={'1:eliminate':good})
            except PolicyPending:pass  # A final three-person tie remains a distinct question.
            self.assertEqual(loaded._festival_run['eliminated'][0].entity_id,picked)
            self.assertEqual(len(calls),25)
            self.assertEqual(loaded._standard_run['phase'],'complete')
            self.restore(loaded,parts)

    def test_final_tie_has_no_implicit_winner_and_explicit_choice_survives_restore(self):
        host,actors=self.fixture(3,True)
        with patch.object(ContestEngine,'d6',lambda self,n:[1]*n):
            with self.assertRaises(PolicyPending) as pending:
                self.play(host,actors,lambda c,r,*a:(self.safe_moves[(r-1)%2],0))
        ask=pending.exception.obligations[0]
        self.assertEqual(ask['key'],'1:winner')
        decision={'value':ask['choices'][-1],'reason':'Actual explicit test GM tie response','scope':ask['scope']}
        self.play(host,actors,decisions={ask['key']:decision})
        self.assertEqual(host._festival_run['winner'].entity_id,decision['value'])
        restored,parts=self.restore(host,actors)
        self.assertEqual(restored._festival_run['winner'].entity_id,decision['value'])

    def test_codec_rejects_forged_survivor_history_policy_and_child_identity(self):
        host,actors=self.fixture()
        self.play(host,actors)
        for field,replacement in [('survivors',tuple(actors[:3])),('eliminated',()),('id','other')]:
            with self.subTest(field=field):
                original=host._festival_run[field];host._festival_run[field]=replacement
                with self.assertRaises(StateCodecError):dump_contest(host,actors)
                host._festival_run[field]=original
        original=host._festival_run['history'][0]['eliminate']
        host._festival_run['history'][0]['eliminate']=actors[-1]
        with self.assertRaises(StateCodecError):dump_contest(host,actors)
        host._festival_run['history'][0]['eliminate']=original
        self.restore(host,actors)

    def test_completed_result_has_exactly_three_distinct_survivors_on_restore(self):
        host,actors=self.fixture(4)
        result=self.play(host,actors)
        original=host._festival_run['result']
        self.assertEqual(len(original),3)
        for malformed in ((original[0],*original),list(original)):
            with self.subTest(malformed=type(malformed).__name__):
                host._festival_run['result']=malformed
                with self.assertRaises(StateCodecError):dump_contest(host,actors)
        host._festival_run['result']=original
        loaded,parts=self.restore(host,actors)
        replay=self.play(loaded,parts)
        self.assertEqual(len(replay),3)
        self.assertEqual(len(set(replay)),3)
        self.assertEqual([c.entity_id for c in replay],[c.entity_id for c in result])

    def test_native_pokemon_binding_and_no_trainer_or_callback_reentry(self):
        from test_category2_state_codec import ContestStateCodecTests
        ContestStateCodecTests.setUpClass()
        case=ContestStateCodecTests()
        host,actors,native,trainers,pokemon=case.fixture()
        from engine import Combatant
        extra=Combatant(native.r,dict(deepcopy(pokemon[0].spec),id='contest/festival-extra',
                                     name='extra',trainer_id=trainers[0].entity_id))
        native.everyone.append(extra)
        host._native_intro_bindings.clear()
        # Derived pools exercise the real source contribution ledger at a child boundary.
        actors=[host.contestant_from_combatants(native,p,t,'매력',
                    smart_stat_policy='ptk-literal-defense')
                for p,t in [*zip(pokemon,trainers),(extra,trainers[0])]]
        for i,c in enumerate(actors):c.appeal=1000*i
        learned=actors[0].moves[0]
        def choose(c,r,a,k):
            with self.assertRaises(ValueError):self.play(host,actors)
            with self.assertRaises(ValueError):host.snapshot('callback')
            return c.moves[(r-1)%len(c.moves)],0
        self.play(host,actors,choose)
        envelope=json.loads(json.dumps(dump_contest(host,actors)))
        restored,parts=load_contest(host.r,envelope,native_rules=native.r)
        self.assertTrue(all(restored._native_intro_bindings[c][1].kind=='pokemon' for c in parts))
        with self.assertRaises(ValueError):
            host.run(actors,self.stat,lambda *a:(learned,0),variant='festival',trainer_model='simultaneous',
                     contest_id=OCCURRENCE,festival_policy=self.policy())


if __name__=='__main__':unittest.main()
