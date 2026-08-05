# Music Taste Agents

Hey, this is my music recommender. You tell it what you like (a vibe, a genre, or seed artists like Olivia Rodrigo or Bad Bunny) and it looks for similar artists with real albums.

It uses two agents. One digs through Pitchfork. The other digs through Rate Your Music. Then it merges what they find into one list. Bandcamp is out because those picks were not great.

You can ask for up to 9 albums. If it cannot fill that many it will just say sorry and show what it found.

## Run it on your machine

Copy the example env file:

```bash
cd ~/music-taste-agents
cp .env.example .env
```

### With Gemini

Get a key from Google AI Studio, put it in `.env` like this:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
OPENAI_MODEL=gemini-2.0-flash
```

Then:

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8787
```

### With Ollama (fully local, no cloud key)

```bash
ollama pull llama3.2
```

In `.env`:

```
LLM_PROVIDER=ollama
OPENAI_MODEL=llama3.2
```

Open http://127.0.0.1:8787 in your browser.

## Docker

Do not put secrets in the image. Pass them when you run it.

```bash
docker build -t music-taste-agents .

docker run --rm -p 8787:8787 \
  -e LLM_PROVIDER=gemini \
  -e GEMINI_API_KEY=your_key \
  -e OPENAI_MODEL=gemini-2.0-flash \
  music-taste-agents
```

Then open http://127.0.0.1:8787

If you host this somewhere later, set the same env vars as secrets and start with:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## How it works

You hit `POST /api/recommend` with your taste, optional seed artists, and a limit. Pitchfork and Rate Your Music run in parallel. The app merges their picks and prefers artists that show up in more than one place.

Keep your `.env` private. Never commit API keys.
