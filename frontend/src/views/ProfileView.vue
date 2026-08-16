<template>
  <div class="profile">
    <header class="profile-head">
      <h1>个人中心</h1>
      <p>管理你的账号资料，回顾简历与投递进展</p>
    </header>

    <!-- 账号卡片 -->
    <section class="account-card">
      <div class="avatar-block">
        <div class="avatar-wrap">
          <img v-if="avatarUrl" :src="avatarUrl" class="avatar-img" alt="头像" />
          <span v-else class="avatar-fallback">{{ initial }}</span>
          <button class="avatar-edit" type="button" :disabled="avatarUploading" @click="pickAvatar">
            {{ avatarUploading ? '上传中' : '更换' }}
          </button>
        </div>
        <input
          ref="avatarInput"
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          class="avatar-input"
          @change="handleAvatarChange"
        />
        <p class="avatar-hint">支持 JPG / PNG / GIF / WebP，不超过 2MB</p>
      </div>

      <div class="account-info">
        <div class="account-name-row">
          <template v-if="editingName">
            <input
              v-model="nameDraft"
              class="name-input"
              maxlength="32"
              placeholder="输入昵称"
              @keydown.enter="saveName"
              @keydown.esc="cancelName"
            />
            <button class="mini-btn primary" :disabled="savingName" @click="saveName">
              {{ savingName ? '保存中' : '保存' }}
            </button>
            <button class="mini-btn" @click="cancelName">取消</button>
          </template>
          <template v-else>
            <h2>{{ auth.user?.name || '未命名用户' }}</h2>
            <button class="mini-btn" @click="startEditName">编辑昵称</button>
          </template>
        </div>

        <dl class="account-meta">
          <div>
            <dt>邮箱</dt>
            <dd>{{ auth.user?.email || '—' }}</dd>
          </div>
          <div>
            <dt>角色</dt>
            <dd><span class="role-badge" :class="auth.user?.role">{{ roleLabel }}</span></dd>
          </div>
          <div>
            <dt>注册时间</dt>
            <dd>{{ formatDate(auth.user?.createdAt) || '—' }}</dd>
          </div>
        </dl>
      </div>
    </section>

    <!-- 数据概览 -->
    <section class="stat-grid">
      <article v-for="card in statCards" :key="card.label" class="stat-card">
        <span class="stat-value">{{ card.value }}</span>
        <span class="stat-label">{{ card.label }}</span>
      </article>
    </section>

    <div class="panel-grid">
      <!-- 我的简历 -->
      <section class="panel">
        <div class="panel-head">
          <h3>我的简历</h3>
          <router-link to="/chat" class="panel-link">去创建</router-link>
        </div>
        <p v-if="!auth.resumeHistory.length" class="panel-empty">还没有生成过简历</p>
        <ul v-else class="resume-list">
          <li v-for="item in recentResumes" :key="item.id" class="resume-item" @click="openResume(item)">
            <span class="resume-score" :style="{ color: item.gradeColor || scoreColor(item.score) }">
              {{ item.score ?? '--' }}
            </span>
            <span class="resume-main">
              <strong>{{ item.targetJob || '未命名简历' }}</strong>
              <small>{{ formatDate(item.createdAt) }}</small>
            </span>
            <span class="resume-open">打开</span>
          </li>
        </ul>
      </section>

      <!-- 投递记录 -->
      <section class="panel">
        <div class="panel-head">
          <h3>最近投递</h3>
          <router-link to="/dashboard" class="panel-link">全部投递</router-link>
        </div>
        <p v-if="applicationsLoading" class="panel-empty">加载中...</p>
        <p v-else-if="!recentApplications.length" class="panel-empty">还没有投递记录</p>
        <ul v-else class="apply-list">
          <li v-for="item in recentApplications" :key="item.id" class="apply-item">
            <span class="apply-main">
              <strong>{{ item.jobTitle || '未知职位' }}</strong>
              <small>{{ item.company || '—' }}</small>
            </span>
            <span class="apply-side">
              <span class="apply-status" :class="item.status">{{ item.statusLabel || item.status }}</span>
              <small>{{ formatDate(item.appliedAt) }}</small>
            </span>
          </li>
        </ul>
      </section>
    </div>

    <!-- 账号安全 -->
    <section class="panel security">
      <div class="panel-head">
        <h3>账号安全</h3>
        <button v-if="!showPasswordForm" class="mini-btn" @click="showPasswordForm = true">修改密码</button>
      </div>
      <p v-if="!showPasswordForm" class="panel-empty left">定期更换密码可以更好地保护账号安全</p>
      <form v-else class="password-form" @submit.prevent="submitPassword">
        <input v-model="passwordForm.current" type="password" placeholder="当前密码" autocomplete="current-password" />
        <input v-model="passwordForm.next" type="password" placeholder="新密码（至少 8 位，含大小写字母和数字）" autocomplete="new-password" />
        <input v-model="passwordForm.confirm" type="password" placeholder="确认新密码" autocomplete="new-password" />
        <div class="password-actions">
          <button class="mini-btn primary" type="submit" :disabled="savingPassword">
            {{ savingPassword ? '提交中' : '确认修改' }}
          </button>
          <button class="mini-btn" type="button" @click="cancelPassword">取消</button>
        </div>
      </form>
    </section>

    <p v-if="errorMsg" class="feedback error">{{ errorMsg }}</p>
    <p v-else-if="successMsg" class="feedback success">{{ successMsg }}</p>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { profileApi, resolveAssetUrl } from '@/api'
