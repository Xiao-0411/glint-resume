<template>
  <div class="home">
    <!-- 1. Hero + Paths 左右排列（顶部） -->
    <section class="combo-section">
      <!-- 顶部居中大标题 -->
      <div class="combo-headline">
        <h1 class="hero-title">
          一键生成<span class="hero-highlight">专业简历</span>，告别繁琐排版
        </h1>
      </div>

      <div class="combo-inner">
        <!-- 左侧：Hero 描述 + CTA -->
        <div class="combo-hero">
          <p class="hero-desc">
            上传旧简历智能优化，或者告诉 AI 你的目标岗位，从零开始，10 分钟生成一份让 HR 眼前一亮的简历
          </p>
          <div class="hero-cta">
            <div class="hero-input-row">
              <input
                ref="inputRef"
                v-model="jobInput"
                class="hero-input"
                type="text"
                placeholder="输入你想应聘的岗位，如「产品经理」..."
                @keydown.enter.prevent="onStart"
              />
              <button class="hero-btn" type="button" @click="onStart" :disabled="!jobInput.trim()">
                开始生成
              </button>
            </div>
            <div class="hero-tags">
              <span class="tags-hint">热门：</span>
              <button v-for="job in quickJobs" :key="job" class="hero-tag" @click="quickSelect(job)">
                {{ job }}
              </button>
            </div>
          </div>
          <div class="hero-stats">
            <div class="stat-item">
              <span class="stat-num">{{ stat1Display }}+</span>
              <span class="stat-label">优秀简历生成</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat-item">
              <span class="stat-num">{{ stat2.toFixed(1) }}</span>
              <span class="stat-label">用户评分</span>
            </div>
            <div class="stat-divider"></div>
            <div class="stat-item">
              <span class="stat-num">{{ stat3 }}%</span>
              <span class="stat-label">面试邀请率提升</span>
            </div>
          </div>
        </div>

        <!-- 右侧：双路径卡片（垂直堆叠） -->
        <div class="combo-paths">
          <div class="paths-header">
            <h2 class="paths-title">两种方式，同样专业</h2>
            <p class="paths-sub">选择适合你的方式</p>
          </div>
          <div class="paths-stack">
            <div class="path-card path-from-scratch" @click="focusInput">
              <div class="path-icon">
                <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 20h9"/>
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                </svg>
              </div>
              <div class="path-body">
                <h3 class="path-title">从零生成</h3>
                <p class="path-desc">告诉 AI 你的目标岗位，STAR-L 法则自动重塑经历</p>
                <span class="path-action">
                  开始对话
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12"/>
                    <polyline points="12 5 19 12 12 19"/>
                  </svg>
                </span>
              </div>
            </div>
            <div class="path-card path-upload-resume" @click="goUpload">
              <div class="path-icon">
                <svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </div>
              <div class="path-body">
                <h3 class="path-title">上传优化</h3>
                <p class="path-desc">上传 PDF 简历，AI 五维诊断并精准改进</p>
                <span class="path-action">
                  上传简历
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12"/>
                    <polyline points="12 5 19 12 12 19"/>
                  </svg>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 2. 三步搞定专业简历 -->
    <section class="steps-section">
      <div class="section-header">
        <h2 class="section-title">三步搞定专业简历</h2>
        <p class="section-sub">比传统简历写作快 5 倍，质量超越 90% 的求职者</p>
      </div>
      <div class="steps-grid">
        <div class="step-card">
          <div class="step-num">1</div>
          <h4 class="step-title">输入目标岗位</h4>
          <p class="step-desc">告诉 AI 你想应聘的职位，系统自动匹配该岗位的核心能力模型</p>
        </div>
        <div class="step-arrow">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/>
            <polyline points="12 5 19 12 12 19"/>
          </svg>
        </div>
        <div class="step-card">
          <div class="step-num">2</div>
          <h4 class="step-title">AI 智能对话</h4>
          <p class="step-desc">像和朋友聊天一样，AI 引导你挖掘校园经历、实习项目，用 STAR-L 法则重塑</p>
        </div>
        <div class="step-arrow">
          <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/>
            <polyline points="12 5 19 12 12 19"/>
          </svg>
        </div>
        <div class="step-card">
          <div class="step-num">3</div>
          <h4 class="step-title">一键导出简历</h4>
          <p class="step-desc">自动排版生成专业 PDF 简历，附带五维质量评分报告，即拿即用</p>
        </div>
      </div>
    </section>

    <!-- 3. 核心优势 -->
    <section class="features-section">
      <div class="section-header">
        <h2 class="section-title">为什么选择识光简历</h2>
      </div>
      <div class="features-grid">
        <div class="feature-item">
          <div class="feature-icon">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
          </div>
          <h4>STAR-L 法则驱动</h4>
          <p>基于 HR 最认可的情境-任务-行动-结果-学习框架，让每段经历都直击面试官</p>
        </div>
        <div class="feature-item">
          <div class="feature-icon">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
          </div>
          <h4>五维质量评估</h4>
          <p>从完整性、匹配度、量化度、专业性、可读性五个维度精准诊断简历质量</p>
        </div>
        <div class="feature-item">
          <div class="feature-icon">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </div>
          <h4>诚信可追溯</h4>
          <p>AI 辅助包装而非虚构，所有描述基于你的真实经历，拒绝简历造假</p>
        </div>
        <div class="feature-item">
          <div class="feature-icon">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
          </div>
          <h4>一键导出 PDF</h4>
          <p>自动排版为 A4 标准格式，即拿即用，无需手动调整格式和排版</p>
        </div>
      </div>
    </section>

    <!-- 底部 -->
    <footer class="page-footer">
      <div class="footer-inner">
        <div class="footer-brand">
          <span class="footer-logo-text">识光简历</span>
          <span class="footer-tagline">STAR-L 法则驱动 · AI 辅助包装，诚信可追溯</span>
        </div>
        <div class="footer-links">
          <span>简历模板</span>
          <span>使用帮助</span>
          <span>关于我们</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { extractJobName } from '@/utils/jobMatcher'

