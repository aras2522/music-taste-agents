# Music Taste Agents

Hey, this is my music recommender. You tell it what you like (a vibe, a genre, or seed artists like Olivia Rodrigo or Bad Bunny) and it looks for similar artists with real albums.

It uses two agents. One digs through Pitchfork. The other digs through Rate Your Music. Then it merges what they find into one list.

## Stack

Django Python backend with MVC templates and a Django REST Framework API. React + Tailwind for the interactive UI. The Pitchfork and Rate Your Music engine lives in the Django app `backend/recommender/`.

Spring Boot is not in this repo because that is a Java framework and this backend is Django/Python.

## Project layout

```
frontend/                 React + Vite + Tailwind
backend/config/           Django project settings and URLs
backend/api/              REST API (views + serializer)
backend/web/              MVC templates
backend/recommender/      recommendation engine (agents, schemas, sources)
```

## Run it on your machine

### 1) Backend (Django)

```bash
cd ~/music-taste-agents
cp .env.example .env
uv sync
cd backend
uv run python manage.py migrate
uv run uvicorn config.asgi:application --reload --port 8787
```

Django MVC pages:
http://127.0.0.1:8787/
http://127.0.0.1:8787/about/

REST API:
http://127.0.0.1:8787/api/health
POST http://127.0.0.1:8787/api/recommend

### 2) Frontend (React + Tailwind)

In another terminal:

```bash
cd ~/music-taste-agents/frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173/app/

### Env

Gemini:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
OPENAI_MODEL=gemini-3.8-flash
```

Ollama:

```
LLM_PROVIDER=ollama
OPENAI_MODEL=llama3.2
```

## Docker

```bash
docker build -t music-taste-agents .

docker run --rm -p 8787:8787 \
  -e LLM_PROVIDER=gemini \
  -e GEMINI_API_KEY=your_key \
  -e OPENAI_MODEL=gemini-3.8-flash \
  music-taste-agents
```

Then open:
http://127.0.0.1:8787/ for the Django MVC home
http://127.0.0.1:8787/app/ for the React UI

Keep your `.env` private. Never commit API keys.
