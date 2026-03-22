import asyncio
import logging
import traceback
from typing import Optional

from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

async def astream(llm, messages, extra_body, config: Optional[RunnableConfig], retry_cnt = 5):
    # Fast-fail if TTFB exceeds threshold to avoid waiting full client timeout per retry
    TTFB_TIMEOUT_SECONDS = 100
    PER_CHUNK_IDLE_TIMEOUT_SECONDS = 100
    
    try:
        stream = llm.astream(input=messages, extra_body=extra_body, config=config)
        aiter = stream.__aiter__()
        
        try:
            first_chunk = await asyncio.wait_for(aiter.__anext__(), timeout=TTFB_TIMEOUT_SECONDS)
        except asyncio.TimeoutError as timeout_err:
            # TimeoutError should NOT retry - fast fail as designed
            error_msg = f"TTFB exceeded {TTFB_TIMEOUT_SECONDS}s without receiving first token"
            logger.error(error_msg)
            raise TimeoutError(error_msg) from timeout_err

        result = first_chunk

        # Continue consuming the remaining chunks with per-chunk idle timeout
        while True:
            try:
                chunk = await asyncio.wait_for(aiter.__anext__(), timeout=PER_CHUNK_IDLE_TIMEOUT_SECONDS)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError as timeout_err:
                # TimeoutError should NOT retry - fast fail as designed
                error_msg = f"Stream stalled: no chunk for {PER_CHUNK_IDLE_TIMEOUT_SECONDS}s after TTFB"
                logger.error(error_msg)
                raise TimeoutError(error_msg) from timeout_err

            result = result + chunk
        return result
    except TimeoutError:
        # Don't retry on timeout - re-raise immediately for fast-fail behavior
        raise
    except Exception as e:
        error_msg = traceback.format_exc()
        
        # 检查是否是 429 限流错误
        is_rate_limit = "429" in error_msg or "Too Many Requests" in error_msg or "insufficient_quota" in error_msg
        
        if is_rate_limit:
            logger.error(f"Rate limit exceeded, waiting before retry... {retry_cnt} retries remaining")
        
        logger.error(f"Request failed: {error_msg}, {retry_cnt} retries remaining")
        
        if retry_cnt > 0:
            # 429 错误需要更长的等待时间
            if is_rate_limit:
                wait_time = 10 * (6 - retry_cnt)  # 10s, 20s, 30s, 40s, 50s
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                await asyncio.sleep(3)
            return await astream(llm, messages, extra_body, config, retry_cnt - 1)
        else:
            raise