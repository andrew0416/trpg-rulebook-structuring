"""Category-2 Blessing state: shared source identity and actual native consumers."""
from copy import deepcopy
from unittest.mock import patch
import json,unittest
import test_category2_team_blessings as fixture
import blessing_effects as B,effect_instances as E,state_codec as CODEC


class CoreBlessingStateTests(unittest.TestCase):
    setUpClass=classmethod(fixture.TeamBlessingTests.setUpClass.__func__)
    known=fixture.TeamBlessingTests.known
    add=fixture.TeamBlessingTests.add
    snap=fixture.TeamBlessingTests.snap
    restored=fixture.TeamBlessingTests.restored
    valid=fixture.TeamBlessingTests.valid
    begin=fixture.TeamBlessingTests.begin
    answer=fixture.TeamBlessingTests.answer
    attack=fixture.TeamBlessingTests.attack

    def setUp(self):fixture.TeamBlessingTests.setUp(self)

    def cast(self,name,actor=None):
        actor=actor or self.a;self.known(actor,name);self.begin(actor)
        with patch.object(self.e,'d20',return_value=18):self.e.use_move(actor,actor,'move/'+name)
        return next(r for r in B.live(actor) if r['source']=='move/'+name)

    def ability(self,name,actor=None):
        actor=actor or self.p
        self.e.gm.set_ability(actor,name,reason='actual acquired sourced Blessing Ability')
        self.assertFalse(B.live(actor),'registration must not activate a manual Blessing')
        self.begin(actor)
        result=self.e.activate_ability(actor,name,actor)
        record=next(r for r in B.live(actor) if r['id']==result['effect_id'])
        self.assertEqual(actor.budget['swift'],0)
        self.assertEqual(actor.spec['frequency_state']['activations']['ability:'+name]['used'],1)
        return record

    def test_representative_ability_uses_one_native_team_pool_for_trainer_and_pokemon(self):
        r=self.ability('재앙의그릇');self.assertEqual(r['source'],'ability/재앙의그릇')
        self.assertEqual(r['effect'],B.definition(self.r,'move/빛의장막')['payload'])
        self.assertIs(B.beneficiaries(self.e,self.a)[0][1],r)
        self.answer(True);self.attack(self.a);self.assertEqual(B.remaining(r),1)
        self.attack(self.p);self.assertFalse(B.live(self.p))
        ended=self.p.spec[B.HISTORY][-1]
        self.assertEqual(ended['id'],r['id']);self.assertEqual(B.remaining(ended),0)
        self.assertEqual({x['target_id'] for x in ended['decisions']},{self.a.entity_id,self.p.entity_id})
        self.assertEqual(ended[E.KEY]['state'],'consumed');self.valid()

    def test_remaining_three_ability_sources_keep_printed_shared_capacity_and_direction(self):
        for name,move,direction in [('재앙의목간','몸통박치기','defense'),('재앙의검','몸통박치기','offense'),('재앙의구슬','물대포','offense')]:
            with self.subTest(source=name):
                self.setUp();r=self.ability(name);self.answer(True)
                if direction=='defense':self.attack(self.a,move)
                else:
                    self.known(self.a,move);self.begin(self.a)
                    with patch.object(self.e,'d20',return_value=18),patch.object(self.e.rulings,'decide',wraps=self.e.rulings.decide) as choice:
                        self.e.use_move(self.a,self.other,'move/'+move,set_damage=True)
                    prompt=next(args.args[0] for args in choice.call_args_list if args.args[0]['type']=='team_blessing')
                    self.assertEqual((prompt['actor'],prompt['actor_id']),(self.a.name,self.a.entity_id))
                self.assertEqual(B.remaining(r),1)
                obs=r['decisions'][0]
                self.assertEqual(obs['multiplier_after'],0.5 if direction=='defense' else 1.5)
                self.assertEqual(r[E.KEY]['capacity']['limit'],2);self.valid()

    def test_critical_and_stage_consumers_read_the_actual_allied_pool(self):
        guard=self.cast('주술');self.answer(True)
        self.other.blessings.append({'name':'legacy Dragon Cheer','left':1,'on':'successful attack','effect':'convert hit to crit vs one target','src':{}})
        self.valid()
        with patch.object(self.e,'roll_damage',wraps=self.e.roll_damage) as roll:
            self.attack(self.p,roll=20)
        self.assertFalse(roll.call_args.args[3])
        self.assertEqual(self.other.blessings[0]['left'],1)
        self.assertEqual(B.remaining(guard),2)
        self.assertEqual(guard['decisions'][0]['actor_id'],self.p.entity_id)
        self.assertEqual(guard['decisions'][0]['kind'],'critical_guard')
        mist=self.cast('흰안개');self.e._inflictor=self.other
        self.e.change_stage(self.p,'atk',-1);self.e.change_stage(self.a,'def',-1)
        self.assertEqual((self.p.stages['atk'],self.a.stages['def']),(0,0))
        self.assertEqual(B.remaining(mist),1)
        self.e._inflictor=self.a;self.e.change_stage(self.a,'spa',-1)
        self.assertEqual(self.a.stages['spa'],0);self.assertFalse(any(r['id']==mist['id'] for r in B.live(self.a)))
        self.e._inflictor=None;self.valid()

    def test_dragon_cheer_uses_one_pool_and_records_its_source_exception(self):
        r=self.cast('드래곤옐');self.answer(True);self.known(self.p,'몸통박치기')
        self.e.gm.set_types(self.p,['드래곤'],reason='actual Dragon beneficiary')
        for expected in (2,1):
            self.begin(self.p)
            with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.p,self.other,'move/몸통박치기',set_damage=True)
            self.assertEqual(B.remaining(r),expected)
        self.assertEqual([x['charged'] for x in r['decisions']],[False,True])
        self.assertEqual(r['decisions'][0]['facts']['actor_types'],['드래곤']);self.valid()

    def test_new_payload_state_survives_creator_exit_and_restores_one_shared_scope(self):
        r=self.cast('신비의부적',self.p);uid=r['id']
        self.assertEqual(r['effect'],{'kind':'team_status_guard','duration':'next_turn','procedure':'status_effect_ignore'})
        self.e.end_of_turn(self.p);self.e.gm.recall(self.p,reason='actual creator switch')
        self.e.gm.faint(self.p,reason='actual creator faint');self.e.end_encounter();self.e.end_scene()
        self.assertIs(B.beneficiaries(self.e,self.a)[0][1],r)
        self.assertEqual(B.remaining(r),3)
        restored=self.restored();actors={c.entity_id:c for c in restored.gm.everyone}
        owner=actors[self.p.entity_id];ally=actors[self.a.entity_id]
        self.assertEqual(B.beneficiaries(restored,ally)[0][1]['id'],uid)
        self.assertEqual(B.remaining(B.live(owner)[0]),3)
        self.assertTrue(restored.validate_state()['valid'])

    def test_move_exchange_and_removal_use_the_same_ability_and_move_instances(self):
        ability=self.ability('재앙의그릇');status=self.cast('신비의부적')
        ids={ability['id'],status['id']};self.begin(self.other)
        with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.other,self.other,'move/코트체인지')
        self.assertEqual({r['id'] for _,r in B.beneficiaries(self.e,self.other)},ids)
        self.assertFalse(B.beneficiaries(self.e,self.a))
        self.known(self.a,'안개제거');self.begin(self.a)
        with patch.object(self.e,'d20',return_value=18):self.e.use_move(self.a,self.a,'move/안개제거')
        self.assertFalse(B.live(self.p));self.assertFalse(B.live(self.a))
        for owner,record in ((self.p,ability),(self.a,status)):
            closed=next(x for x in owner.spec[B.HISTORY] if x['id']==record['id'])
            self.assertEqual(closed[E.KEY]['end_event']['source'],'move/안개제거')
            self.assertEqual(closed['scope_history'][-1]['side'],'wild')
        self.valid()
        self.setUp();ability=self.ability('재앙의그릇');status=self.cast('신비의부적')
        from ruleset import UnresolvedRuleSelection
        before=self.snap()
        with self.assertRaises(UnresolvedRuleSelection):
            self.e.gm.set_ability(self.other,'배리어프리',reason='unresolved same-name ability admission')
        self.assertEqual(self.snap(),before)
        import effects as FX
        clear=next(x for x in self.r.ability_effects['배리어프리'] if x['type']=='clear_field')
        result=FX.run_effects(self.e,self.other,self.other,[clear],{'hit':True,'engine':self.e},'ability/배리어프리')
        self.assertEqual(result[1],0)
        self.assertFalse(B.live(self.p));self.assertFalse(B.live(self.a))
        for owner,record in ((self.p,ability),(self.a,status)):
            closed=next(x for x in owner.spec[B.HISTORY] if x['id']==record['id'])
            self.assertEqual(closed[E.KEY]['end_event']['source'],'ability/배리어프리')
        self.valid()

    def test_reaction_blocker_and_manual_refusal_preserve_shared_state(self):
        r=self.ability('재앙의목간');self.answer(True)
        from ruleset import UnresolvedRuleSelection
        before=self.snap()
        with self.assertRaises(UnresolvedRuleSelection):
            self.e.gm.set_ability(self.other,'보이지않는주먹',reason='unresolved same-name ability admission')
        self.assertEqual(self.snap(),before)
        self.known(self.other,'레이징불')
        self.begin(self.other)
        self.e.resolve_attack_damage(self.other,self.a,self.r.move('move/레이징불'),set_damage=True)
        self.assertEqual(B.remaining(r),2);self.assertFalse(r['decisions'])
        self.attack(self.a,'몸통박치기');self.assertEqual(B.remaining(r),1)
        self.begin(self.p);before=self.snap()
        with self.assertRaises(ValueError):self.e.activate_ability(self.p,'재앙의목간',self.p)
        self.assertEqual(self.snap(),before);self.valid()

    def test_new_record_capacity_source_scope_and_generic_receipt_cannot_be_forged(self):
        r=self.cast('흰안개');self.answer(True);self.e._inflictor=self.other
        self.e.change_stage(self.p,'atk',-1);self.e._inflictor=None
        good=deepcopy(r)
        for field in ('capacity','source','scope','receipt'):
            with self.subTest(field=field):
                r.clear();r.update(deepcopy(good))
                if field=='capacity':r[E.KEY]['capacity']['limit']=4
                elif field=='source':r['source']='move/주술'
                elif field=='scope':r['scope_history'][0]['side']='other'
                else:r['decisions'][0]['sequence']+=1
                with self.assertRaises(CODEC.StateCodecError):CODEC.dump_engine(self.e)
        r.clear();r.update(good);self.valid()

    def test_effectiveness_previews_preserve_known_thresholds_and_hold_only_pending_crossing(self):
        import effects_ext as EXT,class_passive_combat as CLASS
        r=self.ability('재앙의검');self.known(self.a,'깨트리기')
        self.e.gm.set_ability(self.other,'불가사의부적',reason='actual pre-hit consumer')
        move=self.r.move('move/깨트리기');mm=self.r.move_mech(move['id'])[0]
        for types,expected in [(['노말'],1.5),(['에스퍼'],0.5),(['고스트'],0)]:
            with self.subTest(types=types):
                self.e.gm.set_types(self.other,types,reason='actual threshold boundary')
                before=self.snap()
                self.assertEqual(CLASS._effectiveness_preview(self.e,self.a,self.other,move,mm),expected)
                self.assertEqual(EXT.blocks_hit(self.e,self.a,self.other,move,mm),None if expected>1 else 'ability/불가사의부적')
                self.assertEqual(self.snap(),before)
        self.e.gm.set_types(self.other,['물'],reason='actual optional crossing from neutral')
        self.begin(self.a);before=self.snap()
        with self.assertRaisesRegex(ValueError,'optional shared Blessing'):
            self.e.use_move(self.a,self.other,move['id'],set_damage=True)
        self.assertEqual(self.snap(),before)
        with self.assertRaisesRegex(ValueError,'optional shared Blessing'):
            CLASS._effectiveness_preview(self.e,self.a,self.other,move,mm)
        blocked=self.r.move('move/레이징불');blocked_mm=self.r.move_mech(blocked['id'])[0]
        self.assertEqual(CLASS._effectiveness_preview(self.e,self.a,self.other,blocked,blocked_mm),1)
        self.assertEqual(EXT.blocks_hit(self.e,self.a,self.other,blocked,blocked_mm),'ability/불가사의부적')
        self.assertEqual(B.remaining(r),2);self.assertFalse(r['decisions']);self.valid()


if __name__=='__main__':unittest.main()
