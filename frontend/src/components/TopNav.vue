<template>
  <header class="top-nav">
    <div class="nav-inner">
      <!-- 品牌 Logo -->
      <router-link to="/" class="brand-logo" title="回到首页">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="logo-svg">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
        <span class="logo-text">识光简历</span>
      </router-link>

      <!-- Dock 风格导航 -->
      <nav class="nav-dock" @mousemove="handleDockMove" @mouseleave="resetDock">
        <router-link
          :ref="el => setDockItemRef(el, 0)"
          :style="dockItemStyle(0)"
          to="/"
          class="dock-item"
        >
          首页
        </router-link>
        <router-link
          :ref="el => setDockItemRef(el, 1)"
          :style="dockItemStyle(1)"
          to="/chat"
          class="dock-item dock-item-accent"
        >
          创建简历
        </router-link>
        <router-link
          :ref="el => setDockItemRef(el, 2)"
          :style="dockItemStyle(2)"
          to="/dashboard"
          class="dock-item"
        >
          求职投递
        </router-link>
      </nav>

      <!-- 用户区域 -->
      <div class="user-area">
        <template v-if="auth.isLoggedIn">
          <div class="user-dropdown" ref="dropdownRef">
            <button class="user-btn" @click="showDropdown = !showDropdown">
              <span class="user-avatar">{{ auth.user?.name?.charAt(0)?.toUpperCase() || 'U' }}</span>
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
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>
          </svg>
          <span class="login-text">登录</span>
        </button>
      </div>
    </div>

    <LoginDialog />
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
const dockItems = []
const dockScales = ref([1, 1, 1])

function setDockItemRef(el, index) {
  dockItems[index] = el?.$el || el
}

function handleDockMove(event) {
  const maxDistance = 180

  dockScales.value = dockItems.map((item) => {
    if (!item) return 1
    const rect = item.getBoundingClientRect()
    const distance = Math.abs(event.clientX - (rect.left + rect.width / 2))
    const proximity = Math.max(0, 1 - distance / maxDistance)
    const easedProximity = 1 - Math.pow(1 - proximity, 2)
    return 1 + 0.06 * easedProximity
  })
}

function resetDock() {
  dockScales.value = [1, 1, 1]
}

function dockItemStyle(index) {
  const scale = dockScales.value[index] || 1
  const lift = Math.max(0, (scale - 1) * 30)
  return {
    '--dock-scale': scale,
    '--dock-lift': `${lift}px`
  }
}

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
  display: flex;
  justify-content: center;
  width: 100%;
  min-height: 72px;
  padding: 0 clamp(24px, 5vw, 80px);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(18px) saturate(160%);
  -webkit-backdrop-filter: blur(18px) saturate(160%);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 6px 22px rgba(15, 23, 42, 0.05);
}

.nav-inner {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  width: min(1280px, 100%);
  min-height: 72px;
  gap: 24px;
  padding: 8px 0;
}

.brand-logo {
  display: flex;
  align-items: center;
  justify-self: start;
  gap: 8px;
  text-decoration: none;
  transition: opacity 0.2s ease;
}
.brand-logo:hover { opacity: 0.8; }
.logo-svg { color: var(--color-primary); }
.logo-text {
  font-weight: 700;
  font-size: 1.1rem;
  color: var(--color-text);
}

/* Dock 风格导航 */
.nav-dock {
  display: flex;
  align-items: center;
  justify-self: center;
  justify-content: space-between;
  width: clamp(380px, 30vw, 480px);
  height: 44px;
  gap: 12px;
}

.dock-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0 16px;
  border-radius: 8px;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid var(--color-border);
  box-shadow: var(--shadow-xs);
  font-size: 0.9rem;
  font-weight: 600;
  white-space: nowrap;
  transform: translateY(calc(var(--dock-lift, 0px) * -1)) scale(var(--dock-scale, 1));
  transition:
    transform 110ms var(--ease-out),
    color 180ms ease,
    background-color 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease;
  text-decoration: none;
  outline: none;
  transform-origin: center bottom;
  will-change: transform;
}

.dock-item:hover,
.dock-item:focus-visible {
  background: var(--color-primary-soft);
  border-color: var(--color-primary-light);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.12);
  color: var(--color-primary);
}

.dock-item.router-link-active {
  color: var(--color-primary);
  background: #FFFFFF;
  border-color: rgba(224, 231, 255, 0.95);
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.1);
}

.dock-item-accent {
  color: var(--color-primary);
}

/* 用户区域 */
.user-area {
  display: flex;
  align-items: center;
  justify-self: end;
}

.login-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 12px;
  border-radius: 9px;
  background: var(--gradient-primary);
  border: 1px solid transparent;
  color: #FFFFFF;
  font-size: 0.9rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s;
}

.login-btn:hover {
  box-shadow: var(--shadow-primary);
  transform: translateY(-1px);
}

.user-dropdown { position: relative; }

.user-btn {
  display: flex;
  align-items: center;
  padding: 0;
  border: none;
  background: transparent;
  cursor: pointer;
}

.user-avatar {
  width: 36px; height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--gradient-primary);
  color: #fff;
  font-weight: 700;
  font-size: 0.9rem;
  transition: transform 0.2s;
}

.user-avatar:hover {
  transform: scale(1.1);
}

.dropdown-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 160px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-xl);
  overflow: hidden;
  z-index: 10;
  padding: 6px;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.15s;
  text-decoration: none;
}

.dropdown-item svg { color: var(--color-text-muted); }
.dropdown-item:hover { background: var(--color-primary-soft); color: var(--color-text); }
.dropdown-item:hover svg { color: var(--color-primary); }
.dropdown-item.danger:hover { background: rgba(239, 68, 68, 0.15); color: #EF4444; }
.dropdown-item.danger:hover svg { color: #EF4444; }

@media (max-width: 768px) {
  .top-nav {
    min-height: 60px;
    padding: 0 12px;
  }
  .logo-text { display: none; }
  .nav-inner {
    grid-template-columns: 40px minmax(0, 1fr) 40px;
    min-height: 60px;
    gap: 6px;
    padding: 6px 0;
  }
  .nav-dock {
    width: min(310px, 100%);
    height: 42px;
    gap: 6px;
  }
  .dock-item {
    height: 36px;
    padding: 0 8px;
    font-size: 0.8rem;
    transform: none;
  }
  .login-btn { padding: 8px; }
  .login-text { display: none; }
}

@media (max-width: 390px) {
  .top-nav { padding: 0 8px; }
  .nav-inner {
    grid-template-columns: 34px minmax(0, 1fr) 34px;
    gap: 3px;
  }
  .brand-logo svg { width: 28px; height: 28px; }
  .nav-dock { gap: 4px; }
  .dock-item { height: 34px; padding: 0 5px; font-size: 0.75rem; }
  .login-btn { padding: 7px; }
}

@media (prefers-reduced-motion: reduce) {
  .dock-item { transition: color 180ms ease, background-color 180ms ease; }
}
</style>
