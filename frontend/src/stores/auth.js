import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiMode, authApi, resumeApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const token = ref(localStorage.getItem('auth_token') || '')

  // ---- 登录弹窗全局控制 ----
  const showLogin = ref(false)
  // 未登录时被拦截的待执行操作（登录成功后自动继续）
  let pendingAction = null
  // 标记本次登录是否用于"继续被拦截的操作"（用于避免与"恢复旧进度"冲突）
  const lastLoginViaGate = ref(false)

  // ---- 我的简历历史（按用户存 localStorage） ----
  const resumeHistory = ref([])

  const isLoggedIn = computed(() => !!user.value && !!token.value)
  const userKey = computed(() => (user.value ? (user.value.id || user.value.email || user.value.name || 'guest') : ''))
  const isSuperAdmin = computed(() => user.value?.role === 'super_admin')
  const isAdmin = computed(() => ['admin', 'super_admin'].includes(user.value?.role))

  function openLogin() {
    showLogin.value = true
  }

  function closeLogin() {
    showLogin.value = false
    pendingAction = null
  }

  /**
   * 需要登录才能继续的动作：
   *  - 已登录 → 直接执行
   *  - 未登录 → 弹出登录框，登录成功后自动执行
   */
  function requireLogin(action) {
    if (isLoggedIn.value) {
      action?.()
      return
    }
    pendingAction = typeof action === 'function' ? action : null
    showLogin.value = true
  }

  async function login(credentials) {
    try {
      const authData = await authApi.login({
        account: credentials.account,
        password: credentials.password
      })
      applyAuthSession(authData)
      return user.value
    } catch (e) {
      throw new Error(toAuthErrorMessage(e, '登录失败，请稍后重试'))
    }
  }

  async function register(credentials) {
    try {
      const authData = await authApi.register({
        account: credentials.account,
        verificationCode: credentials.verificationCode,
        password: credentials.password,
        displayName: credentials.displayName || ''
      })
      applyAuthSession(authData)
      return user.value
    } catch (e) {
      throw new Error(toAuthErrorMessage(e, '注册失败，请稍后重试'))
    }
  }

  async function sendEmailCode(email) {
    try {
      return await authApi.sendEmailCode({ email })
    } catch (e) {
      throw new Error(toAuthErrorMessage(e, '验证码发送失败，请稍后重试'))
    }
  }

  async function refreshCurrentUser() {
    if (!token.value) return null
    try {
      const currentUser = await authApi.me()
      user.value = normalizeUser(currentUser)
      localStorage.setItem('auth_user', JSON.stringify(user.value))
      await loadHistory()
      return user.value
    } catch {
      logout()
      return null
    }
  }

  function applyAuthSession(authData) {
    user.value = normalizeUser(authData.user)
    token.value = authData.token
    localStorage.setItem('auth_token', token.value)
    localStorage.setItem('auth_user', JSON.stringify(user.value))
    loadHistory()
    showLogin.value = false
    // 执行登录前被拦截的操作
    const action = pendingAction
    pendingAction = null
    lastLoginViaGate.value = !!action
    if (action) action()
  }

  function normalizeUser(raw) {
    return {
      id: raw?.id || '',
      email: raw?.email || '',
      name: raw?.name || raw?.email || '用户',
      role: raw?.role || 'user',
      isActive: raw?.is_active ?? raw?.isActive ?? true,
      avatar: raw?.avatar || ''
    }
  }

  function toAuthErrorMessage(error, fallback) {
    const detail = error?.response?.data?.detail
    if (Array.isArray(detail)) {
      return detail[0]?.msg || fallback
    }
    return detail || error?.message || fallback
  }

  function logout() {
    user.value = null
    token.value = ''
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    resumeHistory.value = []
    lastLoginViaGate.value = false
  }

  // ---- 简历历史读写 ----
  function historyStorageKey() {
    return `resume_history_${userKey.value}`
  }

  async function loadHistory() {
    if (!userKey.value) {
      resumeHistory.value = []
      return
    }
    loadLocalHistory()
    await refreshResumeHistory()
  }

  function loadLocalHistory() {
    try {
      resumeHistory.value = JSON.parse(localStorage.getItem(historyStorageKey()) || '[]')
    } catch {
      resumeHistory.value = []
    }
  }

  async function refreshResumeHistory() {
    if (!isLoggedIn.value || apiMode !== 'backend') return
    try {
      const rows = await resumeApi.listHistory(30)
      resumeHistory.value = rows.map(normalizeHistoryItem).filter(item => item.resume)
      persistHistory()
    } catch {
      // 后端不可用时保留刚才恢复出的本地历史
    }
  }

  function persistHistory() {
    if (!userKey.value) return
    localStorage.setItem(historyStorageKey(), JSON.stringify(resumeHistory.value))
  }

  /**
   * 生成一份简历后存入历史
   * record: { targetJob, score, grade, gradeColor, source, resume, qualityReport }
   */
  function addResumeToHistory(record) {
    if (!isLoggedIn.value || !record) return
    const id = record.savedResumeId
      ? String(record.savedResumeId)
      : 'r_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
    const entry = {
      id,
      createdAt: Date.now(),
      ...record
    }
    const existingIdx = resumeHistory.value.findIndex(item => String(item.id) === id)
    if (existingIdx >= 0) {
      resumeHistory.value[existingIdx] = { ...resumeHistory.value[existingIdx], ...entry }
    } else {
      resumeHistory.value.unshift(entry)
    }
    // 最多保留 30 条
    if (resumeHistory.value.length > 30) {
      resumeHistory.value = resumeHistory.value.slice(0, 30)
    }
    persistHistory()
    refreshResumeHistory()
    return entry
  }

  async function removeResumeFromHistory(id) {
    const resumeId = String(id)
    resumeHistory.value = resumeHistory.value.filter(r => String(r.id) !== resumeId)
    persistHistory()
    if (apiMode === 'backend' && /^\d+$/.test(resumeId)) {
      try {
        await resumeApi.deleteHistory(resumeId)
      } catch {
        await refreshResumeHistory()
      }
    }
  }

  function clearHistory() {
    resumeHistory.value = []
    persistHistory()
  }

  // ---- 初始化：恢复登录状态 + 历史 ----
  const savedUser = localStorage.getItem('auth_user')
  if (savedUser) {
    try {
      user.value = normalizeUser(JSON.parse(savedUser))
      if (!user.value.id) {
        user.value = null
        token.value = ''
        localStorage.removeItem('auth_token')
        localStorage.removeItem('auth_user')
      }
    } catch {
      user.value = null
    }
  }
  if (user.value && token.value) {
    loadHistory()
  }

  return {
    // state
    user,
    token,
    showLogin,
    resumeHistory,
    lastLoginViaGate,
    // getters
    isLoggedIn,
    userKey,
    isAdmin,
    isSuperAdmin,
    // actions
    openLogin,
    closeLogin,
    requireLogin,
    login,
    sendEmailCode,
    register,
    refreshCurrentUser,
    logout,
    loadHistory,
    addResumeToHistory,
    removeResumeFromHistory,
    clearHistory
  }
})

function normalizeHistoryItem(item) {
  const report = item.quality_report || item.qualityReport || {}
  const createdAt = parseCreatedAt(item.created_at || item.createdAt)
  return {
    id: String(item.id || item.savedResumeId || `r_${createdAt}`),
    sessionId: item.session_id || item.sessionId || '',
    createdAt,
    targetJob: item.target_job || item.targetJob || item.resume?.basic?.target_job || '未命名简历',
    score: item.total_score ?? item.score ?? report.total_score ?? null,
    grade: item.grade || report.grade || '',
    gradeColor: item.gradeColor || report.grade_color || '',
    source: item.source || 'chat',
    resume: item.resume || null,
    qualityReport: item.quality_report || item.qualityReport || null
  }
}

function parseCreatedAt(value) {
  if (typeof value === 'number') return value
  const parsed = Date.parse(value || '')
  return Number.isNaN(parsed) ? Date.now() : parsed
}
