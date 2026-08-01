# 架构决策记录

本文档记录 AI Reading Coach 后端的关键架构决策，便于后续维护者理解设计动机并保持一致的扩展方式。

## 1. 垂直模块化结构

后端采用**垂直（按功能）模块化**而非水平（按层）分层。每个功能自包含于 `app/modules/` 下的独立包：

```
app/modules/<feature>/
├── __init__.py
├── router.py     # FastAPI 路由（端点）
├── schemas.py    # Pydantic 请求/响应模型
├── service.py    # 业务逻辑（按需添加）
└── models.py     # SQLAlchemy ORM 模型（按需添加）
```

**动机**：功能可独立新增、修改或移除，而不触碰共享基础设施。每个切片拥有自己的路由、Schema 与 Service，最大化模块内聚、最小化跨模块耦合。`app/modules/health` 是新增功能时可直接复制的标准模板。

**聚合方式**：所有模块路由在 `app/api/router.py` 中挂载，统一使用 `/api/v1` 前缀，为前端提供单一稳定的 API 基础地址。

## 2. AI Provider 分层

AI 能力抽象在 Provider 层之后，底层 LLM 服务（DeepSeek 及未来其他模型）可无缝切换，无需改动业务逻辑：

```
modules/<feature>/service.py
        ↓ 调用
core/ai/provider.py   # Provider 接口（待实现）
        ↓ 委托
core/ai/deepseek.py   # DeepSeek 客户端（httpx）
```

通过 `AI_DEFAULT_PROVIDER` 配置项选择当前 Provider；新 Provider 实现相同接口并在工厂中注册即可启用。

## 3. 统一响应信封

**所有** API 端点返回统一的 JSON 结构：

```json
{ "code": 0, "message": "success", "data": {} }
```

- `code == 0` 表示成功。
- `code != 0` 表示发生错误（校验、认证、业务、服务器等）。

**实现**（`app/core/response.py`）：
- `ResponseModel[T]` 为泛型 Pydantic 模型，OpenAPI 文档可描述具体 payload 类型，同时线上格式保持统一。
- `success(data, message)` 与 `error(code, message, data)` 辅助函数直接构造字典返回。

**异常处理**（`app/core/exceptions.py`）：
- 自定义 `BizException` 携带业务 `code` 与 `message`。
- 全局处理器将 `BizException`、`RequestValidationError`、`HTTPException` 及未捕获的 `Exception` 统一包装为信封格式，HTTP 状态码统一返回 200，以 body 中的 `code` 作为客户端判断依据。
- 错误码命名空间：`1xxxx` 校验、`2xxxx` 认证、`4xxxx` HTTP、`5xxxx` 服务器、`9xxxx` 通用业务。

## 4. 全异步优先

所有 I/O 均为异步（`async def`）：
- SQLAlchemy 异步引擎 + `asyncpg` 驱动。
- `redis.asyncio` 客户端 + hiredis 解析器。
- MinIO 客户端为同步，仅在启动（lifespan）阶段用于 bucket 初始化；运行时上传/下载后续可异步化处理。

## 5. 配置管理

单一 `Settings` 类（`pydantic-settings`）从 `backend/.env` 读取全部环境变量，通过 `lru_cache` 缓存为单例，全局以 `settings` 引用 —— 配置唯一来源。

## 6. Lifespan 资源管理

`app/main.py` 使用 FastAPI 的 `lifespan` 上下文：
- **启动**：配置日志、确保 MinIO bucket 存在。
- **关闭**：释放 Redis 连接池。

## 7. 端口分配

| 服务 | 端口 | 说明 |
| ---- | ---- | ---- |
| 后端（API） | 8000 | `uvicorn app.main:app` |
| PostgreSQL | 5432 | 数据库名 `ai_reading_coach` |
| Redis | 6379 | db 0 |
| MinIO API | 9000 | S3 兼容 |
| MinIO 控制台 | 9001 | Web 界面 |
| 前端（开发） | 5173 | Vite 默认 |

## 8. 容器与主机网络

- **主机运行后端**：`.env` 使用 `localhost` 地址，访问容器映射端口。
- **容器运行后端**：`docker-compose.yml` 将 `DATABASE_URL`、`REDIS_URL`、`MINIO_ENDPOINT` 覆盖为 Docker 服务名（`postgres`、`redis`、`minio`）。

这种双模式既保留了主机开发的热重载速度，也支持全容器化部署。
