# AI Reading Coach

AI 英语阅读学习平台。它不是翻译软件或背单词工具，而是一位始终陪伴用户阅读英文文章的 AI 阅读伙伴，通过划词解释、长句解析、段落总结与问答，帮助用户减少阅读打断、持续积累词汇、建立阅读习惯。

产品核心设计理念：**Never Leave The Reading Page** —— 尽量不让用户离开阅读页面，AI 的所有能力都围绕"减少阅读打断"展开。

## 功能特性

**📖 阅读辅助**
- 划词解释（AI 流式输出释义 + 音标 + 例句），并标注该词的**词汇等级**（四级 / 六级 / 考研，来自分级词库）
- 长句语法分析、段落总结、基于文章上下文的 AI 问答
- 文章库：难度星级（1-5 ★）、四六级真题（`cet4`/`cet6`）筛选、阅读时长统计

**🧠 智能学习对话**
- ReAct Agent 多轮对话，思考流程（thinking / tool_call / tool_result）可视化
- 内置 10 个工具：查收藏词、查分级词库等级、阅读历史、文章内容、学习画像、长期记忆等

**📚 生词本与背诵**
- 收藏单词、掌握度标记（新词/学习中/熟悉/已掌握）、学习次数统计、**词汇等级徽标**
- AI 辅助背诵：背诵方案生成 → 逐卡背诵 → **双向召回检验**（看英文写中文 → 看中文写英文，通过才计入），可按等级筛选背诵
- 句子收藏：干净列表 + 详情弹窗 + 笔记

**🎯 个性化推荐**
- 首页三档 AI 推荐（适合学习 / 匹配 / 挑战），结合用户水平、画像与阅读历史

**⚙️ 模型配置**
- 每用户可配置多个大模型（Base URL / API Key / 模型名），API Key **加密存储**，一次只激活一个，失败时给出友好中文提示

**🔐 账户与安全**
- JWT 访问令牌 + 刷新令牌，登录态过期自动跳转登录页并提示重新登录
- 个人中心：头像上传（MinIO）、用户名 / 密码修改

## 技术栈

| 层级 | 技术 |
| ---- | ---- |
| 后端 | Python 3.11、FastAPI（全异步）、SQLAlchemy 2.0、asyncpg、Pydantic v2 |
| 数据库 | PostgreSQL 16，迁移用 Alembic（异步）+ `init.sql` 全量初始化 |
| 缓存 | Redis 7（异步客户端） |
| 对象存储 | MinIO（S3 兼容，头像 / 后续资源） |
| AI | DeepSeek 默认 Provider；支持用户自定义多模型（OpenAI 兼容 API），架构可无缝切换 |
| 前端 | Vite + Vue3 + TypeScript + naive-ui + Pinia + vue-i18n + Tailwind CSS |
| 基础设施 | Docker Compose |

## 目录结构

```
AI_English/
├── backend/
│   ├── app/
│   │   ├── core/           # 横切基础设施：配置、数据库、Redis、MinIO、响应/异常、AI 提供方
│   │   ├── api/            # 路由聚合与公共依赖（认证、管理员校验）
│   │   ├── modules/        # 垂直业务模块
│   │   │   ├── auth/ users/          # 认证与用户（JWT、头像、密码）
│   │   │   ├── article/              # 文章（难度星级、四六级）
│   │   │   ├── reading/              # 生词本、句子收藏、阅读历史、背诵方案
│   │   │   ├── ai/                   # 划词/长句/段落/问答/阅读总结/练习
│   │   │   ├── llm_config/           # 用户自定义多模型配置（加密）
│   │   │   ├── word_bank/            # 分级单词知识库（四级/六级/考研）
│   │   │   └── admin/                # 管理后台
│   │   └── agents/         # Agent 层
│   │       ├── reading_coach.py      # ReAct 阅读教练（多轮对话，10 个工具）
│   │       ├── recommender.py        # 首页文章推荐 Agent（单次 LLM + 规则降级）
│   │       ├── vocabulary_planner.py # 背诵规划 Agent（选词 + 顺序 + 建议）
│   │       └── tools/                # 工具集（base/记忆/画像/阅读/词库等）
│   ├── prompts/            # LLM 提示词模板（system/reading/agents）
│   ├── alembic/            # 数据库迁移
│   ├── scripts/            # 工具脚本（如词库导入 import_word_bank.py）
│   ├── data/               # 开源分级词表源文件
│   ├── requirements.txt / Dockerfile / .env / .env.example
├── frontend/               # Vue3 + TS + naive-ui
│   └── src/
│       ├── views/          # 页面（首页、文章、智能学习、生词本、句子、历史、模型配置、个人中心、管理端）
│       ├── components/     # 组件（ArticleCard、StarRating、CetFilter、SpeakerButton、reading/AiPanel、AgentThinkingFlow 等）
│       ├── api/ stores/ composables/ locales/ router/
├── docs/                   # 架构决策文档
├── docker-compose.yml
└── README.md
```

