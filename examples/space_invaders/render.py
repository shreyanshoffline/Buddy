"""pygame drawing for Space Invaders. Reads Game state; never changes it."""
import pygame
from game import W, H

SPRITES = {
    0: ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX", "X.XXXXXXX.X", "X.X.....X.X", "...XX.XX..."],
    1: ["..X.....X..", "X..X...X..X", "X.XXXXXXX.X", "XXX.XXX.XXX", "XXXXXXXXXXX", ".XXXXXXXXX.", "..X.....X..", ".X.......X."],
    2: ["...XXXX....", ".XXXXXXXXXX", "XXXXXXXXXXX", "XXX..XX..XX", "XXXXXXXXXXX", "...XX..XX..", "..XX.XX.XX.", "XX.......XX"],
}
COLORS = {0: (255, 90, 120), 1: (255, 200, 80), 2: (90, 255, 160), 3: (90, 255, 160), 4: (90, 255, 160)}
_cache = {}


def _sprite(kind, w, h, color):
    key = (kind, w, h, color)
    if key not in _cache:
        rows = SPRITES[kind]
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cw, ch = w / len(rows[0]), h / len(rows)
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c == "X":
                    pygame.draw.rect(surf, color, (x * cw, y * ch, cw + 1, ch + 1))
        _cache[key] = surf
    return _cache[key]


def draw(screen, game, font, big, paused=False, title=False):
    screen.fill((6, 6, 20))
    for i in game.invaders:
        kind = 0 if i.row == 0 else 1 if i.row < 3 else 2
        screen.blit(_sprite(kind, int(i.w), int(i.h), COLORS[i.row]), (i.x, i.y))
    for s in game.shields:
        pygame.draw.rect(screen, (80, 220, 120), (s.x, s.y, s.w, s.h))
    p = game.player
    pygame.draw.polygon(screen, (230, 230, 255), [(p.x, p.y + p.h), (p.x + p.w / 2, p.y), (p.x + p.w, p.y + p.h)])
    for b in game.bullets:
        pygame.draw.rect(screen, (255, 255, 255), (b.x, b.y, b.w, b.h))
    for b in game.bombs:
        pygame.draw.rect(screen, (255, 120, 80), (b.x, b.y, b.w, b.h))
    if game.ufo:
        pygame.draw.ellipse(screen, (255, 60, 60), (game.ufo.x, game.ufo.y, game.ufo.w, game.ufo.h))
    screen.blit(font.render("SCORE %05d" % game.score, True, (255, 255, 255)), (16, 10))
    screen.blit(font.render("HI %05d" % game.hiscore, True, (255, 220, 120)), (W // 2 - 50, 10))
    screen.blit(font.render("LIVES %d  LEVEL %d" % (game.lives, game.level), True, (255, 255, 255)), (W - 200, 10))
    msg = None
    if title:
        msg = "SPACE INVADERS - press SPACE"
    elif paused:
        msg = "PAUSED - press P"
    elif game.state == "game_over":
        msg = "GAME OVER - press R"
    if msg:
        text = big.render(msg, True, (255, 255, 255))
        screen.blit(text, (W // 2 - text.get_width() // 2, H // 2 - 20))
