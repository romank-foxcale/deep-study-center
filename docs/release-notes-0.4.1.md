Deep Study Center is a local study app. AI agents turn your books and goals into lessons, check what you know, and read your reasoning. It runs on your own machine. You choose which model provider does each job.

## Download

- **Windows:** `Deep.Study.Center_0.4.1_x64-setup.exe`. A per-user install; no admin rights needed.
- The installer is **not code-signed**. Windows SmartScreen warns on the first run: click "More info", then "Run anyway".
- SHA-256: `AEF048D9C7BE16FBD8074E825A3BA50EFBF674CD6F57FE2B0B1819BF99EA96DF`
- **From 0.4.0:** install 0.4.1 once by hand. 0.4.0 has no updater. From 0.4.1 on, the app finds new versions by itself.
- macOS and Linux: there is no installer yet. Run from source with `start.sh` (see the README).

## What is in 0.4.1

- **The app updates itself.** After the start, the app looks for a newer release and offers "Install and restart". Updates are signed; the app installs only an update with a correct signature. `DSC_NO_UPDATE_CHECK=1` turns the check off.
- **Sources.** One "Add source" dialog for a PDF or a link (web page or video), with a name, a type, upload progress and Cancel. The same file or link twice is refused. Types: Book, Article, Internet source, Video, Custom. Search and type filters on Sources and Books.
- **Books.** A trash can on every card. Links and "teach me" topics are on the shelf. Each book has one color, on its card and on the map.
- **Book lessons: one idea per lesson,** each built on what you already know. Books mapped before show "Re-plan lessons".
- **The formula tree is a derivation graph.** Each node shows its math. "What is it built from?" goes one level down. A formula page is made only when you ask for one. Formula pages look different and have no quiz.
- **Lessons.** Python edits survive a refresh. Board tasks state their inputs and the form of the answer. Cleaner formula hover cards.
- **Back** at the top of every page. The map's Tree view zooms with the mouse wheel.
- **Removed or on hold:** the book goal (80/20), the Anki export, the Graph, Nebula and Globe map views. Practice and goals are on hold.

At the first start, 0.4.1 changes old source types (`post` becomes Internet source, `other` becomes Custom) and adds a hash to each PDF for the duplicate check. Nothing is deleted.

The full history is in [docs/CHANGELOG.md](https://github.com/romank-foxcale/deep-study-center/blob/main/docs/CHANGELOG.md).

## Privacy

Your workspace (lessons, answers, PDFs) stays in a folder on your machine. Agent jobs send the needed text to the model provider that you choose in Settings. Dictation with Whisper runs locally. The update check asks GitHub for the newest release and sends no data about you.
