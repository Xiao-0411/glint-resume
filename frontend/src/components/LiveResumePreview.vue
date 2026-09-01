<template>
  <div class="live-paper-wrap">
    <div class="paper-label">
      <span class="dot-live"></span>
      <span>{{ previewLabel }}</span>
    </div>

    <div class="paper">
      <!-- 顶部基本信息 -->
      <header class="resume-header">
        <div class="name-block">
          <transition name="fade-slide" mode="out-in">
            <h1 v-if="has('basic')" key="real" class="name">{{ displayResume.basic.fullname }}</h1>
            <h1 v-else key="ph" class="name name-placeholder">姓 名</h1>
          </transition>
          <div class="target">求职意向：<span>{{ targetJob || '——' }}</span></div>
        </div>
        <div class="contact">
          <transition-group name="fade-slide">
            <template v-if="has('basic')">
              <div class="contact-item" key="email">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ci-icon">
                  <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                  <polyline points="22,6 12,13 2,6"/>
                </svg>
                <span>{{ displayResume.basic.email }}</span>
              </div>
              <div class="contact-item" key="phone">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ci-icon">
                  <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>
                </svg>
                <span>{{ displayResume.basic.phone }}</span>
              </div>
              <div class="contact-item" key="loc">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ci-icon">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                  <circle cx="12" cy="10" r="3"/>
                </svg>
                <span>{{ displayResume.basic.location }}</span>
              </div>
            </template>
            <template v-else>
              <div class="contact-placeholder" key="ph1">联系方式</div>
              <div class="contact-placeholder" key="ph2">———</div>
            </template>
          </transition-group>
        </div>
      </header>

      <!-- 教育背景 -->
      <transition name="section-reveal">
        <section v-if="has('education')" class="resume-section">
          <h2 class="section-title">
            <span class="title-bar"></span>
            <span>教育背景</span>
          </h2>
          <div class="edu-list">
            <div v-for="(edu, i) in displayResume.education" :key="i" class="edu-item">
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
      </transition>

      <!-- 项目经历 -->
      <transition name="section-reveal">
        <section v-if="has('experiences')" class="resume-section">
          <h2 class="section-title">
            <span class="title-bar"></span>
            <span>项目经历</span>
          </h2>
          <div class="exp-list">
            <div v-for="(exp, i) in displayResume.experiences" :key="exp.id || i" class="exp-item">
              <div class="exp-head">
                <div class="exp-title-wrap">
                  <span class="exp-title">{{ exp.title }}</span>
                  <span class="exp-role">| {{ exp.role }}</span>
                </div>
                <span class="exp-period">{{ exp.period }}</span>
              </div>
              <ul class="exp-bullets">
                <li v-for="(b, j) in exp.bullets" :key="j">{{ b }}</li>
              </ul>
            </div>
          </div>
        </section>
      </transition>

      <!-- 技能 -->
      <transition name="section-reveal">
        <section v-if="has('skills')" class="resume-section">
          <h2 class="section-title">
            <span class="title-bar"></span>
            <span>专业技能</span>
          </h2>
          <div class="skill-grid">
            <div class="skill-row">
              <span class="skill-label">技术栈</span>
              <div class="skill-chips">
                <span v-for="s in displayResume.skills.technical" :key="s" class="chip">{{ s }}</span>
              </div>
            </div>
            <div v-if="displayResume.skills.tools.length" class="skill-row">
              <span class="skill-label">工具</span>
              <div class="skill-chips">
                <span v-for="s in displayResume.skills.tools" :key="s" class="chip">{{ s }}</span>
              </div>
            </div>
            <div class="skill-row">
              <span class="skill-label">产品能力</span>
              <div class="skill-chips">
                <span v-for="s in displayResume.skills.product" :key="s" class="chip">{{ s }}</span>
              </div>
            </div>
            <div class="skill-row">
              <span class="skill-label">软技能</span>
              <div class="skill-chips">
                <span v-for="s in displayResume.skills.soft" :key="s" class="chip">{{ s }}</span>
              </div>
            </div>
          </div>
        </section>
      </transition>

      <!-- 获奖 -->
      <transition name="section-reveal">
        <section v-if="has('awards') && displayResume.awards && displayResume.awards.length" class="resume-section">
          <h2 class="section-title">
            <span class="title-bar"></span>
            <span>获奖荣誉</span>
          </h2>
          <ul class="award-list">
            <li v-for="(a, i) in displayResume.awards" :key="i">{{ a }}</li>
          </ul>
        </section>
      </transition>

      <!-- 空状态：所有 section 都未解锁时 -->
      <div v-if="completedCount === 0" class="awaiting">
        <div class="awaiting-icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="9" y1="13" x2="15" y2="13"/>
            <line x1="9" y1="17" x2="13" y2="17"/>
          </svg>
        </div>
        <div class="awaiting-title">简历还是空白的</div>
        <div class="awaiting-desc">从左侧开始对话，每完成一项就会自动写入这里</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { buildMockResume } from '@/api/mock'

