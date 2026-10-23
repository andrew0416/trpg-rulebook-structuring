"""
격자·범위 모듈 (A층 '이동과 위치선정' + Ch10 '범위 키워드').
원문의 범위 정의는 그림([img])이 많아서, 글로 적힌 정의와 전투 데모(원뿔 2가 두 대상을 덮음)로 복원했다.
가정은 ASSUMPTIONS 에 적어 두었다.

좌표: (x, y) 정수 칸(1칸 = 1m). 인접 = 체비셰프 거리 1. 매우 인접 = 상하좌우.
"""
ASSUMPTIONS = {
    "cone": "PTU 1.05 p343: 직교 첫 줄 1칸, 이후 폭 3칸. 대각선 Cone2 도식 3칸 검증; 더 큰 대각선은 폭/대각선 거리의 일반화로 별도 검수 필요.",
    "close_blast": "인접 폭발 X: 사용자에 인접한 X×X 정사각형. 방향은 사용자가 고른다(모서리 기준).",
    "line": "PTU 1.05 p344: 길이는 미터, 대각선 이동 비용 1,2,1,2를 적용.",
    "los": "차단 지형 판정은 시작점과 대상 칸 중심을 잇는 브레즌햄 선이 차단 칸을 지나면 막힌 것으로 본다.",
}


def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


