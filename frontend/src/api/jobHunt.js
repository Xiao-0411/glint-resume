/**
 * 求职加速 Mock API
 */
import {
  mockJobSearch, mockAdaptResume, mockApplyJob,
  mockGetApplications, mockUpdateApplicationStatus
} from './mock'
import {
  jobSearch, adaptResume, applyJob,
  getApplications, updateApplicationStatus
} from './backend'

const USE_BACKEND = import.meta.env.VITE_USE_BACKEND === 'true'

export const jobHuntApi = {
  search: (payload) => USE_BACKEND
    ? jobSearch(payload)
    : mockJobSearch(payload),

  adapt: (payload) => USE_BACKEND
    ? adaptResume(payload)
    : mockAdaptResume(payload),

  apply: (payload) => USE_BACKEND
    ? applyJob(payload)
    : mockApplyJob(payload),

  getApplications: () => USE_BACKEND
    ? getApplications()
    : mockGetApplications(),

  updateApplicationStatus: (payload) => USE_BACKEND
    ? updateApplicationStatus(payload)
    : mockUpdateApplicationStatus(payload)
}
