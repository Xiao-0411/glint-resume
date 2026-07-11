"""
Mock 兜底数据 —— 完全复刻前端 mock 脚本
当 USE_MOCK=true 或 LLM_API_KEY 未配置时启用
确保:即使没有 LLM,demo 也能完整走通
"""
from typing import Dict, List

# 9 轮对话脚本,与前端 mock 完全对齐
def build_dialog_script(target_job: str) -> List[Dict]:
    job = target_job or "产品经理"
    return [
        {
            "reply": (
                f"你好!欢迎使用识光简历 ✈️\n\n"
                f"你想做「**{job}**」,这是个很有发展空间的方向。"
                f"接下来我会像聊天一样,一步步帮你梳理简历内容。\n\n"
                "**第一步:先认识一下你**\n"
                "方便告诉我你的**姓名**、**联系方式**(手机或邮箱)和**所在城市**吗?"
                '一句话简单说就行,比如:"我叫李同学,手机 138xxxx,邮箱 xx@qq.com,在上海"。'
            ),
            "stage": "basic_info",
            "stage_label": "基本信息",
            "quick_replies": ["李同学,138 0000 0000,上海", "我先不填,直接开始", "只想填邮箱可以吗"]
        },
        {
            "reply": (
                "好的,记下来啦 ✅\n\n"
                "**第二步:你的教育背景**\n"
                "请告诉我你的**学校**、**专业**、**学历**和**预计毕业时间**。"
                "如果有 GPA、专业排名、关键课程也可以一起说。\n\n"
                '比如:"我是某 985 大学计算机科学专业本科,2025 年 6 月毕业,GPA 3.7"。'
            ),
            "stage": "education",
            "stage_label": "教育背景",
            "quick_replies": ["本科 2025 届", "硕士 2025 届", "我还在大二/大三"]
        },
        {
            "reply": (
                "教育背景已收到 🎓\n\n"
                "**第三步:挖掘你的经历**\n"
                "这是简历最关键的部分。**大学期间,哪个课程作业 / 项目 / 实习 / 比赛 / "
                "社团活动让你印象最深刻?**\n\n"
                "哪怕只是一次课堂实验、一个小工具、一段志愿服务都可以——"
                "很多看似平常的经历,经过 STAR-L 重塑后会非常出彩。"
            ),
            "stage": "experience_mining",
            "stage_label": "项目经历",
            "quick_replies": ["做过一个课程项目", "参加过一场比赛", "有过实习经历", "参加过社团"]
        },
        {
            "reply": (
                "这段经历很有挖掘价值 ✨\n\n"
                "我来用 **STAR-L 法则**深入了解一下:\n\n"
                "• **背景(S)**:这个项目是在什么背景下做的?要解决什么问题?\n"
                "• **角色(T)**:你**具体负责哪一部分**?团队里你的角色是什么?\n\n"
                "一句话简单说说就行。"
            ),
            "stage": "experience_mining",
            "stage_label": "项目经历",
            "quick_replies": ["是课程要求的", "自己感兴趣发起的", "老师指定的课题"]
        },
        {
            "reply": (
                "思路很清晰!再继续聊聊:\n\n"
                "• **行动(A)**:你用了**什么工具或方法**?过程中遇到过什么困难,是怎么解决的?\n"
                "• **成果(R)**:最终的成果是什么?有没有**具体数据**(用户数、效率提升、得分、获奖等)?\n\n"
                '数据越具体越好——这是简历的"金字招牌"。'
            ),
            "stage": "experience_mining",
            "stage_label": "项目经历",
            "quick_replies": ["用了 Python/Vue 等技术", "遇到过技术难题", "成果还不错"]
        },
        {
            "reply": (
                "太棒了!最后一个问题:**做完这个项目,你最大的收获是什么(L)?** "
                "是技术能力的提升,还是方法论的成长?\n\n"
                "另外,**你还有其他经历**吗?比如其他课程项目、实习、社团、志愿服务……越多越好。"
            ),
            "stage": "experience_mining",
            "stage_label": "项目经历",
            "quick_replies": ["还有一段比赛经历", "有一段社团经历", "就这些了"]
        },
        {
            "reply": (
                "我已经记下你的几段经历了 📒\n\n"
                "**第四步:你的技能清单**\n"
                "请告诉我你掌握的**技术栈 / 工具 / 软件 / 语言**,分类列举即可。\n\n"
                "比如:\n"
                "• 技术栈:Java、Spring Boot、MySQL、Redis\n"
                "• 工具:Git、Linux、VSCode\n"
                "• 软技能:项目管理、跨部门沟通"
            ),
            "stage": "skills",
            "stage_label": "技能",
            "quick_replies": ["让 AI 根据经历推断", "我有一份技能清单", "不确定怎么填"]
        },
        {
            "reply": (
                "技能记录完毕 🛠️\n\n"
                "**第五步:获奖与荣誉(可选)**\n"
                "你有什么**奖学金、竞赛奖项、证书**之类的吗?"
                '如果有就简单列举一下,没有的话可以直接说"没有",我们继续下一步。'
            ),
            "stage": "awards",
            "stage_label": "获奖",
            "quick_replies": ["获得过奖学金", "有比赛获奖", "考过相关证书", "没有获奖经历"]
        },
        {
            "reply": (
                "好的,所有信息都收集齐了 🎯\n\n"
                "我对你的整体画像已经有了清晰的了解:\n"
                "• **基本信息** ✅\n"
                "• **教育背景** ✅\n"
                "• **项目/经历**(含 STAR-L 细节)✅\n"
                "• **技能清单** ✅\n"
                "• **获奖荣誉** ✅\n\n"
                "接下来我会用 STAR-L 法则重塑你的经历描述,"
                "生成一份**专业、量化、可信**的简历,并附上五维质量评估报告。\n\n"
                "稍等几秒……"
            ),
            "stage": "ready_to_generate",
            "stage_label": "准备生成",
            "quick_replies": []
        }
    ]


