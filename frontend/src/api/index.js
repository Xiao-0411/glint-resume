/**
 * 后端 API 封装入口
 *
 * 通过 .env 中 VITE_USE_BACKEND 切换:
 *  - 'true'  → 调用真实后端(端口 8000),对话走 SSE 流式
 *  - 否则     → 走 mock.js (前端独立演示)
 */
import { mockChatReply, mockGenerateResume, mockEvaluateResumeText, mockReevaluateResume } from './mock'
import {
  sendChatStream,
  generateResume,
  evaluateText,
  reevaluateResume,
  loginAccount,
  sendEmailCode,
  registerAccount,
  getCurrentUser,
  attachSession,
  getLatestSession,
  listResumes,
  deleteResume,
  listAdminUsers,
  updateAdminUser,
  deleteAdminUser
} from './backend'

const USE_BACKEND = import.meta.env.VITE_USE_BACKEND === 'true'

// ============ 对话 ============

export const chatApi = {
  /**
   * 非流式调用(mock 用) —— 兼容旧接口
   */
  send: (payload) => mockChatReply(payload),

  /**
   * 流式调用(真实后端用)
   * payload: { sessionId, targetJob, userMessage, userMsgCount }
   * handlers: { onDelta(text), onDone(meta), onError(err) }
   *
   * mock 模式下也会"模拟流式":将完整回复按字符切块通过 onDelta 推送
   */
  sendStream: async (payload, handlers = {}) => {
    if (USE_BACKEND) {
      return sendChatStream(payload, handlers)
    }
    // mock 模拟流式
    try {
      const resp = await mockChatReply(payload)
      const text = resp.reply
      const chunkSize = 4
      for (let i = 0; i < text.length; i += chunkSize) {
        handlers.onDelta?.(text.slice(i, i + chunkSize))
        await new Promise(r => setTimeout(r, 25))
      }
      handlers.onDone?.({
        stage: resp.stage,
        stageLabel: resp.stageLabel,
        quickReplies: resp.quickReplies || [],
        fallback: false
      })
    } catch (e) {
      handlers.onError?.(e)
    }
  }
}

// ============ 简历 ============

export const resumeApi = {
  generate: (payload) => USE_BACKEND
    ? generateResume(payload)
    : mockGenerateResume(payload),

  evaluateText: (payload) => USE_BACKEND
    ? evaluateText(payload)
    : mockEvaluateResumeText(payload),

  // 用户编辑简历后重评:传当前简历对象,保留 exp_id
  reevaluate: (payload) => USE_BACKEND
    ? reevaluateResume(payload)
    : mockReevaluateResume(payload),

  listHistory: (limit = 30) => USE_BACKEND
    ? listResumes(limit)
    : Promise.resolve([]),

  deleteHistory: (resumeId) => USE_BACKEND
    ? deleteResume(resumeId)
    : Promise.resolve({ ok: true })
}

// ============ 账号 ============

export const authApi = {
  login: loginAccount,
  sendEmailCode,
  register: registerAccount,
  me: getCurrentUser
}

// ============ 会话 ============

export const sessionApi = {
  attach: attachSession,
  latest: getLatestSession
}

// ============ 权限 / 账号管理 ============

export const adminApi = {
  listUsers: listAdminUsers,
  updateUser: updateAdminUser,
  deleteUser: deleteAdminUser
}

// 暴露当前模式(供 UI 显示)
export const apiMode = USE_BACKEND ? 'backend' : 'mock'
