"""Only the actual Rider gaps/difference; the unchanged Rider body reuses Book proof."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine
import test_book_conquerors_march as BASE
import conquerors_march as CM,control_mount as M,pass_moves as PASS
import trainer_feature_acquisition as A,state_fields as SF,state_codec as CODEC
import state_grants as G,world_entities as W,frequency as F,action_points as AP
import feature_ability_lessons as LESSONS,ability_transitions as AB

AREA=BASE.FAMILY_MOVES['파열']

class RiderFullTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rules=Rules(ROOT,ruleset='all')

    def setUp(self):
        self.original_answers=deepcopy(self.rules.rulings.answers)
        self.original_hooks={key:list(value) for key,value in self.rules.rulings.hooks.items()}
        self.original_effects=deepcopy(self.rules.rulings.effects)
        self.original_ruling_log=deepcopy(self.rules.rulings.log)

    def tearDown(self):
        self.rules.rulings.answers[:]=self.original_answers
        self.rules.rulings.hooks={key:list(value) for key,value in self.original_hooks.items()}
        self.rules.rulings.effects=deepcopy(self.original_effects)
        self.rules.rulings.log[:]=self.original_ruling_log

    def setup(self,*,run_up=True,mounted=True,feature=None):
        self.tearDown()
        self.h=BASE.ConquerorsMarchTests();self.h.rules=self.rules
        self.h.setup(run_up=run_up,mounted=mounted,moves=list(BASE.FAMILY_MOVES.values()))
        self.sync()
        self.a.spec['skills']['격투']=3
        if feature is not None:
            self.h.acquire(M.RIDE_AS_ONE)
            if feature in (CM.REPRISAL,CM.OVERRUN):
                SF.base_patch(self.a,{'skills':{'곡예':5,'육상':3,'격투':3,'명령':3}},reason='actual Expert Rider qualification')
            self.h.acquire(feature)
        self.enemy.spec['moves']=[AREA,'move/몸통박치기'];self.enemy.moves=list(self.enemy.spec['moves'])

    def sync(self):
        self.e,self.a,self.p,self.enemy,self.other=self.h.e,self.h.a,self.h.p,self.h.enemy,self.h.other
    def acquire(self,uid):return self.h.acquire(uid)
    def restore(self):self.h.restore();self.sync()
    def valid(self):self.h.valid()
    def answer(self,key,value):self.e.rulings.add_answer(key,value,reason='explicit actual player reaction choice',scope='session')
    def snapshot(self):return deepcopy((CODEC.dump_engine(self.e),self.e.rng.getstate()))
    def reject(self,fn):
        before=self.snapshot()
        with self.assertRaises(ValueError):fn()
        self.assertEqual(self.snapshot(),before)
    def combat(self,actor):self.h.start();self.e.start_of_turn(actor)
    def area(self,*,roll=15,mid=AREA):
        with patch.object(Engine,'d20',return_value=roll):
            return self.e.use_move_on(self.enemy,self.a,mid,self.e.everyone,set_damage=True)
    def gm_floor(self,mid):
        floors=[effect for effect in self.e.r.move_mech('move/칼등치기')[0]['effects_exec'] if effect['type']=='damage_floor']
        self.assertEqual(len(floors),1)
        self.e.rule_effect(mid,'add',deepcopy(floors[0]),reason='Explicit GM table override: this attack uses the core False Swipe floor; not a printed PTU combination',scope='campaign')
        self.assertTrue(any(row['kind']=='effect' and mid in row['what'] for row in self.e.rulings.log))
    def listener(self,actor,key):
        from hashlib import sha256
        source='input/'+self.rules.selection.units['combat/struggle']['source']['file']
        doc={'schema':1,'id':'event/rider-'+key,'variants':[{
            'rule_id':'combat/struggle','source':{'file':source,'sha256':sha256((ROOT/source).read_bytes()).hexdigest()},
            'inputs':{'hit':{'authority':'context','type':'boolean','question':'Native hit'},
                      'choice':{'authority':'gm','type':'boolean','question':'Actual reaction choice'}},
            'when':{'op':'eq','left':{'$input':'hit'},'right':True},
            'values':{'effects':[{'type':'stage_change','stat':'atk','delta':1,'target':'self'}]}}]}
        return self.e.subscribe_source_policy(actor,key,doc,event='move_resolved',inputs={'hit':'hit'})
    def choose_listener(self,event,actor,listener):
        return self.e.choose_passive_event(event,actor,listener,
            {'decisions':{'choice':{'value':True,'reason':'actual native listener choice'}}})
    def lesson(self,**kw):
        opts=dict(target=self.p,feature=CM.RAMMING,ability=CM.RUN_UP,seconds=45,reason='observed complete Extended Run Up lesson')
        opts.update(kw)
        return self.e.pokemon_activity(self.a,'teach_feature_ability',**opts)

    def test_ramming_actual_extended_payment_permanent_grant_and_codec(self):
        self.setup(run_up=False,mounted=False)
        self.p.spec['tutor_points']=2
        result=self.lesson()
        self.assertEqual((result['source'],result['ability'],result['point_cost']),(CM.RAMMING,CM.RUN_UP,2))
        self.assertEqual((self.p.spec['tutor_points'],self.e.elapsed_seconds),(0,45))
        self.assertTrue(AB.active(self.p,CM.RUN_UP))
        payment=self.p.spec[G.KEY]['payments'][result['payment']['group_id']]
        self.assertEqual(payment['paid'],2)
        source=self.p.spec[G.KEY]['sources'][payment['children'][0]]
        self.assertEqual((source['owner_id'],source['lifetime']),(None,None))
        self.restore();self.assertTrue(AB.active(self.p,CM.RUN_UP));self.valid()
        self.reject(self.lesson)
        self.h.board();self.h.start();self.h.order();self.h.close(self.a);self.e.start_of_turn(self.p)
        with patch.object(Engine,'d20',return_value=15):row=self.h.pass_move(BASE.FAMILY_MOVES['대시'])
        self.assertEqual(row['phase'],'complete');self.valid()

    def test_ramming_real_ownership_parent_balance_and_manual_fail_closed(self):
        self.setup(run_up=False,mounted=False);self.p.spec['tutor_points']=1
        self.reject(self.lesson);self.p.spec['tutor_points']=2
        self.reject(lambda:self.lesson(ability='ability/철주먹'))
        self.reject(lambda:self.lesson(seconds=0))
        self.reject(lambda:self.e.manual_feat(self.a,CM.RAMMING,self.p))
        self.p.spec['trainer_id']=self.enemy.entity_id
        self.reject(self.lesson)
        self.p.spec['trainer_id']=self.a.entity_id
        self.h.start();self.reject(self.lesson)

    def test_ramming_late_clock_payment_failure_is_atomic(self):
        self.setup(run_up=False,mounted=False);self.p.spec['tutor_points']=2
        with patch.object(LESSONS.PAYMENTS,'acquire',side_effect=ValueError('actual late payment failure')):
            self.reject(self.lesson)
        self.assertEqual(self.e.elapsed_seconds,0);self.assertFalse(AB.active(self.p,CM.RUN_UP))

    def test_real_three_reaction_acquisitions_parent_alternatives_speed_replay(self):
        self.setup(mounted=False)
        self.reject(lambda:self.acquire(CM.LEAN));self.reject(lambda:self.acquire(CM.REPRISAL))
        self.acquire(M.RIDE_AS_ONE);before=self.a.stats['spe']
        self.acquire(CM.LEAN)
        self.reject(lambda:self.acquire(CM.REPRISAL));self.reject(lambda:self.acquire(CM.OVERRUN))
        SF.base_patch(self.a,{'skills':{'곡예':3,'육상':5,'명령':3}},reason='actual Expert Athletics alternative')
        rows=[self.acquire(uid) for uid in (CM.REPRISAL,CM.OVERRUN)]
        self.assertEqual(self.a.stats['spe'],before+3)
        SF.base_patch(self.a,{'skills':{'곡예':1,'육상':1}},reason='historical rank loss after acquisition')
        self.restore()
        for uid,row in zip((CM.REPRISAL,CM.OVERRUN),rows):self.assertEqual(self.acquire(uid),row)
        self.valid()

    def test_csv_all_five_families_keep_dash_and_pass_in_real_native_hits(self):
        for family,mid in list(BASE.FAMILY_MOVES.items())[:5]:
            with self.subTest(family=family):
                self.setup();self.h.start()
                self.e.conquerors_march(self.a,self.p,event_id='csv/order',edition=CM.CSV)
                self.h.close(self.a);self.e.start_of_turn(self.p)
                seen=[];native=Engine._apply_hit_recipient
                def observe(e,a,t,move_id,move,*args,**kw):
                    if a.entity_id==self.p.entity_id:
                        self.assertIn('대시',move['range']);self.assertIn('통과',move['range'])
                        self.assertIn('대시',move['keywords']);self.assertIn('통과',move['keywords']);seen.append(t.entity_id)
                    return native(e,a,t,move_id,move,*args,**kw)
                with patch.object(Engine,'d20',return_value=15),patch.object(Engine,'_apply_hit_recipient',observe):
                    row=self.h.pass_move(mid)
                self.assertEqual(seen,[self.enemy.entity_id,self.other.entity_id])
                self.assertEqual(self.p.move_uses[mid],1);self.assertEqual(self.p.budget['standard'],0)
                self.restore();self.valid()

    def test_csv_selection_is_exact_idempotent_and_book_remains_pass_only(self):
        self.setup();self.h.start()
        self.reject(lambda:self.e.conquerors_march(self.a,self.p,event_id='bad',edition='csv'))
        row=self.e.conquerors_march(self.a,self.p,event_id='csv/order',edition=CM.CSV)
        self.assertEqual(self.e.conquerors_march(self.a,self.p,event_id='csv/order',edition=CM.CSV),row)
        self.reject(lambda:self.e.conquerors_march(self.a,self.p,event_id='csv/order'))
        self.restore();self.h.close(self.a);self.e.start_of_turn(self.p)
        before=self.p.budget['standard']
        with patch.object(Engine,'d20',return_value=15):self.h.pass_move(BASE.FAMILY_MOVES['대시'])
        self.assertEqual(before-self.p.budget['standard'],1)
        self.setup();self.h.start();self.h.order();self.h.close(self.a);self.e.start_of_turn(self.p)
        native=Engine._apply_hit_recipient;seen=[]
        def observe(e,a,t,mid,move,*args,**kw):
            if a.entity_id==self.p.entity_id:self.assertNotIn('대시',move['range']);seen.append(t.entity_id)
            return native(e,a,t,mid,move,*args,**kw)
        with patch.object(Engine,'d20',return_value=15),patch.object(Engine,'_apply_hit_recipient',observe):self.h.pass_move(BASE.FAMILY_MOVES['대시'])
        self.assertEqual(len(seen),2);self.valid()

    def test_csv_source_drift_is_rejected_before_action(self):
        self.setup();self.h.start()
        with patch.dict(CM.CSV_SOURCE,{'sha256':'0'*64}):
            self.reject(lambda:self.e.conquerors_march(self.a,self.p,event_id='csv/drift',edition=CM.CSV))

    def test_overrun_uses_actual_roll_speed_and_target_reduction(self):
        results=[]
        for chosen in (False,True):
            self.setup(feature=CM.OVERRUN);self.answer('rider_overrun',chosen);self.combat(self.p)
            before=self.enemy.hp
            with patch.object(Engine,'d20',return_value=15):
                damage=self.e.use_move_on(self.p,self.enemy,BASE.FAMILY_MOVES['대시'],self.e.everyone,set_damage=True)
            self.assertEqual(before-self.enemy.hp,damage)
            results.append(damage)
            state=F.state(self.a)['activations']
            self.assertEqual(CM.OVERRUN in state,chosen)
            self.restore();self.valid()
        self.assertEqual(results[1]-results[0],25-18)

    def test_overrun_actual_pass_scene_twice_and_no_generic_passive(self):
        self.setup(feature=CM.OVERRUN);self.answer('rider_overrun',True);self.h.start();self.h.order()
        self.h.close(self.a);self.e.start_of_turn(self.p)
        with patch.object(Engine,'d20',return_value=15):self.h.pass_move(BASE.FAMILY_MOVES['대시'])
        self.assertFalse(F.activation_allowed(self.a,CM.OVERRUN,{'kind':'scene','uses':2},engine=self.e,action_actor=self.a))
        self.assertFalse(any(m.get('source')==CM.OVERRUN and m.get('type')=='damage_roll_mod' for m in self.p.modifiers))
        self.valid()

    def test_overrun_no_mount_no_run_up_non_dash_or_preview_never_spends(self):
        for mode in ('unmounted','no_run_up','ordinary'):
            self.setup(feature=CM.OVERRUN,run_up=mode!='no_run_up',mounted=mode!='unmounted')
            if mode=='unmounted':self.e.gm.set_position(self.a,(0,1),reason='actual dismounted Rider stands beside the mount')
            self.answer('rider_overrun',True);self.combat(self.p)
            mid='move/물대포' if mode=='ordinary' else BASE.FAMILY_MOVES['대시']
            if mid not in self.p.moves:
                self.e.gm.set_move(self.p,BASE.FAMILY_MOVES['파열(변화)'],add=False,reason='actual forgotten unused Move leaves one legal known-Move slot')
                self.e.gm.set_move(self.p,mid,reason='actual selected ranged non-Dash comparison Move')
            before=deepcopy(F.state(self.a))
            self.e.roll_damage(self.p,self.enemy,self.e.r.move(mid),False,True)
            self.assertEqual(F.state(self.a),before)
            with patch.object(Engine,'d20',return_value=15):self.e.use_move_on(self.p,self.enemy,mid,self.e.everyone,set_damage=True)
            self.assertNotIn(CM.OVERRUN,F.state(self.a)['activations']);self.valid()

    def test_reprisal_actual_adjacent_mount_hit_native_free_struggle_and_ap(self):
        self.setup(feature=CM.REPRISAL);self.answer('rider_reprisal',{'use':True,'options':{'set_damage':True}})
        self.combat(self.enemy);before=(self.enemy.hp,AP.available(self.a))
        self.assertFalse(hasattr(self.a,'budget'))
        with patch.object(Engine,'d20',return_value=15):self.e.use_move_on(self.enemy,self.p,'move/몸통박치기',self.e.everyone,set_damage=True)
        self.assertLess(self.enemy.hp,before[0]);self.assertEqual(AP.available(self.a),before[1]-1)
        self.assertFalse(hasattr(self.a,'budget'));self.assertEqual(self.a.move_uses.get('struggle',0),0)
        self.restore();self.valid()
        completion=next(row for row in self.e._move_completions.values() if row.get('rider_reprisal'))
        hp=self.enemy.hp;ap=AP.available(self.a);CM.after_move(self.e,completion)
        self.assertEqual((self.enemy.hp,AP.available(self.a)),(hp,ap))

    def test_reprisal_miss_rider_hit_decline_and_nonadjacent_never_charge(self):
        for mode in ('miss','rider','decline','distant'):
            self.setup(feature=CM.REPRISAL);self.answer('rider_reprisal',mode!='decline')
            mid='move/몸통박치기'
            if mode=='miss':
                self.e.gm.set_stage(self.enemy,'acc',value=-6,reason='actual reduced accuracy for the observed miss')
                self.e.gm.set_stage(self.p,'eva',value=6,reason='actual increased evasion for the observed miss')
            if mode=='distant':
                self.e.gm.set_position(self.enemy,(4,0),reason='observed nonadjacent triggering foe')
                mid='move/물대포';self.e.gm.set_move(self.enemy,mid,reason='actual ranged hit without a Dash approach')
            self.combat(self.enemy);ap=AP.available(self.a)
            with patch.object(Engine,'d20',return_value=1 if mode=='miss' else 15):
                self.e.use_move_on(self.enemy,self.a if mode=='rider' else self.p,mid,self.e.everyone,set_damage=True)
            self.assertEqual(AP.available(self.a),ap,mode);self.valid()

    def test_reprisal_counter_failure_rolls_back_triggering_hit_and_cost(self):
        self.setup(feature=CM.REPRISAL);self.answer('rider_reprisal',True);self.combat(self.enemy)
        native=Engine._apply_hit_recipient
        def fail(e,a,t,mid,*args,**kw):
            if mid=='struggle':raise ValueError('late actual counter failure')
            return native(e,a,t,mid,*args,**kw)
        with patch.object(Engine,'d20',return_value=15),patch.object(Engine,'_apply_hit_recipient',fail):
            self.reject(lambda:self.e.use_move_on(self.enemy,self.p,'move/몸통박치기',self.e.everyone,set_damage=True))

    def test_lean_actual_both_damage_resisted_before_either_hp_once_and_codec(self):
        results=[]
        for chosen in (False,True):
            self.setup(feature=CM.LEAN);self.answer('rider_lean_in',chosen);self.combat(self.enemy)
            old={c.entity_id:c.hp for c in (self.a,self.p)};seen=[];native=Engine.take_damage
            def observe(e,c,amount):
                if c.entity_id in old:
                    pair=getattr(e,'_rider_lean_pair',None)
                    self.assertIsNotNone(pair);self.assertTrue(pair['batch'])
                    if not seen:self.assertEqual([x.hp for x in (W.actor_index(e)[self.a.entity_id],W.actor_index(e)[self.p.entity_id])],list(old.values()))
                    seen.append((c.entity_id,amount))
                return native(e,c,amount)
            with patch.object(Engine,'take_damage',observe):total=self.area()
            damages=[old[c.entity_id]-c.hp for c in (self.a,self.p)]
            self.assertEqual(total,sum(damages));self.assertEqual(len(seen),2);results.append(damages)
            self.assertEqual(CM.LEAN in F.state(self.a)['activations'],chosen)
            self.restore();self.valid();self.assertFalse(hasattr(self.e,'_rider_lean_pair'))
        self.assertEqual(results[1],[x//2 for x in results[0]])

    def test_lean_one_miss_zero_damage_and_unmounted_never_spend(self):
        for mode in ('miss','zero','immune','unmounted'):
            self.setup(feature=CM.LEAN,mounted=mode!='unmounted');self.answer('rider_lean_in',True)
            if mode=='zero':
                self.e.gm.set_stat(self.p,'def',value=1000,reason='actual defense leaves native minimum one before typing')
                self.e.gm.set_types(self.p,['격투'],reason='actual Dark resistance makes native one times half round to zero before Lean')
            mid=AREA
            if mode=='immune':
                mid='move/폭음파'
                self.e.gm.set_move(self.enemy,mid,reason='actual known Normal Burst1 comparison attack')
                self.e.gm.set_types(self.p,['고스트'],reason='actual Normal immunity before native Boomburst')
            self.combat(self.enemy);hp=(self.a.hp,self.p.hp)
            if mode=='miss':
                native=Engine.accuracy_check
                def miss(e,a,t,move,situational=0,**kw):
                    if t.entity_id==self.p.entity_id:situational-=100
                    return native(e,a,t,move,situational,**kw)
                with patch.object(Engine,'accuracy_check',miss):self.area()
            else:self.area(mid=mid)
            self.assertNotIn(CM.LEAN,F.state(self.a)['activations'],mode);self.valid()
            if mode in ('zero','immune'):
                self.assertEqual(self.p.hp,hp[1]);self.assertLess(self.a.hp,hp[0])

    def test_lean_final_hooks_once_and_late_pair_failure_atomic(self):
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        calls=[]
        self.e.rulings.add_hook('before_damage',lambda value,ctx:calls.append(value) or value,reason='observe actual final post-choice damage')
        try:self.area()
        finally:self.e.rulings.hooks['before_damage'].pop()
        self.assertEqual(len(calls),2);self.assertTrue(all(x>0 for x in calls));self.valid()
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        native=Engine.take_damage
        def fail(e,c,amount):
            if c.entity_id==self.p.entity_id:raise ValueError('late second actual paired HP failure')
            return native(e,c,amount)
        with patch.object(Engine,'take_damage',fail):self.reject(self.area)
        self.assertNotIn(CM.LEAN,F.state(self.a)['activations'])

    def test_lean_reverse_recipient_order_uses_same_pair_and_single_quota(self):
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True)
        self.e.everyone[:]=[self.enemy,self.p,self.a,self.other]
        self.combat(self.enemy);old=(self.a.hp,self.p.hp);total=self.area()
        self.assertEqual(total,old[0]-self.a.hp+old[1]-self.p.hp)
        self.assertEqual(F.state(self.a)['activations'][CM.LEAN]['used'],1)
        self.valid()

    def test_lean_ordinary_single_target_is_not_area_and_scene_cap_is_two(self):
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        with patch.object(Engine,'d20',return_value=15):self.e.use_move_on(self.enemy,self.p,'move/몸통박치기',self.e.everyone,set_damage=True)
        self.assertNotIn(CM.LEAN,F.state(self.a)['activations'])
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        for n in range(3):
            self.area()
            self.assertEqual(F.state(self.a)['activations'][CM.LEAN]['used'],min(2,n+1))
            if n==2:break
            self.e.end_of_turn(self.enemy)
            for actor in (self.a,self.p):self.e.gm.set_hp(actor,value=actor.max_hp,reason='actual restorative treatment between attacks')
            self.e.start_round(self.e.everyone);self.e.start_of_turn(self.enemy);self.e.end_of_turn(self.enemy)
            self.e.start_round(self.e.everyone);self.e.start_of_turn(self.enemy)

    def test_lean_cold_saved_pre_action_reconstructs_actual_hit_group(self):
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        self.restore();old=(self.a.hp,self.p.hp);damage=self.area()
        self.assertEqual(damage,old[0]-self.a.hp+old[1]-self.p.hp)
        self.restore();self.valid();self.assertFalse(hasattr(self.e,'_rider_lean_pair'))

    def test_lean_partner_cancel_before_damage_does_not_spend(self):
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        import effects_ext as EXT
        native=EXT.blocks_hit
        def cancel(e,a,t,*args,**kw):
            if t.entity_id==self.p.entity_id:return 'actual cannot-hit recipient gate'
            return native(e,a,t,*args,**kw)
        with patch.object(EXT,'blocks_hit',cancel):self.area()
        self.assertNotIn(CM.LEAN,F.state(self.a)['activations'])

    def test_lean_partner_native_defense_wait_cold_resume_no_partial_hp(self):
        import passive_events as EVENTS
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        self.e.watch_move_defense(self.p,[{'actor_id':self.a.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual mounted ally observes its next defense offer')
        hp=(self.a.hp,self.p.hp)
        with self.assertRaises(EVENTS.PassiveEventPending):self.area()
        event=self.e._passive_pending
        self.assertEqual((self.a.hp,self.p.hp),hp);self.assertNotIn(CM.LEAN,F.state(self.a)['activations'])
        self.assertEqual((self.enemy.move_uses[AREA],self.enemy.budget['standard']),(1,0))
        self.valid();self.restore()
        with patch.object(Engine,'d20',side_effect=AssertionError('actual accuracy was already observed')):
            total=self.e.choose_move_defense(event,self.a,use=False,reason='actual pending intercept declined')
        self.assertEqual(total,hp[0]-self.a.hp+hp[1]-self.p.hp)
        self.assertEqual(F.state(self.a)['activations'][CM.LEAN]['used'],1)
        self.assertEqual(self.enemy.move_uses[AREA],1);self.assertIsNone(self.e._passive_pending)
        self.restore();self.valid()

    def test_lean_both_actual_return_listeners_cold_resume_each_without_hp_replay(self):
        import passive_events as EVENTS
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True)
        listener=self.listener(self.enemy,'paired-returns');self.combat(self.enemy)
        before=(self.a.hp,self.p.hp)
        with self.assertRaises(EVENTS.PassiveEventPending):self.area()
        first=self.e._passive_pending;completion=self.e._move_completions[self.e._passive_events[first]['completion_id']]
        second=completion['rider_pair_wait']['pending_id'];self.assertNotEqual(first,second)
        hp=(self.a.hp,self.p.hp);self.assertLess(hp[0],before[0]);self.assertLess(hp[1],before[1])
        self.assertEqual(F.state(self.a)['activations'][CM.LEAN]['used'],1)
        self.valid();self.restore()
        with patch.object(Engine,'d20',side_effect=AssertionError('returned hits must not reroll')),self.assertRaises(EVENTS.PassiveEventPending):
            self.choose_listener(first,self.enemy,listener)
        self.assertEqual(self.e._passive_pending,second);self.assertEqual((self.a.hp,self.p.hp),hp)
        self.valid();self.restore()
        with patch.object(Engine,'d20',side_effect=AssertionError('applied HP must not reroll')):
            total=self.choose_listener(second,self.enemy,listener)
        self.assertEqual(total,before[0]-hp[0]+before[1]-hp[1])
        self.assertEqual((self.a.hp,self.p.hp),hp);self.assertEqual(self.enemy.stages['atk'],2)
        self.assertEqual(self.enemy.move_uses[AREA],1);self.assertIsNone(self.e._passive_pending);self.valid()

    def test_lean_native_observed_selection_tampering_is_rejected_before_resume(self):
        import passive_events as EVENTS
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        self.e.watch_move_defense(self.p,[{'actor_id':self.a.entity_id,'source':'maneuver/근접-가로채기'}],reason='actual second recipient defense boundary')
        with self.assertRaises(EVENTS.PassiveEventPending):self.area()
        self.valid();self.restore();event=self.e._passive_pending
        completion=self.e._move_completions[self.e._passive_events[event]['completion_id']]
        first=self.e._passive_events[completion['rider_pair_wait']['first_id']]
        row=first['rider_damage_selection'];damage=row['damage'];row['damage']+=1
        self.assertFalse(self.e.validate_state()['valid'])
        row['damage']=damage;self.valid()
        for key in ('rider_damage_selection','rider_pair_source'):
            recorded=first.pop(key)
            self.assertFalse(self.e.validate_state()['valid'])
            first[key]=recorded;self.valid()
        with patch.object(Engine,'d20',side_effect=AssertionError('paid native accuracy is retained')):
            self.e.choose_move_defense(event,self.a,use=False,reason='actual observed defense declined after restoring original evidence')
        self.assertEqual(F.state(self.a)['activations'][CM.LEAN]['used'],1);self.valid()

    def test_lean_actual_partner_detect_after_cold_wait_keeps_first_hit_without_spend(self):
        import passive_events as EVENTS
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True)
        self.e.gm.set_move(self.p,BASE.FAMILY_MOVES['파열(변화)'],add=False,reason='actual forgotten unused Move leaves one legal known-Move slot')
        self.e.gm.set_move(self.p,'move/판별',reason='actual mount knows native Detect')
        self.combat(self.enemy)
        self.e.watch_move_defense(self.p,[{'actor_id':self.p.entity_id,'source':'move/판별'}],reason='actual mount watches its next hit for Detect')
        hp=(self.a.hp,self.p.hp)
        with self.assertRaises(EVENTS.PassiveEventPending):self.area()
        event=self.e._passive_pending;self.assertEqual((self.a.hp,self.p.hp),hp)
        self.valid();self.restore()
        with patch.object(Engine,'d20',return_value=15):self.e.choose_move_defense(event,self.p,use=True,reason='actual native Detect selected')
        self.assertLess(self.a.hp,hp[0]);self.assertEqual(self.p.hp,hp[1])
        self.assertNotIn(CM.LEAN,F.state(self.a)['activations']);self.assertEqual(self.p.move_uses['move/판별'],1)
        self.assertIsNone(self.e._passive_pending);self.restore();self.valid()

    def test_lean_nonlinear_final_hook_once_and_own_zero_still_consumes(self):
        self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True);self.combat(self.enemy)
        calls=[]
        def nonlinear(value,ctx):calls.append((value,ctx['target'].entity_id));return value*value//10000
        self.e.rulings.add_hook('before_damage',nonlinear,reason='actual one final nonlinear extension')
        hp=(self.a.hp,self.p.hp)
        try:self.area()
        finally:self.e.rulings.hooks['before_damage'].pop()
        self.assertEqual(len(calls),2);self.assertEqual({x[1] for x in calls},{self.a.entity_id,self.p.entity_id})
        self.assertEqual((self.a.hp,self.p.hp),hp)
        self.assertEqual(F.state(self.a)['activations'][CM.LEAN]['used'],1);self.valid()

    def test_lean_actual_false_swipe_and_explicit_gm_area_floor_zero_do_not_consume(self):
        # Preserve the printed False Swipe Pass guard, NOT whole-Pass certification.
        # Actual single/area recipient floor tests use explicit public GM overrides;
        # neither combination is claimed as a printed PTU False Swipe attack.
        for area in (False,True):
            self.setup(feature=CM.LEAN);self.answer('rider_lean_in',True)
            self.e.gm.set_move(self.enemy,'move/칼등치기',reason='actual known core False Swipe')
            self.e.gm.set_hp(self.p,value=1,reason='actual one remaining mount HP')
            self.combat(self.enemy)
            self.reject(lambda:self.e.use_move(self.enemy,self.p,'move/칼등치기',set_damage=True))
            self.gm_floor(AREA if area else 'move/몸통박치기')
            if area:self.area()
            else:
                with patch.object(Engine,'d20',return_value=15):self.e.use_move_on(self.enemy,self.p,'move/몸통박치기',self.e.everyone,set_damage=True)
            self.assertEqual(self.p.hp,1);self.assertNotIn(CM.LEAN,F.state(self.a)['activations']);self.valid()

    def test_reprisal_zero_damage_is_still_an_actual_hit(self):
        # Actual native single-recipient hit0 under an explicit public GM floor,
        # not a printed PTU combination or certification of False Swipe Pass.
        self.setup(feature=CM.REPRISAL);self.answer('rider_reprisal',{'use':True,'options':{'set_damage':True}})
        self.gm_floor('move/몸통박치기')
        self.e.gm.set_hp(self.p,value=1,reason='actual mount at one remaining HP')
        self.combat(self.enemy);ap=AP.available(self.a);hp=self.enemy.hp
        with patch.object(Engine,'d20',return_value=15):self.e.use_move_on(self.enemy,self.p,'move/몸통박치기',self.e.everyone,set_damage=True)
        self.assertEqual(self.p.hp,1);self.assertEqual(AP.available(self.a),ap-1);self.assertLess(self.enemy.hp,hp);self.valid()
        self.restore();hp=self.enemy.hp;ap=AP.available(self.a)
        completion=next(row for row in self.e._move_completions.values() if row.get('rider_reprisal'))
        CM.after_move(self.e,completion)
        self.assertEqual((self.enemy.hp,AP.available(self.a)),(hp,ap));self.valid()

    def test_lean_with_reprisal_native_child_wait_preserves_both_actual_hp_and_ap(self):
        import passive_events as EVENTS
        for mount_first in (False,True):
            self.setup(feature=CM.LEAN)
            SF.base_patch(self.a,{'skills':{'곡예':5,'육상':3,'격투':3,'명령':3}},reason='actual Expert Cavalier qualification')
            self.acquire(CM.REPRISAL);self.answer('rider_lean_in',True)
            self.answer('rider_reprisal',{'use':True,'options':{'set_damage':True}})
            if mount_first:self.e.everyone[:]=[self.enemy,self.p,self.a,self.other]
            listener=self.listener(self.a,'lean-cavalier-child');self.combat(self.enemy)
            ap=AP.available(self.a);old=(self.a.hp,self.p.hp)
            with self.assertRaises(EVENTS.PassiveEventPending):self.area()
            event=self.e._passive_pending;hp=(self.a.hp,self.p.hp,self.enemy.hp)
            self.assertLess(hp[0],old[0]);self.assertLess(hp[1],old[1])
            self.assertEqual((AP.available(self.a),F.state(self.a)['activations'][CM.LEAN]['used']),(ap-1,1))
            self.valid();self.restore()
            with patch.object(Engine,'d20',side_effect=AssertionError('both native hits already applied')):self.choose_listener(event,self.a,listener)
            self.assertEqual((self.a.hp,self.p.hp,self.enemy.hp),hp);self.assertEqual(AP.available(self.a),ap-1)
            self.assertEqual(self.enemy.move_uses[AREA],1);self.assertIsNone(self.e._passive_pending);self.valid()

    def test_reprisal_first_return_precedes_later_area_wait(self):
        import passive_events as EVENTS
        self.setup(feature=CM.REPRISAL);self.answer('rider_reprisal',{'use':True,'options':{'set_damage':True}})
        self.e.everyone[:]=[self.enemy,self.p,self.a,self.other]
        listener=self.listener(self.enemy,'reprisal-parent');self.combat(self.enemy)
        ap=AP.available(self.a);hp=self.enemy.hp
        with self.assertRaises(EVENTS.PassiveEventPending):self.area()
        first=self.e._passive_pending;self.assertIs(self.e._passive_events[first]['target'],self.p)
        self.assertEqual(AP.available(self.a),ap)
        with patch.object(Engine,'d20',return_value=15),self.assertRaises(EVENTS.PassiveEventPending):self.choose_listener(first,self.enemy,listener)
        self.assertEqual(AP.available(self.a),ap-1);self.assertLess(self.enemy.hp,hp)
        later=self.e._passive_pending;self.assertIs(self.e._passive_events[later]['target'],self.a)
        self.valid();self.restore();hp=self.enemy.hp
        with patch.object(Engine,'d20',side_effect=AssertionError('actual parent hits already observed')):self.choose_listener(later,self.enemy,listener)
        self.assertEqual((self.enemy.hp,AP.available(self.a)),(hp,ap-1));self.valid()

    def test_reprisal_child_struggle_wait_cold_resumes_unfinished_area_once(self):
        import passive_events as EVENTS
        self.setup(feature=CM.REPRISAL);self.answer('rider_reprisal',{'use':True,'options':{'set_damage':True}})
        self.e.everyone[:]=[self.enemy,self.p,self.a,self.other]
        listener=self.listener(self.a,'reprisal-child');self.combat(self.enemy)
        before=(self.a.hp,self.p.hp,self.enemy.hp,AP.available(self.a))
        with self.assertRaises(EVENTS.PassiveEventPending):self.area()
        child=self.e._passive_pending;self.assertIs(self.e._passive_events[child]['actor'],self.a)
        self.assertEqual(self.e._passive_events[child]['move_id'],'struggle')
        self.assertEqual(self.a.hp,before[0]);self.assertLess(self.p.hp,before[1]);self.assertLess(self.enemy.hp,before[2])
        hp=(self.p.hp,self.enemy.hp);self.assertEqual(AP.available(self.a),before[3]-1)
        self.valid();self.restore()
        with patch.object(Engine,'d20',return_value=15):self.choose_listener(child,self.a,listener)
        self.assertEqual((self.p.hp,self.enemy.hp),hp);self.assertLess(self.a.hp,before[0])
        self.assertEqual(AP.available(self.a),before[3]-1);self.assertEqual(self.enemy.move_uses[AREA],1)
        self.assertIsNone(self.e._passive_pending);self.restore();self.valid()

if __name__=='__main__':unittest.main()