const props = defineProps({
  targetJob: { type: String, default: '' },
  completedSections: { type: Array, default: () => [] },
  // 后端实时下发的真实抽取数据;mock 模式下为空对象 → 回落到样例排版
  profile: { type: Object, default: () => ({}) }
})

// 是否拿到了后端真实数据(任一关键字段非空)
const hasReal = computed(() => {
  const p = props.profile || {}
  const skills = p.skills || {}
  return !!(
    p.fullname ||
    p.email ||
    p.phone ||
    p.location ||
    (Array.isArray(p.education) && p.education.length) ||
    (Array.isArray(p.experiences) && p.experiences.length) ||
    (Array.isArray(skills.technical) && skills.technical.length) ||
    (Array.isArray(skills.tools) && skills.tools.length) ||
    (Array.isArray(skills.product) && skills.product.length) ||
    (Array.isArray(skills.soft) && skills.soft.length) ||
    (Array.isArray(p.awards) && p.awards.length)
  )
})

// 抽取阶段经历还没有 bullets,临时用 STAR-L 要点展示
function starlToBullets(star) {
  if (!star || typeof star !== 'object') return []
  return ['situation', 'task', 'action', 'result', 'learning']
    .map(k => star[k])
    .filter(v => v && String(v).trim())
}

function mapProfile(p) {
  return {
    basic: {
      fullname: p.fullname || '',
      target_job: p.target_job || props.targetJob || '',
      email: p.email || '',
      phone: p.phone || '',
      location: p.location || ''
    },
    education: Array.isArray(p.education) ? p.education : [],
    experiences: (Array.isArray(p.experiences) ? p.experiences : []).map((e, i) => ({
      id: e.id || `exp_${i + 1}`,
      title: e.title || '',
      role: e.role || '',
      period: e.period || '',
      bullets: (Array.isArray(e.bullets) && e.bullets.length) ? e.bullets : starlToBullets(e.star_l)
    })),
    skills: {
      technical: (p.skills && p.skills.technical) || [],
      tools: (p.skills && p.skills.tools) || [],
      product: (p.skills && p.skills.product) || [],
      soft: (p.skills && p.skills.soft) || []
    },
    awards: Array.isArray(p.awards) ? p.awards : []
  }
}

// 真实模式渲染真实数据;否则(mock 模式)回落到样例排版
const displayResume = computed(() => hasReal.value ? mapProfile(props.profile) : buildMockResume(props.targetJob))
const previewLabel = computed(() => hasReal.value ? '实时预览 · 随对话自动填充' : '排版预览 · 示例')

function has(key) {
  return props.completedSections.includes(key)
}

const completedCount = computed(() => props.completedSections.length)
</script>

<style scoped>
.live-paper-wrap {
  width: 100%;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.paper-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--color-primary-dark);
  background: rgba(37, 99, 235, 0.08);
  border: 1px solid rgba(37, 99, 235, 0.15);
  letter-spacing: 0.4px;
  flex-shrink: 0;
}

.dot-live {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
  box-shadow: 0 0 0 3px rgba(5, 150, 105, 0.18);
  animation: pulse-live 1.6s ease-in-out infinite;
}

@keyframes pulse-live {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.85); }
}

/* ============ A4 纸张 ============ */
.paper {
  background: white;
  width: 100%;
  max-width: 880px;
  flex: 1;
  min-height: 0;
  padding: 44px 52px;
  box-shadow:
    0 1px 2px rgba(15, 23, 42, 0.04),
    0 16px 40px rgba(15, 23, 42, 0.10);
  border-radius: 6px;
  color: #1F2937;
  font-size: 15px;
  line-height: 1.7;
  position: relative;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
}

