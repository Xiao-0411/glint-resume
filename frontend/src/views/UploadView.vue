<template>
  <div class="upload-view">
    <!-- 顶部 -->
    <header class="topbar">
      <button class="back-btn" @click="goHome">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        <span>返回首页</span>
      </button>
      <span class="brand-name"><BrandMark :size="26" label="识光简历" /><strong>识光</strong><span>简历</span></span>
    </header>

    <!-- 主体 -->
    <main class="main">
      <div class="hero-text">
        <h1 class="hero-title">
          上传你的<span class="gradient-text">简历</span>
        </h1>
        <p class="hero-sub">
          上传 PDF 简历，AI 自动解析内容并生成五维质量评估报告
        </p>
      </div>

      <!-- 拖拽 / 点击上传区 -->
      <section
        v-if="!parsed"
        class="dropzone"
        :class="{ dragover: isDragging, error: errMsg }"
        @click="onClickPick"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDrop"
      >
        <input
          ref="fileInputRef"
          type="file"
          accept="application/pdf,.pdf"
          class="hidden-input"
          @change="onFileChange"
        />

        <div v-if="!parsing" class="dropzone-inner">
          <div class="dz-icon">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
          </div>
          <h3 class="dz-title">拖拽 PDF 到这里 或 <span class="link">点击选择文件</span></h3>
          <p class="dz-tips">
            仅支持 PDF 格式 · 单文件最大 10 MB · 全程本地解析，不上传服务器
          </p>
          <p v-if="!auth.isLoggedIn" class="login-required-tip">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            登录后即可上传并解析简历
          </p>
          <div v-if="errMsg" class="err-msg">{{ errMsg }}</div>
        </div>

        <div v-else class="dz-parsing">
          <div class="parse-ring">
            <svg viewBox="0 0 60 60" class="parse-ring-svg">
              <circle cx="30" cy="30" r="26" class="parse-ring-bg" />
              <circle
                cx="30"
                cy="30"
                r="26"
                class="parse-ring-fg"
                :style="{ strokeDashoffset: 163.36 * (1 - parseProgress) }"
              />
            </svg>
            <span class="parse-percent">{{ Math.round(parseProgress * 100) }}<i>%</i></span>
          </div>
          <p class="parse-text">正在解析简历内容</p>
        </div>
      </section>

      <!-- 解析结果预览 -->
      <section v-else class="parsed-card">
        <div class="parsed-head">
          <div class="file-info">
            <div class="file-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div class="file-meta">
              <div class="file-name">{{ fileInfo.name }}</div>
              <div class="file-detail">
                <span>{{ formatFileSize(fileInfo.size) }}</span>
                <span class="dot">·</span>
                <span>{{ parsed.numPages }} 页</span>
                <span class="dot">·</span>
                <span>{{ parsed.text.length }} 字符</span>
              </div>
            </div>
          </div>
          <button class="ghost-btn" @click="reset">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="3 6 5 6 21 6"/>
              <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
            </svg>
            <span>重新上传</span>
          </button>
        </div>

        <div class="text-preview">
          <div class="preview-label">解析出的文本</div>
          <pre class="preview-text">{{ truncatedText }}</pre>
          <div v-if="parsed.text.length > 1200" class="preview-more">
            仅显示前 1200 字，共 {{ parsed.text.length }} 字符
          </div>
        </div>

        <div class="actions">
          <button class="btn-primary" @click="startEvaluate">
            <span>开始 AI 评估</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/>
              <polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
          <p class="action-tip">点击后将基于解析内容生成简历重塑版本与质量评估报告</p>
        </div>
      </section>
    </main>

    <LoadingOverlay
      :visible="evaluating"
      title="AI 正在评估你的简历"
      subtitle="深度分析五维质量指标..."
      :duration="45000"
      @done="onEvaluated"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import BrandMark from '@/components/BrandMark.vue'
import { resumeApi } from '@/api'
import { parsePdf, formatFileSize } from '@/utils/pdfParser'
import LoadingOverlay from '@/components/LoadingOverlay.vue'

const router = useRouter()
const store = useChatStore()
const auth = useAuthStore()

const fileInputRef = ref(null)
const isDragging = ref(false)
const parsing = ref(false)
const parseProgress = ref(0)
const errMsg = ref('')
const parsed = ref(null)
const fileInfo = ref({ name: '', size: 0 })
const evaluating = ref(false)

const truncatedText = computed(() => {
  if (!parsed.value) return ''
  const t = parsed.value.text
  return t.length > 1200 ? t.slice(0, 1200) + ' ...' : t
})

