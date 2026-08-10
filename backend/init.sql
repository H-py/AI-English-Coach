-- ============================================================
-- AI Reading Coach - 数据库初始化脚本
-- 数据库：PostgreSQL 16
-- 数据库名：ai_reading_coach
--
-- 使用方式：
--   方式一（命令行）：
--     psql -U postgres -d ai_reading_coach -f init.sql
--   方式二（Docker）：
--     docker exec -i arc-postgres psql -U postgres -d ai_reading_coach < init.sql
--   方式三（GUI 工具如 DBeaver / pgAdmin）：
--     直接复制本文件内容执行
-- ============================================================

-- ------------------------------------------------------------
-- 1. 枚举类型：english_level
-- ------------------------------------------------------------
-- 对应 backend/app/modules/users/models.py 中的 EnglishLevel 枚举
-- beginner    初级
-- intermediate 中级
-- advanced    高级
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'englishlevel') THEN
        CREATE TYPE englishlevel AS ENUM ('beginner', 'intermediate', 'advanced');
    END IF;
END$$;

-- ------------------------------------------------------------
-- 1b. 枚举类型：userrole
-- ------------------------------------------------------------
-- 对应 backend/app/modules/users/models.py 中的 UserRole 枚举
-- user  普通用户
-- admin 管理员
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'userrole') THEN
        CREATE TYPE userrole AS ENUM ('user', 'admin');
    END IF;
END$$;

-- ------------------------------------------------------------
-- 2. users 表
-- ------------------------------------------------------------
-- 对应 backend/app/modules/users/models.py 中的 User 模型
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    username        VARCHAR(50)  NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    avatar_url      VARCHAR(512),
    english_level   englishlevel NOT NULL DEFAULT 'beginner',
    role            userrole     NOT NULL DEFAULT 'user',
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 唯一约束（含索引）
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email    ON users (email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);

-- updated_at 自动更新触发器（模拟 ORM 的 onupdate=func.now()）
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ------------------------------------------------------------
-- 3. 测试数据（可选）
-- ------------------------------------------------------------
-- 测试账号：
--   邮箱：test@reading.coach
--   用户名：testuser
--   密码：password123
--   密码哈希由 bcrypt 生成，后端 verify_password 可直接校验
-- INSERT INTO users (email, username, password_hash, english_level, is_active)
-- VALUES (
--     'test@reading.coach',
--     'testuser',
--     '$2b$12$9PYBI0wxL/LHkTjBRebM5eauMvnTCzhnX8ioz/LUjNoE5Qtsf2aFG',
--     'beginner',
--     TRUE
-- )
-- ON CONFLICT (email) DO NOTHING;

-- ------------------------------------------------------------
-- 4. 枚举类型：difficulty
-- ------------------------------------------------------------
-- 对应 backend/app/modules/article/models.py 中的 Difficulty 枚举
-- CEFR 标准等级：a1/a2/b1/b2/c1/c2
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'difficulty') THEN
        CREATE TYPE difficulty AS ENUM ('a1', 'a2', 'b1', 'b2', 'c1', 'c2');
    END IF;
END$$;

