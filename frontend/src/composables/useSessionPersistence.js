import { onUnmounted, watch } from 'vue'
import { sessionApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'

const SAVE_DELAY_MS = 400

export function useSessionPersistence() {
  const auth = useAuthStore()
  const chat = useChatStore()
  let saveTimer = null

  const progressKey = () => `resume_progress_${auth.userKey}`

  function hasActiveChatState() {
    return Boolean(chat.targetJob || chat.messages.length || chat.resumeData || chat.qualityReport)
  }

  function saveProgress() {
    if (!auth.isLoggedIn || !auth.userKey) return
    try {
      localStorage.setItem(progressKey(), JSON.stringify({
        sessionId: chat.sessionId,
        targetJob: chat.targetJob,
        currentStage: chat.currentStage,
        messages: chat.messages,
        userProfile: chat.userProfile,
        extractedProfile: chat.extractedProfile,
        resumeData: chat.resumeData,
        qualityReport: chat.qualityReport,
        currentResumeId: chat.currentResumeId
      }))
    } catch {
      // 浏览器禁用本地存储时仍允许继续使用当前会话。
    }
  }

  function restoreLocalProgress() {
    if (!auth.isLoggedIn || !auth.userKey) return false
    try {
      const raw = localStorage.getItem(progressKey())
      if (!raw) return false
      chat.hydrate(JSON.parse(raw))
      return true
    } catch {
      return false
    }
  }

  async function attachCurrentSession() {
    if (!auth.isLoggedIn || !chat.sessionId || !hasActiveChatState()) return
    try {
      await sessionApi.attach({ sessionId: chat.sessionId, targetJob: chat.targetJob })
    } catch {
      // 远端绑定失败不影响当前本地会话。
    }
  }

  async function restoreRemoteProgress() {
    if (!auth.isLoggedIn) return false
    try {
      const snapshot = snapshotFromBackend(await sessionApi.latest())
      if (!snapshot) return false
      chat.hydrate(snapshot)
      return true
    } catch {
      return false
    }
  }

  function restoreProgress() {
    if (!restoreLocalProgress()) void restoreRemoteProgress()
  }

  restoreProgress()

  const stopAuthWatch = watch(() => auth.isLoggedIn, async (isLoggedIn, wasLoggedIn) => {
    if (!isLoggedIn || wasLoggedIn) return
    await attachCurrentSession()
    if (!auth.lastLoginViaGate && !hasActiveChatState() && !restoreLocalProgress()) {
      await restoreRemoteProgress()
    }
  })

  const stopStoreSubscription = chat.$subscribe(() => {
    if (!auth.isLoggedIn) return
    clearTimeout(saveTimer)
    saveTimer = setTimeout(saveProgress, SAVE_DELAY_MS)
  })

  onUnmounted(() => {
    clearTimeout(saveTimer)
    stopAuthWatch()
    stopStoreSubscription()
  })
}

function snapshotFromBackend(data) {
  const session = data?.session
  const latestResume = data?.latest_resume
  if (!session && !latestResume) return null

  const messages = Array.isArray(session?.messages)
    ? session.messages.map((message, index) => ({
        role: message.role === 'assistant' ? 'ai' : message.role,
        text: message.content || '',
        ts: Date.now() + index,
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
    qualityReport: latestResume?.quality_report || null,
    currentResumeId: latestResume?.id || null
  }
}
