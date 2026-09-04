/**
 * 真实后端 API 调用（HTTP + 完整 JSON，前端本地模拟播放）
 * 通过 VITE_API_BASE_URL 指向后端。
 * 生产架构:前端在 Cloudflare Pages(纯静态,无 /api 反代),后端经本机
 * Cloudflare Tunnel 暴露为 api.sgjl.cloud —— 所以生产不能用同源相对路径。
 */
import axios from 'axios'

const DEFAULT_BASE_URL = import.meta.env.DEV
  ? 'http://127.0.0.1:8000'
  : 'https://api.sgjl.cloud'
// 不能用 ||：万一显式配了空串会被当假值吞掉,悄悄退回默认值,不易排查。
const rawBaseUrl = import.meta.env.VITE_API_BASE_URL
const BASE_URL = rawBaseUrl === undefined ? DEFAULT_BASE_URL : rawBaseUrl

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' }
})

function getAuthToken() {
  return localStorage.getItem('auth_token') || ''
}

function withAuthHeaders(headers = {}) {
  const token = getAuthToken()
  return token ? { ...headers, Authorization: `Bearer ${token}` } : headers
}

http.interceptors.request.use((config) => {
  const token = getAuthToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export async function loginAccount(payload) {
  const { data } = await http.post('/api/auth/login', {
    account: payload.account,
    password: payload.password
  })
  return data
}

export async function sendEmailCode(payload) {
  const { data } = await http.post('/api/auth/email-code/send', {
    email: payload.email
  })
  return data
}

export async function registerAccount(payload) {
  const { data } = await http.post('/api/auth/register', {
    account: payload.account,
    verification_code: payload.verificationCode,
    password: payload.password,
    display_name: payload.displayName || ''
  })
  return data
}

export async function getCurrentUser() {
  const { data } = await http.get('/api/auth/me')
  return data
}

/**
 * 个人中心 —— 更新昵称 / 头像
 */
export async function updateProfile(payload) {
  const body = {}
  // 只提交真正要改的字段：后端把 null 当作"不改"
  if (payload.displayName !== undefined) body.display_name = payload.displayName
  if (payload.avatar !== undefined) body.avatar = payload.avatar
  const { data } = await http.patch('/api/profile', body)
  return data
}

/**
 * 上传头像图片，返回更新后的用户对象
 */
export async function uploadAvatar(file) {
  const form = new FormData()
  form.append('file', file)
  // 显式清掉默认的 application/json，让浏览器自己带 multipart boundary
  const { data } = await http.post('/api/profile/avatar', form, {
    headers: { 'Content-Type': undefined }
  })
  return data
}

export async function changePassword(payload) {
  const { data } = await http.post('/api/profile/password', {
    current_password: payload.currentPassword,
    new_password: payload.newPassword
  })
  return data
}

export async function getProfileStats() {
  const { data } = await http.get('/api/profile/stats')
  return data
}

/**
 * 头像相对路径 → 可直接放进 img src 的绝对地址
 */
export function resolveAssetUrl(path) {
  if (!path) return ''
  if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return path
  // 去掉 baseURL 末尾的 /，否则拼出 //uploads/... 匹配不到后端挂载点
  const base = BASE_URL.replace(/\/+$/, '')
  return `${base}${path.startsWith('/') ? path : `/${path}`}`
}

export async function attachSession(payload) {
  const { data } = await http.post('/api/sessions/attach', {
    session_id: payload.sessionId,
    target_job: payload.targetJob || ''
  })
  return data
}

export async function getLatestSession() {
  const { data } = await http.get('/api/sessions/latest')
  return data
}

/**
 * 对话请求：后端返回完整 JSON，前端在此函数中模拟流式播放
 * @param {Object} payload - { sessionId, targetJob, userMessage, userMsgCount }
 * @param {Object} handlers - { onDelta(text), onDone(meta), onError(err) }
 */
export async function sendChatStream(payload, handlers = {}) {
  const url = `${BASE_URL}/api/chat`
  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: withAuthHeaders({ 'Content-Type': 'application/json' }),
      signal: payload.signal,
      body: JSON.stringify({
        session_id: payload.sessionId,
        target_job: payload.targetJob || '',
        user_message: payload.userMessage,
        user_msg_count: payload.userMsgCount
      })
    })
  } catch (e) {
    if (e?.name === 'AbortError') throw e
    handlers.onError?.(new Error('无法连接到后端,请确认后端服务已启动'))
    return
  }

  if (!response.ok) {
    let detail = ''
    try {
      const body = await response.json()
      detail = body?.detail || body?.message || ''
    } catch {
      // Keep the status-only error when the server did not return JSON.
    }
    handlers.onError?.(new Error(detail || `后端返回 ${response.status}`))
    return
  }

  try {
    // The backend returns one validated JSON envelope. Simulate chunks only
    // after the complete reply has arrived, so no partial text can be shown.
    const data = await response.json()
    if (data?.complete !== true || typeof data.reply !== 'string' || !data.reply.trim()) {
      throw new Error('后端返回的对话格式不完整')
    }
    const reply = data.reply.trim()
    const chunkSize = 4
    for (let i = 0; i < reply.length; i += chunkSize) {
      if (payload.signal?.aborted) {
        const abortError = new Error('请求已取消')
        abortError.name = 'AbortError'
        throw abortError
      }
      handlers.onDelta?.(reply.slice(i, i + chunkSize))
      await new Promise((resolve, reject) => {
        const signal = payload.signal
        let timer
        const onAbort = () => {
          if (timer) clearTimeout(timer)
          const abortError = new Error('请求已取消')
          abortError.name = 'AbortError'
          reject(abortError)
        }
        if (signal?.aborted) {
          onAbort()
          return
        }
        if (signal) signal.addEventListener('abort', onAbort, { once: true })
        timer = setTimeout(() => {
          signal?.removeEventListener('abort', onAbort)
          resolve()
        }, 24)
      })
    }
    handlers.onDone?.({
      stage: data.stage,
      stageLabel: data.stage_label,
      quickReplies: data.quick_replies || [],
      fallback: !!data.fallback,
      fallbackReason: data.fallback_reason || '',
      extracted: data.extracted || null
    })
  } catch (e) {
    if (e?.name === 'AbortError') throw e
    handlers.onError?.(e)
  }
}

