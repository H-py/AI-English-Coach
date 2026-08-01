# AI Reading Coach - 后端服务

AI Reading Coach 平台的 FastAPI 后端，采用全异步架构与垂直模块化设计。

## 技术栈

- **Python 3.11** + **FastAPI**（异步 ASGI）
- **SQLAlchemy 2.0**（异步）+ **asyncpg** + **Alembic** 迁移
- **Redis**（异步客户端 + hiredis 解析器）
- **MinIO**（S3 兼容对象存储）
- **Pydantic v2** + **pydantic-settings**（配置与校验）
- **PyJWT**（JWT 认证辅助，Phase 1 预留）

## 目录结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 应用工厂、lifespan、CORS、异常处理
│   ├── core/                # 横切基础设施（配置、数据库、Redis、响应等）
│   ├── api/                 # 路由聚合与公共依赖
│   └── modules/             # 垂直模块切片（health 为范式模板）
├── alembic/                 # 异步迁移配置
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

## 数据库迁移

```bash
# 生成新迁移（在 backend/ 目录）
alembic revision --autogenerate -m "描述本次变更"

# 应用迁移
alembic upgrade head
```

> 注意：新增带 ORM 模型的模块后，需在 `alembic/env.py` 中导入该模块的 `models`，否则自动生成迁移无法发现新表。

## API 规范

- 基础地址：`http://localhost:8000/api/v1`
- 健康检查：`GET /api/v1/health`
- Swagger 文档：`http://localhost:8000/docs`
- ReDoc 文档：`http://localhost:8000/redoc`

所有接口统一返回信封格式：

```json
{ "code": 0, "message": "success", "data": {} }
```

`code` 为 `0` 表示成功，非 `0` 表示错误（校验、认证、业务、服务器等）。
