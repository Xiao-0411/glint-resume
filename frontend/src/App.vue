<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-shell">
        <top-nav />
        <main class="app-main">
          <router-view v-slot="{ Component, route }">
            <transition :name="route.meta.transition || 'fade'" mode="out-in">
              <component :is="Component" :key="route.path" />
            </transition>
          </router-view>
        </main>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { watch } from 'vue'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import TopNav from '@/components/TopNav.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { sessionApi } from '@/api'

const themeOverrides = {
  common: {
    primaryColor: '#2563EB',
    primaryColorHover: '#3B82F6',
    primaryColorPressed: '#1D4ED8',
    primaryColorSuppl: '#2563EB',
    borderRadius: '10px',
    fontFamily: '"PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif'
  }
}

/* ============ 登录后本地保存 / 恢复"当前进度" ============ */
const auth = useAuthStore()
const chat = useChatStore()

const progressKey = () => `resume_progress_${auth.userKey}`

function saveProgress() {
  if (!auth.isLoggedIn) return
  try {
    localStorage.setItem(progressKey(), JSON.stringify({
      sessionId: chat.sessionId,
      targetJob: chat.targetJob,
      currentStage: chat.currentStage,
      messages: chat.messages,
      extractedProfile: chat.extractedProfile,
      resumeData: chat.resumeData,
      qualityReport: chat.qualityReport
    }))
  } catch (e) { /* localStorage 不可用时静默 */ }
}

function hasActiveChatState() {
  return !!chat.targetJob || chat.messages.length > 0 || !!chat.resumeData || !!chat.qualityReport
}

function restoreLocalProgress() {
  if (!auth.isLoggedIn) return
  try {
    const raw = localStorage.getItem(progressKey())
    if (!raw) return false
    chat.hydrate(JSON.parse(raw))
    return true
  } catch (e) { /* 快照损坏时忽略 */ }
  return false
}

async function attachCurrentSession() {
  if (!auth.isLoggedIn || !chat.sessionId || !hasActiveChatState()) return
  try {
    await sessionApi.attach({
      sessionId: chat.sessionId,
      targetJob: chat.targetJob
    })
  } catch (e) { /* 绑定失败不打断当前交互 */ }
}

function snapshotFromBackend(data) {
  const session = data?.session
  const latestResume = data?.latest_resume
  if (!session && !latestResume) return null

  const messages = Array.isArray(session?.messages)
    ? session.messages.map((m, idx) => ({
        role: m.role === 'assistant' ? 'ai' : m.role,
        text: m.content || '',
        ts: Date.now() + idx,
        streaming: false
      }))
    : []

  return {
    sessionId: session?.session_id || latestResume?.session_id || '',
    targetJob: session?.target_job || latestResume?.target_job || '',
    currentStage: session?.stage || 'basic_info',
    messages,
    extractedProfile: session?.extracted || {},
    resumeData: latestResume?.resume || null,
    qualityReport: latestResume?.quality_report || null
  }
}

async function restoreRemoteProgress() {
  if (!auth.isLoggedIn) return false
  try {
    const data = await sessionApi.latest()
    const snap = snapshotFromBackend(data)
    if (!snap) return false
    chat.hydrate(snap)
    return true
  } catch (e) { /* 后端不可用时仍可用本地快照 */ }
  return false
}

function restoreProgress() {
  const restoredLocal = restoreLocalProgress()
  if (!restoredLocal) restoreRemoteProgress()
}

// 开局即恢复（在子路由组件挂载前同步执行，避免 /result 误判为空而跳回首页）
restoreProgress()

// 通过导航栏直接登录（非"被拦截操作"触发）时，恢复该用户上次的进度
watch(() => auth.isLoggedIn, async (now, prev) => {
  if (!now || prev) return
  await attachCurrentSession()
  if (!auth.lastLoginViaGate && !hasActiveChatState()) {
    const restoredLocal = restoreLocalProgress()
    if (!restoredLocal) await restoreRemoteProgress()
  }
})

// 进度变化时防抖写入本地
let saveTimer = null
chat.$subscribe(() => {
  if (!auth.isLoggedIn) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(saveProgress, 400)
})
</script>

<style>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.app-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.45s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.slide-enter-active,
.slide-leave-active {
  transition: all 0.55s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.slide-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.slide-leave-to {
  opacity: 0;
  transform: translateX(-40px);
}
</style>
