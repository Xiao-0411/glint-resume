/**
 * 求职加速 API。职位相关数据必须来自后端真实职位库/实时抓取。
 */
import {
  jobSearch, adaptResume, applyJob,
  getApplications, updateApplicationStatus, getCrawlerStatus
} from './backend'

export const jobHuntApi = {
  search: (payload) => jobSearch(payload),
  adapt: (payload) => adaptResume(payload),
  apply: (payload) => applyJob(payload),
  getApplications: () => getApplications(),
  updateApplicationStatus: (payload) => updateApplicationStatus(payload),
  getCrawlerStatus: () => getCrawlerStatus()
}
