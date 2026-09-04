<template>
  <div class="chat-layout">
    <!-- 顶部：返回 + 目标岗位 + 横向 stepper -->
    <header class="topbar">
      <button class="back-btn" @click="goBack" title="返回首页">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
      </button>
      <div class="topbar-info">
        <span class="topbar-label">目标岗位</span>
        <span class="topbar-title">{{ store.targetJob || '对话中' }}</span>
      </div>

      <ol class="stepper">
        <li
          v-for="(s, idx) in steps"
          :key="s.key"
          :class="['step', stepStatus(idx)]"
        >
          <div class="step-circle">
            <svg v-if="stepStatus(idx) === 'done'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <span v-else>{{ idx + 1 }}</span>
          </div>
          <span class="step-label">{{ s.label }}</span>
          <span v-if="idx < steps.length - 1" class="step-connector"></span>
        </li>
      </ol>
    </header>

    <!-- 主体：左对话 / 右简历 -->
    <div class="main-grid">
      <!-- 左：对话 -->
      <section class="chat-pane">
        <main class="chat-area" ref="chatAreaRef">
          <div class="chat-inner">
            <ChatBubble
              v-for="(msg, idx) in store.messages"
              :key="idx"
              :role="msg.role"
              :text="msg.text"
              :ts="msg.ts"
              :typewriter="false"
              :streaming="!!msg.streaming"
              :quick-replies="idx === store.messages.length - 1 && msg.role === 'ai' && !msg.streaming ? currentQuickReplies : []"
              @typing-done="onTypingDone(idx)"
              @quick="onQuickReply"
            />
            <div v-if="aiThinking" class="thinking">
              <div class="thinking-avatar">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              </div>
              <div class="thinking-dots">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </main>

        <!-- 未登录拦截：信息已齐全，提示登录后生成 -->
        <div v-if="needLogin && !auth.isLoggedIn" class="login-gate">
          <div class="login-gate-text">
            <strong>简历信息已收集完成 🎉</strong>
            <span>登录后即可立即生成并保存你的专属简历</span>
          </div>
          <button class="login-gate-btn" @click="triggerGenerate">登录并生成简历</button>
        </div>

        <footer class="input-footer">
          <div class="input-row" :class="{ disabled: busy }">
            <textarea
              ref="textareaRef"
              v-model="text"
              class="textarea"
              placeholder="说说你的经历..."
              :disabled="busy"
              rows="1"
              @keydown.enter.exact.prevent="onSend"
              @input="autoGrow"
            ></textarea>
            <button
              class="send-btn"
              :disabled="!canSend"
              @click="onSend"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/>
                <polyline points="12 5 19 12 12 19"/>
              </svg>
            </button>
          </div>
          <div class="input-hint"><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行</div>
        </footer>
      </section>

      <!-- 右：实时简历 -->
      <aside class="resume-pane">
        <LiveResumePreview
          :target-job="store.targetJob"
          :completed-sections="completedSections"
          :profile="store.extractedProfile"
        />
      </aside>
    </div>

    <LoadingOverlay
      :visible="generating"
      title="正在生成你的简历"
      subtitle="分析经历，重塑专业描述..."
      :duration="45000"
      @done="onGenerated"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { chatApi, resumeApi, apiMode } from '@/api'
import ChatBubble from '@/components/ChatBubble.vue'
import LoadingOverlay from '@/components/LoadingOverlay.vue'
import LiveResumePreview from '@/components/LiveResumePreview.vue'

const router = useRouter()
const store = useChatStore()
const auth = useAuthStore()

const chatAreaRef = ref(null)
const textareaRef = ref(null)
const text = ref('')
const aiThinking = ref(false)
// Keep the composer locked for the whole SSE lifecycle. Once the first token
// arrives aiThinking is hidden, but the prior request is still in flight.
const streamingActive = ref(false)
const generating = ref(false)
const needLogin = ref(false)
const currentQuickReplies = ref([])
let streamController = null

const steps = [
  { key: 'basic_info', label: '基本信息' },
  { key: 'education', label: '教育背景' },
  { key: 'experience_mining', label: '项目经历' },
  { key: 'skills_awards', label: '技能荣誉' }
]

