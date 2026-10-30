"""Source-authored shared capture checks; execute only in the integrated candidate."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import capture_resolution as CAPTURE,missed_ball_body as BODY,state_codec as CODEC
import test_core_missed_ball_body as BASE


class SharedCaptureTests(unittest.TestCase):
    def fixture(self):
        f=BASE.MissedBallTests();f.rules=Rules(str(ROOT),ruleset='core');f.setUp()
        return f

    def test_native_throw_keeps_one_accuracy_one_ball_one_action_and_result_after_fresh_restore(self):
        for face,success in ((1,False),(20,True)):
            with self.subTest(face=face):
                f=self.fixture();resolve=CAPTURE._post_hit;accuracy=Engine.accuracy_check
                with patch.object(CAPTURE,'_post_hit',wraps=resolve) as post,patch.object(BODY,'launch',wraps=BODY.launch) as launch,patch.object(Engine,'accuracy_check',autospec=True,side_effect=accuracy) as hit:
                    self.assertEqual(f.throw(fixed_accuracy=20,fixed_capture=face),success)
                self.assertEqual((post.call_count,launch.call_count,hit.call_count),(1,1,1))
                self.assertEqual(f.a.budget['standard'],0);self.assertEqual(f.a.spec['items']['몬스터볼'],0)
                row=deepcopy(f.attempt());uid=row['physical_instance_id']
                self.assertEqual(row['status'],'captured' if success else 'failed_capture')
                self.assertEqual(bool(f.ball().get('consumed')),success)
                cold=CODEC.load_engine(Rules(str(ROOT),ruleset='core'),json.loads(json.dumps(CODEC.dump_engine(f.e))))
                actor=next(a for a in cold.gm.everyone if a.entity_id==f.a.entity_id)
                self.assertEqual(actor.spec['capture_attempts'][row['id']],row)
                self.assertEqual(bool(cold._physical_objects[uid].get('consumed')),success)

    def test_native_miss_never_enters_shared_capture_roll(self):
        f=self.fixture()
        with patch.object(CAPTURE,'_post_hit',wraps=CAPTURE._post_hit) as post:
            self.assertFalse(f.throw(fixed_accuracy=1,fixed_capture=20))
        post.assert_not_called();self.assertEqual(f.attempt()['status'],'recoverable_on_ground')
        self.assertNotIn('resolution',f.attempt());self.assertFalse(f.ball().get('consumed',False))

    def test_native_core_capture_retains_d100_automatic_face(self):
        f=self.fixture()
        self.assertTrue(f.throw(fixed_accuracy=20,fixed_capture=100,capture_source='core_105'))
        resolution=f.attempt()['resolution']
        self.assertEqual((resolution['sides'],resolution['comparison'],resolution['automatic']),(100,'<=',True))
        self.assertEqual(resolution['modifiers']['accuracy_natural20'],-10)

    def test_fling_plan_is_plain_data_without_launch_payment_or_roll(self):
        f=self.fixture();before=f.snap()
        plan=CAPTURE.fling_preflight(f.e,f.a,f.t,'몬스터볼',{'fixed_capture':20})
        self.assertEqual(json.loads(json.dumps(plan)),plan)
        self.assertEqual(plan['actor_id'],f.a.entity_id);self.assertEqual(plan['target_id'],f.t.entity_id)
        self.assertEqual(f.snap(),before);self.assertNotIn('capture_attempts',f.a.spec)
        for options in ({'fixed_accuracy':20},{'collector_choice':lambda facts:None},{'fixed_capture':21}):
            with self.assertRaises(ValueError):CAPTURE.fling_preflight(f.e,f.a,f.t,'몬스터볼',options)
            self.assertEqual(f.snap(),before)

    def test_fling_postdamage_plan_never_grants_fainted_capture_combo(self):
        f=self.fixture();f.t.hp=0;self.assertTrue(f.t.fainted);before=f.snap()
        with self.assertRaises(ValueError):CAPTURE.fling_preflight(f.e,f.a,f.t,'몬스터볼',{})
        plan=CAPTURE.fling_preflight(f.e,f.a,f.t,'몬스터볼',{},after_damage=True)
        self.assertFalse(plan['combo']);self.assertEqual(f.snap(),before)

    def test_unissued_fling_admission_cannot_spend_or_create_attempt(self):
        f=self.fixture();plan=CAPTURE.fling_preflight(f.e,f.a,f.t,'몬스터볼',{});before=f.snap()
        for token in ('unissued','fling-admission:1'):
            with self.assertRaises(ValueError):CAPTURE.fling_post_hit(f.e,f.a,f.t,token,deepcopy(plan))
            self.assertEqual(f.snap(),before);self.assertNotIn('capture_attempts',f.a.spec)


if __name__=='__main__':unittest.main()
