"""
SignalR Listener Service
Connects to C# OPC backend and receives real-time tag updates.

Production hardening (May 2026):
  - Single watchdog thread (guarded by is_alive check)           [item 1]
  - threading.Lock() around all connection state mutations        [item 2]
  - Heartbeat-timeout detection (silence → force reconnect)      [item 3]
  - Clean connection teardown on every reconnect                  [item 4]
  - Structured logging with retry/backoff/state context           [item 6]
  - Long-disconnect alarm after ALARM_DISCONNECT_SECS (5 min)    [item 7]
"""
import logging
import time
import threading
from signalrcore.hub_connection_builder import HubConnectionBuilder

logger = logging.getLogger(__name__)

# ── Back-off schedule (seconds). Last value repeats forever — never gives up.
_RECONNECT_BACKOFF = [2, 5, 10, 30, 60]

# ── If no TagValuesUpdated message arrives for this many seconds the TCP
#    socket is assumed silently dead; watchdog forces a full reconnect.
HEARTBEAT_TIMEOUT_SECS = 30

# ── After this many seconds of total disconnect, raise an ERROR-level alarm.
ALARM_DISCONNECT_SECS = 300   # 5 minutes


class SignalRListener:
    """
    Manages a persistent, self-healing SignalR connection to the C# OPC backend.

    Thread-safety
    -------------
    All mutations of self.connection / self.is_connected are made with
    self._conn_lock held.  Callbacks, watchdog, and stop() never race.

    Recovery layers
    ---------------
    1. signalrcore internal auto-reconnect  (fast: 0/2/5/10/30/60 s)
    2. Watchdog outer loop                  (rebuilds full connection object)
    3. Heartbeat-timeout check              (detects silent dead TCP)
    """

    def __init__(self, signalr_config: dict, tag_cache, on_update_callback):
        self.host      = signalr_config['host']
        self.port      = signalr_config['port']
        self.hub_path  = signalr_config['hub_path']
        self.hub_url   = f"http://{self.host}:{self.port}{self.hub_path}"
        self.tag_cache = tag_cache
        self.on_update_callback = on_update_callback

        # ── Connection state (always mutate under _conn_lock) ─────────────
        self._conn_lock   = threading.Lock()
        self.connection   = None
        self.is_connected = False

        # ── Control ───────────────────────────────────────────────────────
        self._stop_event      = threading.Event()
        self._watchdog_thread = None

        # ── Heartbeat / alarm tracking ────────────────────────────────────
        self._last_message_time   = time.monotonic()
        self._disconnected_since: float | None = None   # monotonic ts

        # ── Batching ──────────────────────────────────────────────────────
        self.update_buffer   = []
        self.buffer_lock     = threading.Lock()
        self.batch_interval  = 0.2      # 200 ms window
        self.last_batch_time = time.time()

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    def connect(self):
        """Start connection + infinite watchdog.  Idempotent — safe to call repeatedly."""
        self._stop_event.clear()
        self._build_and_start()

        # ── Item 1: Prevent duplicate watchdog threads ────────────────────
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            logger.debug("[SignalR] Watchdog already alive — skipping duplicate start")
            return

        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name='SignalR-Watchdog'
        )
        self._watchdog_thread.start()
        logger.info("[SignalR] Watchdog thread started")

    def stop(self):
        """Gracefully stop watchdog and close the connection."""
        logger.info("[SignalR] Stopping listener…")
        self._stop_event.set()
        with self._conn_lock:               # ── Item 2: connection lock
            self._teardown_connection()
        logger.info("[SignalR] Listener stopped")

    # ─────────────────────────────────────────────────────────────────────
    # Internal: connection lifecycle (all use _conn_lock)
    # ─────────────────────────────────────────────────────────────────────

    def _teardown_connection(self):
        """
        Destroy the current HubConnection cleanly.
        MUST be called with self._conn_lock already held.
        This ensures subscriptions are removed with the object (Item 4).
        """
        if self.connection is not None:
            try:
                self.connection.stop()
            except Exception as exc:
                logger.debug("[SignalR] Teardown error (ignored): %s", exc)
            self.connection = None      # drop reference → old subscriptions GC'd
        self.is_connected = False

    def _build_and_start(self):
        """
        Tear down previous connection, build a fresh HubConnection, start it.
        Thread-safe: acquires _conn_lock.
        """
        with self._conn_lock:           # ── Item 2: connection lock
            logger.info(
                "[SignalR] Building new HubConnection",
                extra={"hub": self.hub_url, "state": "building"},
            )
            self._teardown_connection()  # ── Item 4: clean subscription lifecycle

            try:
                conn = HubConnectionBuilder() \
                    .with_url(self.hub_url) \
                    .configure_logging(logging.WARNING) \
                    .with_automatic_reconnect({
                        "type": "interval",
                        "keep_alive_interval": 10,
                        "intervals": [0, 2, 5, 10, 30, 60],
                    }) \
                    .build()

                # Register events on fresh object — no duplicate handlers possible
                conn.on("TagValuesUpdated", self._on_tag_values_updated)
                conn.on_open(self._on_connected)
                conn.on_close(self._on_disconnected)
                conn.on_error(self._on_error)

                conn.start()
                self.connection = conn
                logger.info("[SignalR] HubConnection.start() called — awaiting on_open")

            except Exception as exc:
                logger.error(
                    "[SignalR] Failed to build/start HubConnection: %s",
                    exc,
                    extra={"hub": self.hub_url, "state": "build_failed"},
                    exc_info=True,
                )
                self.is_connected = False

    # ─────────────────────────────────────────────────────────────────────
    # Watchdog loop (Item 1 + 3 + 6 + 7)
    # ─────────────────────────────────────────────────────────────────────

    def _watchdog_loop(self):
        """
        Runs forever in a daemon thread.
        Each cycle:
          1. Check heartbeat timeout  → force-reconnect if silent
          2. Check is_connected       → rebuild if still down
          3. Check disconnect-alarm   → ERROR after ALARM_DISCONNECT_SECS
        """
        attempt = 0
        while not self._stop_event.is_set():
            delay = _RECONNECT_BACKOFF[min(attempt, len(_RECONNECT_BACKOFF) - 1)]
            self._stop_event.wait(delay)
            if self._stop_event.is_set():
                break

            # ── Item 3: Heartbeat timeout ─────────────────────────────────
            with self._conn_lock:
                currently_connected = self.is_connected

            if currently_connected:
                silence = time.monotonic() - self._last_message_time
                if silence > HEARTBEAT_TIMEOUT_SECS:
                    logger.warning(
                        "[SignalR] Heartbeat timeout — no data for %.0f s "
                        "(threshold=%d s). Forcing reconnect.",
                        silence, HEARTBEAT_TIMEOUT_SECS,
                        extra={
                            "state": "heartbeat_timeout",
                            "silence_secs": int(silence),
                            "threshold_secs": HEARTBEAT_TIMEOUT_SECS,
                        },
                    )
                    with self._conn_lock:
                        self.is_connected = False
                    currently_connected = False

            # ── Reconnect if needed ───────────────────────────────────────
            if not currently_connected:
                attempt += 1
                next_delay = _RECONNECT_BACKOFF[min(attempt, len(_RECONNECT_BACKOFF) - 1)]

                # ── Item 6: Structured reconnect log ─────────────────────
                logger.warning(
                    "[SignalR] Reconnect attempt #%d | backoff=%ds | next=%ds",
                    attempt, delay, next_delay,
                    extra={
                        "state": "reconnecting",
                        "retry": attempt,
                        "backoff_used": delay,
                        "next_backoff": next_delay,
                        "hub": self.hub_url,
                    },
                )

                # ── Item 7: Long-disconnect alarm ─────────────────────────
                now_mono = time.monotonic()
                if self._disconnected_since is None:
                    self._disconnected_since = now_mono
                else:
                    down_secs = now_mono - self._disconnected_since
                    if down_secs >= ALARM_DISCONNECT_SECS:
                        logger.error(
                            "[SignalR] ⚠️  BACKEND UNREACHABLE for %.0f s — "
                            "OPC data is FROZEN. Verify C# service on port %s.",
                            down_secs, self.port,
                            extra={
                                "state": "alarm_disconnected",
                                "disconnected_for_secs": int(down_secs),
                                "hub": self.hub_url,
                            },
                        )

                self._build_and_start()

            else:
                # Connection healthy — reset counters
                if attempt > 0:
                    logger.info(
                        "[SignalR] Connection healthy — watchdog counters reset "
                        "(was at attempt #%d)",
                        attempt,
                        extra={"state": "connected", "retry_reset_from": attempt},
                    )
                attempt = 0
                self._disconnected_since = None

    # ─────────────────────────────────────────────────────────────────────
    # SignalR callbacks (Item 2: state mutations under lock)
    # ─────────────────────────────────────────────────────────────────────

    def _on_connected(self):
        with self._conn_lock:
            self.is_connected = True
        self._last_message_time = time.monotonic()
        logger.info(
            "[SignalR] ✅ OPC Backend connected — %s",
            self.hub_url,
            extra={"state": "connected", "hub": self.hub_url},
        )
        threading.Thread(
            target=self._subscribe_to_tags, daemon=True, name='SignalR-Subscribe'
        ).start()

    def _on_disconnected(self):
        with self._conn_lock:
            self.is_connected = False
        logger.warning(
            "[SignalR] ⚠️  OPC Backend disconnected — %s",
            self.hub_url,
            extra={"state": "disconnected", "hub": self.hub_url},
        )

    def _on_error(self, error):
        logger.error(
            "[SignalR] ❌ Connection error: %s",
            error,
            extra={"state": "error", "hub": self.hub_url},
        )

    # ─────────────────────────────────────────────────────────────────────
    # Tag subscription (Item 4: uses snapshot of connection at call time)
    # ─────────────────────────────────────────────────────────────────────

    def _subscribe_to_tags(self):
        """Send SubscribeToTags after connection opens.  Runs in its own thread."""
        time.sleep(2)   # let tag cache finish loading
        with self._conn_lock:
            conn = self.connection      # snapshot — safe to use outside lock

        if conn is None:
            logger.warning("[SignalR] Cannot subscribe — connection already gone")
            return

        try:
            tag_ids = list(self.tag_cache.get_tag_ids())
            if not tag_ids:
                logger.warning("[SignalR] Tag cache empty, retrying in 2 s…")
                time.sleep(2)
                tag_ids = list(self.tag_cache.get_tag_ids())

            if tag_ids:
                conn.send("SubscribeToTags", [tag_ids])
                logger.info(
                    "[SignalR] ✅ Subscribed to %d tags (sample: %s)",
                    len(tag_ids), tag_ids[:5],
                    extra={"tag_count": len(tag_ids), "state": "subscribed"},
                )
            else:
                logger.error(
                    "[SignalR] No tags in cache after retry — check DB / tag_master.",
                    extra={"state": "subscription_failed"},
                )
        except Exception as exc:
            logger.error("[SignalR] SubscribeToTags failed: %s", exc, exc_info=True)

    # ─────────────────────────────────────────────────────────────────────
    # Data handler (Item 3: resets heartbeat timer)
    # ─────────────────────────────────────────────────────────────────────

    def _on_tag_values_updated(self, data):
        """Handle TagValuesUpdated from C# backend. Resets heartbeat, batches callback."""
        # ── Item 3: reset heartbeat on every real message ─────────────────
        self._last_message_time = time.monotonic()

        try:
            # signalrcore sometimes wraps payload as [[tag, tag]] — unwrap
            if isinstance(data, list) and data and isinstance(data[0], list):
                tags_data = data[0]
            elif isinstance(data, list):
                tags_data = data
            else:
                return

            with self.buffer_lock:
                self.update_buffer.extend(tags_data)
                current_time = time.time()
                if current_time - self.last_batch_time >= self.batch_interval:
                    if self.update_buffer:
                        batch = self.update_buffer.copy()
                        self.update_buffer.clear()
                        self.last_batch_time = current_time
                        threading.Thread(
                            target=self.on_update_callback,
                            args=(batch,),
                            daemon=True,
                        ).start()

        except Exception as exc:
            logger.error("[SignalR] Error in _on_tag_values_updated: %s", exc, exc_info=True)
