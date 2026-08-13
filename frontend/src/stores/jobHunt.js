import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 求职加速 —— 职位搜索、匹配分级、投递追踪状态管理
 */
export const useJobHuntStore = defineStore('jobHunt', () => {
  // ---- 职位搜索 ----
  const searchKeyword = ref('')
  const searchResults = ref([])       // 原始搜索结果
  const matchedJobs = ref([])         // 匹配分级后的结果 { id, title, company, salary, location, matchLevel, matchScore, reasons, missingSkills, adapted }
  const searchLoading = ref(false)

  // ---- 投递记录 ----
  const applications = ref([])        // { id, jobId, jobTitle, company, resumeVersion, appliedAt, status, statusHistory }

  // ---- 统计 ----
  const stats = ref({
    total: 0,
    screened: 0,
    interviewing: 0,
    offered: 0,
    rejected: 0
  })

  // ---- 简历适配 ----
  const adaptingJobId = ref(null)
  const adaptedResumes = ref({})      // jobId -> { originalScore, adaptedScore, html }

  // ---- Getters ----
  const conversionRates = computed(() => {
    const t = stats.value.total
    if (t === 0) return { screened: 0, interview: 0, offer: 0 }
    return {
      screened: Math.round((stats.value.screened / t) * 100),
      interview: Math.round((stats.value.interviewing / t) * 100),
      offer: Math.round((stats.value.offered / t) * 100)
    }
  })

  // ---- Actions ----
  function setSearchResults(jobs) {
    searchResults.value = jobs
  }

  function setMatchedJobs(jobs) {
    matchedJobs.value = jobs
  }

  function setSearchLoading(val) {
    searchLoading.value = val
  }

  function addApplication(app) {
    applications.value.unshift(app)
    recalcStats()
  }

  function updateApplicationStatus(appId, newStatus) {
    const app = applications.value.find(a => a.id === appId)
    if (!app) return
    const now = new Date().toISOString()
    if (!app.statusHistory) app.statusHistory = []
    app.statusHistory.push({ status: newStatus, at: now })
    app.status = newStatus
    app.updatedAt = now
    recalcStats()
  }

  function recalcStats() {
    const apps = applications.value
    stats.value = {
      total: apps.length,
      screened: apps.filter(a => ['screened', 'interviewing', 'offered', 'rejected'].includes(a.status)).length,
      interviewing: apps.filter(a => ['interviewing', 'offered'].includes(a.status)).length,
      offered: apps.filter(a => a.status === 'offered').length,
      rejected: apps.filter(a => a.status === 'rejected').length
    }
  }

  function setAdaptingJobId(jobId) {
    adaptingJobId.value = jobId
  }

  function saveAdaptedResume(jobId, data) {
    adaptedResumes.value[jobId] = data
  }

  function reset() {
    searchKeyword.value = ''
    searchResults.value = []
    matchedJobs.value = []
    searchLoading.value = false
    applications.value = []
    stats.value = { total: 0, screened: 0, interviewing: 0, offered: 0, rejected: 0 }
    adaptingJobId.value = null
    adaptedResumes.value = {}
  }

  return {
    searchKeyword, searchResults, matchedJobs, searchLoading,
    applications, stats, adaptingJobId, adaptedResumes,
    conversionRates,
    setSearchResults, setMatchedJobs, setSearchLoading,
    addApplication, updateApplicationStatus, recalcStats,
    setAdaptingJobId, saveAdaptedResume, reset
  }
})
