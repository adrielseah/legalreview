# ClauseLens

AI-powered legal clause risk reviewer.  
Upload a `.docx` or `.pdf` contract, and ClauseLens extracts every annotated clause, explains it in plain English, and assesses risk — all for free using Google Gemini.

---

## What you need installed once

| Tool | Minimum version | Download |
|------|----------------|---------|
| Node.js | 18+ | https://nodejs.org (LTS button) |
| Python | 3.11+ | https://www.python.org/downloads |

Verify after installing:
```bash
node -v        # should show v18 or higher
python3 --version  # should show 3.11 or higher
```

---

## Step 1 — Create a free Supabase account

1. Go to https://supabase.com and sign up (free, no credit card)
2. Click **"New project"** — give it any name, pick a region close to you, and set a strong database password (save it!)
3. Wait ~1 minute for it to provision

---

## Step 2 — Get your Supabase credentials

From your Supabase project dashboard:

**Session Pooler connection strings (for the database):**
→ Left sidebar → **Settings** → **Database** → scroll to **"Connection string"**
→ Select the **"Session pooler"** tab (not "Direct connection")
→ Copy the URI — it looks like:
```
postgresql://postgres.abcdefghijklmn:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

**Project URL and Service Role Key:**
→ Left sidebar → **Settings** → **API**
→ Copy the **Project URL** (e.g. `https://abcdefghijklmn.supabase.co`)
→ Copy the **`service_role`** key (click "Reveal" — keep this secret!)

---

## Step 3 — Get a free Google Gemini API key

ClauseLens uses Google Gemini for AI features — it's **free** with no credit card required.

1. Go to https://aistudio.google.com
2. Click **"Get API key"** → **"Create API key"**
3. Copy the key (starts with `AIza...`)

---

## Step 4 — Fill in your credentials

Open `apps/api/.env` in any text editor and replace the placeholder values:

```env
# ── Database (Supabase Session Pooler) ────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://postgres.YOUR_PROJECT_REF:[YOUR-PASSWORD]@aws-0-REGION.pooler.supabase.com:5432/postgres?prepared_statement_cache_size=0
SYNC_DATABASE_URL=postgresql://postgres.YOUR_PROJECT_REF:[YOUR-PASSWORD]@aws-0-REGION.pooler.supabase.com:5432/postgres

# ── Storage (Supabase) ────────────────────────────────────────────────────────
STORAGE_BACKEND=supabase
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY

# ── AI (Gemini — free tier, no credit card needed) ────────────────────────────
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
EXPLANATION_MODEL=gemini-2.5-flash-lite
DOCTYPE_MODEL=gemini-2.5-flash-lite
EMBEDDING_MODEL=text-embedding-004
EMBEDDING_DIM=768

# ── Admin (optional, for /admin/precedents page) ───────────────────────────────
ADMIN_API_KEY=your-long-random-secret
```

For the **admin precedents** page to work, also create `apps/web/.env` (or `.env.local`) with the same secret:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_ADMIN_API_KEY=your-long-random-secret
```

Use the same value as `ADMIN_API_KEY` above.

**Important:** If your database password contains special characters (e.g. `@`, `#`), URL-encode them in `DATABASE_URL` only:
- `@` → `%40`
- `#` → `%23`

Leave `SYNC_DATABASE_URL` with the plain password (psycopg2 handles it separately).

---

## Step 5 — Set up the database schema

1. In your Supabase project, click **"SQL Editor"** in the left sidebar
2. Click **"New query"**
3. Open the file `schema.sql` in this folder and paste **all** its contents into the editor
4. Click **"Run"**

You should see a success message. This only needs to be done once.

---

## Step 6 — First-time setup (run once)

Open a Terminal, navigate to this folder, and run:

```bash
./setup.sh
```

This installs all Node and Python dependencies. Takes 2–3 minutes.

If you get a permissions error:
```bash
chmod +x setup.sh start.sh
```

---

## Step 7 — Start the app

Every time you want to use ClauseLens:

```bash
./start.sh
```

Then open your browser to: **http://localhost:3000**

Press `Ctrl+C` to stop both servers.

---

## How it works

1. **Create a Vendor Case** — represents a contract counterparty
2. **Upload a document** — `.docx` or `.pdf` (up to 25 MB)
3. ClauseLens processes it through a 6-stage pipeline:
   - `downloading` → fetches from storage
   - `detecting` → identifies contract type (NDA, MSA, SaaS, etc.)
   - `parsing` → extracts all comments/annotations and their surrounding clause text
   - `expanding` → groups comments into clause cards
   - `embedding` → generates semantic vectors for similarity search
   - `storing` → saves to database
4. **Review** — browse extracted clauses, click "Explain" for a plain-English summary from Gemini
5. **Run history** — each reparse creates a new run; browse and compare past runs
6. **Export** — download results as JSON

---

## Development commands

```bash
make setup      # first-time install
make start      # start API + web together
make api        # start only the API (port 8000)
make web        # start only the web dev server (port 3000)
make test       # run Python unit tests
make lint       # lint Python with ruff
make e2e        # run Playwright end-to-end tests
make pip pkg=X  # install a new Python package and save to requirements.txt
make clean      # remove build artifacts
```

---

## Project structure

```
apps/
  api/          FastAPI backend (Python)
    app/
      routers/  API endpoints (vendors, documents, clauses, jobs, search, admin)
      parsers/  DOCX and PDF clause extractors
      services/ LLM, embeddings, storage
      workers/  Background task pipeline (tasks.py)
      db/       SQLAlchemy models and session
    .env        ← your credentials go here
    requirements.txt
  web/          Next.js frontend (TypeScript)
    app/        Pages (App Router)
    components/ Shared UI components
packages/
  shared/       Shared TypeScript types
schema.sql      Run this once in Supabase SQL Editor
setup.sh        First-time dependency installer
start.sh        Starts API + web dev server concurrently
```

---

## Troubleshooting

**"permission denied: ./setup.sh"**
→ Run: `chmod +x setup.sh start.sh`

**"python3: command not found"**
→ Install Python 3.11+ from https://www.python.org/downloads

**"node: command not found"**
→ Install Node.js 18+ from https://nodejs.org

**Setup fails with "Please fill in your Supabase credentials"**
→ Open `apps/api/.env` and replace all placeholder values (anything containing `YOUR_`)

**Database connection errors**
→ Make sure you're using the **Session Pooler** URL (not "Direct connection") from Supabase  
→ URL-encode any special characters in your password within `DATABASE_URL`  
→ Confirm the schema has been run in Supabase SQL Editor

**Gemini API errors**
→ Check your `GEMINI_API_KEY` in `apps/api/.env`  
→ Get a free key at https://aistudio.google.com  
→ To disable AI features temporarily: set `DISABLE_LLM=true` and `DISABLE_EMBEDDINGS=true`

**Document stuck in "Detecting" or never reaches "Done"**
→ Restart the API (`Ctrl+C` then `./start.sh`) — background tasks resume on next upload  
→ Use the **Reparse** button on the document review page to retry processing
