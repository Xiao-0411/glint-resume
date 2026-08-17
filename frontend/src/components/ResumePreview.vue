<template>
  <div class="resume-preview-wrap">
    <!-- 工具栏（不打印） -->
    <div v-if="showToolbar" class="toolbar no-print">
      <div class="tool-info">
        <span class="paper-size">A4 · 210 × 297 mm</span>
        <span class="dot">·</span>
        <span class="page-count">单页</span>
      </div>
      <div class="tool-actions">
        <button class="tool-btn" @click="onPrint">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 6 2 18 2 18 9"/>
            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
            <rect x="6" y="14" width="12" height="8"/>
          </svg>
          <span>导出 PDF</span>
        </button>
      </div>
    </div>

    <!-- A4 简历纸 -->
    <div class="paper printable" v-if="resume">
      <!-- 顶部基本信息 -->
      <header class="resume-header">
        <div class="name-block">
          <h1 class="name">{{ resume.basic.fullname }}</h1>
          <div class="target">求职意向：<span>{{ resume.basic.target_job }}</span></div>
        </div>
        <div class="contact">
          <div class="contact-item">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ci-icon">
              <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
              <polyline points="22,6 12,13 2,6"/>
            </svg>
            <span>{{ resume.basic.email }}</span>
          </div>
          <div class="contact-item">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ci-icon">
              <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
            </svg>
            <span>{{ resume.basic.phone }}</span>
          </div>
          <div class="contact-item">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ci-icon">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
              <circle cx="12" cy="10" r="3"/>
            </svg>
            <span>{{ resume.basic.location }}</span>
          </div>
        </div>
      </header>

      <!-- 教育背景 -->
      <section class="resume-section">
        <h2 class="section-title">
          <span class="title-bar"></span>
          <span>教育背景</span>
        </h2>
        <div class="edu-list">
          <div v-for="(edu, i) in resume.education" :key="i" class="edu-item">
            <div class="edu-row">
              <span class="edu-school">{{ edu.school }}</span>
              <span class="edu-period">{{ edu.period }}</span>
            </div>
            <div class="edu-row sub">
              <span>{{ edu.major }} · {{ edu.degree }}</span>
              <span v-if="edu.gpa">GPA: {{ edu.gpa }}</span>
            </div>
            <ul v-if="edu.highlights && edu.highlights.length" class="edu-highlights">
              <li v-for="(h, j) in edu.highlights" :key="j">{{ h }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 项目经历 -->
      <section class="resume-section">
        <h2 class="section-title">
          <span class="title-bar"></span>
          <span>项目经历</span>
        </h2>
        <div class="exp-list">
          <div
            v-for="(exp, i) in resume.experiences"
            :key="exp.id || i"
            :class="['exp-item', { 'exp-highlighted': isExpHighlighted(exp) }]"
            @click="onExpClick(exp)"
          >
            <div class="exp-head">
              <div class="exp-title-wrap">
                <span class="exp-title">{{ exp.title }}</span>
                <span class="exp-role">| {{ exp.role }}</span>
              </div>
              <div class="exp-head-right">
                <span class="exp-period">{{ exp.period }}</span>
                <button
                  v-if="editable"
                  class="exp-edit-icon no-print"
                  title="编辑这段经历"
                  @click.stop="$emit('edit-experience', exp)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 20h9"/>
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/>
                  </svg>
                  <span>编辑</span>
                </button>
              </div>
            </div>
            <ul class="exp-bullets">
              <li v-for="(b, j) in exp.bullets" :key="j">{{ b }}</li>
            </ul>
            <span v-if="exp.tag" class="exp-tag" :class="`tag-${exp.tag.color}`">
              {{ tagIcon(exp.tag.color) }} {{ exp.tag.label }}
            </span>
          </div>
        </div>
      </section>

      <!-- 技能 -->
      <section class="resume-section">
        <h2 class="section-title">
          <span class="title-bar"></span>
          <span>专业技能</span>
        </h2>
        <div class="skill-grid">
          <div class="skill-row">
            <span class="skill-label">技术栈</span>
            <div class="skill-chips">
              <span v-for="s in resume.skills.technical" :key="s" class="chip">{{ s }}</span>
            </div>
          </div>
          <div class="skill-row">
            <span class="skill-label">产品能力</span>
            <div class="skill-chips">
              <span v-for="s in resume.skills.product" :key="s" class="chip">{{ s }}</span>
            </div>
          </div>
          <div class="skill-row">
            <span class="skill-label">软技能</span>
            <div class="skill-chips">
              <span v-for="s in resume.skills.soft" :key="s" class="chip">{{ s }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 获奖 -->
      <section class="resume-section" v-if="resume.awards && resume.awards.length">
        <h2 class="section-title">
          <span class="title-bar"></span>
          <span>获奖荣誉</span>
        </h2>
        <ul class="award-list">
          <li v-for="(a, i) in resume.awards" :key="i">{{ a }}</li>
        </ul>
      </section>

      <!-- 自我评价 -->
      <section class="resume-section" v-if="resume.self_evaluation">
        <h2 class="section-title">
          <span class="title-bar"></span>
          <span>自我评价</span>
        </h2>
        <p class="self-eval">{{ resume.self_evaluation }}</p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { downloadResumePdf } from '@/api/backend'
import { useChatStore } from '@/stores/chat'

const store = useChatStore()

const props = defineProps({
  resume: { type: Object, required: true },
  highlights: { type: Array, default: () => [] },
  editable: { type: Boolean, default: false },
  showToolbar: { type: Boolean, default: true }
})

const emit = defineEmits(['highlight-click', 'edit-experience'])

function onPrint() {
  if (store.currentResumeId) {
    downloadResumePdf(store.currentResumeId)
  } else {
    window.print()
  }
}

function tagIcon(color) {
  if (color === 'green') return '✓'
  if (color === 'yellow') return '!'
  return 'i'
}

/**
 * 判断该 exp 是否被当前 focused 的 improvement 命中
 * 匹配优先级:
 *  1. improvement.target_exp_id === exp.id  (精准)
 *  2. improvement.evidence 命中 exp.title 或 bullets 子串
 *  3. improvement.actions[*].original 命中 exp.bullets
 *  4. improvement.desc / title 双向模糊匹配 exp.title(兜底)
 */
function isExpHighlighted(exp) {
  if (!props.highlights || !props.highlights.length) return false
  if (!exp) return false
  const stripPrefix = s => (s || '').replace(/^(校|我的|本人|公司|学校|大学)/, '')
  return props.highlights.some(h => {
    if (!h) return false
    if (h.target_exp_id && h.target_exp_id === exp.id) return true

    const evidence = (h.evidence || '').trim()
    if (evidence) {
      if (exp.title && evidence.includes(exp.title)) return true
      if (Array.isArray(exp.bullets) && exp.bullets.some(b => b && (b.includes(evidence) || evidence.includes(b)))) return true
    }

    if (Array.isArray(h.actions)) {
      for (const a of h.actions) {
        const orig = (a && typeof a === 'object' ? a.original : '') || ''
        if (!orig.trim()) continue
        if (Array.isArray(exp.bullets) && exp.bullets.some(b => b && (b.includes(orig) || orig.includes(b)))) return true
      }
    }

    const t = exp.title || ''
    if (!t) return false
    const tStripped = stripPrefix(t)
    const text = (h.desc || '') + ' ' + (h.title || '')
    if (text.includes(t)) return true
    if (tStripped && text.includes(tStripped)) return true
    return false
  })
}

function onExpClick(exp) {
  if (isExpHighlighted(exp)) {
    emit('highlight-click', exp)
  }
}
</script>

<style scoped>
.resume-preview-wrap {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

/* ============ 工具栏 ============ */
.toolbar {
  width: 100%;
  max-width: 920px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.tool-info {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-muted);
  font-size: 15px;
}

.dot { opacity: 0.4; }

.tool-actions {
  display: flex;
  gap: 8px;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-md);
  font-size: 15px;
  font-weight: 600;
  box-shadow: var(--shadow-primary);
  transition: all 0.25s var(--ease-out);
}

.tool-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

/* ============ A4 纸张 ============ */
.paper {
  background: white;
  width: 100%;
  max-width: 920px;
  min-height: 1300px;       /* A4 比例 */
  padding: 48px 56px;
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 12px 32px rgba(15, 23, 42, 0.12);
  border-radius: 4px;
  position: relative;
  color: #1F2937;
  font-size: 16.5px;
  line-height: 1.7;
  animation: fadeInUp 0.6s ease;
}

/* ============ 顶部信息 ============ */
.resume-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 18px;
  margin-bottom: 24px;
  border-bottom: 2px solid #1F2937;
}

.name {
  font-size: 36px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #0F172A;
  margin-bottom: 6px;
}

.target {
  font-size: 17px;
  color: #475569;
}

.target span {
  color: var(--color-primary);
  font-weight: 600;
}

.contact {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 16px;
  color: #475569;
}

.contact-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.ci-icon {
  color: var(--color-primary);
  flex-shrink: 0;
}

/* ============ Section ============ */
.resume-section {
  margin-bottom: 22px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 20px;
  font-weight: 700;
  color: #0F172A;
  margin-bottom: 12px;
  letter-spacing: 0.5px;
}

.title-bar {
  width: 4px;
  height: 20px;
  background: var(--gradient-primary);
  border-radius: 2px;
}

/* ============ 教育 ============ */
.edu-list { display: flex; flex-direction: column; gap: 10px; }

.edu-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.edu-row.sub {
  color: #64748B;
  font-size: 16px;
  margin-top: 2px;
}

.edu-school {
  font-weight: 600;
  font-size: 18px;
  color: #0F172A;
}

.edu-period {
  font-size: 15px;
  color: #64748B;
}

.edu-highlights {
  margin: 6px 0 0 14px;
  font-size: 16px;
  color: #334155;
}

.edu-highlights li {
  list-style: disc;
  margin-bottom: 2px;
}

/* ============ 经历 ============ */
.exp-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.exp-item {
  position: relative;
  padding: 4px 8px;
  margin: 0 -8px;
  border-radius: 6px;
  transition: background 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out);
}

