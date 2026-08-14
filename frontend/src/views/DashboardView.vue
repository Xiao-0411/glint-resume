<template>
  <div class="dashboard">
    <!-- 主内容区 -->
    <main class="dashboard-main">
      <!-- Tab 导航 -->
      <nav class="tab-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-btn', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          <span class="tab-icon" aria-hidden="true">
            <svg v-if="tab.key === 'search'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <svg v-else-if="tab.key === 'tracker'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
          </span>
          <span class="tab-label">{{ tab.label }}</span>
          <span v-if="tab.badge" class="tab-badge">{{ tab.badge }}</span>
        </button>
      </nav>

      <!-- ========== Tab 1: 职位搜索与匹配 ========== -->
      <section v-if="activeTab === 'search'" class="tab-panel">
        <!-- 搜索栏 -->
        <div class="search-bar">
          <div class="search-input-wrap">
            <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              v-model="searchKeyword"
              class="search-input"
              type="text"
              :placeholder="'搜索职位、公司或技能...（默认匹配：' + (chatStore.targetJob || '产品经理') + '）'"
              @keydown.enter="onSearch"
            />
          </div>
          <button class="search-btn" @click="onSearch" :disabled="huntStore.searchLoading">
            {{ huntStore.searchLoading ? '搜索中...' : '搜索职位' }}
          </button>
        </div>

        <!-- 匹配分级图例 -->
        <div class="legend">
          <span class="legend-item"><span class="dot green"></span>高匹配 可直接投递</span>
          <span class="legend-item"><span class="dot yellow"></span>中匹配 建议微调适配</span>
          <span class="legend-item"><span class="dot red"></span>低匹配 暂不建议</span>
          <span class="legend-item"><span class="dot unknown"></span>匹配度未知 缺简历或岗位未列要求</span>
        </div>

        <!-- 匹配依据：如实说明分数怎么来的，不含糊其辞 -->
        <div v-if="matchBasisText" class="match-basis">{{ matchBasisText }}</div>

        <div v-if="crawlerStatuses.length" class="crawler-status-bar">
          <span class="crawler-status-title">数据渠道</span>
          <span v-for="item in crawlerStatuses" :key="item.platform" class="crawler-status-item">
            <span :class="['crawler-status-dot', item.status]"></span>
            {{ item.label }} {{ crawlerStatusLabel(item.status) }}
            <small v-if="item.lastJobCount">{{ item.lastJobCount }} 条</small>
          </span>
        </div>

        <!-- 无简历提示：可浏览职位，但投递 / 适配需先创建简历 -->
        <div v-if="!hasResume" class="no-resume-banner">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
          </svg>
          <span class="no-resume-text">你还没有简历，当前可自由浏览职位；<strong>创建简历后</strong>即可使用一键投递与 AI 适配。</span>
          <button class="no-resume-btn" @click="goCreateResume">去创建简历</button>
        </div>

        <!-- 加载 -->
        <div v-if="huntStore.searchLoading" class="loading-state">
          <div class="spinner"></div>
          <span>正在智能搜索匹配职位...</span>
        </div>

        <!-- 空态 -->
        <div v-else-if="huntStore.matchedJobs.length === 0" class="empty-state">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <p class="empty-text">{{ searchMessage }}</p>
        </div>

        <!-- 结果列表 -->
        <div v-else class="job-list">
          <div
            v-for="job in huntStore.matchedJobs"
            :key="job.id"
            :class="['job-card', 'match-' + job.matchLevel]"
            @click="onOpenJobDetail(job)"
          >
            <div class="job-body">
              <!-- 顶部：标题 + 匹配标签 + 薪资 -->
              <div class="job-top">
                <div class="job-top-left">
                  <h3 class="job-title">{{ job.title }}</h3>
                  <div class="job-meta">
                    <span class="job-company">{{ job.company }}</span>
                    <span class="job-sep">·</span>
                    <span class="job-location">{{ job.location }}</span>
                    <span v-for="tag in job.tags" :key="tag" class="job-tag">{{ tag }}</span>
                    <span v-if="job.platform" class="job-source">{{ platformLabel(job.platform) }}</span>
                  </div>
                </div>
                <div class="job-top-right">
                  <span :class="['match-tag', job.matchLevel]">
                    <span class="match-dot"></span>
                    {{ matchLabel(job) }}
                  </span>
                  <span class="job-salary">{{ job.salary }}</span>
                </div>
              </div>

              <p class="job-desc">{{ job.description }}</p>
              <div v-if="job.crawledAt || job.url" class="job-freshness">
                <span v-if="job.crawledAt">抓取于 {{ formatDateTime(job.crawledAt) }}</span>
                <a v-if="job.url" :href="job.url" target="_blank" rel="noopener noreferrer" @click.stop>查看原始职位</a>
              </div>

              <!-- 匹配理由 -->
              <div class="match-reason">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
                <span>{{ job.reasons }}</span>
              </div>

              <!-- 缺失技能 -->
              <div v-if="job.missingSkills?.length > 0" class="missing-skills">
                <span class="missing-label">待补足技能</span>
                <span v-for="sk in job.missingSkills" :key="sk" class="missing-tag">{{ sk }}</span>
              </div>

              <!-- 操作按钮 -->
              <div class="job-actions" @click.stop>
                <button
                  v-if="job.matchLevel === 'green'"
                  class="action-btn primary"
                  @click="onApplyJob(job, 'original')"
                  :disabled="appliedJobIds[job.id] || !hasResume"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                  </svg>
                  {{ appliedJobIds[job.id] ? '已投递' : '一键投递' }}
                </button>
                <template v-if="job.matchLevel === 'yellow'">
                  <button
                    class="action-btn secondary"
                    @click="onAdaptResume(job)"
                    :disabled="huntStore.adaptingJobId === job.id || !hasResume"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                    </svg>
                    {{ huntStore.adaptingJobId === job.id ? 'AI 适配中...' : 'AI 微调适配' }}
                  </button>
                  <button
                    v-if="huntStore.adaptedResumes[job.id]"
                    class="action-btn primary"
                    @click="onApplyJob(job, 'adapted')"
                    :disabled="appliedJobIds[job.id] || !hasResume"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                    </svg>
                    {{ appliedJobIds[job.id] ? '已投递' : '投递适配版' }}
                  </button>
                </template>
                <button v-if="job.matchLevel === 'red'" class="action-btn disabled-btn" disabled>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  暂不建议投递
                </button>
                <!-- 匹配度无法评估（没有简历 / JD 未列明要求）：
                     不做推荐，但也不能让这张卡片没有任何可操作项 -->
                <button
                  v-if="job.matchLevel === 'unknown'"
                  class="action-btn secondary"
                  @click="onApplyJob(job, 'original')"
                  :disabled="appliedJobIds[job.id] || !hasResume"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
                  </svg>
                  {{ appliedJobIds[job.id] ? '已投递' : (hasResume ? '仍要投递' : '请先创建简历') }}
                </button>
              </div>

              <!-- 适配结果对比 -->
              <div v-if="huntStore.adaptedResumes[job.id]" class="adapt-result">
                <div class="adapt-compare">
                  <span class="adapt-label">原简历</span>
                  <span class="adapt-score">{{ huntStore.adaptedResumes[job.id].originalScore }}分</span>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="adapt-arrow-icon">
                    <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
                  </svg>
                  <span class="adapt-label">适配版</span>
                  <span class="adapt-score up">{{ huntStore.adaptedResumes[job.id].adaptedScore }}分</span>
                </div>
                <div class="adapt-changes">
                  <span v-for="(ch, i) in huntStore.adaptedResumes[job.id].changes" :key="i" class="adapt-change-item">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                    {{ ch }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ========== Tab 2: 投递进度看板 ========== -->
      <section v-if="activeTab === 'tracker'" class="tab-panel">
        <!-- 转化漏斗 -->
        <div class="funnel-section">
          <div class="funnel-row">
            <div class="funnel-card">
              <div class="funnel-num">{{ huntStore.stats.total }}</div>
              <div class="funnel-label">总投递</div>
            </div>
            <div class="funnel-sep">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
            <div class="funnel-card" :class="{ active: huntStore.stats.screened > 0 }">
              <div class="funnel-num">{{ huntStore.stats.screened }}</div>
              <div class="funnel-label">通过筛选</div>
              <div class="funnel-rate">{{ huntStore.conversionRates.screened }}%</div>
            </div>
            <div class="funnel-sep">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
            <div class="funnel-card" :class="{ active: huntStore.stats.interviewing > 0 }">
              <div class="funnel-num">{{ huntStore.stats.interviewing }}</div>
              <div class="funnel-label">面试中</div>
              <div class="funnel-rate">{{ huntStore.conversionRates.interview }}%</div>
            </div>
            <div class="funnel-sep">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
            </div>
            <div class="funnel-card highlight" :class="{ active: huntStore.stats.offered > 0 }">
              <div class="funnel-num">{{ huntStore.stats.offered }}</div>
              <div class="funnel-label">Offer</div>
              <div class="funnel-rate">{{ huntStore.conversionRates.offer }}%</div>
            </div>
          </div>
        </div>

        <!-- Kanban 看板 -->
        <div class="kanban" v-if="huntStore.applications.length > 0">
          <div class="kanban-col">
            <div class="kanban-col-header col-applied">
              <span>已投递</span>
              <span class="kanban-count">{{ appsByStatus('applied').length }}</span>
            </div>
            <div class="kanban-cards">
              <div v-for="app in appsByStatus('applied')" :key="app.id" class="kanban-card">
                <div class="kc-title">{{ app.jobTitle }}</div>
                <div class="kc-company">{{ app.company }}</div>
                <div class="kc-meta">
                  <span class="kc-version">{{ app.resumeVersion === 'adapted' ? '适配版' : '原版' }}</span>
                  <span class="kc-date">{{ formatDate(app.appliedAt) }}</span>
                </div>
                <div class="kc-actions">
                  <button class="kc-btn" @click="onMoveStatus(app, 'screened')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    通过筛选
                  </button>
                  <button class="kc-btn danger" @click="onMoveStatus(app, 'rejected')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    未通过
                  </button>
                </div>
              </div>
              <div v-if="appsByStatus('applied').length === 0" class="kanban-empty">-</div>
            </div>
          </div>

          <div class="kanban-col">
            <div class="kanban-col-header col-screened">
              <span>通过筛选</span>
              <span class="kanban-count">{{ appsByStatus('screened').length }}</span>
            </div>
            <div class="kanban-cards">
              <div v-for="app in appsByStatus('screened')" :key="app.id" class="kanban-card">
                <div class="kc-title">{{ app.jobTitle }}</div>
                <div class="kc-company">{{ app.company }}</div>
                <div class="kc-meta">
                  <span class="kc-version">{{ app.resumeVersion === 'adapted' ? '适配版' : '原版' }}</span>
                  <span class="kc-date">{{ formatDate(app.appliedAt) }}</span>
                </div>
                <div class="kc-actions">
                  <button class="kc-btn" @click="onMoveStatus(app, 'interviewing')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    推进面试
                  </button>
                  <button class="kc-btn danger" @click="onMoveStatus(app, 'rejected')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    未通过
                  </button>
                </div>
              </div>
              <div v-if="appsByStatus('screened').length === 0" class="kanban-empty">-</div>
            </div>
          </div>

          <div class="kanban-col">
            <div class="kanban-col-header col-interviewing">
              <span>面试中</span>
              <span class="kanban-count">{{ appsByStatus('interviewing').length }}</span>
            </div>
            <div class="kanban-cards">
              <div v-for="app in appsByStatus('interviewing')" :key="app.id" class="kanban-card">
                <div class="kc-title">{{ app.jobTitle }}</div>
                <div class="kc-company">{{ app.company }}</div>
                <div class="kc-badge interviewing">面试中</div>
                <div class="kc-meta">
                  <span class="kc-date">{{ formatDate(app.appliedAt) }}</span>
                </div>
                <div class="kc-actions">
                  <button class="kc-btn success" @click="onMoveStatus(app, 'offered')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    获得 Offer
                  </button>
                  <button class="kc-btn danger" @click="onMoveStatus(app, 'rejected')">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    未通过
                  </button>
                </div>
              </div>
              <div v-if="appsByStatus('interviewing').length === 0" class="kanban-empty">-</div>
            </div>
          </div>

          <div class="kanban-col">
            <div class="kanban-col-header col-offered">
              <span>Offer</span>
              <span class="kanban-count">{{ appsByStatus('offered').length }}</span>
            </div>
            <div class="kanban-cards">
              <div v-for="app in appsByStatus('offered')" :key="app.id" class="kanban-card success-card">
                <div class="kc-title">{{ app.jobTitle }}</div>
                <div class="kc-company">{{ app.company }}</div>
                <div class="kc-badge offered">已获 Offer</div>
                <div class="kc-meta">
                  <span class="kc-date">{{ formatDate(app.appliedAt) }}</span>
                </div>
              </div>
              <div v-if="appsByStatus('offered').length === 0" class="kanban-empty">-</div>
            </div>
          </div>

          <div class="kanban-col">
            <div class="kanban-col-header col-rejected">
              <span>未通过</span>
              <span class="kanban-count">{{ appsByStatus('rejected').length }}</span>
            </div>
            <div class="kanban-cards">
              <div v-for="app in appsByStatus('rejected')" :key="app.id" class="kanban-card rejected-card">
                <div class="kc-title">{{ app.jobTitle }}</div>
                <div class="kc-company">{{ app.company }}</div>
                <div class="kc-reason">未通过筛选</div>
                <div class="kc-meta">
                  <span class="kc-date">{{ formatDate(app.appliedAt) }}</span>
                </div>
              </div>
              <div v-if="appsByStatus('rejected').length === 0" class="kanban-empty">-</div>
            </div>
          </div>
        </div>

        <!-- 空态 -->
        <div v-else class="empty-state">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
            <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
          </svg>
          <p class="empty-text">暂无投递记录</p>
          <p class="empty-hint">去「职位搜索」开始投递吧</p>
        </div>
      </section>

      <!-- ========== Tab 3: 质量归因分析 ========== -->
      <section v-if="activeTab === 'analytics'" class="tab-panel">
        <!-- 简历质量分卡片 -->
        <div class="qa-header" v-if="chatStore.qualityReport">
          <div class="qa-score-big">
            <div class="qa-score-ring" :style="{ '--pct': (chatStore.qualityReport.total_score / 100) }">
              <span class="qa-score-num" :style="{ color: chatStore.qualityReport.grade_color }">{{ chatStore.qualityReport.total_score }}</span>
            </div>
            <div class="qa-score-meta">
              <span class="qa-grade" :style="{ color: chatStore.qualityReport.grade_color }">{{ chatStore.qualityReport.grade }}</span>
              <span class="qa-desc">当前简历质量分</span>
            </div>
          </div>
          <div class="qa-header-right">
            <div class="qa-header-dims" v-if="chatStore.qualityReport.dimensions">
              <div v-for="d in chatStore.qualityReport.dimensions" :key="d.name" class="qa-header-dim">
                <div class="qa-dim-head">
                  <span class="qa-dim-name">{{ d.name }}</span>
                  <span class="qa-dim-score">{{ d.score }}</span>
                </div>
                <div class="qa-dim-bar">
                  <div class="qa-dim-fill" :style="{ width: d.score + '%' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="empty-state">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
          </svg>
          <p class="empty-text">请先在「简历锻造」中生成简历</p>
        </div>

        <!-- 当前投递数据分析 -->
        <div class="qa-section" v-if="huntStore.applications.length > 0">
          <h3 class="qa-section-title">你的投递数据</h3>
          <div class="qa-data-row">
            <div class="qa-data-card">
              <span class="qa-data-num">{{ huntStore.stats.total }}</span>
              <span class="qa-data-label">总投递数</span>
            </div>
            <div class="qa-data-card">
              <span class="qa-data-num">{{ huntStore.stats.screened }}</span>
              <span class="qa-data-label">通过筛选</span>
            </div>
            <div class="qa-data-card">
              <span class="qa-data-num">{{ huntStore.conversionRates.screened }}%</span>
              <span class="qa-data-label">筛选通过率</span>
            </div>
            <div class="qa-data-card">
              <span class="qa-data-num">{{ huntStore.conversionRates.offer }}%</span>
              <span class="qa-data-label">Offer 转化率</span>
            </div>
          </div>

          <!-- 洞察 -->
          <div class="qa-insight-box">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="qa-insight-icon">
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            <div class="qa-insight-text">
              <strong>分析建议：</strong>
              当前简历质量分为
              <strong style="font-size: 1.1rem; color: var(--color-primary);">{{ chatStore.qualityReport?.total_score ?? '--' }}</strong> 分（{{ chatStore.qualityReport?.grade || '未评估' }}）。
              <template v-if="chatStore.qualityReport?.total_score < 52">
                建议先回到「简历锻造」补齐经历与量化成果，再加大投递量。
              </template>
              <template v-else-if="chatStore.qualityReport?.total_score < 68">
                已具备基本竞争力，建议针对中匹配岗位使用 AI 微调适配，补足 JD 要求的关键技能。
              </template>
              <template v-else>
                简历质量良好，建议优先投递高匹配岗位，并着手准备面试。
              </template>
            </div>
          </div>
        </div>

        <!-- 技能缺口分析：统计自本次搜索到的真实 JD，不含预设内容 -->
        <div class="qa-section" v-if="skillGaps.length > 0">
          <h3 class="qa-section-title">技能补足建议</h3>
          <p class="qa-section-sub">
            统计自本次搜索到的 {{ huntStore.matchedJobs.length }} 个真实职位，以下技能被要求最多但你的简历中尚未体现
          </p>
          <div class="qa-skill-gaps">
            <div class="gap-card" v-for="gap in skillGaps" :key="gap.skill">
              <div class="gap-icon-wrap">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
                </svg>
              </div>
              <div class="gap-info">
                <div class="gap-name">{{ gap.skill }}</div>
                <div class="gap-reason">
                  {{ gap.count }} / {{ huntStore.matchedJobs.length }} 个职位要求，你的简历中未体现
                </div>
                <div class="gap-action">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"/>
                  </svg>
                  在经历中补充一段使用「{{ gap.skill }}」的实践，并写出可量化的成果
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- ========== 职位详情整页 ========== -->
    <div v-if="detailJob" class="detail-page">
      <!-- 顶部返回栏 -->
      <div class="detail-topbar">
        <button class="detail-back-btn" @click="closeDetail">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          <span>返回职位列表</span>
        </button>
        <div class="detail-topbar-left">
          <h2 class="detail-job-title">{{ detailJob.title }}</h2>
          <div class="detail-job-meta">
            <span class="detail-company">{{ detailJob.company }}</span>
            <span class="job-sep">·</span>
            <span class="detail-location">{{ detailJob.location }}</span>
            <span class="detail-salary">{{ detailJob.salary }}</span>
            <span :class="['match-tag', detailLevel]">
              <span class="match-dot"></span>
              {{ matchLabel({ matchLevel: detailLevel, matchScore: detailJob.matchScore }) }}
            </span>
          </div>
        </div>
      </div>

      <!-- 左右分栏 -->
      <div class="detail-body">
        <!-- 左侧：职位详情 -->
        <div class="detail-left">
          <div class="detail-section">
            <h4 class="detail-section-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              职位描述
            </h4>
            <p class="detail-desc">{{ detailJob.description }}</p>
          </div>

          <div class="detail-section">
            <h4 class="detail-section-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              能力要求
            </h4>
            <div class="detail-tags">
              <span v-for="req in detailJob.requirements" :key="req" class="detail-tag">{{ req }}</span>
            </div>
          </div>

          <div class="detail-section">
            <h4 class="detail-section-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              匹配分析
            </h4>
            <div class="detail-reason">{{ detailJob.reasons }}</div>
            <div v-if="detailJob.missingSkills?.length > 0" class="detail-missing">
              <span class="detail-missing-label">待补足技能：</span>
              <span v-for="sk in detailJob.missingSkills" :key="sk" class="missing-tag">{{ sk }}</span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="detail-actions">
            <button
              v-if="detailLevel === 'green'"
              class="action-btn primary"
              @click.stop="onApplyJob(detailJob, 'original')"
              :disabled="appliedJobIds[detailJob.id] || !hasResume"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              {{ appliedJobIds[detailJob.id] ? '已投递' : '一键投递' }}
            </button>
            <button
              v-if="detailLevel === 'yellow'"
              class="action-btn secondary"
              @click.stop="onAdaptResume(detailJob)"
              :disabled="adaptingDetail || huntStore.adaptingJobId === detailJob.id || !hasResume"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
              {{ (adaptingDetail || huntStore.adaptingJobId === detailJob.id) ? 'AI 适配中...' : '重新适配' }}
            </button>
            <button
              v-if="detailLevel === 'yellow' && huntStore.adaptedResumes[detailJob.id]"
              class="action-btn primary"
              @click.stop="onApplyJob(detailJob, 'adapted')"
              :disabled="appliedJobIds[detailJob.id] || !hasResume"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              {{ appliedJobIds[detailJob.id] ? '已投递' : '投递适配版' }}
            </button>
            <button v-if="detailLevel === 'red'" class="action-btn disabled-btn" disabled>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              暂不建议投递
            </button>
            <!-- 匹配度无法评估时同样要给出可操作项，理由见列表页同名分支 -->
            <button
              v-if="detailLevel === 'unknown'"
              class="action-btn secondary"
              @click.stop="onApplyJob(detailJob, 'original')"
              :disabled="appliedJobIds[detailJob.id] || !hasResume"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
              {{ appliedJobIds[detailJob.id] ? '已投递' : (hasResume ? '仍要投递' : '请先创建简历') }}
            </button>
          </div>
        </div>

        <!-- 右侧：简历（绿色=原简历全文，黄/红=适配前后对比） -->
        <div class="detail-right">
          <div class="detail-right-header">
            <h4 class="detail-section-title">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              {{ !hasResume ? '简历适配' : (detailNoChange ? '你的简历' : '适配版简历') }}
            </h4>
            <div v-if="detailAdapted && !detailNoChange" class="detail-score-compare">
              <span class="detail-score-old">{{ detailAdapted.originalScore }}分</span>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="adapt-arrow-icon">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
              </svg>
              <span class="detail-score-new">{{ detailAdapted.adaptedScore }}分</span>
            </div>
          </div>

          <!-- 未体现的 JD 技能：AI 不会替用户把它们写进简历，只能提示去补 -->
          <div v-if="detailAdapted?.skillAdvice" class="adapt-skill-advice">
            {{ detailAdapted.skillAdvice }}
          </div>

          <!-- 高匹配提示 -->
          <div v-if="detailAdapted && detailNoChange" class="resume-nochange-banner">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
            </svg>
            <span>你的简历已覆盖该岗位的主要技能要求，无需修改即可直接投递</span>
          </div>

          <!-- 图例（仅适配场景显示） -->
          <div v-if="detailAdapted && !detailNoChange" class="diff-legend">
            <span class="diff-legend-item"><span class="diff-dot added"></span>新增/优化</span>
            <span class="diff-legend-item"><span class="diff-dot removed"></span>原文</span>
          </div>

          <!-- 未登录：蒙版锁定，需登录后才显示简历 -->
          <div v-if="!auth.isLoggedIn" class="resume-lock">
            <div class="resume-lock-blur" aria-hidden="true">
              <div class="sk sk-title"></div>
              <div class="sk sk-w90"></div>
              <div class="sk sk-w70"></div>
              <div class="sk sk-w90"></div>
              <div class="sk sk-w50"></div>
              <div class="sk sk-w70"></div>
              <div class="sk sk-w90"></div>
              <div class="sk sk-w50"></div>
            </div>
            <div class="resume-lock-overlay">
              <div class="resume-lock-icon">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                </svg>
              </div>
              <p class="resume-lock-title">登录后查看适配简历</p>
              <p class="resume-lock-sub">登录即可查看 AI 为该岗位定制的简历与匹配优化</p>
              <button class="resume-lock-btn" @click="auth.openLogin()">登录查看</button>
            </div>
          </div>

          <!-- 已登录但还没有简历：引导先去创建，不伪造适配简历 -->
          <div v-else-if="!hasResume" class="resume-empty-guide">
            <div class="resume-empty-icon">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/>
              </svg>
            </div>
            <p class="resume-empty-title">你还没有简历</p>
            <p class="resume-empty-sub">创建简历后，AI 才能针对该岗位做匹配适配，并支持一键投递</p>
            <button class="resume-empty-btn" @click="goCreateResume">去创建简历</button>
          </div>

          <!-- 适配中 -->
          <div v-else-if="adaptingDetail" class="adapting-state">
            <div class="spinner"></div>
            <span>AI 正在为此岗位准备简历...</span>
          </div>

          <!-- 绿色高匹配：直接展示成品简历（A4 排版，无需修改即可投递） -->
          <div v-else-if="detailNoChange && detailAdapted" class="detail-resume-clean">
            <ResumePreview :resume="detailAdapted.originalResume" :show-toolbar="false" />
          </div>

          <!-- 黄/红：适配前后逐行对比 -->
          <div v-else-if="detailAdapted && detailAdapted.sections" class="diff-sections">
            <div v-for="(sec, si) in detailAdapted.sections" :key="si" class="diff-section">
              <div class="diff-section-name">{{ sec.name }}</div>
              <div v-for="(ch, ci) in sec.changes" :key="ci" :class="['diff-line', ch.type]">
                <template v-if="ch.type === 'unchanged'">
                  <span class="diff-text">{{ ch.text }}</span>
                </template>
                <template v-else-if="ch.type === 'added'">
                  <span class="diff-prefix added">+</span>
                  <span class="diff-text added">{{ ch.text }}</span>
                </template>
                <template v-else-if="ch.type === 'changed'">
                  <div class="diff-changed-group">
                    <div class="diff-changed-old">
                      <span class="diff-prefix removed">-</span>
                      <span class="diff-text removed">{{ ch.original }}</span>
                    </div>
                    <div class="diff-changed-new">
                      <span class="diff-prefix added">+</span>
                      <span class="diff-text added">{{ ch.adapted }}</span>
                    </div>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- 加载失败兜底 -->
          <div v-else class="diff-empty">
            <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" opacity="0.35">
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
            </svg>
            <p>简历加载失败，请关闭后重试</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast.visible" :class="['toast', toast.type]">
      <svg v-if="toast.type === 'success'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
      </svg>
      <span>{{ toast.message }}</span>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useJobHuntStore } from '@/stores/jobHunt'