const busy = computed(() => aiThinking.value || streamingActive.value || generating.value)
const canSend = computed(() => text.value.trim().length > 0 && !busy.value)

const lastAiIdx = computed(() => {
  for (let i = store.messages.length - 1; i >= 0; i--) {
    if (store.messages[i].role === 'ai') return i
  }
  return -1
})

// 只按后端已确认并提交的结构化数据展示；尚无真实数据的 mock 流程仍按
// stage 展示示例排版。
const completedSections = computed(() => {
  const profile = store.extractedProfile || {}
  const skills = profile.skills || {}
  const populated = []
  if (profile.fullname || profile.email || profile.phone || profile.location) populated.push('basic')
  if (Array.isArray(profile.education) && profile.education.length) populated.push('education')
  if (Array.isArray(profile.experiences) && profile.experiences.length) populated.push('experiences')
  if (
    (Array.isArray(skills.technical) && skills.technical.length) ||
    (Array.isArray(skills.tools) && skills.tools.length) ||
    (Array.isArray(skills.product) && skills.product.length) ||
    (Array.isArray(skills.soft) && skills.soft.length)
  ) populated.push('skills')
  if (Array.isArray(profile.awards) && profile.awards.length) populated.push('awards')
  if (populated.length) return populated

  // In real backend mode, an empty snapshot means nothing has been confirmed
  // yet. Do not unlock sample sections merely because the state machine moved
  // stages. Mock mode keeps its illustrative layout for offline demos.
  if (apiMode !== 'mock') return []

  const stage = store.currentStage
  if (stage === 'basic_info') return []
  if (stage === 'education') return ['basic']
  if (stage === 'experience_mining') return ['basic', 'education']
  if (stage === 'awards') return ['basic', 'education', 'experiences']
  if (stage === 'skills') return ['basic', 'education', 'experiences', 'awards']
  if (stage === 'ready_to_generate') return ['basic', 'education', 'experiences', 'skills', 'awards']
  return []
})

function stepStatus(idx) {
  const stage = store.currentStage
  const currentStepIdx = (() => {
    if (stage === 'basic_info') return 0
    if (stage === 'education') return 1
    if (stage === 'experience_mining') return 2
    if (stage === 'awards' || stage === 'skills' || stage === 'ready_to_generate') return 3
    return 0
  })()
  if (idx < currentStepIdx) return 'done'
  if (idx === currentStepIdx) return 'active'
  return 'pending'
}

onMounted(async () => {
  if (!store.targetJob) {
    router.replace('/')
    return
  }
  if (store.messages.length === 0) {
    await sendUserMessage(`我想做${store.targetJob}`)
  }
})

onUnmounted(() => streamController?.abort())

function onSend() {
  if (!canSend.value) return
  const msg = text.value.trim()
  text.value = ''
  nextTick(() => autoGrow())
  sendUserMessage(msg)
}

function onQuickReply(text) {
  sendUserMessage(text)
}

async function sendUserMessage(text) {
  if (busy.value) return

  store.pushMessage('user', text)
  currentQuickReplies.value = []
  aiThinking.value = true
  streamingActive.value = true
  await scrollToBottom()

  let aiIdx = -1
  let firstChunkArrived = false
  streamController?.abort()
  streamController = new AbortController()

  try {
    await chatApi.sendStream(
      {
        sessionId: store.sessionId,
        targetJob: store.targetJob,
        userMessage: text,
        userMsgCount: store.userMessageCount,
        signal: streamController.signal
      },
      {
        onDelta: (chunk) => {
          if (!firstChunkArrived) {
            firstChunkArrived = true
            aiThinking.value = false
            aiIdx = store.pushMessage('ai', '', { streaming: true })
          }
          store.appendToMessage(aiIdx, chunk)
          scrollToBottom()
        },
        onDone: (meta) => {
          streamingActive.value = false
          store.setStage(meta.stage)
          if (meta.extracted) store.setExtracted(meta.extracted)
          currentQuickReplies.value = meta.quickReplies || []

          if (aiIdx === -1) {
            aiThinking.value = false
            aiIdx = store.pushMessage('ai', '(空回复)', { streaming: false })
          } else {
            store.finishStreamingMessage(aiIdx, { quickReplies: meta.quickReplies || [] })
          }

          // fallback 提示：LLM 不可用时明确告知用户
          if (meta.fallback) {
            const reason = meta.fallbackReason || '当前 AI 服务繁忙，展示的是示例内容'
            store.pushMessage('ai', `⚠️ ${reason}`, { isFallbackNotice: true })
          }

          if (meta.stage === 'ready_to_generate') {
            triggerGenerate()
          }
        },
        onError: (err) => {
          streamingActive.value = false
          aiThinking.value = false
          if (aiIdx === -1) {
            store.pushMessage('ai', `抱歉，出了点问题：${err.message || '请稍后重试'}`)
          } else {
            store.finishStreamingMessage(aiIdx)
            store.pushMessage('ai', `刚才的回复未能完整生成：${err.message || '请重新发送上一条内容'}`)
          }
        }
      }
    )
  } catch (error) {
    if (error?.name !== 'AbortError') throw error
  } finally {
    streamingActive.value = false
    aiThinking.value = false
    streamController = null
  }
  await scrollToBottom()
}

