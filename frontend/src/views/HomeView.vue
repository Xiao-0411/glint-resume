<template>
  <div class="home">
    <div class="home-pattern" aria-hidden="true"></div>
    <!-- ====== 1. Hero ====== -->
    <section class="hero">
      <div class="container">
        <div class="hero-badge">
          <span class="badge-dot"></span>
          AI 智能简历平台
        </div>
        <h1 class="hero-title">
          让你的简历<ShinyText color="#4F46E5" shine-color="#A78BFA" :duration="3">脱颖而出</ShinyText>
        </h1>
        <p class="hero-desc">
          告诉 AI 你的经历和目标，10 分钟生成让 HR 眼前一亮的专业简历
        </p>

        <div class="hero-action">
          <div class="hero-input-wrap">
            <svg class="hero-input-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              ref="inputRef"
              v-model="jobInput"
              class="hero-input"
              type="text"
              placeholder="输入你想应聘的岗位，如「产品经理」..."
              @keydown.enter.prevent="onStart"
            />
            <button class="hero-btn" @click="onStart" :disabled="!jobInput.trim()">
              开始生成
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
            </button>
          </div>
          <div class="hero-tags">
            <button v-for="job in quickJobs" :key="job" class="hero-tag" @click="quickSelect(job)">{{ job }}</button>
          </div>
        </div>

        <div class="hero-paths">
          <button class="hero-path purple" type="button" @click="focusInput">
            <div class="hp-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
              </svg>
            </div>
            <div class="hp-text">
              <span class="hp-badge">推荐</span>
              <strong>从零生成简历</strong>
              <span>AI 引导挖掘经历，STAR-L 法则重塑</span>
            </div>
            <svg class="hp-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
          <button class="hero-path white" type="button" @click="goUpload">
            <div class="hp-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <div class="hp-text">
              <strong>上传简历优化</strong>
              <span>上传 PDF，AI 五维诊断并精准改进</span>
            </div>
            <svg class="hp-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
        </div>

        <div class="hero-stats">
          <div class="hstat">
            <span class="hstat-num">{{ stat1Display }}+</span>
            <span class="hstat-label">简历已生成</span>
          </div>
          <div class="hstat-divider"></div>
          <div class="hstat">
            <span class="hstat-num">{{ stat2.toFixed(1) }}</span>
            <span class="hstat-label">用户评分</span>
          </div>
          <div class="hstat-divider"></div>
          <div class="hstat">
            <span class="hstat-num">{{ stat3 }}%</span>
            <span class="hstat-label">面试邀请率提升</span>
          </div>
        </div>
      </div>
    </section>

    <section class="steps">
      <div class="container">
        <div class="section-head">
          <span class="section-label">三步搞定</span>
          <h2 class="section-title">比传统方式<span class="text-gradient">快 5 倍</span></h2>
        </div>
        <div class="steps-grid">
          <article class="step-card" v-for="step in steps" :key="step.title">
            <div class="step-visual" :class="`step-visual--${step.icon}`" aria-hidden="true">
              <div class="visual-toolbar"><i></i><i></i><i></i></div>
              <div v-if="step.icon === 'target'" class="target-preview">
                <span class="preview-label">目标岗位</span>
                <strong>产品经理</strong>
                <div class="preview-tags"><span>用户洞察</span><span>数据分析</span></div>
              </div>
              <div v-else-if="step.icon === 'message'" class="message-preview">
                <span class="message-ai">你最有成就感的项目是什么？</span>
                <span class="message-user">校园二手平台，从 0 做到 2,000 用户</span>
              </div>
              <div v-else class="resume-preview">
                <div class="resume-avatar"></div>
                <div class="resume-lines"><strong></strong><span></span><span></span></div>
                <div class="resume-score">92</div>
              </div>
            </div>
            <div class="step-num">{{ step.eyebrow }}</div>
            <h4>{{ step.title }}</h4>
            <p>{{ step.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <section class="features">
      <div class="container">
        <div class="section-head">
          <span class="section-label">为什么选择我们</span>
          <h2 class="section-title">不只是工具，更是<span class="text-gradient">求职伙伴</span></h2>
        </div>
        <div class="features-grid">
          <SpotlightCard class="feat-card" :class="{ 'feat-card-featured': feat.featured }" v-for="feat in features" :key="feat.title">
            <div class="feat-icon-wrap">
              <HomeIcon :name="feat.icon" />
            </div>
            <h4>{{ feat.title }}</h4>
            <p>{{ feat.desc }}</p>
          </SpotlightCard>
        </div>
      </div>
    </section>

    <section class="compare">
      <div class="container">
        <div class="section-head">
          <span class="section-label">真实效果</span>
          <h2 class="section-title">优化效果<span class="text-gradient">立竿见影</span></h2>
        </div>
        <div class="compare-row">
          <div class="compare-side">
            <span class="compare-label">优化前</span>
            <div class="compare-paper compare-paper--before" aria-label="优化前简历示意">
              <div class="paper-heading"><strong>产品实习生</strong><span>简历</span></div>
              <div class="paper-section"><b>项目经历</b><p>负责需求沟通和原型设计，完成产品功能。</p></div>
              <div class="paper-section"><b>校园经历</b><p>参与社团活动，协助完成日常运营工作。</p></div>
              <div class="paper-note"><span>问题</span> 描述宽泛，缺少结果与岗位关键词</div>
            </div>
          </div>
          <div class="compare-vs">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </div>
          <div class="compare-side">
            <span class="compare-label highlight">优化后</span>
            <div class="compare-paper compare-paper--after" aria-label="优化后简历示意">
              <div class="paper-heading"><strong>产品经理</strong><span>匹配度 92%</span></div>
              <div class="paper-section"><b>校园二手交易平台</b><p>主导 18 场用户访谈，重构发布流程，上线 6 周新增 2,000 名用户。</p></div>
              <div class="paper-section"><b>社团运营项目</b><p>设计分层触达策略，活动到场率从 43% 提升至 71%。</p></div>
              <div class="paper-note"><span>提升</span> 结果量化，能力与岗位要求直接对齐</div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="cta-section">
      <div class="container">
        <div class="cta-banner">
          <div class="cta-banner-bg"></div>
          <h2>准备好让你的简历<span class="cta-highlight">脱颖而出</span>了吗？</h2>
          <p>免费开始，无需下载，3 分钟看到效果</p>
          <button class="cta-btn" @click="focusInput">
            免费开始使用
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
        </div>
      </div>
    </section>

    <footer class="footer">
      <div class="container">
        <div class="footer-grid">
          <div class="footer-brand">
            <span class="footer-logo">识光简历</span>
            <span class="footer-tagline">AI 驱动的智能简历平台</span>
          </div>
          <div class="footer-col">
            <span class="footer-col-title">产品</span>
            <span>简历生成</span><span>简历优化</span><span>求职投递</span>
          </div>
          <div class="footer-col">
            <span class="footer-col-title">支持</span>
            <span>使用帮助</span><span>常见问题</span><span>联系我们</span>
          </div>
          <div class="footer-col">
            <span class="footer-col-title">关于</span>
            <span>关于我们</span><span>隐私政策</span><span>服务条款</span>
          </div>
        </div>
        <div class="footer-bottom">
          <span>&copy; 2026 识光简历 · Glint</span>
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { extractJobName } from '@/utils/jobMatcher'
import HomeIcon from '@/components/home/HomeIcon.vue'
import SpotlightCard from '@/components/effects/SpotlightCard.vue'
import ShinyText from '@/components/effects/ShinyText.vue'
import { quickJobs, steps, features } from '@/content/home'

const router = useRouter()
const store = useChatStore()
const auth = useAuthStore()

const jobInput = ref('')
const inputRef = ref(null)
const stat1 = ref(0)
const stat2 = ref(0)
const stat3 = ref(0)
const stat1Display = computed(() => stat1.value.toLocaleString('en-US'))

const animationIds = new Set()

function animateNum(refVar, target, duration = 1600, isFloat = false) {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    refVar.value = target
    return
  }
  const start = performance.now()
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration)
    const eased = 1 - Math.pow(1 - t, 3)
    refVar.value = isFloat ? +(target * eased).toFixed(1) : Math.round(target * eased)
    if (t < 1) {
      const animationId = requestAnimationFrame(tick)
      animationIds.add(animationId)
    }
  }
  const animationId = requestAnimationFrame(tick)
  animationIds.add(animationId)
}

