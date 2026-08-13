# -*- coding: utf-8 -*-
import sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from app.services.skill_extract import extract_skills, _ALIAS_PATTERNS
from app.services.jd_corpus import _skills_of_job

desc = ("岗位职责：\n1. 负责电商交易系统后端服务的设计与开发，参与高并发场景下的架构演进；\n"
        "2. 参与核心链路的性能优化与稳定性建设，保障大促期间系统平稳运行；\n"
        "3. 与产品、前端、测试协作，推动需求高质量落地。\n"
        "任职要求：\n1. 本科及以上学历，计算机相关专业，3 年以上 Java 开发经验；\n"
        "2. 熟练掌握 Java、Spring Boot、MyBatis，熟悉 JVM 原理与调优；\n"
        "3. 熟悉 MySQL、Redis、Kafka，有分库分表、缓存设计经验；\n"
        "4. 了解 Docker/Kubernetes，有云原生实践经验者优先；\n"
        "5. 具备良好的沟通能力与团队协作意识。") * 1
print('desc len =', len(desc))
print('alias patterns =', len(_ALIAS_PATTERNS))

t0 = time.perf_counter()
for _ in range(200):
    extract_skills(desc)
dt = time.perf_counter() - t0
print('extract_skills x200 (=1 profile build of 200 JDs): %.3f s  (%.2f ms each)' % (dt, dt/200*1000))

long_desc = desc * 5
t0 = time.perf_counter()
for _ in range(200):
    extract_skills(long_desc)
dt = time.perf_counter() - t0
print('extract_skills x200 on %d-char JD: %.3f s' % (len(long_desc), dt))
