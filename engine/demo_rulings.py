"""GM 재정(개변) 시연: 파일럿 전투를 data/gm-rulings.json 의 재정을 켜고 다시 돌린다. 같은 seed 라 차이는 전부 재정 때문이다.
  python -X utf8 -I engine/demo_rulings.py <root> [seed]   → output/gm-rulings-demo.md, output/gm-rulings-report.md"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import Rules, scenario  # noqa: E402
from rulings import InteractiveGM  # noqa: E402


def main(root, seed=5, interactive=False):
    path = os.path.join(root, "data/gm-rulings.json")
    if interactive:      # 터미널에서 GM 이 프롬프트마다 직접 답한다 (빈 입력 = 엔진 기본값)
        Rules._gm_provider = InteractiveGM()
    e = scenario(root, seed, use_hand=True, rulings_path=path)
    # 전투 도중의 즉흥 재정도 가능하다: 장면이 끝나면 장면 범위 재정은 해제된다
    e.end_scene()
    head = ["# GM 재정 시연 (자동 생성)", "", f"파일 `data/gm-rulings.json` 의 재정 {len([x for x in e.rulings.log if x['kind'] != 'end_scene'])}건을 켜고 파일럿 전투(seed {seed})를 다시 돌린 로그. 기본 로그 output/pilot-combat-log.md 와 같은 주사위이므로 차이는 전부 재정 때문이다.", "",
            "## 적용된 재정", ""]
    for x in e.rulings.log:
        if x["kind"] == "end_scene":
            continue
        head.append(f"- **{x['kind']}** {x['what']}: {x['before']} → {x['after']} [{x['scope']}] — {x['reason']}")
    head += ["", "## 전투 로그", ""]
    out = "\n".join(head + e.log_lines) + "\n"
    open(os.path.join(root, "output/gm-rulings-demo.md"), "w", encoding="utf-8").write(out)
    open(os.path.join(root, "output/gm-rulings-report.md"), "w", encoding="utf-8").write(e.rulings.report())
    print("\n".join(head))
    print(f"로그 {len(e.log_lines)}줄, GM 개변 표식 {sum(1 for l in e.log_lines if 'GM 개변' in l or 'GM 답' in l)}줄")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".", int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 5, interactive="--interactive" in sys.argv)
