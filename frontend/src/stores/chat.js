import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 对话与简历数据全局状态
 */
export const useChatStore = defineStore('chat', () => {
  // ---- 会话基础信息 ----
  const sessionId = ref(generateSessionId())
  const targetJob = ref('')   // 用户岗位意向

  // ---- 对话状态 ----
  const messages = ref([])    // { role: 'user' | 'ai', text, ts, typing?: boolean }
  const currentStage = ref('basic_info')
  //   basic_info → education → experience_mining → awards → skills → ready_to_generate

  // ---- 用户 profile（增量提取） ----
  const userProfile = ref({
    fullname: '',
    target_job: '',
    email: '',
    phone: '',
    education: [],
    experiences: [],
    skills: []
  })

  // ---- 后端实时下发的结构化抽取快照（驱动对话页右侧"实时预览"渲染真实内容） ----
  const extractedProfile = ref({})

  // ---- 结果数据 ----
  const resumeData = ref(null)
  const qualityReport = ref(null)
  const currentResumeId = ref(null)      // 当前简历的数据库 ID（用于 PDF 导出等）
  const resumeDirty = ref(false)        // 用户编辑后未重新评定
  const reEvaluating = ref(false)       // 正在重新评定中

  // ---- Getters ----
  const messageCount = computed(() => messages.value.length)
  const userMessageCount = computed(
    () => messages.value.filter(m => m.role === 'user').length
  )

  // ---- Actions ----
  function setTargetJob(job) {
    targetJob.value = job
    userProfile.value.target_job = job
  }

  function setSessionId(id) {
    if (typeof id === 'string' && id.trim()) {
      sessionId.value = id
    }
  }

  function pushMessage(role, text, extra = {}) {
    messages.value.push({
      role,
      text,
      ts: Date.now(),
      ...extra
    })
    return messages.value.length - 1   // 返回索引,便于后续追加
  }

  function appendToMessage(idx, chunk) {
    const m = messages.value[idx]
    if (m) m.text += chunk
  }

  function finishStreamingMessage(idx, patch = {}) {
    const m = messages.value[idx]
    if (m) {
      m.streaming = false
      Object.assign(m, patch)
    }
  }

  function setStage(stage) {
    currentStage.value = stage
  }

  function setExtracted(data) {
    // 后端每轮下发的是累积快照,直接整体替换即可（mock 模式不会调用,保持为空 → 预览回落到样例）
    if (data && typeof data === 'object') {
      extractedProfile.value = data
    }
  }

  function setResume(resume, report, resumeId = null) {
    resumeData.value = resume
    qualityReport.value = report
    currentResumeId.value = resumeId
    resumeDirty.value = false
  }

  /**
   * 用户编辑某段经历后,更新简历并标记为脏
   * patch: { title?, role?, period?, bullets? }
   */
  function updateExperience(expId, patch) {
    if (!resumeData.value?.experiences) return
    const list = resumeData.value.experiences
    const idx = list.findIndex(e => e.id === expId)
    if (idx === -1) return
    list[idx] = { ...list[idx], ...patch }
    // 标记为用户编辑过(便于UI识别)
    if (list[idx].tag) {
      list[idx].tag = { label: '用户已修改', level: 'medium', color: 'yellow' }
    }
    resumeDirty.value = true
  }

  function setResumeDirty(val) {
    resumeDirty.value = !!val
  }

  function setReEvaluating(val) {
    reEvaluating.value = !!val
  }

  function applyNewQualityReport(report, resumeId = null) {
    qualityReport.value = report
    if (resumeId != null) currentResumeId.value = resumeId
    resumeDirty.value = false
  }

  function reset() {
    sessionId.value = generateSessionId()
    targetJob.value = ''
    messages.value = []
    currentStage.value = 'basic_info'
    userProfile.value = {
      fullname: '',
      target_job: '',
      email: '',
      phone: '',
      education: [],
      experiences: [],
      skills: []
    }
    extractedProfile.value = {}
    resumeData.value = null
    qualityReport.value = null
    currentResumeId.value = null
    resumeDirty.value = false
    reEvaluating.value = false
  }

  /**
   * 从本地快照恢复"当前进度"（登录后自动调用）
   * snap: { targetJob, currentStage, messages, resumeData, qualityReport }
   */
  function hydrate(snap) {
    if (!snap || typeof snap !== 'object') return
    setSessionId(snap.sessionId || snap.session_id || '')
    if (typeof snap.targetJob === 'string') targetJob.value = snap.targetJob
    if (snap.currentStage) currentStage.value = snap.currentStage
    if (Array.isArray(snap.messages)) {
      // 去掉残留的流式标记，避免恢复出"正在输入"的气泡
      messages.value = snap.messages.map(m => ({ ...m, streaming: false }))
    }
    if (snap.resumeData) resumeData.value = snap.resumeData
    if (snap.qualityReport) qualityReport.value = snap.qualityReport
    if (snap.extractedProfile) extractedProfile.value = snap.extractedProfile
    resumeDirty.value = false
    reEvaluating.value = false
  }

  return {
    // state
    sessionId,
    targetJob,
    messages,
    currentStage,
    userProfile,
    extractedProfile,
    resumeData,
    qualityReport,
    currentResumeId,
    resumeDirty,
    reEvaluating,
    // getters
    messageCount,
    userMessageCount,
    // actions
    setTargetJob,
    setSessionId,
    pushMessage,
    appendToMessage,
    finishStreamingMessage,
    setStage,
    setExtracted,
    setResume,
    updateExperience,
    setResumeDirty,
    setReEvaluating,
    applyNewQualityReport,
    reset,
    hydrate
  }
})

function generateSessionId() {
  return 'sess_' + Date.now().toString(36) + '_' + crypto.randomUUID().replace(/-/g, '').slice(0, 12)
}
