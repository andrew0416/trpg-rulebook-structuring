"""Source-oracle audit, deliberately separate from implementation regression tests.
Run: python -X utf8 -B -I tools/audit_execution_accuracy.py [root] [--ruleset core|all]
Exit 0: selected obligations pass; 1: rule/contract mismatch; 2: source drift or probe error.
A pass never certifies unexamined rules. Expectations are stored independently in data/.
"""
import argparse
import contextlib
import hashlib
import io
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--ruleset", choices=["core", "all"], default="core")
    args = ap.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "engine"))
    from engine import Rules, Engine, Combatant
    from builder import build_pokemon
    import effects as FX
    import items as ITEMS

    manifest_path = root / "data/execution-accuracy-oracles.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = []
    for case in manifest["cases"]:
        result = dict(case)
        engine = None
        try:
            for source in case["sources"]:
                lines = (root / source["file"]).read_text(encoding="utf-8").splitlines()
                excerpt = "\n".join(lines[source["start"]-1:source["end"]])
                if hashlib.sha256(excerpt.encode()).hexdigest() != source["excerpt_sha256"]:
                    raise ValueError("Source changed; re-review oracle: " + source["file"])
            with contextlib.redirect_stdout(io.StringIO()):
                rules = Rules(str(root), ruleset=args.ruleset)
                engine = Engine(rules, 11)
                def actor(name, kind="pokemon", **extra):
                    spec = dict(name=name, kind=kind, level=30,
                                stats=dict.fromkeys(["hp","atk","def","spa","spd","spe"],20),
                                types=[], abilities=[], moves=["move/몸통박치기"])
                    spec.update(extra)
                    return Combatant(rules, spec)
                def effects(a, t, payload):
                    done, held = FX.run_effects(engine,a,t,payload,
                        dict(engine=engine,attacker=a,target=t,hit=True,nat=20),"source-audit")
                    if held:
                        raise RuntimeError(f"Probe effects held: {done=}, {held=}")
                a = actor("사용자", "trainer")
                t = actor("대상")
                engine.everyone = [a,t]
                p = case["args"]
                mode = p.get("mode")
                if case["probe"] == "consumable":
                    item = "플러스파워" if mode == "x_next" else "상처약"
                    a.spec["items"] = {item:1}
                    if mode == "medic_next":
                        a.spec["edges"] = ["메딕 훈련"]
                        engine.register_abilities(a)
                    if mode.startswith("self_"):
                        t = a
                    t.hp = 50
                    engine.start_of_turn(a)
                    engine.use_item(a,item,t)
                    if mode == "heal": actual = t.hp
                    elif mode in ("self_budget", "user_budget"): actual = dict(a.budget)
                    else:
                        engine.start_of_turn(t)
                        actual = dict(t.budget)
                elif case["probe"] == "x_item":
                    if mode == "trainer": t = actor("대상 트레이너","trainer")
                    engine.everyone = [a,t]
                    a.spec["items"] = {"플러스파워":1}
                    engine.start_of_turn(a)
                    engine.use_item(a,"플러스파워",t)
                    if mode == "expiry": engine.end_scene()
                    actual = t.stages["atk"]
                elif case["probe"] == "hp":
                    t.injuries = p.get("injuries",0)
                    t.hp = p.get("hp",100)
                    if mode == "base": actual = t.base_max_hp
                    elif mode == "cap": actual = t.max_hp
                    elif mode == "tick": actual = engine.tick(t)
                    else:
                        if mode == "damage": engine.take_damage(t,p["amount"])
                        elif mode == "loss": engine.lose_hp(t,p["amount"])
                        elif mode == "heal": engine.heal(t,p["amount"])
                        elif mode == "recross":
                            t.hp=60
                            engine.lose_hp(t,10)
                            engine.heal(t,10)
                            engine.lose_hp(t,10)
                        else: raise ValueError(mode)
                        actual = [t.hp,t.injuries]
                elif case["probe"] == "ko":
                    a.hp = p["hp"]
                    engine.check_fainted(a)
                    engine.start_of_turn(a)
                    engine.use_move(a,t,"move/몸통박치기",set_damage=True)
                    actual = a.move_uses.get("move/몸통박치기",0)
                elif case["probe"] == "stage":
                    effects(a,t,[dict(type="stage_change",target="target",**p)])
                    actual = t.accuracy_stage if p["stat"]=="acc" else t.evasion_mod if p["stat"]=="eva" else t.stages[p["stat"]]
                elif case["probe"] == "stage_end":
                    effects(a,t,[dict(type="stage_change",target="target",stat=s,delta=2) for s in ["atk","acc","eva"]])
                    engine.end_scene()
                    actual = [t.stages["atk"],t.accuracy_stage,t.evasion_mod]
                elif case["probe"] == "held":
                    a = Combatant(rules,build_pokemon(rules,p["species"],19,item="분홍진주"))
                    t = actor("교환 대상")
                    engine.everyone = [a,t]
                    engine.register_abilities(a)
                    def bonus(who, mid="move/환상빔"):
                        return FX.passive_damage_mods(engine,who,t,rules.move(mid),dict(attacker=who,target=t,hit=True))[1]
                    if mode.startswith("duplicate"): ITEMS.register_item(engine,a)
                    if mode.startswith("drop"): effects(t,a,[dict(type="item_drop")])
                    if mode == "swap":
                        effects(a,t,[dict(type="swap_items")])
                        actual = [bonus(a),bonus(t)]
                    elif mode in ("stage","duplicate_stage","drop_stage"): actual = a.stages["spa"]
                    elif mode == "normal": actual = bonus(a,"move/몸통박치기")
                    else: actual = bonus(a)
                else:
                    raise ValueError("Unknown probe: " + case["probe"])
            result.update(actual=actual,status="pass" if actual==case["expected"] else "fail")
        except Exception as exc:
            result.update(actual=None,status="error",error=f"{type(exc).__name__}: {exc}")
        result["execution_log"] = engine.log_lines if engine else []
        results.append(result)

    counts = dict(Counter(row["status"] for row in results))
    hashes = {str(p.relative_to(root)).replace("\\","/"):digest(p)
              for folder,glob in [("engine","*.py"),("data","*.json"),("output/entities","*.json")]
              for p in sorted((root/folder).glob(glob))}
    report = dict(generated_at=datetime.now(timezone.utc).isoformat(),ruleset=args.ruleset,
        scope=manifest["scope"],fixture=manifest["fixture"],oracle_sha256=digest(manifest_path),
        runner_sha256=digest(Path(__file__)),input_hashes=hashes,counts=counts,
        unresolved_groups=sorted({x["group"] for x in results if x["status"]!="pass"}),
        unverified=manifest["unverified"],results=results)
    path=root/f"output/execution-accuracy-audit-{args.ruleset}.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(dict(report=str(path),counts=counts,unresolved_groups=report["unresolved_groups"]),ensure_ascii=False))
    for row in results:
        if row["status"]!="pass":
            print(f"{row['status'].upper()} {row['id']} {row['title']}: expected={row['expected']!r} actual={row['actual']!r}" + (" "+row["error"] if "error" in row else ""))
    return 2 if counts.get("error") else 1 if counts.get("fail") else 0


if __name__ == "__main__":
    raise SystemExit(main())
