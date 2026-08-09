<template>
  <div class="result-workbench">
    <!-- 顶部栏 -->
    <header class="topbar no-print">
      <button class="back-btn" @click="goHome">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
        <span>首页</span>
      </button>
      <span class="brand-name">识光简历</span>
      <div class="topbar-right">
        <router-link to="/dashboard" class="ghost-btn accent">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <span>求职加速</span>
        </router-link>
        <button class="ghost-btn" @click="onPrint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="6 9 6 2 18 2 18 9"/>
            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
            <rect x="6" y="14" width="12" height="8"/>
          </svg>
          <span>导出 PDF</span>
        </button>
      </div>
    </header>

    <!-- 主体：左右分栏 -->
    <main class="workbench-main">
      <!-- 左侧：简历预览 -->
      <section class="resume-panel" ref="resumePanelRef">
        <ResumePreview
          :resume="resume"
          :highlights="activeHighlights"
          :editable="true"
          @highlight-click="onHighlightClick"
          @edit-experience="onEditExperience"
        />
      </section>

      <!-- 右侧：诊断面板 -->
      <aside class="diagnostic-panel">
        <!-- "简历已修改"提示条 -->
        <div v-if="resumeDirty && !reEvaluating" class="dirty-banner no-print">
          <div class="db-left">
            <span class="db-dot"></span>
            <div class="db-text">
              <strong>简历已修改</strong>
              <span>当前分数为修改前结果</span>
            </div>
          </div>
          <button class="db-btn" @click="reEvaluateNow">立即重评</button>
        </div>

        <!-- 重评中 loading -->
        <div v-if="reEvaluating" class="dirty-banner reeval-loading no-print">
          <span class="loader-dot"></span>
          <span>正在重新评定简历质量...</span>
        </div>

        <!-- 综合评分卡片 -->
        <div class="score-card" v-if="report" :class="{ 'is-dirty': resumeDirty }">
          <div class="score-main">
            <span class="score-num" :style="{ color: report.grade_color }">{{ report.total_score }}</span>
            <div class="score-meta">
              <span class="score-label">简历质量分</span>
              <span class="score-grade" :style="{ color: report.grade_color }">{{ report.grade }}{{ gradeGapText }}</span>
            </div>
          </div>
          <div class="score-mini" v-if="report.dimensions">
            <div v-for="d in topDimensions" :key="d.name" class="mini-dim">
              <div class="mini-dim-head">
                <span class="mini-dim-name">{{ d.name }}</span>
                <span class="mini-dim-score">{{ d.score }}</span>
              </div>
              <div class="mini-dim-bar">
                <div class="mini-dim-fill" :style="{ width: d.score + '%' }"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tab 切换 -->
        <div class="panel-tabs">
          <button
            :class="['panel-tab', { active: diagnosticTab === 'improvements' }]"
            @click="diagnosticTab = 'improvements'"
          >
            优化建议
          </button>
          <button
            :class="['panel-tab', { active: diagnosticTab === 'details' }]"
            @click="diagnosticTab = 'details'"
          >
            详细分析
          </button>
        </div>

        <!-- 优化建议列表 -->
        <div class="improvements-list" v-if="diagnosticTab === 'improvements' && report">
          <div class="im-section-label">关键改进</div>
          <div
            v-for="(im, i) in report.improvements"
            :key="i"
            :class="['im-card', { focused: focusedImprovement === i }]"
            @click="focusImprovement(i)"
          >
            <div class="im-card-head">
              <span class="im-dim-tag">{{ im.title }}</span>
              <span class="im-score-badge">{{ im.score }} 分</span>
            </div>
            <p class="im-desc">{{ im.desc }}</p>
            <div v-if="im.actions && im.actions.length" class="im-actions">
              <div
                v-for="(a, j) in im.actions"
                :key="j"
                class="im-action-card"
              >
                <div v-if="actionOriginal(a)" class="im-action-original">
                  <span class="im-action-label">原文</span>
                  <span class="im-action-original-text">{{ actionOriginal(a) }}</span>
                </div>
                <div class="im-action-suggestion">
                  <span class="im-action-label im-action-label-suggest">{{ actionOriginal(a) ? '改写' : '建议' }}</span>
                  <span class="im-action-suggestion-text">{{ actionSuggestion(a) }}</span>
                </div>
                <div v-if="actionReason(a)" class="im-action-reason">
                  <span class="im-action-reason-dot">▸</span>
                  <span>{{ actionReason(a) }}</span>
                </div>
                <div class="im-action-foot">
                  <button
                    v-if="canApplyAction(im, a) || appliedKey === `im-${i}-${j}`"
                    class="im-apply-btn"
                    :class="{ applied: appliedKey === `im-${i}-${j}` }"
                    @click.stop="applyActionToResume(im, a, `im-${i}-${j}`)"
                    :disabled="appliedKey === `im-${i}-${j}`"
                  >
                    {{ appliedKey === `im-${i}-${j}` ? '✓ 已应用到简历' : '一键应用到简历' }}
                  </button>
                  <button
                    class="im-copy-btn im-copy-btn-card"
                    :class="{ copied: copiedKey === `im-${i}-${j}` }"
                    @click.stop="copyText(actionSuggestion(a), `im-${i}-${j}`)"
                  >
                    {{ copiedKey === `im-${i}-${j}` ? '✓ 已复制' : '复制改写' }}
                  </button>
                </div>
              </div>
            </div>
            <button
              v-if="matchedExpForImprovement(im)"
              class="im-edit-btn"
              @click.stop="openEditForImprovement(im, i)"
            >
              修改此项
            </button>
            <button
              v-else
              class="im-edit-btn im-edit-btn-disabled"
              @click.stop="focusImprovement(i)"
              :title="focusedImprovement === i ? '已聚焦,但未匹配到具体段落' : '点击聚焦到简历相关位置'"
            >
              {{ focusedImprovement === i ? '已聚焦' : '聚焦此项' }}
            </button>
          </div>

          <div class="im-section-label">锦上添花</div>
          <div
            v-for="(h, i) in (report.highlights || [])"
            :key="'hl-' + i"
            class="im-card hl-card"
          >
            <div class="im-card-head">
              <span class="im-dim-tag hl-tag">{{ h.title }}</span>
              <span class="im-score-badge hl-score">{{ h.score }} 分</span>
            </div>
            <p class="im-desc">{{ h.desc }}</p>
          </div>
        </div>

        <!-- 详细分析 -->
        <div class="details-view" v-if="diagnosticTab === 'details' && report">
          <!-- 雷达图 -->
          <div class="radar-wrap">
            <v-chart class="radar-chart" :option="radarOption" autoresize />
          </div>

          <!-- 维度解读 -->
          <div class="dim-details">
            <div v-for="d in report.dimensions" :key="d.name" class="dim-detail-item">
              <div class="dd-head">
                <span class="dd-name">{{ d.name }}</span>
                <span class="dd-score" :class="scoreLevel(d.score)">{{ d.score }} / {{ d.max }}</span>
              </div>
              <div class="dd-bar">
                <div class="dd-bar-fill" :class="scoreLevel(d.score)" :style="{ width: d.score + '%' }"></div>
              </div>
              <p class="dd-desc">{{ d.desc }}</p>
            </div>
          </div>

          <!-- 行动指南 -->
          <div class="action-guide" v-if="report.action_guide">
            <p>{{ report.action_guide }}</p>
          </div>

          <!-- 诚信声明 -->
          <div class="integrity" v-if="report.integrity_statement">
            <p>{{ report.integrity_statement }}</p>
          </div>
        </div>
      </aside>
    </main>

    <!-- 编辑经历弹窗 -->
    <ExperienceEditDialog
      :exp="editingExp"
      @close="editingExp = null"
      @save="onSaveExperience"
    />

    <!-- 重新评定询问弹窗 -->
    <ReEvaluateDialog
      :open="showReEvalDialog"
      :exp-title="lastEditedTitle"
      @confirm="onReEvalConfirm"
      @later="onReEvalLater"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import ResumePreview from '@/components/ResumePreview.vue'
