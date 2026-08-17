"""
PDF 导出服务 —— 使用 WeasyPrint 将简历 JSON 渲染为 A4 PDF

依赖: weasyprint (pip install weasyprint)
Windows 需额外安装 GTK3: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows
Linux: apt install weasyprint 或 pip install weasyprint
"""
import logging

logger = logging.getLogger("glint.pdf")


# A4 简历 HTML 模板（中文）
RESUME_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-center {{
      content: "识光简历 · AI 生成";
      font-size: 8pt;
      color: #999;
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
    }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", sans-serif;
    font-size: 10.5pt;
    line-height: 1.65;
    color: #1a1a1a;
  }}

  /* ====== 头部 ====== */
  .header {{
    text-align: center;
    padding-bottom: 12px;
    border-bottom: 2px solid #2563eb;
    margin-bottom: 14px;
  }}
  .header .name {{ font-size: 22pt; font-weight: 700; letter-spacing: 2px; margin-bottom: 4px; }}
  .header .job {{ font-size: 11pt; color: #2563eb; font-weight: 600; margin-bottom: 6px; }}
  .header .contact {{ font-size: 9pt; color: #555; }}
  .header .contact span {{ margin: 0 8px; }}

  /* ====== 章节 ====== */
  .section {{ margin-bottom: 12px; }}
  .section-title {{
    font-size: 12pt;
    font-weight: 700;
    color: #2563eb;
    border-bottom: 1px solid #d0d7e8;
    padding-bottom: 3px;
    margin-bottom: 8px;
    letter-spacing: 1px;
  }}

  /* ====== 教育背景 ====== */
  .edu-item {{ margin-bottom: 6px; }}
  .edu-item .edu-main {{ display: flex; justify-content: space-between; font-weight: 600; }}
  .edu-item .edu-detail {{ font-size: 9.5pt; color: #555; margin-top: 1px; }}

  /* ====== 经历 ====== */
  .exp-item {{ margin-bottom: 10px; }}
  .exp-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 3px; }}
  .exp-title {{ font-weight: 700; font-size: 11pt; }}
  .exp-role {{ color: #2563eb; font-weight: 600; font-size: 10pt; }}
  .exp-period {{ font-size: 9pt; color: #888; white-space: nowrap; }}
  .exp-bullets {{ padding-left: 16px; }}
  .exp-bullets li {{ margin-bottom: 2px; font-size: 10pt; text-align: justify; }}

  /* ====== 技能 ====== */
  .skill-group {{ margin-bottom: 4px; }}
  .skill-label {{ font-weight: 700; display: inline-block; min-width: 56px; font-size: 10pt; }}
  .skill-text {{ font-size: 10pt; color: #444; }}

  /* ====== 获奖 ====== */
  .award-list {{ padding-left: 16px; }}
  .award-list li {{ margin-bottom: 2px; font-size: 10pt; }}

  /* ====== 自评 ====== */
  .self-eval {{ font-size: 10pt; text-align: justify; color: #444; line-height: 1.7; }}

  /* ====== 标签 ====== */
  .tag {{
    display: inline-block;
    font-size: 7.5pt;
    padding: 1px 6px;
    border-radius: 3px;
    margin-left: 6px;
    font-weight: 400;
    vertical-align: middle;
  }}
  .tag-green {{ background: #d1fae5; color: #065f46; }}
  .tag-yellow {{ background: #fef3c7; color: #92400e; }}
</style>
</head>
<body>

<div class="header">
  <div class="name">{fullname}</div>
  <div class="job">求职意向：{target_job}</div>
  <div class="contact">
    {contact_line}
  </div>
</div>

{education_section}

{experience_section}

{skills_section}

{awards_section}

{self_eval_section}

</body>
</html>"""


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_contact_line(basic: dict) -> str:
    parts = []
    for key, label in [("phone", "📱"), ("email", "📧"), ("location", "📍")]:
        val = (basic.get(key) or "").strip()
        if val:
            parts.append(f"<span>{label} {_escape_html(val)}</span>")
    return "".join(parts) if parts else ""


def _build_education(education: list) -> str:
    if not education:
        return ""
    items = []
    for edu in education:
        school = _escape_html(edu.get("school", ""))
        major = _escape_html(edu.get("major", ""))
        degree = _escape_html(edu.get("degree", ""))
        period = _escape_html(edu.get("period", ""))
        gpa = _escape_html(edu.get("gpa", ""))
        highlights = edu.get("highlights") or []

        detail_parts = []
        if gpa:
            detail_parts.append(f"GPA {gpa}")
        if highlights:
            detail_parts.append(" · ".join(_escape_html(h) for h in highlights))

        items.append(f"""<div class="edu-item">
  <div class="edu-main">
    <span>{school} · {major} · {degree}</span>
    <span>{period}</span>
  </div>
  {f'<div class="edu-detail">{" · ".join(detail_parts)}</div>' if detail_parts else ''}
</div>""")

    return f"""<div class="section">
<div class="section-title">教育背景</div>
{''.join(items)}
</div>"""


def _build_experiences(experiences: list) -> str:
    if not experiences:
        return ""
    items = []
    for exp in experiences:
        title = _escape_html(exp.get("title", ""))
        role = _escape_html(exp.get("role", ""))
        period = _escape_html(exp.get("period", ""))
        bullets = exp.get("bullets") or []
        tag = exp.get("tag") or {}
        tag_color = tag.get("color", "green")
        tag_label = _escape_html(tag.get("label", ""))

        bullets_html = "\n".join(
            f"    <li>{_escape_html(b)}</li>" for b in bullets if b
        )

        items.append(f"""<div class="exp-item">
  <div class="exp-header">
    <span>
      <span class="exp-title">{title}</span>
      <span class="exp-role"> · {role}</span>
      {f'<span class="tag tag-{tag_color}">{tag_label}</span>' if tag_label else ''}
    </span>
    <span class="exp-period">{period}</span>
  </div>
  <ul class="exp-bullets">
{bullets_html}
  </ul>
</div>""")

    return f"""<div class="section">
<div class="section-title">项目经历</div>
{''.join(items)}
</div>"""


def _build_skills(skills: dict) -> str:
    if not skills:
        return ""
    groups = []
    for key, label in [("technical", "技术栈"), ("product", "产品能力"), ("soft", "软技能")]:
        items = skills.get(key) or []
        if items:
            groups.append(
                f'<div class="skill-group"><span class="skill-label">{label}：</span>'
                f'<span class="skill-text">{_escape_html("、".join(items))}</span></div>'
            )
    if not groups:
        return ""
    return f"""<div class="section">
<div class="section-title">技能清单</div>
{''.join(groups)}
</div>"""


def _build_awards(awards: list) -> str:
    if not awards:
        return ""
    items = "\n".join(f"  <li>{_escape_html(a)}</li>" for a in awards if a)
    return f"""<div class="section">
<div class="section-title">获奖荣誉</div>
<ul class="award-list">
{items}
</ul>
</div>"""


def _build_self_eval(text: str) -> str:
    if not text or not text.strip():
        return ""
    return f"""<div class="section">
<div class="section-title">自我评价</div>
<div class="self-eval">{_escape_html(text.strip())}</div>
</div>"""


def build_resume_html(resume: dict) -> str:
    """将简历 JSON 渲染为 A4 排版的 HTML 字符串"""
    basic = resume.get("basic") or {}
    fullname = _escape_html(basic.get("fullname") or "未命名")
    target_job = _escape_html(basic.get("target_job") or "未指定岗位")

    return RESUME_HTML_TEMPLATE.format(
        fullname=fullname or "未命名",
        target_job=target_job or "未指定岗位",
        contact_line=_build_contact_line(basic),
        education_section=_build_education(resume.get("education") or []),
        experience_section=_build_experiences(resume.get("experiences") or []),
        skills_section=_build_skills(resume.get("skills") or {}),
        awards_section=_build_awards(resume.get("awards") or []),
        self_eval_section=_build_self_eval(resume.get("self_evaluation") or ""),
    )


def generate_pdf_bytes(resume: dict) -> bytes:
    """生成 PDF 字节流，失败时抛出异常"""
    html = build_resume_html(resume)
    try:
        from weasyprint import HTML, default_url_fetcher

        # 防止 SSRF：只允许加载 data: URI，禁止加载外部资源
        def safe_url_fetcher(url, timeout=10):
            if url.startswith("data:"):
                return default_url_fetcher(url, timeout=timeout)
            # 拒绝所有外部 URL（图片、样式等），防止 SSRF 攻击
            raise ValueError(f"Blocked external resource: {url}")

        doc = HTML(string=html, url_fetcher=safe_url_fetcher)
        return doc.write_pdf()
    except ImportError:
        raise RuntimeError(
            "WeasyPrint 未安装。请运行: pip install weasyprint\n"
            "Windows 用户还需安装 GTK3: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows"
        )
    except Exception as e:
        logger.error("pdf_generation_failed", extra={"error": str(e)})
        raise RuntimeError(f"PDF 生成失败: {e}")
