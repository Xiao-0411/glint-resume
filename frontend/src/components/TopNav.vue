<template>
  <header class="top-nav">
    <div class="nav-inner">
      <!-- 品牌 Logo -->
      <router-link to="/" class="brand-logo" title="回到首页">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" class="logo-svg">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
        <span class="logo-text">识光简历</span>
      </router-link>

      <!-- 功能入口 -->
      <nav class="nav-links">
        <router-link to="/" class="nav-link">首页</router-link>
        <router-link to="/chat" class="nav-link nav-link-accent">创建简历</router-link>
        <router-link to="/dashboard" class="nav-link">求职投递</router-link>
      </nav>

      <!-- 用户区域 -->
      <div class="user-area">
        <template v-if="auth.isLoggedIn">
          <div class="user-dropdown" ref="dropdownRef">
            <button class="user-btn" @click="showDropdown = !showDropdown">
              <span class="user-avatar">{{ auth.user?.name?.charAt(0)?.toUpperCase() || 'U' }}</span>
              <span class="user-name">{{ auth.user?.name }}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            <div v-if="showDropdown" class="dropdown-menu">
              <div class="dropdown-item" @click="openHistory">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
                </svg>
                我的简历
              </div>
              <router-link v-if="auth.isAdmin" to="/admin/users" class="dropdown-item" @click="showDropdown = false">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                </svg>
                账号管理
              </router-link>
              <div class="dropdown-item danger" @click="handleLogout">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
                </svg>
                退出登录
              </div>
            </div>
          </div>
        </template>
        <button v-else class="login-btn" @click="auth.openLogin()">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
          </svg>
          <span>登录</span>
        </button>
      </div>
    </div>

    <!-- 登录弹窗（全局，由 auth store 控制） -->
    <LoginDialog />
    <!-- 我的简历历史 -->
    <ResumeHistoryDialog v-model:show="showHistory" />
  </header>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import LoginDialog from '@/components/LoginDialog.vue'
import ResumeHistoryDialog from '@/components/ResumeHistoryDialog.vue'

const auth = useAuthStore()
const showDropdown = ref(false)
const showHistory = ref(false)
const dropdownRef = ref(null)

function openHistory() {
  showDropdown.value = false
  showHistory.value = true
}

function handleLogout() {
  showDropdown.value = false
  auth.logout()
}

function handleClickOutside(e) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target)) {
    showDropdown.value = false
  }
}

onMounted(() => window.addEventListener('click', handleClickOutside))
onUnmounted(() => window.removeEventListener('click', handleClickOutside))
</script>

<style scoped>
.top-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px) saturate(180%);
  -webkit-backdrop-filter: blur(16px) saturate(180%);
  border-bottom: 1px solid rgba(229, 231, 235, 0.6);
}

.nav-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  margin: 0 auto;
  padding: 20px clamp(48px, 3.2vw, 64px);
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  text-decoration: none;
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.brand-logo:hover { transform: scale(1.04); }
.logo-svg { color: #2563EB; }
.logo-text { font-weight: 700; font-size: 1.7rem; color: #1F2937; letter-spacing: -0.3px; }

.nav-links { display: flex; align-items: center; gap: 18px; }

.nav-link {
  padding: 13px 32px;
  border-radius: 10px;
  font-size: 1.4rem;
  font-weight: 500;
  color: #6B7280;
  text-decoration: none;
  transition: all 0.2s;
}
.nav-link:hover { background: #F3F4F6; color: #1F2937; }
.nav-link-accent {
  background: linear-gradient(135deg, #2563EB, #1D4ED8);
  color: #fff !important;
  font-weight: 600;
}
.nav-link-accent:hover {
  background: linear-gradient(135deg, #1D4ED8, #1E40AF);
  color: #fff !important;
  box-shadow: 0 6px 18px rgba(37,99,235,0.4);
}

.user-area { display: flex; align-items: center; }

.login-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 13px 30px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 1.3rem;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}
.login-btn:hover { border-color: #2563EB; color: #2563EB; background: #EFF6FF; }

.user-dropdown { position: relative; }
.user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 1.3rem;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}
.user-btn:hover { border-color: #2563EB; }
.user-avatar {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563EB, #1D4ED8);
  color: #fff;
  font-weight: 700;
  font-size: 1.25rem;
}
.user-name { font-weight: 500; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 168px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  box-shadow: 0 8px 30px rgba(0,0,0,0.10);
  overflow: hidden;
  z-index: 10;
  padding: 6px;
}
.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 14px;
  font-size: 1.1rem;
  color: #374151;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s, color 0.15s;
  text-decoration: none;
}
.dropdown-item svg { color: #9CA3AF; flex-shrink: 0; }
.dropdown-item:hover { background: #F3F4F6; color: #1F2937; }
.dropdown-item:hover svg { color: #2563EB; }
.dropdown-item.danger:hover { background: #FEE2E2; color: #DC2626; }
.dropdown-item.danger:hover svg { color: #DC2626; }

@media (max-width: 768px) {
  .nav-inner { padding: 14px 20px; }
  .logo-text { display: none; }
  .nav-link { padding: 10px 18px; font-size: 1.2rem; }
  .login-btn span { display: none; }
}
</style>
