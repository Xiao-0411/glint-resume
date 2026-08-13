# -*- coding: utf-8 -*-
"""Simulate the new match math with realistic JD/profile data."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from app.services.jd_corpus import JobProfile, _job_search_terms, _starter_profile
from app.services.job_match import (
    extract_resume_skills, job_required_skills, match_resume_to_job, rank_jobs,
)
from app.services.skill_extract import canonicalize, extract_skills
import app.services.evaluation_service as ev

print('=== 1. tags pollution: what does job_required_skills return for a real 智联/猎聘 job? ===')
zhaopin_job = {
    "title": "Java后端开发工程师",
    "tags": ["五险一金", "带薪年假", "定期体检", "节日福利", "年终奖金"],   # 智联 welfare
    "requirements": ["Java", "Spring", "MySQL", "Redis"],
    "description": "负责电商交易系统后端研发，熟悉 Java、Spring Boot、MySQL、Redis。",
}
liepin_job = {
    "title": "Java后端开发工程师",
    "tags": ["已上市", "1000-9999人", "互联网", "融资未公开", "北京"],      # 猎聘 company tags
    "requirements": ["Java", "Spring", "MySQL"],
    "description": "负责后端服务开发。",
}
print(' zhaopin required =', job_required_skills(zhaopin_job))
print(' liepin  required =', job_required_skills(liepin_job))

resume = {
    "basic": {"fullname": "张三", "phone": "138", "target_job": "Java后端开发工程师"},
    "education": [{"school": "某大学", "major": "计算机"}],
    "experiences": [{
        "id": "e1", "title": "某公司后端实习", "role": "后端开发实习生",
        "bullets": [
            "主导设计订单服务模块，基于 Spring Boot + MySQL 实现下单链路，接口 P99 从 800ms 降至 120ms",
            "使用 Redis 缓存热点数据，QPS 从 200 提升到 1200",
        ],
    }],
    "skills": {"technical": ["Java", "Spring Boot", "MySQL", "Redis", "Git", "Linux"]},
}
rs = extract_resume_skills(resume)
print(' resume proven =', rs.proven)
print(' resume listed =', rs.listed)

# 用真实 JD 语料构建的画像（模拟：Java 后端 200 条 JD）
profile_jd = JobProfile(
    target_job="Java后端开发工程师",
    skill_weights={"Java": 0.92, "MySQL": 0.81, "Spring": 0.74, "Redis": 0.63,
                   "Linux": 0.41, "Git": 0.30, "Kafka": 0.22, "Docker": 0.20,
                   "微服务": 0.18, "Kubernetes": 0.14, "Elasticsearch": 0.12,
                   "MongoDB": 0.09, "Python": 0.08, "Go": 0.07, "Dubbo": 0.06,
                   "Netty": 0.05, "MyBatis": 0.05, "五险一金": 0.55, "带薪年假": 0.31,
                   "已上市": 0.12, "1000-9999人": 0.10},
    sample_size=200, source="jd")

for name, job in (("zhaopin", zhaopin_job), ("liepin", liepin_job)):
    m = match_resume_to_job(rs, job, profile_jd)
    print(' %-8s -> score=%s level=%s matched=%s missing=%s' % (name, m["score"], m["level"], m["matched"], m["missing"]))
    print('           reasons: %s' % m["reasons"])

print('\n=== 2. neutral-0.5 vs df-scale: JD skill NOT in profile outweighs a 40%%-frequency skill ===')
job_x = {"title": "t", "tags": [], "requirements": ["Java", "MySQL", "Rust", "Scala"], "description": ""}
m = match_resume_to_job(rs, job_x, profile_jd)
print(' required=Java(0.92)+MySQL(0.81)+Rust(0.5 default)+Scala(0.5 default)')
print(' resume has Java+MySQL ->', m["score"], m["level"])

print('\n=== 3. evaluation_service._score_match denominator = WHOLE profile ===')
r = ev._score_match(resume, "Java后端开发工程师", profile_jd)
print(' ', r)
tot = sum(profile_jd.skill_weights.values())
earn = sum(w * rs.credit_of(s) for s, w in profile_jd.skill_weights.items())
print('  total_weight=%.2f earned=%.2f -> %.1f%%' % (tot, earn, earn / tot * 100))

print('\n=== 4. non-tech resume (运营) with starter profile ===')
op_resume = {
    "basic": {"fullname": "李四", "phone": "1", "target_job": "用户运营"},
    "education": [{"school": "某大学", "major": "汉语言"}],
    "experiences": [{"id": "e1", "title": "校园公众号", "role": "负责人",
        "bullets": ["独立策划并撰写推文 60 篇，累计阅读量从 800 提升到 12000",
                     "组织线下活动 8 场，参与人数累计 1200 人"]}],
    "skills": {"technical": ["Excel", "PPT"], "soft": ["文案", "策划"]},
}
p_op = _starter_profile("用户运营")
print(' starter profile:', p_op.source, p_op.skill_weights)
rs_op = extract_resume_skills(op_resume)
print(' resume skills proven=%s listed=%s empty=%s' % (rs_op.proven, rs_op.listed, rs_op.is_empty))
print(' _score_match ->', ev._score_match(op_resume, "用户运营", p_op))
print(' _score_match_by_keyword (old path) ->', ev._score_match_by_keyword(op_resume, "用户运营"))

print('\n=== 5. _job_search_terms pathological output ===')
for j in ["Java后端开发工程师", "C语言工程师", "运营", "开发工程师", "岗", "数据分析",
          "%", "a_b", "产品%经理", "_", "算法工程师（校招）"]:
    print('  %-18r -> %r' % (j, _job_search_terms(j)))
