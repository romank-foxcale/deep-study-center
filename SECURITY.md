# Security

Deep Study Center runs on your own computer and listens only on `127.0.0.1`. It has no login, so do not expose its
port to a network.

Please report a security problem privately: use GitHub's "Report a vulnerability" (Security tab of the repository),
not a public issue. Include the steps to reproduce it and the version or commit.

Known limits:

- The local Python runner for exercises is not a sandbox. You review each exercise's test code before it first runs;
  the Docker option adds isolation (see `backend/dsc/runner.py`).
- Agent jobs run the model CLIs you installed, with their own permissions and settings.
