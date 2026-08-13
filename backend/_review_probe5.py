# -*- coding: utf-8 -*-
import sys, io, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

spec = importlib.util.spec_from_file_location("sr", r"C:/Users/xiaoweizhong/AppData/Local/Temp/rev/sr_f025ed5.py")
sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(sr)

print('=== A. mock_adapt_resume with a real DB job id ===')
from app.mock.fallback import mock_adapt_resume, JOB_DATABASE
for jid, tj in (("job_db_4271", "Java后端开发工程师"), ("job_db_88", "前端开发工程师"), ("job_db_1", "数据分析师")):
    r = mock_adapt_resume(job_id=jid, target_job=tj)
    print('  job_id=%-14s target=%-16s -> matchLevel=%s originalScore=%s adaptedScore=%s' % (
        jid, tj, r["matchLevel"], r["originalScore"], r["adaptedScore"]))
    print('     adapted target_job set to: %r  (JOB_DATABASE[0]=%r)' % (
        r["adaptedResume"]["basic"]["target_job"], JOB_DATABASE[0]["title"]))
    print('     changes: %s' % r["changes"][:1])

print('\n=== B. 量化度 formula: old (avg*.8+ratio*.2) vs new (avg*.55+depth*.45) ===')
def old(per):
    avg = sum(per)/len(per); ratio = sum(1 for p in per if p>=0.8)/len(per)
    return round((avg*0.8+ratio*0.2)*100)
def new(per):
    avg = sum(per)/len(per); depth = min(1.0, sum(1 for p in per if p>=0.8)/3)
    return round((avg*0.55+depth*0.45)*100)
cases = {
    '1 条硬成果':                       [1.0],
    '3 条硬成果':                       [1.0,1.0,1.0],
    '10 条都有量纲数字(0.65)':          [0.65]*10,
    '3 条硬成果 + 7 条空描述':          [1.0,1.0,1.0]+[0.0]*7,
    '1 条硬成果 + 4 条平常(0.0)':       [1.0,0,0,0,0],
    '6 条中等(0.65) + 1 条硬':          [0.65]*6+[1.0],
}
for k, per in cases.items():
    print('  %-28s old=%3d  new=%3d  (Δ %+d)' % (k, old(per), new(per), new(per)-old(per)))

print('\n=== C. 日期区间被当成硬成果 (>=0.8 计入 depth) ===')
date_bullets = [
    '2021年9月至2023年6月担任社团组织委员，负责日常事务',
    '从2019年到2021年担任第2组组长',
    '从2020年9月到2024年6月就读于某大学计算机专业',
    '负责活动的现场执行工作，每周投入约3小时',
]
per = [sr.score_bullet_quant(b) for b in date_bullets]
for b, p in zip(date_bullets, per):
    print('  %.2f  %s' % (p, b))
print('  -> 量化度 = %d (strong_count=%d)' % (new(per), sum(1 for p in per if p>=0.8)))

print('\n=== D. jd_corpus 缓存:失败/空结果也会被缓存 30 分钟 ===')
import app.services.jd_corpus as jc
jc.clear_cache()
p1 = jc.build_profile(None, "Java后端开发工程师")   # DB 不可用 -> starter
print('  1st build ->', p1.source, p1.sample_size, 'cached keys=', list(jc._CACHE))
p2 = jc.build_profile(None, "Java后端开发工程师")
print('  2nd build (from cache) -> same object:', p1 is p2)
# 缓存无上限
for i in range(2000):
    jc.build_profile(None, "岗位%d" % i)
print('  after 2000 distinct target_job -> len(_CACHE) =', len(jc._CACHE), '(no eviction / no max size)')
