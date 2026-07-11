<template>
  <transition name="re-eval-fade">
    <div v-if="open" class="dialog-mask" @click.self="$emit('later')">
      <div class="dialog">
        <div class="dialog-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
            <path d="M21 3v5h-5"/>
            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
            <path d="M3 21v-5h5"/>
          </svg>
        </div>
        <h3 class="dialog-title">简历已修改</h3>
        <p class="dialog-text">
          <span class="resume-mark">「{{ expTitle || '该段经历' }}」</span> 已更新。是否立即重新评定质量分?
        </p>

        <div class="opt-list">
          <button
            class="opt opt-primary"
            @click="$emit('confirm')"
          >
            <div class="opt-main">
              <span class="opt-title">立即重新评定</span>
              <span class="opt-sub">系统会基于最新内容生成新的五维评分(约 2~3 秒)</span>
            </div>
            <span class="opt-arrow">›</span>
          </button>
          <button
            class="opt opt-ghost"
            @click="$emit('later')"
          >
            <div class="opt-main">
              <span class="opt-title">稍后重新评定</span>
              <span class="opt-sub">保持当前分数,顶部会出现「待重评」提示,随时可点击重评</span>
            </div>
            <span class="opt-arrow">›</span>
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
defineProps({
  open: { type: Boolean, default: false },
  expTitle: { type: String, default: '' }
})

defineEmits(['confirm', 'later'])
</script>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 1100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.dialog {
  width: 100%;
  max-width: 460px;
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.25);
  padding: 28px 24px 22px;
  text-align: center;
}

.dialog-icon {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 14px;
}

.dialog-title {
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
  letter-spacing: -0.2px;
}

.dialog-text {
  font-size: 1.05rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin-bottom: 18px;
}

.resume-mark {
  color: var(--color-primary);
  font-weight: 700;
}

.opt-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  text-align: left;
}

.opt {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  transition: all 0.2s var(--ease-out);
  border: 1px solid transparent;
}

.opt-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.opt-title {
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.1px;
}

.opt-sub {
  font-size: 0.92rem;
  line-height: 1.5;
  opacity: 0.85;
}

.opt-arrow {
  font-size: 1.6rem;
  font-weight: 300;
  opacity: 0.55;
  transition: transform 0.2s var(--ease-out);
}

.opt:hover .opt-arrow {
  transform: translateX(3px);
}

.opt-primary {
  background: var(--gradient-primary);
  color: white;
  box-shadow: var(--shadow-primary);
}

.opt-primary:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

.opt-ghost {
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  border-color: var(--color-border-light);
}

.opt-ghost:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
  border-color: var(--color-border);
}

.re-eval-fade-enter-active,
.re-eval-fade-leave-active {
  transition: opacity 0.22s var(--ease-out);
}
.re-eval-fade-enter-active .dialog,
.re-eval-fade-leave-active .dialog {
  transition: transform 0.22s var(--ease-out), opacity 0.22s var(--ease-out);
}
.re-eval-fade-enter-from,
.re-eval-fade-leave-to {
  opacity: 0;
}
.re-eval-fade-enter-from .dialog,
.re-eval-fade-leave-to .dialog {
  transform: translateY(12px) scale(0.96);
  opacity: 0;
}
</style>
