Deep Study Center is a local study app. AI agents turn your books and goals into lessons, check what you know, and read your reasoning. It runs on your own machine. You choose which model provider does each job.

## Download

- **Windows:** `Deep Study Center_0.4.0_x64-setup.exe`. A per-user install; no admin rights needed.
- The installer is **not code-signed**. Windows SmartScreen warns on the first run: click "More info", then "Run anyway".
- SHA-256: `F9B28AF89615965D062E05EC7A579C22D56639F91D54DDE754476B5F17C73D0F`
- macOS and Linux: there is no installer yet. Run from source with `start.sh` (see the README).

## What is in 0.4.0

- **Teach me this book.** A PDF becomes chapters of lessons by topic. Lessons are written from the book's pages when you open them, with idea links, a quiz, and a drawing board that the grader reads.
- **The tutor reads your reasoning.** It marks each part of your thinking as right or wrong, names the wrong assumption, follows it until it breaks, and then derives how it really works. This works in checks, study sessions and explain-backs.
- **Formulas.** Hover a formula to see what it means and where you met it. Formula lessons have interactive widgets. Frames show what you know: green (learned), orange (learned in another form), gray (new). Your preferred form is used in every lesson. 3D surfaces show gradient descent, momentum, RMSProp and Adam.
- **Building blocks.** A formula lesson is built from the bottom up: notations, simpler formulas, ideas. "Learn these first" makes the blocks you miss. One topic is one shared block across books. "Next" picks a lesson whose parts you already hold. The whole formula tree is on one page.
- **Knowledge map, study sessions, recall practice, local dictation (Whisper)** and the new design: Today, Books, Learn, Practice, Map.

The full history is in [docs/CHANGELOG.md](https://github.com/romank-foxcale/deep-study-center/blob/main/docs/CHANGELOG.md).

## Privacy

Your workspace (lessons, answers, PDFs) stays in a folder on your machine. Agent jobs send the needed text to the model provider that you choose in Settings. Dictation with Whisper runs locally.