function onClickPick() {
  if (parsing.value) return
  errMsg.value = ''
  // 触发上传动作即要求登录，未登录不弹出文件选择框；登录后自动继续
  auth.requireLogin(() => fileInputRef.value?.click())
}

function onFileChange(e) {
  const f = e.target.files?.[0]
  if (f) handleFile(f)
}

function onDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer.files?.[0]
  if (!f) return
  // 触发上传动作即要求登录，登录后自动继续解析
  auth.requireLogin(() => handleFile(f))
}

async function handleFile(file) {
  errMsg.value = ''
  if (file.size > 10 * 1024 * 1024) {
    errMsg.value = '文件大小超过 10 MB 限制'
    return
  }
  fileInfo.value = { name: file.name, size: file.size }
  parsing.value = true
  parseProgress.value = 0
  try {
    const result = await parsePdf(file, p => { parseProgress.value = p })
    if (!result.text || result.text.length < 30) {
      errMsg.value = '解析后内容过少，可能是扫描版 PDF。请尝试其他文件或使用对话模式。'
      parsing.value = false
      return
    }
    parsed.value = result
    parsing.value = false
  } catch (e) {
    errMsg.value = e.message || '解析失败，请确认是有效的 PDF 文件'
    parsing.value = false
  }
}

function reset() {
  parsed.value = null
  fileInfo.value = { name: '', size: 0 }
  errMsg.value = ''
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function startEvaluate() {
  if (!parsed.value) return
  // 直接访问 /upload 的兜底：未登录先登录，登录后自动继续评估
  auth.requireLogin(doEvaluate)
}

async function doEvaluate() {
  evaluating.value = true
  try {
    const { resume, qualityReport, savedResumeId } = await resumeApi.evaluateText({
      text: parsed.value.text,
      fileName: fileInfo.value.name,
      sessionId: store.sessionId,
      targetJob: store.targetJob
    })
    const targetJob = resume?.basic?.target_job || store.targetJob || fileInfo.value.name || '上传简历'
    store.setTargetJob(targetJob)
    store.setResume(resume, qualityReport, savedResumeId)
    auth.addResumeToHistory({
      savedResumeId,
      sessionId: store.sessionId,
      targetJob,
      score: qualityReport?.total_score ?? null,
      grade: qualityReport?.grade || '',
      gradeColor: qualityReport?.grade_color || '',
      source: 'upload',
      resume,
      qualityReport
    })
    // 数据到手才跳转,不能依赖进度条动画结束(真实耗时远超动画时长)
    evaluating.value = false
    router.push('/result')
  } catch (e) {
    evaluating.value = false
    errMsg.value = '评估失败，请重试'
  }
}

function onEvaluated() {}

function goHome() {
  router.push('/')
}
</script>

<style scoped>
.upload-view {
  min-height: 100%;
  background:
    radial-gradient(ellipse 80% 50% at 50% 0%, rgba(37, 99, 235, 0.05), transparent 70%),
    var(--color-bg);
  display: flex;
  flex-direction: column;
}

/* 顶部 */
.topbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 28px;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(14px) saturate(180%);
  -webkit-backdrop-filter: blur(14px) saturate(180%);
  border-bottom: 1px solid var(--color-border-light);
  position: sticky;
  top: 0;
  z-index: 10;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  transition: all 0.2s var(--ease-out);
}

.back-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
  transform: translateX(-1px);
}

.brand-name {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: 0;
}
.brand-name strong {
  font-weight: 800;
}
.brand-name > span {
  color: var(--color-text-muted);
  font-size: 0.9em;
}

/* Hero 文本 */
.main {
  flex: 1;
  max-width: 720px;
  margin: 0 auto;
  width: 100%;
  padding: 48px 24px 80px;
  animation: fadeInUp 0.6s var(--ease-out);
}

.hero-text {
  text-align: center;
  margin-bottom: 40px;
}

.hero-title {
  font-size: 3rem;
  font-weight: 800;
  margin-bottom: 12px;
  letter-spacing: -1px;
  color: var(--color-text);
  line-height: 1.2;
}

.hero-sub {
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  line-height: 1.65;
}

/* 拖拽区 */
.dropzone {
  width: 100%;
  background: var(--color-bg-card);
  border: 2px dashed var(--color-border);
  border-radius: var(--radius-xl);
  padding: 56px 40px;
  text-align: center;
  cursor: pointer;
  transition: all 0.3s var(--ease-out);
  min-height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.dropzone::before {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.06), transparent 60%);
  opacity: 0;
  transition: opacity 0.3s var(--ease-out);
  pointer-events: none;
}

