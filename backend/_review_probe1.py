# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
from app.services.scoring_rules import (
    QUANT_DELTA, QUANT_DELTA_REV, QUANT_RANGE, QUANT_WITH_UNIT, QUANT_RANK,
    score_bullet_quant, score_bullet_professional, score_bullet_credibility,
)

tests = [
    '显著提升，覆盖3个模块',      # 显著提升，覆盖3个模块
    '显著提升 覆盖3个模块',           # 显著提升 覆盖3个模块
    '大幅优化 完成5个页面',           # 大幅优化 完成5个页面
    '优化了流程 编写12篇文档',     # 优化了流程 编写12篇文档
    '从2019年到2021年担任第2组组长',  # 从2019年到2021年担任第2组组长
    '从2019年至2021年负责3个项目',    # 从2019年至2021年负责3个项目
    '从大二到大四参加了2次比赛',  # 从大二到大四参加了2次比赛
    '从 800ms 优化至 120ms',                              # 从 800ms 优化至 120ms
    'QPS 从 200 提升到 1200',                             # QPS 从 200 提升到 1200
    '接口耗时降低 65%',                           # 接口耗时降低 65%
    '从1个人到了5个人的团队',      # 从1个人到了5个人的团队
    '从第3名提升到第1名',                 # 从第3名提升到第1名
]

for t in tests:
    print(t)
    print('   DELTA=%s REV=%s RANGE=%s UNIT=%s RANK=%s -> quant=%.2f' % (
        bool(QUANT_DELTA.search(t)), bool(QUANT_DELTA_REV.search(t)),
        bool(QUANT_RANGE.search(t)), bool(QUANT_WITH_UNIT.search(t)),
        bool(QUANT_RANK.search(t)), score_bullet_quant(t)))

print('\n--- professional scoring ---')
pro_tests = [
    '主导设计行业领先的完美架构，显著提升性能，大幅优化体验',  # 主导设计行业领先的完美架构，显著提升性能，大幅优化体验
    '主导设计订单服务架构，接口 P99 从 800ms 降至 120ms，支撑日均 200 万请求',  # good one
    '负责前端页面开发，完成 12 个业务页面的交付',
]
for t in pro_tests:
    print(t)
    print('   professional=%.3f credibility=%.3f' % (score_bullet_professional(t), score_bullet_credibility(t)))
