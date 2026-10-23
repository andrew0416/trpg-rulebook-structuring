"""
콘테스트 엔진 검증: 챕터 8 '콘테스트 데모(시범)' 의 주사위 눈을 그대로 넣어 라운드별 어필·펌블·흥분도와 최종 결과를 재현한다.

  python -X utf8 -I engine/test_contest.py <experiment_root>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from contest import ContestEngine, ContestRules, demo_contestants  # noqa: E402


class FixedRng:
    def __init__(self, seq):
        self.seq = list(seq)

    def randint(self, a, b):
        v = self.seq.pop(0)
        assert a <= v <= b
        return v


def run(root):
    r = ContestRules(root)
    e = ContestEngine(r, apply_intro_bonus=False)   # 데모는 매력 사용자에게 시작 어필 +2 를 주지 않는다 (원문 규칙과 데모의 불일치)
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    cs = demo_contestants()
    naru, zubat, mawile = cs
    e.rng = FixedRng([5, 1, 3, 4, 4, 4, 3, 1, 6, 2, 5, 6, 2])
    e.intro_stage(cs, "귀여움")
    check("소개 단계: [5,1,3,4,4]→4, [4,3,1,6]→3, [2,5,6,2]→2 귀여움 주사위 (+스피드 2 = 내루미 6)", naru.stat_dice["귀여움"] == 6 and zubat.stat_dice["귀여움"] == 3 and mawile.stat_dice["귀여움"] == 2, f"{naru.stat_dice} {zubat.stat_dice} {mawile.stat_dice}")
    check("문자 배정: 내루미 A, 주뱃 B, 입치트 C", (naru.letter, zubat.letter, mawile.letter) == ("A", "B", "C"))
    # 라운드 1: 무대 C A B, 턴 순서 A(중심) B C
    e.perform(naru, "헤롱헤롱", "귀여움", [mawile, zubat], True, fixed_rolls=[3, 2, 6, 1])
    check("R1 내루미 헤롱헤롱(고조, 중심) [3,2,6,1] → 어필 4, 펌블 1, 흥분도 2", (naru.appeal, naru.fumble, naru.excitement) == (4, 1, 2), f"{naru}")
    e.perform(zubat, "유턴", "귀여움", [naru], False, fixed_rolls=[6, 1, 2, 1, 5, 1])
    check("R1 주뱃 유턴(반전 어필 5d6 +1 일치) [6,1,2,1,5,1] → 어필 4", zubat.appeal == 4, f"{zubat}")
    # 데모는 '5d6' 이라 쓰고 눈 4개만 보여준다. 규칙대로면 3(고조)+2(스탯)+1(일치)=6d6. 데모의 4개 + 점수 없는 1 두 개로 채움.
    e.perform(mawile, "달콤한향기", "귀여움", [naru], False, spend_stat_dice=2, fixed_rolls=[2, 6, 4, 1, 1, 1])
    check("R1 입치트 달콤한향기(고조, 스탯 2) [2,6,4,1,+1,1] → 어필 4, 흥분도 2 (데모는 주사위 수를 5d6이라 적고 4개만 표시)", (mawile.appeal, mawile.excitement) == (4, 2), f"{mawile}")
    # 라운드 2: 무대 A B C, 턴 순서 B(중심) C A
    e.perform(zubat, "이상한빛", "귀여움", [naru, mawile], True, spend_stat_dice=3, fixed_rolls=[1, 1, 4, 6, 5, 1, 6, 2])
    check("R2 주뱃 이상한빛(동요, 중심, 슬기로움 스탯 3) → 어필 +10 (14), 펌블 3; 내루미·입치트 흥분도 -1", (zubat.appeal, zubat.fumble, naru.excitement, mawile.excitement) == (14, 3, 1, 1), f"{zubat} {naru.excitement} {mawile.excitement}")
    e.perform(mawile, "거짓울음", "귀여움", [zubat], False, fixed_rolls=[6, 6, 3, 5])
    check("R2 입치트 거짓울음(고조, 흥분도 1 → 4d6) [6,6,3,5] → 어필 +6 (10), 흥분도 3", (mawile.appeal, mawile.excitement) == (10, 3), f"{mawile}")
    e.perform(naru, "아쿠아테일", "귀여움", [zubat], False, spend_stat_dice=3, fixed_rolls=[1, 5, 3, 3, 4, 6, 6, 5, 3, 5])
    check("R2 내루미 아쿠아테일(안정된 공연 5 + 흥분도 1 + 일치 1 + 스탯 3 = 10d6) → 어필 +11 (15), 흥분도 2", (naru.appeal, naru.excitement) == (15, 2), f"{naru}")
    # 라운드 3: 무대 B C A, 턴 순서 C(중심) A B
    e.perform(mawile, "기가임팩트", "귀여움", [zubat, naru], True, spend_stat_dice=2, fixed_rolls=[3, 4, 5, 4, 1, 5, 6, 4, 1, 6, 2])
    check("R3 입치트 기가임팩트(이제부터: 흥분도 3 → 6d6, +3 흥분도, +2 아름다움 = 11d6, 중심) 재굴림 눈 → 어필 +17 (27), 펌블 +2", (mawile.appeal, mawile.fumble) == (27, 2), f"{mawile}")
    e.perform(naru, "웅크리기", "귀여움", [mawile], False, spend_stat_dice=3, fixed_rolls=[5, 3, 1, 3, 5, 1, 3, 6, 6])
    check("R3 내루미 웅크리기(방해 3 + 흥분도 2 + 일치 1 + 스탯 3 = 9d6) → 입치트 펌블 +9 (11), 내루미 어필 그대로 15", (mawile.fumble, naru.appeal) == (11, 15), f"{mawile} {naru}")
    e.perform(zubat, "화풀이", "귀여움", [mawile], False, spend_stat_dice=3, fixed_rolls=[5, 6, 4, 6, 6, 4, 3, 1, 3])
    check("R3 주뱃 화풀이(필사 5 + 일치 1 + 스탯 3 = 9d6) → 어필 +14 (28), 펌블 +1 (4)", (zubat.appeal, zubat.fumble) == (28, 4), f"{zubat}")
    final = {c.name: c.appeal - c.fumble for c in cs}
    check("최종: 내루미 14, 입치트 16, 주뱃 24 → 주뱃 우승", final == {"내루미": 14, "입치트": 16, "주뱃": 24}, f"{final}")
    check("스탯 주사위 소모: 내루미 귀여움 0, 주뱃 귀여움 0·슬기로움 0, 입치트 귀여움 0·아름다움 0", naru.stat_dice["귀여움"] == 0 and zubat.stat_dice["귀여움"] == 0 and zubat.stat_dice["슬기로움"] == 0 and mawile.stat_dice["아름다움"] == 0, f"{naru.stat_dice} {zubat.stat_dice} {mawile.stat_dice}")
    # 타입 관계 (원문 예: 근사함 콘테스트에서 슬기로움·귀여움은 대항, 강인함·아름다움은 연합)
    check("타입: 근사함 콘테스트에서 슬기로움 기술 -1d6(대항)", e.type_mod("슬기로움", "근사함")[0] == -1)
    check("타입: 근사함 콘테스트에서 귀여움 기술 -1d6(대항)", e.type_mod("귀여움", "근사함")[0] == -1)
    check("타입: 근사함 콘테스트에서 강인함·아름다움 기술 변화 없음(연합)", e.type_mod("강인함", "근사함")[0] == 0 and e.type_mod("아름다움", "근사함")[0] == 0)

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# PTK 콘테스트 규칙 단위 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과** — 챕터 8 데모의 주사위 눈을 그대로 사용", "", "| # | 규칙 (원문 예시) | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (name, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {name} | {'PASS' if ok else 'FAIL'} | {d} |")
    open(os.path.join(root, "output/contest-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
