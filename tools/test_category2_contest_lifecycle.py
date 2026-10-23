"""Shared contest state lifetime and committed-progress persistence regressions."""
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine'))
from contest import Contestant,ContestRules,ContestEngine
from state_codec import dump_contest,load_contest,StateCodecError

class Pause(Exception):pass

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=ContestRules(ROOT)
        cls.effects={}
        for uid in cls.r._moves:
            try:stat,effect=cls.r.move_contest(uid)
            except (KeyError,ValueError):continue
            cls.effects.setdefault(effect,uid)
    def fixture(self,n=3):
        e=ContestEngine(self.r,seed=156)
        cs=[Contestant(str(i),{},list(self.effects.values()),'매력',1,'귀여움') for i in range(n)]
        return e,cs
    def restore(self,e,cs):
        return load_contest(self.r,json.loads(json.dumps(dump_contest(e,cs))))
    def test_center_commits_after_success_and_survives_every_position_table(self):
        for n in (3,4,5):
            for variant in ('standard','super'):
                with self.subTest(n=n,variant=variant):
                    e,cs=self.fixture(n);calls=[]
                    def choose(c,r,a,k):
                        if calls:raise Pause()
                        self.assertTrue(k);self.assertFalse(c.been_center)
                        calls.append(c.entity_id)
                        return self.effects['신뢰'],0
                    topic=None if variant=='super' else '근사함'
                    with self.assertRaises(Pause):e.run(cs,topic,choose,variant=variant)
                    self.assertEqual([c.entity_id for c in cs if c.been_center],calls)
                    loaded,parts=self.restore(e,cs)
                    loaded.run(parts,topic,lambda *a:(self.effects['신뢰'],0),variant=variant)
                    self.assertTrue(all(c.been_center for c in parts))
                    self.assertEqual(loaded._standard_run['round'],n)
                    self.restore(loaded,parts)
    def test_rejected_center_declaration_does_not_advance_or_mark_visit(self):
        e,cs=self.fixture()
        with self.assertRaises(ValueError):
            e.run(cs,'근사함',lambda *a:(self.effects['신뢰'],4))
        self.assertEqual(e._standard_run['slot'],0)
        self.assertFalse(any(c.been_center for c in cs))
        n,parts=self.restore(e,cs)
        n.run(parts,'근사함',lambda *a:(self.effects['신뢰'],0))
        self.assertTrue(all(c.been_center for c in parts))
    def test_grace_expires_at_final_round_and_next_round_boost_at_contest_end(self):
        for effect,flag in [('은총','immune_fumble'),('준비하기','double_next')]:
            with self.subTest(effect=effect):
                e,cs=self.fixture();seen=[]
                def choose(c,r,a,k):
                    if r==3 and not k:
                        center=next(x for x in cs if x.letter=='C')
                        seen.append(getattr(center,flag))
                    return self.effects[effect if r==3 else '신뢰'],0
                e.run(cs,'근사함',choose)
                self.assertEqual(seen,[True,True])
                self.assertFalse(any(getattr(c,flag) for c in cs))
                self.restore(e,cs)
    def test_next_round_boost_survives_save_and_is_consumed_once(self):
        e,cs=self.fixture();target=[]
        def first(c,r,a,k):
            if r==2:raise Pause()
            if k:target.append(c.entity_id)
            return self.effects['준비하기' if k else '신뢰'],0
        with self.assertRaises(Pause):e.run(cs,'근사함',first)
        n,parts=self.restore(e,cs);c=next(x for x in parts if x.entity_id==target[0])
        self.assertTrue(c.double_next)
        def second(c,r,a,k):
            if r==3:raise Pause()
            return self.effects['신뢰'],0
        with self.assertRaises(Pause):n.run(parts,'근사함',second)
        self.assertFalse(c.double_next)
        self.restore(n,parts)
    def test_codec_rejects_forged_center_and_expired_flags(self):
        e,cs=self.fixture()
        with self.assertRaises(Pause):e.run(cs,'근사함',lambda *a:(_ for _ in ()).throw(Pause()))
        cs[0].been_center=True
        with self.assertRaises(StateCodecError):dump_contest(e,cs)
        cs[0].been_center=False
        e.run(cs,'근사함',lambda *a:(self.effects['신뢰'],0))
        for flag in ('immune_fumble','double_next'):
            setattr(cs[0],flag,True)
            with self.assertRaises(StateCodecError):dump_contest(e,cs)
            setattr(cs[0],flag,False)
        self.restore(e,cs)
    def test_checkpoint_restores_center_cursor_and_remaining_pool_together(self):
        e,cs=self.fixture();calls=[]
        for c in cs:c.stat_dice['근사함']=3
        def choose(c,r,a,k):
            if calls:raise Pause()
            calls.append(c);return '연속자르기',1
        for c in cs:
            if '연속자르기' not in c.moves:c.moves.append('연속자르기')
        with self.assertRaises(Pause):e.run(cs,'근사함',choose)
        e.snapshot('one');before=[(c.been_center,dict(c.stat_dice),c.appeal,c.fumble) for c in cs]
        e.run(cs,'근사함',lambda *a:('연속자르기',1))
        e.restore('one',reason='restore committed first performance')
        self.assertEqual(e._standard_run['slot'],1)
        self.assertEqual([(c.been_center,c.stat_dice,c.appeal,c.fumble) for c in cs],before)
        self.restore(e,cs)
