"""격자·범위 단위 테스트 (원문 정의 + 전투 데모).  python -X utf8 -I engine/test_grid.py <root>"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grid import Grid  # noqa: E402


def run(root):
    res = []

    def check(name, ok, detail=""):
        res.append((name, bool(ok), detail))

    g = Grid(12, 12)
    o = (5, 5)
    check("파열 1 = 인접 8칸", len(g.burst(o, 1)) == 8, f"{len(g.burst(o, 1))}")
    check("파열 2 = 24칸 (5×5 - 자기 칸)", len(g.burst(o, 2)) == 24, f"{len(g.burst(o, 2))}")
    check("원거리 폭발 3 = 3×3 = 9칸", len(g.ranged_blast((5, 5), 3)) == 9)
    check("원거리 폭발 2 = 2×2 = 4칸", len(g.ranged_blast((5, 5), 2)) == 4)
    check("인접 폭발 2 (오른쪽) = 사용자에 인접한 2×2 = 4칸", len(g.close_blast(o, 2, (1, 0))) == 4, f"{sorted(g.close_blast(o, 2, (1, 0)))}")
    check("직선 4 (위) = 4칸", g.line(o, (0, 1), 4) == {(5, 6), (5, 7), (5, 8), (5, 9)})
    cone2 = g.cone(o, (1, 0), 2)
    check("원뿔 2 (오른쪽) = 거리1 1칸 + 거리2 3칸 = 4칸 (데모: 용해액 원뿔 2가 실바나와 아치 둘을 덮음)", len(cone2) == 4 and (6, 5) in cone2 and (7, 4) in cone2 and (7, 6) in cone2, f"{sorted(cone2)}")
    check("매우 인접: 대각선은 아님, 인접: 대각선 포함", g.cardinally_adjacent(o, (6, 5)) and not g.cardinally_adjacent(o, (6, 6)) and g.adjacent(o, (6, 6)))
    check("대각선 이동 비용: 대각선 3칸 = 1+2+1 = 4m", g.diagonal_cost([(0, 0), (1, 1), (2, 2), (3, 3)]) == 4)
    check("직선+대각선 혼합: 직선 2 + 대각선 2 = 2 + 1 + 2 = 5m", g.diagonal_cost([(0, 0), (1, 0), (2, 0), (3, 1), (4, 2)]) == 5)
    # 차단 지형
    wall = Grid(12, 12, blocking={(6, 5)})
    b = wall.burst(o, 2)
    check("차단 지형: 파열은 벽 뒤로 못 간다 ((7,5) 제외, 벽 칸 자체도 제외)", (7, 5) not in b and (6, 5) not in b and ((7, 4) in b or (7, 6) in b), f"{(7,5) in b} {(6,5) in b}")
    check("차단 지형: 직선은 벽에서 멈춘다", wall.line(o, (1, 0), 4) == set())
    check("차단 지형: 원거리 단일 대상은 시작점-대상 직선이 벽을 지나면 막힘", wall.blocked(o, (8, 5)) and not wall.blocked(o, (5, 9)))
    # 포위
    check("포위: 적 2명이 대상에 인접하고 서로 비인접 → 포위", g.flanked((5, 5), [(4, 5), (6, 5)]))
    check("포위: 적 2명이 서로 인접하면 포위 아님", not g.flanked((5, 5), [(4, 5), (4, 6)]))
    check("포위: 대형(2×2 기준) 대상은 적 3명 필요", not g.flanked((5, 5), [(4, 5), (6, 5)], size=2) and g.flanked((5, 5), [(4, 5), (6, 5), (5, 4)], size=2))

    passed = sum(1 for _, ok, _ in res if ok)
    lines = ["# 격자·범위 단위 테스트 (자동 생성)", "", f"**{passed}/{len(res)} 통과**", "", "| # | 규칙 | 결과 | 비고 |", "|---|---|---|---|"]
    for i, (n, ok, d) in enumerate(res, 1):
        lines.append(f"| {i} | {n} | {'PASS' if ok else 'FAIL'} | {d} |")
    open(os.path.join(root, "output/grid-tests.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return passed == len(res)


if __name__ == "__main__":
    sys.exit(0 if run(sys.argv[1] if len(sys.argv) > 1 else ".") else 1)
