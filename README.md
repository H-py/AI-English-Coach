# AI Reading Coach

AI 英语阅读学习平台。它不是翻译软件或背单词工具，而是一位始终陪伴用户阅读英文文章的 AI 阅读伙伴，通过划词解释、长句解析、段落总结与问答，帮助用户减少阅读打断、持续积累词汇、建立阅读习惯。

产品核心设计理念：**Never Leave The Reading Page** —— 尽量不让用户离开阅读页面，AI 的所有能力都围绕"减少阅读打断"展开。

## 技术栈

| 层级 | 技术 |
| ---- | ---- |
| 后端 | Python 3.11、FastAPI（全异步）、SQLAlchemy 2.0、asyncpg |
| 数据库迁移 | Alembic（异步） |
| 缓存 | Redis 7 |
| 对象存储 | MinIO（S3 兼容） |
| AI | DeepSeek（默认 Provider，架构支持无缝切换） |
| 前端 | Vite + Vue3 + TypeScript（端口 5173） |
| 基础设施 | Docker Compose |

## 目录结构

```
AI_English/
├── backend/                # 后端服务
│   ├── app/
│   │   ├── core/           # 基础设施：配置、数据库、Redis、存储、响应、异常等
│   │   ├── api/            # 路由聚合与公共依赖
│   │   └── modules/        # 垂直模块切片（health 为范式模板）
│   ├── alembic/            # 数据库迁移
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env / .env.example
├── frontend/               # 前端应用（Vue3 + TS）
├── docs/                   # 架构决策记录
├── docker-compose.yml
├── .gitignore
└── README.md
```

## 本地开发

### 1. 启动基础设施（Postgres、Redis、MinIO）

在项目根目录执行：

```bash
docker compose up -d postgres redis minio
```

将启动：
- PostgreSQL 16 → `localhost:5432`
- Redis 7 → `localhost:6379`
- MinIO API → `localhost:9000`，控制台 → `localhost:9001`

### 2. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端运行在 `http://localhost:8000`。

> 说明：后端直接在主机运行时，`.env` 中的连接地址使用 `localhost`（指向容器映射端口）；若后端也在 Docker 内运行（`docker compose up -d --build`），`docker-compose.yml` 会自动将连接地址覆盖为服务名（`postgres`、`redis`、`minio`）。

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器运行在 `http://localhost:5173`。

## 访问地址

| 服务 | 地址 |
| ---- | ---- |
| 后端 API | http://localhost:8000/api/v1 |
| 健康检查 | http://localhost:8000/api/v1/health |
| Swagger 文档 | http://localhost:8000/docs |
| ReDoc 文档 | http://localhost:8000/redoc |
| 前端（开发） | http://localhost:5173 |
| MinIO 控制台 | http://localhost:9001 |

## 端口分配

| 服务 | 端口 |
| ---- | ---- |
| 后端 | 8000 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| MinIO API | 9000 |
| MinIO 控制台 | 9001 |
| 前端（开发） | 5173 |

## 统一 API 响应格式

所有接口统一返回：

```json
{ "code": 0, "message": "success", "data": {} }
```

`code` 为 `0` 表示成功，非 `0` 表示错误。详细架构决策见 [docs/architecture.md](docs/architecture.md)。
