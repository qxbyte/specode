'''task_swarm package public surface.

外部消费者：scripts/task_swarm.py launcher 调 `task_swarm.cli.main()`。
测试侧（test_task_swarm_state / outbox / writeback / parse_md）按
`from task_swarm._state import ...` 等子模块路径直接 import。

本 __init__.py 故意保持空白——子模块按需被 cli 或测试加载，无 package-level
公共 API 需 re-export（与 spec_session/__init__.py 不同，spec_session 那边是
为兼容 spec_status.py:25 的旧 `from spec_session import …` 而 re-export）。

stdlib-only。
'''