import ExperienceEditDialog from '@/components/ExperienceEditDialog.vue'
import ReEvaluateDialog from '@/components/ReEvaluateDialog.vue'
import { resumeApi, sessionApi } from '@/api'
import { downloadResumePdf } from '@/api/backend'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { RadarChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import VChart from 'vue-echarts'

use([CanvasRenderer, RadarChart, TooltipComponent, LegendComponent, TitleComponent])

const router = useRouter()
const store = useChatStore()
const auth = useAuthStore()
const { resumeDirty, reEvaluating } = storeToRefs(store)

const resumePanelRef = ref(null)
const diagnosticTab = ref('improvements')
const focusedImprovement = ref(-1)
const copiedKey = ref('')          // 当前被点击"复制"的 key,用于切换按钮文案
const appliedKey = ref('')         // 当前被"一键应用"的 key
let copyTimer = null
let appliedTimer = null

// 编辑/重评相关
const editingExp = ref(null)
const showReEvalDialog = ref(false)
const lastEditedTitle = ref('')

const resume = computed(() => store.resumeData)
const report = computed(() => store.qualityReport)

// 距下一档还差多少分。阈值与后端 evaluation_service._grade_of 对应,
// 已是最高档时不再显示"距卓越还差 N 分"。
const gradeGapText = computed(() => {
  const score = report.value?.total_score
  if (typeof score !== 'number') return ''
  const tiers = [
    { min: 82, label: '卓越' },
    { min: 68, label: '优秀' },
    { min: 52, label: '良好' },
    { min: 35, label: '合格' },
  ]
  const next = [...tiers].reverse().find((t) => score < t.min)
  return next ? ` · 距${next.label}还差 ${next.min - score} 分` : ''
})

const topDimensions = computed(() => {
  if (!report.value?.dimensions) return []
  return report.value.dimensions.slice(0, 3)
})

const activeHighlights = computed(() => {
  if (focusedImprovement.value < 0 || !report.value?.improvements) return []
  return [report.value.improvements[focusedImprovement.value]]
})

const radarOption = computed(() => {
  if (!report.value?.dimensions) return {}
  return {
    tooltip: {
      backgroundColor: 'rgba(17, 24, 39, 0.9)',
      borderColor: 'rgba(37, 99, 235, 0.3)',
      textStyle: { color: '#F9FAFB', fontSize: 12 }
    },
    radar: {
      indicator: report.value.dimensions.map(d => ({ name: d.name, max: d.max })),
      radius: '65%',
      splitNumber: 4,
      axisName: { color: '#4B5563', fontSize: 12, fontWeight: 600 },
      splitLine: { lineStyle: { color: 'rgba(37, 99, 235, 0.10)' } },
      splitArea: {
        areaStyle: {
          color: ['rgba(37, 99, 235, 0.02)', 'rgba(37, 99, 235, 0.05)', 'rgba(37, 99, 235, 0.08)', 'rgba(37, 99, 235, 0.10)']
        }
      },
      axisLine: { lineStyle: { color: 'rgba(37, 99, 235, 0.15)' } }
    },
    series: [{
      type: 'radar',
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2, color: '#2563EB' },
      itemStyle: { color: '#2563EB' },
      areaStyle: {
        color: {
          type: 'radial', x: 0.5, y: 0.5, r: 0.65,
          colorStops: [
            { offset: 0, color: 'rgba(37, 99, 235, 0.35)' },
            { offset: 1, color: 'rgba(8, 145, 178, 0.10)' }
          ]
        }
      },
      data: [{ value: report.value.dimensions.map(d => d.score), name: '当前简历' }]
    }]
  }
})

