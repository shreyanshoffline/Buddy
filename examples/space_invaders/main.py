"""Space Invaders. Arrows/A-D move, SPACE fires, P pauses, R restarts, ESC quits."""
import os

import pygame

from game import Game, W, H
from render import draw

HISCORE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".hiscore")


def load_hiscore():
    try:
        return int(open(HISCORE_FILE).read().strip())
    except (OSError, ValueError):
        return 0


def main(max_frames=None):
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Space Invaders")
    clock = pygame.time.Clock()
    font, big = pygame.font.SysFont("menlo", 18), pygame.font.SysFont("menlo", 36, bold=True)
    game = Game(hiscore=load_hiscore())
    title, paused, frames = True, False, 0
    running = True
    while running and (max_frames is None or frames < max_frames):
        frames += 1
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
            elif e.type == pygame.KEYDOWN:
                if title and e.key == pygame.K_SPACE:
                    title = False
                elif e.key == pygame.K_p and not title:
                    paused = not paused
                elif e.key == pygame.K_r and game.state == "game_over":
                    game.reset()
        keys = pygame.key.get_pressed()
        if not title and not paused:
            game.update(min(clock.get_time() / 1000, 0.05),
                        left=keys[pygame.K_LEFT] or keys[pygame.K_a],
                        right=keys[pygame.K_RIGHT] or keys[pygame.K_d],
                        fire=keys[pygame.K_SPACE])
        draw(screen, game, font, big, paused, title)
        pygame.display.flip()
        clock.tick(60)
    try:
        open(HISCORE_FILE, "w").write(str(game.hiscore))
    except OSError:
        pass
    pygame.quit()


if __name__ == "__main__":
    main()
