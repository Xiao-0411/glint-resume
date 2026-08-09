"""
提交前安全检查

两件事:
1. 禁止提交的路径 —— .env / logs/ / .env.bak* 之类,一旦进入暂存区就拦下
2. 密钥扫描 —— 扫描暂存区(或工作区改动)里有没有像密钥/密码的内容

任一不通过就以退出码 1 结束,让 一键推送.bat 中止流程。

设计取舍:宁可误报也不漏报,但误报要能一眼看出是误报,
所以只打印文件名、行号和脱敏后的片段,绝不输出完整密钥。

用法: python scripts/check_secrets.py
     python scripts/check_secrets.py --self-test   # 跑内置用例
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# ============ 禁止提交的路径 ============
# 这些文件含密钥或是运行时产物,任何情况下都不该进仓库。
# 放在 Python 里而不是 .bat 的 findstr 里,因为这段逻辑需要能被测试。
FORBIDDEN_PATH_RULES = [
    (re.compile(r"(^|/)\.env$"), "环境变量文件含真实密钥"),
    (re.compile(r"(^|/)\.env\.bak"), "环境变量备份文件含真实密钥"),
    (re.compile(r"(^|/)\.env\.local$"), "本地环境变量文件"),
    (re.compile(r"^logs/"), "运行时日志"),
    (re.compile(r"(^|/)\.venv/"), "虚拟环境"),
    (re.compile(r"(^|/)node_modules/"), "依赖目录"),
]

# 不扫描的路径:示例文件本来就写着占位符,构建产物和依赖不是我们写的
SKIP_PARTS = (
    "node_modules/", "/dist/", "dist/", ".venv/", "__pycache__/",
    "package-lock.json", "logs/",
)
SKIP_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff",
               ".woff2", ".ttf", ".pdf", ".zip", ".lock")

# .env.example / .env.production 里是占位符或公开配置,单独放宽
LENIENT_FILES = (".env.example", ".env.production", "check_secrets.py")

# ============ 规则 ============
# 每条:(名称, 正则, 说明, 是否跳过占位符白名单)
#
# strict=True 的规则不做占位符判断:这些格式(sk-ant-、AKIA、私钥头)
# 本身就足够特征化,厂商示例里也不该出现在我们仓库中。
# 之前把占位符白名单套在所有规则上,导致含 "example"/"test" 字样的
# 真实格式密钥被误判为占位符而漏报。
RULES = [
    (
        "疑似真实密钥赋值",
        # KEY=<32位以上的高熵字符串>,排除明显的占位符
        re.compile(
            r"(?i)\b(SECRET|SECRET_KEY|API_KEY|APIKEY|TOKEN|PASSWORD|PASSWD|PWD|"
            r"PRIVATE_KEY|ACCESS_KEY|AUTH_SECRET_KEY)\s*[=:]\s*"
            r"['\"]?([A-Za-z0-9_\-+/=]{32,})['\"]?"
        ),
        "看起来是真实密钥,不该进仓库",
        False,
    ),
    (
        "OpenAI/Anthropic 风格 Key",
        re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9_\-]{20,})"),
        "LLM 服务商密钥",
        True,
    ),
    (
        "AWS Access Key",
        # 整段作为捕获组,否则脱敏和判断只拿到 AKIA 四个字符
        re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"),
        "AWS 凭据",
        True,
    ),
    (
        "私钥文件内容",
        re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)"),
        "私钥",
        True,
    ),
    (
        "数据库连接串含密码",
        # mysql://user:password@host —— 密码非空且不是占位符
        re.compile(
            r"(?i)(mysql|postgres|postgresql|mongodb|redis)(\+\w+)?://"
            r"[^:/\s]+:([^@\s]{6,})@"
        ),
        "连接串里带了真实密码",
        False,
    ),
]

# 占位符白名单:命中这些就不算泄露
PLACEHOLDER_HINTS = (
    "your", "xxx", "changeme", "change_me", "placeholder", "example",
    "replace", "todo", "dummy", "fake", "sample", "test", "demo",
    "请替换", "填写", "你的", "长随机字符串",
    "123456", "password", "secret", "abcdef",
)


def is_placeholder(value: str) -> bool:
    low = value.lower()
    if any(h in low for h in PLACEHOLDER_HINTS):
        return True
    # 全是同一个字符,或明显递增序列
    if len(set(low)) <= 3:
        return True
    return False


def mask(value: str) -> str:
    """脱敏:只留首尾各 3 位"""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}{'*' * 10}{value[-3:]}"


def staged_files() -> list:
    """取暂存区文件;为空则退回未提交改动 + 未跟踪文件"""
    def run(args):
        r = subprocess.run(
            ["git"] + args, cwd=REPO,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return [l for l in r.stdout.splitlines() if l.strip()]

    files = run(["diff", "--cached", "--name-only", "--diff-filter=ACM"])
    if not files:
        files = run(["diff", "--name-only", "--diff-filter=ACM"])
        files += run(["ls-files", "--others", "--exclude-standard"])
    return sorted(set(files))


def should_skip(path: str) -> bool:
    p = path.replace("\\", "/")
    if any(s in p for s in SKIP_PARTS):
        return True
    if p.endswith(SKIP_SUFFIX):
        return True
    return False


def check_forbidden_paths(files: list) -> list:
    """返回 [(路径, 原因)];非空表示有禁止提交的文件"""
    out = []
    for rel in files:
        p = rel.replace("\\", "/")
        for pattern, reason in FORBIDDEN_PATH_RULES:
            if pattern.search(p):
                out.append((rel, reason))
                break
    return out


def _self_test() -> int:
    """内置用例。因为 .bat 难以自动化测试,把可测的逻辑都放在这里。"""
    failures = []

    def check(desc, got, want):
        if got != want:
            failures.append(f"{desc}: got {got!r}, want {want!r}")

    # 禁止路径
    forbidden = [
        "backend/.env", ".env", "backend/.env.bak.authkey",
        "frontend/.env.local", "logs/backend.log", "backend/.venv/x.py",
        "frontend/node_modules/a/b.js",
    ]
    for f in forbidden:
        check(f"应拦下 {f}", bool(check_forbidden_paths([f])), True)

    allowed = [
        "backend/app/main.py", "frontend/src/App.vue",
        "backend/.env.example", "frontend/.env.production",
        "backend/tests/test_x.py", "scripts/check_secrets.py",
    ]
    for f in allowed:
        check(f"应放行 {f}", bool(check_forbidden_paths([f])), False)

    # 密钥规则
    leaks = [
        "AUTH_SECRET_KEY=MDC7aLgTbbs8YwBEafrpvOnCirInMwan5EBovJYQkaKNYHri323m",
        "LLM_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789",
        "AWS_KEY=AKIAIOSFODNN7EXAMPLE",
        "DATABASE_URL=mysql+pymysql://root:MyR3alP4ssw0rd@localhost:3306/g",
        "-----BEGIN RSA PRIVATE KEY-----",
    ]
    for line in leaks:
        hit = False
        for name, pattern, note, strict in RULES:
            m = pattern.search(line)
            if not m:
                continue
            groups = [g for g in m.groups() if g]
            value = groups[-1] if groups else m.group(0)
            if not strict and is_placeholder(value):
                continue
            hit = True
            break
        check(f"应检出密钥 {line[:28]}", hit, True)

    benign = [
        "AUTH_SECRET_KEY=请替换为长随机字符串",
        "AUTH_SECRET_KEY=your-secret-key-here",
        "DATABASE_URL=mysql+pymysql://root:123456@localhost:3306/glint",
        "LLM_MODEL=deepseek-v4-pro",
        "VITE_API_BASE_URL=https://api.sgjl.cloud",
    ]
    for line in benign:
        hit = False
        for name, pattern, note, strict in RULES:
            m = pattern.search(line)
            if not m:
                continue
            groups = [g for g in m.groups() if g]
            value = groups[-1] if groups else m.group(0)
            if not strict and is_placeholder(value):
                continue
            hit = True
            break
        check(f"不应误报 {line[:28]}", hit, False)

    # 脱敏不能泄露原文
    secret = "MDC7aLgTbbs8YwBEafrpvOnCirInMwan"
    masked = mask(secret)
    check("脱敏后不含原文", secret in masked, False)
    check("脱敏保留首尾", masked.startswith("MDC") and masked.endswith("wan"), True)

    if failures:
        print("SELF-TEST FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print(f"SELF-TEST OK ({len(forbidden) + len(allowed) + len(leaks) + len(benign) + 2} 项)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()

    files = staged_files()
    if not files:
        return 0

    # ---- 1. 禁止提交的路径 ----
    bad_paths = check_forbidden_paths(files)
    if bad_paths:
        print()
        print("  以下文件禁止提交:")
        print("  " + "-" * 56)
        for rel, reason in bad_paths:
            print(f"  {rel}")
            print(f"    原因: {reason}")
        print("  " + "-" * 56)
        print("  请检查根目录 .gitignore,并执行 git reset 取消暂存。")
        return 1

    # ---- 2. 密钥扫描 ----
    findings = []
    for rel in files:
        if should_skip(rel):
            continue
        # 扫描器自身含测试用的假密钥,跳过以免自我误报
        if rel.replace("\\", "/").endswith("scripts/check_secrets.py"):
            continue
        full = REPO / rel
        if not full.is_file():
            continue
        lenient = any(rel.endswith(f) for f in LENIENT_FILES)
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > 2_000_000:  # 跳过超大文件
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("#", "//", "*", "rem ")):
                continue
            for name, pattern, note, strict in RULES:
                m = pattern.search(line)
                if not m:
                    continue
                # 取最后一个捕获组作为疑似密钥值
                groups = [g for g in m.groups() if g]
                value = groups[-1] if groups else m.group(0)
                if not strict and is_placeholder(value):
                    continue
                if lenient and not strict:
                    continue
                findings.append((rel, lineno, name, note, mask(value)))
                break

    if not findings:
        return 0

    print()
    print("  发现疑似敏感内容:")
    print("  " + "-" * 56)
    for rel, lineno, name, note, masked in findings:
        print(f"  {rel}:{lineno}")
        print(f"    类型: {name} —— {note}")
        print(f"    片段: {masked}")
        print()
    print("  " + "-" * 56)
    print("  若确认是误报,可临时改用: git push origin <branch>")
    print("  若确实是密钥,请从提交中移除并考虑立即轮换该密钥。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
