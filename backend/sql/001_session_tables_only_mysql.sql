-- MySQL tables only.
-- Use this when your MySQL account cannot CREATE DATABASE.
-- In phpMyAdmin, first click a database you already have permission to use,
-- then import this file into that selected database.

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(64) PRIMARY KEY,
  email VARCHAR(255) UNIQUE NULL,
  display_name VARCHAR(128) NOT NULL DEFAULT '',
  password_hash VARCHAR(255) NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'user',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX ix_users_email (email),
  INDEX ix_users_role (role),
  INDEX ix_users_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS email_verification_codes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL,
  purpose VARCHAR(32) NOT NULL DEFAULT 'register',
  code_hash VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  sent_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX ix_email_codes_email (email),
  INDEX ix_email_codes_purpose (purpose)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
  id VARCHAR(64) PRIMARY KEY,
  user_id VARCHAR(64) NULL,
  target_job VARCHAR(128) NOT NULL DEFAULT '',
  stage VARCHAR(32) NOT NULL DEFAULT 'basic_info',
  extracted JSON NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX ix_sessions_user_id (user_id),
  CONSTRAINT fk_sessions_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL,
  role VARCHAR(16) NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  INDEX ix_messages_session_id (session_id),
  CONSTRAINT fk_messages_session_id
    FOREIGN KEY (session_id) REFERENCES sessions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resumes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NULL,
  session_id VARCHAR(64) NULL,
  target_job VARCHAR(128) NOT NULL DEFAULT '',
  resume_json JSON NULL,
  quality_report_json JSON NULL,
  total_score INT NOT NULL DEFAULT 0,
  grade VARCHAR(16) NOT NULL DEFAULT '',
  source VARCHAR(32) NOT NULL DEFAULT 'chat',
  created_at DATETIME NOT NULL,
  INDEX ix_resumes_user_id (user_id),
  INDEX ix_resumes_session_id (session_id),
  CONSTRAINT fk_resumes_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_resumes_session_id
    FOREIGN KEY (session_id) REFERENCES sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS llm_usage_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id VARCHAR(64) NULL,
  session_id VARCHAR(64) NULL,
  endpoint VARCHAR(128) NOT NULL DEFAULT '',
  source VARCHAR(64) NOT NULL DEFAULT '',
  model VARCHAR(128) NOT NULL DEFAULT '',
  prompt_tokens INT NOT NULL DEFAULT 0,
  completion_tokens INT NOT NULL DEFAULT 0,
  total_tokens INT NOT NULL DEFAULT 0,
  cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'success',
  error_message TEXT NULL,
  created_at DATETIME NOT NULL,
  INDEX ix_llm_usage_user_id (user_id),
  INDEX ix_llm_usage_session_id (session_id),
  INDEX ix_llm_usage_endpoint (endpoint),
  INDEX ix_llm_usage_status (status),
  INDEX ix_llm_usage_created_at (created_at),
  CONSTRAINT fk_llm_usage_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_llm_usage_session_id
    FOREIGN KEY (session_id) REFERENCES sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO users (id, email, display_name, created_at, updated_at)
VALUES ('anonymous', NULL, '匿名用户', UTC_TIMESTAMP(), UTC_TIMESTAMP());
