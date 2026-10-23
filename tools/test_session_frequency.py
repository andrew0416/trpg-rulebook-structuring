"""Optional session activation periods; Daily Move session recovery remains unresolved.
Source ch11:2533-2543; ordinary Move recovery ch07:750/754, ch10:224.
Direct quota keys below are test fixtures, not claimed source features.
"""
import copy,hashlib,json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'engine').is_dir():ROOT=Path(r'D:\trpg-rulebook-structuring\ptk-structure-experiment')
sys.path.insert(0,str(ROOT/'engine'))
from engine import Rules,Engine,Combatant
import frequency as F
import downtime as DT
KEY='test_fixture/session_activation'
TEST_CONDITIONS={'test_default_policy_stays_game_day': ['SF01'], 'test_option_requires_explicit_boolean_deferral': ['SF01', 'SF03', 'SF14'], 'test_first_label_preserves_spent_legacy_quota': ['SF09', 'SF12'], 'test_first_label_preserves_existing_day_activation': ['SF09', 'SF12'], 'test_new_session_resets_cap_not_each_call': ['SF02', 'SF09'], 'test_physical_new_day_does_not_restore_session_activation': ['SF02', 'SF07'], 'test_closed_round_is_still_active_encounter': ['SF03', 'SF10', 'SF11'], 'test_explicit_encounter_without_round_can_defer': ['SF03', 'SF10'], 'test_immediate_mode_does_not_end_encounter': ['SF03', 'SF09'], 'test_deferred_completion_refreshes_once': ['SF09', 'SF11'], 'test_pending_other_id_and_past_id_rejected': ['SF09', 'SF11', 'SF14'], 'test_invalid_encounter_finish_does_not_commit_refresh': ['SF14'], 'test_nonfrequency_state_is_unchanged': ['SF06', 'SF07', 'SF08'], 'test_scene_activation_is_not_refreshed': ['SF02', 'SF05'], 'test_off_field_actor_receives_same_boundary': ['SF13'], 'test_daily_move_unused_quota_is_preserved': ['SF04'], 'test_daily_move_spent_quota_is_not_restored_by_session': ['SF04'], 'test_center_restoration_keeps_once_per_scene_restriction': ['SF04', 'SF05', 'SF06'], 'test_eligible_extended_rest_preserves_existing_move_path': ['SF04', 'SF06'], 'test_same_day_extended_rest_does_not_restore_daily_move': ['SF04'], 'test_default_daily_move_still_needs_explicit_recovery': ['SF01', 'SF04'], 'test_explicit_full_frequency_restore_removes_pending_marker': ['SF04'], 'test_snapshot_restores_pending_session_and_usage': ['SF09', 'SF11', 'SF12'], 'test_session_actor_cannot_silently_enter_game_day_engine': ['SF12', 'SF14'], 'test_same_id_call_can_admit_new_participant_without_reset': ['SF09', 'SF13']}

def source_review_path():
    saved=ROOT/'data/verification/session-frequency-source-review.json'
    return saved if saved.exists() else Path(__file__).with_name('session-frequency-source-review.json')

class SessionFrequencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(str(ROOT),ruleset='core')
    def actor(self,name='session fixture'):
        return Combatant(self.rules,dict(name=name,kind='trainer',level=1,stats={s:10 for s in ['hp','atk','def','spa','spd','spe']},types=[],moves=[],abilities=[]))
    def setup_pair(self,defer=False):
        e=Engine(self.rules,session_frequency=True,defer_session_refresh=defer);c=self.actor()
        self.assertEqual(e.begin_session('s1',[c]),'initialized')
        return e,c
    def consume(self,e,c,frequency='하루',key=KEY):
        self.assertTrue(F.activation_allowed(c,key,frequency,engine=e))
        F.consume_activation(c,key,frequency,engine=e)
    def allowed(self,e,c,frequency='하루',key=KEY):return F.activation_allowed(c,key,frequency,engine=e)
    def daily_move(self,e,c):
        mid='move/대폭발'
        self.assertEqual(e.r.selection.resolve(mid),mid)
        self.assertEqual(F.move_frequency(e,mid,c),('daily',1))
        return mid
    def test_default_policy_stays_game_day(self):
        e=Engine(self.rules);c=self.actor();self.consume(e,c)
        with self.assertRaises(ValueError):e.begin_session('s1',[c])
        self.assertFalse(self.allowed(e,c));DT.new_day(c);self.assertTrue(self.allowed(e,c))
    def test_option_requires_explicit_boolean_deferral(self):
        for kw in [dict(session_frequency=True),dict(session_frequency='true'),dict(session_frequency=True,defer_session_refresh=1),dict(session_frequency=False,defer_session_refresh=False)]:
            with self.subTest(kw=kw):
                with self.assertRaises(ValueError):Engine(self.rules,**kw)
    def test_first_label_preserves_spent_legacy_quota(self):
        e=Engine(self.rules,session_frequency=True,defer_session_refresh=False);c=self.actor()
        c.spec['daily_feat_uses']={KEY:1}
        self.assertEqual(e.begin_session('s1',[c]),'initialized')
        self.assertFalse(self.allowed(e,c))
        self.assertEqual(e.session_epoch,0)
    def test_first_label_preserves_existing_day_activation(self):
        c=self.actor();F.consume_activation(c,KEY,'하루')
        e=Engine(self.rules,session_frequency=True,defer_session_refresh=False)
        e.begin_session('s1',[c]);self.assertFalse(self.allowed(e,c))
    def test_new_session_resets_cap_not_each_call(self):
        e,c=self.setup_pair();self.consume(e,c,'하루x2');self.consume(e,c,'하루x2')
        self.assertFalse(self.allowed(e,c,'하루x2'));self.assertEqual(e.begin_session('s1'),'unchanged')
        self.assertFalse(self.allowed(e,c,'하루x2'));self.assertEqual(e.begin_session('s2'),'refreshed')
        self.consume(e,c,'하루x2');self.consume(e,c,'하루x2');self.assertFalse(self.allowed(e,c,'하루x2'))
    def test_physical_new_day_does_not_restore_session_activation(self):
        e,c=self.setup_pair();self.consume(e,c);DT.new_day(c)
        self.assertFalse(self.allowed(e,c));self.assertEqual(F.state(c)['day'],1)
    def test_closed_round_is_still_active_encounter(self):
        e,c=self.setup_pair(defer=True);self.consume(e,c);e.start_round([c]);e.end_round()
        self.assertTrue(e.encounter_active);self.assertIsNone(e.round_start_seconds)
        self.assertEqual(e.begin_session('s2'),'deferred');self.assertFalse(self.allowed(e,c))
        e.end_encounter();self.assertTrue(self.allowed(e,c));self.assertFalse(e.encounter_active)
        self.assertEqual(e.elapsed_seconds,10)
    def test_explicit_encounter_without_round_can_defer(self):
        e,c=self.setup_pair(defer=True);self.consume(e,c);e.begin_encounter([c])
        self.assertEqual(e.begin_session('s2'),'deferred');self.assertEqual(e.session_id,'s1')
        e.end_encounter();self.assertEqual(e.session_id,'s2');self.assertEqual(e.elapsed_seconds,0)
    def test_immediate_mode_does_not_end_encounter(self):
        e,c=self.setup_pair();self.consume(e,c);e.begin_encounter([c])
        self.assertEqual(e.begin_session('s2'),'refreshed');self.assertTrue(e.encounter_active)
        self.assertTrue(self.allowed(e,c))
    def test_deferred_completion_refreshes_once(self):
        e,c=self.setup_pair(defer=True);self.consume(e,c);e.begin_encounter()
        self.assertEqual(e.begin_session('s2'),'deferred');self.assertEqual(e.begin_session('s2'),'deferred')
        e.end_encounter();self.consume(e,c);e.end_encounter()
        self.assertFalse(self.allowed(e,c));self.assertEqual(e.session_epoch,1)
    def test_pending_other_id_and_past_id_rejected(self):
        e,c=self.setup_pair(defer=True);self.consume(e,c);e.begin_encounter();e.begin_session('s2')
        before=copy.deepcopy(F.state(c))
        with self.assertRaises(ValueError):e.begin_session('s3')
        self.assertEqual(F.state(c),before);e.end_encounter()
        with self.assertRaises(ValueError):e.begin_session('s1')
        self.assertEqual(e.session_id,'s2')
    def test_invalid_encounter_finish_does_not_commit_refresh(self):
        e,c=self.setup_pair(defer=True);self.consume(e,c);e.start_round([c]);e.begin_session('s2')
        before=(e.session_id,e.pending_session_id,e.session_epoch,copy.deepcopy(F.state(c)))
        with self.assertRaises(ValueError):e.end_encounter(round_elapsed_seconds=11)
        self.assertEqual((e.session_id,e.pending_session_id,e.session_epoch,F.state(c)),before)
        self.assertTrue(e.encounter_active)
    def test_nonfrequency_state_is_unchanged(self):
        e,c=self.setup_pair();self.consume(e,c)
        c.spec.update(ap_spent=2,ap_removed=1,rested_minutes_today=480,injuries_healed_today=3,center_injuries_today=2,injured_today=True,egg_progress=9)
        c.counters['item-use']=3;c.injuries=1;c.hp=17;c.temp_hp=5;c.conditions.add('독');c.faint_recovery_seconds=271
        # Reconcile the directly edited injury fixture before measuring a session boundary.
        e.time_actors([c])
        before=(copy.deepcopy({k:v for k,v in c.spec.items() if k!='frequency_state'}),copy.deepcopy(c.counters),c.hp,c.temp_hp,c.injuries,set(c.conditions),c.faint_recovery_seconds,e.elapsed_seconds,F.state(c)['day'],F.state(c)['scene'],F.state(c)['turn'])
        e.begin_session('s2')
        after=(copy.deepcopy({k:v for k,v in c.spec.items() if k!='frequency_state'}),copy.deepcopy(c.counters),c.hp,c.temp_hp,c.injuries,set(c.conditions),c.faint_recovery_seconds,e.elapsed_seconds,F.state(c)['day'],F.state(c)['scene'],F.state(c)['turn'])
        self.assertEqual(after,before)
    def test_scene_activation_is_not_refreshed(self):
        e,c=self.setup_pair();self.consume(e,c,'장면',key='test_fixture/scene')
        e.begin_session('s2');self.assertFalse(self.allowed(e,c,'장면',key='test_fixture/scene'))
    def test_off_field_actor_receives_same_boundary(self):
        e,c=self.setup_pair(defer=True);other=self.actor('off field');other.on_field=False
        e.time_actors([other]);self.consume(e,c);self.consume(e,other)
        e.begin_encounter([c]);e.begin_session('s2');e.end_encounter([c])
        self.assertTrue(self.allowed(e,c));self.assertTrue(self.allowed(e,other));self.assertFalse(other.on_field)
    def test_daily_move_unused_quota_is_preserved(self):
        e,c=self.setup_pair();mid=self.daily_move(e,c)
        e.begin_session('s2');self.assertTrue(F.move_allowed(e,c,mid)[0])
        self.assertEqual(c.move_uses.get(mid,0),0)
    def test_daily_move_spent_quota_is_not_restored_by_session(self):
        e,c=self.setup_pair();mid=self.daily_move(e,c);F.consume_move(e,c,mid)
        e.begin_session('s2');ok,why=F.move_allowed(e,c,mid)
        self.assertFalse(ok);self.assertIn('미해석',why);self.assertIn('세션',why)
        self.assertEqual(c.move_uses[mid],1)
    def test_center_restoration_keeps_once_per_scene_restriction(self):
        e,c=self.setup_pair();mid=self.daily_move(e,c);F.consume_move(e,c,mid);e.begin_session('s2')
        DT.pokemon_center(e,c)
        self.assertEqual(c.move_uses.get(mid,0),0)
        ok,why=F.move_allowed(e,c,mid);self.assertFalse(ok);self.assertIn('한 장면',why)
        e.end_scene([c]);self.assertTrue(F.move_allowed(e,c,mid)[0])
    def test_eligible_extended_rest_preserves_existing_move_path(self):
        e,c=self.setup_pair();mid=self.daily_move(e,c);F.consume_move(e,c,mid);e.begin_session('s2')
        DT.new_day(c);DT.extended_rest(e,c,4)
        self.assertEqual(c.move_uses.get(mid,0),0)
        self.assertNotIn(mid,F.state(c).get('session_move_refresh_pending',[]))
    def test_same_day_extended_rest_does_not_restore_daily_move(self):
        e,c=self.setup_pair();mid=self.daily_move(e,c);F.consume_move(e,c,mid);e.begin_session('s2')
        DT.extended_rest(e,c,4);self.assertEqual(c.move_uses[mid],1)
    def test_default_daily_move_still_needs_explicit_recovery(self):
        e=Engine(self.rules);c=self.actor();mid=self.daily_move(e,c);F.consume_move(e,c,mid);DT.new_day(c)
        self.assertEqual(c.move_uses[mid],1);DT.extended_rest(e,c,4);self.assertEqual(c.move_uses.get(mid,0),0)
    def test_explicit_full_frequency_restore_removes_pending_marker(self):
        e,c=self.setup_pair();mid=self.daily_move(e,c);F.consume_move(e,c,mid);e.begin_session('s2')
        F.restore_all_moves(c);self.assertEqual(c.move_uses,{})
        self.assertFalse(F.state(c).get('session_move_refresh_pending'));self.assertTrue(F.move_allowed(e,c,mid)[0])
    def test_snapshot_restores_pending_session_and_usage(self):
        e,c=self.setup_pair(defer=True);e.gm.everyone=[c];self.consume(e,c)
        e.begin_encounter();e.begin_session('s2');e.gm.snapshot('pending')
        e.end_encounter();self.consume(e,c);e.gm.restore('pending')
        self.assertEqual((e.session_id,e.pending_session_id,e.session_epoch,e.encounter_active),('s1','s2',0,True))
        self.assertFalse(self.allowed(e,c));e.end_encounter();self.assertTrue(self.allowed(e,c))
    def test_session_actor_cannot_silently_enter_game_day_engine(self):
        e,c=self.setup_pair();other=Engine(self.rules)
        with self.assertRaises(ValueError):F.activation_allowed(c,KEY,'하루',engine=other)
    def test_same_id_call_can_admit_new_participant_without_reset(self):
        # Interface registration invariant, not an additional game rule.
        e,c=self.setup_pair();other=self.actor('late participant')
        F.consume_activation(other,KEY,'하루')
        self.assertEqual(e.begin_session('s1',[other]),'unchanged')
        e.begin_session('s2')
        self.assertTrue(self.allowed(e,other))

    def test_source_anchors_and_bidirectional_condition_links(self):
        from pypdf import PdfReader
        review=json.loads(source_review_path().read_text(encoding='utf-8'));pdf=None
        self.assertIs(review['whole_rule_certified'],False)
        condition_ids={c['id'] for c in review['conditions']}
        for name,ids in TEST_CONDITIONS.items():
            self.assertTrue(set(ids)<=condition_ids)
            for cid in ids:
                condition=next(c for c in review['conditions'] if c['id']==cid)
                self.assertIn('SESSION-'+name,condition['runtime_test_ids'])
        for condition in review['conditions']:
            self.assertTrue(condition['runtime_test_ids'])
            for tid in condition['runtime_test_ids']:
                self.assertIn(condition['id'],TEST_CONDITIONS[tid.removeprefix('SESSION-')])
        for anchor in review['source_anchors']:
            path=ROOT/anchor['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),anchor['file_sha256'])
            excerpt=anchor['excerpt']
            self.assertEqual(hashlib.sha256(excerpt.encode()).hexdigest(),anchor['excerpt_sha256'])
            if anchor['kind']=='markdown':
                actual='\n'.join(path.read_text(encoding='utf-8').splitlines()[anchor['start']-1:anchor['end']])
                self.assertEqual(actual,excerpt)
            else:
                if pdf is None:pdf=PdfReader(str(path))
                page=pdf.pages[anchor['page_index']].extract_text()
                self.assertEqual(hashlib.sha256(page.encode()).hexdigest(),anchor['page_text_sha256'])
                self.assertIn(excerpt,page)

if __name__=='__main__':
    class Result(unittest.TextTestResult):
        def __init__(self,*a,**k):super().__init__(*a,**k);self.rows=[]
        def addSuccess(self,t):super().addSuccess(t);self.rows.append(dict(id='SESSION-'+t._testMethodName,status='pass',condition_ids=TEST_CONDITIONS.get(t._testMethodName,[])))
        def addFailure(self,t,e):super().addFailure(t,e);self.rows.append(dict(id='SESSION-'+t._testMethodName,status='fail',condition_ids=TEST_CONDITIONS.get(t._testMethodName,[])))
        def addError(self,t,e):super().addError(t,e);self.rows.append(dict(id='SESSION-'+t._testMethodName,status='error',condition_ids=TEST_CONDITIONS.get(t._testMethodName,[])))
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.loadTestsFromTestCase(SessionFrequencyTests))
    files=['tools/test_session_frequency.py','data/verification/session-frequency-source-review.json','engine/engine.py','engine/frequency.py','engine/gm_state.py','engine/downtime.py','engine/items.py','engine/effects.py','engine/damage_reactions.py','input/ch11-running-the-game.md','input/ch07-combat.md','input/ch10-index-reference.md']
    review=json.loads(source_review_path().read_text(encoding='utf-8'))
    files=list(dict.fromkeys(files+[a['file'] for a in review['source_anchors']]))
    report=dict(source_review_sha256=hashlib.sha256(source_review_path().read_bytes()).hexdigest(),scope='Optional session activation period only; daily Move automatic session refill remains unresolved.',whole_rule_certified=False,results=result.rows,input_hashes={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    target=ROOT/'output/session-frequency-tests.json' if Path(__file__).resolve().parent==ROOT/'tools' else Path(__file__).with_suffix('.results.json')
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
