"""Space Invaders game logic. No pygame in here, so it can be tested headless."""
import random
from dataclasses import dataclass

W, H = 800, 600
ROW_POINTS = [30, 20, 20, 10, 10]
COLS, ROWS = 11, 5


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float

    def hits(self, o):
        return self.x < o.x + o.w and self.x + self.w > o.x and self.y < o.y + o.h and self.y + self.h > o.y


class Invader(Box):
    def __init__(self, x, y, row):
        super().__init__(x, y, 32, 24)
        self.row = row
        self.points = ROW_POINTS[row]


class Game:
    def __init__(self, seed=None, hiscore=0):
        self.rng = random.Random(seed)
        self.hiscore = hiscore
        self.reset()

    def reset(self):
        self.score, self.lives, self.level, self.state = 0, 3, 1, "playing"
        self.start_wave()

    def start_wave(self):
        self.invaders = [Invader(60 + c * 52, 70 + r * 40, r) for r in range(ROWS) for c in range(COLS)]
        self.total = len(self.invaders)
        self.direction = 1
        self.player = Box(W / 2 - 20, H - 60, 40, 20)
        self.cooldown = 0.0
        self.bullets, self.bombs = [], []
        self.bomb_timer = 1.0
        self.ufo, self.ufo_timer = None, 15.0
        self.shields = [Box(x + dx * 6, H - 150 + dy * 6, 6, 6)
                        for x in (110, 290, 470, 650) for dx in range(10) for dy in range(5)]

    # ---- per-frame update -------------------------------------------------
    def update(self, dt, left=False, right=False, fire=False):
        if self.state != "playing":
            return
        speed = 320
        self.player.x = max(0, min(W - self.player.w, self.player.x + (right - left) * speed * dt))
        self.cooldown -= dt
        if fire and self.cooldown <= 0 and len(self.bullets) < 2:
            self.bullets.append(Box(self.player.x + self.player.w / 2 - 2, self.player.y - 12, 4, 12))
            self.cooldown = 0.35
        for b in self.bullets:
            b.y -= 560 * dt
        self.bullets = [b for b in self.bullets if b.y + b.h > 0]
        self._move_invaders(dt)
        self._bombs(dt)
        self._ufo(dt)
        self._collisions()
        if self.state == "playing" and not self.invaders:
            self.level += 1
            lives, score = self.lives, self.score
            self.start_wave()
            self.lives, self.score = lives, score

    def _move_invaders(self, dt):
        alive = len(self.invaders)
        if not alive:
            return
        speed = (28 + 22 * self.level) * (1 + 3.0 * (self.total - alive) / self.total)
        dx = self.direction * speed * dt
        left = min(i.x for i in self.invaders) + dx
        right = max(i.x + i.w for i in self.invaders) + dx
        if left < 10 or right > W - 10:
            self.direction *= -1
            for i in self.invaders:
                i.y += 18
        else:
            for i in self.invaders:
                i.x += dx
        if any(i.y + i.h >= self.player.y for i in self.invaders):
            self._lose_all()

    def _bombs(self, dt):
        self.bomb_timer -= dt
        if self.bomb_timer <= 0 and self.invaders:
            bottoms = {}
            for i in self.invaders:
                col = round(i.x / 52)
                if col not in bottoms or i.y > bottoms[col].y:
                    bottoms[col] = i
            shooter = self.rng.choice(list(bottoms.values()))
            self.bombs.append(Box(shooter.x + shooter.w / 2 - 2, shooter.y + shooter.h, 4, 12))
            self.bomb_timer = max(0.25, 1.2 - 0.08 * self.level) * self.rng.uniform(0.6, 1.2)
        for b in self.bombs:
            b.y += 260 * dt
        self.bombs = [b for b in self.bombs if b.y < H]

    def _ufo(self, dt):
        self.ufo_timer -= dt
        if self.ufo is None and self.ufo_timer <= 0:
            self.ufo = Box(-40, 40, 40, 18)
            self.ufo_timer = 20.0
        if self.ufo:
            self.ufo.x += 150 * dt
            if self.ufo.x > W:
                self.ufo = None

    def _collisions(self):
        for b in list(self.bullets):
            hit = next((i for i in self.invaders if b.hits(i)), None)
            if hit:
                self.invaders.remove(hit)
                self.bullets.remove(b)
                self._add_score(hit.points)
                continue
            if self.ufo and b.hits(self.ufo):
                self.ufo = None
                self.bullets.remove(b)
                self._add_score(self.rng.choice([50, 100, 150, 300]))
                continue
            block = next((s for s in self.shields if b.hits(s)), None)
            if block:
                self.shields.remove(block)
                self.bullets.remove(b)
        for b in list(self.bombs):
            block = next((s for s in self.shields if b.hits(s)), None)
            if block:
                self.shields.remove(block)
                self.bombs.remove(b)
            elif b.hits(self.player):
                self.bombs.remove(b)
                self.lives -= 1
                if self.lives <= 0:
                    self._lose_all()

    def _add_score(self, pts):
        self.score += pts
        self.hiscore = max(self.hiscore, self.score)

    def _lose_all(self):
        self.lives = max(0, self.lives)
        self.state = "game_over"
