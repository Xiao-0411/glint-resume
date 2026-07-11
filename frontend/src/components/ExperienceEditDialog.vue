<template>
  <transition name="dialog-fade">
    <div v-if="exp" class="dialog-mask" @click.self="onClose">
      <div class="dialog">
        <header class="dialog-head">
          <div class="head-left">
            <span class="head-icon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 20h9"/>
                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4z"/>
              </svg>
            </span>
            <div class="head-titles">
              <h3 class="dialog-title">编辑经历</h3>
              <span class="dialog-sub">修改后系统会询问是否立即重新评定</span>
            </div>
          </div>
          <button class="dialog-close" @click="onClose">×</button>
        </header>

        <div class="dialog-body">
          <!-- 三项元信息 -->
          <div class="meta-grid">
            <div class="field">
              <label>项目 / 经历名称</label>
              <input v-model="draft.title" type="text" maxlength="40" placeholder="如:校园食堂点餐系统" />
            </div>
            <div class="field">
              <label>角色 / 职位</label>
              <input v-model="draft.role" type="text" maxlength="30" placeholder="如:后端负责人" />
            </div>
            <div class="field">
              <label>时间段</label>
              <input v-model="draft.period" type="text" maxlength="30" placeholder="如:2023.09 - 2024.01" />
            </div>
          </div>

          <!-- bullets -->
          <div class="bullets-section">
            <div class="bullets-head">
              <label>项目要点(bullet 描述)</label>
              <button class="add-bullet" @click="addBullet" type="button">+ 添加一条</button>
            </div>
            <div class="bullet-list">
              <div
                v-for="(b, i) in draft.bullets"
                :key="i"
                class="bullet-row"
              >
                <span class="bullet-no">{{ i + 1 }}</span>
                <textarea
                  v-model="draft.bullets[i]"
                  rows="2"
                  :placeholder="`第 ${i + 1} 条要点,使用动词开头,尽量量化`"
                  @input="autoGrow($event)"
                  ref="bulletRefs"
                ></textarea>
                <button
                  class="bullet-del"
                  @click="removeBullet(i)"
                  type="button"
                  :disabled="draft.bullets.length <= 1"
                  title="删除"
                >×</button>
              </div>
            </div>
          </div>

          <p class="hint">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>建议每条要点 25~50 字,以动词开头(如"主导/设计/优化/分析"),并尽可能附数据。</span>
          </p>
        </div>

        <footer class="dialog-foot">
          <button class="btn-ghost" @click="onClose">取消</button>
          <button class="btn-primary" :disabled="!canSave" @click="onSave">保存修改</button>
        </footer>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, watch, computed, nextTick } from 'vue'

const props = defineProps({
  exp: { type: Object, default: null }
})

const emit = defineEmits(['close', 'save'])

const draft = ref({ title: '', role: '', period: '', bullets: [''] })
const bulletRefs = ref([])

watch(() => props.exp, (val) => {
  if (val) {
    draft.value = {
      title: val.title || '',
      role: val.role || '',
      period: val.period || '',
      bullets: Array.isArray(val.bullets) && val.bullets.length ? [...val.bullets] : ['']
    }
    nextTick(() => {
      if (bulletRefs.value) {
        bulletRefs.value.forEach(t => autoGrow({ target: t }))
      }
    })
  }
}, { immediate: true })

const canSave = computed(() => {
  if (!draft.value.title.trim()) return false
  return draft.value.bullets.some(b => b && b.trim())
})

function addBullet() {
  draft.value.bullets.push('')
}

function removeBullet(i) {
  if (draft.value.bullets.length <= 1) return
  draft.value.bullets.splice(i, 1)
}

function autoGrow(e) {
  const el = e.target
  if (!el) return
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

function onClose() {
  emit('close')
}

function onSave() {
  if (!canSave.value) return
  emit('save', {
    title: draft.value.title.trim(),
    role: draft.value.role.trim(),
    period: draft.value.period.trim(),
    bullets: draft.value.bullets.map(b => b.trim()).filter(b => b)
  })
}
</script>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.dialog {
  width: 100%;
  max-width: 720px;
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.25);
  overflow: hidden;
}

.dialog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid var(--color-border-light);
  background: linear-gradient(180deg, var(--color-bg-card), var(--color-bg-subtle));
}

.head-left {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.head-icon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.head-titles {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dialog-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.2px;
}

.dialog-sub {
  font-size: 0.95rem;
  color: var(--color-text-muted);
}

.dialog-close {
  width: 32px;
  height: 32px;
  font-size: 1.5rem;
  line-height: 1;
  color: var(--color-text-muted);
  border-radius: var(--radius-sm);
  transition: all 0.2s var(--ease-out);
}

.dialog-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.meta-grid .field:first-child {
  grid-column: span 2;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.field input,
.bullet-row textarea {
  width: 100%;
  padding: 9px 12px;
  font-size: 1.05rem;
  color: var(--color-text);
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: inherit;
  line-height: 1.55;
  transition: border-color 0.2s, box-shadow 0.2s;
  resize: none;
}

.field input:focus,
.bullet-row textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.bullets-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bullets-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.bullets-head label {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.add-bullet {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-primary);
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  border: 1px dashed var(--color-primary-light);
  transition: all 0.2s var(--ease-out);
}

.add-bullet:hover {
  background: var(--color-primary-soft);
}

.bullet-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bullet-row {
  position: relative;
  display: grid;
  grid-template-columns: 28px 1fr 28px;
  align-items: start;
  gap: 6px;
}

.bullet-no {
  margin-top: 10px;
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--color-text-muted);
  text-align: center;
}

.bullet-row textarea {
  min-height: 50px;
}

.bullet-del {
  margin-top: 4px;
  width: 28px;
  height: 28px;
  font-size: 1.1rem;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  transition: all 0.2s var(--ease-out);
}

.bullet-del:hover:not(:disabled) {
  background: var(--color-danger-soft, rgba(239, 68, 68, 0.10));
  color: var(--color-danger, #DC2626);
}

.bullet-del:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.hint {
  display: inline-flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  background: var(--color-warning-soft);
  border-radius: var(--radius-sm);
  font-size: 0.95rem;
  color: #92400E;
  line-height: 1.5;
}

.hint svg {
  flex-shrink: 0;
  margin-top: 2px;
}

.dialog-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 24px;
  border-top: 1px solid var(--color-border-light);
  background: var(--color-bg-subtle);
}

.btn-ghost,
.btn-primary {
  padding: 9px 18px;
  font-size: 1.05rem;
  font-weight: 600;
  border-radius: var(--radius-sm);
  transition: all 0.2s var(--ease-out);
}

.btn-ghost {
  color: var(--color-text-secondary);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
}

.btn-ghost:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
}

.btn-primary {
  background: var(--gradient-primary);
  color: white;
  box-shadow: var(--shadow-primary);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

.btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

/* 过渡 */
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.22s var(--ease-out);
}
.dialog-fade-enter-active .dialog,
.dialog-fade-leave-active .dialog {
  transition: transform 0.22s var(--ease-out), opacity 0.22s var(--ease-out);
}
.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
.dialog-fade-enter-from .dialog,
.dialog-fade-leave-to .dialog {
  transform: translateY(12px) scale(0.97);
  opacity: 0;
}
</style>
