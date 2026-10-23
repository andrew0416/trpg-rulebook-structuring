"""User-adopted defaults, persistent GM overrides and actual consumer boundaries."""
from copy import deepcopy
from pathlib import Path
import json, unittest
from unittest.mock import patch
from engine import Combatant
import effects as FX
import temporary_hp as TEMP
import contest_festival as FESTIVAL
from contest import ContestEngine
from native_rule_policy import PolicyPending
from state_codec import dump_engine, load_engine, dump_contest, StateCodecError
import test_hp_loss_resources as HP_FIX
import test_festival_progression as FEST_FIX
Pause, OCCURRENCE = FEST_FIX.Pause, FEST_FIX.OCCURRENCE

ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')


class HPLossPolicyTests(unittest.TestCase):
    setUpClass=classmethod(HP_FIX.HPLossResources.setUpClass.__func__)
    fixture=HP_FIX.HPLossResources.fixture

    def pair(self):
        e,a,_=self.fixture(hp=20,temp=10)
        b=Combatant(self.rules,dict(deepcopy(a.spec),id='policy/target',name='other'))
        b.hp=40;e.everyone.append(b)
        e.gm.set_temp_hp(b,10,reason='observed target pool',duration_seconds=300)
        a.pos=(0,0);b.pos=(1,0);b.side='enemy'
        return e,a,b

    def test_default_and_gm_override_keep_cap_bypass_and_ordinary_allocation(self):
        for mode,expected in [('temp_first',(20,2)),('bypass',(12,10))]:
            e,c,_=self.fixture(hp=20,temp=10);c.damage_cap={'value':1}
            if mode=='bypass':e.gm.set_hp_loss_policy(mode,reason='GM interpretation')
            e.lose_hp(c,8,unpreventable=True)
            self.assertEqual((c.hp,c.temp_hp),expected)
            e.lose_hp(c,8)
            self.assertEqual(c.temp_hp,expected[1]-1)  # Ordinary cap and temp-first are unchanged.

    def test_invalid_gm_policy_is_atomic_and_returned_dictionary_is_defensive(self):
        e,c,_=self.fixture(temp=10)
        before=deepcopy((e._hp_loss_policy,e.log_lines,e.rulings.log))
        for mode,reason in [('bad','why'),(True,'why'),('bypass',''),('bypass',None)]:
            with self.assertRaises(ValueError):e.gm.set_hp_loss_policy(mode,reason=reason)
            self.assertEqual((e._hp_loss_policy,e.log_lines,e.rulings.log),before)
        result=e.gm.set_hp_loss_policy('bypass',reason='GM interpretation')
        result['mode']='temp_first';TEMP.loss_policy(e)['mode']='temp_first'
        self.assertEqual(TEMP.loss_policy(e)['mode'],'bypass')
        self.assertEqual(e.rulings.log[-1]['after']['mode'],'bypass')

    def test_nondefault_snapshot_json_restore_and_forged_values(self):
        e,c,_=self.fixture(hp=20,temp=10)
        e.gm.set_hp_loss_policy('bypass',reason='persistent GM interpretation')
        e.gm.snapshot('override')
        payload=json.loads(json.dumps(dump_engine(e)))
        restored=load_engine(self.rules,payload)
        restored.lose_hp(restored.everyone[0],8,unpreventable=True)
        self.assertEqual((restored.everyone[0].hp,restored.everyone[0].temp_hp),(12,10))
        e.gm.set_hp_loss_policy('temp_first',reason='later selection');e.gm.restore('override')
        self.assertEqual(TEMP.loss_policy(e)['mode'],'bypass')
        e.lose_hp(c,8,unpreventable=True);self.assertEqual((c.hp,c.temp_hp),(12,10))
        for node in payload['nodes'].values():
            if node['kind']=='dict':
                for pair in node['items']:
                    if pair==['mode','bypass']:pair[1]='forged'
        with self.assertRaises(StateCodecError):load_engine(self.rules,payload)
        e.gm.snapshots['override']['engine']['_hp_loss_policy']['mode']='forged'
        before=(c.hp,c.temp_hp,TEMP.loss_policy(e))
        with self.assertRaises(ValueError):e.gm.restore('override')
        self.assertEqual((c.hp,c.temp_hp,TEMP.loss_policy(e)),before)
        e._hp_loss_policy={'mode':'forged','reason':'invalid'}
        with self.assertRaises(StateCodecError):dump_engine(e)
        with self.assertRaises(ValueError):e.gm.snapshot('invalid')

    def test_selected_curse_declaration_and_native_pain_split_share_policy(self):
        for mode in ('temp_first','bypass'):
            with self.subTest(mode=mode):
                e,a,b=self.pair()
                if mode=='bypass':e.gm.set_hp_loss_policy(mode,reason='GM interpretation')
                # Real selected source effect, not a fabricated unpreventable flag.
                branch=next(x for x in self.rules.move_mech('move/저주')[0]['effects_exec']
                            if x.get('if')=='user is 고스트')
                loss=next(x for x in branch['then'] if x['type']=='hp_loss')
                a.hp=70;e.gm.set_temp_hp(a,30,reason='Curse pool',duration_seconds=300)
                a.damage_cap={'value':1}
                FX.h_hp_loss(e,a,b,loss,dict(attacker=a,target=b,source_id='move/저주',hit=True))
                self.assertEqual((a.hp,a.temp_hp),(70,4) if mode=='temp_first' else (44,30))
                e,a,b=self.pair()
                if mode=='bypass':e.gm.set_hp_loss_policy(mode,reason='GM interpretation')
                a.damage_cap=b.damage_cap={'value':0}
                e.gm.set_move(a,'move/아픔나누기',True,reason='actual native source')
                e.start_round([a,b]);e.start_of_turn(a)
                e.use_move_on(a,b,'move/아픔나누기',[a,b])
                self.assertEqual((a.hp,a.temp_hp,b.hp,b.temp_hp),
                    (35,0,45,0) if mode=='temp_first' else (25,10,35,10))
                self.assertEqual((a.injuries,b.injuries),(0,0))
                self.assertEqual(a.budget['standard'],0)

    def test_actual_gmax_residual_uses_same_default_and_persistent_override(self):
        from test_category2_gmax_moves import GMaxMoveTests
        GMaxMoveTests.setUpClass();case=GMaxMoveTests()
        import gmax_moves as GMAX
        for mode in ('temp_first','bypass'):
            e,a,b,_,_,_=case.activate('C2CSV-MOVE-R1016')
            b.hp=b.max_hp;hp=b.hp;loss=b.base_max_hp//6
            e.gm.set_temp_hp(b,loss+5,reason='observed residual pool',duration_seconds=300)
            b.damage_cap={'value':0}
            if mode=='bypass':e.gm.set_hp_loss_policy(mode,reason='GM interpretation')
            GMAX.start_turn(e,b)
            self.assertEqual((b.hp,b.temp_hp),
                (hp,5) if mode=='temp_first' else (hp-loss,loss+5))
            self.assertEqual(b.spec[GMAX.EFFECTS][0]['turns'],3)