onMounted(async () => {
  if (!resume.value || !report.value) {
    await restoreLatestResume()
    if (!store.resumeData || !store.qualityReport) {
      router.replace('/')
    }
  }
})

async function restoreLatestResume() {
  if (!auth.isLoggedIn) return false
  try {
    const data = await sessionApi.latest()
    const session = data?.session
    const latestResume = data?.latest_resume
    if (!latestResume?.resume || !latestResume?.quality_report) return false

    const messages = Array.isArray(session?.messages)
      ? session.messages.map((m, idx) => ({
          role: m.role === 'assistant' ? 'ai' : m.role,
          text: m.content || '',
          ts: Date.now() + idx,
          streaming: false
        }))
      : []

    store.hydrate({
      sessionId: session?.session_id || latestResume.session_id || '',
      targetJob: session?.target_job || latestResume.target_job || '',
      currentStage: session?.stage || 'ready_to_generate',
      messages,
      extractedProfile: session?.extracted || {},
      resumeData: latestResume.resume,
      qualityReport: latestResume.quality_report
    })
    return true
  } catch {
    return false
  }
}

function focusImprovement(idx) {
  focusedImprovement.value = focusedImprovement.value === idx ? -1 : idx
}

function onHighlightClick() {
  focusedImprovement.value = -1
}

