"""个性化推荐 API：首页「今日建议」。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from . import recommend_service
from .auth_deps import AuthContext, get_auth_context, get_db

router = APIRouter(prefix="/api/recommendations", tags=["个性化推荐"])


@router.get("/today", summary="今日建议")
def today_recommendations(
    limit: int = Query(default=3, ge=1, le=10),
    ctx: AuthContext = Depends(get_auth_context),
    conn=Depends(get_db),
):
    """按错题、趋势、聊天知识点生成建议；年级只做排序权重。

    必须登录：推荐依赖当前用户的历史；游客看到的是通用引导。
    """
    return recommend_service.today(
        conn,
        ctx.user["id"],
        grade=ctx.user.get("grade"),
        limit=limit,
    )
