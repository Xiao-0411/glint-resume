/**
 * 简历板块定义 —— 与后端 app/services/resume_sections.py 保持一致
 *
 * 对话不再按固定顺序推进:开场列出板块,用户自己选择先做哪一块;
 * 每完成一块回到"选择板块"状态。简历正文各板块的先后顺序由用户调整,
 * 基本信息固定在页眉,不参与排序。
 */
export const HUB_STAGE = 'section_select'
export const READY_STAGE = 'ready_to_generate'
export const GENERATE_ACTION = 'generate'
export const GENERATE_LABEL = '生成简历'

export const RESUME_SECTIONS = [
  { key: 'basic_info', label: '基本信息', desc: '姓名、联系方式、所在城市', required: true, movable: false },
  { key: 'education', label: '教育背景', desc: '学校、专业、学历、毕业时间', required: false, movable: true },
  { key: 'experience_mining', label: '项目经历', desc: '项目 / 实习 / 比赛 / 社团', required: true, movable: true },
  { key: 'skills', label: '专业技能', desc: '技术栈、工具、软技能', required: false, movable: true },
  { key: 'awards', label: '获奖荣誉', desc: '奖学金、竞赛奖项、证书', required: false, movable: true },
  { key: 'self_evaluation', label: '自我评价', desc: '一两句话概括核心优势', required: false, movable: true }
]

export const SECTION_BY_KEY = Object.fromEntries(RESUME_SECTIONS.map(s => [s.key, s]))
export const SECTION_LABELS = Object.fromEntries(RESUME_SECTIONS.map(s => [s.key, s.label]))
export const REQUIRED_KEYS = RESUME_SECTIONS.filter(s => s.required).map(s => s.key)
export const DEFAULT_SECTION_ORDER = RESUME_SECTIONS.filter(s => s.movable).map(s => s.key)

/** 快捷选项文案 → 板块 key(或 generate),点击时带上显式 section 让后端不必猜测 */
export function sectionKeyForLabel(text) {
  const clean = (text || '').trim()
  if (!clean) return null
  if (clean === GENERATE_LABEL) return GENERATE_ACTION
  const hit = RESUME_SECTIONS.find(s => s.label === clean)
  return hit ? hit.key : null
}

/** 补齐/去重后的正文板块顺序:未知 key 丢弃,缺失 key 按默认顺序追加 */
export function normalizeSectionOrder(order) {
  const result = []
  for (const key of Array.isArray(order) ? order : []) {
    if (DEFAULT_SECTION_ORDER.includes(key) && !result.includes(key)) result.push(key)
  }
  for (const key of DEFAULT_SECTION_ORDER) {
    if (!result.includes(key)) result.push(key)
  }
  return result
}

export function normalizeProgress(progress) {
  const data = progress && typeof progress === 'object' ? progress : {}
  const completed = (Array.isArray(data.completed) ? data.completed : []).filter(k => SECTION_BY_KEY[k])
  const skipped = (Array.isArray(data.skipped) ? data.skipped : [])
    .filter(k => SECTION_BY_KEY[k] && !completed.includes(k))
  return {
    completed: [...new Set(completed)],
    skipped: [...new Set(skipped)],
    order: normalizeSectionOrder(data.order)
  }
}

/** 把某个板块在顺序中上移/下移一位,返回新数组 */
export function moveSectionInOrder(order, key, direction) {
  const list = normalizeSectionOrder(order)
  const idx = list.indexOf(key)
  const target = idx + (direction === 'up' ? -1 : 1)
  if (idx === -1 || target < 0 || target >= list.length) return list
  ;[list[idx], list[target]] = [list[target], list[idx]]
  return list
}

export function remainingSections(progress) {
  const p = normalizeProgress(progress)
  const done = new Set([...p.completed, ...p.skipped])
  return RESUME_SECTIONS.filter(s => !done.has(s.key))
}

export function missingRequired(progress) {
  const p = normalizeProgress(progress)
  return RESUME_SECTIONS.filter(s => s.required && !p.completed.includes(s.key))
}

export function canGenerate(progress) {
  return missingRequired(progress).length === 0
}