class Grid:
    def __init__(self, width, height, blocking=(), rough=(), slow=(), walls=()):
        self.w, self.h = width, height
        self.blocking = set(blocking)
        self.rough = set(rough)
        self.slow = set(slow)
        self.walls = set()
        for a, b in walls:
            a, b = tuple(a), tuple(b)
            if abs(a[0]-b[0]) + abs(a[1]-b[1]) != 1:
                raise ValueError("A wall must separate two cardinally adjacent cells")
            self.walls.add(tuple(sorted((a, b))))

    def inside(self, c):
        return 0 <= c[0] < self.w and 0 <= c[1] < self.h

    # ---------- 이동 ----------
    def diagonal_cost(self, path):
        """대각선 이동: 턴 내 첫 대각선 1m, 둘째 2m, 셋째 1m … (ch07 '대각선 이동')"""
        cost, diag = 0, 0
        for a, b in zip(path, path[1:]):
            dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
            assert dx <= 1 and dy <= 1
            if dx == 1 and dy == 1:
                diag += 1
                step = 1 if diag % 2 else 2
            else:
                step = 1
            cost += step * (2 if b in self.slow else 1)
        return cost

    def adjacent(self, a, b):
        return cheb(a, b) == 1

    def cardinally_adjacent(self, a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1

    # ---------- 시야/차단 ----------
    def line_cells(self, a, b):
        """브레즌햄 선 (양 끝 제외)."""
        x0, y0 = a
        x1, y1 = b
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        cells = []
        while (x0, y0) != (x1, y1):
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
            cells.append((x0, y0))
        return cells[:-1]

    def blocked(self, origin, target):
        return (any(c in self.blocking for c in self.line_cells(origin, target))
                or target in self.blocking or self.wall_blocked(origin, target))

    def wall_blocked(self, origin, target):
        """Trace center-to-center through cell-edge walls (PTU p345).
        Touching one wall endpoint does not occlude a corner; an L or continuous
        joined wall does. Fraction coordinates keep those corner cases exact.
        """
        return bool(self.wall_crossings(origin, target))

    def wall_crossings(self, origin, target, *, walls=None):
        """Exact crossings of actual cell-edge surfaces, with the same corner rule."""
        from fractions import Fraction
        endpoint_hits = {}; crossings = {}
        vector = (target[0]-origin[0], target[1]-origin[1])
        for a, b in self.walls if walls is None else walls:
            axis = 0 if a[0] != b[0] else 1
            other = 1-axis
            if not vector[axis]:continue
            position = Fraction(a[axis]+b[axis], 2)
            t = (position-origin[axis])/vector[axis]
            if not 0 < t < 1:continue
            cross = origin[other] + t*vector[other]
            center = a[other]
            low, high = center-Fraction(1,2), center+Fraction(1,2)
            if low < cross < high:crossings[t] = tuple(origin[i]+t*vector[i] for i in range(2))
            if cross in (low, high):endpoint_hits[t] = endpoint_hits.get(t,0)+1
        for t, count in endpoint_hits.items():
            if count >= 2:crossings[t] = tuple(origin[i]+t*vector[i] for i in range(2))
        return [crossings[t] for t in sorted(crossings)]

    # ---------- 범위 ----------
    def burst(self, origin, x):
        """파열 X: 사용자 주변 반경 X. 차단 지형 뒤는 제외 (ch10 '범위와 차단 지형')."""
        out = set()
        for cx in range(origin[0] - x, origin[0] + x + 1):
            for cy in range(origin[1] - x, origin[1] + x + 1):
                c = (cx, cy)
                if c != origin and self.inside(c) and cheb(origin, c) <= x and not self.blocked(origin, c):
                    out.add(c)
        return out

    def ranged_blast(self, center, y):
        """원거리 폭발 Y: 중심 기준 Y×Y 정사각형(Y 홀수면 중심 대칭, 짝수면 중심이 좌상단 쪽). 시작점은 폭발 중심."""
        off = (y - 1) // 2
        out = set()
        for cx in range(center[0] - off, center[0] - off + y):
            for cy in range(center[1] - off, center[1] - off + y):
                c = (cx, cy)
                if self.inside(c) and not self.blocked(center, c):
                    out.add(c)
        return out

    def close_blast(self, origin, x, direction):
        """인접 폭발 X: 사용자에 인접한 X×X 정사각형. direction = (dx, dy) 단위 벡터."""
        dx, dy = direction
        sx = origin[0] + (1 if dx > 0 else -x if dx < 0 else -(x // 2))
        sy = origin[1] + (1 if dy > 0 else -x if dy < 0 else -(x // 2))
        out = set()
        for cx in range(sx, sx + x):
            for cy in range(sy, sy + x):
                c = (cx, cy)
                if self.inside(c) and c != origin and not self.blocked(origin, c):
                    out.add(c)
        return out

    def line(self, origin, direction, x):
        dx, dy = direction
        out, c, spent = set(), origin, 0
        for step in range(1, x + 1):
            cost = 2 if dx and dy and step % 2 == 0 else 1
            if spent + cost > x:break
            c = (c[0] + dx, c[1] + dy)
            if not self.inside(c) or self.blocked(origin, c):break
            out.add(c)
            spent += cost
        return out

    def cone(self, origin, direction, x):
        """PTU p343 fixed-width cardinal rows and the pictured diagonal Cone2."""
        dx, dy = direction
        out = set()
        if dx and dy:
            for i in range(1, x + 1):
                for j in range(1, x + 1):
                    # The pictured diagonal footprint, extended with movement distance.
                    if abs(i-j) <= 1 and max(i,j) + min(i,j)//2 <= x:
                        out.add((origin[0]+dx*i, origin[1]+dy*j))
        else:
            for d in range(1, x + 1):
                for off in ([0] if d == 1 else [-1,0,1]):
                    out.add((origin[0]+dx*d+(off if dx==0 else 0),
                             origin[1]+dy*d+(off if dy==0 else 0)))
        return {c for c in out if self.inside(c) and not self.blocked(origin, c)}

    # ---------- 포위 ----------
    def flanked(self, target, enemies, size=1):
        """소형/중형: 대상에 인접한 적 2명이 서로 인접하지 않으면 포위(-2 회피). 대형 3, 거대형 4 (ch07 '포위하기')."""
        need = {1: 2, 2: 3, 3: 4, 4: 5}.get(size, 2)
        adj = [e for e in enemies if self.adjacent(target, e)]
        if len(adj) < need:
            return False
        for i, a in enumerate(adj):
            for b in adj[i + 1:]:
                if not self.adjacent(a, b):
                    return True
        return False
