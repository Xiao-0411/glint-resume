"""清理 jobs 表中的脏数据。

三类脏数据：
1. 占位公司名（"未知公司"）——卡片解析失败的产物，无法用于展示。
2. 关键字段全空——薪资、地点、经验、学历都为空的记录没有筛选价值。
3. 卡片文本冒充 JD——description 里重复出现岗位名/公司/薪资，是列表页
   整块 innerText 被写进详情字段，喂给模型会污染匹配结果。

用法：
    python scripts/clean_dirty_jobs.py --dry-run   # 只统计不删除
    python scripts/clean_dirty_jobs.py             # 实际执行
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.models.db_models import Job  # noqa: E402
from app.crawlers.card_parser import publishability_reason  # noqa: E402

JD_MARKERS = ("岗位职责", "职位职责", "任职要求", "职位要求", "职位描述", "工作职责", "岗位要求")


def is_unpublishable(job: Job) -> bool:
    return bool(publishability_reason({
        "title": job.title,
        "platform_job_id": job.platform_job_id,
        "company": job.company,
        "salary": job.salary,
        "location": job.location,
    }))


def is_empty_shell(job: Job) -> bool:
    """薪资、地点、经验、学历全空 —— 没有任何筛选维度。"""
    return not any(
        (getattr(job, field) or "").strip()
        for field in ("salary", "location", "experience", "education")
    )


def is_card_text_description(job: Job) -> bool:
    """description 是列表卡片文本而非真实 JD。"""
    description = (job.description or "").strip()
    if not description:
        return False
    if len(description) < 120:
        # 过短的描述本就不可用，直接视为需清空。
        return True
    if any(marker in description for marker in JD_MARKERS):
        return False
    # 长文本但不含任何 JD 结构标记：检查是否在重复卡片字段。
    repeated = sum(
        bool(value and str(value).strip() and str(value).strip() in description)
        for value in (job.title, job.company, job.salary)
    )
    return repeated >= 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        jobs = db.query(Job).all()
        to_delete: list[Job] = []
        to_blank: list[Job] = []

        for job in jobs:
            if is_unpublishable(job) or is_empty_shell(job):
                to_delete.append(job)
            elif is_card_text_description(job):
                to_blank.append(job)

        print(f"扫描 {len(jobs)} 条职位")
        print(f"  待删除（缺少岗位名、公司、薪资或地点）: {len(to_delete)}")
        print(f"  待清空 description（卡片文本冒充 JD）: {len(to_blank)}")

        by_platform: dict[str, int] = {}
        for job in to_delete:
            by_platform[job.platform] = by_platform.get(job.platform, 0) + 1
        for platform, count in sorted(by_platform.items()):
            print(f"    删除明细 {platform}: {count}")

        if args.dry_run:
            print("\n[dry-run] 未写库")
            return 0

        for job in to_delete:
            db.delete(job)
        for job in to_blank:
            job.description = ""
        db.commit()
        print(f"\n已删除 {len(to_delete)} 条，已清空 {len(to_blank)} 条 description")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"清理失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