-- ------------------------------------------------------------
-- 5. articles 表
-- ------------------------------------------------------------
-- 对应 backend/app/modules/article/models.py 中的 Article 模型
CREATE TABLE IF NOT EXISTS articles (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title           VARCHAR(500) NOT NULL,
    content         TEXT         NOT NULL,
    summary         TEXT,
    source          VARCHAR(255),
    difficulty      difficulty   NOT NULL DEFAULT 'b1',
    word_count      INTEGER      NOT NULL DEFAULT 0,
    reading_time    INTEGER,
    cover_url       VARCHAR(512),
    tags            JSON         NOT NULL DEFAULT '[]',
    is_published    BOOLEAN      NOT NULL DEFAULT TRUE,
    view_count      INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_articles_difficulty   ON articles (difficulty);
CREATE INDEX IF NOT EXISTS ix_articles_is_published ON articles (is_published);
CREATE INDEX IF NOT EXISTS ix_articles_created_at   ON articles (created_at DESC);

-- updated_at 触发器
DROP TRIGGER IF EXISTS trg_articles_updated_at ON articles;
CREATE TRIGGER trg_articles_updated_at
    BEFORE UPDATE ON articles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ------------------------------------------------------------
-- 6. 测试文章数据（可选）
-- ------------------------------------------------------------
INSERT INTO articles (title, content, summary, source, difficulty, word_count, reading_time, tags, is_published)
VALUES
(
    'The Art of Reading Slowly',
    'In a world that prizes speed, reading slowly is a quiet act of rebellion. When we rush through paragraphs and skim through pages, we miss the subtle textures that make language beautiful. A slow reader notices the rhythm of sentences, the weight of individual words, and the spaces between ideas.

Reading slowly does not mean reading poorly. On the contrary, it often leads to deeper understanding. When you give yourself permission to pause, to reread a sentence, to let a paragraph sink in, you build a richer connection with the text. You start to hear the author''s voice rather than just processing their arguments.

Research suggests that slow reading improves comprehension, retention, and even empathy. When we read at a natural pace, our brains have time to form associations, ask questions, and imagine scenes. We become participants in the text rather than mere consumers of information.

Try this: the next time you open an article, set a timer for twenty minutes and read only half as much as you normally would. Notice what you gain — the details, the nuances, the pleasure of the words themselves. Reading slowly is not about doing less. It is about experiencing more.',
    'An essay on the benefits of reading at a slower pace, arguing that it improves comprehension, retention, and empathy.',
    'Reading Quarterly',
    'b1',
    185,
    2,
    '["reading", "habits", "essay"]',
    TRUE
),
(
    'Why Birds Migrate: A Journey Across Continents',
    'Every autumn, millions of birds embark on extraordinary journeys across oceans, deserts, and mountain ranges. The Arctic Tern, for example, travels from its breeding grounds in the Arctic to the Antarctic and back each year — a round trip of over 70,000 kilometers. This is the longest regular migration of any animal on Earth.

But why do birds migrate? The primary reasons are food and breeding. As temperatures drop in the northern hemisphere, insects die off and plants stop producing fruit. Birds that depend on these food sources must move to warmer regions where food remains abundant. Spring migration reverses this pattern, as birds return to northern breeding grounds where longer days and abundant insects provide ideal conditions for raising young.

Navigation is one of the most fascinating aspects of bird migration. Birds use multiple cues to find their way: the position of the sun and stars, Earth''s magnetic field, landmarks like coastlines and rivers, and even olfactory maps. Some species, like homing pigeons, can also detect infrasound — low-frequency sounds that travel vast distances.

Climate change is disrupting these ancient patterns. Rising temperatures cause plants to bloom earlier and insects to emerge sooner, creating a mismatch between migrants'' arrival times and the availability of their food sources. Scientists are tracking these changes using GPS tags and satellite data, building a clearer picture of how migration is shifting in response to a warming world.',
    'An exploration of bird migration patterns, navigation methods, and the impact of climate change.',
    'Nature Today',
    'b2',
    240,
    3,
    '["science", "nature", "animals"]',
    TRUE
),
(
    'The Psychology of Habit Formation',
    'Habits are the invisible architecture of daily life. Research from Duke University suggests that about 40 percent of our daily actions are driven by habit rather than conscious decision. Understanding how habits form — and how to change them — is one of the most practical insights psychology has to offer.

The habit loop, popularized by Charles Duhigg, consists of three components: a cue, a routine, and a reward. The cue is a trigger that initiates the behavior. The routine is the behavior itself. The reward is the positive outcome that reinforces the loop. Over time, this loop becomes increasingly automatic, eventually requiring little to no conscious effort.

Building a new habit requires making the cue obvious, the routine easy, and the reward satisfying. James Clear, author of Atomic Habits, recommends starting with a version of the habit that takes just two minutes. Want to read more? Start with one page. Want to exercise? Start with a two-minute walk. The goal is not the action itself but the establishment of the identity: you become someone who reads, who exercises.

Breaking a bad habit reverses the process: make the cue invisible, the routine difficult, and the reward unsatisfying. This is why environment design is so powerful — it is easier to avoid temptation than to resist it.

Consistency matters more than intensity. Missing a day is fine, but never miss two in a row. The brain learns from patterns, not exceptions.',
    'A guide to understanding and applying the psychology of habit formation in daily life.',
    'Mind Weekly',
    'b2',
    275,
    3,
    '["psychology", "self-improvement", "habits"]',
    TRUE
),
(
    'Why workers are nostalgic for life before AI',
    'Do you miss your old working life, the one before AI muscled in? Many do. Job hunters complain of the lack of the human touch as algorithms screen their applications and interviews are conducted by robo‑recruiters. Some lament that generative AI has intensified work rather than given them room to breathe.
In one study, “employees worked at a faster pace [and] took on a broader scope of tasks” due to AI. Others spurn it altogether, opting out of automated shortcuts because it makes them lazy‑brained and contaminates their thinking.

Almost two‑thirds (65 per cent) of white‑collar workers regularly yearn for their old working life, according to consultancy Adaptavist. About a third would ditch GenAI for inhibiting creativity, its research finds, while a similar proportion worry about misuse. Almost half say the need to fact‑check AI slop is adding to the slog — contrary to the grand promise that the future of work would dial down the drudgery.

While only a survey, the sentiment chimes. Putting together a coherent report at the touch of a button seems easy but verifying it, and pruning the dross, is a time suck. Just look at the proliferation of AI‑generated LinkedIn posts. It’s not just that they have become formulaic but also interminably long. The alternative to checking is ridicule and even sanctions, as demonstrated by lawyers and consultants upbraided for including hallucinated cases in their legal arguments and reports.

The impact of the technology on creativity is worrying. Research into creative writing among the general population rather than professional novelists finds that GenAI may inspire more plot twists, but overall leads to a duplication of ideas and a homogeneity of stories. Another study on innovation by the Wharton School at the University of Pennsylvania found similar results — while the ideas improved, the diversity weakened, leading one author to warn that “if you rely on ChatGPT as your only creative adviser, you’ll soon run out of ideas, because they’re too similar to each other”.

Employers flip‑flopping AI policies have also discombobulated staff. First encouraged to use the technology to automate tasks and experiment widely, employees are now being asked to rein it in to control costs as tech companies switch to token‑based billing. This is even before moving on to fears over job losses, ethical and environmental issues. Is it any wonder some crave a pre‑AI workplace? In May, the former Google chief executive Eric Schmidt was booed by graduating students while delivering his commencement speech to the University of Arizona, warning them not to spurn the AI revolution. “When someone offers you a seat on the rocket ship, you do not ask which seat, you just get on. Graduates, the rocket ship is here,” he said.

Brian Merchant, author of Blood in the Machine, has drawn parallels between the 18th‑century protests of the Luddites and modern resistance to AI. Both are commonly misconstrued as technophobes. But students’ reaction to the ex‑Google boss and the yearning for a pre‑AI world do not necessarily mean outright rejection — rather an objection to how it is used. Why should a graduate strap themselves to a rocket without asking questions? Jason Dressel, chief executive of the History Factory, which works with brands on heritage and archives, says nostalgia speaks to a desire for “stability, agency and economic confidence” while navigating rapid change. “AI intensifies that feeling because it is reshaping not only how people work, but how their contribution is valued.”

As with all nostalgia, however, the risk is casting the past in rose hues. AI’s incursion into art and writing certainly increases cultural homogeneity and blandness built on stealing creators’ work to train large language models. But many consumers do not care and film, television and publishing executives were perfectly capable of putting out banal and repetitive content before AI came along. Not every creation is an experimental work of genius.

While there are very serious concerns about how young people will learn how to do their job when the basic tasks can be done by AI, is it really the case that the apprenticeship model in banks and law firms of making graduates repeat a monotonous task 1,000 times was the best way? Or could older executives’ affection for their distant youth be muddying their view?
Scrutinising the past is a useful way to clarify the bits of work we want to keep and which to ditch — but only if we are honest with ourselves.',
    '为什么AI时代，越来越多人想回到从前？',
    '金融时报',
    'c1',
    749,
    4,
    '["AI"]',
    TRUE
)
ON CONFLICT DO NOTHING;

-- ------------------------------------------------------------
-- 7. 枚举类型：masterylevel
-- ------------------------------------------------------------
-- 对应 backend/app/modules/reading/models.py 中的 MasteryLevel 枚举
-- SQLAlchemy Enum(MasteryLevel) 默认使用类名小写 "masterylevel" 作为 PG 类型名
-- 单词掌握程度：new → learning → familiar → mastered
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'masterylevel') THEN
        CREATE TYPE masterylevel AS ENUM ('new', 'learning', 'familiar', 'mastered');
    END IF;
