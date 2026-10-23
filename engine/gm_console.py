"""
GM 콘솔: 파일럿 전투를 턴 단위로 멈추고 GM 이 끼어든다. 각 전투원의 턴 직전에 명령을 받는다.
  python -X utf8 -I engine/gm_console.py <root> [seed] [--ruleset=NAME] [--rulings] [--script=파일]
명령: next(n, 빈 줄) 다음 턴 / show 상태 / <상태 명령> (gm_state.command 문법: '아치 hp 30 -- 낙석') / rule formula tick max_hp/8 -- 이유 /
      rule mech combat/critical-hit default_range 18 / rule situational accuracy +2 마야 / snapshot 이름 / restore 이름 / quit
--script 는 한 줄에 하나씩 '턴번호: 명령' (예: '3: 아치 hp 10 -- 낙석'); 테스트와 재현용.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import scenario  # noqa: E402


def make_hook(engine, commands=None, interactive=False):
    """scenario 의 턴 훅. commands: {턴번호: [명령…]} (턴번호는 1부터 전투원 턴마다 +1)."""
    state = {"turn": 0}

    def hook(e, c, rnd):
        state["turn"] += 1
        gm = e.gm
        for line in (commands or {}).get(state["turn"], []):
            e.log(f"  [GM 명령 @턴 {state['turn']}] {line}", "gm/console")
            run_line(e, line)
        if not interactive:
            return
        print(f"\n--- 라운드 {rnd}, 턴 {state['turn']}: {c.name} 차례 ---")
        print(gm.show())
        while True:
            try:
                line = input("GM> ").strip()
            except EOFError:
                return
            if line in ("", "n", "next"):
                return
            if line in ("q", "quit"):
                raise SystemExit(0)
            print(run_line(e, line))
    return hook


def run_line(e, line):
    if line == "show":
        return e.gm.show()
    if line.startswith("rule "):
        reason = ""
        if "--" in line:
            line, reason = [x.strip() for x in line.split("--", 1)]
        t = line.split()
        kind = t[1]
        if kind == "formula":
            e.rule_formula(t[2], " ".join(t[3:]), reason)
        elif kind == "mech":
            v = t[4]
            v = int(v) if v.lstrip("-").isdigit() else float(v) if v.replace(".", "", 1).isdigit() else v
            e.rule_mech(t[2], t[3], v, reason, scope="scene")
        elif kind == "situational":
            e.rule_situational(t[2], int(t[3]), t[4] if len(t) > 4 else None, uses="scene", reason=reason)
        else:
            return f"모르는 rule 종류: {kind}"
        return "ok"
    try:
        return e.gm.command(line)
    except Exception as ex:
        return f"오류: {ex}"


def main(root, seed=5, ruleset=None, rulings=False, script=None, interactive=True):
    commands = {}
    if script:
        for line in open(script, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            turn, cmd = line.split(":", 1)
            commands.setdefault(int(turn), []).append(cmd.strip())
    hook = make_hook(None, commands, interactive)
    e = scenario(root, seed, use_hand=True, rulings_path=os.path.join(root, "data/gm-rulings.json") if rulings else None, ruleset=ruleset, hook=hook)
    out = "\n".join(e.log_lines) + "\n"
    open(os.path.join(root, "output/gm-console-log.md"), "w", encoding="utf-8").write("# GM 콘솔 전투 로그 (자동 생성)\n\n" + out)
    open(os.path.join(root, "output/gm-console-report.md"), "w", encoding="utf-8").write(e.rulings.report())
    return e


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "."
    seed = next((int(a) for a in sys.argv[2:] if a.isdigit()), 5)
    ruleset = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--ruleset=")), None)
    script = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--script=")), None)
    eng = main(root, seed, ruleset, "--rulings" in sys.argv, script, interactive=script is None)
    print(f"로그 {len(eng.log_lines)}줄 → output/gm-console-log.md, GM 개입 {sum(1 for l in eng.log_lines if 'GM 상태' in l or 'GM 개변' in l)}줄")
