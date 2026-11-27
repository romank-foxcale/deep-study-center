Deep Study Center is a local study app. AI agents turn your books and goals into lessons, check what you know, and read your reasoning. It runs on your own machine. You choose which model provider does each job.

## Download

New in 0.7.0: the app is also for macOS and Linux.

- **Windows:** `Deep.Study.Center_0.7.0_x64-setup.exe`. A per-user install; no admin rights needed. The installer is **not code-signed**: Windows SmartScreen warns on the first run. Click "More info", then "Run anyway".
- **macOS (11 or later):** `Deep.Study.Center_0.7.0_aarch64.dmg` for Apple Silicon (M1 and later), `Deep.Study.Center_0.7.0_x64.dmg` for Intel. Drag the app to Applications. The app is **not notarized by Apple**, so macOS stops the first start. Open System Settings → Privacy & Security and click "Open Anyway". Or run once in Terminal: `xattr -dr com.apple.quarantine "/Applications/Deep Study Center.app"`.
- **Linux (x86_64):** `Deep.Study.Center_0.7.0_amd64.AppImage` (make it executable and run it) or the `.deb` package.
- **From 0.4.1 or later (Windows):** the app offers this update by itself after the start. Click "Install and restart". The macOS and Linux apps also update themselves from 0.7.0 on.
- **From 0.4.0:** install 0.7.0 once by hand. 0.4.0 has no updater.
- The app uses the model CLIs that you installed (Claude Code, Codex or Cursor) or an API key. On macOS and Linux it also finds the CLIs when you open it from Finder or a desktop menu.

## What is in 0.7.0: teach first, and macOS and Linux

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
