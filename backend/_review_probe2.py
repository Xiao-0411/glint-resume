# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')
import app.services.scoring_rules as sr

print('_SEP =', repr(sr._SEP))
print('_UNIT =', repr(sr._UNIT))
print('QUANT_DELTA =', repr(sr.QUANT_DELTA.pattern))
print()
print('QUANT_RANGE =', repr(sr.QUANT_RANGE.pattern))
print()
s = '显著提升 覆盖3个模块'
print(s, '->', sr.QUANT_DELTA.search(s))
s2 = '从2019年到2021年担任第2组组长'
print(s2, '->', sr.QUANT_RANGE.search(s2))
s3 = '从2019年到2021年，共3人'
print(s3, '->', sr.QUANT_RANGE.search(s3))
s4 = '任期从2019到2021'
print(s4, '->', sr.QUANT_RANGE.search(s4))
print()
print('score_bullet_quant src:')
import inspect
print(inspect.getsource(sr.score_bullet_quant))
