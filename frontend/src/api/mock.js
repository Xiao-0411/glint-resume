/**
 * Mock API —— 前端独立演示用
 * 模拟 AI 对话回复 / 简历生成 / 质量评估
 * 真实接入时把这里的函数替换成 axios 调用后端 /api/* 即可
 */

/* ============ 1. 对话 Mock ============ */

/**
 * 根据当前对话轮次和岗位意向，返回 AI 的下一句回复
 * @param {Object} params { targetJob, userMessage, userMsgCount }
 * @returns {Promise<{reply: string, stage: string, stageLabel?: string, quickReplies?: string[]}>}
 */
export function mockChatReply({ targetJob, userMessage, userMsgCount }) {
  return new Promise(resolve => {
    setTimeout(() => {
      const script = buildDialogScript(targetJob)
      const idx = Math.min(userMsgCount - 1, script.length - 1)
      resolve(script[idx])
    }, 600 + Math.random() * 400)
  })
}

/**
 * 完整简历对话流程（按真实写简历顺序）：
 *  ① 基本信息 → ② 教育背景 → ③ 项目经历（多轮 STAR-L 追问）→ ④ 技能 → ⑤ 获奖 → ⑥ 准备生成
 *
 * 阶段标签用于驱动顶部进度条：
 *  - basic_info       基本信息
 *  - education        教育背景
 *  - experience_mining 项目经历
 *  - skills           技能
 *  - awards           获奖
 *  - ready_to_generate 准备生成
 */