/**
 * 根据 improvement 找到对应经历
 * 匹配优先级:
 *  1. target_exp_id 精准命中
 *  2. evidence(后端返回的"评分原因/原文片段")子串扫描 experiences 的 bullets/title
 *  3. action.original 扫描 bullets
 *  4. title/desc 双向模糊匹配(去除"校"/"我的"等常见前缀)
 */
function matchedExpForImprovement(im) {
  if (!im || !resume.value?.experiences) return null
  const list = resume.value.experiences

  // 1. target_exp_id 精准命中
  if (im.target_exp_id) {
    const hit = list.find(e => e.id === im.target_exp_id)
    if (hit) return hit
  }

  // 2. evidence 子串扫描
  const evidence = (im.evidence || '').trim()
  if (evidence) {
    const hit = list.find(e => {
      if (!e) return false
      if (e.title && evidence.includes(e.title)) return true
      if (Array.isArray(e.bullets)) {
        return e.bullets.some(b => b && (b.includes(evidence) || evidence.includes(b)))
      }
      return false
    })
    if (hit) return hit
  }

  // 3. action.original 扫描 bullets
  if (Array.isArray(im.actions)) {
    for (const a of im.actions) {
      const orig = (a && typeof a === 'object' ? a.original : '') || ''
      if (!orig.trim()) continue
      const hit = list.find(e =>
        Array.isArray(e.bullets) && e.bullets.some(b => b && (b.includes(orig) || orig.includes(b)))
      )
      if (hit) return hit
    }
  }

  // 4. title/desc 双向模糊匹配
  const text = ((im.desc || '') + ' ' + (im.title || '')).trim()
  if (!text) return null
  const stripPrefix = s => (s || '').replace(/^(校|我的|本人|公司|学校|大学)/, '')
  return list.find(e => {
    if (!e?.title) return false
    const t = e.title
    const tStripped = stripPrefix(t)
    if (text.includes(t)) return true
    if (tStripped && text.includes(tStripped)) return true
    return false
  }) || null
}

/**
 * action 兼容字符串与 {original, suggestion, reason} 对象两种格式
 */
function actionOriginal(a) {
  if (!a) return ''
  if (typeof a === 'string') return ''
  return (a.original || '').trim()
}
function actionSuggestion(a) {
  if (!a) return ''
  if (typeof a === 'string') return a
  return a.suggestion || ''
}
function actionReason(a) {
  if (!a || typeof a === 'string') return ''
  return a.reason || ''
}

/**
 * 是否允许"一键应用":需要原文 + 改写 + 能匹配到经历且原文确实出现在该经历的某条 bullet 中
 */
function canApplyAction(im, a) {
  const orig = actionOriginal(a)
  const sug = actionSuggestion(a)
  if (!orig || !sug) return false
  const exp = matchedExpForImprovement(im)
  if (!exp || !Array.isArray(exp.bullets)) return false
  return exp.bullets.some(b => b && (b.includes(orig) || orig.includes(b)))
}

/**
 * 一键应用:把匹配到的 bullet 替换为 suggestion,标记简历为 dirty
 */
