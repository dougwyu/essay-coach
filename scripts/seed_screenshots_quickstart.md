# Screenshot Quickstart

## 1. Start the server

```bash
cd essay-coach
python app.py
```

## 2. Seed demo data (analytics pages)

In a second terminal, from the `essay-coach` directory:

```bash
python scripts/seed_screenshots.py
```

This creates a `demo_instructor / demo_password` account with a Biology 101 class
and pre-seeded student attempts, so the instructor analytics pages show realistic data.

## 3. Capture screenshots

From the `essay-coach` directory, with the server still running:

```bash
python docs/capture_screenshots.py
```

The script registers a fresh student account on each run (timestamp-suffixed username),
calls the AI for real feedback on two attempts, and saves all screenshots to `docs/images/`.

> **Note:** `capture_screenshots.py` depends on specific class and question UUIDs
> hardcoded at the top of the file. If the database is wiped and recreated, update
> `CLASS_ID`, `Q_CELLDIV`, `Q_PHOTOSYN`, `INST_CODE`, and `INVITE` to match the new values.
