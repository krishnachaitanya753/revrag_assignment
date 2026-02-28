# 🎙️ Revrag Voice Agent

A real-time voice agent built with LiveKit that joins a room, listens to you, and echoes back **"You said: <text>"** — with zero overlap and automatic silence reminders.

---

## Setup

```bash
git clone <your-repo-url>
cd revrag-voice-agent

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
python agent.py download-files  # downloads Silero VAD model

cp .env.example .env            # fill in your credentials
```

## Environment Variables

| Variable | Description |
|---|---|
| `LIVEKIT_URL` | `wss://your-project.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit API key |
| `LIVEKIT_API_SECRET` | LiveKit API secret |
| `DEEPGRAM_API_KEY` | Deepgram API key (STT) |
| `CARTESIA_API_KEY` | Cartesia API key (TTS) |

## Run

```bash
python agent.py start
```

Test at [agents-playground.livekit.io](https://agents-playground.livekit.io) with your LiveKit credentials.

---

## How It Works

**STT → Echo → TTS** — no LLM in the loop. Deepgram transcribes speech, the agent builds `"You said: <text>"` directly, Cartesia speaks it back. Keeps latency consistently under 300ms.

**No Overlap** — Silero VAD runs continuously on incoming audio. The moment you speak, `AgentSession` cancels any active TTS playback within ~20ms. The agent never speaks over you.

**Silence Reminder** — a background watcher polls every 5s. If no speech is detected for 20s, the agent says *"Still here, go ahead."* The reminder repeats every 20s of continued silence and resets the moment you speak.

---

## SDK & Services

| | |
|---|---|
| Framework | `livekit-agents` v1.x |
| VAD | Silero — runs locally, free |
| STT | Deepgram Nova-3 |
| TTS | Cartesia Sonic-3 |

## Known Limitations

- Targets the first participant to join; multi-participant rooms not handled
- Silence reminder may fire up to 5s after the 20s threshold (poll interval)
- No conversation history — each utterance is independent