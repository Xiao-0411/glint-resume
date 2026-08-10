<template>
  <n-modal
    :show="auth.showLogin"
    @update:show="onUpdateShow"
    :mask-closable="true"
    transform-origin="center"
  >
    <div class="login-card">
      <button class="login-close" type="button" @click="close" aria-label="关闭">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>

      <!-- 品牌化头部 -->
      <div class="login-head">
        <div class="login-logo">
          <BrandMark :size="68" label="识光简历" />
        </div>
        <h2 class="login-title">{{ isRegister ? '创建账号' : '欢迎回来' }}</h2>
        <p class="login-sub">{{ isRegister ? '注册后即可保存你的专属简历与投递记录' : '登录后即可生成、保存与投递你的专属简历' }}</p>
      </div>

      <!-- 表单 -->
      <div class="login-form">
        <div class="form-item">
          <label>邮箱</label>
          <div class="input-wrap">
            <svg class="input-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 4h16v16H4z"/><polyline points="22,6 12,13 2,6"/>
            </svg>
            <input v-model="username" class="form-input" type="email" placeholder="请输入邮箱" @keydown.enter="handleLogin" />
          </div>
        </div>

        <div v-if="isRegister" class="form-item">
          <label>邮箱验证码</label>
          <div class="input-wrap code-wrap">
            <svg class="input-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 6 9 17l-5-5"/>
            </svg>
            <input v-model="emailCode" class="form-input" type="text" inputmode="numeric" maxlength="6" placeholder="请输入验证码" @keydown.enter="handleLogin" />
            <button class="code-btn" type="button" :disabled="sendingCode || codeCountdown > 0" @click="handleSendCode">
              {{ codeCountdown > 0 ? `${codeCountdown}s` : (sendingCode ? '发送中' : '发送验证码') }}
            </button>
          </div>
        </div>

        <div v-if="isRegister" class="form-item">
          <label>昵称</label>
          <div class="input-wrap">
            <svg class="input-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
            </svg>
            <input v-model="displayName" class="form-input" type="text" maxlength="32" placeholder="可选" @keydown.enter="handleLogin" />
          </div>
        </div>

        <div class="form-item">
          <label>密码</label>
          <div class="input-wrap">
            <svg class="input-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <input v-model="password" class="form-input" type="password" :placeholder="isRegister ? '至少8位，包含字母和数字' : '请输入密码'" @keydown.enter="handleLogin" />
          </div>
        </div>

        <div v-if="isRegister" class="form-item">
          <label>确认密码</label>
          <div class="input-wrap">
            <svg class="input-icon" width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
            <input v-model="confirmPassword" class="form-input" type="password" placeholder="请再次输入密码" @keydown.enter="handleLogin" />
          </div>
        </div>

        <div v-if="errorMsg" class="form-error">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          {{ errorMsg }}
        </div>

        <div v-if="successMsg" class="form-success">
          {{ successMsg }}
        </div>

        <button class="btn-login" :disabled="loading" @click="handleLogin">
          <span v-if="!loading">{{ isRegister ? '注 册' : '登 录' }}</span>
          <span v-else class="btn-loading"><i class="spin"></i>{{ isRegister ? '注册中...' : '登录中...' }}</span>
        </button>

        <div class="form-footer">
          <template v-if="!isRegister">
            还没有账号？<a href="#" @click.prevent="handleRegister">立即注册</a>
          </template>
          <template v-else>
            已有账号？<a href="#" @click.prevent="handleGoLogin">去登录</a>
          </template>
        </div>
      </div>
    </div>
  </n-modal>
</template>

<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { NModal } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import BrandMark from '@/components/BrandMark.vue'

const auth = useAuthStore()
const username = ref('')
const emailCode = ref('')
const displayName = ref('')
const password = ref('')
const confirmPassword = ref('')
const mode = ref('login')
const loading = ref(false)
const sendingCode = ref(false)
const codeCountdown = ref(0)
const errorMsg = ref('')
const successMsg = ref('')
const isRegister = computed(() => mode.value === 'register')
const passwordPolicyText = '密码至少需要 8 位，并包含字母和数字'
let countdownTimer = null

function resetForm() {
  username.value = ''
  emailCode.value = ''
  displayName.value = ''
  password.value = ''
  confirmPassword.value = ''
  mode.value = 'login'
  errorMsg.value = ''
  successMsg.value = ''
  loading.value = false
  sendingCode.value = false
  clearCountdown()
}

function close() {
  auth.closeLogin()
  resetForm()
}

function onUpdateShow(v) {
  if (!v) close()
}

