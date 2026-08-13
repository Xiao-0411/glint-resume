/**
 * 真实后端 API 调用（HTTP + SSE 流式）
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
const BASE_URL = (rawBaseUrl === undefined || rawBaseUrl === '')
  ? DEFAULT_BASE_URL
  : rawBaseUrl

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
 * 解析 SSE 事件流（fetch 版本,因为我们要 POST + 流读取）
 * 返回异步迭代器,每次 yield { event, data }
 *
 * 兼容处理:
 *  - sse-starlette 默认使用 \r\n\r\n 作为事件分隔
 *  - 其他实现使用 \n\n
 *  - 部分代理用 \r\r
 *  统一把所有行尾归一为 \n,然后按 \n\n 拆事件
 */
async function* parseSSEStream(response) {
  if (!response.body) throw new Error('响应没有 body 流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    // 增量解码并归一化行尾
    let chunk = decoder.decode(value, { stream: true })
    chunk = chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    buffer += chunk

    let sepIdx
    while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sepIdx)
      buffer = buffer.slice(sepIdx + 2)

      let eventName = 'message'
      let dataLines = []
      for (const line of rawEvent.split('\n')) {
        if (!line || line.startsWith(':')) continue   // 跳过注释/keep-alive
        if (line.startsWith('event:')) eventName = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      const dataStr = dataLines.join('\n')
      if (dataStr) {
        try {
          yield { event: eventName, data: JSON.parse(dataStr) }
        } catch {
          yield { event: eventName, data: dataStr }
        }
      }
    }
  }

  // 流结束时若还有残余事件,补处理一次
  if (buffer.trim()) {
    let eventName = 'message'
    let dataLines = []
    for (const line of buffer.split('\n')) {
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    const dataStr = dataLines.join('\n')
    if (dataStr) {
      try {
        yield { event: eventName, data: JSON.parse(dataStr) }
      } catch {
        yield { event: eventName, data: dataStr }
      }
    }
  }
}

/**
 * 流式对话
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
    handlers.onError?.(new Error(`后端返回 ${response.status}`))
    return
  }

  try {
    for await (const evt of parseSSEStream(response)) {
      if (evt.event === 'delta' && evt.data?.text) {
        handlers.onDelta?.(evt.data.text)
      } else if (evt.event === 'done') {
        handlers.onDone?.({
          stage: evt.data.stage,
          stageLabel: evt.data.stage_label,
          quickReplies: evt.data.quick_replies || [],
          fallback: !!evt.data.fallback,
          fallbackReason: evt.data.fallback_reason || '',
          extracted: evt.data.extracted || null
        })
        return
      } else if (evt.event === 'error') {
        handlers.onError?.(new Error(evt.data?.message || '流式错误'))
        return
      }
    }
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
    target_job: payload.targetJob || ''
  })
  return data
}

export async function getCrawlerStatus() {
  const { data } = await http.get('/api/jobs/crawler-status')
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
