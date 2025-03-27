import functools
import os
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, cast

from onyx.onyxbot.slack.utils import get_user_email
from langfuse import Langfuse
from langfuse.decorators import observe
from langfuse.api.resources.commons.types import ObservationLevel

# Type variable for return type
RT = TypeVar("RT")

# Initialize Langfuse client
langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_HOST")
)

# Check if Langfuse is properly configured
is_langfuse_configured = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get(
        "LANGFUSE_SECRET_KEY")
)


def safe_trace(
    name: str,
    input_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    level: Optional[ObservationLevel] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    A decorator that safely traces a function execution.
    If Langfuse is not configured, it will just execute the function without tracing.

    Args:
        name: Name of the trace
        input_data: Input data for the trace
        metadata: Additional metadata
        tags: Tags for the trace
        level: Observation level
        user_id: User ID for the trace
        session_id: Session ID for the trace
    """
    def decorator(func: Callable[..., RT]) -> Callable[..., RT]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> RT:
            if not is_langfuse_configured:
                return func(*args, **kwargs)

            # Extract trace_id from kwargs if available
            trace_id = kwargs.pop("trace_id", None)

            # Start timing
            start_time = time.time()

            # Prepare input data
            actual_input = input_data or {}
            if not input_data:
                # Try to extract some meaningful data from args and kwargs
                if args and hasattr(args[0], "__dict__"):
                    actual_input = {
                        "args_type": str(type(args[0])),
                        "has_args": True
                    }
                if kwargs:
                    actual_input["kwargs_keys"] = list(kwargs.keys())

            try:
                # Create a new trace or span - updated to not use context manager
                current_span = langfuse.trace(
                    name=name,
                    input=actual_input,
                    metadata=metadata,
                    tags=tags,
                    level=level,
                    user_id=user_id,
                    session_id=session_id,
                    id=trace_id,
                )

                # Add trace_id to kwargs for nested functions
                kwargs["trace_id"] = current_span.id
                result = func(*args, **kwargs)

                # Calculate execution time
                execution_time = time.time() - start_time

                # Log the result and execution time
                current_span.update(
                    output={"execution_time": execution_time},
                    status="success"
                )

                return result
            except Exception as e:
                # Log the error
                if is_langfuse_configured:
                    # Use existing trace_id as parent if available
                    error_trace = langfuse.trace(
                        name=f"{name}_error",
                        input=actual_input,
                        metadata={"error": str(e), "error_type": str(type(e))},
                        tags=tags + ["error"] if tags else ["error"],
                        level=ObservationLevel.ERROR,
                        user_id=user_id,
                        session_id=session_id,
                        parent_id=trace_id,
                    )

                    # Calculate execution time until error
                    execution_time = time.time() - start_time

                    # Update the error trace with execution time
                    error_trace.update(
                        output={"execution_time_until_error": execution_time},
                        status="error"
                    )
                # Re-raise the exception
                raise

        return wrapper

    return decorator


def create_trace_for_message(message_info, channel_name=None, client=None):
    """
    Create a trace for a message.
    Returns a trace_id that can be passed to other functions.

    Args:
        message_info: Information about the message
        channel_name: Name of the channel
        client: Slack client for additional info resolution

    Returns:
        trace_id: ID of the created trace or None if Langfuse is not configured
    """
    if not is_langfuse_configured:
        return None

    # Extract useful information from message_info
    metadata = {
        "channel": message_info.channel_to_respond,
        "channel_name": channel_name,
        "is_bot_msg": message_info.is_bot_msg,
        "is_bot_dm": message_info.is_bot_dm,
        "bypass_filters": message_info.bypass_filters,
    }

    # Create user_id from sender_id or email
    user_id = None
    if client and message_info.sender_id:
        user_id = get_user_email(message_info.sender_id, client)

    # Fall back to email from message_info or default to unknown
    if not user_id:
        user_id = message_info.email or "unknown_user"

    # Create a session_id from the thread
    session_id = message_info.thread_to_respond or message_info.msg_to_respond

    # Create a trace
    trace = langfuse.trace(
        name="slack_message_handling",
        input={"message_count": len(message_info.thread_messages)},
        metadata=metadata,
        tags=["slack", "message"],
        user_id=user_id,
        session_id=session_id,
    )

    return trace.id


def log_llm_call(
    trace_id: Optional[str],
    model: str,
    prompt: str,
    completion: str,
    tokens_prompt: Optional[int] = None,
    tokens_completion: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Log an LLM call to Langfuse.

    Args:
        trace_id: ID of the parent trace
        model: Name of the LLM model
        prompt: The prompt sent to the LLM
        completion: The response from the LLM
        tokens_prompt: Number of tokens in the prompt
        tokens_completion: Number of tokens in the completion
        metadata: Additional metadata
    """
    if not is_langfuse_configured or not trace_id:
        return

    try:
        langfuse.generation(
            name="llm_call",
            model=model,
            prompt=prompt,
            completion=completion,
            prompt_tokens=tokens_prompt,
            completion_tokens=tokens_completion,
            metadata=metadata or {},
            parent_id=trace_id,
        )
    except Exception as e:
        # Log but don't crash the application if Langfuse logging fails
        print(f"Error logging LLM call to Langfuse: {str(e)}")


def log_retrieval(
    trace_id: Optional[str],
    query: str,
    documents: List[Any],
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Log a document retrieval operation to Langfuse.

    Args:
        trace_id: ID of the parent trace
        query: The search query
        documents: List of retrieved documents
        metadata: Additional metadata
    """
    if not is_langfuse_configured or not trace_id:
        return

    try:
        # Extract document IDs or other identifiers
        doc_ids = []
        for i, doc in enumerate(documents):
            doc_id = getattr(doc, "document_id",
                             None) or getattr(doc, "id", None)
            if doc_id:
                doc_ids.append(doc_id)
            else:
                doc_ids.append(f"doc_{i}")

        langfuse.span(
            name="document_retrieval",
            input={"query": query},
            output={"document_ids": doc_ids, "document_count": len(documents)},
            metadata=metadata or {},
            parent_id=trace_id,
        )
    except Exception as e:
        # Log but don't crash the application if Langfuse logging fails
        print(f"Error logging retrieval to Langfuse: {str(e)}")


def log_user_feedback(
    trace_id: Optional[str],
    is_positive: Optional[bool],
    feedback_text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Log user feedback to Langfuse.

    Args:
        trace_id: ID of the parent trace
        is_positive: Whether the feedback is positive
        feedback_text: Additional feedback text
        metadata: Additional metadata
    """
    if not is_langfuse_configured or not trace_id:
        return

    try:
        score = None
        if is_positive is not None:
            score = 1.0 if is_positive else 0.0

        langfuse.score(
            name="user_feedback",
            value=score,
            comment=feedback_text or "",
            metadata=metadata or {},
            trace_id=trace_id,
        )
    except Exception as e:
        # Log but don't crash the application if Langfuse logging fails
        print(f"Error logging user feedback to Langfuse: {str(e)}")


def log_custom_span(
    trace_id: Optional[str],
    name: str,
    input_data: Optional[Dict[str, Any]] = None,
    output_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    level: Optional[ObservationLevel] = None,
):
    """
    Log a custom span to Langfuse for tracking arbitrary operations.

    Args:
        trace_id: ID of the parent trace
        name: Name of the span
        input_data: Input data for the span
        output_data: Output data from the span
        metadata: Additional metadata
        tags: Tags for the span
        level: Observation level
    """
    if not is_langfuse_configured or not trace_id:
        return

    try:
        langfuse.span(
            name=name,
            input=input_data or {},
            output=output_data or {},
            metadata=metadata or {},
            tags=tags or [],
            level=level,
            parent_id=trace_id,
        )
    except Exception as e:
        # Log but don't crash the application if Langfuse logging fails
        print(f"Error logging custom span to Langfuse: {str(e)}")
