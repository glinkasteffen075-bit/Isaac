from __future__ import annotations

import asyncio
from executor import get_executor, Task, TaskType, TaskStatus
from memory import get_memory


async def _run_reliability() -> dict:
    from unittest.mock import patch
    from logic import QualityScore

    exe = get_executor()
    mem = get_memory()
    tid = "eval_reliability_checkpoint"
    task = Task(id=tid, typ=TaskType.CHAT, prompt="checkpoint test", beschreibung="checkpoint test")
    task.status = TaskStatus.RUNNING
    task.iteration = 2
    exe._tasks[tid] = task
    exe._checkpoint(task, "tool_running", tool_snapshot={"tool": "search_web"}, result_snapshot={"partial": True}, side_effect_refs=["search:checkpoint test"])
    cp = mem.get_latest_checkpoint(tid)
    task.status = TaskStatus.RESUMABLE
    ok_resume = exe.resume_task(tid)
    task2 = exe.get_task(tid)

    chat_tid = "eval_reliability_chat_resume"
    chat_task = Task(id=chat_tid, typ=TaskType.CHAT, prompt="Was ist 2+2?", beschreibung="chat resume eval")
    chat_task.status = TaskStatus.QUEUED
    exe._tasks[chat_tid] = chat_task
    calls = {"ai": 0}

    async def _flaky_ai(current_task):
        calls["ai"] += 1
        if calls["ai"] == 1:
            raise ConnectionError("relay timeout")
        current_task.antwort = "4"
        current_task.provider_used = "eval-mock"
        current_task.score = QualityScore(total=9.0)
        current_task.status = TaskStatus.DONE

    with patch.object(exe, "_execute_ai", side_effect=_flaky_ai):
        await exe._execute(chat_task)
    chat_resumable = chat_task.status == TaskStatus.RESUMABLE
    exe.resume_task(chat_tid)
    with patch.object(exe, "_execute_ai", side_effect=_flaky_ai):
        await exe._execute(exe.get_task(chat_tid))

    cases = [
        {"name": "checkpoint_written", "ok": bool(cp and cp.get("state_name") == "tool_running"), "detail": cp or {}},
        {"name": "task_resumable", "ok": bool(ok_resume and task2 and task2.status == TaskStatus.QUEUED), "detail": task2.to_dict() if task2 else {}},
        {
            "name": "interrupted_chat_resume_completes",
            "ok": chat_resumable and exe.get_task(chat_tid).status == TaskStatus.DONE,
            "detail": {"calls": calls["ai"], "status": exe.get_task(chat_tid).status.value},
        },
    ]
    passed = sum(1 for c in cases if c["ok"])
    return {"suite": "reliability", "passed": passed, "total": len(cases), "cases": cases}


def run() -> dict:
    return asyncio.run(_run_reliability())


if __name__ == "__main__":
    import json
    print(json.dumps(run(), ensure_ascii=False, indent=2))
