"""
Message buffer for merging consecutive messages from the same sender.

When a user sends multiple short messages within a time window (e.g. 4 seconds),
this buffer collects them and merges into a single text before processing.
This prevents the AI from responding to each fragment separately.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MERGE_WINDOW_SECONDS = 4.0


@dataclass
class BufferedSender:
    """Accumulates events from a single sender in a single chat."""
    sender_id: int
    chat_id: int
    events: List[Any] = field(default_factory=list)
    telegram_service: Any = None
    timer_task: Optional[asyncio.Task] = None


class MessageBuffer:
    """
    Buffers consecutive messages from the same sender within a time window.

    When the window expires, all buffered messages are resolved to text
    (voice transcribed, media marked, text passed through) and merged
    before calling the real handler.
    """

    def __init__(
        self,
        resolve_fn: Callable,
        handler_fn: Callable,
        window: float = MERGE_WINDOW_SECONDS,
    ):
        """
        Args:
            resolve_fn: async function(event, telegram_service) -> Optional[str]
                        Resolves a single event to text.
            handler_fn: async function(event, telegram_service, merged_text) -> None
                        The real message handler, called with merged text.
            window: seconds to wait for more messages before flushing.
        """
        self._resolve_fn = resolve_fn
        self._handler_fn = handler_fn
        self._window = window
        self._buffers: Dict[Tuple[int, int], BufferedSender] = {}
        self._lock = asyncio.Lock()

    async def on_message(self, event, telegram_service) -> None:
        """Called for every incoming message. Buffers and schedules processing."""
        sender_id = event.sender_id or event.chat_id
        chat_id = event.chat_id
        if not sender_id or not chat_id:
            # Can't buffer without IDs, skip (will be handled by main handler)
            return

        key = (sender_id, chat_id)

        async with self._lock:
            if key in self._buffers:
                buf = self._buffers[key]
                buf.events.append(event)
                # Cancel existing timer and reset
                if buf.timer_task and not buf.timer_task.done():
                    buf.timer_task.cancel()
                buf.timer_task = asyncio.create_task(self._flush_after_delay(key))
            else:
                buf = BufferedSender(
                    sender_id=sender_id,
                    chat_id=chat_id,
                    telegram_service=telegram_service,
                )
                buf.events.append(event)
                buf.timer_task = asyncio.create_task(self._flush_after_delay(key))
                self._buffers[key] = buf

    async def _flush_after_delay(self, key: Tuple[int, int]) -> None:
        """Wait for the merge window, then process all buffered messages."""
        await asyncio.sleep(self._window)

        async with self._lock:
            buf = self._buffers.pop(key, None)

        if not buf or not buf.events:
            return

        try:
            if len(buf.events) == 1:
                # Single message, no merging needed — resolve and process
                resolved = await self._resolve_fn(buf.events[0], buf.telegram_service)
                if resolved and resolved.strip():
                    await self._handler_fn(buf.events[0], buf.telegram_service, resolved)
            else:
                # Multiple messages — resolve each, merge, process
                logger.info(f"Merging {len(buf.events)} messages from sender {buf.sender_id}")
                texts = []
                for evt in buf.events:
                    resolved = await self._resolve_fn(evt, buf.telegram_service)
                    if resolved and resolved.strip():
                        texts.append(resolved)

                if texts:
                    merged_text = "\n".join(texts)
                    # Use first event as the base for metadata
                    await self._handler_fn(buf.events[0], buf.telegram_service, merged_text)
        except Exception as e:
            logger.error(f"Error processing buffered messages for {key}: {e}", exc_info=True)

    async def flush_all(self) -> None:
        """Flush all pending buffers immediately (for shutdown)."""
        async with self._lock:
            keys = list(self._buffers.keys())
            for key in keys:
                buf = self._buffers.pop(key, None)
                if buf and buf.timer_task and not buf.timer_task.done():
                    buf.timer_task.cancel()