onMounted(() => {
  animateNum(stat1, 3200)
  animateNum(stat2, 4.9, 1600, true)
  animateNum(stat3, 85)
})

onUnmounted(() => {
  animationIds.forEach(cancelAnimationFrame)
  animationIds.clear()
})

function quickSelect(job) {
  jobInput.value = `我想做${job}`
  nextTick(() => inputRef.value?.focus())
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
  store.reset()
  router.push('/upload')
}
</script>

<style scoped>
/* ==================== 全局 ==================== */
.home {
  position: relative;
  width: 100%;
  background: #F8FAFC;
  isolation: isolate;
}

.home section,
.home .footer {
  position: relative;
  z-index: 1;
}

.home-pattern {
  position: absolute;
  inset: 0 0 auto;
  z-index: 0;
  height: min(760px, 100vh);
  opacity: 0.7;
  pointer-events: none;
  background-image:
    radial-gradient(circle, rgba(79, 70, 229, 0.2) 1px, transparent 1.2px),
    linear-gradient(180deg, rgba(238, 242, 255, 0.72), rgba(248, 250, 252, 0));
  background-size: 18px 18px, 100% 100%;
  mask-image: linear-gradient(to bottom, #000 20%, transparent 94%);
  -webkit-mask-image: linear-gradient(to bottom, #000 20%, transparent 94%);
}

.container {
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 clamp(32px, 5vw, 64px);
}

.text-gradient {
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.section-head {
  text-align: center;
  margin-bottom: 3.5rem;
}

.section-label {
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: #4F46E5;
  background: rgba(79, 70, 229, 0.08);
  padding: 6px 16px;
  border-radius: 999px;
  margin-bottom: 1rem;
}

.section-title {
  font-size: 2.6rem;
  font-weight: 800;
  color: #0F172A;
  letter-spacing: -1.2px;
  line-height: 1.2;
}

/* ==================== 1. Hero ==================== */
.hero {
  position: relative;
  padding: 4rem 0 1.5rem;
  text-align: center;
  overflow: hidden;
  isolation: isolate;
  background: linear-gradient(
    180deg,
    rgba(248, 250, 252, 0.4) 0%,
    rgba(248, 250, 252, 0.58) 100%
  );
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 18px;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 999px;
  font-size: 0.9rem;
  font-weight: 600;
  color: #64748B;
  margin-bottom: 1.5rem;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.badge-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #10B981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.4);
}

.hero-title {
  font-size: 4rem;
  font-weight: 800;
  color: #0F172A;
  letter-spacing: -2px;
  line-height: 1.1;
  margin: 0 0 1rem;
}

.hero-desc {
  font-size: 1.2rem;
  color: #64748B;
  line-height: 1.7;
  max-width: 520px;
  margin: 0 auto 2.5rem;
}

/* Hero 输入区 */
.hero-action {
  max-width: 560px;
  margin: 0 auto 2rem;
}

.hero-input-wrap {
  display: flex;
  align-items: center;
  background: #FFFFFF;
  border: 1.5px solid #E2E8F0;
  border-radius: 16px;
  padding: 5px 5px 5px 18px;
  margin-bottom: 14px;
  transition: all 0.25s;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.hero-input-wrap:focus-within {
  border-color: #4F46E5;
  box-shadow: 0 0 0 4px rgba(79, 70, 229, 0.08), 0 4px 16px rgba(79, 70, 229, 0.08);
}

.hero-input-icon {
  color: #94A3B8;
  flex-shrink: 0;
}

.hero-input {
  flex: 1;
  height: 48px;
  padding: 0 12px;
  font-size: 1.05rem;
  background: transparent;
  border: none;
  outline: none;
  color: #0F172A;
  font-family: inherit;
}

.hero-input::placeholder {
  color: #94A3B8;
}

.hero-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 46px;
  padding: 0 26px;
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
  color: #fff;
  font-weight: 700;
  font-size: 1rem;
  border-radius: 12px;
  white-space: nowrap;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.25s;
  box-shadow: 0 4px 16px rgba(79, 70, 229, 0.25);
}

.hero-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 24px rgba(79, 70, 229, 0.35);
}

.hero-btn:disabled {
  background: #E2E8F0;
  color: #94A3B8;
  box-shadow: none;
  cursor: not-allowed;
}

.hero-tags {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-tag {
  padding: 8px 18px;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 999px;
  color: #64748B;
  font-size: 0.92rem;
  font-family: inherit;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.hero-tag:hover {
  border-color: #4F46E5;
  color: #4F46E5;
  background: rgba(79, 70, 229, 0.04);
}

/* 两种入口卡片 */
.hero-paths {
  display: flex;
  gap: 16px;
  max-width: 700px;
  margin: 0 auto 2.5rem;
}

.hero-path {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
  border-radius: 16px;
  border: none;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.3s;
}

.hero-path:hover {
  transform: translateY(-2px);
}

.hero-path.purple {
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
  color: #fff;
  box-shadow: 0 4px 20px rgba(79, 70, 229, 0.25);
}

.hero-path.purple:hover {
  box-shadow: 0 8px 28px rgba(79, 70, 229, 0.35);
}

.hero-path.white {
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.hero-path.white:hover {
  border-color: #C7D2FE;
  box-shadow: 0 4px 16px rgba(79, 70, 229, 0.06);
}

.hp-icon {
  width: 40px; height: 40px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(255,255,255,0.2);
}

.hero-path.white .hp-icon {
  background: rgba(79, 70, 229, 0.08);
  color: #4F46E5;
}

.hp-text {
  flex: 1;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.hp-text strong {
  font-size: 0.95rem;
  font-weight: 700;
}

.hero-path.white .hp-text strong {
  color: #0F172A;
}

.hp-text span:last-child {
  font-size: 0.8rem;
  opacity: 0.75;
  line-height: 1.4;
}

.hero-path.white .hp-text span:last-child {
  color: #64748B;
  opacity: 1;
}

.hp-badge {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(255,255,255,0.25);
  border-radius: 999px;
  font-size: 0.68rem;
  font-weight: 700;
  width: fit-content;
  margin-bottom: 2px;
}

.hp-arrow {
  flex-shrink: 0;
  opacity: 0.5;
  transition: transform 0.25s;
}

.hero-path:hover .hp-arrow {
  transform: translateX(3px);
}

.hero-path.white .hp-arrow {
  color: #4F46E5;
  opacity: 0.6;
}

/* 统计数据 */
.hero-stats {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
}

.hstat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 0 32px;
}

.hstat-num {
  font-size: 1.8rem;
  font-weight: 800;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, #4F46E5, #7C3AED);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hstat-label {
  font-size: 0.85rem;
  color: #94A3B8;
  font-weight: 500;
}

.hstat-divider {
  width: 1px;
  height: 40px;
  background: #E2E8F0;
}

/* ==================== 2. 三步流程 ==================== */
.steps {
  padding: 1.5rem 0 6rem;
  background: rgba(255, 255, 255, 0.78);
}

.steps-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 32px;
}

.step-card {
  text-align: left;
}

.step-visual {
  position: relative;
  aspect-ratio: 16/10;
  margin-bottom: 1.4rem;
  overflow: hidden;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  background: #FFFFFF;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08);
  transition: transform 0.3s var(--ease-out), box-shadow 0.3s var(--ease-out);
}

.step-card:hover .step-visual {
  transform: translateY(-4px);
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.12);
}

.visual-toolbar {
  display: flex;
  gap: 5px;
  height: 28px;
  padding: 10px 12px;
  background: #F8FAFC;
  border-bottom: 1px solid #E2E8F0;
}

.visual-toolbar i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #CBD5E1;
}

.target-preview,
.message-preview,
.resume-preview {
  height: calc(100% - 28px);
  padding: 20px;
}

.target-preview {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
  background: linear-gradient(135deg, #FFFFFF, #F0FDFA);
}

.preview-label {
  color: #64748B;
  font-size: 0.72rem;
  font-weight: 700;
}

.target-preview strong {
  color: #0F172A;
  font-size: 1.35rem;
}

.preview-tags {
  display: flex;
  gap: 6px;
}

.preview-tags span {
  padding: 4px 8px;
  border-radius: 4px;
  color: #0F766E;
  background: #CCFBF1;
  font-size: 0.68rem;
  font-weight: 700;
}

.message-preview {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 10px;
  background: #F8FAFC;
}

.message-preview span {
  max-width: 86%;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 0.7rem;
  line-height: 1.45;
}

.message-ai {
  color: #334155;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
}

.message-user {
  align-self: flex-end;
  color: #FFFFFF;
  background: #4F46E5;
}

.resume-preview {
  display: grid;
  grid-template-columns: 34px 1fr 46px;
  align-items: start;
  gap: 12px;
  background: linear-gradient(150deg, #FFFFFF 0%, #F8FAFC 100%);
}

.resume-avatar {
  width: 34px;
  height: 34px;
  border-radius: 6px;
  background: #0F172A;
}

.resume-lines {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.resume-lines strong,
.resume-lines span {
  display: block;
  height: 5px;
  border-radius: 3px;
  background: #CBD5E1;
}

.resume-lines strong { width: 64%; height: 8px; background: #475569; }
.resume-lines span:last-child { width: 78%; }

.resume-score {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border: 4px solid #34D399;
  border-radius: 50%;
  color: #047857;
  font-weight: 800;
}

.step-num {
  font-size: 0.78rem;
  font-weight: 800;
  color: #0F766E;
  margin-bottom: 0.5rem;
}

.step-card h4 {
  font-size: 1.2rem;
  font-weight: 700;
  color: #0F172A;
  margin-bottom: 0.4rem;
}

.step-card p {
  font-size: 0.95rem;
  color: #64748B;
  line-height: 1.6;
  max-width: 300px;
}

/* ==================== 3. 核心优势 ==================== */
.features {
  padding: 6rem 0;
  background: rgba(248, 250, 252, 0.7);
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 20px;
}

.feat-card {
  padding: 2rem;
  border-radius: 20px;
  background: #FFFFFF;
  border: 1px solid #F1F5F9;
  transition: all 0.3s;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
}

.feat-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(79, 70, 229, 0.06);
  border-color: #E0E7FF;
}

.feat-card-featured {
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
  color: #fff;
  border: none;
  box-shadow: 0 4px 20px rgba(79, 70, 229, 0.2);
}

.feat-card-featured:hover {
  box-shadow: 0 8px 32px rgba(79, 70, 229, 0.3);
}

.feat-icon-wrap {
  width: 48px; height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: rgba(79, 70, 229, 0.08);
  color: #4F46E5;
  margin-bottom: 1rem;
  transition: transform 0.3s;
}

.feat-icon-wrap svg {
  width: 24px;
  height: 24px;
}

.feat-card:hover .feat-icon-wrap {
  transform: scale(1.1);
}

.feat-card-featured .feat-icon-wrap {
  background: rgba(255,255,255,0.2);
  color: #fff;
}

.feat-card h4 {
  font-size: 1.2rem;
  font-weight: 700;
  color: #0F172A;
  margin-bottom: 0.5rem;
}

.feat-card p {
  font-size: 0.95rem;
  color: #64748B;
  line-height: 1.65;
}

.feat-card.feat-card-featured h4 {
  color: #FFFFFF;
}

.feat-card.feat-card-featured p {
  color: rgba(255, 255, 255, 0.84);
}

/* ==================== 4. 效果对比 ==================== */
.compare {
  padding: 6rem 0;
  background: rgba(255, 255, 255, 0.78);
}

.compare-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
}

.compare-side {
  flex: 1;
  max-width: 360px;
  text-align: center;
}

.compare-label {
  display: inline-block;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: #94A3B8;
  margin-bottom: 1rem;
}

.compare-label.highlight {
  color: #10B981;
}

.compare-paper {
  aspect-ratio: 3/4;
  padding: 34px 30px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  background: #FFFFFF;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.09);
  color: #334155;
  text-align: left;
}

.compare-paper--after {
  border-color: rgba(16, 185, 129, 0.4);
  box-shadow: 0 16px 36px rgba(16, 185, 129, 0.12);
}

.paper-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 18px;
  border-bottom: 2px solid #0F172A;
}

.paper-heading strong {
  color: #0F172A;
  font-size: 1.05rem;
}

.paper-heading span {
  color: #64748B;
  font-size: 0.68rem;
  font-weight: 700;
}

.compare-paper--after .paper-heading span {
  padding: 4px 7px;
  border-radius: 4px;
  color: #047857;
  background: #D1FAE5;
}

.paper-section {
  padding: 18px 0;
  border-bottom: 1px solid #E2E8F0;
}

.paper-section b {
  display: block;
  margin-bottom: 8px;
  color: #334155;
  font-size: 0.78rem;
}

.paper-section p {
  color: #64748B;
  font-size: 0.72rem;
  line-height: 1.7;
}

.paper-note {
  margin-top: 18px;
  padding: 10px;
  border-radius: 6px;
  color: #64748B;
  background: #F8FAFC;
  font-size: 0.68rem;
  line-height: 1.6;
}

.paper-note span {
  margin-right: 4px;
  color: #B45309;
  font-weight: 800;
}

.compare-paper--after .paper-note {
  color: #065F46;
  background: #ECFDF5;
}

.compare-paper--after .paper-note span {
  color: #047857;
}

.compare-vs {
  flex-shrink: 0;
  width: 48px; height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #F1F5F9;
  color: #94A3B8;
}

/* ==================== 5. CTA ==================== */
.cta-section {
  padding: 5rem 0;
  background: rgba(248, 250, 252, 0.72);
}

.cta-banner {
  position: relative;
  text-align: center;
  padding: 4rem 2rem;
  border-radius: 24px;
  background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
  overflow: hidden;
}

.cta-banner-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 20% 30%, rgba(255,255,255,0.1), transparent 50%),
    radial-gradient(circle at 80% 70%, rgba(255,255,255,0.05), transparent 50%);
  pointer-events: none;
}

.cta-banner h2 {
  position: relative;
  font-size: 2.4rem;
  font-weight: 800;
  color: #fff;
  letter-spacing: -1px;
  line-height: 1.3;
  margin-bottom: 0.8rem;
}

.cta-highlight {
  color: #FCD34D;
}

.cta-banner p {
  position: relative;
  font-size: 1.15rem;
  color: rgba(255,255,255,0.75);
  margin-bottom: 2rem;
}

.cta-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 15px 36px;
  background: #FFFFFF;
  color: #4F46E5;
  font-size: 1.15rem;
  font-weight: 700;
  border-radius: 14px;
  border: none;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.25s;
  box-shadow: 0 4px 20px rgba(0,0,0,0.1);
}

.cta-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(0,0,0,0.15);
}

/* ==================== 6. Footer ==================== */
.footer {
  padding: 4rem 0 2rem;
  background: rgba(255, 255, 255, 0.86);
  border-top: 1px solid #F1F5F9;
}

.footer-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: 40px;
  margin-bottom: 2.5rem;
}

.footer-brand {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.footer-logo {
  font-size: 1.3rem;
  font-weight: 800;
  background: linear-gradient(135deg, #4F46E5, #7C3AED);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.footer-tagline {
  font-size: 0.9rem;
  color: #94A3B8;
}

.footer-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.footer-col-title {
  font-size: 0.8rem;
  font-weight: 700;
  color: #0F172A;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 2px;
}

.footer-col span:not(.footer-col-title) {
  font-size: 0.9rem;
  color: #64748B;
  cursor: pointer;
  transition: color 0.2s;
}

.footer-col span:not(.footer-col-title):hover {
  color: #4F46E5;
}

.footer-bottom {
  padding-top: 1.5rem;
  border-top: 1px solid #F1F5F9;
  text-align: center;
  font-size: 0.85rem;
  color: #94A3B8;
}

/* ==================== 响应式 ==================== */
@media (max-width: 1024px) {
  .hero-title { font-size: 3rem; }
  .section-title { font-size: 2rem; }
  .hero-paths { flex-direction: column; }
  .steps-grid { grid-template-columns: 1fr; max-width: 400px; margin: 0 auto; }
  .features-grid { grid-template-columns: 1fr; }
  .compare-row { flex-direction: column; }
  .compare-vs { transform: rotate(90deg); }
  .compare-side { max-width: 100%; width: 100%; }
  .compare-paper { aspect-ratio: auto; min-height: 330px; }
  .footer-grid { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 768px) {
  .hero { padding: 3rem 0 1.5rem; }
  .hero-title { font-size: 2.4rem; letter-spacing: -1px; }
  .hero-desc { font-size: 1.05rem; }
  .hero-input-wrap { flex-direction: column; padding: 10px; gap: 8px; }
  .hero-input { width: 100%; text-align: center; }
  .hero-btn { width: 100%; justify-content: center; }
  .hero-path { min-height: 70px; padding: 12px 16px; }
  .hero-path .hp-text span:last-child { display: none; }
  .hero-stats { display: none; }
  .section-title { font-size: 1.8rem; }
  .cta-banner h2 { font-size: 1.8rem; }
  .footer-grid { grid-template-columns: 1fr; gap: 24px; }
}

@media (max-width: 480px) {
  .hero-title { font-size: 2rem; }
  .hero-paths { max-width: 100%; }
}
</style>
