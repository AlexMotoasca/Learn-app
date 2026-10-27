# Uplearn

A work-in-progress learning app for Romanian high-school biology. The project combines a React frontend with a Flask API for accounts, AI-generated quizzes, learning progress, and a lesson-aware chatbot powered by a local Ollama model.

## Current status

- **Backend:** registration, JWT login, profile updates, quiz generation, quiz submission, scores, streaks, and module progress are implemented.
- **Learning content:** eight Romanian biology modules are included in `backend/Lessons/biologie/`.
- **Frontend:** the entry point renders the registration form. Submission is simulated; the login and registration components still need API integration. `App.jsx` contains the unused Vite starter screen.
- **Chatbot UI:** `backend/frontend/src/components/Chatbot.jsx` is an empty placeholder. Use the API directly for now.

## Stack

React 19, Vite 7, Flask, SQLAlchemy, Flask-JWT-Extended, SQLite (default) or PostgreSQL, Ollama, Sentence Transformers, and FAISS.

## Repository layout

```text
Learn-app/
├── backend/
│   ├── app.py                 # App factory, routes, and development server
│   ├── config.py              # Environment-based configuration
│   ├── extensions.py          # Database and JWT extensions
│   ├── models/                # User, subject, and topic models
│   ├── routes/                # Authentication, quizzes, and chatbot
│   ├── utils/ollama_client.py  # Local model HTTP client
│   ├── Lessons/biologie/      # Biology modules 1–8
│   ├── storage/               # FAISS index and chunk metadata
│   ├── tools/                 # Lesson conversion and indexing scripts
│   └── tests/test_routes.py   # Empty test placeholder
└── learn-app/
    ├── src/main.jsx           # Renders the registration form
    ├── src/LoginRegister/     # Login and registration components
    └── package.json           # Frontend commands and dependencies
```

## Local setup

Run the backend and frontend in separate terminals. The commands below use PowerShell, starting from the repository root.

### Prerequisites

- Node.js compatible with Vite 7 (20.19+ or 22.12+) and npm.
- Python 3.12+; `config.py` uses f-string syntax requiring Python 3.12 or newer.
- Ollama with a downloaded generation model.
- Internet access on first use to download the Sentence Transformers embedding model.
- PostgreSQL only if you choose it instead of SQLite.

### 1. Install backend dependencies

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install python-dotenv numpy faiss-cpu sentence-transformers
```

The second install command supplies packages imported by the backend but currently missing from `requirements.txt`. These additional dependencies are not pinned.

### 2. Configure the backend

Create or edit `backend/.env` with local values:

```dotenv
SECRET_KEY=replace-with-a-random-development-secret
JWT_SECRET_KEY=replace-with-a-different-random-secret
OLLAMA_MODEL=qwen2.5:14b
OLLAMA_URL=http://127.0.0.1:11434/api/generate
OLLAMA_TIMEOUT=30
```

`qwen2.5:14b` is an example model selection; choose a model your machine can run and use the same name in Ollama and `.env`.

| Variable | Behavior |
| --- | --- |
| `SECRET_KEY` | Flask secret; the code has a development fallback. |
| `JWT_SECRET_KEY` | Token-signing secret; the code has a development fallback. |
| `DATABASE_URL` | Optional SQLAlchemy URL. If unset, uses `backend/uplearn.db`. For PostgreSQL, use `postgresql://USER:PASSWORD@localhost:5432/uplearn` with an existing database. |
| `OLLAMA_MODEL` | Required for generation; there is no model fallback in the configuration. |
| `OLLAMA_URL` | Defaults to the local Ollama `/api/generate` endpoint above. |
| `OLLAMA_TIMEOUT` | Parsed by configuration, but the HTTP client currently uses a fixed 300-second timeout. |
| `OPENAI_API_KEY` | Read by configuration; the current generation routes use Ollama. |

The repository currently tracks `backend/.env`. Keep real credentials out of version control and replace any exposed credentials before using them elsewhere.

### 3. Start Ollama and the API

With Ollama installed and running:

```powershell
ollama pull qwen2.5:14b
```

From `backend/`:

```powershell
.\.venv\Scripts\python.exe app.py
```

The development API listens at `http://127.0.0.1:5000`. Running `app.py` creates missing database tables. It does not migrate existing tables.

Start the API from **inside `backend/`**: lesson and index paths are relative to the working directory. Quiz routes load the embedding model and FAISS index during application startup, so those dependencies and files are required even when only using authentication.