.dropzone:hover {
  border-color: var(--color-primary);
  background: var(--color-bg-card);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.dropzone:hover::before {
  opacity: 1;
}

.dropzone.dragover {
  border-color: var(--color-primary);
  border-style: solid;
  background: var(--color-primary-soft);
  transform: scale(1.01);
  box-shadow: var(--shadow-focus), var(--shadow-md);
}

.dropzone.dragover::before {
  opacity: 1;
}

.dropzone.error {
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}

.dropzone-inner {
  width: 100%;
  position: relative;
  z-index: 1;
}

.dz-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  border-radius: var(--radius-lg);
  background: var(--gradient-primary);
  color: white;
  margin-bottom: 20px;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.25);
  transition: transform 0.35s var(--ease-out);
}

.dropzone:hover .dz-icon {
  transform: translateY(-3px) scale(1.04);
}

.dz-title {
  font-size: 1.45rem;
  font-weight: 600;
  color: var(--color-text);
  margin-bottom: 10px;
  letter-spacing: -0.2px;
}

.dz-title .link {
  color: var(--color-primary);
  font-weight: 700;
}

.dz-tips {
  font-size: 1.05rem;
  color: var(--color-text-muted);
  line-height: 1.7;
}

.err-msg {
  margin-top: 14px;
  padding: 9px 16px;
  background: var(--color-danger-soft);
  border: 1px solid rgba(220, 38, 38, 0.25);
  color: var(--color-danger);
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 500;
  display: inline-block;
}

.login-required-tip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-top: 16px;
  padding: 8px 16px;
  background: var(--color-primary-soft);
  border: 1px solid rgba(37, 99, 235, 0.2);
  color: var(--color-primary);
  border-radius: var(--radius-pill);
  font-size: 0.98rem;
  font-weight: 600;
}

.hidden-input { display: none; }

/* 解析中：圆环进度 */
.dz-parsing {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  color: var(--color-text-secondary);
  font-size: 1.15rem;
}

.parse-ring {
  position: relative;
  width: 80px;
  height: 80px;
}

.parse-ring-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.parse-ring-bg {
  fill: none;
  stroke: var(--color-border-light);
  stroke-width: 4;
}

.parse-ring-fg {
  fill: none;
  stroke: var(--color-primary);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 163.36;
  stroke-dashoffset: 163.36;
  transition: stroke-dashoffset 0.2s var(--ease-out);
  filter: drop-shadow(0 0 4px rgba(37, 99, 235, 0.4));
}

.parse-percent {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.7rem;
  font-weight: 800;
  color: var(--color-primary);
  letter-spacing: -0.5px;
}

.parse-percent i {
  font-style: normal;
  font-size: 0.9rem;
  font-weight: 700;
  margin-left: 1px;
  color: var(--color-text-muted);
}

.parse-text {
  font-weight: 500;
}

/* 解析结果卡片 */
.parsed-card {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: 28px;
  box-shadow: var(--shadow-md);
  animation: fadeInUp 0.5s var(--ease-out);
}

.parsed-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--color-border-light);
}

.file-info {
  display: inline-flex;
  align-items: center;
  gap: 14px;
}

.file-icon {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.file-name {
  font-weight: 700;
  font-size: 1.2rem;
  color: var(--color-text);
  margin-bottom: 4px;
  word-break: break-all;
  letter-spacing: -0.2px;
}

.file-detail {
  font-size: 0.95rem;
  color: var(--color-text-muted);
}

.dot {
  margin: 0 6px;
  opacity: 0.4;
}

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 500;
  transition: all 0.2s var(--ease-out);
  flex-shrink: 0;
}

.ghost-btn:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

/* 文本预览 */
.text-preview {
  background: var(--color-bg);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: 18px;
  margin-bottom: 22px;
}

.preview-label {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--color-text-muted);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
}

.preview-text {
  font-family: var(--font-sans);
  font-size: 1.05rem;
  color: var(--color-text-secondary);
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
}

.preview-more {
  margin-top: 10px;
  text-align: center;
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

/* 行动按钮 */
.actions {
  text-align: center;
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-lg);
  font-size: 1.25rem;
  font-weight: 600;
  transition: all 0.25s var(--ease-out);
  box-shadow: var(--shadow-primary);
}

.btn-primary:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-primary-strong);
}

.btn-primary:active {
  transform: translateY(0);
}

.action-tip {
  margin-top: 12px;
  font-size: 0.9rem;
  color: var(--color-text-muted);
}

/* 响应式 */
@media (max-width: 768px) {
  .topbar {
    padding: 12px 16px;
  }
  .main {
    padding: 28px 16px 48px;
  }
  .hero-title {
    font-size: 2.4rem;
  }
  .dropzone {
    padding: 40px 20px;
  }
  .parsed-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