const router = useRouter()
const store = useChatStore()
const auth = useAuthStore()

const jobInput = ref('')
const inputRef = ref(null)
const quickJobs = ['产品经理', 'Java 后端开发', '前端开发', '数据分析师', 'UI 设计师']

// 数字滚动动画
const stat1 = ref(0)
const stat2 = ref(0)
const stat3 = ref(0)

const stat1Display = computed(() => stat1.value.toLocaleString('en-US'))

function animateNum(refVar, target, duration = 1400, isFloat = false) {
  const start = performance.now()
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - Math.pow(1 - t, 3)
    refVar.value = isFloat ? +(target * eased).toFixed(1) : Math.round(target * eased)
    if (t < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

onMounted(() => {
  animateNum(stat1, 3200)
  animateNum(stat2, 4.9, 1400, true)
  animateNum(stat3, 85)
})

function quickSelect(job) {
  jobInput.value = `我想做${job}`
  nextTick(() => {
    inputRef.value?.focus()
  })
}

function focusInput() {
  inputRef.value?.focus()
  inputRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function onStart() {
  const raw = jobInput.value.trim()
  if (!raw) return
  auth.requireLogin(() => {
    const job = extractJobName(raw)
    store.reset()
    store.setTargetJob(job)
    router.push('/chat')
  })
}

function goUpload() {
  // 上传阶段无需登录，登录推迟到「选择/拖拽文件」时再触发
  store.reset()
  router.push('/upload')
}
</script>

<style scoped>
.home {
  min-height: 100%;
  width: 100%;
  background: #FFFFFF;
}

/* ============ 2. 三步流程（中段） ============ */
.steps-section {
  position: relative;
  padding: 8rem clamp(64px, 7vw, 120px) 8.5rem;
  background: linear-gradient(180deg, #FFFFFF 0%, #FAFBFF 60%, #FFFFFF 100%);
  overflow: hidden;
}

.section-header {
  position: relative;
  text-align: center;
  margin-bottom: 5.5rem;
}

.section-title {
  font-size: 2.6rem;
  font-weight: 800;
  color: var(--color-text);
  margin-bottom: 1.1rem;
  letter-spacing: -1.2px;
  line-height: 1.2;
}

.section-sub {
  font-size: 1.5rem;
  color: var(--color-text-muted);
}

.steps-grid {
  position: relative;
  max-width: 1536px;
  margin: 0 auto;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 0;
}

.step-card {
  flex: 1;
  max-width: 360px;
  text-align: center;
  padding: 0 24px;
  position: relative;
  animation: fadeInUp 0.6s var(--ease-out) backwards;
}

.step-card:nth-child(1) { animation-delay: 0.05s; }
.step-card:nth-child(3) { animation-delay: 0.20s; }
.step-card:nth-child(5) { animation-delay: 0.35s; }

.step-num {
  width: 94px;
  height: 94px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--gradient-primary);
  color: white;
  font-size: 2.15rem;
  font-weight: 800;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.30);
  position: relative;
}

.step-num::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid rgba(37, 99, 235, 0.20);
  animation: pulseRing 2.4s var(--ease-out) infinite;
}

@keyframes pulseRing {
  0% { transform: scale(1); opacity: 0.8; }
  100% { transform: scale(1.5); opacity: 0; }
}

.step-card:nth-child(3) .step-num::before { animation-delay: 0.4s; }
.step-card:nth-child(5) .step-num::before { animation-delay: 0.8s; }

.step-title {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 0.75rem;
  letter-spacing: -0.3px;
}

.step-desc {
  font-size: 1.3rem;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

.step-arrow {
  flex-shrink: 0;
  padding-top: 26px;
  color: var(--color-primary-light);
  animation: fadeIn 0.8s ease 0.4s backwards;
}

/* ============ 1. Hero + Paths 左右（主入口） ============ */
.combo-section {
  padding: 6.5rem clamp(64px, 7vw, 120px) 9.5rem;
  min-height: calc(100vh - 76px);
  background:
    radial-gradient(ellipse 80% 60% at 20% 0%, rgba(37, 99, 235, 0.07), transparent 70%),
    radial-gradient(ellipse 60% 50% at 90% 10%, rgba(8, 145, 178, 0.06), transparent 70%),
    linear-gradient(180deg, #FAFBFF 0%, #FFFFFF 100%);
  position: relative;
  overflow: hidden;
}

.combo-section::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(37, 99, 235, 0.028) 1px, transparent 1px),
    linear-gradient(90deg, rgba(37, 99, 235, 0.028) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 80% 70% at 50% 20%, black 30%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse 80% 70% at 50% 20%, black 30%, transparent 80%);
  pointer-events: none;
}

.combo-headline {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 1536px;
  margin: 0 auto 5.5rem;
  text-align: center;
  animation: fadeInUp 0.7s var(--ease-out);
}

.combo-inner {
  position: relative;
  z-index: 1;
  max-width: 1536px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.9fr);
  gap: 96px;
  align-items: center;
}