function onTypingDone(idx) {
  scrollToBottom()
}

async function triggerGenerate() {
  if (generating.value) {
    return
  }
  // 对话已完成、简历即将生成：未登录则先弹登录，登录成功后自动继续生成
  if (!auth.isLoggedIn) {
    needLogin.value = true
    auth.requireLogin(doGenerate)
    return
  }
  doGenerate()
}

async function doGenerate() {
  needLogin.value = false
  if (generating.value) return
  generating.value = true
  try {
    const result = await resumeApi.generate({
      sessionId: store.sessionId,
      targetJob: store.targetJob
    })
    store.setResume(result.resume, result.qualityReport, result.savedResumeId)
    saveToHistory(result.resume, result.qualityReport, 'chat', result.savedResumeId)

    // fallback 提示：简历生成使用了 mock 数据时告知用户
    if (result.fallback) {
      const reason = result.fallbackReason || '当前 AI 服务繁忙，展示的是示例内容'
      store.pushMessage('ai', `⚠️ ${reason}`, { isFallbackNotice: true })
    }

    generating.value = false
    router.push('/result')
  } catch (e) {
    generating.value = false
    // 422 = 经历不足，后端明确拒绝生成。把原因告诉用户并留在对话里继续补充，
    // 不要笼统报"出了点问题"，否则用户不知道该做什么。
    const status = e?.response?.status
    const detail = e?.response?.data?.detail
    if (status === 422 && detail) {
      store.pushMessage('ai', detail)
    } else {
      store.pushMessage('ai', '生成简历时出了点问题，请稍后重试。')
    }
  }
}

function onGenerated() {}

// 生成成功后存入"我的简历"历史（已登录才会真正写入）
function saveToHistory(resume, report, source, savedResumeId = null) {
  auth.addResumeToHistory({
    savedResumeId,
    sessionId: store.sessionId,
    targetJob: resume?.basic?.target_job || store.targetJob || '未命名简历',
    score: report?.total_score ?? null,
    grade: report?.grade || '',
    gradeColor: report?.grade_color || '',
    source,
    resume,
    qualityReport: report
  })
}

async function scrollToBottom() {
  await nextTick()
  const el = chatAreaRef.value
  if (el) {
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }
}

function autoGrow() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 120) + 'px'
}

function goBack() {
  if (confirm('返回首页将清空当前对话，确定吗？')) {
    store.reset()
    router.push('/')
  }
}

watch(() => store.messages.length, scrollToBottom)
</script>

<style scoped>
.chat-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg);
  overflow: hidden;
  position: relative;
}

/* 全局背景科技光晕 */
.chat-layout::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 10% 10%, rgba(37, 99, 235, 0.06), transparent 45%),
    radial-gradient(circle at 90% 90%, rgba(8, 145, 178, 0.05), transparent 50%);
  z-index: 0;
}

/* ============ 顶部 ============ */
.topbar {
  position: relative;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 14px 28px;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(18px) saturate(180%);
  -webkit-backdrop-filter: blur(18px) saturate(180%);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.back-btn {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--color-border-light);
  transition: all 0.2s var(--ease-out);
  flex-shrink: 0;
}