function applyActionToResume(im, a, key) {
  const orig = actionOriginal(a)
  const sug = actionSuggestion(a)
  if (!orig || !sug) return
  const exp = matchedExpForImprovement(im)
  if (!exp || !Array.isArray(exp.bullets)) return

  const idx = exp.bullets.findIndex(b => b && (b.includes(orig) || orig.includes(b)))
  if (idx === -1) return

  const newBullets = exp.bullets.slice()
  newBullets[idx] = sug
  store.updateExperience(exp.id, { bullets: newBullets })

  // 视觉反馈
  if (key) {
    appliedKey.value = key
    if (appliedTimer) clearTimeout(appliedTimer)
    appliedTimer = setTimeout(() => {
      appliedKey.value = ''
      appliedTimer = null
    }, 2400)
  }
}

/**
 * 点击 improvement 卡片的"修改此项"按钮 —— 聚焦 + 打开编辑弹窗
 */
function openEditForImprovement(im, idx) {
  focusedImprovement.value = idx
  const exp = matchedExpForImprovement(im)
  if (exp) {
    editingExp.value = { ...exp }
  }
}

/**
 * 用户点击简历区"编辑"按钮
 */
function onEditExperience(exp) {
  editingExp.value = { ...exp }
}

/**
 * 编辑弹窗 -> 保存
 */
function onSaveExperience(patch) {
  if (!editingExp.value) return
  const expId = editingExp.value.id
  store.updateExperience(expId, patch)
  lastEditedTitle.value = patch.title || editingExp.value.title || ''
  editingExp.value = null
  // 立刻弹出重评询问
  showReEvalDialog.value = true
}

/**
 * 重评弹窗 -> 立即重评
 */
async function onReEvalConfirm() {
  showReEvalDialog.value = false
  await triggerReEvaluate()
}

/**
 * 重评弹窗 -> 稍后重评 (保留 dirty 标记)
 */
function onReEvalLater() {
  showReEvalDialog.value = false
  // resumeDirty 已经在 store.updateExperience 里设置好了
}

/**
 * 顶部 banner 上"立即重评"按钮直接调用
 */
async function reEvaluateNow() {
  await triggerReEvaluate()
}

/**
 * 真正调用后端 / mock 做重新评定
 */
async function triggerReEvaluate() {
  if (!resume.value) return
  store.setReEvaluating(true)
  try {
    // 直接用当前简历对象重评,保留 exp_id —— 避免走"上传文本"管线导致 evidence/exp_id 错位
    const { qualityReport: newReport, savedResumeId } = await resumeApi.reevaluate({
      resume: resume.value,
      targetJob: resume.value?.basic?.target_job || store.targetJob,
      sessionId: store.sessionId
    })
    if (newReport) {
      store.applyNewQualityReport(newReport)
      auth.addResumeToHistory({
        savedResumeId,
        sessionId: store.sessionId,
        targetJob: resume.value?.basic?.target_job || store.targetJob || '未命名简历',
        score: newReport?.total_score ?? null,
        grade: newReport?.grade || '',
        gradeColor: newReport?.grade_color || '',
        source: 'edit',
        resume: resume.value,
        qualityReport: newReport
      })
    }
  } catch (e) {
    alert('重新评定失败,请稍后再试')
  } finally {
    store.setReEvaluating(false)
  }
}

/**
 * 复制 + 给点击按钮添加"✓ 已复制"反馈,2 秒后还原
 */
function copyText(text, key) {
  if (!text) return
  try {
    navigator.clipboard.writeText(text)
  } catch (e) {
    // clipboard write failed silently
  }
  if (key) {
    copiedKey.value = key
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      copiedKey.value = ''
      copyTimer = null
    }, 1800)
  }
}

function scoreLevel(score) {
  // 阈值与后端 evaluation_service._grade_of 保持一致
  if (score >= 82) return 'excellent'
  if (score >= 68) return 'good'
  if (score >= 52) return 'pass'
  return 'warn'
}

function onPrint() {
  if (store.currentResumeId) {
    downloadResumePdf(store.currentResumeId)
  } else {
    // 兜底：没有数据库 ID 时回退到浏览器打印
    window.print()
  }
}

function goHome() {
  store.reset()
  router.push('/')
}
</script>

<style scoped>
.result-workbench {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  overflow: hidden;
}