END$$;

-- ------------------------------------------------------------
-- 8. word_collections 表（生词本）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/reading/models.py 中的 WordCollection 模型
CREATE TABLE IF NOT EXISTS word_collections (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    word            VARCHAR(255) NOT NULL,
    context         TEXT         NOT NULL,
    article_id      BIGINT       REFERENCES articles(id),
    ai_explanation  TEXT,
    mastery_level   masterylevel   NOT NULL DEFAULT 'new',
    study_count     INTEGER      NOT NULL DEFAULT 0,
    last_studied_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_word_collections_user_id ON word_collections (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_word_collections_user_word ON word_collections (user_id, word);

-- updated_at 触发器
DROP TRIGGER IF EXISTS trg_word_collections_updated_at ON word_collections;
CREATE TRIGGER trg_word_collections_updated_at
    BEFORE UPDATE ON word_collections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ------------------------------------------------------------
-- 9. sentence_collections 表（句子收藏）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/reading/models.py 中的 SentenceCollection 模型
CREATE TABLE IF NOT EXISTS sentence_collections (
    id          BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT       NOT NULL REFERENCES users(id),
    sentence    TEXT         NOT NULL,
    article_id  BIGINT       REFERENCES articles(id),
    note        TEXT,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_sentence_collections_user_id ON sentence_collections (user_id);

-- ------------------------------------------------------------
-- 10. reading_histories 表（阅读历史）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/reading/models.py 中的 ReadingHistory 模型
CREATE TABLE IF NOT EXISTS reading_histories (
    id               BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          BIGINT       NOT NULL REFERENCES users(id),
    article_id       BIGINT       NOT NULL REFERENCES articles(id),
    started_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ended_at         TIMESTAMPTZ,
    duration_seconds INTEGER,
    read_count       INTEGER      NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_reading_histories_user_id ON reading_histories (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reading_histories_user_article ON reading_histories (user_id, article_id);

-- ------------------------------------------------------------
-- 11. ai_conversations 表（AI 对话记录）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/ai/models.py 中的 AiConversation 模型
-- history_id 将对话消息关联到具体的阅读会话，使每次阅读的问答
-- 记录可以被独立提取用于生成阅读总结。
CREATE TABLE IF NOT EXISTS ai_conversations (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    article_id      BIGINT       NOT NULL REFERENCES articles(id),
    history_id      BIGINT       REFERENCES reading_histories(id),
    role            VARCHAR(20)  NOT NULL,
    content         TEXT         NOT NULL,
    is_summarized   BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_ai_conversations_user_id    ON ai_conversations (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_conversations_article_id ON ai_conversations (article_id);
CREATE INDEX IF NOT EXISTS ix_ai_conversations_history_id ON ai_conversations (history_id);

-- ------------------------------------------------------------
-- 12. ai_memories 表（AI 长期记忆）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/ai/models.py 中的 AiMemory 模型
-- 当未摘要的对话消息超过 token 阈值时，最旧的一批消息会被
-- LLM 压缩为摘要存入此表。memory_type 区分摘要/事实/错误/偏好。
CREATE TABLE IF NOT EXISTS ai_memories (
    id           BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id      BIGINT       NOT NULL REFERENCES users(id),
    article_id   BIGINT       REFERENCES articles(id),
    memory_type  VARCHAR(30)  NOT NULL,
    content      TEXT         NOT NULL,
    importance   FLOAT        NOT NULL DEFAULT 0.5,
    token_count  INTEGER      NOT NULL DEFAULT 0,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_ai_memories_user_id    ON ai_memories (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_memories_article_id ON ai_memories (article_id);

-- ------------------------------------------------------------
-- 13. user_profiles 表（用户画像）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/ai/models.py 中的 UserProfile 模型
-- 每个用户一行，由 LLM 从积累的记忆中定期生成/更新。
-- profile_summary 是自然语言画像，注入 system prompt 供 AI 个性化响应。
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id          BIGINT       PRIMARY KEY REFERENCES users(id),
    profile_summary  TEXT,
    strengths        JSON         NOT NULL DEFAULT '[]',
    weaknesses       JSON         NOT NULL DEFAULT '[]',
    learning_style   VARCHAR(50),
    interests        JSON         NOT NULL DEFAULT '[]',
    common_mistakes  JSON         NOT NULL DEFAULT '[]',
    message_count    INTEGER      NOT NULL DEFAULT 0,
    last_updated_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------------------
-- 14. ai_activities 表（AI 交互活动记录）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/ai/models.py 中的 AiActivity 模型
-- 每次 AI 交互（查词、分析句子、翻译、段落摘要、问答）都会记录一条
-- 活动日志，关联到具体的阅读会话。这些数据用于生成阅读总结。
CREATE TABLE IF NOT EXISTS ai_activities (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    article_id      BIGINT       NOT NULL REFERENCES articles(id),
    history_id      BIGINT       REFERENCES reading_histories(id),
    activity_type   VARCHAR(30)  NOT NULL,
    content         TEXT         NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_ai_activities_user_id    ON ai_activities (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_activities_article_id ON ai_activities (article_id);
CREATE INDEX IF NOT EXISTS ix_ai_activities_history_id ON ai_activities (history_id);

-- ------------------------------------------------------------
-- 15. reading_summaries 表（阅读总结）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/ai/models.py 中的 ReadingSummary 模型
-- 每个阅读会话最多保留一条总结，重新生成会覆盖旧的。
-- activity_stats 存储各类活动的统计数据（查词数、句子数、问答数、时长）。
CREATE TABLE IF NOT EXISTS reading_summaries (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    article_id      BIGINT       NOT NULL REFERENCES articles(id),
    history_id      BIGINT       NOT NULL REFERENCES reading_histories(id),
    content         TEXT         NOT NULL,
    activity_stats  JSON         NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引与约束
CREATE INDEX IF NOT EXISTS ix_reading_summaries_user_id ON reading_summaries (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_reading_summaries_history ON reading_summaries (history_id);

-- ------------------------------------------------------------
-- 16. reading_quizzes 表（阅读练习题）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/ai/models.py 中的 ReadingQuiz 模型
-- 每个阅读会话可以有多份练习题。questions 是 JSON 数组，每元素含
-- 题目、选项、正确答案和解析。user_answers 在提交前为 NULL。
CREATE TABLE IF NOT EXISTS reading_quizzes (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    article_id      BIGINT       NOT NULL REFERENCES articles(id),
    history_id      BIGINT       NOT NULL REFERENCES reading_histories(id),
    questions       JSON         NOT NULL DEFAULT '[]',
    user_answers    JSON,
    score           INTEGER,
    total           INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_reading_quizzes_user_id ON reading_quizzes (user_id);

-- ------------------------------------------------------------
-- 17. agent_conversations 表（Agent 多轮对话容器）
-- ------------------------------------------------------------
-- 对应 backend/app/agents/modules/models.py 中的 AgentConversation 模型
-- 一个对话包含多条 agent_sessions（Q&A 对），用户点击"新对话"
-- 时创建新的 conversation，后续消息都属于同一 conversation。
CREATE TABLE IF NOT EXISTS agent_conversations (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    title           VARCHAR(200) NOT NULL DEFAULT '新对话',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_agent_conversations_user_id ON agent_conversations (user_id);

-- updated_at 触发器
DROP TRIGGER IF EXISTS trg_agent_conversations_updated_at ON agent_conversations;
CREATE TRIGGER trg_agent_conversations_updated_at
    BEFORE UPDATE ON agent_conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ------------------------------------------------------------
-- 18. agent_sessions 表（Agent 执行会话）
-- ------------------------------------------------------------
-- 对应 backend/app/agents/modules/models.py 中的 AgentSession 模型
-- 每当用户向 Agent 发送一条消息时创建一条会话记录，记录用户输入、
-- Agent 最终回答、总步数和执行状态（completed/failed/max_iterations）。
-- conversation_id 将会话关联到所属的多轮对话（可为 NULL，兼容旧数据）。
CREATE TABLE IF NOT EXISTS agent_sessions (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         BIGINT       NOT NULL REFERENCES users(id),
    article_id      BIGINT       REFERENCES articles(id),
    history_id      BIGINT       REFERENCES reading_histories(id),
    conversation_id BIGINT       REFERENCES agent_conversations(id),
    agent_type      VARCHAR(50)  NOT NULL,
    user_message    TEXT         NOT NULL,
    final_answer    TEXT,
    total_steps     INTEGER      NOT NULL DEFAULT 0,
    status          VARCHAR(20)  NOT NULL DEFAULT 'completed',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_agent_sessions_user_id         ON agent_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_agent_sessions_conversation_id ON agent_sessions (conversation_id);

-- ------------------------------------------------------------
-- 19. agent_steps 表（Agent 执行步骤记录）
-- ------------------------------------------------------------
-- 对应 backend/app/agents/modules/models.py 中的 AgentStepRecord 模型
-- 每个会话包含多个步骤记录，按 step_order 排列。步骤类型包括
-- thinking（思考）、tool_call（工具调用）和 tool_result（工具结果）。
-- tool_arguments 和 tool_result 以 JSON 格式存储，便于后续分析和回放。
CREATE TABLE IF NOT EXISTS agent_steps (
    id              BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id      BIGINT       NOT NULL REFERENCES agent_sessions(id),
    step_order      INTEGER      NOT NULL,
    step_type       VARCHAR(20)  NOT NULL,
    content         TEXT,
    tool_name       VARCHAR(100),
    tool_arguments  JSON,
    tool_result     JSON,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_agent_steps_session_id ON agent_steps (session_id);

-- ------------------------------------------------------------
-- 20. 验证查询
-- ------------------------------------------------------------
-- 执行后可运行以下语句确认表和数据：
--   SELECT id, email, username, english_level FROM users;
--   SELECT id, title, difficulty, word_count, tags FROM articles;
--   SELECT DISTINCT jsonb_array_elements_text(tags) AS tag FROM articles ORDER BY tag;
--   SELECT id, word, mastery_level, study_count FROM word_collections;
--   SELECT id, sentence FROM sentence_collections;
--   SELECT id, article_id, duration_seconds FROM reading_histories;
--   SELECT id, article_id, role FROM ai_conversations;
--   SELECT id, user_id, activity_type FROM ai_activities;
--   SELECT id, history_id, LEFT(content, 50) FROM reading_summaries;
--   SELECT id, history_id, score, total FROM reading_quizzes;
--   SELECT id, user_id, title FROM agent_conversations;
--   SELECT id, conversation_id, agent_type, status, total_steps FROM agent_sessions;
--   SELECT id, session_id, step_order, step_type, tool_name FROM agent_steps;