.exp-item.exp-highlighted {
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.10), rgba(245, 158, 11, 0.02));
  box-shadow: inset 3px 0 0 var(--color-warning);
  animation: highlightPulse 0.6s var(--ease-out);
  cursor: pointer;
}

@keyframes highlightPulse {
  0% { background: rgba(245, 158, 11, 0.25); }
  100% { background: linear-gradient(90deg, rgba(245, 158, 11, 0.10), rgba(245, 158, 11, 0.02)); }
}

.exp-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 6px;
}

.exp-head-right {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.exp-edit-icon {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  font-size: 13px;
  color: var(--color-primary);
  background: var(--color-primary-soft);
  border: 1px solid var(--color-primary-light);
  border-radius: 999px;
  font-weight: 600;
  transition: all 0.2s var(--ease-out);
  opacity: 0;
}

.exp-item:hover .exp-edit-icon,
.exp-item.exp-highlighted .exp-edit-icon {
  opacity: 1;
}

.exp-edit-icon:hover {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
  transform: translateY(-1px);
}

.exp-title-wrap {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.exp-title {
  font-weight: 700;
  font-size: 19px;
  color: #0F172A;
}

.exp-role {
  font-size: 16px;
  color: #475569;
  font-weight: 500;
}

.exp-period {
  font-size: 15px;
  color: #64748B;
  flex-shrink: 0;
}

.exp-bullets {
  margin: 4px 0 8px 16px;
  color: #1F2937;
}

.exp-bullets li {
  list-style: disc;
  margin-bottom: 3px;
}

.exp-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 500;
  margin-top: 2px;
}

.exp-tag.tag-green {
  background: rgba(16, 185, 129, 0.10);
  color: #047857;
  border: 1px solid rgba(16, 185, 129, 0.30);
}

.exp-tag.tag-yellow {
  background: rgba(245, 158, 11, 0.10);
  color: #B45309;
  border: 1px solid rgba(245, 158, 11, 0.30);
}

/* ============ 技能 ============ */
.skill-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.skill-label {
  flex-shrink: 0;
  width: 80px;
  font-size: 16px;
  color: #64748B;
  padding-top: 2px;
}

.skill-chips {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 4px 14px;
  background: #F1F5F9;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  font-size: 15px;
  color: #334155;
}

/* ============ 获奖 ============ */
.award-list {
  margin-left: 16px;
}

.award-list li {
  list-style: disc;
  margin-bottom: 4px;
}

/* ============ 自评 ============ */
.self-eval {
  color: #334155;
  line-height: 1.7;
}

/* ============ 打印优化 ============ */
@media print {
  .paper {
    box-shadow: none !important;
    min-height: auto;
    max-width: 100%;
    padding: 24mm 18mm;
  }
}

@media (max-width: 768px) {
  .paper {
    padding: 28px 22px;
    min-height: auto;
  }
  .resume-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .exp-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}
</style>
