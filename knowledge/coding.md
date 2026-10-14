# Coding guide — build, fix, and upgrade software with the code_* tools
Read a section with read_guide("coding", section="<keyword>"). Everything here assumes the coding-mode loop: write -> run -> read output -> fix -> repeat.

## Loop
- New project: code_new_project(name) -> path. Existing: use the folder given; code_overview first.
- Write files with code_write (complete, no stubs), tweak with code_edit (exact text, unique match).
- After each change: code_check (syntax), then code_run / code_test. Read the real output. Fix the root cause.
- Done = it ran and passed in this session. Say what you could not verify.

## Environment
- Python deps: code_setup_env(folder, "pygame requests") makes folder/.venv; code_run then uses it automatically.
- Pure-Python stdlib projects need no venv. Run scripts with `python3 file.py`.
- Windowed programs never exit by themselves: test them headless (headless=true sets SDL dummy drivers) or add a `max_frames` argument to main() for smoke tests, then code_launch for the user.
- Node projects: code_run("npm install"), code_run("npm test"). HTML/JS: code_check runs `node --check` if Node exists.

## Upgrading existing code
1. code_overview(folder); read README and the entry point.
2. code_search for the functions/classes involved; code_read only those ranges.
3. Run existing tests first (code_test). Note what already fails so you don't take the blame.
4. Make the smallest edits that do the job. Match naming, indentation, and style. Do not reformat untouched code.
5. Run tests again; add a test for each behavior you change or add.
6. If a refactor spreads, code_undo the file and take a smaller step.
7. Summarise as: what changed (files), why, how verified, anything risky.
Typical upgrades: add type hints and docstrings, extract duplicated code, replace deprecated APIs, fix bugs from a stack trace (search the failing line, read 30 lines around it, reproduce, fix, rerun), add error handling at I/O boundaries, speed up hot loops after measuring, port Python 2 idioms, add CLI arguments, add logging.

## Debugging recipe
Reproduce with code_run -> read the last traceback line first -> code_read around that file:line -> form one hypothesis -> change one thing -> rerun. Add a print/assert only to confirm a guess, then remove it. If three attempts fail, re-read the requirements instead of patching further.

## Tests
- Python: write `tests/test_*.py` using unittest (works everywhere) or pytest if installed. Test behavior, not implementation. Include one long randomized/soak test that must not crash.
- Keep logic free of I/O and UI so it is testable. Pass in a seed for randomness.

## Games
Default: Python + pygame in a project venv. Browser/HTML if the user says web, browser, or JS.
Architecture (always split): `game.py` pure logic with `update(dt, inputs)` and plain data; `render.py` draws only; `main.py` events + loop + hi-score; `tests/test_game.py`. Fixed 60 FPS, clamp dt (0.05). Draw with shapes or sprites defined as strings; no external assets.
Game checklist: title screen, pause (P), game over + restart (R), score, hi-score saved to a file, lives, levels that get harder, sensible controls (arrows + WASD, SPACE), window caption, ESC quits.
Headless verification: run main(max_frames=300) with headless=true; render one frame to PNG with pygame.image.save and look at it if you can; run the unit tests.

## Space Invaders (full spec)
- 800x600. Player ship bottom, moves left/right at ~320 px/s, clamped. Fire with SPACE: 0.35 s cooldown, max 2 bullets on screen.
- 5 rows x 11 columns of invaders, three sprite shapes, row points 30/20/20/10/10. The block marches sideways; at an edge it reverses and drops ~18 px. Speed rises as invaders die (up to ~4x) and with each level.
- Invaders drop bombs from the lowest invader in a random column; interval shrinks with level. Bomb hit = lose a life; 0 lives = game over.
- 4 destructible shields built from small blocks; bullets and bombs each remove the block they hit.
- UFO crosses the top every ~20 s; shooting it gives 50/100/150/300.
- Clear the wave -> next level, keep score and lives. Invaders reaching the player's row = game over.
- Tests to write: initial state; movement + clamp; fire cooldown and bullet cap; bullet kills invader and scores; edge reversal and descent; bomb hit and game over; shield absorbs; wave clear -> level 2; invaders reach bottom; UFO shot; 90 s random-input soak.
- Beware: a test that runs "N seconds" must account for real speeds; compute from px/s instead of guessing.

## Web (single-file HTML) projects
One index.html with inline CSS/JS, `<canvas>` for games, requestAnimationFrame with dt, keyboard via keydown/keyup sets. Check with code_check (node --check on extracted JS if needed) and open_url("file:///path/index.html") for the user. Use Buddy's browser (web_open) to load it yourself and read the page for errors.

## Git (only when asked)
`git status`, `git diff` via code_run to review. Never push or force-push without the user's confirmation. Commit messages: imperative, one line + optional body.

## Pitfalls
- Editing code you haven't read. Giant single-file dumps (hit output limits: split into modules). Declaring success without running. Tests that only restate the implementation. Hard-coded absolute paths. Secrets in code. Infinite-loop programs run without a timeout.
