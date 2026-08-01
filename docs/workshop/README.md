# Workshop deck

*Turning Vibes into Code — a masterclass on making agents write decent
code with predictable(ish) results.* ~45 min talk + 30 min hands-on,
built around this repo and [agent-code-intel](https://github.com/zmij/agent-code-intel),
with the [Lazy Sudoku](https://lazy-sudoku.online) codebase as the
reference deployment.

`slides.md` is a [Marp](https://marp.app) deck; the full speaker
narrative lives in the HTML comments after each slide and shows up in
Marp's presenter view (press `P` in the rendered deck).

## Rendering

```bash
npx -y @marp-team/marp-cli docs/workshop/slides.md -o slides.html  # browsable deck
npx -y @marp-team/marp-cli docs/workshop/slides.md --pdf           # handout
npx -y @marp-team/marp-cli docs/workshop/slides.md -p              # live preview
```

The design-rationale notes behind the talk are in
[../WORKSHOP.md](../WORKSHOP.md). Conference-template PPTX conversion
tooling lives in the reference deployment repo (it binds to a specific
branded template).