def mock_chat_reply(target_job: str, user_msg_count: int) -> Dict:
    script = build_dialog_script(target_job)
    idx = min(user_msg_count - 1, len(script) - 1)
    if idx < 0:
        idx = 0
    return script[idx]


def mock_resume(target_job: str = "产品经理") -> Dict:
    job = target_job or "产品经理"
    return {
        "basic": {
            "fullname": "李同学",
            "target_job": job,
            "email": "li.student@example.com",
            "phone": "138 0000 0000",
            "location": "上海"
        },
        "education": [
            {
                "school": "某 985 大学",
                "major": "计算机科学与技术",
                "degree": "本科",
                "period": "2021.09 - 2025.06",
                "gpa": "3.7 / 4.0",
                "highlights": ["专业排名前 15%", "获学业奖学金 2 次"]
            }
        ],
        "experiences": [
            {
                "id": "exp_001",
                "title": "校园食堂智能点餐系统",
                "type": "course_project",
                "role": "后端负责人",
                "period": "2023.09 - 2024.01",
                "bullets": [
                    "主导设计基于 Spring Boot 的微服务架构,承载 3000+ 同学的日均点餐请求",
                    "设计并实现 12 个 RESTful API 接口,使用 Redis 缓存热门菜品数据,接口平均响应时间降至 80ms",
                    "推动团队建立代码评审机制,项目在《软件工程》课程中获 A 级评分(年级前 5%)",
                    "深入理解需求分析→架构设计→上线发布的完整研发流程,建立工程化思维"
                ],
                "tag": {"label": "基于真实项目重塑", "level": "high", "color": "green"}
            },
            {
                "id": "exp_002",
                "title": "全国大学生数据分析竞赛",
                "type": "competition",
                "role": "数据分析师",
                "period": "2024.03 - 2024.06",
                "bullets": [
                    "面向城市共享单车调度优化课题,独立完成数据清洗、特征构建与模型搭建",
                    "分析 2 万条出行数据,运用 K-Means 聚类算法识别出 5 类高峰用户行为",
                    "提出基于时段-区域的动态调度方案,模拟测试中预计可降低空载率 18%",
                    "团队获华东赛区三等奖,相关方案被指导老师推荐至校创新创业中心"
                ],
                "tag": {"label": "基于赛事经历重塑", "level": "high", "color": "green"}
            },
            {
                "id": "exp_003",
                "title": "校学生会信息中心",
                "type": "club",
                "role": "技术干事",
                "period": "2022.09 - 2023.06",
                "bullets": [
                    "负责学生会公众号日常运营,期间策划并发布 30+ 篇推文,平均阅读量提升 40%",
                    "搭建表单系统替代纸质流程,将活动报名效率提升约 3 倍",
                    "协调 5 人小组完成校庆视频拍摄与剪辑,全网播放量破 5 万次"
                ],
                "tag": {"label": "基于课外实践拔高", "level": "medium", "color": "yellow"}
            }
        ],
        "skills": {
            "technical": ["Java / Spring Boot", "Python", "MySQL / Redis", "Git", "Linux 基础"],
            "product": ["需求分析", "原型设计 (Figma / Axure)", "数据驱动决策", "PRD 撰写"],
            "soft": ["团队协作", "项目推动", "问题拆解"]
        },
        "awards": [
            "2024 全国大学生数据分析大赛华东赛区三等奖",
            "2023 校三好学生",
            "2022-2024 校学业奖学金(共 2 次)"
        ],
        "self_evaluation": (
            "具备扎实的工程能力与产品思维,能够主导从 0 到 1 的项目落地。"
            "善于在不同角色间灵活切换,乐于在跨团队协作中创造价值。"
        )
    }