import { useAuthStore } from '@/stores/auth'
import { jobHuntApi } from '@/api/jobHunt'
import ResumePreview from '@/components/ResumePreview.vue'

const router = useRouter()
const chatStore = useChatStore()
const huntStore = useJobHuntStore()
const auth = useAuthStore()

// 是否已有简历：适配 / 投递 / 简历展示都以此为前提，
// 避免"明明没简历，求职投递却凭空显示一份简历或投递记录"的矛盾
const hasResume = computed(() => !!chatStore.resumeData || auth.resumeHistory.length > 0)

const activeTab = ref('search')
const searchKeyword = ref('')
const searchMessage = ref('输入关键词搜索真实职位，结果来自招聘平台实时数据')
const crawlerStatuses = ref([])
const appliedJobIds = reactive({})
// 后端返回的匹配依据：是否用到了简历、岗位画像来自真实 JD 还是兜底词表
const matchBasis = ref(null)

// 匹配标签文案。后端在"没有简历"或"JD 未列明要求"时返回 null 分数，
// 此时不能显示 "0%" 或凭空给一个数 —— 如实说明无法评估。
function matchLabel(job) {
  if (job.matchScore === null || job.matchScore === undefined) return '匹配度未知'
  const level = { green: '高匹配', yellow: '中匹配', red: '低匹配' }[job.matchLevel] || '匹配度'
  return `${level} ${job.matchScore}%`
}

