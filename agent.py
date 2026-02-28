"""
Revrag Voice Agent
==================
A real-time voice agent that:
  - Joins a LiveKit room
  - Listens to user speech via Deepgram STT (Nova-3)
  - Responds with "You said: <text>" via Cartesia TTS (Sonic-3)
  - Never speaks over the user (Silero VAD + interrupt handling)
  - Plays a reminder every 20s of continuous silence

HOW NO-OVERLAP WORKS:
  1. Silero VAD runs continuously on the incoming audio track.
  2. When VAD detects speech START:
     -> AgentSession immediately cancels any in-progress TTS playback
     -> Agent enters LISTENING state, publishes zero audio
  3. When VAD detects speech END:
     -> Audio is sent to Deepgram STT -> transcript produced
     -> on_user_turn_completed fires -> echo response generated
     -> Cartesia TTS converts response to audio -> published to room
  4. If user speaks mid-playback -> step 2 fires again (interrupt)
     -> Current TTS stops within one audio frame (~20ms)
  This guarantees the agent NEVER speaks while the user is speaking.

HOW SILENCE HANDLING WORKS:
  - _silence_watcher polls every POLL_INTERVAL seconds.
  - If elapsed >= SILENCE_TIMEOUT: play reminder, reset _last_speech_time.
  - Resetting the clock means the reminder fires again after ANOTHER 20s
    of continued silence - not just once total.
  - User speech always resets the clock via on_user_turn_completed.
  - Audio is never looped or continuously published.
"""

import asyncio
import logging
import time

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.plugins import silero

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("revrag-agent")

# -- Constants -----------------------------------------------------------------
SILENCE_TIMEOUT = 20   # seconds of silence before reminder fires
POLL_INTERVAL   = 5    # how often silence watcher checks (seconds)

# Short texts = faster TTS, avoids "flush audio emitter" warning in logs
GREETING_TEXT = "Hello! Say anything and I'll echo it back."
REMINDER_TEXT = "Still here, go ahead."


# -- Agent ---------------------------------------------------------------------
class EchoAgent(Agent):
    """
    Listens to the user and echoes their words back via TTS.
    No LLM is used - on_user_turn_completed handles the response directly,
    saving ~350ms of latency per turn vs. routing through an LLM.
    """

    def __init__(self):
        super().__init__(instructions="Echo agent - repeats what the user says.")
        self._last_speech_time: float = time.monotonic()
        self._silence_task: asyncio.Task | None = None

    # -- Lifecycle -------------------------------------------------------------

    async def on_enter(self):
        logger.info("EchoAgent entered the session.")
        await self.session.say(GREETING_TEXT, allow_interruptions=True)
        self._silence_task = asyncio.ensure_future(self._silence_watcher())

    async def on_exit(self):
        if self._silence_task:
            self._silence_task.cancel()

    # -- Echo logic (no LLM) --------------------------------------------------

    async def on_user_turn_completed(self, turn_ctx, new_message):
        """
        Called by AgentSession after STT produces a transcript.
        Bypasses LLM entirely - echo is built directly here.
        Pipeline: STT -> this function -> TTS  (no LLM hop = ~350ms saved)
        """
        text = (new_message.text_content or "").strip()
        self._last_speech_time = time.monotonic()  # reset silence timer

        if text:
            response = f"You said: {text}"
            logger.info("User: '%s' -> Agent: '%s'", text, response)
        else:
            response = "Sorry, I didn't catch that."
            logger.info("Empty transcript received.")

        await self.session.say(response, allow_interruptions=True)

    # -- Silence watcher -------------------------------------------------------

    async def _silence_watcher(self):
        """
        Polls every POLL_INTERVAL seconds.

        After playing the reminder, _last_speech_time is reset to now,
        starting a fresh 20s window. This means the reminder fires again
        after another 20s of continued silence.

        Timeline (continuous silence):
          t=0   User stops speaking
          t=20  Reminder plays -> clock resets
          t=40  Reminder plays -> clock resets
          t=60  Reminder plays -> ...

        Timeline (user speaks between reminders):
          t=0   User stops speaking
          t=20  Reminder plays -> clock resets
          t=25  User speaks -> on_user_turn_completed resets clock
          t=45  Reminder plays -> clock resets
        """
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed = time.monotonic() - self._last_speech_time

            if elapsed >= SILENCE_TIMEOUT:
                logger.info("%.0fs of silence - playing reminder.", elapsed)
                await self.session.say(REMINDER_TEXT, allow_interruptions=True)
                self._last_speech_time = time.monotonic()  # reset for next window


# -- Worker setup --------------------------------------------------------------

def prewarm(proc: JobProcess):
    """
    Runs once per worker process before jobs are assigned.
    Loads Silero VAD into memory to eliminate cold-start latency.
    """
    logger.info("Prewarming Silero VAD...")
    proc.userdata["vad"] = silero.VAD.load()
    logger.info("Silero VAD ready.")


async def entrypoint(ctx: JobContext):
    """Called for each incoming job (one LiveKit room = one job)."""
    logger.info("Connecting to room: %s", ctx.room.name)
    await ctx.connect()

    logger.info("Waiting for a participant to join...")
    participant = await ctx.wait_for_participant()
    logger.info("Participant connected: %s", participant.identity)

    session = AgentSession(
        stt="deepgram/nova-3:multi",
        tts="cartesia/sonic-3:9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
        vad=ctx.proc.userdata["vad"],
    )

    await session.start(
        agent=EchoAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(),
    )

    logger.info("Agent session running.")
    await asyncio.Event().wait()


# -- Entry ---------------------------------------------------------------------

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )