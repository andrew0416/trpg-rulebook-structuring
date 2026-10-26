"""Selected Flame Burst splash after a real crafted-weapon primary hit."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

STAGE=Path(__file__).resolve().parents[1]
ROOT=STAGE if (STAGE/'data/core-rules.json').exists() else Path(os.environ.get(
    'PTK_CANONICAL_ROOT',r'D:/trpg-rulebook-structuring/work/public-actions-20261023/repository'))
sys.path[:0]=[str(STAGE/'engine'),str(ROOT/'engine'),str(ROOT/'tools')]
import test_fantasy_weapon_revision as WEAPON
from builder import build_trainer
from engine import Combatant,Engine
import attack_damage_history as HISTORY
import body_state as BODY
import effects as FX
import event_trace as TRACE
from native_scenario_fixture import assert_rejected_unchanged

MOVE='move/불꽃튀기기'
EFFECT={'type':'hp_loss','value':5,'target':'cardinally adjacent to target'}


class FlameBurstNativeConsumerTests(unittest.TestCase):
    def scene(self):
        fixture=WEAPON.FantasyWeaponRevisionTests()
        e,a,targets=fixture.fixture(count=5)
        weapon=fixture.equip(e,a,'crafted_item/나인플레임의-스태프')
        TRACE.enable(e,False)
        for actor,pos in zip([a,*targets],[(5,5),(6,5),(8,5),(8,6),(11,5),(6,6)]):
            e.gm.set_position(actor,pos,reason='actual Flame Burst spatial observation')
        primary,east,diagonal,remote,south=targets
        BODY.observe(e,primary,[(0,0),(1,0)],reason='actual two-cell primary body')
        trainer=Combatant(e.r,build_trainer(e.r,'adjacent splash trainer',20,
            dict.fromkeys(('hp','atk','def','spa','spd','spe'),30),moves=[],abilities=[]))
        e.gm.add_combatant(trainer,side='bystander',pos=(6,4),reason='actual adjacent trainer')
        BODY.observe(e,trainer,[(0,0)],reason='actual complete trainer body')
        e.gm.set_temp_hp(south,3,reason='actual temporary HP before ordinary splash loss',duration_seconds=300)
        fixture.begin(e,a)
        return e,a,primary,east,diagonal,remote,south,trainer,weapon

    def test_actual_crafted_hit_splashes_cardinal_trainers_pokemon_and_adjacent_user_once(self):
        e,a,t,east,diagonal,remote,south,trainer,weapon=self.scene()
        e,a,t,east,diagonal,remote,south,trainer=WEAPON.FantasyWeaponRevisionTests().restore(
            e,a,t,east,diagonal,remote,south,trainer)
        others=(a,east,diagonal,remote,south,trainer)
        before={c.entity_id:(c.hp,c.temp_hp,deepcopy(HISTORY.records(c))) for c in others}
        target_hp=t.hp
        with patch.object(Engine,'d20',return_value=17):
            damage=e.use_move_on(a,t,MOVE,e.everyone,weapon_id=weapon,set_damage=True)
        self.assertGreater(damage,0)
        self.assertEqual(t.hp,target_hp-damage)  # The primary is not its own adjacent recipient.
        self.assertEqual(HISTORY.amount(HISTORY.last_damage(t)),damage)
        for c in (a,east,trainer):
            self.assertEqual((c.hp,c.temp_hp),(before[c.entity_id][0]-5,0))
        self.assertEqual((south.hp,south.temp_hp),(before[south.entity_id][0]-2,0))
        for c in (diagonal,remote):
            self.assertEqual((c.hp,c.temp_hp),before[c.entity_id][:2])
        for c in others:self.assertEqual(HISTORY.records(c),before[c.entity_id][2])
        self.assertEqual((a.move_uses[MOVE],a.budget['standard']),(1,0))
        rows=[row for row in e._effect_dispatch_receipts.values()
              if row['source_id']==MOVE and row['effect'].get('type')=='hp_loss']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'completed')
        self.assertNotIn('attack_damage',rows[0])
        self.assertNotIn('attack_hp_loss',rows[0])
        self.assertEqual(e.effect_stats['held'],0)
        self.assertTrue(e.validate_state()['valid'])

    def test_primary_and_adjacent_user_faint_do_not_cancel_the_remaining_actual_splash(self):
        e,a,t,east,diagonal,remote,south,trainer,weapon=self.scene()
        e.gm.set_hp(t,1,reason='actual vulnerable primary before the hit')
        e.gm.set_hp(a,4,reason='actual vulnerable adjacent user before splash')
        hp={c.entity_id:c.hp for c in (east,diagonal,remote,south,trainer)}
        with patch.object(Engine,'d20',return_value=17):
            self.assertGreater(e.use_move_on(a,t,MOVE,e.everyone,weapon_id=weapon,set_damage=True),0)
        self.assertTrue(t.fainted);self.assertTrue(a.fainted)
        for c in (east,trainer):self.assertEqual(c.hp,hp[c.entity_id]-5)
        self.assertEqual((south.hp,south.temp_hp),(hp[south.entity_id]-2,0))
        for c in (diagonal,remote):self.assertEqual(c.hp,hp[c.entity_id])
        self.assertEqual((a.move_uses[MOVE],a.budget['standard']),(1,0))
        self.assertEqual(e.effect_stats['held'],0)

    def test_actual_primary_miss_spends_one_move_without_any_splash(self):
        e,a,t,*tail=self.scene();weapon=tail[-1]
        before=[(c.hp,c.temp_hp,deepcopy(HISTORY.records(c))) for c in e.everyone]
        with patch.object(Engine,'d20',return_value=1):
            self.assertEqual(e.use_move_on(a,t,MOVE,e.everyone,weapon_id=weapon,set_damage=True),0)
        self.assertEqual([(c.hp,c.temp_hp,HISTORY.records(c)) for c in e.everyone],before)
        self.assertEqual((a.move_uses[MOVE],a.budget['standard']),(1,0))
        self.assertFalse(any(row['source_id']==MOVE and row['status']=='completed'
            and row['effect'].get('type')=='hp_loss' for row in getattr(e,'_effect_dispatch_receipts',{}).values()))

    def test_unbound_hit_label_cannot_forge_the_native_primary_producer(self):
        e,a,t,*_=self.scene()
        before=deepcopy(([(c.hp,c.temp_hp,HISTORY.records(c)) for c in e.everyone],a.budget,a.move_uses,e.rng.getstate()))
        result=FX.run_effects(e,a,t,[EFFECT],
            dict(hit=True,nat=17,move=e.r.move(MOVE),engine=e),MOVE)
        self.assertEqual(tuple(result),(0,1))
        self.assertEqual(result.outcomes[0].status,'execution_failed')
        self.assertEqual(([(c.hp,c.temp_hp,HISTORY.records(c)) for c in e.everyone],a.budget,a.move_uses,e.rng.getstate()),before)

    def test_changed_selected_payload_or_source_is_rejected_before_any_native_payment(self):
        e,a,t,*tail=self.scene();weapon=tail[-1]
        with patch.dict(e.r.moves_llm['불꽃튀기기'],effects=[dict(EFFECT,value=6)]):
            assert_rejected_unchanged(e,lambda:e.use_move_on(a,t,MOVE,e.everyone,weapon_id=weapon,set_damage=True),
                reason_pattern='exact selected cardinal HP-loss source')
        origin=e.r.selection.units[MOVE]['source']
        with patch.dict(origin,record_span=[268,268]):
            assert_rejected_unchanged(e,lambda:FX.preflight_effects(e,a,t,[EFFECT],MOVE),
                reason_pattern='exact selected cardinal HP-loss source')
        assert_rejected_unchanged(e,lambda:FX.preflight_effects(e,a,t,[EFFECT],'move/몸통박치기'),
            reason_pattern='explicit native target-set binding')

    def test_unknown_remote_body_and_mapless_contact_do_not_silently_narrow_the_splash(self):
        e,a,t,east,diagonal,remote,south,trainer,weapon=self.scene()
        remote.spec.pop('footprint')
        remote.spec['size']=None
        self.assertFalse(BODY.projection(remote)['geometry_complete'])
        assert_rejected_unchanged(e,lambda:e.use_move_on(a,t,MOVE,e.everyone,weapon_id=weapon,set_damage=True),
            reason_pattern='full observed body geometry')
        e,a,t,*_=self.scene();e.grid=None
        assert_rejected_unchanged(e,lambda:FX.preflight_effects(e,a,t,[EFFECT],MOVE),
            reason_pattern='mapped cardinal body geometry')


if __name__=='__main__':unittest.main()
