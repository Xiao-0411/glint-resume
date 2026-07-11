<template>
  <div class="admin-users">
    <header class="admin-head">
      <div>
        <h1>账号管理</h1>
        <p>{{ auth.isSuperAdmin ? '管理管理员与普通用户账号' : '管理普通用户账号' }}</p>
      </div>
      <button class="refresh-btn" @click="loadUsers" :disabled="loading">
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </header>

    <section v-if="!auth.isAdmin" class="denied">
      <h2>无权访问</h2>
      <p>当前账号没有管理员权限。</p>
    </section>

    <template v-else>
      <section class="filters">
        <input
          v-model="keyword"
          type="text"
          placeholder="搜索邮箱或昵称"
          @keydown.enter="loadUsers"
        />
        <select v-model="roleFilter" @change="loadUsers">
          <option value="">全部可管理账号</option>
          <option value="user">普通用户</option>
          <option v-if="auth.isSuperAdmin" value="admin">管理员</option>
        </select>
        <button class="search-btn" @click="loadUsers">搜索</button>
      </section>

      <section class="user-table-wrap">
        <table class="user-table">
          <thead>
            <tr>
              <th>账号</th>
              <th>角色</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="5" class="empty-cell">正在加载账号...</td>
            </tr>
            <tr v-else-if="users.length === 0">
              <td colspan="5" class="empty-cell">没有可管理的账号</td>
            </tr>
            <tr v-for="item in users" v-else :key="item.id">
              <td>
                <div class="account-main">
                  <strong>{{ item.name || item.email || '未命名账号' }}</strong>
                  <span>{{ item.email || item.id }}</span>
                </div>
              </td>
              <td>
                <span class="role-badge" :class="item.role">{{ roleLabel(item.role) }}</span>
              </td>
              <td>
                <span class="status-badge" :class="{ off: !item.is_active }">
                  {{ item.is_active ? '启用' : '禁用' }}
                </span>
              </td>
              <td>{{ formatDate(item.created_at) }}</td>
              <td>
                <div class="actions">
                  <button @click="toggleActive(item)">
                    {{ item.is_active ? '禁用' : '启用' }}
                  </button>
                  <button
                    v-if="auth.isSuperAdmin && item.role === 'user'"
                    class="primary"
                    @click="changeRole(item, 'admin')"
                  >
                    升为管理员
                  </button>
                  <button
                    v-if="auth.isSuperAdmin && item.role === 'admin'"
                    @click="changeRole(item, 'user')"
                  >
                    降为普通用户
                  </button>
                  <button class="danger" @click="deleteUser(item)">删除</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { adminApi } from '@/api'

const router = useRouter()
const auth = useAuthStore()

const users = ref([])
const loading = ref(false)
const keyword = ref('')
const roleFilter = ref('')
const errorMsg = ref('')

onMounted(async () => {
  if (!auth.isLoggedIn) {
    auth.openLogin()
    router.replace('/')
    return
  }
  if (!auth.isAdmin) return
  await loadUsers()
})

async function loadUsers() {
  if (!auth.isAdmin) return
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await adminApi.listUsers({
      keyword: keyword.value,
      role: roleFilter.value,
      limit: 100,
      offset: 0
    })
    users.value = data.users || []
  } catch (e) {
    errorMsg.value = errorMessage(e, '账号列表加载失败')
  } finally {
    loading.value = false
  }
}

async function toggleActive(item) {
  errorMsg.value = ''
  try {
    const updated = await adminApi.updateUser(item.id, { isActive: !item.is_active })
    replaceUser(updated)
  } catch (e) {
    errorMsg.value = errorMessage(e, '账号状态更新失败')
  }
}

async function changeRole(item, role) {
  errorMsg.value = ''
  try {
    const updated = await adminApi.updateUser(item.id, { role })
    replaceUser(updated)
  } catch (e) {
    errorMsg.value = errorMessage(e, '角色更新失败')
  }
}

async function deleteUser(item) {
  if (!confirm(`确定删除账号「${item.email || item.name}」吗？`)) return
  errorMsg.value = ''
  try {
    await adminApi.deleteUser(item.id)
    users.value = users.value.filter(u => u.id !== item.id)
  } catch (e) {
    errorMsg.value = errorMessage(e, '账号删除失败')
  }
}

function replaceUser(updated) {
  const idx = users.value.findIndex(u => u.id === updated.id)
  if (idx >= 0) users.value[idx] = updated
  else users.value.unshift(updated)
}

function roleLabel(role) {
  if (role === 'super_admin') return '超级管理员'
  if (role === 'admin') return '管理员'
  return '普通用户'
}

function formatDate(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function errorMessage(error, fallback) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return detail || error?.message || fallback
}
</script>

<style scoped>
.admin-users {
  min-height: 100%;
  padding: 32px clamp(24px, 5vw, 72px);
  background: var(--color-bg);
}

.admin-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.admin-head h1 {
  font-size: 2rem;
  font-weight: 800;
  color: var(--color-text);
  margin-bottom: 6px;
}

.admin-head p {
  color: var(--color-text-secondary);
  font-size: 1.05rem;
}

.refresh-btn,
.search-btn,
.actions button {
  padding: 9px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text-secondary);
  font-weight: 600;
  transition: all 0.18s var(--ease-out);
}

.refresh-btn:hover,
.search-btn:hover,
.actions button:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-primary-soft);
}

.filters {
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
}

.filters input,
.filters select {
  height: 42px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  color: var(--color-text);
  font-size: 1rem;
}

.filters input {
  min-width: 280px;
}

.user-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-card);
  box-shadow: var(--shadow-xs);
}

.user-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 860px;
}

.user-table th,
.user-table td {
  padding: 16px 18px;
  text-align: left;
  border-bottom: 1px solid var(--color-border-light);
}

.user-table th {
  background: var(--color-bg-subtle);
  color: var(--color-text-muted);
  font-size: 0.9rem;
  font-weight: 800;
}

.account-main {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.account-main strong {
  color: var(--color-text);
  font-size: 1.05rem;
}

.account-main span {
  color: var(--color-text-muted);
  font-size: 0.92rem;
}

.role-badge,
.status-badge {
  display: inline-flex;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  font-size: 0.88rem;
  font-weight: 700;
}

.role-badge.user {
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
}

.role-badge.admin {
  background: #FEF3C7;
  color: #B45309;
}

.role-badge.super_admin {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.status-badge {
  background: #D1FAE5;
  color: #047857;
}

.status-badge.off {
  background: #FEE2E2;
  color: #B91C1C;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.actions .primary {
  background: var(--gradient-primary);
  color: #fff;
  border-color: transparent;
}

.actions .primary:hover {
  color: #fff;
  box-shadow: var(--shadow-primary);
}

.actions .danger {
  color: var(--color-danger);
}

.actions .danger:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
  background: var(--color-danger-soft);
}

.empty-cell,
.denied {
  text-align: center;
  color: var(--color-text-muted);
  padding: 48px 20px;
}

.denied {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
}

.denied h2 {
  color: var(--color-text);
  margin-bottom: 8px;
}

.error-msg {
  margin-top: 14px;
  color: var(--color-danger);
  font-weight: 600;
}

@media (max-width: 720px) {
  .admin-head,
  .filters {
    flex-direction: column;
    align-items: stretch;
  }

  .filters input {
    min-width: 0;
  }
}
</style>