def mock_quality_report(from_upload: bool = False, source_file: str = None) -> Dict:
    return {
        "total_score": 82,
        "grade": "优秀",
        "grade_color": "#10B981",
        "dimensions": [
            {"name": "完整度", "score": 88, "max": 100, "desc": "简历各模块齐全,结构清晰"},
            {"name": "量化度", "score": 72, "max": 100, "desc": "部分经历缺少具体数字"},
            {"name": "专业度", "score": 85, "max": 100, "desc": "用词专业,动词有力"},
            {"name": "匹配度", "score": 80, "max": 100, "desc": "与目标岗位关键词对齐度较高"},
            {"name": "可信度", "score": 90, "max": 100, "desc": "内容真实可追溯"}
        ],
        "highlights": [
            {
                "title": "内容真实可信",
                "score": 90,
                "desc": "所有经历均基于真实对话生成,包装度合理,未触及诚信红线。",
                "icon": "shield"
            },
            {
                "title": "结构完整专业",
                "score": 88,
                "desc": "简历包含教育、项目、技能、获奖等核心模块,符合企业 HR 阅读习惯。",
                "icon": "check"
            }
        ],
        "improvements": [
            {
                "title": "经历数量偏少",
                "score": 60,
                "desc": "目前仅识别到 3 段项目/实习经历,大学生简历建议至少 3~5 段。是否还有课程项目、社团活动、志愿服务、兼职、竞赛经历未填写?",
                "target_exp_id": None,
                "evidence": "",
                "actions": [
                    {
                        "original": "",
                        "suggestion": "补充一段「实习经历(哪怕只有 1~2 个月的远程/线上实习)」,套用 STAR-L 法则展开",
                        "reason": "学生简历缺少实习是常见短板"
                    },
                    {
                        "original": "",
                        "suggestion": "补充一段「志愿服务 / 公益项目」,体现责任感和软技能",
                        "reason": "丰富经历类型提升整体竞争力"
                    },
                    {
                        "original": "",
                        "suggestion": "补充一段「课题研究 / 老师带的科研小项目」",
                        "reason": "学术与工程能力兼备的信号"
                    }
                ]
            },
            {
                "title": "量化度偏低",
                "score": 72,
                "desc": "经历「校学生会信息中心」中部分 bullet 缺少具体数字,以下是改写示例。",
                "target_exp_id": "exp_003",
                "evidence": "搭建表单系统替代纸质流程,将活动报名效率提升约 3 倍",
                "actions": [
                    {
                        "original": "搭建表单系统替代纸质流程,将活动报名效率提升约 3 倍",
                        "suggestion": "搭建在线表单系统替代纸质流程,覆盖 8 个学生组织,累计处理 1200+ 条报名,平均节省每场活动 6 小时整理时间",
                        "reason": "把'3 倍'拆成可验证的绝对数字"
                    },
                    {
                        "original": "协调 5 人小组完成校庆视频拍摄与剪辑,全网播放量破 5 万次",
                        "suggestion": "主导 5 人小组完成校庆视频拍摄与剪辑,全网播放量 5.2 万次,登上学校官方微信置顶 3 天",
                        "reason": "补充传播深度的二级证据"
                    },
                    {
                        "original": "",
                        "suggestion": "将'阅读量较多'统一改为'平均阅读量 400+,最高单篇 1.2 万'",
                        "reason": "用绝对数字替代模糊词"
                    }
                ]
            },
            {
                "title": "岗位匹配度可优化",
                "score": 80,
                "desc": "目标岗位「产品经理」的核心关键词如「用户调研」「数据分析」「产品迭代」等出现频次还可提升。",
                "target_exp_id": "exp_001",
                "evidence": "设计并实现 12 个 RESTful API 接口,使用 Redis 缓存热门菜品数据,接口平均响应时间降至 80ms",
                "actions": [
                    {
                        "original": "设计并实现 12 个 RESTful API 接口,使用 Redis 缓存热门菜品数据,接口平均响应时间降至 80ms",
                        "suggestion": "在上线前完成 30 份学生用户调研,基于反馈迭代 3 版交互原型后再设计 12 个 RESTful 接口,接口平均响应时间降至 80ms",
                        "reason": "在技术动作前置一段产品视角的用户调研 / 迭代"
                    },
                    {
                        "original": "",
                        "suggestion": "技能板块新增『产品工具:Figma、Axure、墨刀、数据看板』",
                        "reason": "命中产品经理 JD 中的工具关键词"
                    },
                    {
                        "original": "",
                        "suggestion": "把『校园食堂智能点餐系统』调到经历列表第一位",
                        "reason": "该项目和产品经理最相关,前置提升匹配度"
                    }
                ]
            }
        ],
        "action_guide": "聚焦量化补充与关键词优化,按建议修改 3-5 处,预计总分可提升至 88 分以上。",
        "integrity_statement": "本简历所有内容均基于你的真实对话生成,AI 仅做专业性重述与合理拔高,未编造任何不存在的经历。",
        "from_upload": from_upload,
        "source_file": source_file
    }


