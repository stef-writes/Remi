"""Canonical log event names.

Every structured log event in the application should use a constant from
this module so that event names are discoverable, greppable, and stable
enough to build dashboards and alerts against.
"""


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

    # -- Knowledge / Signals ------------------------------------------------
    GRAPH_RETRIEVAL_FAILED = "graph_retrieval_failed"
    GRAPH_EXPAND_FAILED = "graph_expand_failed"
    SIGNAL_RETRIEVAL_FAILED = "signal_retrieval_failed"
    VECTOR_SEARCH_FAILED = "vector_search_failed"

    ENTAILMENT_COMPLETE = "entailment_complete"
    ENTAILMENT_EVAL_FAILED = "entailment_eval_failed"
    SIGNAL_PIPELINE_FAILED = "signal_pipeline_failed"
    PATTERN_DETECTION_FAILED = "pattern_detection_failed"

    PRODUCER_STARTING = "producer_starting"

    # -- Ingestion / Documents ----------------------------------------------
    CLASSIFY_DOCUMENT_FAILED = "classify_document_failed"
    ENRICH_ROWS_FAILED = "enrich_rows_failed"
    INGESTION_FAILED = "ingestion_failed"
    PROPERTY_DIRECTORY_EMPTY = "property_directory_empty"
    SNAPSHOT_CAPTURE_FAILED = "snapshot_capture_failed"

    SEED_REPORT_MISSING = "seed_report_missing"
    SEED_REPORT_FAILED = "seed_report_failed"
    SEED_AUTO_ASSIGN_FAILED = "seed_auto_assign_failed"
    SEED_SIGNALS_FAILED = "seed_signals_failed"

    # -- Embeddings ---------------------------------------------------------
    EMBEDDING_PIPELINE_EMPTY = "embedding_pipeline_empty"
    EMBEDDING_BATCH_FAILED = "embedding_batch_failed"
    EMBEDDING_PIPELINE_FAILED = "embedding_pipeline_failed"
    MANAGER_SIGNAL_AGG_FAILED = "manager_signal_aggregation_failed"

    # -- Sandbox ------------------------------------------------------------
    SANDBOX_SESSION_CREATED = "sandbox_session_created"
    SANDBOX_SESSION_DESTROYED = "sandbox_session_destroyed"

    # -- Server lifecycle ---------------------------------------------------
    SERVER_READY = "server_ready"
    SERVER_SHUTDOWN = "server_shutdown"

    # -- Intent routing -----------------------------------------------------
    INTENT_CLASSIFIED = "intent_classified"

    # -- HTTP middleware ----------------------------------------------------
    HTTP_REQUEST = "http_request"
    HTTP_ERROR_RESPONSE = "http_error_response"
    UNHANDLED_ERROR = "unhandled_error"
