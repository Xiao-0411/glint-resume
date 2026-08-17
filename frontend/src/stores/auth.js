import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiMode, authApi, profileApi, resumeApi } from '@/api'

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
    } catch (e) {
      // 只有后端明确说"你没登录/没权限"才登出。
      // 网络抖动、后端重启期间的 502 不该把用户踢下线。
      const code = e?.response?.status
      if (code === 401 || code === 403) logout()
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
      avatar: raw?.avatar || '',
      createdAt: raw?.created_at || raw?.createdAt || ''
    }
  }

  /** 个人中心改完资料后统一回写本地缓存 */
  function applyUpdatedUser(raw) {
    user.value = normalizeUser(raw)
    localStorage.setItem('auth_user', JSON.stringify(user.value))
    return user.value
  }

  async function updateProfile(payload) {
    try {
      return applyUpdatedUser(await profileApi.update(payload))
    } catch (e) {
      throw new Error(toAuthErrorMessage(e, '资料更新失败，请稍后重试'))
    }
  }

  async function uploadAvatar(file) {
    try {
      return applyUpdatedUser(await profileApi.uploadAvatar(file))
    } catch (e) {
      throw new Error(toAuthErrorMessage(e, '头像上传失败，请稍后重试'))
    }
  }

  async function changePassword(payload) {
    try {
      return await profileApi.changePassword(payload)
    } catch (e) {
      throw new Error(toAuthErrorMessage(e, '密码修改失败，请稍后重试'))
    }
  }

  function toAuthErrorMessage(error, fallback) {
    const detail = error?.response?.data?.detail
    if (Array.isArray(detail)) {
      return detail[0]?.msg || fallback
    }
    if (detail) return detail
    // 没有 response = 请求压根没到后端(服务未启动/跨域被拒/域名不通)。
    // 此时 error.message 是 axios 的英文原文 "Network Error"，对用户毫无意义。
    if (!error?.response) {
      return '无法连接到服务器，请检查网络或确认后端服务已启动'
    }
    return error?.message || fallback
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
    updateProfile,
    uploadAvatar,
    changePassword,
    logout,
    addResumeToHistory,
    removeResumeFromHistory
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