# ============ 职位数据库 ============

JOB_DATABASE = [
    {"id": "job_001", "title": "产品经理（校招）", "company": "字节跳动", "salary": "18-25K", "location": "北京", "tags": ["大厂", "校招"], "description": "负责短视频产品用户增长方向，通过数据分析和用户调研推动产品迭代。要求：具备产品思维、数据敏感度，熟悉原型设计工具，有相关实习或项目经历优先。", "requirements": ["产品思维", "数据分析", "Figma", "用户调研", "执行力"]},
    {"id": "job_002", "title": "Java后端开发", "company": "阿里巴巴", "salary": "20-28K", "location": "杭州", "tags": ["大厂", "校招"], "description": "参与电商交易系统后端研发，负责高并发场景下的接口设计与优化。要求：扎实的Java基础，熟悉Spring Boot/MyBatis，了解MySQL和Redis。", "requirements": ["Java", "Spring Boot", "MySQL", "Redis", "数据结构"]},
    {"id": "job_003", "title": "前端开发工程师", "company": "拼多多", "salary": "16-22K", "location": "上海", "tags": ["大厂"], "description": "参与拼多多商家平台前端开发，使用Vue/React技术栈。要求：熟悉HTML/CSS/JS，了解现代前端框架，有项目经验。", "requirements": ["Vue.js", "JavaScript", "CSS", "React", "TypeScript"]},
    {"id": "job_004", "title": "产品助理", "company": "小红书", "salary": "12-18K", "location": "上海", "tags": ["中厂", "校招"], "description": "协助产品经理完成需求文档撰写、用户调研、竞品分析和数据看板搭建。要求：逻辑清晰、文字表达强，有用户访谈经验。", "requirements": ["需求分析", "PRD撰写", "用户研究", "Excel", "沟通能力"]},
    {"id": "job_005", "title": "数据分析师", "company": "美团", "salary": "15-22K", "location": "北京", "tags": ["大厂", "急招"], "description": "负责外卖业务数据分析，搭建指标体系，输出策略建议。要求：熟练使用SQL、Python，有数据分析和可视化项目经验。", "requirements": ["SQL", "Python", "数据可视化", "统计分析", "业务理解"]},
    {"id": "job_006", "title": "运营专员", "company": "B站", "salary": "10-15K", "location": "上海", "tags": ["中厂", "校招"], "description": "负责B站内容生态运营，策划活动提升UP主活跃度。要求：对内容社区有热爱，脑洞大，执行力强。", "requirements": ["活动策划", "文案撰写", "数据分析", "用户运营", "跨部门沟通"]},
    {"id": "job_007", "title": "软件测试工程师", "company": "华为", "salary": "15-20K", "location": "深圳", "tags": ["大厂", "校招"], "description": "负责5G通信产品的软件测试，包括自动化测试脚本编写和测试工具开发。要求：掌握至少一门编程语言，有测试理论基础。", "requirements": ["Python", "Java", "自动化测试", "Linux", "问题排查"]},
    {"id": "job_008", "title": "AI产品实习生", "company": "百度", "salary": "8-12K", "location": "北京", "tags": ["大厂", "实习"], "description": "参与AI对话产品设计，收集用户反馈，撰写产品需求。要求：对LLM/AIGC有理解，逻辑思维强，一周至少4天。", "requirements": ["产品思维", "AI理解", "PRD撰写", "数据分析", "沟通能力"]},
    {"id": "job_009", "title": "后端开发（Python）", "company": "知乎", "salary": "14-20K", "location": "北京", "tags": ["中厂"], "description": "负责知乎内容推荐系统后端服务开发，包括Feed流和搜索排序。要求：精通Python，熟悉Django/Flask，了解推荐算法。", "requirements": ["Python", "Django", "Flask", "MySQL", "Redis", "系统设计"]},
    {"id": "job_010", "title": "市场管培生", "company": "宝洁", "salary": "13-17K", "location": "广州", "tags": ["外企", "校招"], "description": "轮岗制管培项目，涉及品牌市场、消费者洞察、数字营销等方向。要求：英语流利，数据分析能力强，具备领导力潜力。", "requirements": ["英语六级", "数据分析", "项目管理", "沟通表达", "领导力"]},
    {"id": "job_011", "title": "全栈开发工程师", "company": "快手", "salary": "18-26K", "location": "北京", "tags": ["大厂", "急招"], "description": "负责快手创作者平台全栈开发，前后端都需要接触。要求：熟练掌握一种前端框架和一种后端语言。", "requirements": ["Vue.js", "Node.js", "MySQL", "Redis", "系统设计"]},
    {"id": "job_012", "title": "用户研究员", "company": "小米", "salary": "12-18K", "location": "北京", "tags": ["大厂", "校招"], "description": "负责手机和IoT产品的用户研究，包括定性访谈和定量问卷分析。要求：了解用户研究方法论，有访谈和数据分析经验。", "requirements": ["用户访谈", "问卷设计", "SPSS", "同理心", "报告撰写"]},
    {"id": "job_013", "title": "iOS开发工程师", "company": "网易", "salary": "15-22K", "location": "杭州", "tags": ["大厂", "校招"], "description": "负责网易云音乐iOS客户端的功能开发与性能优化。要求：熟悉Swift/OC，了解iOS开发框架，有上架App经验优先。", "requirements": ["Swift", "Objective-C", "UIKit", "网络编程", "性能优化"]},
    {"id": "job_014", "title": "游戏策划", "company": "米哈游", "salary": "16-24K", "location": "上海", "tags": ["大厂", "校招"], "description": "负责原神/星穹铁道等项目的关卡设计和玩法策划。要求：热爱游戏，有丰富的游戏体验，逻辑分析能力强。", "requirements": ["策划思维", "文档撰写", "沟通协作", "逻辑推理", "数值设计"]},
    {"id": "job_015", "title": "项目经理助理", "company": "中兴通讯", "salary": "10-14K", "location": "深圳", "tags": ["大厂", "校招"], "description": "协助项目经理跟进通信项目的交付进度，协调资源，管理风险。要求：沟通能力强，有条理，有PMP认证加分。", "requirements": ["项目管理", "沟通协调", "风险管理", "PPT", "抗压能力"]},
    {"id": "job_016", "title": "产品经理实习生", "company": "得物", "salary": "6-10K", "location": "上海", "tags": ["中厂", "实习"], "description": "参与得物App社区板块的产品设计，协助完成需求分析和可用性测试。要求：对潮流文化有兴趣，有原型设计能力。", "requirements": ["产品思维", "原型设计", "Figma", "用户调研", "执行力"]},
    {"id": "job_017", "title": "数据工程师", "company": "京东", "salary": "18-26K", "location": "北京", "tags": ["大厂", "急招"], "description": "负责京东物流数据仓库的构建和维护，包括ETL流程设计和数据质量监控。要求：熟悉Hadoop/Spark生态，有大数据项目经验。", "requirements": ["Spark", "Hadoop", "Python", "SQL", "数据建模"]},
    {"id": "job_018", "title": "技术支持工程师", "company": "深信服", "salary": "8-14K", "location": "深圳", "tags": ["中厂", "校招"], "description": "为客户的网络安全产品提供技术支持，解决配置和故障问题。要求：了解网络协议和Linux系统，有良好的沟通表达能力。", "requirements": ["TCP/IP", "Linux", "网络安全", "沟通表达", "英语"]},
    {"id": "job_019", "title": "产品经理（B端）", "company": "用友", "salary": "14-20K", "location": "北京", "tags": ["中厂", "校招"], "description": "负责企业财税管理软件的产品规划和迭代。要求：对企业管理有兴趣，逻辑严谨，有B端产品认知。", "requirements": ["产品思维", "B端理解", "PRD撰写", "逻辑思维", "沟通表达"]},
    {"id": "job_020", "title": "Python爬虫工程师", "company": "汽车之家", "salary": "12-18K", "location": "上海", "tags": ["中厂", "急招"], "description": "负责汽车之家数据采集平台的开发和维护。要求：精通Python爬虫相关库，了解反爬机制。", "requirements": ["Python", "Scrapy", "反爬对抗", "MySQL", "MongoDB"]},
]

