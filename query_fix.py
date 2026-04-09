"""
nblm_core.query
~~~~~~~~~~~~~~~
Send a single query to a NotebookLM notebook with retry / back-off logic.

Public API:
    send_query(client, nb_id, prompt_text, ...) -> str
"""

import asyncio
from typing import Optional, List, Callable


# ---------------------------------------------------------------------------
# Default constants (can be overridden per call)
# ---------------------------------------------------------------------------

DEFAULT_REQUEST_TIMEOUT = 180       # seconds per API call
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAYS = [5, 10, 20]  # exponential back-off schedule


# ---------------------------------------------------------------------------
# Core query function
# ---------------------------------------------------------------------------

async def send_query(
    client,
    nb_id: str,
    prompt_text: str,
    *,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delays: Optional[List[int]] = None,
    on_retry: Optional[Callable[[int, int, int, Exception], None]] = None,
) -> str:
    """
    Send a single query to the notebook and return the text response.

    Parameters
    ----------
    client : NotebookLMClient
        An initialised, connected client.
    nb_id : str
        Notebook identifier.
    prompt_text : str
        The query text (breadcrumb path or templated string).
    request_timeout : int
        Per-attempt timeout in seconds.
    max_retries : int
        Total number of attempts before giving up.
    retry_delays : list[int] | None
        Delays (in seconds) between retries. Falls back to
        DEFAULT_RETRY_DELAYS when None.
    on_retry : callable | None
        Optional callback ``(attempt, max_retries, delay, exc) -> None``
        invoked before each retry sleep.  Callers (e.g. the CLI) can
        use this to print progress / warnings.

    Returns
    -------
    str
        The model's answer, or an error placeholder if all retries fail.
    """
    if retry_delays is None:
        retry_delays = DEFAULT_RETRY_DELAYS

    last_error: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            result = await asyncio.wait_for(
                client.chat.ask(nb_id, prompt_text),
                timeout=request_timeout,
            )
            return result.answer
        except (asyncio.TimeoutError, Exception) as exc:
            last_error = exc
            if attempt < max_retries - 1:
                delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
                if on_retry is not None:
                    on_retry(attempt + 1, max_retries, delay, exc)
                await asyncio.sleep(delay)

    # All retries exhausted
    node_label = prompt_text.split("\n")[-1].strip()
    return f"> [!ERROR] ГЕНЕРАЦИЯ ПРЕРВАНА ДЛЯ: {node_label}"
