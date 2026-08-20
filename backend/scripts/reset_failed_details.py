"""把 JD 补全失败的岗位重置为待补状态。

失败可能只是当时 Chrome 没开或网络抖动，不应永久放弃。
定期跑一次即可让这些岗位重新排队。

用法：
    python scripts/reset_failed_details.py             # 重置全部 failed
    python scripts/reset_failed_details.py --limit 200 # 只重置最近 200 条
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.models.db_models import Job  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="最多重置多少条，0 表示不限")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Job).filter(Job.detail_status == "failed").order_by(Job.crawled_at.desc())
        if args.limit > 0:
            query = query.limit(args.limit)
        rows = query.all()
        for row in rows:
            row.detail_status = "pending"
        db.commit()
        print(f"已重置 {len(rows)} 条失败记录为 pending")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"重置失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