KW_MAP = {
    "产品经理": ["产品思维", "需求分析", "Figma", "PRD撰写", "用户调研", "数据分析", "原型设计"],
    "产品": ["产品思维", "需求分析", "Figma", "PRD撰写", "用户调研", "数据分析", "原型设计"],
    "后端开发": ["Java", "Spring Boot", "Python", "MySQL", "Redis", "系统设计", "数据结构"],
    "Java": ["Java", "Spring Boot", "MySQL", "Redis", "数据结构", "系统设计"],
    "后端": ["Java", "Python", "MySQL", "Redis", "系统设计", "数据结构"],
    "前端": ["Vue.js", "JavaScript", "React", "CSS", "TypeScript", "HTML"],
    "数据分析": ["SQL", "Python", "数据可视化", "统计分析", "Excel"],
    "测试": ["Python", "Java", "自动化测试", "Linux", "问题排查"],
    "运营": ["活动策划", "文案撰写", "数据分析", "用户运营"],
}


def _calc_match(target_job: str, job: dict) -> dict:
    t = (target_job or "").lower()
    keywords = []
    for k, v in KW_MAP.items():
        if k.lower() in t:
            keywords = v
            break
    if not keywords:
        keywords = job["requirements"][:4]

    match_count = 0
    matched = []
    for req in job["requirements"]:
        for kw in keywords:
            if kw.lower() in req.lower() or req.lower() in kw.lower():
                match_count += 1
                matched.append(kw)
                break

    score = round((match_count / len(job["requirements"])) * 100) if job["requirements"] else 50
    return {"score": score, "matched_keywords": matched}