## 数据库（主要表）

| 表 | 说明 |
| ---- | ---- |
| `users` | 用户（邮箱、用户名、密码哈希、英语水平、头像） |
| `articles` | 文章（难度星级 `difficulty`、四六级真题 `cet_type`） |
| `word_collections` | 生词本（掌握度、学习次数、AI 解释） |
| `sentence_collections` | 句子收藏 |
| `reading_histories` | 阅读历史（时长、阅读次数） |
| `ai_conversations` / `ai_activities` | 文章内 AI 对话与活动日志 |
| `reading_summaries` / `reading_quizzes` | 阅读总结与练习题 |
| `user_profiles` / `ai_memories` | 学习画像与长期记忆 |
| `agent_conversations` / `agent_sessions` / `agent_steps` | 智能学习对话、会话与思考步骤 |
| `user_llm_configs` | 用户自定义大模型配置（每用户多条，至多一条激活） |
| `word_bank` / `word_bank_levels` | 分级单词知识库（词条 + 等级多对多） |

## Agent 与分级词库

- **ReAct 阅读教练**（`reading_coach.py`）：Thought → Action → Observation 推理循环，10 个数据工具，最终回答流式输出；智能学习页对话即此 Agent。
- **规划类 Agent**（与 ReAct 隔离）：文章推荐 `recommender.py`、背诵方案 `vocabulary_planner.py` —— 数据工具收集上下文 → 单次 LLM 调用 → JSON 解析校验 → **规则降级**（LLM 失败绝不报错）。
- **分级词库**：`word_bank` + `word_bank_levels`，等级 `cet4` / `cet6` / `kaoyan`（可拓展）。查词（`explain_word`）、Agent 工具（`lookup_word_level`）、生词本徽标、背诵等级筛选均基于词库。开源词表经 `backend/scripts/import_word_bank.py` 幂等导入。

## 本地开发

### 1. 启动基础设施（Postgres、Redis、MinIO）

```bash
docker compose up -d postgres redis minio
```

### 2. 初始化数据库

```bash
# 方式一：执行全量初始化脚本（含建表与种子数据）
psql -U postgres -d ai_reading_coach -f backend/init.sql

# 方式二：使用 Alembic 迁移（新增 ORM 模型后需先在 alembic/env.py 导入）
cd backend && alembic upgrade head
```

### 3. 导入分级词库（可选，为查词标注等级提供数据）

```bash
cd backend
python -m scripts.import_word_bank \
    --cet4 data/CET4_edited.txt --cet6 data/CET6_edited.txt --kaoyan data/NPEE_Wordlist.txt
```

### 4. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端运行在 `http://localhost:8000`。

### 5. 启动前端

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

`code` 为 `0` 表示成功，非 `0` 表示错误。认证失败（401）会由前端拦截器统一清除登录态并跳转登录页。详细架构决策见 [docs/architecture.md](docs/architecture.md)。
