"""全量抓取的滚动游标。

单轮抓不完全部「城市 × 关键词」组合，因此每轮只取一个切片并把位置持久化；
进程重启后从上次位置继续，避免永远重复抓开头那几项。

城市与关键词游标推进速度不同：城市每轮推进，关键词只在城市走完一整圈时推进一格，
这样组合覆盖顺序是「先把所有城市配当前关键词跑完，再换下一个关键词」。
"""
from __future__ import annotations

from typing import Sequence

from app.core.database import SessionLocal
from app.models.db_models import CrawlCursor
from app.core.logging_config import get_logger

logger = get_logger("glint.crawler.cursor")


def _read_position(scope: str) -> tuple[int, int]:
    db = SessionLocal()
    try:
        row = db.query(CrawlCursor).filter(CrawlCursor.scope == scope).first()
        return (row.position, row.cycle) if row else (0, 0)
    finally:
        db.close()


def _write_position(scope: str, position: int, cycle: int) -> None:
    db = SessionLocal()
    try:
        row = db.query(CrawlCursor).filter(CrawlCursor.scope == scope).first()
        if row is None:
            row = CrawlCursor(scope=scope)
            db.add(row)
        row.position = position
        row.cycle = cycle
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("cursor_write_failed", extra={"scope": scope, "error": str(exc)})
    finally:
        db.close()


def next_slice(scope: str, pool: Sequence[str], size: int) -> list[str]:
    """取出下一段并推进游标，走到末尾时回绕并记一次整轮完成。

    数据库不可用时退化为返回头部切片：抓取降级为重复覆盖，但不至于中断。
    """
    if not pool:
        return []
    size = max(1, min(size, len(pool)))
    try:
        position, cycle = _read_position(scope)
    except Exception as exc:  # noqa: BLE001
        logger.error("cursor_read_failed", extra={"scope": scope, "error": str(exc)})
        return list(pool[:size])

    position %= len(pool)
    end = position + size
    if end <= len(pool):
        selected = list(pool[position:end])
        next_position = end % len(pool)
        completed = next_position == 0
    else:
        # 回绕：尾部接头部，保证每轮切片长度一致。
        wrapped = end - len(pool)
        selected = list(pool[position:]) + list(pool[:wrapped])
        next_position = wrapped
        completed = True

    _write_position(scope, next_position, cycle + (1 if completed else 0))
    return selected


def slice_at(pool: Sequence[str], offset: int, size: int) -> list[str]:
    """从指定偏移取一段，越界时回绕。不读写游标。"""
    if not pool:
        return []
    size = max(1, min(size, len(pool)))
    start = offset % len(pool)
    end = start + size
    if end <= len(pool):
        return list(pool[start:end])
    return list(pool[start:]) + list(pool[: end - len(pool)])


def city_cycles() -> int:
    """城市游标已完成的整圈数，用于决定关键词偏移。"""
    try:
        return _read_position("city")[1]
    except Exception as exc:  # noqa: BLE001
        logger.error("cursor_cycle_read_failed", extra={"error": str(exc)})
        return 0


def cursor_snapshot() -> dict:
    """当前游标状态，供监控接口展示抓取进度。"""
    db = SessionLocal()
    try:
        return {
            row.scope: {"position": row.position, "cycle": row.cycle}
            for row in db.query(CrawlCursor).all()
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("cursor_snapshot_failed", extra={"error": str(exc)})
        return {}
    finally:
        db.close()