/**
 * 生成简历 + 质量报告
 */
export async function generateResume(payload) {
  // 生成涉及多次 LLM 调用,给更长超时(后端已并行重写经历,通常更快)
  const { data } = await http.post('/api/resume/generate', {
    session_id: payload.sessionId,
    target_job: payload.targetJob || ''
  }, { timeout: 240000 })
  return {
    resume: data.resume,
    qualityReport: data.quality_report,
    savedResumeId: data.saved_resume_id || null,
    fallback: !!data.fallback,
    fallbackReason: data.fallback_reason || ''
  }
}

/**
 * PDF 解析文本 → 简历 + 报告
 */
export async function evaluateText(payload) {
  const { data } = await http.post('/api/resume/evaluate-text', {
    text: payload.text,
    file_name: payload.fileName || 'uploaded.pdf',
    session_id: payload.sessionId,
    target_job: payload.targetJob || ''
  }, { timeout: 240000 })
  return {
    resume: data.resume,
    qualityReport: data.quality_report,
    savedResumeId: data.saved_resume_id || null
  }
}

/**
 * 对已有简历对象直接重评(用户编辑后),保留 exp_id
 */
export async function reevaluateResume(payload) {
  const { data } = await http.post('/api/resume/evaluate', {
    resume: payload.resume,
    target_job: payload.targetJob || '',
    session_id: payload.sessionId
  }, { timeout: 240000 })
  return {
    qualityReport: data.quality_report,
    savedResumeId: data.saved_resume_id || null
  }
}

export async function listResumes(limit = 30) {
  const { data } = await http.get('/api/resumes', { params: { limit } })
  return data.resumes || []
}

export async function deleteResume(resumeId) {
  const { data } = await http.delete(`/api/resumes/${resumeId}`)
  return data
}

/**
 * 导出简历为 PDF（服务端生成 A4 PDF 并下载）
 * @param {number|string} resumeId - 简历 ID
 */
export function downloadResumePdf(resumeId) {
  const url = `${BASE_URL}/api/resume/pdf?resume_id=${resumeId}`
  // 通过 fetch + blob 方式下载（需要带 Authorization header）
  fetch(url, { headers: withAuthHeaders({}) })
    .then(resp => {
      if (!resp.ok) throw new Error(`导出失败 (${resp.status})`)
      return resp.blob()
    })
    .then(blob => {
      const blobUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = blobUrl
      a.download = ''
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(blobUrl)
    })
    .catch(err => {
      alert('PDF 导出失败：' + (err.message || '请稍后重试'))
    })
}

/**
 * 健康检查 —— 启动时判断后端是否在线
 */
/**
 * 职位搜索
 */
export async function jobSearch(payload) {
  const { data } = await http.post('/api/jobs/search', {
    keyword: payload.keyword || '',
    target_job: payload.targetJob || '',
    provinces: payload.provinces || [],
    locations: payload.locations || [],
    educations: payload.educations || []
  }, { timeout: 240000 })
  return data
}

export async function getCrawlerStatus() {
  const { data } = await http.get('/api/jobs/crawler-status')
  return data
}

export async function getJobLocations() {
  const { data } = await http.get('/api/jobs/locations')
  return data
}

export async function getJobDetail(jobId) {
  const numericId = String(jobId || '').replace(/^job_db_/, '')
  const { data } = await http.get(`/api/jobs/detail/${encodeURIComponent(numericId)}`, { timeout: 60000 })
  return data
}

/**
 * 简历适配
 */
export async function adaptResume(payload) {
  const { data } = await http.post('/api/jobs/adapt', {
    job_id: payload.jobId,
    target_job: payload.targetJob || ''
  })
  return data
}

/**
 * 一键投递
 */
export async function applyJob(payload) {
  const { data } = await http.post('/api/jobs/apply', {
    job_id: payload.jobId,
    resume_version: payload.resumeVersion || 'original'
  })
  return data
}

/**
 * 获取投递列表 + 统计
 */
export async function getApplications() {
  const { data } = await http.get('/api/jobs/applications')
  return data
}

/**
 * 更新投递状态
 */
export async function updateApplicationStatus(payload) {
  const { data } = await http.post('/api/jobs/applications/status', {
    application_id: payload.applicationId,
    status: payload.status
  })
  return data
}

export async function listAdminUsers(payload = {}) {
  const { data } = await http.get('/api/admin/users', {
    params: {
      role: payload.role || '',
      keyword: payload.keyword || '',
      limit: payload.limit || 100,
      offset: payload.offset || 0
    }
  })
  return data
}

export async function updateAdminUser(userId, payload) {
  const { data } = await http.patch(`/api/admin/users/${userId}`, {
    display_name: payload.displayName,
    role: payload.role,
    is_active: payload.isActive
  })
  return data.user
}

export async function deleteAdminUser(userId) {
  const { data } = await http.delete(`/api/admin/users/${userId}`)
  return data
}

export async function checkHealth() {
  try {
    const { data } = await http.get('/api/health', { timeout: 3000 })
    return data
  } catch {
    return null
  }
}