import { jobHuntApi } from '@/api/jobHunt'

const router = useRouter()
const auth = useAuthStore()
const chat = useChatStore()

const stats = ref(null)
const applications = ref([])
const applicationsLoading = ref(false)

const editingName = ref(false)
const nameDraft = ref('')
const savingName = ref(false)

const avatarInput = ref(null)
const avatarUploading = ref(false)

const showPasswordForm = ref(false)
const savingPassword = ref(false)
const passwordForm = reactive({ current: '', next: '', confirm: '' })

const errorMsg = ref('')
const successMsg = ref('')

const avatarUrl = computed(() => resolveAssetUrl(auth.user?.avatar))
const initial = computed(() => auth.user?.name?.charAt(0)?.toUpperCase() || 'U')
const recentResumes = computed(() => auth.resumeHistory.slice(0, 5))
const recentApplications = computed(() => applications.value.slice(0, 5))

const roleLabel = computed(() => {
  if (auth.user?.role === 'super_admin') return '超级管理员'
  if (auth.user?.role === 'admin') return '管理员'
  return '普通用户'
})

// 统计接口不可用时（mock 模式）退回本地历史，卡片不留空
const statCards = computed(() => {
  const localCount = auth.resumeHistory.length
  const localScores = auth.resumeHistory.map(r => r.score).filter(s => typeof s === 'number')
  const localBest = localScores.length ? Math.max(...localScores) : null
  return [
    { label: '生成简历', value: stats.value?.resume_count ?? localCount },
    { label: '最高分', value: stats.value?.best_score ?? localBest ?? '--' },
    { label: '平均分', value: stats.value?.average_score ?? '--' },
    { label: '投递职位', value: stats.value?.application_count ?? applications.value.length },
    { label: '进入面试', value: stats.value?.interview_count ?? '--' }
  ]
})

onMounted(async () => {
  if (!auth.isLoggedIn) {
    auth.openLogin()
    router.replace('/')
    return
  }
  auth.refreshCurrentUser()
  loadStats()
  loadApplications()
})

async function loadStats() {
  try {
    stats.value = await profileApi.stats()
  } catch {
    // 概览失败不该挡住整页，卡片会退回本地历史统计
  }
}

async function loadApplications() {
  applicationsLoading.value = true
  try {
    const data = await jobHuntApi.getApplications()
    applications.value = data.applications || []
  } catch {
    applications.value = []
  } finally {
    applicationsLoading.value = false
  }
}

function startEditName() {
  nameDraft.value = auth.user?.name || ''
  editingName.value = true
  clearFeedback()
}

function cancelName() {
  editingName.value = false
  nameDraft.value = ''
}

