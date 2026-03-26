# Essay Coach — Deployment Design

**Date:** 2026-03-27
**Scope:** University department deployment (5–20 instructors, a few hundred students)
**Hosting:** University-managed Linux VM
**Maintenance:** Shared — developer owns app, IT owns infrastructure

---

## Approach

Docker Compose stack with Nginx reverse proxy and PostgreSQL. The LLM backend is switchable via environment variable between the Anthropic Claude API and a locally hosted Ollama model — allowing the university to start with the API and migrate to on-premises LLM hosting when/if GPU hardware is available.

---

## Responsibility Split

### IT owns
- Linux VM provisioning (Ubuntu 22.04 LTS recommended; min 4 vCPU / 8 GB RAM / 50 GB disk; more if running Ollama locally)
- Docker and Docker Compose installation
- Subdomain assignment and DNS configuration (e.g., `essaycoach.university.edu`)
- TLS certificate provisioning and renewal
- Firewall rules: ports 80 and 443 open to campus network; port 22 restricted to developer + IT admin IPs
- Outbound HTTPS whitelist to `api.anthropic.com:443` (required only if using Claude API backend)
- Nightly `pg_dump` backup of the PostgreSQL data volume to university backup storage
- VM-level monitoring and OS patching

### Developer owns
- `Dockerfile`, `docker-compose.yml`, `nginx.conf` in the repo
- App updates: `git pull && docker compose build app && docker compose up -d app`
- Database schema migrations
- Anthropic API key and PostgreSQL credentials (in `.env` on the server, never in the repo)
- App-level log monitoring: `docker compose logs app`
- LLM backend configuration

---

## Application Stack

### Containers

| Container | Purpose |
|-----------|---------|
| `app` | FastAPI + uvicorn, built from repo `Dockerfile` |
| `db` | PostgreSQL 16, data in a named Docker volume |
| `nginx` | Reverse proxy, TLS termination, serves static files directly |
| `ollama` | *(optional)* Local LLM server — only included if `LLM_BACKEND=ollama` |

### LLM Backend

Switchable via environment variables — no code changes required to swap backends:

```
LLM_BACKEND=anthropic          # Claude API (default)
LLM_BACKEND=ollama             # Local Ollama endpoint

OLLAMA_MODEL=llama3.3:70b      # Model to serve (if using Ollama)
OLLAMA_BASE_URL=http://ollama:11434
```

#### Candidate local LLMs (if Ollama path chosen)

| Model | Size | Quality | Hardware floor |
|-------|------|---------|----------------|
| Llama 3.3 70B (Meta) | 70B | Closest to Claude-class feedback | 2× A100 40GB GPU or ~96 GB RAM |
| Qwen 2.5 72B (Alibaba) | 72B | Excellent structured analysis | 2× A100 40GB GPU or ~96 GB RAM |
| Mistral Small 3.1 24B | 24B | Good quality, lighter hardware | 1× A100 40GB or 2× A40 |
| DeepSeek-R1 Distill 32B | 32B | Strong reasoning/structured feedback | 2× A40 |
| Phi-4 14B (Microsoft) | 14B | Viable on CPU for low traffic | 1× A40 or ~32 GB RAM |

**Note:** With the Anthropic API backend, student essay text is sent to Anthropic's servers. IT and legal must confirm FERPA compliance before go-live. With the Ollama backend, all data stays on campus.

### Database

- Production: PostgreSQL 16 (named Docker volume)
- Migration: one-time SQLite → PostgreSQL migration script run before go-live
- Backups: nightly `pg_dump` shipped to university storage by IT

### Secrets

All secrets live in a `.env` file on the server, outside the repo, mounted into the container at runtime:

```
ANTHROPIC_API_KEY=...
DATABASE_URL=postgresql://...
LLM_BACKEND=anthropic
```

---

## Networking & Security

- Nginx handles all inbound traffic on 443 (HTTPS) and 80 (redirect to HTTPS)
- The `app` container is not exposed to the host — traffic flows only through Nginx
- PostgreSQL port 5432 and Ollama port 11434 are internal to the Docker network only
- Per-IP rate limiting on `/feedback` endpoint (Nginx) to prevent runaway API costs or abuse
- SSH access restricted to developer + IT admin IPs via university firewall

---

## Go-Live Checklist

### Developer (pre-launch)
- [ ] Add `Dockerfile`, `docker-compose.yml`, `nginx.conf` to repo
- [ ] Add PostgreSQL driver support to `db.py`
- [ ] Add `LLM_BACKEND` switchable logic to `feedback.py`
- [ ] Write SQLite → PostgreSQL one-time migration script
- [ ] Create `.env.example` with all required variables documented
- [ ] Run full test suite against PostgreSQL locally

### IT (pre-launch)
- [ ] Provision Ubuntu 22.04 VM (see specs above)
- [ ] Install Docker and Docker Compose
- [ ] Assign subdomain and configure DNS
- [ ] Obtain and install TLS certificate
- [ ] Configure firewall rules
- [ ] Whitelist `api.anthropic.com:443` outbound (if using Claude API)
- [ ] Set up nightly `pg_dump` backup
- [ ] Confirm FERPA/data privacy sign-off

### Go-live (developer + IT)
- [ ] Developer SSH in, clone repo, create `.env` from `.env.example`
- [ ] `docker compose up -d`
- [ ] Verify app at `https://essaycoach.university.edu`
- [ ] Register first instructor account via invite code in logs
- [ ] Smoke test: create class, submit answer, confirm feedback returns

---

## Ongoing Maintenance

| Task | Owner | How |
|------|-------|-----|
| App updates | Developer | `git pull && docker compose build app && docker compose up -d app` |
| OS/Docker patching | IT | Standard university patch schedule; coordinate with developer for downtime |
| Database backups | IT | Nightly `pg_dump`; monthly restore drill |
| API key rotation | Developer | Update `.env`, `docker compose up -d app` |
| Log review | Developer | `docker compose logs app` |
| Nginx access logs | IT | Standard log monitoring for abuse patterns |

---

## IT Information Needed

The following must be confirmed with IT before deployment proceeds:

1. **VM specifications** — Available CPU, RAM, disk, and GPU (if Ollama path is chosen)
2. **Subdomain** — Assigned hostname (e.g., `essaycoach.university.edu`)
3. **TLS certificate** — University-issued cert or permission to use Let's Encrypt
4. **Firewall policy** — Confirmation that ports 80/443 can be opened and `api.anthropic.com` can be whitelisted outbound
5. **FERPA / data privacy** — Sign-off on student essay text being sent to Anthropic API, OR decision to use local Ollama instead
6. **Backup infrastructure** — Where `pg_dump` output should be shipped and retention policy
7. **Access policy** — Who gets SSH access; how developer SSH keys are provisioned
8. **Planned maintenance windows** — When OS patching and restarts can be scheduled

---

## IT Kickoff Email

See `docs/it-kickoff-email.md`.