def mock_job_search(keyword: str = "", target_job: str = "") -> dict:
    import time
    kw = (keyword or target_job or "").lower()
    if not kw or len(kw) < 2:
        results = JOB_DATABASE[:12]
    else:
        results = [j for j in JOB_DATABASE if
                   kw in j["title"].lower() or kw in j["company"].lower() or
                   any(kw in t for t in j["tags"]) or
                   any(kw in r.lower() for r in j["requirements"])]
        if not results:
            results = JOB_DATABASE[:8]

    matched = []
    for job in results:
        m = _calc_match(target_job or keyword, job)
        score = m["score"]
        if score >= 85:
            level, reasons = "green", f"岗位要求「{'、'.join(m['matched_keywords'][:3])}」与你的技能高度匹配"
            missing = []
        elif score >= 60:
            missing = [r for r in job["requirements"] if not any(
                mk.lower() in r.lower() or r.lower() in mk.lower() for mk in m["matched_keywords"])]
            reasons = f"匹配度中等，建议微调简历突出「{'、'.join(m['matched_keywords'])}」等技能"
            missing = missing[:2]
            level = "yellow"
        else:
            missing = [r for r in job["requirements"] if not any(
                mk.lower() in r.lower() or r.lower() in mk.lower() for mk in m["matched_keywords"])]
            reasons = f"核心技能「{'、'.join(missing[:3])}」暂不匹配，建议先补足再投递"
            missing = missing[:3]
            level = "red"

        matched.append({
            **job,
            "matchScore": score,
            "matchLevel": level,
            "reasons": reasons,
            "missingSkills": missing
        })

    matched.sort(key=lambda x: x["matchScore"], reverse=True)
    return {"jobs": matched, "total": len(matched)}


