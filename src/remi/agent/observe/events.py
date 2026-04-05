"""Structured log event name constants.

A single namespace for all event name strings used with structlog across
the system. Centralising names makes them discoverable, greppable, and
stable across refactors.
"""

from __future__ import annotations


class Event:
    """Namespace for all structured log event names."""

    # -- Agent / LLM --------------------------------------------------------
    ASK_START = "ask_start"
    CHAT_RUN_START = "chat_run_start"
    ITERATION_START = "iteration_start"
    MAX_ITERATIONS = "max_iterations_reached"

    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_ERROR = "tool_call_error"

    LLM_STREAM_ERROR = "llm_stream_error"
    LLM_TOOL_ARGS_ERROR = "llm_tool_args_error"

    RETRY_ATTEMPT = "retry_attempt"
    RETRY_EXHAUSTED = "retry_exhausted"

    AGENT_CONFIG_INVALID = "agent_config_invalid"

    # -- Chat / WebSocket ---------------------------------------------------
    CHAT_SEND_ERROR = "chat_send_error"
    CHAT_SEND_CANCELLED = "chat_send_cancelled"
    CHAT_STOP = "chat_stop"
    NOTIFICATION_SEND_FAILED = "notification_send_failed"
    MANAGER_SCOPE_FAILED = "manager_scope_resolve_failed"
    SESSION_NOT_FOUND = "session_not_found"
    SESSIONS_EVICTED = "sessions_evicted"

    WS_CONNECT = "ws_chat_connect"
    WS_DISCONNECT = "ws_chat_disconnect"
    WS_ERROR = "ws_chat_error"
    WS_EVENTS_CONNECT = "ws_events_connect"
    WS_EVENTS_DISCONNECT = "ws_events_disconnect"
    WS_RPC_CANCELLED = "background_rpc_cancelled"
    WS_RPC_SEND_FAILED = "background_rpc_send_failed"
    WS_PING_FAILED = "ws_ping_failed"

    # -- Knowledge / Signals ------------------------------------------------
    GRAPH_RETRIEVAL_FAILED = "graph_retrieval_failed"
    GRAPH_EXPAND_FAILED = "graph_expand_failed"
    SIGNAL_RETRIEVAL_FAILED = "signal_retrieval_failed"
    VECTOR_SEARCH_FAILED = "vector_search_failed"

    PATTERN_DETECTION_FAILED = "pattern_detection_failed"

    PRODUCER_STARTING = "producer_starting"

    # -- Ingestion / Documents ----------------------------------------------
    CLASSIFY_DOCUMENT_FAILED = "classify_document_failed"
    ENRICH_ROWS_FAILED = "enrich_rows_failed"
    INGESTION_FAILED = "ingestion_failed"
    PROPERTY_DIRECTORY_EMPTY = "property_directory_empty"
    SNAPSHOT_CAPTURE_FAILED = "snapshot_capture_failed"

    LOAD_REPORT_MISSING = "load_report_missing"
    LOAD_REPORT_FAILED = "load_report_failed"

    # -- Embeddings ---------------------------------------------------------
    EMBEDDING_PIPELINE_EMPTY = "embedding_pipeline_empty"
    EMBEDDING_BATCH_FAILED = "embedding_batch_failed"
    EMBEDDING_PIPELINE_FAILED = "embedding_pipeline_failed"
    MANAGER_SIGNAL_AGG_FAILED = "manager_signal_aggregation_failed"

    # -- Server lifecycle ---------------------------------------------------
    SERVER_READY = "server_ready"
    SERVER_SHUTDOWN = "server_shutdown"

    # -- Intent routing -----------------------------------------------------
    INTENT_CLASSIFIED = "intent_classified"

    # -- HTTP middleware ----------------------------------------------------
    HTTP_REQUEST = "http_request"
    HTTP_ERROR_RESPONSE = "http_error_response"
    UNHANDLED_ERROR = "unhandled_error"