async function handleLogin() {
  errorMsg.value = ''
  successMsg.value = ''
  if (!username.value.trim() || !password.value.trim()) {
    errorMsg.value = '请输入邮箱和密码'
    return
  }
  if (!isValidEmail(username.value.trim())) {
    errorMsg.value = '请输入有效邮箱'
    return
  }
  if (isRegister.value && !isStrongPassword(password.value.trim())) {
    errorMsg.value = passwordPolicyText
    return
  }
  if (isRegister.value && !emailCode.value.trim()) {
    errorMsg.value = '请输入邮箱验证码'
    return
  }
  if (isRegister.value && password.value.trim() !== confirmPassword.value.trim()) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }

  loading.value = true
  const account = username.value.trim()
  const pwd = password.value.trim()
  try {
    if (isRegister.value) {
      await auth.register({
        account,
        verificationCode: emailCode.value.trim(),
        password: pwd,
        displayName: displayName.value.trim() || account.split('@')[0]
      })
    } else {
      await auth.login({ account, password: pwd })
    }
    resetForm()
  } catch (e) {
    errorMsg.value = e.message || (isRegister.value ? '注册失败，请稍后重试' : '登录失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

function handleRegister() {
  mode.value = 'register'
  errorMsg.value = ''
  successMsg.value = ''
}

function handleGoLogin() {
  mode.value = 'login'
  errorMsg.value = ''
  successMsg.value = ''
}

async function handleSendCode() {
  errorMsg.value = ''
  successMsg.value = ''
  const email = username.value.trim()
  if (!isValidEmail(email)) {
    errorMsg.value = '请输入有效邮箱'
    return
  }

  sendingCode.value = true
  try {
    const resp = await auth.sendEmailCode(email)
    successMsg.value = resp.dev_code
      ? `开发模式验证码：${resp.dev_code}`
      : '验证码已发送，请查收邮箱'
    startCountdown(resp.cooldown_seconds || 60)
  } catch (e) {
    errorMsg.value = e.message || '验证码发送失败，请稍后重试'
  } finally {
    sendingCode.value = false
  }
}

function startCountdown(seconds) {
  clearCountdown()
  codeCountdown.value = seconds
  countdownTimer = setInterval(() => {
    codeCountdown.value -= 1
    if (codeCountdown.value <= 0) clearCountdown()
  }, 1000)
}

function clearCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
  codeCountdown.value = 0
}

function isValidEmail(value) {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)
}

function isStrongPassword(value) {
  return value.length >= 8 && /[A-Za-z]/.test(value) && /\d/.test(value)
}

onUnmounted(clearCountdown)
</script>

<style scoped>
.login-card {
  position: relative;
  width: 640px;
  max-width: 92vw;
  max-height: 86vh;
  overflow-y: auto;
  background: var(--color-bg-card);
  border-radius: var(--radius-2xl);
  padding: 40px 60px 36px;
  box-shadow: var(--shadow-xl);
  border: 1px solid var(--color-border-light);
  animation: scaleIn 0.28s var(--ease-out);
}

.login-card::-webkit-scrollbar {
  width: 6px;
}
.login-card::-webkit-scrollbar-thumb {
  background: rgba(156, 163, 175, 0.38);
  border-radius: 999px;
}

.login-close {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all 0.2s var(--ease-out);
}
.login-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
}

/* 头部 */
.login-head {
  text-align: center;
  margin-bottom: 28px;
}
.login-logo {
  width: 68px;
  height: 68px;
  margin: 0 auto 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-logo svg { width: 68px; height: 68px; }
.login-title {
  font-size: 2.2rem;
  font-weight: 800;
  color: var(--color-text);
  letter-spacing: 0;
  margin-bottom: 8px;
}
.login-sub {
  font-size: 1.15rem;
  color: var(--color-text-muted);
  line-height: 1.5;
}

/* 表单 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.form-item label {
  font-size: 1.12rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}
.input-wrap {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  height: 52px;
  padding: 0 16px;
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-subtle);
  transition: all 0.2s var(--ease-out);
}
.input-wrap:focus-within {
  border-color: var(--color-primary);
  background: var(--color-bg-card);
  box-shadow: var(--shadow-focus);
}
.input-icon {
  color: var(--color-text-muted);
  flex-shrink: 0;
}
.form-input {
  flex: 1;
  width: 100%;
  min-width: 0;
  height: 100%;
  padding: 0;
  border-radius: 0;
  outline: none;
  font-size: 1.18rem;
  color: var(--color-text);
  background: transparent;
  font-family: inherit;
}
.form-input:focus,
.form-input:focus-visible {
  outline: none;
}
.form-input::placeholder {
  color: var(--color-text-muted);
}

.code-wrap {
  padding-right: 10px;
}
.code-btn {
  flex-shrink: 0;
  height: 38px;
  padding: 0 14px;
  border-radius: var(--radius-md);
  background: var(--color-primary);
  color: #fff;
  font-size: 1rem;
  font-weight: 700;
  white-space: nowrap;
  transition: all 0.2s var(--ease-out);
}
.code-btn:hover:not(:disabled) {
  background: var(--color-primary-dark, #1D4ED8);
}
.code-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.form-error {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-danger);
  font-size: 1.05rem;
  font-weight: 500;
  margin-top: -4px;
}

.form-success {
  color: var(--color-success, #059669);
  font-size: 1.05rem;
  font-weight: 600;
  margin-top: -4px;
  line-height: 1.5;
}

.btn-login {
  width: 100%;
  height: 54px;
  margin-top: 6px;
  background: var(--gradient-primary);
  color: #fff;
  border-radius: var(--radius-lg);
  font-size: 1.25rem;
  font-weight: 700;
  letter-spacing: 3px;
  transition: all 0.2s var(--ease-out);
  box-shadow: var(--shadow-primary);
}
.btn-login:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}
.btn-login:active:not(:disabled) {
  transform: translateY(0);
}
.btn-login:disabled {
  opacity: 0.75;
  cursor: not-allowed;
}
.btn-loading {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  letter-spacing: normal;
}
.spin {
  width: 20px;
  height: 20px;
  border: 2.5px solid rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
  border-radius: 50%;
  display: inline-block;
  animation: rotate 0.7s linear infinite;
}

.form-footer {
  text-align: center;
  font-size: 1.08rem;
  color: var(--color-text-muted);
  margin-top: 4px;
}
.form-footer a {
  color: var(--color-primary);
  font-weight: 600;
}
.form-footer a:hover {
  text-decoration: underline;
}

@media (max-width: 640px) {
  .login-card {
    max-height: 90vh;
    padding: 40px 24px 32px;
  }
  .login-title { font-size: 2rem; }
  .login-sub { font-size: 1.08rem; }
}
</style>