def _build_resume_diff(original: dict, adapted: dict, job: dict) -> list:
    sections = []

    # 1. 基本信息
    basic_changes = []
    if original["basic"]["target_job"] != adapted["basic"]["target_job"]:
        basic_changes.append({
            "type": "changed",
            "original": f"求职意向：{original['basic']['target_job']}",
            "adapted": f"求职意向：{adapted['basic']['target_job']}"
        })
    basic_changes.append({
        "type": "unchanged",
        "text": f"姓名：{original['basic']['fullname']}  |  {original['basic']['email']}  |  {original['basic']['phone']}  |  {original['basic']['location']}"
    })
    sections.append({"name": "基本信息", "changes": basic_changes})

    # 2. 教育背景
    edu_changes = [{"type": "unchanged", "text": f"{e['school']}  {e['major']}  {e['degree']}  {e['period']}  GPA {e['gpa']}"} for e in original["education"]]
    sections.append({"name": "教育背景", "changes": edu_changes})

    # 3. 项目经历
    exp_changes = []
    for i, ae in enumerate(adapted["experiences"]):
        oe = original["experiences"][i] if i < len(original["experiences"]) else None
        if oe is None:
            exp_changes.append({"type": "added", "text": ae["title"] + "（新增）"})
            for b in ae["bullets"]:
                exp_changes.append({"type": "added", "text": "• " + b})
            continue
        exp_changes.append({"type": "unchanged", "text": f"{ae['title']}  |  {ae['role']}  |  {ae['period']}"})
        for j, ab in enumerate(ae["bullets"]):
            ob = oe["bullets"][j] if j < len(oe["bullets"]) else None
            if ob is None:
                exp_changes.append({"type": "added", "text": "• " + ab})
            elif ab != ob:
                exp_changes.append({"type": "changed", "original": "• " + ob, "adapted": "• " + ab})
            else:
                exp_changes.append({"type": "unchanged", "text": "• " + ab})
    sections.append({"name": "项目经历", "changes": exp_changes})

    # 4. 技能清单
    skill_changes = []
    if adapted["skills"].get("highlight"):
        skill_changes.append({"type": "added", "text": "🎯 重点技能：" + "、".join(adapted["skills"]["highlight"])})
    for key, label in [("technical", "技术栈"), ("product", "产品能力"), ("soft", "软技能")]:
        o_skills = original["skills"].get(key, [])
        a_skills = adapted["skills"].get(key, [])
        all_skills = list(dict.fromkeys(o_skills + a_skills))
        if all_skills:
            skill_changes.append({"type": "unchanged", "text": f"{label}：{'、'.join(all_skills)}"})
    sections.append({"name": "技能清单", "changes": skill_changes})

    # 5. 获奖荣誉
    award_changes = [{"type": "unchanged", "text": a} for a in original["awards"]]
    sections.append({"name": "获奖荣誉", "changes": award_changes})

    # 6. 自我评价
    if adapted.get("self_evaluation") != original.get("self_evaluation"):
        sections.append({"name": "自我评价", "changes": [{"type": "changed", "original": original["self_evaluation"], "adapted": adapted["self_evaluation"]}]})
    else:
        sections.append({"name": "自我评价", "changes": [{"type": "unchanged", "text": original["self_evaluation"]}]})

    return sections


def mock_adapt_resume(job_id: str = "", target_job: str = "") -> dict:
    import copy
    job = next((j for j in JOB_DATABASE if j["id"] == job_id), JOB_DATABASE[0])
    original = mock_resume(target_job or "产品经理")
    match = _calc_match(target_job or "产品经理", job)

    # 高匹配（≥85）：简历无需修改，返回原简历全文（sections 全为 unchanged）
    if match["score"] >= 85:
        clone = copy.deepcopy(original)
        return {
            "jobId": job_id,
            "matchLevel": "green",
            "noChange": True,
            "originalScore": 86,
            "adaptedScore": 86,
            "originalResume": original,
            "adaptedResume": clone,
            "sections": _build_resume_diff(original, clone, job),
            "changes": [],
            "adapted": False
        }

    adapted = copy.deepcopy(original)
    adapted["basic"]["target_job"] = job["title"]
    if adapted["experiences"]:
        kw = "、".join(job["requirements"][:3])
        adapted["experiences"][0]["bullets"][0] += f"。项目过程中运用{kw}相关能力"
    adapted["skills"]["highlight"] = job["requirements"][:4]
    is_yellow = match["score"] >= 60
    return {
        "jobId": job_id,
        "matchLevel": "yellow" if is_yellow else "red",
        "noChange": False,
        "originalScore": 76 if is_yellow else 62,
        "adaptedScore": 85 if is_yellow else 74,
        "originalResume": original,
        "adaptedResume": adapted,
        "sections": _build_resume_diff(original, adapted, job),
        "changes": [
            f"将目标岗位调整为「{job['title']}」",
            f"突出强调技能：{'、'.join(job['requirements'][:3])}",
            "经历描述中融入岗位关键词",
        ],
        "adapted": True
    }


