
import asyncio
import secrets
import socket
import time

import aiohttp
import edge_tts
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["语音朗读"])

# 临时保存待播放文本，不写入磁盘或数据库
tts_sessions = {}
SESSION_TTL = 300  # 5分钟后过期


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)


def clean_expired_sessions():
    now = time.time()
    expired = [
        token for token, item in tts_sessions.items()
        if now - item["created_at"] > SESSION_TTL
    ]
    for token in expired:
        tts_sessions.pop(token, None)


@router.post("/tts/stream/session")
async def create_tts_session(data: TTSRequest, request: Request):
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="朗读文本不能为空")

    clean_expired_sessions()

    token = secrets.token_urlsafe(24)
    tts_sessions[token] = {
        "text": text,
        "created_at": time.time()
    }

    audio_url = str(
        request.url_for("tts_audio_stream", token=token)
    )

    return {"audio_url": audio_url}


@router.get("/tts/stream/{token}", name="tts_audio_stream")
async def tts_audio_stream(token: str):
    clean_expired_sessions()

    session = tts_sessions.pop(token, None)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="语音任务不存在或已过期，请重新请求"
        )

    text = session["text"]

    # 强制 IPv4，规避当前环境的 IPv6 连接问题
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    communicate = edge_tts.Communicate(
        text,
        voice="zh-CN-XiaoxiaoNeural",
        connector=connector
    )

    stream = communicate.stream()

    # 先取到第一段音频，确保连接失败时还能返回 HTTP 错误
    first_audio = None

    try:
        async for chunk in stream:
            if chunk["type"] == "audio":
                first_audio = chunk["data"]
                break

        if first_audio is None:
            await stream.aclose()
            raise HTTPException(
                status_code=502,
                detail="语音服务没有返回音频"
            )

    except HTTPException:
        raise
    except Exception as e:
        await stream.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"语音生成失败：{str(e)}"
        )

    async def audio_generator():
        try:
            yield first_audio

            async for chunk in stream:
                if chunk["type"] == "audio":
                    yield chunk["data"]

        finally:
            await stream.aclose()

    return StreamingResponse(
        audio_generator(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no"
        }
    )
