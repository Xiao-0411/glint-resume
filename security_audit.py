"""
识光简历 —— 安全攻击模拟脚本
=============================
模拟黑客视角对项目进行自动化安全测试，输出漏洞报告。

用法:
  python security_audit.py                    # 仅代码静态分析
  python security_audit.py --target http://localhost:8000  # 含动态测试（需后端运行中）

注意：本脚本仅用于安全审计目的，请勿对未授权的目标使用。
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Tuple

# ====== 配置 ======
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# 报告输出
REPORT_LINES: List[str] = []


def log(msg: str, level: str = "INFO"):
    prefix = {"INFO": "[*]", "PASS": "[✓]", "FAIL": "[!]", "WARN": "[?]", "HDR": "[#]"}
    line = f"{prefix.get(level, '[*]')} {msg}"
    print(line)
    REPORT_LINES.append(line)


def hdr(msg: str):
    log("=" * 60, "HDR")
    log(msg, "HDR")
    log("=" * 60, "HDR")


# ====================================================================
# 1. 静态代码分析
# ====================================================================

def check_hardcoded_secrets():
    """检查代码中是否有硬编码的密钥/密码"""
    hdr("1. 硬编码密钥检查")
    patterns = [
        (r"(?i)(api_key|apikey|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "疑似硬编码密钥"),
        (r"(?i)sk-[a-zA-Z0-9]{20,}", "OpenAI/Anthropic API Key 格式"),
        (r"(?i)AKIA[0-9A-Z]{16}", "AWS Access Key"),
    ]
    findings = 0
    for fpath in BACKEND_DIR.rglob("*.py"):
        if ".venv" in str(fpath) or "__pycache__" in str(fpath):
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
            for pat, desc in patterns:
                for match in re.finditer(pat, content):
                    line_no = content[:match.start()].count("\n") + 1
                    log(f"  {fpath.relative_to(PROJECT_ROOT)}:{line_no} - {desc}", "FAIL")
                    findings += 1
        except Exception:
            pass
    if findings == 0:
        log("  未发现硬编码密钥（代码层面）", "PASS")
    else:
        log(f"  共发现 {findings} 处疑似硬编码密钥", "FAIL")


def check_dotenv_exposure():
    """检查 .env 文件是否可能被泄露"""
    hdr("2. .env 文件泄露风险")
    env_file = BACKEND_DIR / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        sensitive = []
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=")[0]
                if any(k in key.upper() for k in ["KEY", "PASSWORD", "SECRET", "TOKEN"]):
                    sensitive.append(key)
        if sensitive:
            log(f"  .env 包含 {len(sensitive)} 个敏感配置项: {', '.join(sensitive)}", "WARN")
            log(f"  确认 .gitignore 已排除 .env", "INFO")
        else:
            log("  .env 未发现敏感配置", "PASS")
    else:
        log("  .env 文件不存在", "INFO")

    gitignore = BACKEND_DIR / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8")
        if ".env" in content:
            log("  .gitignore 已排除 .env", "PASS")
        else:
            log("  .gitignore 未排除 .env！", "FAIL")
    else:
        log("  backend/.gitignore 不存在", "FAIL")


def check_xss_vulnerabilities():
    """检查前端 XSS 漏洞"""
    hdr("3. XSS 漏洞检查")
    findings = 0
    for fpath in FRONTEND_DIR.rglob("*.vue"):
        if "node_modules" in str(fpath) or "dist" in str(fpath):
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
            # 检查 v-html
            for match in re.finditer(r"v-html\s*=\s*[\"']([^\"']+)[\"']", content):
                expr = match.group(1)
                line_no = content[:match.start()].count("\n") + 1
                log(f"  {fpath.relative_to(PROJECT_ROOT)}:{line_no} - v-html=\"${expr}\"", "FAIL")
                findings += 1
            # 检查 innerHTML
            for match in re.finditer(r"\.innerHTML\s*=", content):
                line_no = content[:match.start()].count("\n") + 1
                log(f"  {fpath.relative_to(PROJECT_ROOT)}:{line_no} - .innerHTML 赋值", "FAIL")
                findings += 1
        except Exception:
            pass
    if findings == 0:
        log("  未发现 XSS 漏洞", "PASS")
    else:
        log(f"  共发现 {findings} 处 XSS 风险点", "FAIL")


def check_auth_weaknesses():
    """检查认证相关弱点"""
    hdr("4. 认证机制检查")
    findings = 0

    # 检查密码策略
    auth_py = BACKEND_DIR / "app" / "api" / "auth.py"
    if auth_py.exists():
        content = auth_py.read_text(encoding="utf-8")
        if "len(password) < 8" in content:
            log("  密码最小长度: 8 位", "PASS")
        else:
            log("  密码最小长度不足 8 位", "FAIL")
            findings += 1
        if "isupper" in content and "islower" in content and "isdigit" in content:
            log("  密码复杂度: 大小写字母+数字", "PASS")
        else:
            log("  密码复杂度要求不足", "FAIL")
            findings += 1

    # 检查 token 有效期
    config_py = BACKEND_DIR / "app" / "core" / "config.py"
    if config_py.exists():
        content = config_py.read_text(encoding="utf-8")
        m = re.search(r'AUTH_TOKEN_EXPIRE_MINUTES.*?["\'](\d+)["\']', content)
        if m:
            minutes = int(m.group(1))
            if minutes <= 1440:
                log(f"  Token 有效期: {minutes} 分钟 (≤24h)", "PASS")
            else:
                log(f"  Token 有效期: {minutes} 分钟 (>24h, 偏长)", "WARN")
                findings += 1

    # 检查暴力破解防护
    if auth_py.exists():
        content = auth_py.read_text(encoding="utf-8")
        if "brute_force" in content.lower() or "lockout" in content.lower() or "LOGIN_MAX_FAILURES" in content:
            log("  登录暴力破解防护: 已实现", "PASS")
        else:
            log("  登录暴力破解防护: 未实现", "FAIL")
            findings += 1

    if findings == 0:
        log("  认证机制无明显弱点", "PASS")


def check_cors_config():
    """检查 CORS 配置"""
    hdr("5. CORS 配置检查")
    main_py = BACKEND_DIR / "main.py"
    if main_py.exists():
        content = main_py.read_text(encoding="utf-8")
        if 'allow_methods=["*"]' in content or "allow_methods=['*']" in content:
            log("  allow_methods 为通配符 *", "FAIL")
        else:
            log("  allow_methods 已限制", "PASS")
        if 'allow_headers=["*"]' in content or "allow_headers=['*']" in content:
            log("  allow_headers 为通配符 *", "FAIL")
        else:
            log("  allow_headers 已限制", "PASS")


def check_rate_limiting():
    """检查限流配置"""
    hdr("6. 限流配置检查")
    config_py = BACKEND_DIR / "app" / "core" / "config.py"
    if config_py.exists():
        content = config_py.read_text(encoding="utf-8")
        m = re.search(r'RATE_LIMIT_PER_MIN.*?["\'](\d+)["\']', content)
        if m:
            limit = int(m.group(1))
            if limit > 0:
                log(f"  限流: {limit} 次/分钟", "PASS")
            else:
                log("  限流已关闭 (RATE_LIMIT_PER_MIN=0)", "FAIL")
        else:
            log("  未找到限流配置", "FAIL")


def check_sql_injection():
    """检查 SQL 注入风险"""
    hdr("7. SQL 注入检查")
    findings = 0
    for fpath in BACKEND_DIR.rglob("*.py"):
        if ".venv" in str(fpath) or "__pycache__" in str(fpath):
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
            # 检查原始 SQL 拼接
            for match in re.finditer(r'(?:execute|text)\s*\(\s*f["\']', content):
                line_no = content[:match.start()].count("\n") + 1
                log(f"  {fpath.relative_to(PROJECT_ROOT)}:{line_no} - 原始 SQL 执行", "WARN")
                findings += 1
            # 检查 f-string SQL
            for match in re.finditer(r'text\s*\(\s*f["\']', content):
                line_no = content[:match.start()].count("\n") + 1
                log(f"  {fpath.relative_to(PROJECT_ROOT)}:{line_no} - f-string SQL (注入风险)", "FAIL")
                findings += 1
        except Exception:
            pass
    if findings == 0:
        log("  未发现 SQL 注入风险", "PASS")


def check_error_handling():
    """检查错误信息泄露"""
    hdr("8. 错误信息泄露检查")
    findings = 0
    for fpath in BACKEND_DIR.rglob("*.py"):
        if ".venv" in str(fpath) or "__pycache__" in str(fpath):
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
            # 检查裸 except
            for match in re.finditer(r"except\s*:", content):
                line_no = content[:match.start()].count("\n") + 1
                log(f"  {fpath.relative_to(PROJECT_ROOT)}:{line_no} - 裸 except (可能吞掉异常)", "WARN")
                findings += 1
        except Exception:
            pass
    if findings == 0:
        log("  未发现裸 except", "PASS")


def check_security_headers():
    """检查安全响应头"""
    hdr("9. 安全响应头检查")
    main_py = BACKEND_DIR / "main.py"
    if main_py.exists():
        content = main_py.read_text(encoding="utf-8")
        headers_found = []
        for header in ["X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy",
                        "X-XSS-Protection", "Referrer-Policy"]:
            if header in content:
                headers_found.append(header)
        if headers_found:
            log(f"  已配置安全头: {', '.join(headers_found)}", "PASS")
        else:
            log("  未配置安全响应头", "FAIL")


def check_session_id_strength():
    """检查 Session ID 强度"""
    hdr("10. Session ID 强度检查")
    chat_js = FRONTEND_DIR / "src" / "stores" / "chat.js"
    if chat_js.exists():
        content = chat_js.read_text(encoding="utf-8")
        if "crypto.randomUUID" in content:
            log("  Session ID 使用 crypto.randomUUID()", "PASS")
        elif "Math.random" in content:
            log("  Session ID 使用 Math.random() (可预测)", "FAIL")
        else:
            log("  未找到 Session ID 生成逻辑", "WARN")


def check_input_validation():
    """检查输入验证"""
    hdr("11. 输入验证检查")
    sanitizer = BACKEND_DIR / "app" / "core" / "input_sanitizer.py"
    if sanitizer.exists():
        content = sanitizer.read_text(encoding="utf-8")
        if "MAX_USER_INPUT_LENGTH" in content:
            m = re.search(r"MAX_USER_INPUT_LENGTH\s*=\s*(\d+)", content)
            if m:
                log(f"  用户输入长度限制: {m.group(1)} 字符", "PASS")
        if "_INJECTION_PATTERNS" in content:
            log("  Prompt injection 防护: 已实现", "PASS")
        else:
            log("  Prompt injection 防护: 未实现", "FAIL")
    else:
        log("  input_sanitizer.py 不存在", "FAIL")


# ====================================================================
# 2. 动态测试（需要后端运行中）
# ====================================================================

def dynamic_tests(target: str):
    """对运行中的后端进行动态安全测试"""
    hdr("12. 动态安全测试")

    if not target.startswith("http"):
        target = f"http://{target}"

    def req(method: str, path: str, data=None, headers=None, expect_status=None):
        url = f"{target}{path}"
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        body = json.dumps(data).encode() if data else None
        try:
            r = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            resp = urllib.request.urlopen(r, timeout=5)
            return resp.status, resp.read().decode()[:500]
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()[:500]
        except Exception as e:
            return None, str(e)

    # 测试 1: 健康检查
    status, body = req("GET", "/api/health")
    if status == 200:
        log("  后端健康检查: 通过", "PASS")
    else:
        log(f"  后端健康检查: 失败 ({status})", "FAIL")
        log("  跳过后续动态测试", "INFO")
        return

    # 测试 2: 无认证访问受保护端点
    status, body = req("POST", "/api/chat", data={"session_id": "test", "user_message": "hi", "user_msg_count": 1})
    if status == 401:
        log("  未认证访问 /api/chat: 正确返回 401", "PASS")
    else:
        log(f"  未认证访问 /api/chat: 返回 {status} (应为 401)", "FAIL")

    # 测试 3: 登录暴力破解模拟
    log("  登录暴力破解测试 (5次错误密码)...", "INFO")
    blocked = False
    for i in range(7):
        status, body = req("POST", "/api/auth/login",
                           data={"account": "test@example.com", "password": f"wrong{i}"})
        if status == 429:
            blocked = True
            log(f"  第 {i+1} 次尝试被限流 (429)，暴力破解防护生效", "PASS")
            break
        time.sleep(0.1)
    if not blocked:
        log("  7 次错误登录均未被拦截，缺少暴力破解防护！", "FAIL")

    # 测试 4: 超大请求体
    status, body = req("POST", "/api/resume/evaluate-text",
                       data={"text": "A" * 100000, "file_name": "test.pdf"})
    if status in (400, 413, 422):
        log(f"  超大请求体: 正确拒绝 ({status})", "PASS")
    else:
        log(f"  超大请求体: 返回 {status} (无大小限制)", "WARN")

    # 测试 5: SQL 注入探测
    status, body = req("POST", "/api/auth/login",
                       data={"account": "admin' OR '1'='1", "password": "test"})
    if status == 401:
        log("  SQL 注入探测: 正确返回 401 (未绕过认证)", "PASS")
    else:
        log(f"  SQL 注入探测: 返回 {status}", "WARN")

    # 测试 6: 安全响应头
    status, body = req("GET", "/api/health")
    try:
        r = urllib.request.Request(f"{target}/api/health")
        resp = urllib.request.urlopen(r, timeout=5)
        headers = dict(resp.headers)
        for h in ["X-Content-Type-Options", "X-Frame-Options", "Content-Security-Policy"]:
            if h in headers:
                log(f"  安全头 {h}: {headers[h][:60]}", "PASS")
            else:
                log(f"  安全头 {h}: 缺失", "FAIL")
    except Exception as e:
        log(f"  安全头检查失败: {e}", "WARN")


# ====================================================================
# 3. 报告生成
# ====================================================================

def generate_report():
    """输出最终报告"""
    hdr("安全审计报告")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    log(f"审计时间: {now}", "INFO")
    log(f"项目路径: {PROJECT_ROOT}", "INFO")

    fail_count = sum(1 for line in REPORT_LINES if "[!]" in line)
    warn_count = sum(1 for line in REPORT_LINES if "[?]" in line)
    pass_count = sum(1 for line in REPORT_LINES if "[✓]" in line)

    log("", "INFO")
    log(f"统计: {pass_count} 通过, {warn_count} 警告, {fail_count} 失败", "HDR")

    # 写入文件
    report_path = PROJECT_ROOT / "security_audit_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(REPORT_LINES))
    log(f"\n报告已保存至: {report_path}", "INFO")


# ====================================================================
# Main
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="识光简历安全攻击模拟脚本")
    parser.add_argument("--target", "-t", type=str, default="",
                        help="后端地址 (如 http://localhost:8000)，用于动态测试")
    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════╗
║     识光简历 (Glint) 安全攻击模拟审计工具           ║
║     Security Audit & Attack Simulation              ║
╚══════════════════════════════════════════════════════╝
""")

    # 静态分析
    check_hardcoded_secrets()
    check_dotenv_exposure()
    check_xss_vulnerabilities()
    check_auth_weaknesses()
    check_cors_config()
    check_rate_limiting()
    check_sql_injection()
    check_error_handling()
    check_security_headers()
    check_session_id_strength()
    check_input_validation()

    # 动态测试
    if args.target:
        dynamic_tests(args.target)
    else:
        hdr("12. 动态安全测试")
        log("  未指定 --target，跳过动态测试", "INFO")
        log("  用法: python security_audit.py --target http://localhost:8000", "INFO")

    generate_report()


if __name__ == "__main__":
    main()