Check the server from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/
```

Expected response: `{"message":"Uplearn API is running"}`.

### 4. Start the frontend

From the repository root, in a separate terminal:

```powershell
cd learn-app
npm ci
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. The current registration form does not send requests to Flask. There is no frontend API URL setting or Vite API proxy configured yet.

## API reference

All paths below are relative to `http://127.0.0.1:5000`. Send JSON request bodies with `Content-Type: application/json`. Protected routes require `Authorization: Bearer <access_token>`.

| Method | Path | JWT | Input / purpose |
| --- | --- | --- | --- |
| GET | `/` | No | API status message. |
| POST | `/auth/register` | No | `username`, `email`, `password`. |
| POST | `/auth/login` | No | `username` or `email`, plus `password`; returns `access_token` and user data. |
| GET | `/auth/profile` | Yes | Profile, score, streaks, and module lists. |
| POST | `/auth/profile` | Yes | Update username, email, password, total score, or module lists. |
| GET | `/api/quiz/biolaureat` | No | Header `X-Module: 1`; generates five questions from that module. |
| POST | `/api/quiz/generate_text` | No | `text`; generates questions from supplied lesson text. |
| POST | `/api/quiz/debug_model` | No | `prompt`; returns raw model output. |
| GET | `/api/quiz/daily` | Yes | Optional `module` (a number, comma-separated numbers, or `all`) and `count` (default 5). |
| POST | `/api/quiz/submit` | Yes | Submit `questions_correct`, `questions_total`, and optional `module`; alternatively accepts `score` and `max_score`. |
| POST | `/api/chatbot/respond` | Yes | `prompt`, optional `module`, `history`, and `max_context_chars`. Returns `reply`. |

Generated questions include `question`, `options`, `correct_index` (zero-based), `explanation`, and `source_sentence`. Generation depends on the model returning the expected JSON format.

Quiz submission adds points and updates daily streaks. A module is marked complete at a score of at least 70%. The daily quiz defaults to modules in the user's in-progress or completed lists. The chatbot requires at least one such module and restricts explicit module selections to those lists.

### Example: create an account and generate a daily quiz

```powershell
$baseUrl = 'http://127.0.0.1:5000'
$registration = @{
    username = 'student'
    email = 'student@example.com'
    password = 'replace-with-your-local-password'
} | ConvertTo-Json
Invoke-RestMethod "$baseUrl/auth/register" -Method Post -ContentType 'application/json' -Body $registration

$credentials = @{ username = 'student'; password = 'replace-with-your-local-password' } | ConvertTo-Json
$login = Invoke-RestMethod "$baseUrl/auth/login" -Method Post -ContentType 'application/json' -Body $credentials
$headers = @{ Authorization = "Bearer $($login.access_token)" }

$progress = @{ modules_in_progress = @(1) } | ConvertTo-Json
Invoke-RestMethod "$baseUrl/auth/profile" -Method Post -Headers $headers -ContentType 'application/json' -Body $progress
Invoke-RestMethod "$baseUrl/api/quiz/daily?module=1&count=5" -Headers $headers
```

## Lesson maintenance

Run these commands from `backend/`, using its virtual environment.

Rebuild the retrieval index after changing module text:

```powershell
.\.venv\Scripts\python.exe tools/index_modules.py
```

This overwrites `storage/index.faiss` and `storage/meta.json`, using `paraphrase-multilingual-MiniLM-L12-v2` embeddings. Restart the API afterward to load the rebuilt files.

Convert a DOCX lesson to UTF-8 text:

```powershell
.\.venv\Scripts\python.exe tools/docx_to_txt_improved.py "C:\path\lesson.docx" "Lessons\lesson.txt"
```

The converter first tries built-in ZIP/XML extraction. Optional fallbacks require `docx2txt`, `mammoth`, or `python-docx`.

`tools/reflow_text.py` is an experimental text-formatting utility; its heading regex currently uses a variable-width lookbehind that Python's standard `re` does not support.

## Development checks

From `learn-app/`:

```powershell
npm run lint
npm run build
npm run preview
```

`build` writes the frontend to `learn-app/dist/`; `preview` serves that build locally. There is no frontend test script, and `backend/tests/test_routes.py` is empty, so the repository does not yet provide an automated backend test suite.

## Known limitations

- The frontend and backend are not connected end to end.
- The Python requirements file omits dependencies listed in the setup instructions above.
- Existing database schemas need manual migration; no migration tooling is included.
- Quiz answers and scores are trusted from the client, and profile updates allow direct score changes. Progress is not protected against manipulation.
- Input validation and error handling need more work before deployment. The Flask entry point enables debug mode, CORS is unrestricted, and model debug endpoints are public.
- Daily quiz generation can be slow because explanations trigger additional model calls per question.