/* ---- Hero 文案 ---- */
.combo-hero {
  display: flex;
  flex-direction: column;
  animation: fadeInUp 0.7s var(--ease-out) 0.1s backwards;
}

.hero-title {
  font-size: 5.5rem;
  font-weight: 800;
  line-height: 1.08;
  color: var(--color-text);
  letter-spacing: -3px;
  margin: 0;
  white-space: nowrap;
}

.hero-highlight {
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  color: transparent;
}

.hero-highlight::selection {
  background: rgba(37, 99, 235, 0.22);
  -webkit-text-fill-color: transparent;
  color: transparent;
}

.hero-highlight::-moz-selection {
  background: rgba(37, 99, 235, 0.22);
  -webkit-text-fill-color: transparent;
  color: transparent;
}

.hero-desc {
  font-size: 1.35rem;
  color: var(--color-text-secondary);
  line-height: 1.65;
  margin-bottom: 2.8rem;
  max-width: 680px;
}

.hero-cta {
  margin-bottom: 2.8rem;
  width: 100%;
}

.hero-input-row {
  display: flex;
  gap: 14px;
  margin-bottom: 22px;
}

.hero-input {
  flex: 1;
  height: 64px;
  padding: 0 24px;
  background: #FFFFFF;
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-lg);
  font-size: 1.4rem;
  color: var(--color-text);
  transition: all 0.25s var(--ease-out);
  font-family: inherit;
  box-shadow: var(--shadow-xs);
}

.hero-input:hover {
  border-color: var(--color-border-strong);
}

.hero-input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
  outline: none;
}

.hero-input::placeholder {
  color: var(--color-text-muted);
  font-size: 1.15rem;
}

.hero-btn {
  height: 64px;
  padding: 0 40px;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-lg);
  font-weight: 600;
  font-size: 1.4rem;
  white-space: nowrap;
  transition: all 0.25s var(--ease-out);
  box-shadow: var(--shadow-primary);
  position: relative;
  overflow: hidden;
}

.hero-btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.18) 0%, transparent 50%);
  opacity: 0;
  transition: opacity 0.3s var(--ease-out);
}

.hero-btn:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

.hero-btn:not(:disabled):hover::after {
  opacity: 1;
}

.hero-btn:not(:disabled):active {
  transform: translateY(0);
}

.hero-btn:disabled {
  background: var(--color-border);
  color: var(--color-text-muted);
  cursor: not-allowed;
  box-shadow: none;
}

