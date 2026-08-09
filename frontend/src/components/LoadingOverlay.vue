<template>
  <transition name="loading-fade">
    <div v-if="visible" class="loading-overlay">
      <div class="loading-content">
        <div class="paper-icon">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
        </div>

        <h2 class="loading-title">{{ title }}</h2>
        <p class="loading-sub">{{ subtitle }}</p>

        <div class="progress-track">
          <div class="progress-bar" :style="{ width: progress + '%' }"></div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: 'AI 正在分析你的经历' },
  subtitle: { type: String, default: '重新连接你的闪光点……' },
  duration: { type: Number, default: 2000 }
})

const emit = defineEmits(['done'])

const progress = ref(0)
let rafId = null

watch(() => props.visible, (v) => {
  if (v) run()
  else progress.value = 0
})

onMounted(() => {
  if (props.visible) run()
})

onBeforeUnmount(() => {
  if (rafId) cancelAnimationFrame(rafId)
})

function run() {
  progress.value = 0
  const start = Date.now()
  const tick = () => {
    const elapsed = Date.now() - start
    // 逼近而非填满：真实耗时不可预测（LLM 40~180s），
    // 进度条走到 95% 后放慢，避免"满格后仍在等"的假完成感。
    const raw = (elapsed / props.duration) * 100
    progress.value = raw < 95
      ? raw
      : Math.min(99, 95 + (raw - 95) * 0.05)
    if (elapsed < props.duration) {
      rafId = requestAnimationFrame(tick)
    } else {
      setTimeout(() => emit('done'), 200)
    }
  }
  rafId = requestAnimationFrame(tick)
}
</script>

<style scoped>
.loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 30% 30%, rgba(37, 99, 235, 0.08), transparent 60%),
    radial-gradient(circle at 70% 70%, rgba(8, 145, 178, 0.06), transparent 60%),
    rgba(249, 250, 251, 0.92);
  backdrop-filter: blur(8px) saturate(180%);
  -webkit-backdrop-filter: blur(8px) saturate(180%);
}

.loading-fade-enter-active,
.loading-fade-leave-active {
  transition: opacity 0.35s var(--ease-out);
}
.loading-fade-enter-from,
.loading-fade-leave-to {
  opacity: 0;
}

.loading-content {
  text-align: center;
  width: 100%;
  max-width: 380px;
  padding: 40px 24px;
  animation: fadeInUp 0.5s var(--ease-out);
}

.paper-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  margin-bottom: 26px;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-xl);
  box-shadow:
    0 10px 28px rgba(37, 99, 235, 0.35),
    inset 0 0 0 1px rgba(255, 255, 255, 0.15);
  animation: float 2.8s ease-in-out infinite;
  position: relative;
}

.paper-icon::before {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: var(--radius-xl);
  border: 1px solid rgba(37, 99, 235, 0.25);
  animation: pulseRing 2.2s var(--ease-out) infinite;
}

@keyframes pulseRing {
  0% { transform: scale(1); opacity: 0.8; }
  100% { transform: scale(1.25); opacity: 0; }
}

.loading-title {
  font-size: 1.7rem;
  font-weight: 800;
  color: var(--color-text);
  margin-bottom: 10px;
  letter-spacing: -0.3px;
}

.loading-sub {
  color: var(--color-text-secondary);
  font-size: 1.15rem;
  margin-bottom: 28px;
  line-height: 1.65;
}

.progress-track {
  width: 100%;
  height: 4px;
  background: var(--color-border-light);
  border-radius: var(--radius-pill);
  overflow: hidden;
  position: relative;
}

.progress-track::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(37, 99, 235, 0.15), transparent);
  animation: shimmer 1.8s ease-in-out infinite;
  background-size: 200% 100%;
}

.progress-bar {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: var(--radius-pill);
  transition: width 0.15s linear;
  box-shadow: 0 0 8px rgba(37, 99, 235, 0.4);
  position: relative;
  z-index: 1;
}
</style>