.back-btn:hover {
  background: var(--color-bg-card);
  color: var(--color-primary);
  border-color: rgba(37, 99, 235, 0.2);
  transform: translateX(-2px);
  box-shadow: var(--shadow-sm);
}

.topbar-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
  margin-right: auto;
}

.topbar-label {
  font-size: 0.72rem;
  color: var(--color-text-muted);
  font-weight: 600;
  letter-spacing: 0.6px;
  text-transform: uppercase;
}

.topbar-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.3px;
  line-height: 1.2;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ============ 横向 Stepper ============ */
.stepper {
  display: flex;
  align-items: center;
  list-style: none;
  gap: 0;
  flex-shrink: 0;
}

.step {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  position: relative;
  transition: all 0.3s var(--ease-out);
}

.step-circle {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 0.85rem;
  font-weight: 700;
  flex-shrink: 0;
  background: var(--color-bg-card);
  color: var(--color-text-muted);
  border: 1.5px solid var(--color-border);
  transition: all 0.25s var(--ease-out);
}

.step.active .step-circle {
  background: var(--gradient-primary);
  color: white;
  border-color: transparent;
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14), 0 2px 6px rgba(37, 99, 235, 0.28);
  animation: pulseStep 2s ease-in-out infinite;
}

@keyframes pulseStep {
  0%, 100% { box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.14), 0 2px 6px rgba(37, 99, 235, 0.28); }
  50% { box-shadow: 0 0 0 7px rgba(37, 99, 235, 0.08), 0 2px 6px rgba(37, 99, 235, 0.28); }
}

.step.done .step-circle {
  background: var(--color-success);
  color: white;
  border-color: var(--color-success);
  box-shadow: 0 2px 4px rgba(5, 150, 105, 0.20);
}

.step.pending .step-circle {
  opacity: 0.6;
}

.step-label {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--color-text);
  letter-spacing: -0.1px;
  white-space: nowrap;
}

.step.pending .step-label {
  color: var(--color-text-muted);
  font-weight: 500;
}

.step.done .step-label {
  color: var(--color-text-secondary);
}

.step-connector {
  display: inline-block;
  width: 40px;
  height: 2px;
  margin: 0 14px;
  background: var(--color-border);
  border-radius: 2px;
  transition: background 0.4s var(--ease-out);
}

.step.done .step-connector {
  background: linear-gradient(90deg, var(--color-success), var(--color-border));
}

/* ============ 主体网格 ============ */
.main-grid {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(420px, 620px);
  min-height: 0;
  position: relative;
  z-index: 1;
}

/* ============ 左侧：对话 ============ */
.chat-pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background:
    radial-gradient(ellipse 80% 50% at 50% 0%, rgba(37, 99, 235, 0.04), transparent 70%);
  border-right: 1px solid var(--color-border-light);
  position: relative;
}

.chat-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 28px 26px 8px;
  min-height: 0;
}

.chat-inner {
  max-width: 720px;
  width: 100%;
  margin: 0 auto;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

/* ============ 思考动画 ============ */
.thinking {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
  animation: fadeInUp 0.3s var(--ease-out);
}

.thinking-avatar {
  width: 38px;
  height: 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-md);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.30), inset 0 1px 0 rgba(255, 255, 255, 0.15);
  flex-shrink: 0;
}

.thinking-dots {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 16px 20px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  border-top-left-radius: var(--radius-xs);
  box-shadow: var(--shadow-sm);
}

.thinking-dots span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-primary);
  opacity: 0.4;
  animation: pulseDot 1.4s infinite both;
}

.thinking-dots span:nth-child(2) { animation-delay: 0.16s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.32s; }

/* ============ 未登录生成拦截条 ============ */
.login-gate {
  flex-shrink: 0;
  max-width: 720px;
  width: calc(100% - 52px);
  margin: 0 auto 4px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 22px;
  background: var(--color-primary-soft);
  border: 1px solid rgba(37, 99, 235, 0.22);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  animation: fadeInUp 0.3s var(--ease-out);
}