def mock_apply_job(job_id: str = "", resume_version: str = "original") -> dict:
    import time, datetime
    job = next((j for j in JOB_DATABASE if j["id"] == job_id), JOB_DATABASE[0])
    now = datetime.datetime.now().isoformat()
    app_id = "app_" + hex(int(time.time() * 1000))[2:]
    return {
        "applicationId": app_id,
        "jobId": job_id,
        "jobTitle": job["title"],
        "company": job["company"],
        "resumeVersion": resume_version,
        "appliedAt": now,
        "status": "applied",
        "statusLabel": "已投递",
        "statusHistory": [{"status": "applied", "at": now, "label": "简历已投递"}]
    }


def mock_get_applications() -> dict:
    import datetime
    now = datetime.datetime.now().isoformat()
    d1 = (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat()
    d2 = (datetime.datetime.now() - datetime.timedelta(days=5)).isoformat()
    d3 = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
    d4 = (datetime.datetime.now() - datetime.timedelta(days=4)).isoformat()
    d5 = (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat()
    return {
        "applications": [
            {"id": "app_a1", "jobId": "job_001", "jobTitle": "产品经理（校招）", "company": "字节跳动", "resumeVersion": "original", "appliedAt": d1, "status": "interviewing", "statusLabel": "面试邀约", "statusHistory": [{"status": "applied", "at": d1, "label": "简历已投递"}, {"status": "screened", "at": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(), "label": "简历通过筛选"}, {"status": "interviewing", "at": (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat(), "label": "面试邀约"}]},
            {"id": "app_a2", "jobId": "job_004", "jobTitle": "产品助理", "company": "小红书", "resumeVersion": "adapted", "appliedAt": d2, "status": "screened", "statusLabel": "简历筛选", "statusHistory": [{"status": "applied", "at": d2, "label": "简历已投递"}, {"status": "screened", "at": (datetime.datetime.now() - datetime.timedelta(days=4)).isoformat(), "label": "简历通过筛选"}]},
            {"id": "app_a3", "jobId": "job_008", "jobTitle": "AI产品实习生", "company": "百度", "resumeVersion": "original", "appliedAt": d3, "status": "offered", "statusLabel": "已获Offer", "statusHistory": [{"status": "applied", "at": d3, "label": "简历已投递"}, {"status": "screened", "at": (datetime.datetime.now() - datetime.timedelta(days=6)).isoformat(), "label": "简历通过筛选"}, {"status": "interviewing", "at": (datetime.datetime.now() - datetime.timedelta(days=4)).isoformat(), "label": "面试邀约"}, {"status": "offered", "at": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(), "label": "已获Offer"}]},
            {"id": "app_a4", "jobId": "job_005", "jobTitle": "数据分析师", "company": "美团", "resumeVersion": "original", "appliedAt": d4, "status": "rejected", "statusLabel": "未通过筛选", "statusHistory": [{"status": "applied", "at": d4, "label": "简历已投递"}, {"status": "rejected", "at": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(), "label": "简历未通过筛选"}]},
            {"id": "app_a5", "jobId": "job_006", "jobTitle": "运营专员", "company": "B站", "resumeVersion": "adapted", "appliedAt": d5, "status": "applied", "statusLabel": "已投递", "statusHistory": [{"status": "applied", "at": d5, "label": "简历已投递"}]},
        ],
        "stats": {"total": 5, "screened": 4, "interviewing": 2, "offered": 1, "rejected": 1}
    }


def mock_update_application_status(application_id: str = "", status: str = "") -> dict:
    import datetime
    label_map = {
        "applied": "已投递", "screened": "简历通过筛选", "interviewing": "面试邀约",
        "offered": "已获Offer", "rejected": "未通过筛选", "withdrawn": "已撤回"
    }
    return {
        "applicationId": application_id,
        "status": status,
        "statusLabel": label_map.get(status, status),
        "updatedAt": datetime.datetime.now().isoformat()
    }