// 如实告知匹配分怎么算出来的，避免 UI 宣称"基于你的简历"而实际并非如此
const matchBasisText = computed(() => {
  const b = matchBasis.value
  if (!b) return ''
  if (!b.hasResume) return '尚未生成简历，暂时无法计算匹配度。创建简历后即可看到与各岗位的真实匹配情况。'
  if (b.profileSource === 'jd' && b.sampleSize) {
    return `匹配度 = 你的简历技能 × 「${b.targetJob}」近期 ${b.sampleSize} 条真实招聘要求（越多岗位要求的技能，权重越高）`
  }
  return `匹配度 = 你的简历技能 × 该职位列明的技能要求（「${b.targetJob}」的真实 JD 样本不足，暂用通用岗位模型）`
})

// 技能缺口：统计本次搜索结果里被最多职位要求、而简历未覆盖的技能。
// 数据全部来自后端返回的 missingSkills，不含任何预设示例。
const skillGaps = computed(() => {
  const counter = new Map()
  for (const job of huntStore.matchedJobs) {
    for (const skill of job.missingSkills || []) {
      counter.set(skill, (counter.get(skill) || 0) + 1)
    }
  }
  return [...counter.entries()]
    .map(([skill, count]) => ({ skill, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 6)
})

// 职位详情整页
const detailJob = ref(null)
const detailAdapted = computed(() => detailJob.value ? huntStore.adaptedResumes[detailJob.value.id] : null)
const adaptingDetail = ref(false)
// 详情页匹配等级用搜索结果 —— 那是按用户真实简历与真实 JD 算出来的。
// 适配接口只返回改写内容与前后分数，不再自带 matchLevel。
const detailLevel = computed(() => detailJob.value?.matchLevel)
// 高匹配（绿色）岗位：适配结果标记 noChange，右侧直接展示原简历全文、不显示 diff
const detailNoChange = computed(() => detailAdapted.value?.noChange === true)

async function onOpenJobDetail(job) {
  detailJob.value = job
  // 未登录：右侧简历区用蒙版锁定，不调用模拟接口；登录后由 watch 自动加载
  if (!auth.isLoggedIn) return
  // 没有简历：右侧显示"去创建简历"引导，不伪造适配简历
  if (!hasResume.value) return
  loadDetailResume(job)
}

// 静默加载该岗位的简历数据，保证右侧不为空
async function loadDetailResume(job) {
  // 没有简历时不调用适配接口，避免凭空生成一份简历
  if (!job || !hasResume.value || adaptingDetail.value || huntStore.adaptedResumes[job.id]) return
  adaptingDetail.value = true
  try {
    const result = await jobHuntApi.adapt({
      jobId: job.id,
      targetJob: chatStore.targetJob
    })
    huntStore.saveAdaptedResume(job.id, result)
  } catch (e) {
    // 静默失败，右侧回落到空态
  } finally {
    adaptingDetail.value = false
  }
}

// 用户在详情页登录后，自动补载此前被蒙版锁定的简历
watch(() => auth.isLoggedIn, (now) => {
  if (now && detailJob.value) loadDetailResume(detailJob.value)
  if (now && hasResume.value) loadApplications()
})

function closeDetail() {
  detailJob.value = null
}

// 跳转到首页「创建简历」入口（用户可自行选择对话生成或上传简历）
function goCreateResume() {
  closeDetail()
  router.push('/')
}

async function loadApplications() {
  try {
    const data = await jobHuntApi.getApplications()
    huntStore.applications = data.applications || []
    if (data.stats) {
      huntStore.stats = data.stats
    } else {
      huntStore.recalcStats()
    }
  } catch (e) {}
}

const tabs = computed(() => [
  { key: 'search', label: '职位搜索', badge: huntStore.matchedJobs.length || null },
  { key: 'tracker', label: '投递看板', badge: huntStore.applications.length || null },
  { key: 'analytics', label: '质量归因' }
])

const toast = reactive({ visible: false, message: '', type: 'success' })

function showToast(msg, type = 'success') {
  toast.message = msg
  toast.type = type
  toast.visible = true
  setTimeout(() => { toast.visible = false }, 3000)
}

async function onSearch() {
  if (!auth.isLoggedIn) {
    auth.requireLogin(onSearch)
    return
  }
  huntStore.setSearchLoading(true)
  try {
    const result = await jobHuntApi.search({
      keyword: searchKeyword.value,
      targetJob: chatStore.targetJob
    })
    huntStore.setMatchedJobs(result.jobs || [])
    matchBasis.value = result.matchBasis || null
    searchMessage.value = result.message || (result.source === 'live_unavailable'
      ? '实时职位暂时不可用，请稍后重试'
      : '暂无匹配的真实职位，请更换关键词后重试')
  } catch (e) {
    showToast('搜索失败，请重试', 'error')
  } finally {
    huntStore.setSearchLoading(false)
  }
}

function platformLabel(platform) {
  return { zhipin: 'BOSS直聘', zhaopin: '智联招聘', liepin: '猎聘' }[platform] || platform
}

function formatDateTime(iso) {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function onAdaptResume(job) {
  if (!hasResume.value) {
    showToast('请先创建简历后再进行 AI 适配', 'error')
    return
  }
  if (!auth.isLoggedIn) {
    auth.requireLogin(() => onAdaptResume(job))
    return
  }
  huntStore.setAdaptingJobId(job.id)
  if (detailJob.value) adaptingDetail.value = true
  try {
    const result = await jobHuntApi.adapt({
      jobId: job.id,
      targetJob: chatStore.targetJob
    })
    huntStore.saveAdaptedResume(job.id, result)
    if (result.adapted) {
      showToast(`适配完成！质量分 ${result.originalScore} → ${result.adaptedScore}，匹配度 ${result.originalMatchScore ?? '-'} → ${result.adaptedMatchScore ?? '-'}`)
    } else {
      showToast(result.changes?.[0] || '当前简历无需调整')
    }
  } catch (e) {
    // 后端会明确说明原因（没有简历 / 职位已下架 / AI 暂不可用），如实转达
    showToast(e?.response?.data?.detail || '适配失败，请重试', 'error')
  } finally {
    huntStore.setAdaptingJobId(null)
    adaptingDetail.value = false
  }
}

async function onApplyJob(job, version) {
  if (!hasResume.value) {
    showToast('请先创建简历后再投递', 'error')
    return
  }
  // 未登录先要求登录，登录成功后自动继续投递
  auth.requireLogin(async () => {
    try {
      const result = await jobHuntApi.apply({
        jobId: job.id,
        resumeVersion: version
      })
      huntStore.addApplication(result)
      appliedJobIds[job.id] = true
      showToast(`已投递「${job.title}」到 ${job.company}`)
    } catch (e) {
      showToast('投递失败，请重试', 'error')
    }
  })
}

async function onMoveStatus(app, newStatus) {
  try {
    await jobHuntApi.updateApplicationStatus({
      applicationId: app.id,
      status: newStatus
    })
    huntStore.updateApplicationStatus(app.id, newStatus)
    const labelMap = { screened: '通过筛选', interviewing: '面试中', offered: '已获Offer', rejected: '未通过' }
    showToast(`「${app.jobTitle}」已标记为 ${labelMap[newStatus] || newStatus}`)
  } catch (e) {
    showToast('状态更新失败', 'error')
  }
}

function appsByStatus(status) {
  return huntStore.applications.filter(a => a.status === status)
}

function formatDate(iso) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

onMounted(() => {
  jobHuntApi.getCrawlerStatus().then(data => { crawlerStatuses.value = data.platforms || [] }).catch(() => {})
  // 没有简历时不加载演示投递记录，保持真实空态，
  // 避免"没简历却有 5 条投递记录"的矛盾
  if (!hasResume.value) {
    huntStore.applications = []
    huntStore.recalcStats()
    return
  }
  if (!auth.isLoggedIn) return
  loadApplications()
})

function crawlerStatusLabel(status) {
  return { success: '正常', running: '抓取中', empty: '无结果', failed: '失败', never: '未运行' }[status] || status
}
</script>

<style scoped>
/* ============ 布局 ============ */
.dashboard {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

/* ============ 主内容区 ============ */
.dashboard-main {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

/* ============ Tab 导航 ============ */
.tab-nav {
  display: flex;
  gap: 6px;
  padding: 14px 24px;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border-light);
  position: sticky;
  top: 0;
  z-index: 10;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--color-text-muted);
  border-radius: var(--radius-md);
  transition: all 0.2s var(--ease-out);
}
.tab-btn:hover {
  color: var(--color-text);
  background: var(--color-bg-hover);
}
.tab-btn.active {
  color: var(--color-primary);
  background: var(--color-primary-soft);
  box-shadow: 0 1px 3px rgba(37, 99, 235, 0.12);
}
.tab-icon { display: flex; align-items: center; }
.tab-label { letter-spacing: -0.1px; }
.tab-badge {
  font-size: 0.78rem;
  background: var(--color-primary);
  color: #fff;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  min-width: 22px;
  text-align: center;
  font-weight: 700;
}

.tab-panel {
  flex: 1;
  padding: 28px 24px;
  overflow-y: auto;
}

/* ============ 搜索栏 ============ */
.search-bar {
  display: flex;
  gap: 14px;
  margin-bottom: 20px;
}
.search-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--color-bg-card);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 0 18px;
  transition: all 0.25s var(--ease-out);
  box-shadow: var(--shadow-xs);
}
.search-input-wrap:hover {
  border-color: var(--color-border-strong);
}
.search-input-wrap:focus-within {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}
.search-icon { color: var(--color-text-muted); flex-shrink: 0; }
.search-input {
  flex: 1;
  height: 54px;
  font-size: 1.2rem;
  background: transparent;
  color: var(--color-text);
}
.search-input::placeholder {
  color: var(--color-text-muted);
  font-size: 1.1rem;
}
.search-btn {
  height: 56px;
  padding: 0 32px;
  background: var(--gradient-primary);
  color: #fff;
  font-size: 1.2rem;
  font-weight: 600;
  border-radius: var(--radius-lg);
  white-space: nowrap;
  transition: all 0.25s var(--ease-out);
  box-shadow: var(--shadow-primary);
}
.search-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}
.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ============ 图例 ============ */
.legend {
  display: flex;
  gap: 28px;
  margin-bottom: 22px;
  font-size: 1.05rem;
  color: var(--color-text-muted);
}
.legend-item { display: flex; align-items: center; gap: 8px; }
.crawler-status-bar {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;
  margin: -8px 0 22px;
  color: var(--color-text-muted);
  font-size: 0.9rem;
}
.crawler-status-title { font-weight: 700; color: var(--color-text-secondary); }
.crawler-status-item { display: inline-flex; align-items: center; gap: 6px; }
.crawler-status-item small { color: var(--color-text-faint); }
.crawler-status-dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; }
.crawler-status-dot.success { background: #10b981; }
.crawler-status-dot.running { background: #f59e0b; }
.crawler-status-dot.empty, .crawler-status-dot.failed { background: #ef4444; }
.dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.dot.green { background: #10B981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15); }
.dot.yellow { background: #F59E0B; box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.15); }
.dot.red { background: #EF4444; box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15); }
.dot.unknown { background: #9CA3AF; box-shadow: 0 0 0 3px rgba(156, 163, 175, 0.15); }

/* ============ 加载 & 空态 ============ */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 80px 0;
  color: var(--color-text-muted);
  font-size: 1.15rem;
}
.spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: rotate 0.8s linear infinite;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 80px 0;
  color: var(--color-text-muted);
}
.empty-icon { opacity: 0.3; }
.empty-text { font-size: 1.25rem; font-weight: 500; }
.empty-hint { font-size: 1.05rem; opacity: 0.7; }

/* ============ 职位卡片 ============ */
.job-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.job-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
  transition: all 0.3s var(--ease-out);
  box-shadow: var(--shadow-xs);
  cursor: pointer;
}
.job-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.job-card.match-green { border-left: 4px solid #10B981; }
.job-card.match-yellow { border-left: 4px solid #F59E0B; }
.job-card.match-red { border-left: 4px solid #EF4444; }
.job-card.match-unknown { border-left: 4px solid #D1D5DB; }

.job-body { padding: 24px 28px; }

.job-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  margin-bottom: 14px;
}
.job-top-left { flex: 1; min-width: 0; }
.job-title { font-size: 1.35rem; font-weight: 700; color: var(--color-text); margin-bottom: 6px; letter-spacing: -0.2px; }
.job-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.job-company { font-size: 1.1rem; font-weight: 600; color: var(--color-text-secondary); }
.job-sep { color: var(--color-text-faint); font-size: 1rem; }
.job-location { font-size: 1rem; color: var(--color-text-muted); }
.job-tag {
  font-size: 0.85rem;
  background: var(--color-bg-hover);
  color: var(--color-text-muted);
  padding: 3px 10px;
  border-radius: var(--radius-xs);
  font-weight: 500;
}
.job-source {
  font-size: 0.82rem;
  color: var(--color-primary);
  border: 1px solid var(--color-primary-soft);
  padding: 2px 8px;
  border-radius: var(--radius-xs);
}
.job-freshness {
  display: flex;
  gap: 14px;
  margin: -4px 0 14px;
  font-size: 0.86rem;
  color: var(--color-text-faint);
}
.job-freshness a { color: var(--color-primary); text-decoration: none; }
.job-freshness a:hover { text-decoration: underline; }
.job-top-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; flex-shrink: 0; }
.job-salary { font-size: 1.3rem; font-weight: 800; color: #EF4444; }

.match-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  font-size: 0.92rem;
  font-weight: 700;
  border-radius: var(--radius-pill);
}
.match-tag.green { background: #D1FAE5; color: #059669; }
.match-tag.yellow { background: #FEF3C7; color: #D97706; }
.match-tag.red { background: #FEE2E2; color: #DC2626; }
.match-tag.unknown { background: #F3F4F6; color: #6B7280; }
.adapt-skill-advice {
  margin: 10px 0 14px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: var(--color-warning-soft, #FEF3C7);
  color: var(--color-warning, #D97706);
  font-size: 12.5px;
  line-height: 1.7;
}
.match-basis {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary, #6B7280);
}
.match-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: currentColor;
}

.job-desc {
  font-size: 1.05rem;
  color: var(--color-text-secondary);
  line-height: 1.7;
  margin-bottom: 16px;
}

.match-reason {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 1rem;
  color: #059669;
  background: #ECFDF5;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  margin-bottom: 10px;
  line-height: 1.6;
}
.match-reason svg { flex-shrink: 0; margin-top: 2px; }

.missing-skills {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.missing-label { font-size: 0.95rem; color: var(--color-text-muted); font-weight: 600; }
.missing-tag {
  font-size: 0.88rem;
  background: var(--color-danger-soft);
  color: var(--color-danger);
  padding: 4px 12px;
  border-radius: var(--radius-xs);
  font-weight: 600;
}

.job-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.action-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 24px;
  font-size: 1.1rem;
  font-weight: 600;
  border-radius: var(--radius-md);
  transition: all 0.2s var(--ease-out);
}
.action-btn.primary {
  background: var(--gradient-primary);
  color: #fff;
  box-shadow: var(--shadow-primary);
}
.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-primary-strong);
  transform: translateY(-1px);
}
.action-btn.secondary {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
.action-btn.secondary:hover:not(:disabled) {
  background: var(--color-primary-lighter);
}
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.disabled-btn {
  background: var(--color-bg-hover);
  color: var(--color-text-muted);
  cursor: not-allowed;
}

/* 适配结果 */
.adapt-result {
  margin-top: 16px;
  padding: 18px 20px;
  background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
  border-radius: var(--radius-lg);
  border: 1px solid #A7F3D0;
}
.adapt-compare {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.adapt-label { font-size: 0.95rem; color: var(--color-text-muted); }
.adapt-score { font-size: 1.25rem; font-weight: 800; color: var(--color-text); }
.adapt-score.up { color: #059669; }
.adapt-arrow-icon { color: var(--color-text-muted); flex-shrink: 0; }
.adapt-changes { display: flex; flex-wrap: wrap; gap: 8px; }
.adapt-change-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.9rem;
  color: #059669;
  font-weight: 600;
}

/* ============ 漏斗 ============ */
.funnel-section {
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  padding: 28px 24px;
  border: 1px solid var(--color-border-light);
  box-shadow: var(--shadow-xs);
  margin-bottom: 28px;
}
.funnel-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
}
.funnel-card {
  flex: 0 0 auto;
  min-width: 130px;
  text-align: center;
  padding: 20px 24px;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-lg);
  opacity: 0.55;
  transition: all 0.3s var(--ease-out);
}
.funnel-card.active { opacity: 1; }
.funnel-card.highlight {
  background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%);
  border: 1px solid var(--color-primary-light);
  opacity: 1;
}
.funnel-num { font-size: 2.6rem; font-weight: 800; color: var(--color-text); letter-spacing: -1px; line-height: 1.1; }
.funnel-label { font-size: 0.95rem; color: var(--color-text-muted); font-weight: 600; margin-top: 4px; }
.funnel-rate { font-size: 0.88rem; color: var(--color-primary); font-weight: 700; margin-top: 4px; }
.funnel-sep {
  padding: 0 16px;
  color: var(--color-text-faint);
  flex-shrink: 0;
}

/* ============ Kanban ============ */
.kanban {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding-bottom: 8px;
}
.kanban-col {
  flex: 1;
  min-width: 210px;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
}
.kanban-col-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  font-size: 1.05rem;
  font-weight: 700;
  border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  letter-spacing: -0.1px;
}
.col-applied { background: #F3F4F6; color: var(--color-text-secondary); }
.col-screened { background: #EFF6FF; color: #2563EB; }
.col-interviewing { background: #FEF3C7; color: #D97706; }
.col-offered { background: #D1FAE5; color: #059669; }
.col-rejected { background: #FEE2E2; color: #DC2626; }
.kanban-count {
  font-size: 0.82rem;
  background: rgba(0,0,0,0.08);
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  font-weight: 600;
}
.kanban-cards {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
  min-height: 80px;
}
.kanban-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  padding: 14px;
  border: 1px solid var(--color-border-light);
  transition: all 0.2s var(--ease-out);
  box-shadow: var(--shadow-xs);
}
.kanban-card:hover { box-shadow: var(--shadow-sm); transform: translateY(-1px); }
.kanban-card.success-card { border-color: #A7F3D0; }
.kanban-card.rejected-card { border-color: #FECACA; opacity: 0.7; }
.kc-title { font-size: 0.95rem; font-weight: 700; color: var(--color-text); margin-bottom: 3px; }
.kc-company { font-size: 0.85rem; color: var(--color-text-muted); margin-bottom: 6px; }
.kc-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.kc-version { font-size: 0.8rem; color: var(--color-text-faint); background: var(--color-bg-hover); padding: 2px 8px; border-radius: var(--radius-xs); }
.kc-date { font-size: 0.8rem; color: var(--color-text-faint); }
.kc-badge {
  display: inline-block;
  font-size: 0.78rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: var(--radius-xs);
  margin-bottom: 6px;
}
.kc-badge.interviewing { background: #FEF3C7; color: #D97706; }
.kc-badge.offered { background: #D1FAE5; color: #059669; }
.kc-reason { font-size: 0.82rem; color: var(--color-danger); margin-bottom: 6px; font-weight: 500; }
.kc-actions { display: flex; gap: 6px; margin-top: 8px; }
.kc-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  font-size: 0.8rem;
  font-weight: 600;
  border-radius: var(--radius-xs);
  background: var(--color-bg-hover);
  color: var(--color-text-secondary);
  transition: all 0.15s var(--ease-out);
}
.kc-btn:hover { background: var(--color-primary-soft); color: var(--color-primary); }
.kc-btn.success:hover { background: var(--color-success-soft); color: var(--color-success); }
.kc-btn.danger { color: var(--color-danger); }
.kc-btn.danger:hover { background: var(--color-danger-soft); }
.kanban-empty {
  text-align: center;
  color: var(--color-text-faint);
  font-size: 0.9rem;
  padding: 24px 0;
}

/* ============ 质量归因 ============ */
.qa-header {
  display: flex;
  align-items: center;
  gap: 32px;
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  padding: 28px 32px;
  margin-bottom: 28px;
  border: 1px solid var(--color-border-light);
  box-shadow: var(--shadow-xs);
}
.qa-score-big { display: flex; align-items: center; gap: 20px; flex-shrink: 0; }
.qa-score-ring {
  width: 96px; height: 96px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: conic-gradient(var(--color-primary) calc(var(--pct) * 360deg), var(--color-border-light) 0);
  position: relative;
}
.qa-score-ring::after {
  content: '';
  position: absolute;
  width: 76px; height: 76px;
  border-radius: 50%;
  background: var(--color-bg-card);
}
.qa-score-num {
  position: relative; z-index: 1;
  font-size: 2rem; font-weight: 800;
}
.qa-score-meta { display: flex; flex-direction: column; gap: 2px; }
.qa-grade { font-size: 1.4rem; font-weight: 700; }
.qa-desc { font-size: 0.95rem; color: var(--color-text-muted); }

.qa-header-right { flex: 1; min-width: 0; }
.qa-header-dims { display: flex; flex-direction: column; gap: 12px; }
.qa-header-dim {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.qa-dim-head {
  display: flex;
  justify-content: space-between;
}
.qa-dim-name { font-size: 1.05rem; color: var(--color-text-secondary); font-weight: 600; }
.qa-dim-score { font-size: 1.05rem; font-weight: 700; color: var(--color-text); }
.qa-dim-bar {
  height: 6px;
  background: var(--color-bg-hover);
  border-radius: 3px;
  overflow: hidden;
}
.qa-dim-fill {
  height: 100%;
  background: var(--gradient-primary);
  border-radius: 3px;
  transition: width 0.6s var(--ease-out);
}

.qa-section { margin-bottom: 32px; }
.qa-section-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 6px;
  letter-spacing: -0.3px;
}
.qa-section-sub {
  font-size: 1.1rem;
  color: var(--color-text-muted);
  margin-bottom: 18px;
  line-height: 1.6;
}

.qa-data-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
  margin-bottom: 22px;
}
.qa-data-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  padding: 24px;
  text-align: center;
  border: 1px solid var(--color-border-light);
  box-shadow: var(--shadow-xs);
  transition: all 0.3s var(--ease-out);
}
.qa-data-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}
.qa-data-num { font-size: 2.6rem; font-weight: 800; color: var(--color-primary); display: block; letter-spacing: -1px; line-height: 1.1; }
.qa-data-label { font-size: 1rem; color: var(--color-text-muted); margin-top: 6px; display: block; font-weight: 500; }

.qa-insight-box {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%);
  border-radius: var(--radius-lg);
  padding: 18px 22px;
  border: 1px solid var(--color-primary-light);
}
.qa-insight-icon { flex-shrink: 0; margin-top: 2px; color: var(--color-primary); }
.qa-insight-text { font-size: 1.1rem; color: var(--color-text-secondary); line-height: 1.7; }

.qa-skill-gaps { display: flex; flex-direction: column; gap: 12px; }
.gap-card {
  display: flex;
  align-items: flex-start;
  gap: 18px;
  background: var(--color-bg-card);
  border-radius: var(--radius-xl);
  padding: 22px 24px;
  border: 1px solid var(--color-border-light);
  transition: all 0.3s var(--ease-out);
  box-shadow: var(--shadow-xs);
}
.gap-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}
.gap-icon-wrap {
  width: 48px; height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background: var(--color-primary-soft);
  color: var(--color-primary);
  flex-shrink: 0;
}
.gap-info { flex: 1; min-width: 0; }
.gap-name { font-size: 1.15rem; font-weight: 700; color: var(--color-text); margin-bottom: 4px; letter-spacing: -0.1px; }
.gap-reason { font-size: 0.95rem; color: var(--color-text-secondary); margin-bottom: 6px; line-height: 1.5; }
.gap-action {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.95rem;
  color: var(--color-primary);
  font-weight: 600;
  line-height: 1.5;
}

/* ============ Toast ============ */
.toast {
  position: fixed;
  bottom: 30px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 32px;
  border-radius: var(--radius-pill);
  font-size: 1.1rem;
  font-weight: 600;
  z-index: 300; /* 高于职位详情整页(200)，确保详情页内投递等操作的提示可见 */
  animation: fadeInUp 0.3s var(--ease-out);
  box-shadow: var(--shadow-xl);
}
.toast.success { background: #059669; color: #fff; }
.toast.error { background: #DC2626; color: #fff; }

@keyframes fadeInUp {
  from { opacity: 0; transform: translateX(-50%) translateY(14px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
@keyframes rotate {
  to { transform: rotate(360deg); }
}

/* ============ 职位详情整页 ============ */
.detail-page {
  position: fixed;
  inset: 0;
  z-index: 200; /* 高于全局顶栏(TopNav z-index:100)，使详情页全屏覆盖、自带返回栏可见可点 */
  background: var(--color-bg);
  display: flex;
  flex-direction: column;
  animation: detailPageIn 0.22s var(--ease-out);
}
@keyframes detailPageIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.detail-topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 16px 32px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(14px) saturate(180%);
  -webkit-backdrop-filter: blur(14px) saturate(180%);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
  z-index: 2;
}
.detail-back-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 16px;
  border-radius: var(--radius-md);
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  background: var(--color-bg-subtle);
  transition: all 0.2s var(--ease-out);
  flex-shrink: 0;
}
.detail-back-btn:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
}
.detail-topbar-left { flex: 1; min-width: 0; }
.detail-job-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 6px;
  letter-spacing: -0.3px;
}
.detail-job-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.detail-company { font-size: 1.1rem; font-weight: 600; color: var(--color-text-secondary); }
.detail-location { font-size: 1rem; color: var(--color-text-muted); }
.detail-salary { font-size: 1.25rem; font-weight: 800; color: #EF4444; }

/* 左右分栏（整页铺满） */
.detail-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
.detail-left {
  flex: 0 0 40%;
  min-width: 0;
  overflow-y: auto;
  padding: 32px 40px;
  border-right: 1px solid var(--color-border-light);
}
.detail-right {
  flex: 0 0 60%;
  min-width: 0;
  overflow-y: auto;
  padding: 32px 40px;
  background: #FAFBFC;
}

/* 高匹配提示横幅 */
.resume-nochange-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  margin-bottom: 18px;
  background: linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%);
  border: 1px solid #A7F3D0;
  border-radius: var(--radius-lg);
  color: #059669;
  font-size: 1.02rem;
  font-weight: 600;
}
.resume-nochange-banner svg { flex-shrink: 0; }

.detail-section { margin-bottom: 24px; }
.detail-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 12px;
  letter-spacing: -0.1px;
}
.detail-desc {
  font-size: 1.05rem;
  color: var(--color-text-secondary);
  line-height: 1.8;
}
.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.detail-tag {
  font-size: 0.95rem;
  background: var(--color-primary-soft);
  color: var(--color-primary);
  padding: 6px 14px;
  border-radius: var(--radius-pill);
  font-weight: 600;
}
.detail-reason {
  font-size: 1rem;
  color: #059669;
  background: #ECFDF5;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  line-height: 1.6;
  margin-bottom: 10px;
}
.detail-missing {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.detail-missing-label { font-size: 0.95rem; color: var(--color-text-muted); font-weight: 600; }
.detail-actions { display: flex; gap: 10px; margin-top: 20px; }

/* 右侧：简历Diff */
.detail-right-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  flex-wrap: wrap;
  gap: 12px;
}
.detail-score-compare {
  display: flex;
  align-items: center;
  gap: 8px;
}
.detail-score-old {
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--color-text-muted);
}
.detail-score-new {
  font-size: 1.25rem;
  font-weight: 800;
  color: #059669;
}

.diff-legend {
  display: flex;
  gap: 20px;
  margin-bottom: 18px;
  font-size: 0.9rem;
  color: var(--color-text-muted);
}
.diff-legend-item { display: flex; align-items: center; gap: 6px; }
.diff-dot { width: 10px; height: 10px; border-radius: 3px; flex-shrink: 0; }
.diff-dot.added { background: #10B981; }
.diff-dot.removed { background: #EF4444; }

.adapting-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 60px 0;
  color: var(--color-text-muted);
  font-size: 1.05rem;
}

/* ============ 未登录：简历蒙版锁定 ============ */
.resume-lock {
  position: relative;
  min-height: 420px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  background: var(--color-bg-card);
  overflow: hidden;
}

.resume-lock-blur {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 32px;
  filter: blur(5px);
  opacity: 0.5;
  pointer-events: none;
}

.resume-lock-blur .sk {
  height: 15px;
  border-radius: 7px;
  background: linear-gradient(90deg, var(--color-border-light), var(--color-bg-subtle));
}
.resume-lock-blur .sk-title { height: 30px; width: 48%; margin-bottom: 10px; }
.resume-lock-blur .sk-w90 { width: 90%; }
.resume-lock-blur .sk-w70 { width: 70%; }
.resume-lock-blur .sk-w50 { width: 50%; }

.resume-lock-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
  padding: 24px;
  background: rgba(255, 255, 255, 0.62);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
}

.resume-lock-icon {
  width: 58px;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}

.resume-lock-title {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--color-text);
}

.resume-lock-sub {
  font-size: 1rem;
  color: var(--color-text-secondary);
  max-width: 280px;
  line-height: 1.6;
}

.resume-lock-btn {
  margin-top: 6px;
  padding: 11px 30px;
  background: var(--gradient-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: 1.1rem;
  font-weight: 600;
  box-shadow: var(--shadow-primary);
  transition: all 0.2s var(--ease-out);
}
.resume-lock-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

/* ============ 详情页：未创建简历引导 ============ */
.resume-empty-guide {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: 420px;
  text-align: center;
  padding: 40px 24px;
  border-radius: var(--radius-lg);
  border: 1px dashed var(--color-border);
  background: var(--color-bg-card);
}
.resume-empty-icon {
  width: 58px;
  height: 58px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
.resume-empty-title {
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--color-text);
}
.resume-empty-sub {
  font-size: 1rem;
  color: var(--color-text-secondary);
  max-width: 320px;
  line-height: 1.6;
}
.resume-empty-btn {
  margin-top: 6px;
  padding: 11px 30px;
  background: var(--gradient-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: 1.1rem;
  font-weight: 600;
  box-shadow: var(--shadow-primary);
  transition: all 0.2s var(--ease-out);
}
.resume-empty-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

/* ============ 搜索页：无简历提示条 ============ */
.no-resume-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  margin-bottom: 18px;
  background: linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%);
  border: 1px solid var(--color-primary-light);
  border-radius: var(--radius-lg);
}
.no-resume-banner > svg { color: var(--color-primary); flex-shrink: 0; }
.no-resume-text {
  flex: 1;
  font-size: 1.02rem;
  color: var(--color-text-secondary);
  line-height: 1.6;
}
.no-resume-text strong { color: var(--color-primary); }
.no-resume-btn {
  flex-shrink: 0;
  padding: 9px 20px;
  background: var(--gradient-primary);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: 1rem;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: var(--shadow-primary);
  transition: all 0.2s var(--ease-out);
}
.no-resume-btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-primary-strong);
}

.diff-sections {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.diff-section {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  overflow: hidden;
}
.diff-section-name {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--color-text);
  padding: 12px 18px;
  background: var(--color-bg-subtle);
  border-bottom: 1px solid var(--color-border-light);
  letter-spacing: -0.1px;
}
.diff-line {
  padding: 8px 18px;
  font-size: 0.92rem;
  line-height: 1.7;
  border-bottom: 1px solid #F3F4F6;
}
.diff-line:last-child { border-bottom: none; }
.diff-line.added {
  background: rgba(16, 185, 129, 0.06);
}
.diff-line.removed {
  background: rgba(239, 68, 68, 0.06);
}
.diff-prefix {
  font-weight: 700;
  margin-right: 6px;
  font-family: 'SF Mono', 'Cascadia Code', monospace;
  font-size: 0.85rem;
}
.diff-prefix.added { color: #059669; }
.diff-prefix.removed { color: #DC2626; }
.diff-text {
  color: var(--color-text);
}
.diff-text.added {
  color: #059669;
  font-weight: 500;
}
.diff-text.removed {
  color: #DC2626;
  font-weight: 500;
}
.diff-text.unchanged {
  color: var(--color-text-secondary);
}
.diff-changed-group { display: flex; flex-direction: column; gap: 4px; }
.diff-changed-old, .diff-changed-new {
  display: flex;
  align-items: flex-start;
}

.diff-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 80px 0;
  color: var(--color-text-muted);
  font-size: 1.05rem;
  text-align: center;
  line-height: 1.6;
}
</style>
