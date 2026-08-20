"""为库中未分类的岗位补跑 AI 分类。

新抓取的岗位在入库前已同步分类；本脚本用于处理存量数据，
或分类接口配置好之前抓到的岗位。

用法：
    python scripts/classify_jobs.py --dry-run      # 只统计待分类数量
    python scripts/classify_jobs.py --limit 200    # 分类最近 200 条
    python scripts/classify_jobs.py                # 分类全部未分类岗位
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.models.db_models import Job  # noqa: E402
from app.services import job_classifier  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条，0 表示全部")
    parser.add_argument("--batch", type=int, default=20, help="单次请求携带的岗位数")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不调用接口")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = (
            db.query(Job)
            .filter(Job.is_active == True, (Job.category == "") | (Job.category.is_(None)))
            .order_by(Job.crawled_at.desc())
        )
        total = query.count()
        if args.limit > 0:
            query = query.limit(args.limit)
        rows = query.all()

        print(f"未分类岗位: {total} 条，本次处理 {len(rows)} 条")
        if args.dry_run:
            print("[dry-run] 未调用接口")
            return 0
        if not rows:
            return 0

        if not job_classifier.is_configured():
            print("岗位分类接口未配置，请先在 backend/.env 填写：", file=sys.stderr)
            print("  JOB_CLASSIFIER_BASE_URL / JOB_CLASSIFIER_API_KEY / JOB_CLASSIFIER_MODEL", file=sys.stderr)
            return 1

        payloads = [
            {
                "title": row.title,
                "company": row.company,
                "tags": row.tags or [],
                "description": row.description or "",
                "requirements": row.requirements or [],
            }
            for row in rows
        ]
        results = job_classifier.classify_all(payloads, batch_size=max(1, args.batch))

        updated = 0
        for row, payload, result in zip(rows, payloads, results):
            if not result:
                continue
            merged = job_classifier.apply_classification(payload, result)
            row.category = merged.get("category", "")
            row.job_level = merged.get("job_level", "")
            row.industry = merged.get("industry", "")
            if merged.get("requirements"):
                row.requirements = merged["requirements"]
            updated += 1
        db.commit()
        print(f"已分类 {updated}/{len(rows)} 条")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"分类失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
