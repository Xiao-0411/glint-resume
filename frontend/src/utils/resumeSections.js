/**
 * 简历 section 解锁判定
 *
 * 右侧「实时预览」要展示哪些板块，优先由后端真实下发的抽取数据决定：
 * 只要某个板块已经抽到内容，就立刻渲染，不必等用户对 recap 说「确认」把 stage 推进。
 * 仅在完全没有真实数据时（mock / 演示模式）才回落到按 stage 解锁的样例排版。
 */

/** 后端抽取数据中，各 section 的判定规则 */
function hasBasic(p) {
  return !!(p.fullname || p.phone || p.email || p.location)
}

function hasEducation(p) {
  return Array.isArray(p.education) && p.education.length > 0
}

function hasExperiences(p) {
  return Array.isArray(p.experiences) && p.experiences.length > 0
}

function hasSkills(p) {
  const skills = p.skills || {}
  return ['technical', 'tools', 'product', 'soft'].some(
    k => Array.isArray(skills[k]) && skills[k].length > 0
  )
}

function hasAwards(p) {
  return Array.isArray(p.awards) && p.awards.length > 0
}

/**
 * 从后端抽取数据推导已解锁的 section
 * @param {Object} profile
 * @returns {string[]}
 */
export function sectionsFromProfile(profile) {
  const p = profile || {}
  const sections = []
  if (hasBasic(p)) sections.push('basic')
  if (hasEducation(p)) sections.push('education')
  if (hasExperiences(p)) sections.push('experiences')
  if (hasSkills(p)) sections.push('skills')
  if (hasAwards(p)) sections.push('awards')
  return sections
}

/**
 * 是否已经拿到后端真实数据（任一 section 有内容）
 * 与 sectionsFromProfile 共用同一套判定，避免出现
 * 「section 已解锁但预览仍回落到 mock 样例」导致渲染假姓名。
 * @param {Object} profile
 * @returns {boolean}
 */
export function hasRealProfile(profile) {
  return sectionsFromProfile(profile).length > 0
}

/** stage → 已解锁 section（mock / 演示模式下的样例排版节奏） */
const STAGE_SECTIONS = {
  basic_info: [],
  education: ['basic'],
  experience_mining: ['basic', 'education'],
  skills: ['basic', 'education', 'experiences'],
  awards: ['basic', 'education', 'experiences', 'skills'],
  ready_to_generate: ['basic', 'education', 'experiences', 'skills', 'awards']
}

/**
 * 从对话 stage 推导已解锁的 section
 * @param {string} stage
 * @returns {string[]}
 */
export function sectionsFromStage(stage) {
  return STAGE_SECTIONS[stage] || []
}
