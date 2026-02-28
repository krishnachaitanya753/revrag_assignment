# 🎙️ Revrag — Real-Time Voice Agent

A real-time voice agent built with **LiveKit Agents v1.x** that joins a LiveKit room, listens to the user, and echoes back *"You said: \<text\>"* — with zero overlap and automatic silence reminders.

---

## Task Breakdown

### ✅ Option B — STT → Response → TTS

- User speaks → **Deepgram Nova-3** transcribes speech to text
- Agent responds with `"You said: <text>"`
- **Cartesia Sonic-3** converts response to audio and publishes it back to the room

No LLM in the pipeline. `on_user_turn_completed()` handles the echo directly — keeping latency consistently under 300ms.

---

### ✅ A. No Overlap

> *"Never speak while the user is speaking. Stop speaking immediately if interrupted."*

**How it works:**

**Silero VAD** runs continuously on the incoming audio stream. `AgentSession` is configured with `allow_interruptions=True` (default in v1.x).

The moment VAD detects the user's voice while the agent is speaking:
1. The active `SpeechHandle` is cancelled immediately
2. TTS playback stops within one audio frame (~20ms)
3. Agent listens to the new utterance → STT → echo → TTS

```
User starts speaking mid-response
        │
        ▼
  Silero VAD detects voice energy
        │
        ▼
  AgentSession cancels TTS SpeechHandle
        │
        ▼
  Agent listens → STT → "You said: ..." → TTS
```

The agent and user are **never speaking simultaneously**.

---

### ✅ B. Silence Handling

> *"If no user speech for 20+ seconds, play a short reminder. Do not continuously publish or loop audio."*

**How it works:**

`_silence_watcher()` runs as a background coroutine, polling every 5 seconds.

- If no user speech detected for **20 seconds** → plays `"Still here, go ahead."`
- After the reminder plays, the clock **resets** — fires again after another 20s of continued silence
- The moment the user speaks, `on_user_turn_completed()` resets the clock naturally
- Audio is **never looped or continuously published** — `session.say()` only pushes audio when there is actual speech to send

```
t=0   User stops speaking
t=20  Reminder plays → clock resets
t=40  Reminder plays → clock resets
t=25* User speaks → clock resets naturally
```

---

## Project Structure

```
revrag_assignment/
├── agent.py           # All agent logic (single file)
├── pyproject.toml     # Project metadata and dependencies
├── .env               # Your credentials (not committed)
├── .env.example       # Credentials template
└── README.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/krishnachaitanya753/revrag_assignment.git
cd revrag_assignment
```

### 2. Create a virtual environment

```bash
uv venv
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Download Silero VAD model

```bash
uv run python agent.py download-files
```

### 5. Configure environment variables

```bash
cp .env.example .env
# Fill in your LiveKit credentials in .env
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LIVEKIT_URL` | ✅ | Your LiveKit server URL e.g. `wss://your-project.livekit.cloud` |
| `LIVEKIT_API_KEY` | ✅ | LiveKit project API key |
| `LIVEKIT_API_SECRET` | ✅ | LiveKit project API secret |

Get free credentials at [cloud.livekit.io](https://cloud.livekit.io).

> STT (Deepgram) and TTS (Cartesia) are accessed through LiveKit's plugin system via your LiveKit Cloud account — no separate API keys required.

---

## How to Run

```bash
uv run python agent.py start
```

Then open [agents-playground.livekit.io](https://agents-playground.livekit.io), enter your LiveKit URL, API key and secret, and connect. The agent joins the room, greets you as **Revrag**, and starts echoing.

> For local testing with console input:
> ```bash
> uv run python agent.py dev
> ```

---

## SDK & External Services

| Component | Provider | Free Tier |
|---|---|---|
| Agent framework | `livekit-agents` v1.x | ✅ |
| VAD | Silero (`livekit-plugins-silero`) — runs locally | ✅ |
|Noise| Cancellationlivekit-plugins-noise-cancellation — runs locally| ✅ |
| STT | Deepgram Nova-3 via LiveKit | ✅ |
| TTS | Cartesia Sonic-3 via LiveKit | ✅ |

---

## Known Limitations

- **Single participant** - targets the first participant to join, multiple participants are not independently handled in this setup
- **Silence polling precision** - reminder may fire up to 5s after the 20s threshold due to poll interval
- **Echo only** - no conversational LLM(current setup) and  doesn't store chat history either.
- **Network latency** - Since we’re hitting US-based AI servers from India, that 200ms–400ms round-trip "ping" makes the agent feel like it’s hesitating, even if the code is fast
- **TTS models** - most of the TTS models aren't good at indian native languages, newer models from indian startups are working well(latency issue is still a problem because of infra availability) so choose models wisely. 
- **STT models** - majority of these models aen't good at transcribing indian languages. Multimodal LLMS are good at but are costly.  
