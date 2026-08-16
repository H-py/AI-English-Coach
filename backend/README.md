# AI Reading Coach - 后端服务

AI Reading Coach 平台的 FastAPI 后端，采用全异步架构、垂直模块化设计与独立的 Agent 层。

## 技术栈

- **Python 3.11** + **FastAPI**（异步 ASGI）
- **SQLAlchemy 2.0**（异步）+ **asyncpg** + **Alembic** 迁移
- **Redis**（异步客户端）
- **MinIO**（S3 兼容对象存储，头像上传）
- **Pydantic v2** + **pydantic-settings**（配置与校验）
- **PyJWT**（访问令牌 + 刷新令牌认证）

## 目录结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 应用工厂、lifespan、CORS、异常处理
│   ├── core/                # 横切基础设施：配置、数据库、Redis、MinIO、响应/异常、
│   │                        #   AI 提供方（DeepSeek + 用户多模型 + 加密 + 缓存 + prompt 管理）
│   ├── api/                 # 路由聚合与公共依赖（get_current_user、get_admin_user）
│   ├── modules/             # 垂直业务模块
│   │   ├── auth/            # 注册、登录、令牌刷新
│   │   ├── users/           # 用户信息、头像上传、修改密码
│   │   ├── article/         # 文章（难度星级、四六级真题）、个性化推荐
│   │   ├── reading/         # 生词本、句子收藏、阅读历史、背诵方案
│   │   ├── ai/              # 划词解释、长句分析、段落总结、文章问答、阅读总结、练习题
│   │   ├── llm_config/      # 用户自定义多模型配置（API Key 加密、单激活）
│   │   ├── word_bank/       # 分级单词知识库（四级/六级/考研，等级多对多）
│   │   └── admin/           # 管理后台
│   └── agents/              # Agent 层（与业务模块隔离）
│       ├── base.py          # ReAct 推理循环（Thought → Action → Observation）
│       ├── reading_coach.py # 阅读教练 Agent（10 个工具，流式最终回答）
│       ├── recommender.py   # 文章推荐 Agent（数据工具 + 单次 LLM + 规则降级）
│       ├── vocabulary_planner.py # 背诵规划 Agent（选词 + 顺序 + 建议）
│       └── tools/           # 数据工具集（base/记忆/画像/阅读/词库/推荐/背诵）
├── prompts/                 # LLM 提示词模板（system/reading/agents，Jinja2 渲染）
├── alembic/                 # 异步迁移配置与版本
├── scripts/                 # 工具脚本（词库导入 import_word_bank.py）
├── data/                    # 开源分级词表源文件（CET4/CET6/NPEE）
├── requirements.txt
├── Dockerfile
├── .env / .env.example
└── README.md
```

## 本地开发

### 方式一：主机直接运行（推荐开发）

先用 Docker Compose 启动依赖服务（在项目根目录）：

```bash
docker compose up -d postgres redis minio
```

再在 `backend/` 目录启动后端：

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

此模式下 `.env` 默认使用 `localhost` 地址，可直接访问容器映射端口。

### 方式二：全部容器化运行

在项目根目录执行：

```bash
docker compose up -d --build
```

容器内运行时，`docker-compose.yml` 会将连接地址覆盖为服务名（`postgres:5432`、`redis:6379`、`minio:9000`）。

## 环境变量

完整列表见 `.env.example`，关键连接变量在两种运行模式下的取值：

| 变量 | 主机运行 | 容器运行 |
| ---- | ---- | ---- |
| `DATABASE_URL` | `...@localhost:5432/...` | `...@postgres:5432/...` |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| `MINIO_ENDPOINT` | `localhost:9000` | `minio:9000` |

## 数据库

- **初始化**：`psql -U postgres -d ai_reading_coach -f init.sql`（全量建表 + 种子数据）
- **迁移**：`alembic upgrade head`；生成新迁移用 `alembic revision --autogenerate -m "描述"`

> 注意：新增带 ORM 模型的模块后，需在 `alembic/env.py` 中导入该模块的 `models`，否则自动生成迁移无法发现新表。

## 分级词库导入

词库为查词标注等级、Agent 查词工具、生词本徽标与背诵等级筛选的数据基础：

```bash
python -m scripts.import_word_bank \
    --cet4 data/CET4_edited.txt --cet6 data/CET6_edited.txt --kaoyan data/NPEE_Wordlist.txt
```

脚本幂等，重复执行不会产生重复数据；支持 `word [音标] 词性. 释义` 文本与 JSON（`{name, trans, ukphone}`）两种词表格式。

## API 规范

- 基础地址：`http://localhost:8000/api/v1`
- 健康检查：`GET /api/v1/health`
- Swagger 文档：`http://localhost:8000/docs`
- ReDoc 文档：`http://localhost:8000/redoc`

所有接口统一返回信封格式：

```json
{ "code": 0, "message": "success", "data": {} }
```

`code` 为 `0` 表示成功，非 `0` 表示错误（校验、认证、业务、服务器等）。认证失败返回 HTTP 401，前端拦截器据此清除登录态并跳转登录页。
