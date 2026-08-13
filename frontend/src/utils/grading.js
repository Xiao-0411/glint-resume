/**
 * 简历评级阈值 —— 前端唯一定义处
 *
 * 阈值必须与后端 `evaluation_service._grade_of` 保持一致。
 * 此前前端有三份互相冲突的实现:
 *   - ResultView.gradeGapText   82/68/52/35（与后端一致）
 *   - ResultView.scoreLevel     82/68/52/35（与后端一致）
 *   - ResumeHistoryDialog.scoreColor  85/70/60（**与后端不一致**）
 * 导致同一份 70 分简历在报告页显示「优秀」绿色、在历史列表里却是另一种颜色。
 * 统一到这里后，改阈值只需改一处。
 */

// 与后端 _grade_of 一一对应，从高到低
export const GRADE_TIERS = [
  { min: 82, label: '卓越', level: 'excellent', color: 'var(--color-success)' },
  { min: 68, label: '优秀', level: 'good', color: 'var(--color-success)' },
  { min: 52, label: '良好', level: 'pass', color: 'var(--color-warning)' },
  { min: 35, label: '合格', level: 'warn', color: 'var(--color-warning)' },
  { min: 0, label: '待提升', level: 'warn', color: 'var(--color-danger)' },
]

function tierOf(score) {
  return GRADE_TIERS.find((t) => score >= t.min) || GRADE_TIERS[GRADE_TIERS.length - 1]
}

/** 分数 -> 样式档位（excellent / good / pass / warn） */
export function scoreLevel(score) {
  if (typeof score !== 'number') return 'warn'
  return tierOf(score).level
}

/** 分数 -> 展示色。后端已给 grade_color 时优先用后端的，避免两边不一致。 */
export function scoreColor(score, backendColor) {
  if (backendColor) return backendColor
  if (typeof score !== 'number') return 'var(--color-text-muted)'
  return tierOf(score).color
}

/** 分数 -> 评级名称（卓越/优秀/…） */
export function gradeLabel(score) {
  if (typeof score !== 'number') return ''
  return tierOf(score).label
}

/** 距下一档还差多少分；已是最高档返回空串 */
export function gradeGapText(score) {
  if (typeof score !== 'number') return ''
  const next = [...GRADE_TIERS].reverse().find((t) => t.min > score)
  return next ? ` · 距${next.label}还差 ${next.min - score} 分` : ''
}
