"""知识点关联视频查询接口（公开只读）。

运行时只读本地 SQLite；不实时搜索 B 站，不接受客户端传入任意 URL。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response

from . import videos
from .auth_deps import get_db

router = APIRouter(prefix="/api", tags=["知识点视频"])


@router.get("/videos", summary="批量查询知识点关联视频")
def list_videos(
    response: Response,
    node_key: list[str] | None = Query(
        default=None,
        description="知识点 node_key，可重复；一次最多 20 个",
    ),
    limit: int = Query(default=2, ge=1, le=5, description="每个知识点最多返回几条"),
    conn=Depends(get_db),
):
    """返回审核通过的 B 站视频。

    - 游客可访问，不需要登录；
    - 只返回 approved 且 active 的记录；
    - 没有视频的 node_key 放在 missing 中。
    """
    # 审核结果会变化，禁止浏览器/代理缓存空的 GET 结果。
    response.headers["Cache-Control"] = "no-store"
    return videos.get_videos_for_nodes(conn, node_key, limit=limit)