.login-gate-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.login-gate-text strong {
  font-size: 1.08rem;
  font-weight: 700;
  color: var(--color-text);
}

.login-gate-text span {
  font-size: 0.92rem;
  color: var(--color-text-secondary);
}

.login-gate-btn {
  flex-shrink: 0;
  padding: 11px 24px;
  background: var(--gradient-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: var(--shadow-primary);
  transition: all 0.2s var(--ease-out);
}

.login-gate-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

/* ============ 底部输入 ============ */
.input-footer {
  padding: 18px 26px 22px;
  background: linear-gradient(180deg, transparent 0%, rgba(249, 250, 251, 0.6) 30%, var(--color-bg) 100%);
  position: relative;
  margin-top: 12px;
  flex-shrink: 0;
}

.input-footer::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 720px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--color-border-light) 20%, var(--color-border-light) 80%, transparent);
  opacity: 0.7;
}

.input-row {
  max-width: 720px;
  margin: 0 auto;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 12px 12px 12px 20px;
  background: var(--color-bg-card);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-xl);
  transition: all 0.25s var(--ease-out);
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.03);
  position: relative;
}

.input-row:hover:not(.disabled) {
  border-color: var(--color-border-strong);
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06), 0 2px 4px rgba(15, 23, 42, 0.04);
}

.input-row:focus-within {
  border-color: rgba(37, 99, 235, 0.4);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.12), 0 2px 6px rgba(37, 99, 235, 0.08);
}

.input-row.disabled {
  opacity: 0.55;
  pointer-events: none;
}

.textarea {
  flex: 1;
  background: transparent;
  color: var(--color-text);
  font-size: 1.15rem;
  line-height: 1.7;
  padding: 12px 0;
  resize: none;
  min-height: 28px;
  max-height: 160px;
  font-family: inherit;
  letter-spacing: -0.1px;
}

.textarea:focus,
.textarea:focus-visible {
  outline: none;
}

.textarea::placeholder {
  color: var(--color-text-muted);
  font-weight: 400;
}

.send-btn {
  width: 44px;
  height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-lg);
  transition: all 0.25s var(--ease-out);
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.30), inset 0 1px 0 rgba(255, 255, 255, 0.15);
}

.send-btn:not(:disabled):hover {
  transform: translateY(-2px) scale(1.02);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.send-btn:not(:disabled):active {
  transform: translateY(0) scale(1);
}

.send-btn:disabled {
  background: var(--color-border);
  color: var(--color-text-muted);
  cursor: not-allowed;
  box-shadow: none;
}

.input-hint {
  max-width: 720px;
  margin: 10px auto 0;
  text-align: center;
  font-size: 0.8rem;
  color: var(--color-text-muted);
  letter-spacing: 0.3px;
}

.input-hint kbd {
  display: inline-block;
  padding: 1px 6px;
  margin: 0 2px;
  font-family: var(--font-mono);
  font-size: 0.74rem;
  color: var(--color-text-secondary);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  box-shadow: 0 1px 0 var(--color-border);
}

/* ============ 右侧：实时简历 ============ */
.resume-pane {
  display: flex;
  flex-direction: column;
  padding: 24px 26px;
  overflow: hidden;
  background:
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(8, 145, 178, 0.05), transparent 70%),
    linear-gradient(180deg, #FAFBFD 0%, #F4F6FA 100%);
  min-width: 0;
  min-height: 0;
}

/* ============ 响应式 ============ */
@media (max-width: 1100px) {
  .step-label {
    display: none;
  }
  .step-connector {
    width: 22px;
    margin: 0 8px;
  }
  .main-grid {
    grid-template-columns: minmax(0, 1fr) minmax(360px, 40vw);
  }
}

@media (max-width: 900px) {
  .main-grid {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 1fr;
  }
  .resume-pane {
    border-top: 1px solid var(--color-border-light);
    padding: 18px 16px;
  }
  .chat-pane {
    border-right: none;
  }
  .topbar {
    padding: 10px 16px;
    gap: 12px;
  }
  .chat-area {
    padding: 16px 12px 8px;
  }
  .input-footer {
    padding: 12px 12px 16px;
  }
  .textarea {
    font-size: 1.02rem;
  }
}
</style>
