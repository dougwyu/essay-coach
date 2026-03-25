# Screenshot Quickstart

## 1. Start the server

```bash
python app.py
```

## 2. Seed demo data

In a second terminal:

```bash
python docs/seed_screenshots.py
```

The script prints your login URL, credentials, and the class analytics URL:

```
Log in at:        http://localhost:8000/login
Credentials:      demo_instructor / demo_password
Class analytics:  http://localhost:8000/instructor/classes/{class_id}/analytics
```

## 3. Capture screenshots

Follow the capture checklist in `docs/superpowers/plans/2026-03-25-screenshots.md`.

- Browser window: **1280×800**
- Save PNGs to `docs/images/`
- 14 screenshots total (9 new, 5 re-captures)
