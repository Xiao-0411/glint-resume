# -*- coding: utf-8 -*-
import sys, io, importlib.util, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

spec = importlib.util.spec_from_file_location("sr", r"C:/Users/xiaoweizhong/AppData/Local/Temp/rev/sr_f025ed5.py")
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)

print('_SEP =', repr(sr._SEP))
print('QUANT_DELTA =', sr.QUANT_DELTA.pattern[:80], '...')
print()

tests = [
    '显著提升 覆盖3个模块',
    '显著提升，覆盖3个模块',
    '大幅优化 完成5个页面',
    '优化了整体流程 编写12篇文档',
    '负责后台功能优化 参与3人小组的日常协作',
    '从2019年到2021年担任第2组组长',
    '从2019年至2021年负责3个项目',
    '从2019年到2021年，共3人',
    '任期从2019到2021',
    '从 800ms 优化至 120ms',
    'QPS 从 200 提升到 1200',
    '从2000万降至200万',
    '接口耗时降低 65%',
    '从大二到大四参加了2次比赛',
    '从第2组到第3组',
    '从2020年9月到2024年6月就读于某大学',
]
for t in tests:
    print('%-40s DELTA=%-5s REV=%-5s RANGE=%-5s UNIT=%-5s RANK=%-5s quant=%.2f' % (
        t, bool(sr.QUANT_DELTA.search(t)), bool(sr.QUANT_DELTA_REV.search(t)),
        bool(sr.QUANT_RANGE.search(t)), bool(sr.QUANT_WITH_UNIT.search(t)),
        bool(sr.QUANT_RANK.search(t)), sr.score_bullet_quant(t)))

print('\n--- ReDoS probe: QUANT_RANGE on long non-matching input ---')
for n in (100, 500, 1000, 2000, 4000, 8000):
    s = '从' + '1' * n + 'x'
    t0 = time.perf_counter()
    sr.QUANT_RANGE.search(s)
    print('  len(%d digits) -> %.4fs' % (n, time.perf_counter() - t0))

print('\n--- ReDoS probe: many 从 prefixes ---')
for n in (50, 200, 500, 1000):
    s = ('从1' * n) + '到'
    t0 = time.perf_counter()
    sr.QUANT_RANGE.search(s)
    print('  n=%d -> %.4fs' % (n, time.perf_counter() - t0))

print('\n--- ReDoS: QUANT_DELTA on long input ---')
for n in (1000, 5000, 20000):
    s = '提升' + 'a' * n
    t0 = time.perf_counter()
    sr.QUANT_DELTA.search(s)
    print('  n=%d -> %.4fs' % (n, time.perf_counter() - t0))

print('\n--- professional (committed version) ---')
pro = [
 '主导设计行业领先的完美架构，显著提升性能，大幅优化体验',
 '主导设计订单服务架构，接口 P99 从 800ms 降至 120ms，支撑日均 200 万请求',
 '负责前端页面开发，完成 12 个业务页面的交付',
 '主导重构核心链路，显著降低耗时 65%，覆盖 200 万用户',
]
for t in pro:
    print('  %.3f  %s' % (sr.score_bullet_professional(t), t))