async function saveName() {
  const name = nameDraft.value.trim()
  if (!name) {
    showError('昵称不能为空')
    return
  }
  if (name === auth.user?.name) {
    cancelName()
    return
  }
  savingName.value = true
  clearFeedback()
  try {
    await auth.updateProfile({ displayName: name })
    editingName.value = false
    showSuccess('昵称已更新')
  } catch (e) {
    showError(e.message)
  } finally {
    savingName.value = false
  }
}

function pickAvatar() {
  avatarInput.value?.click()
}

async function handleAvatarChange(event) {
  const file = event.target.files?.[0]
  // 选完就清空 value，否则连选同一张图不会再触发 change
  event.target.value = ''
  if (!file) return
  if (file.size > 2 * 1024 * 1024) {
    showError('头像不能超过 2MB')
    return
  }
  avatarUploading.value = true
  clearFeedback()
  try {
    await auth.uploadAvatar(file)
    showSuccess('头像已更新')
  } catch (e) {
    showError(e.message)
  } finally {
    avatarUploading.value = false
  }
}

function cancelPassword() {
  showPasswordForm.value = false
  passwordForm.current = ''
  passwordForm.next = ''
  passwordForm.confirm = ''
  clearFeedback()
}

async function submitPassword() {
  if (!passwordForm.current || !passwordForm.next) {
    showError('请填写当前密码和新密码')
    return
  }
  if (passwordForm.next !== passwordForm.confirm) {
    showError('两次输入的新密码不一致')
    return
  }
  savingPassword.value = true
  clearFeedback()
  try {
    await auth.changePassword({
      currentPassword: passwordForm.current,
      newPassword: passwordForm.next
    })
    cancelPassword()
    showSuccess('密码修改成功')
  } catch (e) {
    showError(e.message)
  } finally {
    savingPassword.value = false
  }
}

function openResume(item) {
  if (!item?.resume) return
  if (item.sessionId) chat.setSessionId(item.sessionId)
  chat.setTargetJob(item.targetJob || '')
  chat.setResume(item.resume, item.qualityReport)
  router.push('/result')
}

function scoreColor(score) {
  if (score == null) return 'var(--color-text-muted)'
  if (score >= 85) return 'var(--color-success)'
  if (score >= 70) return 'var(--color-primary)'
  if (score >= 60) return 'var(--color-warning)'
  return 'var(--color-danger)'
}

function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function clearFeedback() {
  errorMsg.value = ''
  successMsg.value = ''
}

function showError(msg) {
  errorMsg.value = msg
  successMsg.value = ''
}

function showSuccess(msg) {
  successMsg.value = msg
  errorMsg.value = ''
}
</script>

<style scoped>
.profile {
  min-height: 100%;
  padding: 32px clamp(24px, 5vw, 72px) 56px;
  background: var(--color-bg);
}

.profile-head {
  margin-bottom: 24px;
}

.profile-head h1 {
  font-size: 2rem;
  font-weight: 800;
  color: var(--color-text);
  margin-bottom: 6px;
}

.profile-head p {
  color: var(--color-text-secondary);
  font-size: 1.05rem;
}

/* ---- 账号卡片 ---- */
.account-card {
  display: flex;
  align-items: center;
  gap: clamp(20px, 4vw, 40px);
  padding: 28px clamp(20px, 3vw, 32px);
  margin-bottom: 20px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.avatar-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.avatar-wrap {
  position: relative;
  width: 92px;
  height: 92px;
}

.avatar-img,
.avatar-fallback {
  width: 92px;
  height: 92px;
  border-radius: 50%;
  object-fit: cover;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar-fallback {
  background: var(--gradient-primary);
  color: #fff;
  font-size: 2.1rem;
  font-weight: 800;
}

.avatar-edit {
  position: absolute;
  left: 50%;
  bottom: -6px;
  transform: translateX(-50%);
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-pill);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  font-weight: 700;
  white-space: nowrap;
  box-shadow: var(--shadow-xs);
  transition: all 0.18s var(--ease-out);
}

.avatar-edit:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.avatar-edit:disabled {
  opacity: 0.6;
}

.avatar-input {
  display: none;
}

.avatar-hint {
  max-width: 150px;
  color: var(--color-text-muted);
  font-size: 0.78rem;
  text-align: center;
  line-height: 1.5;
}

.account-info {
  flex: 1;
  min-width: 0;
}

.account-name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.account-name-row h2 {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--color-text);
}

