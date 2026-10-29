-- Marrow 数据库schema，对应产品文档v0.2第4.4节
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE cores (
    id TEXT PRIMARY KEY,                  -- 例如 'ladr-3a-3c'
    topic TEXT NOT NULL,
    source_book TEXT NOT NULL,
    source_section TEXT NOT NULL,
    active_version_id INTEGER,             -- 指向 core_versions.id，当前生效版本
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE core_versions (
    id SERIAL PRIMARY KEY,
    core_id TEXT NOT NULL REFERENCES cores(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    data JSONB NOT NULL,                   -- 完整core内容，符合 marrow-core-schema-v1
    extracted_by TEXT NOT NULL,            -- 'claude' / 'codex' / 其他harness标识
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending','approved','rejected')),
    reviewed_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (core_id, version_number)
);

ALTER TABLE cores
    ADD CONSTRAINT fk_active_version
    FOREIGN KEY (active_version_id) REFERENCES core_versions(id);

CREATE TABLE user_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    core_id TEXT NOT NULL REFERENCES cores(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (status IN ('not_started','in_progress','completed')),
    last_interacted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, core_id)
);

CREATE TABLE case_attempts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    core_id TEXT NOT NULL REFERENCES cores(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,                 -- 对应core数据里cases[].id
    submitted_answer JSONB,
    is_correct BOOLEAN,
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_core_versions_core_id ON core_versions(core_id);
CREATE INDEX idx_user_progress_user ON user_progress(user_id);
CREATE INDEX idx_case_attempts_user_core ON case_attempts(user_id, core_id);