/* ============ 顶部栏 ============ */
.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(14px) saturate(180%);
  -webkit-backdrop-filter: blur(14px) saturate(180%);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  z-index: 10;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  transition: all 0.2s var(--ease-out);
}

.back-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
}

.brand-name {
  flex: 1;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.2px;
}

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 600;
  transition: all 0.25s var(--ease-out);
  box-shadow: var(--shadow-primary);
}

.ghost-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

.ghost-btn.accent {
  background: transparent;
  color: var(--color-primary);
  border: 1.5px solid var(--color-primary);
  box-shadow: none;
  margin-right: 8px;
}
.ghost-btn.accent:hover {
  background: var(--color-primary-soft);
  box-shadow: none;
  transform: translateY(-1px);
}

/* ============ 主体分栏 ============ */
.workbench-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ============ 左侧简历 ============ */
.resume-panel {
  flex: 7;
  min-width: 0;
  overflow-y: auto;
  padding: 28px 24px;
  background:
    radial-gradient(ellipse 80% 50% at 50% 0%, rgba(37, 99, 235, 0.04), transparent 70%),
    var(--color-bg);
}

/* ============ 右侧诊断面板 ============ */
.diagnostic-panel {
  flex: 3;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-card);
  border-left: 1px solid var(--color-border-light);
  overflow-y: auto;
  box-shadow: -1px 0 0 rgba(15, 23, 42, 0.02);
}

/* 评分卡片 */
.score-card {
  padding: 26px 24px 22px;
  border-bottom: 1px solid var(--color-border-light);
  background:
    radial-gradient(ellipse 60% 80% at 100% 0%, rgba(37, 99, 235, 0.08), transparent 60%),
    linear-gradient(180deg, var(--color-bg-card), var(--color-bg-subtle));
}

.score-main {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 22px;
}

.score-num {
  font-size: 5.5rem;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -3px;
  font-feature-settings: "tnum" on;
}

.score-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.score-label {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.2px;
}

.score-grade {
  font-size: 1.15rem;
  font-weight: 600;
}

.score-mini {
  display: flex;
  flex-direction: column;
  gap: 11px;
}

.mini-dim-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
}

.mini-dim-name {
  font-size: 1.1rem;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.mini-dim-score {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text);
  font-feature-settings: "tnum" on;
}

.mini-dim-bar {
  height: 5px;
  background: var(--color-border-light);
  border-radius: 3px;
  overflow: hidden;
}

.mini-dim-fill {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 3px;
  transition: width 0.8s var(--ease-out);
}

/* Tab 切换 */
.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--color-border-light);
  background: var(--color-bg-card);
  position: sticky;
  top: 0;
  z-index: 2;
}

.panel-tab {
  flex: 1;
  padding: 14px;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--color-text-muted);
  text-align: center;
  transition: all 0.2s var(--ease-out);
  border-bottom: 2px solid transparent;
  position: relative;
}

.panel-tab:hover {
  color: var(--color-text-secondary);
}

.panel-tab.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

/* 优化建议列表 */
.improvements-list {
  flex: 1;
  padding: 18px;
  overflow-y: auto;
}

.im-section-label {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 12px;
  margin-top: 4px;
}

.im-section-label + .im-section-label,
.im-card + .im-section-label {
  margin-top: 18px;
}

.im-card {
  padding: 16px;
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  margin-bottom: 10px;
  cursor: pointer;
  transition: all 0.25s var(--ease-out);
  background: var(--color-bg-card);
}

.im-card:hover {
  border-color: var(--color-border);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.im-card.focused {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.10);
}

.im-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.im-dim-tag {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.1px;
}

.im-score-badge {
  font-size: 0.95rem;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: var(--color-warning-soft);
  color: #92400E;
  font-weight: 700;
}

.im-desc {
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  line-height: 1.65;
  margin-bottom: 10px;
}

.im-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 10px;
}

.im-action-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-light);
  border-left: 3px solid var(--color-primary-light);
  border-radius: var(--radius-sm);
  font-size: 1.1rem;
  color: var(--color-text-secondary);
  line-height: 1.55;
  position: relative;
}

