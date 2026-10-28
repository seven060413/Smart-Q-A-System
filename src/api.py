"""FastAPI 服务：问答接口 + 学生认证接口。"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .auth_api import router as auth_router
from .errors import install_error_handlers
from .generator import QwenGenerator
from .graph import load_full_graph
from .loader import load_nodes
from .pipeline import run_qa
from .subgraph import OUT_PATH

app = FastAPI(title="中小学教材知识图谱智能问答系统")

# 统一错误结构 + X-Request-ID；认证路由在下面注册。
install_error_handlers(app)
app.include_router(auth_router)

# CORS：App 端 uni.request 不受同源限制，但 H5 调试需要放开跨域。
# 阶段 2.5（HTTPS/反向代理）会把这里收紧为白名单；当前保持现状以兼容旧前端。

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 启动时加载图谱、知识点与生成器
graph = load_full_graph()
kp_nodes = load_nodes(OUT_PATH)
generator = QwenGenerator()


class AskRequest(BaseModel):
    question: str


@app.get("/")
def root():
    return {"service": "中小学教材知识图谱智能问答系统", "docs": "/docs"}


@app.post("/api/ask")
def ask(req: AskRequest):
    result = run_qa(req.question, graph, kp_nodes)
    if not result["refused"]:
        result["answer"] = generator.generate(result["prompt"])
    result.pop("prompt", None)
    return result
