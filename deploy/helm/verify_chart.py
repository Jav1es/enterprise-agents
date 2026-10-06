"""离线校验 Helm 渲染结果：YAML 可解析 + k8s 对象结构正确 + 无明文凭据 + 探针/HPA/安全上下文到位。"""
import subprocess, sys, io, os

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
try:
    import yaml
except ImportError:
    print("缺 PyYAML，先装"); sys.exit(2)

HELM = os.path.join(os.environ["TEMP"], "helm.exe")
CHART = r"D:\Jav1e Flies\00-工作区\enterprise-agents\deploy\helm"

# 生产路径：必须走已有 Secret，不允许明文回退
r = subprocess.run(
    [HELM, "template", "ea", CHART,
     "--set", "secrets.create=false",
     "--set", "secrets.llmApiKey.existingSecret=ea-llm-secret"],
    capture_output=True, text=True, encoding="utf-8")
if r.returncode != 0:
    print("渲染失败：", r.stderr[-400:]); sys.exit(2)
docs = [d for d in yaml.safe_load_all(r.stdout) if d]
print(f"渲染对象数: {len(docs)}（生产路径：走已有 Secret）")

# 守卫必须生效：既不给 existingSecret 也不开 create 时必须渲染失败
guard = subprocess.run([HELM, "template", "ea", CHART],
                       capture_output=True, text=True, encoding="utf-8")
GUARD_OK = guard.returncode != 0 and "existingSecret" in guard.stderr
print(f"明文回退守卫: {'生效（拒绝渲染）' if GUARD_OK else '未生效 ← 危险'}")

kinds = {d["kind"] for d in docs}
expect = {"Deployment", "Service", "HorizontalPodAutoscaler", "ConfigMap",
          "PersistentVolumeClaim", "Secret"}
print("kind 集合:", sorted(kinds))
missing = expect - kinds
print("缺失 kind:", missing or "无")

dep = next(d for d in docs if d["kind"] == "Deployment")
c = dep["spec"]["template"]["spec"]["containers"][0]

checks = []
def ck(name, cond, detail=""):
    checks.append((name, cond, detail))

ck("探针 liveness /health", c["livenessProbe"]["httpGet"]["path"] == "/health",
   c["livenessProbe"]["httpGet"]["path"])
ck("探针 readiness /health", c["readinessProbe"]["httpGet"]["path"] == "/health",
   c["readinessProbe"]["httpGet"]["path"])
ck("容器端口 8080", c["ports"][0]["containerPort"] == 8080, str(c["ports"][0]["containerPort"]))
ck("非 root 运行", dep["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"] is True)
ck("禁止提权", c["securityContext"]["allowPrivilegeEscalation"] is False)
ck("resources 有 requests+limits", "requests" in c["resources"] and "limits" in c["resources"])

hpa = next(d for d in docs if d["kind"] == "HorizontalPodAutoscaler")
cpu = hpa["spec"]["metrics"][0]["resource"]["target"]["averageUtilization"]
mem = hpa["spec"]["metrics"][1]["resource"]["target"]["averageUtilization"]
ck("HPA CPU 阈值 70%", cpu == 70, str(cpu))
ck("HPA 内存阈值 80%", mem == 80, str(mem))
ck("HPA autoscaling/v2", hpa["apiVersion"] == "autoscaling/v2", hpa["apiVersion"])
ck("快扩慢缩 behavior", hpa["spec"]["behavior"]["scaleUp"]["stabilizationWindowSeconds"] == 30
   and hpa["spec"]["behavior"]["scaleDown"]["stabilizationWindowSeconds"] == 300)
ck("优雅停机 30s", dep["spec"]["template"]["spec"]["terminationGracePeriodSeconds"] == 30)

envs = {e["name"]: e for e in c["env"]}
ck("LLM_API_KEY 走 secretKeyRef", "valueFrom" in envs["LLM_API_KEY"]
   and envs["LLM_API_KEY"]["valueFrom"]["secretKeyRef"]["name"] == "ea-llm-secret",
   envs["LLM_API_KEY"].get("valueFrom", {}).get("secretKeyRef", {}).get("name", "明文！"))
ck("明文回退守卫生效", GUARD_OK)
ck("POSTGRES_PASSWORD 走 secretKeyRef", "valueFrom" in envs["POSTGRES_PASSWORD"])
ck("OTel 端点已注入", envs["OTEL_EXPORTER_OTLP_ENDPOINT"]["value"].endswith("4318"))

# 明文凭据扫描：渲染结果里不能出现真实密钥形态
import re
bad = [p for p in [r"sk-[A-Za-z0-9]{20,}", r"ghp_[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}"]
       if re.search(p, r.stdout)]
ck("渲染结果无明文密钥形态", not bad, str(bad))
# 渲染结果里不得出现 LLM_API_KEY=明文 形式
ck("无 LLM_API_KEY 明文赋值",
   not re.search(r"LLM_API_KEY:\s*[\"']?(?!PLACEHOLDER)\S{16,}", r.stdout))

print("\n" + "=" * 56)
ok = 0
for name, cond, detail in checks:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    ok += bool(cond)
print("=" * 56)
print(f"{ok}/{len(checks)} 项通过")
sys.exit(0 if ok == len(checks) and not missing else 1)