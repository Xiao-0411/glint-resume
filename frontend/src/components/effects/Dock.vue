<template>
  <div class="dock-outer">
    <div class="dock-panel">
      <div
        v-for="(item, i) in items"
        :key="i"
        class="dock-item"
        :class="{ 'dock-item-hovered': hoveredIndex === i }"
        @click="item.onClick"
        @mouseenter="hoveredIndex = i"
        @mouseleave="hoveredIndex = null"
      >
        <span v-if="hoveredIndex === i" class="dock-label">{{ item.label }}</span>
        <div class="dock-icon">
          <component :is="item.icon" v-if="typeof item.icon !== 'string'" />
          <span v-else v-html="item.icon"></span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  items: { type: Array, required: true }
})

const hoveredIndex = ref(null)
</script>

<style scoped>
.dock-outer {
  position: fixed;
  bottom: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
}

.dock-panel {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 16px;
  background: rgba(18, 15, 23, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.dock-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  outline: none;
}

.dock-item:hover,
.dock-item-hovered {
  width: 64px;
  height: 64px;
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.dock-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 1.2rem;
}

.dock-label {
  position: absolute;
  top: -32px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  padding: 4px 12px;
  border-radius: 6px;
  background: rgba(18, 15, 23, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #fff;
  font-size: 0.75rem;
  pointer-events: none;
  animation: dockLabelIn 0.2s ease-out;
}

@keyframes dockLabelIn {
  from { opacity: 0; transform: translateX(-50%) translateY(4px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
</style>