"""Deterministic integration coverage: build -> equipment -> combat -> recovery -> growth.
Run: python -X utf8 -B -I engine/test_playthrough.py <root>
The trainer fixture's feat prerequisites are GM-approved; this is not a character-legality checker.
The trainer has the Medic Training edge, so a healed Pokemon keeps its next standard/swift action (ch09 아이템 사용).
Without that edge the engine now strips the recipient's next standard and swift action (source audit A03/A07).
"""
import copy
import io
import json
import sys
import unittest
from pathlib import Path

AUDIT_NOTICE = "시나리오 전제: 트레이너 민은 메딕 훈련 엣지를 가져 상처약을 받은 포켓몬이 행동을 잃지 않는다(ch09 아이템 사용). 실행 정확성 감사 39/39 통과 상태에서 재생성."

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from engine import Rules, Engine, Combatant
from builder import build_pokemon, build_trainer
import items as ITEMS
import effects as FX
import downtime as DT
import turn as TURN


class PlaythroughTests(unittest.TestCase):
    def setUp(self):
        self.rules = Rules(str(ROOT))
        self.engine = Engine(self.rules, 11)

    def pokemon(self, species="피그점프", level=19, **kw):
        return Combatant(self.rules, build_pokemon(self.rules, species, level, **kw))

    def trainer(self, **kw):
        return Combatant(self.rules, build_trainer(self.rules, "민", 10,
            {"hp":15,"atk":5,"def":10,"spa":5,"spd":10,"spe":5}, **kw))

    def test_pearl_species_and_move_type_restrictions(self):
        e = self.engine
        for species, expected in [("피그점프", 1), ("캐이시", 0)]:
            c = self.pokemon(species, item="분홍진주")
            e.register_abilities(c)
            self.assertEqual(c.stages["spa"], expected)
            self.assertEqual(c.spec["stats"], c.stats)
        c = self.pokemon("캐이시", item="분홍진주"); e.register_abilities(c)
        plain = self.pokemon("캐이시"); e.register_abilities(plain)
        target = self.pokemon("꼬부기")
        for mid, expected in [("move/환상빔",5),("move/몸통박치기",0)]:
            a=e.roll_damage(c,target,self.rules.move(mid),set_damage=True)
            b=e.roll_damage(plain,target,self.rules.move(mid),set_damage=True)
            self.assertEqual(a-b,expected)

    def test_unselected_items_prompt_without_global_bonus_or_crash(self):
        e = self.engine; target = self.pokemon("꼬부기")
        plain = self.pokemon("캐이시"); e.register_abilities(plain)
        for item in ("타입부스터", "스탯부스터"):
            c = self.pokemon("캐이시", item=item); start=len(e.gm_prompts)
            e.register_abilities(c)
            self.assertGreater(len(e.gm_prompts), start)
            self.assertEqual(c.stages, plain.stages)
            for mid in ("move/환상빔","move/몸통박치기"):
                self.assertEqual(e.roll_damage(c,target,self.rules.move(mid),set_damage=True),
                                 e.roll_damage(plain,target,self.rules.move(mid),set_damage=True))

    def test_unknown_species_gate_is_not_dropped_by_normalization(self):
        raw={"type":"stage_base_mod","stat":"spa","value":1,"if":"unrecognized condition"}
        self.assertEqual(ITEMS.normalize(raw)["if"],raw["if"])
        # A future draft with a new condition must prompt, not apply a passive unconditionally.
        self.rules.items_reviewed["item/분홍진주"]=[raw]
        c=self.pokemon(item="분홍진주");self.engine.register_abilities(c)
        self.assertEqual(c.stages["spa"],0)
        self.assertTrue(self.engine.gm_prompts)

    def test_inventory_and_action_rejections_are_atomic(self):
        e=self.engine; c=self.pokemon();c.hp-=30
        tr=self.trainer(items={"상처약":0});TURN.reset_budget(e,tr)
        original=(c.hp,copy.deepcopy(tr.budget),copy.deepcopy(tr.spec["items"]))
        for item in ("상처약","좋은상처약","item/상처약"):
            self.assertEqual(e.use_item(tr,item,c),(0,0))
            self.assertEqual((c.hp,tr.budget,tr.spec["items"]),original)
        tr.spec["items"]["상처약"]=1
        tr.budget["standard"]=0
        self.assertEqual(e.use_item(tr,"상처약",c),(0,0))
        self.assertEqual(tr.spec["items"]["상처약"],1)
        self.assertEqual(c.hp,original[0])
        TURN.reset_budget(e,tr)
        e.use_item(tr,"item/상처약",c)
        self.assertEqual(tr.spec["items"]["상처약"],0)
        self.assertEqual(tr.budget["standard"],0)
        self.assertEqual(c.hp,original[0]+20)

    def test_growth_registers_new_ability_once_without_duplicate_equipment(self):
        e=self.engine;c=self.pokemon(item="분홍진주");e.register_abilities(c)
        before=dict(c.stats);old_stages=dict(c.stages)
        DT.gain_exp_combatant(e,c,"to next level")
        self.assertEqual(c.level,20)
        self.assertIn("두꺼운지방",c.abilities)
        self.assertEqual(c.abilities,c.spec["abilities"])
        self.assertEqual(c.stages,old_stages)
        self.assertEqual(sum(c.stats.values()),sum(before.values())+1)
        self.assertTrue(all(c.stats[k]>=v for k,v in before.items()))
        fat=[m for m in c.modifiers if m.get("_ability")=="두꺼운지방"]
        self.assertEqual(len(fat),1)
        DT.gain_exp_combatant(e,c,0)
        self.assertEqual([m for m in c.modifiers if m.get("_ability")=="두꺼운지방"],fat)
        attacker=self.pokemon("브케인",20)
        plain=Combatant(self.rules,copy.deepcopy(c.spec))
        move=self.rules.move("move/불꽃세례")
        self.assertLess(e.roll_damage(attacker,c,move,set_damage=True),
                        e.roll_damage(attacker,plain,move,set_damage=True))

    def test_gm_choice_applies_to_selected_pokemon_and_is_logged(self):
        e=self.engine;tr=self.trainer(extra={"feats":["과장된 동작"]});c=self.pokemon()
        e.everyone=[tr,c];e.register_abilities(tr)
        campaign_answers=copy.deepcopy(e.rulings.answers)
        e.rule_answer("자동 치명타가 아니다", {"note":"GM이 변화기 치명타를 확인, 임시 HP 선택",
            "effects":[{"type":"temp_hp","value":"tick","target":"target"}]}, "확인된 수동 발동")
        before=copy.deepcopy((tr.spec,c.spec,getattr(tr,'_action_history',[])))
        self.assertEqual(e.manual_feat(tr,"과장된 동작",c),(0,1))
        self.assertEqual((tr.spec,c.spec,getattr(tr,'_action_history',[])),before)
        self.assertFalse(e.gm_prompts)
        # Component-only GM choice/target/log oracle. This does not implement
        # the source-conditioned Static trigger or authorize a Free activation.
        record=next(x for x in tr.registry if x.get('type')=='feat_manual' and x.get('name')=='과장된 동작')
        FX.run_effects(e,tr,c,record['effects'],{'attacker':tr,'target':c,'hit':True,'engine':e},record['usage_key'])
        self.assertEqual(c.temp_hp,e.tick(c))
        self.assertEqual(tr.temp_hp,0)
        self.assertIn("answer",e.gm_prompts[-1])
        self.assertTrue(any("[GM 답]" in line for line in e.log_lines))
        e.end_scene()
        self.assertEqual(e.rulings.answers,campaign_answers)
        self.assertFalse(any(a["key"]=="자동 치명타가 아니다" for a in e.rulings.answers))

    def playthrough(self):
        e=self.engine; r=self.rules
        # GM-approved trainer loadout; acquisition prerequisites are outside this fixture.
        tr=self.trainer(items={"상처약":3},extra={"feats":["자각","과장된 동작"],"edges":["메딕 훈련"]})
        ally=self.pokemon(item="분홍진주",extra={"trainer":"민","side":"ally"})
        enemy=self.pokemon("캐터피",extra={"side":"enemy"})
        bystander=self.pokemon("캐이시",extra={"trainer":"다른 트레이너","side":"ally"})
        e.everyone=[tr,ally,enemy,bystander]
        for c in e.everyone:e.register_abilities(c)
        self.assertEqual((ally.save_mod,enemy.save_mod,bystander.save_mod),(2,0,0))
        self.assertEqual(ally.stages["spa"],1)
        initial_stats=dict(ally.stats); initial_hp=ally.hp
        steps=[]
        for round_no in range(1,7):
            e.start_round(e.everyone)
            # Enemy acts first in this scripted initiative order to exercise healing.
            e.start_of_turn(enemy)
            before=ally.hp
            dealt=e.use_move(enemy,ally,"move/몸통박치기",set_damage=True)
            self.assertEqual(enemy.budget["standard"],0)
            self.assertLessEqual(ally.hp,before)
            self.assertFalse(ally.fainted)
            e.end_of_turn(enemy)
            e.start_of_turn(tr)
            healed=0
            if ally.hp<=ally.max_hp-20 and tr.spec["items"]["상처약"]:
                before=ally.hp;e.use_item(tr,"상처약",ally);healed=ally.hp-before
                self.assertEqual(healed,min(20,ally.max_hp-before))
                self.assertEqual(tr.budget["standard"],0)
            e.end_of_turn(tr)
            e.start_of_turn(ally)
            self.assertEqual(ally.budget["standard"],1)      # 메딕 훈련: 회복을 받아도 기본 행동 유지
            before=enemy.hp
            damage=e.use_move(ally,enemy,"move/환상빔",set_damage=True)
            self.assertLessEqual(enemy.hp,before)
            self.assertEqual(ally.budget["standard"],0)
            after=enemy.hp;uses=dict(ally.move_uses)
            self.assertEqual(e.use_move(ally,enemy,"move/환상빔",set_damage=True),0)
            self.assertEqual((enemy.hp,ally.move_uses),(after,uses))
            e.end_of_turn(ally)
            steps.append({"round":round_no,"incoming":dealt,"healed":healed,"outgoing":damage,
                          "ally_hp":ally.hp,"enemy_hp":enemy.hp,"potions":tr.spec["items"]["상처약"]})
            if enemy.fainted:break
        self.assertTrue(enemy.fainted)
        self.assertGreater(sum(x["incoming"] for x in steps),0)
        self.assertGreater(sum(x["healed"] for x in steps),0)
        e.end_scene()
        recovery=DT.pokemon_center(e,ally)
        self.assertEqual(ally.hp,ally.max_hp)
        self.assertFalse(ally.conditions)
        award,detail=DT.award_exp(r,[enemy.level],players=1,significance=3)
        DT.gain_exp_combatant(e,ally,award)
        self.assertEqual(ally.level,20)
        self.assertEqual(ally.hp,ally.max_hp)
        self.assertIn("두꺼운지방",ally.abilities)
        self.assertEqual(sum(ally.stats.values())-sum(initial_stats.values()),1)
        self.assertEqual(ally.stages["spa"],1)
        restored=json.loads(json.dumps(ally.spec,ensure_ascii=False))
        self.assertEqual(restored["stat_history"][-1]["event"],"level_up")
        result={"audit_notice":AUDIT_NOTICE,"seed":11,"fixture":"GM-approved trainer feat prerequisites; scripted initiative; set damage",
                "initial_hp":initial_hp,"rounds":steps,"recovery":recovery,"experience":detail,
                "final":{"level":ally.level,"hp":ally.hp,"stats":ally.stats,"abilities":ally.abilities,
                         "potions":tr.spec["items"]["상처약"],"history":restored["stat_history"]}}
        return result,e.log_lines

    def test_complete_playthrough_is_reproducible(self):
        first,log=self.playthrough()
        self.setUp()
        second,log2=self.playthrough()
        self.assertEqual(first,second)
        self.assertEqual(log,log2)
        (ROOT/"output/playthrough.json").write_text(json.dumps(first,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (ROOT/"output/playthrough-log.txt").write_text(AUDIT_NOTICE+"\n\n"+"\n".join(log+first["recovery"])+"\n",encoding="utf-8")


if __name__ == "__main__":
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PlaythroughTests))
    text=stream.getvalue()
    (ROOT/"output/playthrough-tests.md").write_text("# Historical playthrough reproducibility tests\n\n> "+AUDIT_NOTICE+"\n\n```text\n"+text+"```\n",encoding="utf-8")
    print(text)
    sys.exit(0 if result.wasSuccessful() else 1)
