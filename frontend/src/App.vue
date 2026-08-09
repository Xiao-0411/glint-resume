<template>
  <n-config-provider :theme-overrides="themeOverrides">
    <n-message-provider>
      <div class="app-shell">
        <top-nav />
        <main class="app-main">
          <router-view v-slot="{ Component, route }">
            <transition :name="route.meta.transition || 'fade'" mode="out-in">
              <component :is="Component" :key="route.path" />
            </transition>
          </router-view>
        </main>
      </div>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import TopNav from '@/components/TopNav.vue'
import { useSessionPersistence } from '@/composables/useSessionPersistence'

const themeOverrides = {
  common: {
    primaryColor: '#4F46E5',
    primaryColorHover: '#7C3AED',
    primaryColorPressed: '#4338CA',
    primaryColorSuppl: '#4F46E5',
    borderRadius: '12px',
    fontFamily: '"Plus Jakarta Sans", "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif'
  }
}

useSessionPersistence()
</script>

<style>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.app-main {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.45s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.slide-enter-active,
.slide-leave-active {
  transition: all 0.55s var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
}
.slide-enter-from {
  opacity: 0;
  transform: translateX(40px);
}
.slide-leave-to {
  opacity: 0;
  transform: translateX(-40px);
}
</style>
