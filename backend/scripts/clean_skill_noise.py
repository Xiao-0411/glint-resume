"""清除 requirements 中混入的招聘话术。

首批分类实跑时，模型把"高底薪高提成，无外呼""定期团建，退役军人"这类
招聘卖点当成技能写进了 requirements，而 requirements 直接参与匹配度打分。
分类器已在 _normalize 里加了过滤，本脚本用于清洗此前已经入库的记录。

用法：
    python scripts/clean_skill_noise.py --dry-run   # 只列出将被清除的条目
    python scripts/clean_skill_noise.py             # 实际执行
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.models.db_models import Job  # noqa: E402
from app.services.job_classifier import _looks_like_noise  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = db.query(Job).filter(Job.requirements.isnot(None)).all()
        affected = 0
        removed_total = 0

        for row in rows:
            current = [str(item).strip() for item in (row.requirements or []) if str(item).strip()]
            if not current:
                continue
            kept = [item for item in current if not _looks_like_noise(item)]
            if len(kept) == len(current):
                continue

            affected += 1
            removed = [item for item in current if item not in kept]
            removed_total += len(removed)
            if args.dry_run and affected <= 15:
                print(f"[{row.id}] {row.title[:36]}")
                print(f"    清除: {removed}")
                print(f"    保留: {kept}")
            if not args.dry_run:
                row.requirements = kept

        if args.dry_run:
            print(f"\n[dry-run] 将影响 {affected} 条记录，清除 {removed_total} 个噪声条目")
            return 0

        db.commit()
        print(f"已清理 {affected} 条记录，移除 {removed_total} 个噪声条目")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"清理失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