function buildDialogScript(targetJob) {
  const job = targetJob || '产品经理'
  return [
    // 用户第 1 句（自动发送：我想做xxx）—— 开场 + 问基本信息
    {
      reply: `你好！欢迎使用识光简历 ✈️\n\n你想做「**${job}**」，这是个很有发展空间的方向。接下来我会像聊天一样，一步步帮你梳理简历内容。\n\n**第一步：先认识一下你**\n方便告诉我你的**姓名**、**联系方式**（手机或邮箱）和**所在城市**吗？一句话简单说就行，比如："我叫李同学，手机 138xxxx，邮箱 xx@qq.com，在上海"。`,
      stage: 'basic_info',
      stageLabel: '基本信息',
      quickReplies: ['李同学，138 0000 0000，上海', '我先不填，直接开始', '只想填邮箱可以吗']
    },
    // 用户第 2 句（基本信息）—— 问教育背景
    {
      reply: `好的，记下来啦 ✅\n\n**第二步：你的教育背景**\n请告诉我你的**学校**、**专业**、**学历**和**预计毕业时间**。如果有 GPA、专业排名、关键课程也可以一起说。\n\n比如："我是某 985 大学计算机科学专业本科，2025 年 6 月毕业，GPA 3.7"。`,
      stage: 'education',
      stageLabel: '教育背景',
      quickReplies: ['本科 2025 届', '硕士 2025 届', '我还在大二/大三']
    },
    // 用户第 3 句（教育背景）—— 问项目/课程/实习经历
    {
      reply: `教育背景已收到 🎓\n\n**第三步：挖掘你的经历**\n这是简历最关键的部分。**大学期间，哪个课程作业 / 项目 / 实习 / 比赛 / 社团活动让你印象最深刻？**\n\n哪怕只是一次课堂实验、一个小工具、一段志愿服务都可以——很多看似平常的经历，经过 STAR-L 重塑后会非常出彩。`,
      stage: 'experience_mining',
      stageLabel: '项目经历',
      quickReplies: ['做过一个课程项目', '参加过一场比赛', '有过实习经历', '参加过社团']
    },
    // 用户第 4 句（说了一段经历）—— STAR-L：S + T
    {
      reply: `这段经历很有挖掘价值 ✨\n\n我来用 **STAR-L 法则**深入了解一下：\n\n• **背景（S）**：这个项目是在什么背景下做的？要解决什么问题？\n• **角色（T）**：你**具体负责哪一部分**？团队里你的角色是什么？\n\n一句话简单说说就行。`,
      stage: 'experience_mining',
      stageLabel: '项目经历',
      quickReplies: ['是课程要求的', '自己感兴趣发起的', '老师指定的课题']
    },
    // 用户第 5 句（回答了 S/T）—— 追问 A + R
    {
      reply: `思路很清晰！再继续聊聊：\n\n• **行动（A）**：你用了**什么工具或方法**？过程中遇到过什么困难，是怎么解决的？\n• **成果（R）**：最终的成果是什么？有没有**具体数据**（用户数、效率提升、得分、获奖等）？\n\n数据越具体越好——这是简历的"金字招牌"。`,
      stage: 'experience_mining',
      stageLabel: '项目经历',
      quickReplies: ['用了 Python/Vue 等技术', '遇到过技术难题', '成果还不错']
    },
    // 用户第 6 句（回答了 A/R）—— 追问 L + 询问是否还有其他经历
    {
      reply: `太棒了！最后一个问题：**做完这个项目，你最大的收获是什么（L）？** 是技术能力的提升，还是方法论的成长？\n\n另外，**你还有其他经历**吗？比如其他课程项目、实习、社团、志愿服务……越多越好。`,
      stage: 'experience_mining',
      stageLabel: '项目经历',
      quickReplies: ['还有一段比赛经历', '有一段社团经历', '就这些了']
    },
    // 用户第 7 句（回答了 L + 提到/没提到其他经历）—— 询问技能
    {
      reply: `我已经记下你的几段经历了 📒\n\n**第四步：你的技能清单**\n请告诉我你掌握的**技术栈 / 工具 / 软件 / 语言**，分类列举即可。\n\n比如：\n• 技术栈：Java、Spring Boot、MySQL、Redis\n• 工具：Git、Linux、VSCode\n• 软技能：项目管理、跨部门沟通`,
      stage: 'skills',
      stageLabel: '技能',
      quickReplies: ['让 AI 根据经历推断', '我有一份技能清单', '不确定怎么填']
    },
    // 用户第 8 句（说了技能）—— 询问获奖
    {
      reply: `技能记录完毕 🛠️\n\n**第五步：获奖与荣誉（可选）**\n你有什么**奖学金、竞赛奖项、证书**之类的吗？如果有就简单列举一下，没有的话可以直接说"没有"，我们继续下一步。`,
      stage: 'awards',
      stageLabel: '获奖',
      quickReplies: ['获得过奖学金', '有比赛获奖', '考过相关证书', '没有获奖经历']
    },
    // 用户第 9 句（说了获奖/没有）—— 触发生成
    {
      reply: `好的，所有信息都收集齐了 🎯\n\n我对你的整体画像已经有了清晰的了解：\n• **基本信息** ✅\n• **教育背景** ✅\n• **项目/经历**（含 STAR-L 细节）✅\n• **技能清单** ✅\n• **获奖荣誉** ✅\n\n接下来我会用 STAR-L 法则重塑你的经历描述，生成一份**专业、量化、可信**的简历，并附上五维质量评估报告。\n\n稍等几秒……`,
      stage: 'ready_to_generate',
      stageLabel: '准备生成',
      quickReplies: []
    }
  ]
}

/* ============ 2. 简历生成 Mock ============ */

export function mockGenerateResume({ targetJob, sessionId }) {
  return new Promise(resolve => {
    setTimeout(() => {
      resolve({
        resume: buildMockResume(targetJob),
        qualityReport: buildMockQualityReport()
      })
    }, 2200)
  })
}

