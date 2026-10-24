"""Actual Confusion draws and HP consequences at native Move completion."""
from pathlib import Path
from copy import deepcopy
import json,unittest
from unittest.mock import patch
import test_attack_loss_provenance as FIX
from engine import Engine,Combatant
from state_codec import load_engine
import turn as TURN
import state_fields as F
import temporary_hp as TEMP
import confusion_attacks as CONFUSION
import move_completion as COMPLETE
import control_mount as MOUNT


class ConfusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from engine import Rules
        cls.r=Rules(str(FIX.ROOT),ruleset='core-confusion-feb2016')
    def setUp(self):
        self.e=Engine(self.r,1);self.e.everyone=self.e.gm.everyone=[]
        self.a=self.actor('attacker');self.b=self.actor('target');TURN.reset_budget(self.e,self.a)
        self.e.apply_status(self.a,'혼란')

    def actor(self,name):
        c=Combatant(self.r,dict(name=name,kind='pokemon',level=20,
            stats={'hp':30,'atk':31,'spa':45,'def':30,'spd':30,'spe':30},
            types=['노말'],moves=['move/스피드스타','move/분노의앞니','move/용의분노','move/칼춤','move/불태우기','move/미래예지'],
            abilities=[],movement={'land':4}))
        c.side='party' if name=='attacker' else 'foes';self.e.everyone.append(c);return c

    def latest(self):return list(self.e._move_completions.values())[-1]

    def use(self,mid,target=None):return self.e.use_move_on(self.a,target or self.b,mid,self.e.everyone)

    def test_actual_physical_special_and_no_accuracy_status_use_correct_loss_once(self):
        for mid,stat in (('move/분노의앞니','atk'),('move/스피드스타','spa'),('move/칼춤',None)):
            with self.subTest(move=mid):
                self.setUp();expected=self.a.staged(stat)//2 if stat else 2*self.e.tick(self.a)
                TEMP.grant(self.e,self.a,5);hp=self.a.hp
                self.use(mid,self.a if stat is None else self.b)
                row=self.latest();self.assertEqual(row['phase'],'complete');self.assertEqual(row['confusion']['face'],1)
                self.assertEqual(row['confusion']['result']['amount'],expected)
                self.assertEqual((self.a.hp,self.a.temp_hp),(hp-expected+5,0))
                self.assertEqual(self.a.budget['standard'],0)
                if stat is None:self.assertEqual(self.a.stages['atk'],2)
                before=self.e.export_state();self.e.resume_confusion_completion(row['id'])
                self.assertEqual(self.e.export_state(),before)

    def test_successful_confusion_die_and_refused_attack_have_no_self_loss(self):
        self.e.rng.seed(0);hp=self.a.hp;self.use('move/스피드스타')
        self.assertEqual(self.latest()['confusion']['face'],2);self.assertEqual(self.a.hp,hp)
        self.assertEqual(self.latest()['confusion']['result']['reason'],'no_self_hit')
        state=lambda:(self.a.hp,self.a.temp_hp,deepcopy(self.a.budget),deepcopy(self.a.move_uses),
                      deepcopy(self.latest()['confusion']),len(self.e._move_completions),self.e.rng.getstate())
        before=state();self.use('move/스피드스타');self.assertEqual(state(),before)

    def test_missed_attack_still_consumes_failed_confusion_once(self):
        hp=self.a.hp
        with patch.object(self.e,'d20',return_value=1):self.use('move/분노의앞니')
        row=self.latest();self.assertFalse(any(x['hit'] for x in row['results'].values()))
        self.assertEqual(hp-self.a.hp,self.a.staged('atk')//2)
        self.assertEqual(row['confusion']['face'],1)

    def test_late_loss_failure_retains_paid_attack_and_retries_only_consequence(self):
        hp=self.a.hp;other=self.b.hp;original=MOUNT.confusion_loss
        def fail(e,*args,**kw):
            original(e,*args,**kw);raise ValueError('late confusion failure')
        with patch.object(MOUNT,'confusion_loss',fail):
            with self.assertRaisesRegex(ValueError,'late confusion'):self.use('move/스피드스타')
        row=self.latest();self.assertEqual(self.a.hp,hp);self.assertLess(self.b.hp,other)
        self.assertEqual(row['phase'],'completion_effects');self.assertIsNone(row['confusion']['result'])
        before_rng=self.e.rng.getstate();other=self.b.hp;budget=deepcopy(self.a.budget)
        with self.assertRaisesRegex(ValueError,'pending Confusion'):self.use('move/용의분노')
        self.e.resume_confusion_completion(row['id'])
        self.assertEqual(self.b.hp,other);self.assertEqual(self.a.budget,budget);self.assertEqual(self.e.rng.getstate(),before_rng)
        self.assertEqual(hp-self.a.hp,self.a.staged('spa')//2)

    def pending_group(self):
        from test_category2_csv_item_transfers import Tests as Fixtures
        from grid import Grid
        f=Fixtures();f.r=self.r
        e,a,b,c,mid=f.fixture('불태우기',held=(None,'선제공격손톱','예리한손톱'),seed=1)
        e.grid=Grid(10,10);e.apply_status(a,'혼란');hp=a.hp
        e.use_move_on(a,b,mid,e.everyone)
        row=list(e._move_completions.values())[-1]
        self.assertEqual(row['confusion']['face'],1);self.assertIsNone(row['confusion']['result'])
        self.assertEqual(a.hp,hp)
        import equipment_actions as EQUIPMENT
        self.assertEqual(len(EQUIPMENT.pending(e)),2)
        return e,a,b,c,row['id']

    def test_all_actual_recipients_wait_and_both_restores_resume_one_self_hit(self):
        import equipment_actions as EQUIPMENT
        import world_entities as W
        for mode in ('gm','json'):
            with self.subTest(mode=mode):
                e,a,b,c,token=self.pending_group();hp=a.hp
                snapshot=e.gm.snapshot();saved=e.export_state()
                first=EQUIPMENT.pending(e)[0];EQUIPMENT.resolve(e,first['target'],first['id'],choice='drop')
                self.assertEqual(a.hp,hp)
                if mode=='gm':e.gm.restore(snapshot)
                else:e=load_engine(self.r,json.loads(json.dumps(saved,ensure_ascii=False)))
                index=W.actor_index(e);a=index[a.entity_id]
                for n in range(2):
                    row=EQUIPMENT.pending(e)[0];EQUIPMENT.resolve(e,row['target'],row['id'],choice='drop')
                    self.assertEqual(a.hp,hp-(a.staged('spa')//2 if n else 0))
                self.assertEqual(e._move_completions[token]['phase'],'complete')
                before=e.export_state();e.resume_confusion_completion(token);self.assertEqual(e.export_state(),before)

    def test_actual_sleep_before_pending_attack_finishes_prevents_confusion_loss(self):
        import equipment_actions as EQUIPMENT
        e,a,b,c,token=self.pending_group();hp=a.hp;e.apply_status(a,'잠듦')
        for row in list(EQUIPMENT.pending(e)):EQUIPMENT.resolve(e,row['target'],row['id'],choice='drop')
        self.assertEqual(a.hp,hp);self.assertIn('잠듦',a.conditions)
        self.assertEqual(e._move_completions[token]['confusion']['result']['reason'],'asleep')

    def test_actual_end_turn_saves_and_sleep_exception_preserve_opportunity_prohibition(self):
        for asleep,seed,cured in ((False,31,False),(False,5,True),(True,5,False)):
            with self.subTest(asleep=asleep,seed=seed):
                self.setUp();self.e.start_round(self.e.everyone);self.e.start_of_turn(self.a)
                self.assertFalse(TURN.can_aoo(self.e,self.a))
                if asleep:self.e.apply_status(self.a,'잠듦')
                self.e.rng.seed(seed);self.e.end_of_turn(self.a)
                self.assertEqual('혼란' not in self.a.conditions,cured)

    def test_empty_field_move_uses_real_activation_without_inventing_accuracy(self):
        from test_category2_smoke_regions import SmokeTests
        from test_category2_csv_item_transfers import Tests as Fixtures
        f=Fixtures();f.r=self.r;s=SmokeTests();s.fixtures=f
        e,a,b=s.fixture();b.pos=(15,15);s.smoke(e,a,b)
        e.start_round(e.everyone);e.start_of_turn(a,initiative_count=20)
        e.apply_status(a,'혼란');e.rng.seed(1);hp=a.hp
        with patch.object(Engine,'accuracy_check',side_effect=AssertionError('empty field must not roll accuracy')):
            e.use_move_on(a,a,'move/날려버리기',e.everyone,aim=(5,5))
        row=list(e._move_completions.values())[-1]
        self.assertEqual(row['phase'],'complete');self.assertEqual(row['targets'],[])
        self.assertEqual(row['confusion']['face'],1);self.assertEqual(hp-a.hp,2*e.tick(a))
        self.assertTrue(e.validate_state()['valid'])

    def test_delayed_attack_retains_original_draw_and_sleep_exception_until_real_hit(self):
        from test_category2_delayed_attacks import DelayedAttackTests
        f=DelayedAttackTests();f.rules=self.r
        e,a,b=f.world('move/미래예지');e.apply_status(a,'혼란');e.rng.seed(1);hp=a.hp
        e.use_move_on(a,b,'move/미래예지',e.everyone)
        row=list(e._move_completions.values())[-1];token=row['id']
        self.assertEqual(row['confusion']['face'],1);self.assertIsNone(row['confusion']['result']);self.assertEqual(a.hp,hp)
        e.apply_status(a,'잠듦')
        loaded=load_engine(self.r,json.loads(json.dumps(e.export_state(),ensure_ascii=False)))
        import world_entities as W
        index=W.actor_index(loaded);a,b=index[a.entity_id],index[b.entity_id]
        loaded.rng.seed(31)  # Actual end-of-turn Sleep save fails before delayed impact.
        f.finish_target_turn(loaded,a,b)
        self.assertEqual(loaded._move_completions[token]['phase'],'complete')
        self.assertEqual(loaded._move_completions[token]['confusion']['result']['reason'],'asleep')
        self.assertEqual(a.hp,hp)

    def test_changed_confusion_policy_refuses_before_cost_or_randomness(self):
        state=lambda:(deepcopy(self.a.budget),deepcopy(self.a.move_uses),self.a.hp,self.b.hp,
                      set(self.a.conditions),self.e.rng.getstate(),len(getattr(self.e,'_move_completions',{})))
        before=state();original=self.r.condition_effects
        def changed(name):
            rows=deepcopy(original(name))
            if name=='혼란':next(x for x in rows if x['type']=='on_attack_roll')['die']='1d3'
            return rows
        with patch.object(self.r,'condition_effects',changed):
            with self.assertRaisesRegex(ValueError,'reviewed'):self.use('move/스피드스타')
        self.assertEqual(state(),before)

    def test_native_mounted_attack_self_hit_uses_existing_retention_once(self):
        from test_foundation_control_mount import MountTests
        MountTests.setUpClass();f=MountTests();f.r=self.r;f.setUp();f.native();f.begin(f.a)
        f.t.pos=(3,3);f.e.apply_status(f.a,'혼란');f.e.rng.seed(1);hp=f.a.hp
        f.e.use_move_on(f.a,f.t,'struggle',f.e.everyone)
        row=list(f.e._move_completions.values())[-1]
        self.assertEqual(row['confusion']['face'],1)
        self.assertEqual(hp-f.a.hp,f.a.staged('atk')//2)
        history=f.a.custom_conditions['mount_retention_history']
        self.assertEqual(len(history),1);self.assertEqual(history[0]['event'],'confusion')
        before=f.snap();f.e.resume_confusion_completion(row['id']);self.assertEqual(f.snap(),before)

    def test_changed_draw_or_completion_cannot_survive_world_validation(self):
        self.use('move/스피드스타');row=self.latest();actual=deepcopy(row['confusion'])
        row['confusion']['face']=2
        self.assertFalse(self.e.validate_state()['valid'])
        row['confusion']=deepcopy(actual);row['confusion']['result']['amount']+=1
        self.assertFalse(self.e.validate_state()['valid'])
        row['confusion']=actual;self.assertTrue(self.e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
