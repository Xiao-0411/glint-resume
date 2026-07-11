<template>
  <n-modal
    :show="show"
    @update:show="v => emit('update:show', v)"
    :mask-closable="true"
    transform-origin="center"
  >
    <div class="hist-card">
      <button class="hist-close" type="button" @click="emit('update:show', false)" aria-label="关闭">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>

      <div class="hist-head">
        <h2 class="hist-title">我的简历</h2>
        <p class="hist-sub">这里保存了你历次生成的简历，可随时重新打开查看</p>
      </div>

      <!-- 空态 -->
      <div v-if="!auth.resumeHistory.length" class="hist-empty">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        </svg>
        <p>还没有生成过简历</p>
        <span>去首页创建你的第一份简历吧</span>
      </div>

      <!-- 列表 -->
      <div v-else class="hist-list">
        <div v-for="item in auth.resumeHistory" :key="item.id" class="hist-item" @click="openItem(item)">
          <div class="hist-score" :style="{ color: item.gradeColor || scoreColor(item.score) }">
            <span class="hist-score-num">{{ item.score ?? '--' }}</span>
            <span class="hist-score-cap">分</span>
          </div>
          <div class="hist-info">
            <div class="hist-job">{{ item.targetJob || '未命名简历' }}</div>
            <div class="hist-meta">
              <span class="hist-tag" :class="sourceClass(item.source)">
                {{ sourceLabel(item.source) }}
              </span>
              <span v-if="item.grade" class="hist-grade">{{ item.grade }}</span>
              <span class="hist-date">{{ formatDate(item.createdAt) }}</span>
            </div>
          </div>
          <div class="hist-actions" @click.stop>
            <button class="hist-open" @click="openItem(item)">打开</button>
            <button class="hist-del" @click="auth.removeResumeFromHistory(item.id)" title="删除">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </n-modal>
</template>

<script setup>
import { NModal } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'

defineProps({ show: { type: Boolean, default: false } })
const emit = defineEmits(['update:show'])

const router = useRouter()
const auth = useAuthStore()
const chat = useChatStore()

function openItem(item) {
  if (!item?.resume) return
  if (item.sessionId) chat.setSessionId(item.sessionId)
  chat.setTargetJob(item.targetJob || '')
  chat.setResume(item.resume, item.qualityReport)
  emit('update:show', false)
  router.push('/result')
}

function sourceLabel(source) {
  if (source === 'upload' || source === 'upload_mock') return '上传优化'
  if (source === 'edit' || source === 'edit_mock') return '编辑重评'
  return '从零生成'
}

function sourceClass(source) {
  if (source === 'upload' || source === 'upload_mock') return 'upload'
  if (source === 'edit' || source === 'edit_mock') return 'edit'
  return 'chat'
}

function scoreColor(score) {
  if (score == null) return 'var(--color-text-muted)'
  if (score >= 85) return 'var(--color-success)'
  if (score >= 70) return 'var(--color-primary)'
  if (score >= 60) return 'var(--color-warning)'
  return 'var(--color-danger)'
}

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style scoped>
.hist-card {
  position: relative;
  width: 560px;
  max-width: 92vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-card);
  border-radius: var(--radius-2xl);
  padding: 34px 32px 28px;
  box-shadow: var(--shadow-xl);
  border: 1px solid var(--color-border-light);
  animation: scaleIn 0.28s var(--ease-out);
}

.hist-close {
  position: absolute;
  top: 18px;
  right: 18px;
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  transition: all 0.2s var(--ease-out);
}
.hist-close:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
}

.hist-head {
  margin-bottom: 20px;
}
.hist-title {
  font-size: 1.55rem;
  font-weight: 800;
  color: var(--color-text);
  letter-spacing: -0.4px;
  margin-bottom: 6px;
}
.hist-sub {
  font-size: 0.98rem;
  color: var(--color-text-muted);
}

/* 空态 */
.hist-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 0 40px;
  color: var(--color-text-muted);
}
.hist-empty svg { opacity: 0.32; margin-bottom: 6px; }
.hist-empty p { font-size: 1.15rem; font-weight: 600; color: var(--color-text-secondary); }
.hist-empty span { font-size: 0.95rem; }

/* 列表 */
.hist-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding: 2px;
}
.hist-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 18px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  background: var(--color-bg-subtle);
  cursor: pointer;
  transition: all 0.22s var(--ease-out);
}
.hist-item:hover {
  border-color: var(--color-primary-light);
  background: var(--color-bg-card);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.hist-score {
  flex-shrink: 0;
  width: 58px;
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 1px;
}
.hist-score-num {
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: -1px;
  font-feature-settings: "tnum" on;
}
.hist-score-cap {
  font-size: 0.85rem;
  font-weight: 600;
  opacity: 0.7;
}

.hist-info {
  flex: 1;
  min-width: 0;
}
.hist-job {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.2px;
  margin-bottom: 7px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hist-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.hist-tag {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
}
.hist-tag.chat { background: var(--color-primary-soft); color: var(--color-primary); }
.hist-tag.upload { background: #ECFEFF; color: var(--color-accent); }
.hist-tag.edit { background: #FEF3C7; color: #B45309; }
.hist-grade { font-size: 0.88rem; font-weight: 600; color: var(--color-text-secondary); }
.hist-date { font-size: 0.85rem; color: var(--color-text-muted); }

.hist-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.hist-open {
  padding: 8px 18px;
  font-size: 0.98rem;
  font-weight: 600;
  color: #fff;
  background: var(--gradient-primary);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-primary);
  transition: all 0.2s var(--ease-out);
}
.hist-open:hover { transform: translateY(-1px); box-shadow: var(--shadow-primary-strong); }
.hist-del {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border-light);
  transition: all 0.2s var(--ease-out);
}
.hist-del:hover {
  color: var(--color-danger);
  border-color: var(--color-danger);
  background: var(--color-danger-soft);
}
</style>
