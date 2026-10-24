"""Prepared actual source-to-handoff scenarios; no inherited test collection."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'engine'),str(ROOT/'tools')]
from engine import Rules,Engine,Combatant
from builder import build_pokemon
from native_scenario_fixture import prepare_body,assert_rejected_unchanged
import native_switch_transfer as SWITCH
import native_order_transfer as TRANSFER
import class_passive_combat as CLASS
import combat_timing as TIME
import state_codec as CODEC


class NativeSwitchSourceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core=Rules(ROOT,ruleset='core');cls.all=Rules(ROOT,ruleset='all')

    def helper(self,module,name,rules=None):
        rules=rules or self.core;previous=rules.rulings;rules.rulings=deepcopy(previous)
        self.addCleanup(setattr,rules,'rulings',previous)
        module=__import__(module);fixture=getattr(module,name)();fixture.rules=rules
        self.addCleanup(fixture.doCleanups)
        return fixture

    def reserve(self,e,owner,p,*,abilities=(),moves=()):
        q=Combatant(e.r,dict(name='actual transfer reserve',kind='pokemon',level=p.spec['level'],
            stats=deepcopy(p.spec['stats']),skills=deepcopy(p.spec.get('skills',{})),
            types=list(p.types),moves=list(moves),abilities=list(abilities),size='중형',weight_kg=30,
            movement={'land':6,'swim':0,'sky':0,'power':4},trainer_id=owner.entity_id,trainer=owner.name))
        e.gm.add_combatant(q,pos=(6,6),side=p.side,reason='actual separately created reserve')
        prepare_body(e,q,size='중형',offsets=[(0,0)],reason='actual reserve body')
        e.gm.observe_loyalty(q,6,reason='actual reserve obedience')
        e.gm.recall(q,reason='actual reserve before native handoff')
        return q

    def learn_baton(self,e,p):
        if SWITCH.BATON not in p.moves:
            if len(p.moves)>=6:e.gm.set_move(p,p.moves[-1],add=False,reason='actual known Move slot replacement')
            e.gm.set_move(p,SWITCH.BATON,reason='actual learned transfer Move')
        e.gm.observe_loyalty(p,6,reason='actual Baton obedience')

    def baton(self,e,owner,p,q):
        self.learn_baton(e,p)
        if e._active_turn_actor is not p:
            if e._active_turn_actor is not None:e.end_of_turn(e._active_turn_actor)
            e.start_of_turn(p,initiative_count=19)
        SWITCH.select(e,p,q,source=SWITCH.BATON,reason='actual source-specific replacement')
        e.use_move(p,p,SWITCH.BATON)
        self.assertFalse(p.on_field);self.assertTrue(q.on_field)

    def same_sustain(self,e,t,p,q,source,before,bindings):
        self.assertIsNone(CLASS._active(e,p,source))
        row=CLASS._active(e,q,source)[1]
        self.assertEqual({k:v for k,v in row.items() if k not in ('target_id',TRANSFER.KEY)},
                         {k:v for k,v in before.items() if k!='target_id'})
        self.assertEqual(TRANSFER.origin_id(row,q),p.entity_id)
        self.assertEqual(t.ap_account.identified_bindings(),bindings)
        self.assertEqual(row['target_id'],q.entity_id)
        return row

    def test_dress_moves_only_real_item_projections_keeps_wardrobe_and_original_count(self):
        import fashionista as DRESS
        f=self.helper('test_book_fashionista_wardrobe','FashionistaWardrobeTests');f.setUp();f.stocked()
        e,t,p=f.e,f.t,f.p;q=self.reserve(e,t,p)
        wardrobe=deepcopy(DRESS.chic(p))
        f.combat(t,count=20);DRESS.dress_to_impress(e,t,p)
        before=DRESS.dress_record(p);deadline=tuple(before['count_deadline'])
        keys=list(before['fashionista_dress']['registration_keys']);bonus=p.initiative_bonus
        registrations={key:deepcopy(p._item_reg[key]) for key in keys}
        self.baton(e,t,p,q)
        moved=DRESS.dress_record(q)
        self.assertEqual(tuple(moved['count_deadline']),deadline)
        self.assertEqual(q.initiative_bonus,bonus);self.assertEqual(p.initiative_bonus,0)
        self.assertEqual({key:q._item_reg[key] for key in keys},registrations)
        self.assertFalse(any(key in getattr(p,'_item_reg',{}) for key in keys))
        self.assertEqual(DRESS.chic(p),wardrobe)
        self.assertIsNone(DRESS.chic(q))
        loaded=CODEC.load_engine(e.r,json.loads(json.dumps(CODEC.dump_engine(e))))
        new=next(a for a in loaded.everyone if a.entity_id==q.entity_id)
        old=next(a for a in loaded.everyone if a.entity_id==p.entity_id)
        loaded.end_of_turn(old);loaded.end_round();loaded.start_round(loaded.everyone);loaded.at_initiative_count(20)
        self.assertIsNone(DRESS.dress_record(new));self.assertEqual(new.initiative_bonus,0)
        self.assertFalse(any(key in getattr(new,'_item_reg',{}) for key in keys))

    def test_profiling_keeps_original_archive_owner_and_active_end_on_new_holder(self):
        import chronicler as CH
        f=self.helper('test_book_chronicler_actions','ChroniclerActionTests');f.setUp();f.whole()
        e,t,p=f.e,f.t,f.p;q=self.reserve(e,t,p)
        f.archive_subject(f.b,'pokemon','transfer-archived-foe');f.communication();f.combat(t)
        facts=deepcopy(CH.profile_order(e,t,p));paid=t.ap_account.available()
        self.baton(e,t,p,q)
        row=CH.profiling_record(q)
        self.assertEqual(row['chronicler_profiling'],facts)
        self.assertEqual(t.ap_account.available(),paid)
        self.assertEqual(CH.accuracy_bonus(e,q,f.b,e.r.move('move/몸통박치기')),2)
        self.assertTrue(CH.defensive_ignored(e,q,f.b));self.assertIsNone(CH.profiling_record(p))
        e.end_of_turn(p)
        self.assertIsNone(CH.profiling_record(q));self.assertEqual(CH.accuracy_bonus(e,q,f.b,e.r.move('move/몸통박치기')),0)
        self.assertTrue(e.validate_state()['valid'])

    def dress_fixture(self,item):
        f=self.helper('test_book_fashionista_wardrobe','FashionistaWardrobeTests')
        create=f.add
        def initial_actor(name,kind,pos,**extra):
            if kind=='trainer':
                extra.update(classes=[SWITCH.CLASS],feats=['feat/퀵-스위치',SWITCH.ROUND_TRIP,SWITCH.TAG_IN],
                    skills=dict(f.common['skills'],곡예=5))
            return create(name,kind,pos,**extra)
        f.add=initial_actor;f.setUp();f.whole();f.chic()
        q=self.reserve(f.e,f.t,f.p)
        f.item('actual-dress-channel',item,f.p);f.store('actual-dress-channel','wardrobe:1')
        return f,q

    def test_dress_actual_stat_capability_and_ability_channels_survive_paid_tag_handoff(self):
        import fashionista as DRESS
        for item in ('item/돌격조끼','item/방진고글','item/풍선'):
            with self.subTest(item=item):
                f,q=self.dress_fixture(item);e,t,p=f.e,f.t,f.p
                baseline=q.stats['spd'];f.combat(t,count=20);DRESS.dress_to_impress(e,t,p)
                record=DRESS.dress_record(p);original=deepcopy(record['fashionista_dress'])
                paid=t.ap_account.available()
                SWITCH.select_tag_in(e,t,p,reason='actual paid Tag In for existing Dress projection')
                e.gm.recall(p,reason='actual source recall');e.gm.send_out(q,reason='actual next beneficiary')
                self.assertEqual(t.ap_account.available(),paid-1)
                self.assertEqual(DRESS.dress_record(q)['fashionista_dress'],original)
                self.assertIsNone(DRESS.dress_record(p));self.assertIsNone(DRESS.chic(q))
                self.assertEqual(DRESS.wardrobe_items(e,p),[item])
                if item=='item/돌격조끼':
                    self.assertEqual(q.stats['spd'],baseline+5)
                    self.assertIn('난동',p.conditions);self.assertIn('난동',q.conditions)
                elif item=='item/풍선':self.assertIn('부유',q.abilities);self.assertNotIn('부유',p.abilities)
                else:
                    e.gm.set_move(f.q,'move/수면가루',reason='actual powder immunity consumer')
                    e.end_of_turn(t);e.start_of_turn(f.q,initiative_count=19)
                    with patch.object(Engine,'d20',return_value=19):e.use_move_on(f.q,q,'move/수면가루',e.everyone,set_damage=True)
                    self.assertNotIn('잠듦',q.conditions)
                self.assertTrue(e.validate_state()['valid'])

    def test_dress_physical_item_ends_once_after_real_hit_on_transferred_holder(self):
        import fashionista as DRESS,consumption_execution as CONSUMPTION
        for item,terminal in (('item/풍선','destroyed'),('item/레드카드','consumed')):
            with self.subTest(item=item):
                f,q=self.dress_fixture(item);e,t,p=f.e,f.t,f.p
                f.combat(t,count=20);DRESS.dress_to_impress(e,t,p)
                SWITCH.select_tag_in(e,t,p,reason='actual paid transfer of the stored item effects')
                e.gm.recall(p,reason='actual recall');e.gm.send_out(q,reason='actual next beneficiary')
                e.gm.set_position(f.q,(q.pos[0]+1,q.pos[1]),reason='actual adjacent attacking body')
                e.gm.set_move(f.q,'move/몸통박치기',reason='actual learned attack')
                e.end_of_turn(t);e.start_of_turn(f.q,initiative_count=19)
                with patch.object(Engine,'d20',return_value=19):
                    e.use_move_on(f.q,q,'move/몸통박치기',e.everyone,set_damage=True)
                obj=e._physical_objects['actual-dress-channel']
                self.assertIn(terminal,obj)
                self.assertEqual(DRESS.wardrobe_items(e,p),[])
                self.assertEqual(DRESS.dress_record(q)['fashionista_dress']['registration_keys'],[])
                self.assertFalse(any(r.get('item_id')==item for r in q._item_reg.values()))
                if terminal=='consumed':
                    payments=[r for r in CONSUMPTION.validate(q).values() if r['item_stock'].get('instance_id')==obj['id']]
                    self.assertEqual(len(payments),1);self.assertEqual(payments[0]['outcome'],'applied')
                else:self.assertNotIn('부유',q.abilities)
                restored=CODEC.load_engine(e.r,json.loads(json.dumps(CODEC.dump_engine(e))))
                self.assertTrue(restored.validate_state()['valid'])

    def test_conqueror_keeps_paid_order_but_requires_new_holders_actual_run_up_and_mount(self):
        import conquerors_march as MARCH
        f=self.helper('test_book_conquerors_march','ConquerorsMarchTests');f.setup(mounted=False)
        e,t,p=f.e,f.a,f.p;q=self.reserve(e,t,p,abilities=['도움닫기'],moves=['move/니트로차지'])
        import trainer_feature_acquisition as ACQUIRE,juggler as JUGGLER
        e.gm.set_skill(t,'곡예',5,reason='actual Expert Acrobatics for the native Tag In chain')
        for feature in (JUGGLER.QUICK,JUGGLER.CLASS,JUGGLER.ROUND,JUGGLER.TAG):
            ACQUIRE.acquire_static(e,t,feature,acquisition_request_id='march-transfer/'+feature)
        e.gm.set_position(t,(0,2),reason='actual issuer beside the unmounted outgoing Pokemon')
        rider=Combatant(e.r,dict(name='actual independent rider',kind='trainer',level=20,
            stats=deepcopy(t.spec['stats']),skills={'육상':6},moves=[],edges=['edge/탑승-기량'],movement={'land':6}))
        e.gm.add_combatant(rider,pos=(0,1),side=p.side,reason='actual independent mounted consumer')
        prepare_body(e,rider,size='중형',offsets=[(0,0)],reason='actual rider body')
        e.register_abilities(q)
        f.start();e.start_of_turn(t,initiative_count=20);order=deepcopy(f.order())
        # Recall before the Pokemon turn: Baton Pass would spend the shared
        # turn right and leave this round's recipient unable to attack again.
        SWITCH.select_tag_in(e,t,p,reason='actual Tag In before either Pokemon acts')
        e.gm.recall(p,reason='actual selected recall');e.gm.send_out(q,pos=p.pos,reason='actual selected next release')
        self.assertEqual(MARCH.live(q)[0][MARCH.FLAG]['order_id'],order['id'])
        self.assertIsNone(MARCH.current(e,q));self.assertFalse(MARCH.live(p))
        e.end_of_turn(t);e.start_of_turn(rider,initiative_count=18)
        self.assertTrue(e.pokemon_activity(rider,'mounting',target=q,phase='mount',skill='육상',gm_mountable=True)['passed'])
        self.assertEqual(MARCH.current(e,q),order)
        e.end_of_turn(rider);e.start_of_turn(q,initiative_count=17)
        with patch.object(Engine,'d20',return_value=20):
            result=e.use_pass_move(q,'move/니트로차지',(4,0),event_id='transfer-march-pass',range_source=MARCH.FEATURE,
                object_adjudications={},source='gm/march-object-hits',reason='actual new holder mounted Pass')
        self.assertEqual(result['conversion']['order_id'],order['id'])
        self.assertEqual(result['conversion']['mounted_riders'],[rider.entity_id])
        e.end_of_turn(q);e.end_round();self.assertFalse(MARCH.live(q))

    def test_gfw_moves_live_evasion_and_fixed_condition_without_reissuing_paid_ally_set(self):
        import go_fight_win as GO,cheerleader as CHEER
        f=self.helper('test_book_go_fight_win','GoFightWinTests');f.setup(combat=False)
        e,t=f.e,f.a
        p=Combatant(e.r,build_pokemon(e.r,'이브이',20,name='actual GFW recipient',moves=[],abilities=[],
            extra={'trainer_id':t.entity_id,'trainer':t.name}))
        e.gm.add_combatant(p,pos=(1,0),side=t.side,reason='actual owned present ally')
        e.gm.observe_sensory_environment(t,p,paths={'auditory':True},present=True,reason='actual GFW communication')
        q=self.reserve(e,t,p);f.open();e.start_of_turn(t,initiative_count=20)
        use=deepcopy(f.use('evasion'));payment=deepcopy(t.spec[GO.KEY])
        condition=CHEER.live(p)[0]['id'];deadline=next(row['count_deadline'] for row in TIME.records(p) if row.get('go_fight_win_use')==use['id'])
        baseline=q.evasion('물리');self.baton(e,t,p,q)
        self.assertEqual(t.spec[GO.KEY],payment)
        self.assertEqual([row['id'] for row in CHEER.live(q)],[condition]);self.assertFalse(CHEER.live(p))
        moved=next(row for row in TIME.records(q) if row.get('go_fight_win_use')==use['id'])
        self.assertEqual(moved['count_deadline'],deadline);self.assertEqual(q.evasion('물리'),baseline+2)
        self.assertEqual(set(use['targets']),set(payment[-1]['targets']));self.assertNotIn(q.entity_id,use['targets'])
        e.end_of_turn(p);e.end_round();e.start_round(e.everyone);e.at_initiative_count(20)
        self.assertEqual(q.evasion('물리'),baseline)
        self.assertEqual([row['id'] for row in CHEER.live(q)],[condition])
        self.assertTrue(e.validate_state()['valid'])

    def test_all_five_class_stratagems_move_same_source_and_reach_native_accuracy_damage_consumers(self):
        f=self.helper('test_category2_class_passive_combat_bulk','ClassPassiveCombatBulkTests',self.all)
        for source in sorted(CLASS.STRATAGEMS):
            with self.subTest(source=source):
                e,t,p,foe=f.fixture(feats=[source]);q=self.reserve(e,t,p)
                e.gm.observe_sensory_environment(t,p,paths={'auditory':True},present=True,reason='actual Stratagem order')
                e.start_round(e.everyone);e.start_of_turn(t,initiative_count=20)
                self.assertEqual(e.activate_class_passive(t,p,source),(1,0))
                before=deepcopy(CLASS._active(e,p,source)[1]);bindings=deepcopy(dict(t.ap_account.identified_bindings()))
                self.baton(e,t,p,q);self.same_sustain(e,t,p,q,source,before,bindings)
                move=e.r.move('move/화염방사' if source==CLASS.TRICK_SHOT else 'move/몸통박치기')
                modifier=CLASS.damage_roll_modifier(e,q,foe,move,1.0)
                if source==CLASS.RECKLESS:self.assertEqual(modifier,8)
                elif source==CLASS.CAPRICIOUS:self.assertEqual(modifier,-5)
                elif source==CLASS.TRICK_SHOT:self.assertTrue(e.accuracy_check(q,foe,move,fixed_roll=17)[2])
                elif source==CLASS.ADAPTIVE:
                    bug=e.r.move('move/벌레의저항')
                    self.assertEqual(CLASS.damage_roll_modifier(e,q,foe,bug,1.0),CLASS.type_link_rank(e,t,'벌레'))
                elif source==CLASS.PERFECT:self.assertEqual(CLASS.perfect_damage(e,q,move,'2d6+3',1),(15,[6,6]))
                self.assertTrue(CODEC.load_engine(e.r,json.loads(json.dumps(CODEC.dump_engine(e)))).validate_state()['valid'])
                e.end_of_turn(p);e.end_round();e.start_round(e.everyone);e.start_of_turn(t,initiative_count=20)
                self.assertEqual(e.release_class_passive(t,q,source),(1,0))
                self.assertNotIn(before['instance'],t.ap_account.identified_bindings())
                assert_rejected_unchanged(e,lambda:e.release_class_passive(t,q,source),reason_pattern='actual owner')

    def test_all_five_stat_branches_keep_acquisition_binding_and_receiver_stage_consumers(self):
        import stat_ace as STAT,combat_precision_features as PRECISION,condition_recovery as RECOVERY
        for branch in ('atk','def','spa','spd','spe'):
            with self.subTest(branch=branch):
                f=self.helper('test_book_stat_ace_full','StatAceTests');f.setUp();f.family(branch,stratagem=True)
                e,t,p,q=f.e,f.a,f.p,f.q;e.gm.recall(q,reason='actual matching Stat reserve')
                f.activate(branch);before=deepcopy(CLASS._active(e,p,STAT.STRATAGEM)[1]);bound=deepcopy(dict(t.ap_account.identified_bindings()))
                e.change_stage(p,branch,3);self.baton(e,t,p,q)
                self.same_sustain(e,t,p,q,STAT.STRATAGEM,before,bound)
                if branch=='atk':self.assertTrue(e.accuracy_check(q,f.b,e.r.move('move/몸통박치기'),fixed_roll=17)[2])
                elif branch=='spa':self.assertEqual(PRECISION.effect_natural(e,q,e.r.move('move/물대포'),10),13)
                elif branch in ('def','spd'):
                    condition='마비' if branch=='def' else '혼란'
                    self.assertEqual(RECOVERY.saving_check(e,q,condition,16,fixed=10)['dc'],10)
                else:self.assertEqual(STAT.stratagem_bonus(e,q,'movement'),3)
                self.assertTrue(e.validate_state()['valid'])

    def test_all_eighteen_type_stratagems_keep_original_acquisition_and_actual_move_completion_hooks(self):
        import type_ace as TYPE,effects as EFFECTS
        moves={'벌레':'move/벌레의저항','악':'move/물기','드래곤':'move/용의숨결','전기':'move/전기쇼크',
            '페어리':'move/애교부리기','격투':'move/태권당수','불꽃':'move/불꽃세례','비행':'move/바람일으키기',
            '고스트':'move/핥기','풀':'move/잎날가르기','땅':'move/진흙뿌리기','얼음':'move/얼음뭉치','노말':'move/몸통박치기',
            '독':'move/독침','에스퍼':'move/염동력','바위':'move/돌떨구기','강철':'move/메탈클로','물':'move/물대포'}
        weather={'Sunlight Within':'sunny','Desert Heart':'sandstorm','Polar Vortex':'hail','Fishbowl Technique':'rain'}
        self.assertEqual(len(TYPE.STRATAGEMS),18)
        for source in sorted(TYPE.STRATAGEMS):
            with self.subTest(source=source):
                f=self.helper('test_book_type_ace_actions','TypeAceActionsTests');f.setUp()
                branch=TYPE.DEFINITIONS[source]['branch'];chain=[];current=source
                while current!=TYPE.CLASS:
                    chain.insert(0,current);current=TYPE.DEFINITIONS[current].get('parent',TYPE.CLASS)
                f.branch(branch,*chain);e,t,p,q=f.e,f.t,f.p,f.q
                e.gm.recall(q,reason='actual Type reserve with its own initial class-compatible body')
                f.communication();f.combat(t);TYPE.activate(e,t,p,source)
                before=deepcopy(CLASS._active(e,p,source)[1]);bindings=deepcopy(dict(t.ap_account.identified_bindings()))
                stages=dict(p.stages);self.baton(e,t,p,q)
                self.same_sustain(e,t,p,q,source,before,bindings)
                name=TYPE.DEFINITIONS[source]['english']
                if name in weather:self.assertEqual(EFFECTS.effective_weather(e,q),weather[name]);self.assertIsNone(EFFECTS.effective_weather(e,p))
                if name=='Iron Grit':
                    self.assertEqual(q.stages['def'],stages['def']);e.change_stage(q,'def',-1)
                    self.assertEqual(q.stages['def'],stages['def'])
                if name=='Celerity':self.assertEqual(TYPE.initiative(e,q),TYPE.rank(e,t,'비행'))
                e.end_of_turn(p);e.end_round();e.start_round(e.everyone);e.start_of_turn(q,initiative_count=30)
                e.gm.set_position(f.b,(q.pos[0]+1,q.pos[1]),reason='actual adjacent native Move recipient')
                e.gm.set_types(f.b,['노말'],reason='actual neutral recipient without implicit immunity')
                move=moves[branch]
                if branch=='고스트':e.gm.set_types(f.b,['물'],reason='actual nonimmune Ghost recipient')
                e.gm.set_move(q,move,reason='actual learned receiver Move')
                if name=='Sneak Attack':e.gm.add_condition(f.b,'넘어짐',reason='actual printed surprised target condition')
                if name=='Debilitate':e.gm.add_condition(f.b,'독',reason='actual poisoned recipient')
                if name=='Mindbreak':e.gm.add_condition(q,'억압',reason='actual counted Psychic affliction')
                if name=='Overload':f.answer('type_ace_overload',True)
                hp=q.hp
                with patch.object(Engine,'d20',return_value=19):e.use_move_on(q,f.b,move,e.everyone,set_damage=True)
                completion=next(row for row in reversed(list(e._move_completions.values())) if row['actor'] is q)
                self.assertEqual(completion['phase'],'complete');self.assertTrue(completion.get('type_ace_completed'))
                if name=='Close Quarters Mastery':self.assertIs(TYPE.marked(e,f.b),q)
                if name=='Debilitate':self.assertTrue(any(row.get('source')==source and row.get('accuracy_modifier')==-2 for row in TIME.records(f.b)))
                if name=='Fey Trance':self.assertIn('헤롱헤롱',f.b.conditions)
                if name=='Overload':self.assertEqual(hp-q.hp,e.tick(q))
                if name=='Haunting Curse':self.assertEqual(CLASS._active(e,q,source)[1]['tokens'],1)
                if name=='Mindbreak':self.assertEqual(TYPE.effect_range(e,q,e.r.move(move)),1)
                if name=='Iterative Evolution':self.assertEqual(CLASS.damage_roll_modifier(e,q,f.b,e.r.move(move),1.0),TYPE.rank(e,t,'벌레'))
                if name=='Plainly Perfect':self.assertEqual(CLASS.perfect_damage(e,q,e.r.move(move),'2d6+3',1),(15,[6,6]))
                if name=='Incandescence':
                    import pokemon_move_edges as EDGES
                    native=e.r.move(move);stat='atk' if native['class']=='물리' else 'spa'
                    other='spa' if stat=='atk' else 'atk'
                    self.assertEqual(EDGES.mixed_damage_stat(e,q,native,q.staged(stat)),q.staged(stat)+q.staged(other)//2)
                if name=='Unconquerable':
                    e.gm.add_condition(q,'화상',reason='actual new holder end-turn affliction')
                    f.answer('type_ace_choice',True);f.answer('type_ace_unconquerable_cure','화상')
                    with patch.object(Engine,'d20',return_value=17):e.end_of_turn(q)
                    self.assertNotIn('화상',q.conditions)
                if name=='Tough as Schist':
                    import hazard_state as HAZARDS
                    e.end_of_turn(q);e.end_round();e.start_round(e.everyone);e.start_of_turn(q,initiative_count=30)
                    e.gm.set_move(q,'move/스텔스록',reason='actual allied rock producer')
                    e.use_move_on(q,q,'move/스텔스록',e.everyone,aim=[(4,4),(4,5),(5,4),(5,5)])
                    rocks=[rock for envelope in HAZARDS.ensure(e).values() for rock in envelope['instances']
                        if rock['kind']=='stealth_rock' and rock['owner_side']==q.side]
                    self.assertTrue(rocks);selected=rocks[0]['id'];f.answer('type_ace_tough_rock',selected)
                    e.end_of_turn(q);e.start_of_turn(f.b,initiative_count=20)
                    e.gm.set_move(f.b,'move/물대포',reason='actual super-effective incoming consumer')
                    with patch.object(Engine,'d20',return_value=19):e.use_move_on(f.b,q,'move/물대포',e.everyone,set_damage=True)
                    self.assertFalse(any(rock['id']==selected for envelope in HAZARDS.ensure(e).values() for rock in envelope['instances']))
                    self.assertTrue(any(row.get('source')==source and row.get('ace_dr')==TYPE.rank(e,t,'바위') for row in TIME.records(q)))
                self.assertEqual(t.ap_account.identified_bindings(),bindings)
                self.assertTrue(e.validate_state()['valid'])


if __name__=='__main__':unittest.main()
