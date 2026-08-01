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
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_reading_histories_user_id ON reading_histories (user_id);

-- ------------------------------------------------------------
-- 11. ai_conversations 表（AI 对话记录）
-- ------------------------------------------------------------
-- 对应 backend/app/modules/reading/models.py 中的 AiConversation 模型
CREATE TABLE IF NOT EXISTS ai_conversations (
    id          BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id     BIGINT       NOT NULL REFERENCES users(id),
    article_id  BIGINT       NOT NULL REFERENCES articles(id),
    role        VARCHAR(20)  NOT NULL,
    content     TEXT         NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_ai_conversations_user_id    ON ai_conversations (user_id);
CREATE INDEX IF NOT EXISTS ix_ai_conversations_article_id ON ai_conversations (article_id);

-- ------------------------------------------------------------
-- 12. 验证查询
-- ------------------------------------------------------------
-- 执行后可运行以下语句确认表和数据：
--   SELECT id, email, username, english_level FROM users;
--   SELECT id, title, difficulty, word_count, tags FROM articles;
--   SELECT DISTINCT jsonb_array_elements_text(tags) AS tag FROM articles ORDER BY tag;
--   SELECT id, word, mastery_level, study_count FROM word_collections;
--   SELECT id, sentence FROM sentence_collections;
--   SELECT id, article_id, duration_seconds FROM reading_histories;
--   SELECT id, article_id, role FROM ai_conversations;
