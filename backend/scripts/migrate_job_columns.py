"""为 jobs 表补齐分类与 JD 补全所需的列。

SQLAlchemy 的 create_all 不会给已存在的表加列，因此用显式迁移。
脚本可重复执行：已存在的列会被跳过。

用法：
    python scripts/migrate_job_columns.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.database import engine  # noqa: E402

COLUMNS = [
    ("category", "VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'AI 分类的岗位大类'"),
    ("job_level", "VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'AI 判定的职级'"),
    ("industry", "VARCHAR(32) NOT NULL DEFAULT '' COMMENT 'AI 判定的所属行业'"),
    ("detail_status", "VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'JD 补全状态'"),
]
INDEXES = [
    ("idx_jobs_category", "category"),
    ("idx_jobs_detail_status", "detail_status"),
]


def existing_columns(conn) -> set[str]:
    rows = conn.execute(text("SHOW COLUMNS FROM jobs"))
    return {row[0] for row in rows}


def existing_indexes(conn) -> set[str]:
    rows = conn.execute(text("SHOW INDEX FROM jobs"))
    return {row[2] for row in rows}


def main() -> int:
    with engine.begin() as conn:
        present = existing_columns(conn)
        for name, ddl in COLUMNS:
            if name in present:
                print(f"跳过已存在的列: {name}")
                continue
            conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}"))
            print(f"已添加列: {name}")

        present_idx = existing_indexes(conn)
        for index_name, column in INDEXES:
            if index_name in present_idx:
                print(f"跳过已存在的索引: {index_name}")
                continue
            conn.execute(text(f"CREATE INDEX {index_name} ON jobs ({column})"))
            print(f"已创建索引: {index_name}")

        # 存量记录：有可信 JD 的标记为 done，其余留 pending 等待补全。
        updated = conn.execute(text(
            "UPDATE jobs SET detail_status='done' "
            "WHERE CHAR_LENGTH(COALESCE(description,'')) >= 120 AND detail_status='pending'"
        )).rowcount
        print(f"存量已有 JD 标记为 done: {updated} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