class FestivalPolicyTests(unittest.TestCase):
    setUpClass=classmethod(FEST_FIX.FestivalTests.setUpClass.__func__)
    fixture=FEST_FIX.FestivalTests.fixture
    restore=FEST_FIX.FestivalTests.restore

    def play(self,host,actors,chooser=None,*,variant='standard',choice=None):
        return host.run(actors,None if variant=='super' else self.stat,
            chooser or (lambda *a:(self.move,0)),variant='festival',
            contest_id=OCCURRENCE,festival_variant=variant,festival_policy=choice)

    def test_all_presets_default_and_custom_execute_actual_child_transitions(self):
        cases=[None,*[dict(scope=OCCURRENCE,reason='GM preset',preset=k) for k in FESTIVAL.presets()],
               dict(scope=OCCURRENCE,reason='GM custom fields',preset='carry_all',introduction='repeat',
                    stat_dice='carry',excitement='reset',last_move='reset')]
        for n in (3,4,5):
            for variant in ('standard','super'):
                for choice in cases:
                    with self.subTest(n=n,variant=variant,choice=choice):
                        host,actors=self.fixture(n);observed=[]
                        expected=FESTIVAL.policy(choice,OCCURRENCE)
                        native_perform=host.perform
                        # Observe the actual completed previous child, before the next starts.
                        ends={}
                        def perform(c,*a,**kw):
                            result=native_perform(c,*a,**kw)
                            ends[c]=deepcopy((c.stat_dice,c.excitement,c.last_move))
                            return result
                        host.perform=perform
                        def choose(c,r,*a):
                            child=len(host._festival_run['history'])
                            key=(child,c.entity_id)
                            if child and key not in observed:
                                old_pool,old_ex,old_move=ends[c]
                                expected_pool=(deepcopy(host._festival_run['initial_pools'][c])
                                    if expected['stat_dice']=='reset' else deepcopy(old_pool))
                                if expected['introduction']=='repeat':
                                    expected_pool['귀여움']=expected_pool.get('귀여움',0)+1
                                self.assertEqual(c.stat_dice,expected_pool)
                                self.assertEqual(c.excitement,0 if expected['excitement']=='reset' else old_ex)
                                self.assertEqual(c.last_move,None if expected['last_move']=='reset' else old_move)
                                observed.append(key)
                            return self.move,1 if c.stat_dice.get(self.stat,0)>0 else 0
                        with patch.object(ContestEngine,'d6',lambda self,n:[3]*n):
                            result=self.play(host,actors,choose,variant=variant,choice=choice)
                        del host.perform
                        self.assertEqual(len(result),3)
                        self.assertEqual(len(host._festival_run['history']),n-2)
                        self.assertEqual(host._festival_run['policy'],expected)
                        self.restore(host,actors)
                        self.assertEqual(self.play(host,actors,variant=variant),result)
        view=FESTIVAL.presets();view['restart']['excitement']='carry'
        self.assertEqual(FESTIVAL.presets()['restart']['excitement'],'reset')

    def test_sparse_override_legacy_full_input_lock_resume_and_restore_tamper(self):
        choice=dict(scope=OCCURRENCE,reason='single GM override',excitement='carry')
        host,actors=self.fixture(4)
        with self.assertRaises(Pause):self.play(host,actors,lambda *a:(_ for _ in ()).throw(Pause()),choice=choice)
        expected=FESTIVAL.policy(choice,OCCURRENCE)
        choice['excitement']='reset'
        self.assertEqual(host._festival_run['policy'],expected)
        frozen=(host.rng.getstate(),deepcopy(host.log_lines))
        with self.assertRaises(ValueError):self.play(host,actors,choice=choice)
        self.assertEqual((host.rng.getstate(),host.log_lines),frozen)
        host.snapshot('paused');loaded,parts=self.restore(host,actors)
        # Missing selection on resume means frozen policy, not a new default.
        self.play(loaded,parts);self.assertEqual(loaded._festival_run['policy'],expected)
        self.play(host,actors,choice=deepcopy(expected))  # Legacy complete dictionary.
        host.restore('paused',reason='GM restore keeps occurrence selection')
        self.assertEqual(host._festival_run['policy'],expected)
        host._festival_run['policy']['excitement']='reset'
        with self.assertRaises(StateCodecError):dump_contest(host,actors)
        with self.assertRaises(ValueError):self.play(host,actors)

    def test_invalid_preset_scope_reason_field_refuse_before_rng_or_occurrence(self):
        for delta in [dict(preset='bad'),dict(scope='other'),dict(reason=''),
                      dict(last_move='bad'),dict(extra=True),dict(preset=True)]:
            host,actors=self.fixture(4)
            bad=dict(scope=OCCURRENCE,reason='GM explicit input');bad.update(delta)
            before=(host.rng.getstate(),deepcopy(host.log_lines))
            with self.assertRaises(ValueError):self.play(host,actors,choice=bad)
            self.assertIsNone(host._festival_run)
            self.assertEqual((host.rng.getstate(),host.log_lines),before)


if __name__=='__main__':unittest.main()
