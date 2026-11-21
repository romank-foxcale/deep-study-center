"""Entry point of the desktop app's bundled backend: the same `dsc` command line (the app runs `dsc-backend serve`)."""

import sys

from dsc.cli import main

if __name__ == "__main__":
    # The app sends output to a log file; write each line at once, so the log is complete when the app stops us.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(line_buffering=True)
    main()
