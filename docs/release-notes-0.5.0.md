Deep Study Center is a local study app. AI agents turn your books and goals into lessons, check what you know, and read your reasoning. It runs on your own machine. You choose which model provider does each job.

## Download

- **Windows:** `Deep.Study.Center_0.5.0_x64-setup.exe`. A per-user install; no admin rights needed.
- The installer is **not code-signed**. Windows SmartScreen warns on the first run: click "More info", then "Run anyway".
- SHA-256: `D859F0477B556FC07AAF55F1D1DDED4D7A37AEE5DAE321777EA3E35EB159D80D`
- **From 0.4.1:** the app offers this update by itself after the start. Click "Install and restart".
- **From 0.4.0:** install 0.5.0 once by hand. 0.4.0 has no updater.
- macOS and Linux: there is no installer yet. Run from source with `start.sh` (see the README).

## What is in 0.5.0

- **Lessons are planned before they are written.** Opening a new book lesson first makes its plan: a small graph from what you already hold to the lesson's idea, with the form of each step. Watch it being made, cut what you know, ask for another form, add notes, and approve. "Write it now without a plan" keeps the old way.
- **Step lessons.** An approved plan is taught one step at a time: a prediction first, then the step in its form (a short text, an example, a widget, a derivation), then "Check your understanding". A wrong check shows a short repair. "Explain differently" writes one step again with your note.
- **Interactive demos.** When no built-in widget can show a step, a small demo is built for it. It runs in a locked sandbox (no network, no access to the app) and is operated once, hidden, before you see it. A demo that fails is fixed once or left out.
- **Practice is back.** Pick what to practise: a book, a chapter, a lesson and its steps, a field of formulas, or your weakest ideas. Problems mix ideas and get harder step by step. Hints come one at a time. Missed problems come back at the end in a new form.
- **Formulas on the map.** Every formula from your lessons is in a "Formulas" country of its own, split into provinces by field of mathematics. A formula in 2 or 3 fields sits where they meet, in their colors; one in 4 or more is gray.
- **Territories** is the default map view. Country names are in a legend under the map, which can be collapsed.

Lessons written before 0.5.0 stay as they are. Only lessons opened for the first time are planned. Nothing is deleted.

The full history is in [docs/CHANGELOG.md](https://github.com/romank-foxcale/deep-study-center/blob/main/docs/CHANGELOG.md).

## Privacy

Your workspace (lessons, answers, PDFs) stays in a folder on your machine. Agent jobs send the needed text to the model provider that you choose in Settings. Dictation with Whisper runs locally. Demos run without network access. The update check asks GitHub for the newest release and sends no data about you.