.name-input {
  height: 38px;
  padding: 0 12px;
  min-width: 200px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text);
  font-size: 1rem;
  font-family: inherit;
}

.name-input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.account-meta {
  display: flex;
  gap: clamp(24px, 5vw, 56px);
  flex-wrap: wrap;
}

.account-meta dt {
  color: var(--color-text-muted);
  font-size: 0.85rem;
  margin-bottom: 4px;
}

.account-meta dd {
  color: var(--color-text);
  font-size: 0.98rem;
  font-weight: 600;
}

.role-badge {
  display: inline-flex;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  font-weight: 700;
}

.role-badge.admin {
  background: var(--color-warning-soft);
  color: #B45309;
}

.role-badge.super_admin {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

/* ---- 数据概览 ---- */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 20px;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
}

.stat-value {
  font-size: 1.8rem;
  font-weight: 800;
  color: var(--color-primary);
  line-height: 1.1;
}

.stat-label {
  color: var(--color-text-muted);
  font-size: 0.88rem;
  font-weight: 600;
}

/* ---- 面板 ---- */
.panel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}

.panel {
  padding: 22px clamp(18px, 2.5vw, 26px);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-xs);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-head h3 {
  font-size: 1.08rem;
  font-weight: 800;
  color: var(--color-text);
}

.panel-link {
  color: var(--color-primary);
  font-size: 0.88rem;
  font-weight: 700;
  text-decoration: none;
}

.panel-link:hover {
  text-decoration: underline;
}

.panel-empty {
  padding: 28px 0;
  color: var(--color-text-muted);
  text-align: center;
  font-size: 0.95rem;
}

.panel-empty.left {
  padding: 4px 0 0;
  text-align: left;
}

.resume-list,
.apply-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
}

.resume-item,
.apply-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: all 0.18s var(--ease-out);
}

.resume-item {
  cursor: pointer;
}

.resume-item:hover {
  border-color: var(--color-primary-light);
  background: var(--color-primary-soft);
}

.resume-score {
  min-width: 42px;
  font-size: 1.3rem;
  font-weight: 800;
  text-align: center;
}

.resume-main,
.apply-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
  min-width: 0;
}

.resume-main strong,
.apply-main strong {
  color: var(--color-text);
  font-size: 0.98rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-main small,
.apply-main small,
.apply-side small {
  color: var(--color-text-muted);
  font-size: 0.82rem;
}

.resume-open {
  color: var(--color-primary);
  font-size: 0.88rem;
  font-weight: 700;
}

.apply-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.apply-status {
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  font-size: 0.8rem;
  font-weight: 700;
  white-space: nowrap;
}

.apply-status.interviewing,
.apply-status.offered {
  background: var(--color-success-soft);
  color: #047857;
}

.apply-status.rejected {
  background: var(--color-danger-soft);
  color: #B91C1C;
}

/* ---- 账号安全 ---- */
.security {
  max-width: 560px;
}

.password-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.password-form input {
  height: 42px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text);
  font-size: 0.98rem;
  font-family: inherit;
}

.password-form input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.password-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

/* ---- 通用小按钮 ---- */
.mini-btn {
  padding: 7px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-size: 0.88rem;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s var(--ease-out);
}

.mini-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.mini-btn.primary {
  background: var(--gradient-primary);
  border-color: transparent;
  color: #fff;
}

.mini-btn.primary:hover:not(:disabled) {
  color: #fff;
  box-shadow: var(--shadow-primary);
}

.mini-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.feedback {
  margin-top: 16px;
  font-weight: 600;
}

.feedback.error {
  color: var(--color-danger);
}

.feedback.success {
  color: var(--color-success);
}

@media (max-width: 720px) {
  .account-card {
    flex-direction: column;
    align-items: flex-start;
  }

  .avatar-block {
    align-self: center;
  }
}
</style>