.im-action-card:hover {
  border-color: var(--color-border);
  border-left-color: var(--color-primary);
}

.im-action-original,
.im-action-suggestion {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.im-action-label {
  flex-shrink: 0;
  display: inline-block;
  padding: 1px 8px;
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--color-text-muted);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-xs);
  letter-spacing: 0.2px;
  margin-top: 2px;
}

.im-action-label-suggest {
  color: var(--color-primary);
  background: var(--color-primary-soft);
  border-color: var(--color-primary-light);
}

.im-action-original-text {
  flex: 1;
  color: var(--color-text-muted);
  text-decoration: line-through;
  text-decoration-color: rgba(148, 163, 184, 0.45);
  text-decoration-thickness: 1px;
}

.im-action-suggestion-text {
  flex: 1;
  color: var(--color-text);
  font-weight: 500;
}

.im-action-reason {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 0.95rem;
  color: var(--color-text-muted);
  font-style: italic;
  padding-left: 2px;
}

.im-action-reason-dot {
  color: var(--color-primary);
  font-weight: 700;
  flex-shrink: 0;
}

.im-copy-btn-card {
  align-self: flex-end;
  margin-top: 2px;
}

.im-action-foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 2px;
}

.im-apply-btn {
  padding: 5px 14px;
  font-size: 0.95rem;
  font-weight: 700;
  color: white;
  background: var(--gradient-primary);
  border-radius: var(--radius-xs);
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  transition: all 0.2s var(--ease-out);
  letter-spacing: 0.2px;
}

.im-apply-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(37, 99, 235, 0.35);
}

.im-apply-btn.applied {
  background: var(--color-success, #10B981);
  box-shadow: 0 2px 6px rgba(16, 185, 129, 0.30);
  cursor: default;
}

.im-apply-btn:disabled {
  cursor: default;
}

.im-copy-btn {
  padding: 4px 12px;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--color-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  background: var(--color-bg-card);
  transition: all 0.2s var(--ease-out);
}

.im-copy-btn:hover {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.im-edit-btn {
  width: 100%;
  padding: 8px;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--color-primary);
  border: 1px dashed var(--color-primary-light);
  border-radius: var(--radius-sm);
  background: transparent;
  transition: all 0.2s var(--ease-out);
}

.im-edit-btn:hover {
  background: var(--color-primary);
  color: white;
  border-style: solid;
  border-color: var(--color-primary);
}

.im-edit-btn-disabled {
  color: var(--color-text-muted);
  border-color: var(--color-border);
  background: var(--color-bg-subtle);
}

.im-edit-btn-disabled:hover {
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}

.im-copy-btn.copied {
  background: var(--color-success, #10B981);
  color: white;
  border-color: var(--color-success, #10B981);
}

.im-copy-btn.copied:hover {
  background: var(--color-success, #10B981);
  color: white;
  border-color: var(--color-success, #10B981);
}

/* ============ 简历已修改 banner ============ */
.dirty-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 14px 16px 0;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: linear-gradient(90deg, rgba(245, 158, 11, 0.16), rgba(245, 158, 11, 0.06));
  border: 1px solid rgba(245, 158, 11, 0.30);
  animation: bannerSlideIn 0.35s var(--ease-out);
}

@keyframes bannerSlideIn {
  from { opacity: 0; transform: translateY(-6px); }
  to   { opacity: 1; transform: translateY(0); }
}

.db-left {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.db-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-warning);
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.20);
  animation: pulseDot 1.6s infinite;
  flex-shrink: 0;
}

@keyframes pulseDot {
  0%, 100% { box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.20); }
  50%      { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0.32); }
}

.db-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  font-size: 0.98rem;
  color: #92400E;
  line-height: 1.4;
}

.db-text strong {
  font-weight: 700;
}

.db-btn {
  padding: 6px 14px;
  font-size: 0.95rem;
  font-weight: 700;
  color: white;
  background: var(--color-warning);
  border-radius: var(--radius-sm);
  white-space: nowrap;
  transition: all 0.2s var(--ease-out);
  box-shadow: 0 2px 6px rgba(245, 158, 11, 0.30);
}