export function buildMockResume(targetJob) {
  const job = targetJob || '产品经理'
  return {
    basic: {
      fullname: '李同学',
      target_job: job,
      email: 'li.student@example.com',
      phone: '138 0000 0000',
      location: '上海'
    },
    education: [
      {
        school: '某 985 大学',
        major: '计算机科学与技术',
        degree: '本科',
        period: '2021.09 - 2025.06',
        gpa: '3.7 / 4.0',
        highlights: ['专业排名前 15%', '获学业奖学金 2 次']
      }
    ],
    experiences: [
      {
        id: 'exp_001',
        title: '校园食堂智能点餐系统',
        type: 'course_project',
        role: '后端负责人',
        period: '2023.09 - 2024.01',
        bullets: [
          '主导设计基于 Spring Boot 的微服务架构，承载 3000+ 同学的日均点餐请求',
          '设计并实现 12 个 RESTful API 接口，使用 Redis 缓存热门菜品数据，接口平均响应时间降至 80ms',
          '推动团队建立代码评审机制，项目在《软件工程》课程中获 A 级评分（年级前 5%）',
          '深入理解需求分析→架构设计→上线发布的完整研发流程，建立工程化思维'
        ],
        tag: { label: '基于真实项目重塑', level: 'high', color: 'green' }
      },
      {
        id: 'exp_002',
        title: '全国大学生数据分析竞赛',
        type: 'competition',
        role: '数据分析师',
        period: '2024.03 - 2024.06',
        bullets: [
          '面向城市共享单车调度优化课题，独立完成数据清洗、特征构建与模型搭建',
          '分析 2 万条出行数据，运用 K-Means 聚类算法识别出 5 类高峰用户行为',
          '提出基于时段-区域的动态调度方案，模拟测试中预计可降低空载率 18%',
          '团队获华东赛区三等奖，相关方案被指导老师推荐至校创新创业中心'
        ],
        tag: { label: '基于赛事经历重塑', level: 'high', color: 'green' }
      },
      {
        id: 'exp_003',
        title: '校学生会信息中心',
        type: 'club',
        role: '技术干事',
        period: '2022.09 - 2023.06',
        bullets: [
          '负责学生会公众号日常运营，期间策划并发布 30+ 篇推文，平均阅读量提升 40%',
          '搭建表单系统替代纸质流程，将活动报名效率提升约 3 倍',
          '协调 5 人小组完成校庆视频拍摄与剪辑，全网播放量破 5 万次'
        ],
        tag: { label: '基于课外实践拔高', level: 'medium', color: 'yellow' }
      }
    ],
    skills: {
      technical: ['Java / Spring Boot', 'Python', 'MySQL / Redis', 'Git', 'Linux 基础'],
      product: ['需求分析', '原型设计 (Figma / Axure)', '数据驱动决策', 'PRD 撰写'],
      soft: ['团队协作', '项目推动', '问题拆解']
    },
    awards: [
      '2024 全国大学生数据分析大赛华东赛区三等奖',
      '2023 校三好学生',
      '2022-2024 校学业奖学金（共 2 次）'
    ],
    self_evaluation: '具备扎实的工程能力与产品思维，能够主导从 0 到 1 的项目落地。善于在不同角色间灵活切换，乐于在跨团队协作中创造价值。'
  }
}

/* ============ 3. 质量报告 Mock ============ */