.hero-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.tags-hint {
  font-size: 1.25rem;
  color: var(--color-text-muted);
  margin-right: 4px;
}

.hero-tag {
  padding: 11px 24px;
  background: #FFFFFF;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  transition: all 0.2s var(--ease-out);
  font-family: inherit;
  font-weight: 500;
}

.hero-tag:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
  transform: translateY(-1px);
}

.hero-tag:active {
  transform: scale(0.96);
}

.hero-stats {
  display: flex;
  align-items: center;
  gap: 0;
  padding-top: 30px;
  border-top: 1px solid rgba(229, 231, 235, 0.7);
  margin-top: 14px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.stat-num {
  font-size: 2.3rem;
  font-weight: 800;
  letter-spacing: -0.9px;
  font-feature-settings: "tnum" on;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  color: transparent;
}

.stat-label {
  font-size: 1.25rem;
  color: var(--color-text-muted);
}

.stat-divider {
  width: 1px;
  height: 58px;
  background: linear-gradient(180deg, transparent, var(--color-border) 30%, var(--color-border) 70%, transparent);
  margin: 0 38px;
}

/* ---- Paths 卡片（右侧垂直堆叠） ---- */
.combo-paths {
  display: flex;
  flex-direction: column;
  gap: 30px;
  animation: fadeInUp 0.7s var(--ease-out) 0.15s backwards;
}

.paths-header {
  margin-bottom: 14px;
}

.paths-title {
  font-size: 2.1rem;
  font-weight: 800;
  color: var(--color-text);
  letter-spacing: -0.4px;
  margin-bottom: 8px;
}

.paths-sub {
  font-size: 1.3rem;
  color: var(--color-text-muted);
}

.paths-stack {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.path-card {
  position: relative;
  padding: 2rem 2.2rem;
  border-radius: var(--radius-xl);
  cursor: pointer;
  transition: all 0.35s var(--ease-out);
  display: flex;
  align-items: flex-start;
  gap: 26px;
  border: 1px solid transparent;
  overflow: hidden;
}

.path-card::before {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.35s var(--ease-out);
  pointer-events: none;
}

/* 流光扫光效果 */
.path-card::after {
  content: '';
  position: absolute;
  top: 0;
  left: -75%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    100deg,
    transparent 20%,
    rgba(255, 255, 255, 0.16) 50%,
    transparent 80%
  );
  transform: skewX(-20deg);
  transition: left 0.8s var(--ease-out);
  pointer-events: none;
}

.path-card:hover {
  transform: translateY(-3px);
}

.path-card:hover::after {
  left: 125%;
}

.path-card:active {
  transform: translateY(-1px) scale(0.99);
}

.path-card.path-from-scratch {
  background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 55%, #0891B2 100%);
  color: white;
  box-shadow: 0 6px 24px rgba(37, 99, 235, 0.25);
}

.path-card.path-from-scratch::before {
  background:
    radial-gradient(circle at 80% 20%, rgba(255, 255, 255, 0.2), transparent 50%),
    radial-gradient(circle at 20% 90%, rgba(8, 145, 178, 0.3), transparent 50%);
}

.path-card.path-from-scratch:hover {
  box-shadow: 0 14px 40px rgba(37, 99, 235, 0.40);
}

.path-card.path-from-scratch:hover::before {
  opacity: 1;
}

.path-card.path-from-scratch .path-desc {
  color: rgba(255, 255, 255, 0.82);
}

.path-card.path-from-scratch .path-action {
  color: rgba(255, 255, 255, 0.95);
}

.path-card.path-upload-resume {
  background: var(--gradient-card);
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
}

.path-card.path-upload-resume:hover {
  border-color: var(--color-primary-light);
  box-shadow: var(--shadow-lg);
}

.path-icon {
  width: 76px;
  height: 76px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  position: relative;
  z-index: 1;
  transition: transform 0.35s var(--ease-out);
}

.path-card:hover .path-icon {
  transform: scale(1.08) rotate(-3deg);
}

.path-card.path-from-scratch .path-icon {
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(10px);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
}

.path-card.path-upload-resume .path-icon {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.path-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  z-index: 1;
}

.path-title {
  font-size: 1.7rem;
  font-weight: 700;
  letter-spacing: -0.3px;
}

.path-desc {
  font-size: 1.25rem;
  line-height: 1.6;
}

.path-card.path-upload-resume .path-desc {
  color: var(--color-text-secondary);
}

.path-action {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 6px;
  transition: gap 0.25s var(--ease-out);
}

.path-card:hover .path-action {
  gap: 10px;
}

.path-card.path-upload-resume .path-action {
  color: var(--color-primary);
}

/* ============ 3. 核心优势 ============ */
.features-section {
  padding: 8rem clamp(64px, 7vw, 120px) 8.5rem;
  background: linear-gradient(180deg, #F9FAFB 0%, #FAFBFF 100%);
}

.features-grid {
  max-width: 1536px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 44px;
}

.feature-item {
  display: flex;
  flex-direction: column;
  gap: 1.15rem;
  padding: 2.9rem 2.9rem 3rem;
  border-radius: var(--radius-xl);
  background: var(--gradient-card);
  border: 1px solid var(--color-border-light);
  transition: all 0.3s var(--ease-out);
  position: relative;
  overflow: hidden;
}

.feature-item::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: var(--gradient-primary);
  transform: scaleY(0);
  transform-origin: top;
  transition: transform 0.35s var(--ease-out);
}

.feature-item:hover {
  border-color: var(--color-primary-light);
  box-shadow: var(--shadow-md);
  transform: translateY(-3px);
}

.feature-item:hover::before {
  transform: scaleY(1);
}

.feature-icon {
  width: 76px;
  height: 76px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  transition: all 0.3s var(--ease-out);
}

.feature-item:hover .feature-icon {
  background: var(--gradient-primary);
  color: white;
  transform: scale(1.06);
}

.feature-item h4 {
  font-size: 1.7rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.3px;
}

.feature-item p {
  font-size: 1.3rem;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

/* ============ 底部 ============ */
.page-footer {
  background: linear-gradient(180deg, #FAFBFF 0%, #F3F4F6 100%);
  border-top: 1px solid var(--color-border-light);
  padding: 4rem clamp(64px, 7vw, 120px);
}

.footer-inner {
  max-width: 1536px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-brand {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.footer-logo-text {
  font-size: 1.55rem;
  font-weight: 700;
  color: var(--color-text);
}

.footer-tagline {
  font-size: 1.25rem;
  color: var(--color-text-muted);
}

.footer-links {
  display: flex;
  gap: 40px;
  font-size: 1.3rem;
  color: var(--color-text-secondary);
}

.footer-links span {
  cursor: pointer;
  transition: color 0.2s var(--ease-out);
}

.footer-links span:hover {
  color: var(--color-primary);
}

/* ============ 响应式 ============ */
@media (max-width: 1440px) {
  .hero-title {
    font-size: 5.3rem;
    letter-spacing: -2px;
  }
  .combo-inner {
    gap: 72px;
  }
}

@media (max-width: 1200px) {
  .hero-title {
    font-size: 4.8rem;
    letter-spacing: -1.6px;
  }
  .combo-inner {
    gap: 56px;
  }
}

@media (max-width: 1024px) {
  .combo-inner {
    grid-template-columns: 1fr;
    gap: 80px;
  }

  .hero-desc {
    max-width: 100%;
  }

  .hero-title {
    font-size: 3.4rem;
    letter-spacing: -1.5px;
  }
}

@media (max-width: 900px) {
  .hero-title {
    font-size: 2.6rem;
    letter-spacing: -1px;
    white-space: normal;
  }

  .section-title {
    font-size: 2.2rem;
  }

  .combo-section {
    padding: 4rem 40px 5.5rem;
  }

  .steps-section,
  .features-section {
    padding: 5rem 40px 5.5rem;
  }

  .combo-headline {
    margin-bottom: 3rem;
  }

  .section-header {
    margin-bottom: 3rem;
  }

  .steps-grid {
    flex-direction: column;
    align-items: center;
    gap: 16px;
  }

  .step-card {
    max-width: 100%;
  }

  .step-arrow {
    transform: rotate(90deg);
  }

  .features-grid {
    grid-template-columns: 1fr;
  }

  .hero-stats {
    flex-wrap: wrap;
    gap: 12px;
  }

  .stat-divider {
    margin: 0 16px;
  }
}

@media (max-width: 640px) {
  .nav-inner {
    padding: 14px 20px;
  }

  .steps-section,
  .combo-section,
  .features-section {
    padding: 3rem 20px 3.5rem;
  }

  .hero-input-row {
    flex-direction: column;
  }

  .hero-btn {
    width: 100%;
    justify-content: center;
  }

  .section-title {
    font-size: 1.9rem;
  }

  .hero-title {
    font-size: 2.2rem;
  }

  .footer-inner {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }
}
</style>
