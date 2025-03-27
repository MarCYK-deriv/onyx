import functools
import os
import time
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, cast

from langfuse import Langfuse
from langfuse.decorators import observe
from langfuse.api.resources.commons.types import ObservationLevel

# Type variable for return type
RT = TypeVar("RT")

# Initialize Langfuse client
langfuse = Langfuse(
    public_key=os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
    secret_key=os.environ.get("LANGFUSE_SECRET_KEY", ""),
    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
)

# Check if Langfuse is properly configured
is_langfuse_configured = bool(
    os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
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
                # This is a simple example, you might want to customize this
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
                    langfuse.trace(
                        name=f"{name}_error",
                        input=actual_input,
                        metadata={"error": str(e), "error_type": str(type(e))},
                        tags=tags + ["error"] if tags else ["error"],
                        level=ObservationLevel.ERROR,
                        user_id=user_id,
                        session_id=session_id,
                        parent_id=trace_id,
                    )
                # Re-raise the exception
                raise
        
        return wrapper
    
    return decorator


def create_trace_for_message(message_info, channel_name=None):
    """
    Create a trace for a message.
    Returns a trace_id that can be passed to other functions.
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
    user_id = message_info.sender_id or message_info.email or "unknown_user"
    
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
    """
    if not is_langfuse_configured or not trace_id:
        return
    
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


def log_retrieval(
    trace_id: Optional[str],
    query: str,
    documents: List[Any],
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Log a document retrieval operation to Langfuse.
    """
    if not is_langfuse_configured or not trace_id:
        return
    
    # Extract document IDs or other identifiers
    doc_ids = []
    for i, doc in enumerate(documents):
        doc_id = getattr(doc, "document_id", None) or getattr(doc, "id", None)
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


def log_user_feedback(
    trace_id: Optional[str],
    is_positive: Optional[bool],
    feedback_text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Log user feedback to Langfuse.
    """
    if not is_langfuse_configured or not trace_id:
        return
    
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