function buildMockQualityReport() {
  return {
    total_score: 82,
    grade: '优秀',
    grade_color: '#10B981',
    dimensions: [
      { name: '完整度', score: 88, max: 100, desc: '简历各模块齐全，结构清晰' },
      { name: '量化度', score: 72, max: 100, desc: '部分经历缺少具体数字' },
      { name: '专业度', score: 85, max: 100, desc: '用词专业，动词有力' },
      { name: '匹配度', score: 80, max: 100, desc: '与目标岗位关键词对齐度较高' },
      { name: '可信度', score: 90, max: 100, desc: '内容真实可追溯' }
    ],
    highlights: [
      {
        title: '内容真实可信',
        score: 90,
        desc: '所有经历均基于真实对话生成，包装度合理，未触及诚信红线。',
        icon: 'shield'
      },
      {
        title: '结构完整专业',
        score: 88,
        desc: '简历包含教育、项目、技能、获奖等核心模块，符合企业 HR 阅读习惯。',
        icon: 'check'
      }
    ],
    improvements: [
      {
        title: '经历数量偏少',
        score: 60,
        desc: '目前仅识别到 3 段项目/实习经历，大学生简历建议至少 3~5 段。是否还有课程项目、社团活动、志愿服务、兼职、竞赛经历未填写？',
        target_exp_id: null,
        evidence: '',
        actions: [
          {
            original: '',
            suggestion: '补充一段「实习经历（哪怕只有 1~2 个月的远程/线上实习）」，套用 STAR-L 法则展开',
            reason: '学生简历缺少实习是常见短板'
          },
          {
            original: '',
            suggestion: '补充一段「志愿服务 / 公益项目」，体现责任感和软技能',
            reason: '丰富经历类型提升整体竞争力'
          },
          {
            original: '',
            suggestion: '补充一段「课题研究 / 老师带的科研小项目」',
            reason: '学术与工程能力兼备的信号'
          }
        ]
      },
      {
        title: '量化度偏低',
        score: 72,
        desc: '经历「校学生会信息中心」中部分 bullet 缺少具体数字，以下是改写示例。',
        target_exp_id: 'exp_003',
        evidence: '搭建表单系统替代纸质流程，将活动报名效率提升约 3 倍',
        actions: [
          {
            original: '搭建表单系统替代纸质流程，将活动报名效率提升约 3 倍',
            suggestion: '搭建在线表单系统替代纸质流程，覆盖 8 个学生组织，累计处理 1200+ 条报名，平均节省每场活动 6 小时整理时间',
            reason: '把"3 倍"拆成可验证的绝对数字'
          },
          {
            original: '协调 5 人小组完成校庆视频拍摄与剪辑，全网播放量破 5 万次',
            suggestion: '主导 5 人小组完成校庆视频拍摄与剪辑，全网播放量 5.2 万次，登上学校官方微信置顶 3 天',
            reason: '补充传播深度的二级证据'
          },
          {
            original: '',
            suggestion: '将"阅读量较多"统一改为"平均阅读量 400+，最高单篇 1.2 万"',
            reason: '用绝对数字替代模糊词'
          }
        ]
      },
      {
        title: '岗位匹配度可优化',
        score: 80,
        desc: '目标岗位"产品经理"的核心关键词如「用户调研」「数据分析」「产品迭代」等出现频次还可提升。',
        target_exp_id: 'exp_001',
        evidence: '设计并实现 12 个 RESTful API 接口，使用 Redis 缓存热门菜品数据，接口平均响应时间降至 80ms',
        actions: [
          {
            original: '设计并实现 12 个 RESTful API 接口，使用 Redis 缓存热门菜品数据，接口平均响应时间降至 80ms',
            suggestion: '在上线前完成 30 份学生用户调研，基于反馈迭代 3 版交互原型后再设计 12 个 RESTful 接口，接口平均响应时间降至 80ms',
            reason: '在技术动作前置一段产品视角的用户调研 / 迭代'
          },
          {
            original: '',
            suggestion: '技能板块新增『产品工具：Figma、Axure、墨刀、数据看板』',
            reason: '命中产品经理 JD 中的工具关键词'
          },
          {
            original: '',
            suggestion: '把『校园食堂智能点餐系统』调到经历列表第一位',
            reason: '该项目和产品经理最相关，前置提升匹配度'
          }
        ]
      }
    ],
    action_guide: '聚焦量化补充与关键词优化，按建议修改 3-5 处，预计总分可提升至 88 分以上。',
    integrity_statement: '本简历所有内容均基于你的真实对话生成，AI 仅做专业性重述与合理拔高，未编造任何不存在的经历。'
  }
}

/* ============ 4. PDF 文本 → 简历评估（供 UploadView 使用） ============ */

/**
 * 接收 PDF 解析后的文本，返回结构化简历 + 质量报告
 * Demo 阶段直接返回 mock 数据，真实场景应交给 LLM 解析
 * @param {Object} params { text, fileName }
 */
export function mockEvaluateResumeText({ text, fileName }) {
  return new Promise(resolve => {
    setTimeout(() => {
      const resume = buildMockResume('产品经理')
      const report = buildMockQualityReport()
      report.from_upload = true
      report.source_file = fileName || '上传简历.pdf'
      resolve({ resume, qualityReport: report })
    }, 2000)
  })
}

/**
 * 用户编辑简历后重评(mock):直接返回一份固定质量报告
 */
export function mockReevaluateResume() {
  return new Promise(resolve => {
    setTimeout(() => resolve({ qualityReport: buildMockQualityReport() }), 1200)
  })
}

/* ============ 5. 求职加速 Mock ============ */
