"""Source-classified native non-Move hit consumers; no injected completion events."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_book_roughneck_full as RF
import test_book_martial_artist as MF
import roughneck as R, martial_artist as MA, action_points as AP
import trainer_feature_acquisition as T, skill_feature_actions as SF
import combat_timing as CLOCK, combat_modifiers as MOD


class NonMoveHitConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='core')

    def menace(self,*,inner_focus=False,monkey=False,rough_striker=False,grapple_first=False):
        f=RF.RoughneckTests();f.rules=self.rules;f.setUp();self.addCleanup(f.doCleanups)
        skills={'육상':6,'전투':6,'곡예':6,'은신':6,'협박':6,'집중':6}
        f.roughneck(R.MENACE)
        f.p=f.foe(skills=skills,edges=['edge/기본-무술'] if inner_focus else [])
        f.b=f.add('striker',(4,4),speed=25,skills=skills,edges=[R.PRESENCE] if rough_striker else [],feats=[SF.MONKEY] if monkey else [])
        if inner_focus:
            T.acquire_martial_artist(f.e,f.p,acquisition_request_id='focus/class',selected_ability='정신력',lifecycle_policy=T.LIFECYCLE_WHILE_OWNED)
        if rough_striker:T.acquire_static(f.e,f.b,R.CLASS,acquisition_request_id='striker/roughneck')
        if grapple_first:
            f.combat(f.b,count=25)
            f.e.grapple(f.b,f.p,challenger_skill='육상',defender_skill='육상',fixed_accuracy=16,
                challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
            f.e.end_of_turn(f.b);f.e.end_round()
        f.combat(f.t);f.answer('roughneck_menace',True)
        ap=AP.available(f.t)
        self.assertFalse(f.terrorize(f.p,face=20,won=False))
        self.assertEqual((f.t.budget['swift'],AP.available(f.t)),(0,ap))
        self.assertNotIn('풀죽음',f.p.conditions,'new Menace must not affect its own completed Terrorize roll')
        f.e.end_of_turn(f.t);f.e.start_of_turn(f.b,initiative_count=25)
        return f

    def dirty(self,f,*,face=17,won=True,target=None,**extra):
        return f.e.dirty_trick(f.b,target or f.p,'hinder',fixed_accuracy=face,
            challenger_options={'fixed':[6 if won else 1]*6},
            defender_options={'fixed':[1 if won else 6]*6},**extra)

    def event(self,f,actor,source):
        return next(row for row in reversed(f.e._precision_events)
                    if row.get('actor') is actor and row['source']==source and row['kind']=='attack')

    def martial(self):
        f=MF.MartialArtistTests();f.rules=self.rules;f.setUp();self.addCleanup(f.doCleanups)
        f.acquire(training=1);f.start();MA.arm(f.e,f.a,'pummeling_momentum',target=f.t)
        f.use('마하펀치',face=15)
        self.assertEqual(f.a.spec[MA.TAG]['bonus'],1)
        f.next()
        return f

    def tag_dirty(self,f,*,face=17,won=True,target=None):
        return f.e.dirty_trick(f.a,target or f.t,'hinder',fixed_accuracy=face,
            challenger_options={'fixed':[6 if won else 1]*6},defender_options={'fixed':[1 if won else 6]*6})

    def retained_only(self,f,before,ap):
        tag=f.a.spec[MA.TAG]
        self.assertEqual({k:v for k,v in tag.items() if k not in ('hit_turn','fingerprint')},
                         {k:v for k,v in before.items() if k not in ('hit_turn','fingerprint')})
        self.assertEqual(tag['hit_turn'],f.a.custom_conditions['combat_turn_serial'])
        self.assertEqual(AP.available(f.a),ap)
        f.e.end_of_turn(f.a);self.assertIn(MA.TAG,f.a.spec)
        f.restore();f.valid()

    def test_menace_dirty_natural_16_17_independent_of_opposed_win_or_loss(self):
        for face,won in ((16,True),(16,False),(17,True),(17,False)):
            with self.subTest(face=face,won=won):
                f=self.menace();ap=AP.available(f.b)
                self.assertEqual(self.dirty(f,face=face,won=won),won)
                event=self.event(f,f.b,'maneuver/치사한-짓')
                self.assertEqual((event['natural'],event['result']),(face,'accuracy_hit'))
                self.assertEqual('풀죽음' in f.p.conditions,face==17)
                self.assertEqual((f.b.budget['standard'],f.b.budget['swift'],AP.available(f.b)),(0,1,ap))
                f.valid()

    def test_menace_all_other_native_ac_producers_consume_actual_face(self):
        for name in ('disarm','push','trip','grapple','manipulate'):
            with self.subTest(producer=name):
                f=self.menace()
                options=dict(fixed_accuracy=17,challenger_options={'fixed':[6]*6},defender_options={'fixed':[1]*6})
                if name=='disarm':
                    import items
                    items.register_item(f.e,f.p,'소형 방패')
                    f.e.disarm(f.b,f.p,attacker_skill='전투',defender_skill='전투',item_name='소형 방패',**options)
                elif name=='manipulate':
                    f.e.manipulate(f.b,f.p,'terrorize',defender_skill='집중',**options)
                else:getattr(f.e,name)(f.b,f.p,challenger_skill='육상' if name!='trip' else '곡예',defender_skill='육상' if name!='trip' else '곡예',**options)
                self.assertIn('풀죽음',f.p.conditions);f.valid()

    def test_menace_miss_wrong_target_and_expiry_do_not_flinch(self):
        for case in ('miss','other','expired'):
            with self.subTest(case=case):
                f=self.menace();target=f.p;face=1 if case=='miss' else 17
                if case=='other':target=f.add('other',(5,4),side='enemy',skills={'육상':6})
                if case=='expired':
                    f.e.end_of_turn(f.b);f.e.end_round();f.e.start_round(f.e.everyone)
                    f.e.start_of_turn(f.b,initiative_count=25)
                    self.assertFalse(any('incoming_status_range' in r for r in CLOCK.records(f.p)))
                self.dirty(f,face=face,target=target)
                self.assertNotIn('풀죽음',target.conditions);self.assertNotIn('풀죽음',f.p.conditions);f.valid()

    def test_menace_actual_inner_focus_blocks_flinch_on_native_hit(self):
        f=self.menace(inner_focus=True)
        self.assertEqual(MOD.incoming_status_threshold(f.p,'풀죽음',21),17)
        self.assertTrue(self.dirty(f));self.assertNotIn('풀죽음',f.p.conditions)
        self.assertEqual(self.event(f,f.b,'maneuver/치사한-짓')['result'],'accuracy_hit');f.valid()

    def test_cancelled_maneuver_cannot_reuse_previous_same_source_hit(self):
        f=self.menace();self.dirty(f);f.e.cure_status(f.p,'풀죽음')
        other=f.add('other',(5,4),side='enemy',skills={'육상':6})
        count=len(f.e._precision_events)
        self.assertFalse(self.dirty(f,target=other))
        self.assertEqual(len(f.e._precision_events),count)
        self.assertNotIn('풀죽음',f.p.conditions);self.assertNotIn('풀죽음',other.conditions)
        f.valid()

    def test_menace_roughneck_choice_retry_does_not_reapply_or_repay(self):
        f=self.menace(rough_striker=True);f.answer('roughneck_hit','hp')
        with self.assertRaisesRegex(ValueError,'Combat Stat'):self.dirty(f)
        event=self.event(f,f.b,'maneuver/치사한-짓');self.assertIn('풀죽음',f.p.conditions)
        f.e.cure_status(f.p,'풀죽음');ap=AP.available(f.b);rng=f.e.rng.getstate()
        f.answer('roughneck_hit','atk');R.resolve_maneuver(f.e,f.b,event['id'])
        R.resolve_maneuver(f.e,f.b,event['id'])
        self.assertNotIn('풀죽음',f.p.conditions)
        self.assertEqual((f.p.stages['atk'],AP.available(f.b),f.b.budget['standard']),(-1,ap-1,0))
        self.assertEqual(f.e.rng.getstate(),rng);f.restore('t','p','b')
        self.assertEqual(self.event(f,f.b,'maneuver/치사한-짓')['natural'],17)

    def test_menace_observed_skill_retry_and_gm_restore_retain_original_face(self):
        f=self.menace(monkey=True)
        def options(bad):
            return dict(fixed_accuracy=17,
                challenger_options={'roll_id':'menace/skill','fixed':[6]*6,'feature':SF.MONKEY,
                    'feature_options':{'decision':(lambda first:'bad') if bad else (lambda first:False),'reroll_faces':[6]*6}},
                defender_options={'roll_id':'menace/defense','fixed':[1]*6})
        with patch.object(f.e,'accuracy_check',wraps=f.e.accuracy_check) as accuracy:
            with self.assertRaises(ValueError):f.e.dirty_trick(f.b,f.p,'hinder',**options(True))
            self.assertEqual(accuracy.call_count,1);self.assertNotIn('풀죽음',f.p.conditions)
            self.assertEqual(f.b.budget['standard'],0);rng=f.e.rng.getstate()
            f.e.gm.snapshot('pending-native-hit')
            self.assertTrue(f.e.dirty_trick(f.b,f.p,'hinder',**options(False)))
            self.assertEqual(accuracy.call_count,1);self.assertEqual(f.e.rng.getstate(),rng)
            self.assertIn('풀죽음',f.p.conditions)
            f.e.gm.restore('pending-native-hit')
            self.assertNotIn('풀죽음',f.p.conditions)
            self.assertTrue(f.e.dirty_trick(f.b,f.p,'hinder',**options(False)))
            self.assertEqual(accuracy.call_count,1);self.assertIn('풀죽음',f.p.conditions)
        f.restore('t','p','b');self.assertEqual(self.event(f,f.b,'maneuver/치사한-짓')['natural'],17)

    def test_pummeling_dirty_hit_retains_only_on_opposed_win_and_loss(self):
        for won in (True,False):
            with self.subTest(won=won):
                f=self.martial();before=deepcopy(f.a.spec[MA.TAG]);ap=AP.available(f.a)
                self.assertEqual(self.tag_dirty(f,won=won),won)
                self.retained_only(f,before,ap)

    def test_pummeling_miss_other_target_and_cancelled_turn_expire(self):
        for case in ('miss','other','cancelled'):
            with self.subTest(case=case):
                f=self.martial();ap=AP.available(f.a)
                if case=='other':
                    f.e.gm.set_position(f.u,(3,4),reason='actual other adjacent target')
                    self.tag_dirty(f,target=f.u)
                elif case=='miss':self.assertFalse(self.tag_dirty(f,face=1))
                else:
                    import turn
                    self.assertTrue(turn.spend(f.e,f.a,'standard','other ordinary Standard task'))
                    self.assertFalse(self.tag_dirty(f))
                f.e.end_of_turn(f.a);self.assertNotIn(MA.TAG,f.a.spec)
                self.assertEqual(AP.available(f.a),ap);f.valid()

    def test_pummeling_automatic_grapple_struggle_retains_without_natural_or_gain(self):
        f=self.martial();f.e.grapple(f.a,f.t,**f.options(win=True));f.next()
        before=deepcopy(f.a.spec[MA.TAG]);ap=AP.available(f.a)
        result=f.e.grapple_action(f.a,'attack',request_id='retaining-struggle')
        self.assertGreater(result['damage'],0)
        event=self.event(f,f.a,'struggle');self.assertIsNone(event.get('natural'))
        self.assertEqual(event['result'],'damaging_hit')
        self.assertEqual(f.e.grapple_action(f.a,'attack',request_id='retaining-struggle'),result)
        self.retained_only(f,before,ap)

    def test_automatic_grapple_struggle_does_not_invent_menace_flinch_face(self):
        f=self.menace(grapple_first=True)
        self.assertEqual(MOD.incoming_status_threshold(f.p,'풀죽음',21),17)
        result=f.e.grapple_action(f.b,'attack',request_id='automatic-no-natural')
        self.assertGreater(result['damage'],0)
        self.assertIsNone(self.event(f,f.b,'struggle').get('natural'))
        self.assertNotIn('풀죽음',f.p.conditions);f.valid()

    def test_pummeling_nonmove_hit_cannot_create_tag_or_spend_armed_ap(self):
        f=MF.MartialArtistTests();f.rules=self.rules;f.setUp();self.addCleanup(f.doCleanups)
        f.acquire(training=1);f.start();MA.arm(f.e,f.a,'pummeling_momentum',target=f.t)
        ap=AP.available(f.a);self.assertTrue(self.tag_dirty(f))
        self.assertNotIn(MA.TAG,f.a.spec);self.assertEqual(AP.available(f.a),ap)
        self.assertIn('pummeling_momentum',f.a.spec[MA.ARMED]);f.valid()

    def test_pummeling_legacy_validation_is_unchanged_by_nonmove_retention(self):
        f=self.martial();tag=f.a.spec[MA.TAG]
        tag.pop('earned_rank');MA._seal_tag(tag)
        f.e._move_completions[tag['completion_id']].pop(MA.TAG)
        f.restore();self.assertIn('legacy_validation',f.a.spec[MA.TAG])
        before=deepcopy(f.a.spec[MA.TAG]);ap=AP.available(f.a)
        self.assertTrue(self.tag_dirty(f));self.retained_only(f,before,ap)
        self.assertEqual(f.a.spec[MA.TAG]['legacy_validation'],before['legacy_validation'])

    def test_pummeling_gm_restore_retains_hit_turn_and_next_punch_increments_once(self):
        f=self.martial();before=deepcopy(f.a.spec[MA.TAG]);self.tag_dirty(f)
        f.e.gm.snapshot('retained-tag');f.e.end_of_turn(f.a)
        f.e.gm.restore('retained-tag');self.assertEqual(f.a.spec[MA.TAG]['hit_turn'],f.a.custom_conditions['combat_turn_serial'])
        self.assertEqual(f.a.spec[MA.TAG]['earned_rank'],before['earned_rank'])
        f.next();ap=AP.available(f.a);f.use('마하펀치',face=15)
        self.assertEqual((f.a.spec[MA.TAG]['bonus'],AP.available(f.a)),(2,ap));f.restore();f.valid()


if __name__=='__main__':unittest.main()
