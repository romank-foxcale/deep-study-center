Deep Study Center is a local study app. AI agents turn your books and goals into lessons, check what you know, and read your reasoning. It runs on your own machine. You choose which model provider does each job.

## Download

- **Windows:** `Deep.Study.Center_0.7.0_x64-setup.exe`. A per-user install; no admin rights needed.
- The installer is **not code-signed**. Windows SmartScreen warns on the first run: click "More info", then "Run anyway".
- SHA-256: `SHA256_PENDING`
- **From 0.4.1 or later:** the app offers this update by itself after the start. Click "Install and restart".
- **From 0.4.0:** install 0.7.0 once by hand. 0.4.0 has no updater.
- macOS and Linux: there is no installer yet. Run from source with `start.sh` (see the README).

## What is in 0.7.0: teach first

- **"Teach me X" teaches first.** No question comes before a new idea. A new idea starts with a small worked example, then the rule, in short parts with "Continue", then "Your turn". When placement finds that you partly know an idea, you get one problem: solve it and move on, or get a short lesson on only the part you missed.
- **Faster.** The next placement question and the next idea are made while you work, so they show at once. The repair after a wrong check is also written ahead (about 2 s instead of about 16 s).
- **Placement** shows "Question n of at most 8", a bar, and "Show my plan now".
- **The plan is a graph.** Click a box to see it. "Learn it" and "Skip, I know it" work both ways. When two ideas are open, you pick which one comes first.
- **Map search** forgives one wrong letter ("hoffman" finds Huffman). It also finds the ideas of a book or a study session by its title, lists what it found, lights the matches and dims the rest. The map no longer opens empty before "Fit".
- **Book progress as a bar** on the shelf, with the percent.
- **Fix:** "Show my plan now" and then "Start" at once no longer stops with "the next step did not come".

Old code is removed (the week planner, the placement probe, the `dsc roadmap` command, and more). Nothing changes on the screen, and old workspaces keep their old data.

The full history is in [docs/CHANGELOG.md](https://github.com/romank-foxcale/deep-study-center/blob/main/docs/CHANGELOG.md).

## Privacy

Your workspace (lessons, answers, PDFs) stays in a folder on your machine. Agent jobs send the needed text to the model provider that you choose in Settings. Reading a link fetches that page once and sends no data about you. Dictation with Whisper runs locally. Demos run without network access. The update check asks GitHub for the newest release and sends no data about you.
