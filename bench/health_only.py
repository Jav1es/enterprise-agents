"""只压 /health 的压测脚本：用于隔离实验，排除应用逻辑影响。

与 locustfile.py 的区别：不请求任何业务接口（/v1/chat、/v1/chat/stream），
因此不触发 Chroma 检索、记忆读写、编排与 LLM 调用。
若多 worker 下这个脚本的吞吐同样下降，说明瓶颈在压测端或本机调度，而非应用架构。
"""

from __future__ import annotations

from locust import HttpUser, between, task


class HealthOnlyUser(HttpUser):
    wait_time = between(0, 0.1)

    @task
    def health(self):
        with self.client.get("/health", name="GET /health", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"HTTP {r.status_code}")
