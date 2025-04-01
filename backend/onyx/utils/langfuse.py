from langfuse import Langfuse
from model_server.encoders import _embed_openai
from langfuse.openai import openai
import os

from model_server.constants import DEFAULT_OPENAI_MODEL
from shared_configs.utils import batch_list
from shared_configs.configs import OPENAI_EMBEDDING_TIMEOUT
from shared_configs.model_server_models import Embedding
# OpenAI only allows 2048 embeddings to be computed at once
_OPENAI_MAX_INPUT_LEN = 2048

# Langfuse embedding logging
async def embed_with_langfuse(
    texts: list[str],
    model: str | None,
    reduced_dimension: int | None,
    api_key: str = None,
    timeout: int = None,
) -> list[Embedding]:
    # Initialize langfuse client
    langfuse = Langfuse()

    if not model:
        model = DEFAULT_OPENAI_MODEL

    trace = langfuse.trace(
        name=f"embedding_{model}",
        session_id="Embedding-Logger",
        user_id="Embedding-Logger",
        metadata={
            "model": model,
            "text_count": len(texts),
            "dimensions": reduced_dimension,
            # Sample of first text
            "text_sample": texts[0][:100] if texts else ""
        }
    )

    print(f"New embedding trace created: {trace.id}")

    span = trace.span(
        name="embedding_operation",
        input={
            "text_count": len(texts),
            "model": model,
            "reduced_dimension": reduced_dimension
        }
    )

    # Create OpenAI client - ONLY pass the needed parameters
    client = openai.AsyncOpenAI(
        api_key=api_key,
        timeout=timeout or OPENAI_EMBEDDING_TIMEOUT,
    )

    final_embeddings = []

    for text_batch in batch_list(texts, _OPENAI_MAX_INPUT_LEN):
        # Pass the trace_id in headers
        headers = {"X-Langfuse-Trace-Id": trace.id}

        batch_span = trace.span(
            name="embedding_batch",
            input={"batch_size": len(text_batch)}
        )

        response = await client.embeddings.create(
            input=text_batch,
            model=model,
            dimensions=reduced_dimension or openai.NOT_GIVEN,
            extra_headers=headers
        )

        batch_span.end(
            output={
                "token_count": response.usage.total_tokens if hasattr(response, "usage") else None
            }
        )

        final_embeddings.extend(
            [embedding.embedding for embedding in response.data])

    # Log the results
    span.end(
        output={
            "embedding_count": len(final_embeddings),
            "embedding_dimensions": len(final_embeddings[0]) if final_embeddings else 0,
            "embedding_sample": final_embeddings[0][:5] if final_embeddings else None,
        }
    )

    # Add the complete result to the trace
    trace.update(
        output={
            "embedding_count": len(final_embeddings),
            "embedding_dimensions": len(final_embeddings[0]) if final_embeddings else 0,
            # Include samples from first two embeddings if available
            "sample_values": [emb[:3] for emb in final_embeddings[:2]] if final_embeddings else []
        }
    )

    return final_embeddings
