"""
内存 Session 存储 —— 简单的 dict,进程重启即清空
demo 阶段够用,后续要持久化时直接换成 SQLite/Redis
"""
from typing import Dict, List, Any, Optional
from threading import Lock
import time


class SessionStore:
    def __init__(self):
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: str, target_job: str = "") -> Dict[str, Any]:
        with self._lock:
            if session_id not in self._data:
                self._data[session_id] = {
                    "session_id": session_id,
                    "target_job": target_job,
                    "created_at": time.time(),
                    "messages": [],   # [{"role": "user"|"assistant", "content": "..."}]
                    "stage": "basic_info",
                    "extracted": {}    # 增量抽取的结构化数据
                }
            elif target_job and not self._data[session_id].get("target_job"):
                self._data[session_id]["target_job"] = target_job
            return self._data[session_id]

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._data.get(session_id)

    def append_message(self, session_id: str, role: str, content: str):
        with self._lock:
            sess = self._data.get(session_id)
            if sess is None:
                return
            sess["messages"].append({"role": role, "content": content})

    def set_stage(self, session_id: str, stage: str):
        with self._lock:
            sess = self._data.get(session_id)
            if sess is not None:
                sess["stage"] = stage

    def update_extracted(self, session_id: str, info: Dict[str, Any]):
        with self._lock:
            sess = self._data.get(session_id)
            if sess is not None:
                sess["extracted"].update(info)

    def list_sessions(self) -> List[str]:
        return list(self._data.keys())

    def reset(self, session_id: str):
        with self._lock:
            self._data.pop(session_id, None)


# 全局单例
session_store = SessionStore()
