Deep Study Center is a local study app. AI agents turn your books and goals into lessons, check what you know, and read your reasoning. It runs on your own machine. You choose which model provider does each job.

## Download

- **Windows:** `Deep.Study.Center_0.6.0_x64-setup.exe`. A per-user install; no admin rights needed.
- The installer is **not code-signed**. Windows SmartScreen warns on the first run: click "More info", then "Run anyway".
- SHA-256: `45E6360EF3F89FADC65A25933B3C4861754A05383C36BCC2E42DA8B691A286EA`
- **From 0.4.1 or 0.5.0:** the app offers this update by itself after the start. Click "Install and restart".
- **From 0.4.0:** install 0.6.0 once by hand. 0.4.0 has no updater.
- macOS and Linux: there is no installer yet. Run from source with `start.sh` (see the README).

## What is in 0.6.0: one map of ideas

- **One lesson per idea.** When two books (or a book and an article or video) explain the same idea, you get one lesson, written from all of them. The tutor picks the clearest source for each step. The lesson lists its sources.
- **The hex map.** Your map is one hex per idea, from all your sources, with no book countries. Green is learned, blue-gray is started, dark is not explored. Point at a cell to see what it is; click it to see its sources and open its lesson.
- **Gaps.** Dashed, empty hexes show where an idea is missing between two of yours. Add it to your map, ask for more, or say it is not missing. "Find gaps" looks again.
- **Goals on the map.** Add a goal in one line ("a top-level AI/ML engineer, like Karpathy"). It becomes a star at an edge of your map, and every cell moves toward the goals it serves. Click a star for the direction, your progress, the next moves, and the building blocks not on your map yet. The old goal pages (Roadmap, This week, Probe) are removed.
- **The formula flow.** A formula's page shows where each part comes from, as boxes and arrows. Drag a value and watch it move through every formula; click a box to read what it is; try a "what if" form of a key part and see the real result next to yours. Normal lessons no longer show the formula widget; they link to the formula's page.
- **Teach from a link.** "Teach me this" on a web page or a YouTube video: the app reads the page's text or the video's captions and makes lessons from it.
- **Lesson steps on the map.** The steps a planned lesson teaches are ideas of their own on the map.
- **No schedule.** You study, and the map shows your progress. The review schedule, the "due" lists and the states "know strongly" and "due for review" are removed. A learned idea stays learned.

Nothing in your workspace is deleted. Lessons of one idea written before 0.6.0 stay as earlier versions. The old goals' data stays in your workspace.

Video captions need the package `youtube-transcript-api`, which this installer does not include yet: a video link shows a clear message; web pages work.

The full history is in [docs/CHANGELOG.md](https://github.com/romank-foxcale/deep-study-center/blob/main/docs/CHANGELOG.md).

## Privacy

Your workspace (lessons, answers, PDFs) stays in a folder on your machine. Agent jobs send the needed text to the model provider that you choose in Settings. Reading a link fetches that page once and sends no data about you. Dictation with Whisper runs locally. Demos run without network access. The update check asks GitHub for the newest release and sends no data about you.
