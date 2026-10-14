import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from game import Game, Box, W, H, Invader


def run(game, seconds, **inputs):
    for _ in range(int(seconds * 60)):
        game.update(1 / 60, **inputs)


class SpaceInvadersTests(unittest.TestCase):
    def test_initial_state(self):
        g = Game(seed=1)
        self.assertEqual((len(g.invaders), g.lives, g.score, g.state), (55, 3, 0, "playing"))

    def test_player_moves_and_clamps(self):
        g = Game(seed=1)
        x0 = g.player.x
        run(g, 0.2, right=True)
        self.assertGreater(g.player.x, x0)
        run(g, 5, left=True)
        self.assertEqual(g.player.x, 0)
        run(g, 5, right=True)
        self.assertEqual(g.player.x, W - g.player.w)

    def test_fire_has_cooldown_and_bullet_limit(self):
        g = Game(seed=1)
        g.update(1 / 60, fire=True)
        g.update(1 / 60, fire=True)
        self.assertEqual(len(g.bullets), 1)
        run(g, 0.5, fire=True)
        self.assertLessEqual(len(g.bullets), 2)

    def test_bullet_kills_invader_and_scores(self):
        g = Game(seed=1)
        target = g.invaders[0]
        g.bullets.append(Box(target.x + 4, target.y + 4, 4, 12))
        g.update(1 / 60)
        self.assertEqual(len(g.invaders), 54)
        self.assertEqual(g.score, target.points)
        self.assertEqual(g.hiscore, g.score)

    def test_invaders_reverse_and_descend_at_edge(self):
        g = Game(seed=1)
        y0 = max(i.y for i in g.invaders)
        run(g, 5)  # ~3.6s to reach the right edge at level-1 speed, then it turns around
        self.assertEqual(g.direction, -1)
        self.assertGreater(max(i.y for i in g.invaders), y0)

    def test_bomb_hit_costs_life_and_game_over(self):
        g = Game(seed=1)
        for expected in (2, 1, 0):
            g.bombs.append(Box(g.player.x + 5, g.player.y, 4, 12))
            g.update(1 / 60)
            self.assertEqual(g.lives, expected)
        self.assertEqual(g.state, "game_over")
        before = g.player.x
        g.update(1, right=True)
        self.assertEqual(g.player.x, before)

    def test_shield_absorbs_bullet(self):
        g = Game(seed=1)
        block = g.shields[0]
        n = len(g.shields)
        g.bullets.append(Box(block.x, block.y + 4, 4, 12))
        g.update(1 / 60)
        self.assertEqual(len(g.shields), n - 1)

    def test_clearing_wave_starts_next_level_keeping_score(self):
        g = Game(seed=1)
        g.score = 120
        g.invaders = []
        g.update(1 / 60)
        self.assertEqual((g.level, g.score, len(g.invaders)), (2, 120, 55))

    def test_invaders_reaching_player_ends_game(self):
        g = Game(seed=1)
        for i in g.invaders:
            i.y = g.player.y
        g.update(1 / 60)
        self.assertEqual(g.state, "game_over")

    def test_ufo_can_be_shot(self):
        g = Game(seed=1)
        g.ufo = Box(100, 300, 40, 18)
        g.bullets.append(Box(110, 305, 4, 12))
        g.update(1 / 60)
        self.assertIsNone(g.ufo)
        self.assertIn(g.score, (50, 100, 150, 300))

    def test_long_random_play_never_crashes(self):
        g = Game(seed=7)
        for n in range(60 * 90):
            g.update(1 / 60, left=(n // 40) % 2 == 0, right=(n // 40) % 2 == 1, fire=True)
            if g.state == "game_over":
                g.reset()
        self.assertGreaterEqual(g.score, 0)


if __name__ == "__main__":
    unittest.main()