.paper::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--gradient-primary);
  border-radius: 6px 6px 0 0;
  opacity: 0.5;
}

/* ============ 顶部信息 ============ */
.resume-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  margin-bottom: 22px;
  border-bottom: 2px solid #1F2937;
  flex-wrap: wrap;
}

.name {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 2px;
  color: #0F172A;
  margin-bottom: 6px;
  min-height: 36px;
}

.name-placeholder {
  color: #CBD5E1;
  font-weight: 500;
  letter-spacing: 8px;
}

.target {
  font-size: 14px;
  color: #475569;
}

.target span {
  color: var(--color-primary);
  font-weight: 600;
}

.contact {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #475569;
  min-width: 180px;
}

.contact-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.contact-placeholder {
  color: #CBD5E1;
  font-size: 13px;
  letter-spacing: 2px;
}

.ci-icon {
  color: var(--color-primary);
  flex-shrink: 0;
}

/* ============ Section ============ */
.resume-section {
  margin-bottom: 20px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 16px;
  font-weight: 700;
  color: #0F172A;
  margin-bottom: 10px;
  letter-spacing: 0.5px;
}

.title-bar {
  width: 3px;
  height: 17px;
  background: var(--gradient-primary);
  border-radius: 2px;
}

/* ============ 教育 ============ */
.edu-list { display: flex; flex-direction: column; gap: 8px; }

.edu-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.edu-row.sub {
  color: #64748B;
  font-size: 13px;
  margin-top: 1px;
}

.edu-school {
  font-weight: 600;
  font-size: 14.5px;
  color: #0F172A;
}

.edu-period {
  font-size: 12.5px;
  color: #64748B;
}

.edu-highlights {
  margin: 4px 0 0 14px;
  font-size: 13px;
  color: #334155;
}

.edu-highlights li {
  list-style: disc;
  margin-bottom: 1px;
}

/* ============ 经历 ============ */
.exp-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.exp-item {
  padding: 2px 6px;
  margin: 0 -6px;
}

.exp-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 4px;
  flex-wrap: wrap;
  gap: 4px;
}

.exp-title-wrap {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}

.exp-title {
  font-weight: 700;
  font-size: 15px;
  color: #0F172A;
}

.exp-role {
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}

.exp-period {
  font-size: 12.5px;
  color: #64748B;
  flex-shrink: 0;
}

.exp-bullets {
  margin: 2px 0 0 14px;
  color: #1F2937;
}

.exp-bullets li {
  list-style: disc;
  margin-bottom: 2px;
  font-size: 13px;
}

/* ============ 技能 ============ */
.skill-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.skill-label {
  flex-shrink: 0;
  width: 64px;
  font-size: 13px;
  color: #64748B;
  padding-top: 2px;
}

.skill-chips {
  flex: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.chip {
  padding: 3px 10px;
  background: #F1F5F9;
  border: 1px solid #E2E8F0;
  border-radius: 5px;
  font-size: 12.5px;
  color: #334155;
}

/* ============ 获奖 ============ */
.award-list {
  margin-left: 16px;
}

.award-list li {
  list-style: disc;
  margin-bottom: 3px;
  font-size: 13px;
}

/* ============ 等待状态 ============ */
.awaiting {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 60px 24px;
  gap: 12px;
  color: var(--color-text-muted);
}

.awaiting-icon {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.06), rgba(8, 145, 178, 0.04));
  color: var(--color-primary);
  margin-bottom: 4px;
}

.awaiting-title {
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.awaiting-desc {
  font-size: 0.88rem;
  line-height: 1.6;
  max-width: 260px;
}

/* ============ 过渡动画 ============ */
.section-reveal-enter-active {
  transition: all 0.55s cubic-bezier(0.16, 1, 0.3, 1);
}

.section-reveal-leave-active {
  transition: all 0.3s ease;
}

.section-reveal-enter-from {
  opacity: 0;
  transform: translateY(14px);
}

.section-reveal-leave-to {
  opacity: 0;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.4s var(--ease-out);
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ============ 响应式 ============ */
@media (max-width: 1100px) {
  .paper {
    padding: 28px 32px;
    font-size: 13.5px;
  }
  .name { font-size: 26px; }
  .resume-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
}
</style>