.db-btn:hover {
  background: #D97706;
  transform: translateY(-1px);
  box-shadow: 0 4px 10px rgba(245, 158, 11, 0.40);
}

.dirty-banner.reeval-loading {
  justify-content: flex-start;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.10), rgba(37, 99, 235, 0.04));
  border-color: rgba(37, 99, 235, 0.25);
  color: var(--color-primary-dark);
  font-size: 0.98rem;
  font-weight: 600;
}

.loader-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-primary);
  position: relative;
}

.loader-dot::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--color-primary);
  opacity: 0.5;
  animation: loaderPulse 1s infinite;
}

@keyframes loaderPulse {
  0%   { transform: scale(1);   opacity: 0.5; }
  100% { transform: scale(2.4); opacity: 0; }
}

.score-card.is-dirty {
  opacity: 0.7;
  filter: grayscale(15%);
  transition: opacity 0.3s, filter 0.3s;
}

/* 亮点卡片 */
.hl-card {
  border-left: 3px solid var(--color-success);
  background: linear-gradient(90deg, rgba(5, 150, 105, 0.04), transparent 30%);
}

.hl-tag {
  color: var(--color-success);
}

.hl-score {
  background: var(--color-success-soft);
  color: #065F46;
}

/* ============ 详细分析 ============ */
.details-view {
  flex: 1;
  padding: 18px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.radar-wrap {
  background: linear-gradient(135deg, var(--color-bg-subtle), var(--color-bg));
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: 10px;
  flex-shrink: 0;
}

.radar-chart {
  width: 100%;
  height: 280px;
}

.dim-details {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex-shrink: 0;
}

.dim-detail-item {
  padding: 14px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  transition: border-color 0.2s var(--ease-out);
}

.dim-detail-item:hover {
  border-color: var(--color-border);
}

.dd-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.dd-name {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.1px;
}

.dd-score {
  font-size: 1.15rem;
  font-weight: 800;
  font-feature-settings: "tnum" on;
}

.dd-score.excellent { color: var(--color-success); }
.dd-score.good { color: var(--color-primary); }
.dd-score.pass { color: var(--color-warning); }
.dd-score.warn { color: var(--color-danger); }

.dd-bar {
  height: 6px;
  background: var(--color-border-light);
  border-radius: 3px;
  overflow: hidden;
  margin-bottom: 8px;
}

.dd-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.8s var(--ease-out);
}

.dd-bar-fill.excellent { background: linear-gradient(90deg, var(--color-success), #34D399); }
.dd-bar-fill.good { background: var(--gradient-primary); }
.dd-bar-fill.pass { background: linear-gradient(90deg, var(--color-warning), #FBBF24); }
.dd-bar-fill.warn { background: linear-gradient(90deg, var(--color-danger), #F87171); }

.dd-desc {
  font-size: 1.1rem;
  color: var(--color-text-muted);
  line-height: 1.55;
}

.action-guide {
  padding: 18px 20px;
  background: var(--gradient-primary);
  color: white;
  border-radius: var(--radius-md);
  font-size: 1.25rem;
  font-weight: 500;
  line-height: 1.6;
  box-shadow: var(--shadow-primary);
  position: relative;
  overflow: hidden;
  flex-shrink: 0;
}

.action-guide::before {
  content: '';
  position: absolute;
  top: -30px;
  right: -30px;
  width: 120px;
  height: 120px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.18), transparent 70%);
  border-radius: 50%;
}

.action-guide p {
  position: relative;
  z-index: 1;
}

.integrity {
  padding: 14px 16px;
  background: var(--color-bg-subtle);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  font-size: 1.1rem;
  color: var(--color-text-muted);
  line-height: 1.6;
  flex-shrink: 0;
}

/* ============ 响应式 ============ */
@media (max-width: 1024px) {
  .workbench-main {
    flex-direction: column;
  }
  .diagnostic-panel {
    width: 100%;
    max-height: 45vh;
    border-left: none;
    border-top: 1px solid var(--color-border-light);
  }
}
</style>
