"""
用户输入安全过滤 —— prompt injection 防护 + 敏感词过滤

在用户输入进入 LLM prompt 之前进行清洗和校验。
"""
import re
from typing import Optional, Tuple


# 已知的 prompt injection 攻击模式
_INJECTION_PATTERNS = [
    # 试图覆盖 system prompt
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|above|prior)\s+instructions?", re.IGNORECASE),
    re.compile(r"(忽略|无视|忘记|忘掉|抛弃)(掉)?(上面|上述|之前|前面|以上|先前)?(的)?(所有|全部)?(指令|指示|提示|规则|设定|要求|命令)"),
    # 试图扮演新角色
    re.compile(r"you\s+are\s+now\s+(a\s+)?(new\s+)?(role|character|assistant|system)", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\s+you\s+(are|will\s+be|must\s+act\s+as)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are|a\s+different)", re.IGNORECASE),
    re.compile(r"(从现在开始|从此以后|接下来)(,|，)?\s*(你|您)(现在)?(是|将是|要|必须|需要)"),
    re.compile(r"(你|您)(现在)?(是|就是|扮演|模拟|假装|充当)(一个|一名)?(新的)?(角色|系统|助手|管理员|开发者)"),
    # 试图输出 system prompt
    re.compile(r"(print|output|show|reveal|display|tell\s+me)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"what\s+(is|are)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"(输出|打印|显示|展示|告诉我|重复|复述)(一下|下)?(你的)?(系统)?(提示词|prompt|指令|设定|规则)", re.IGNORECASE),
    # 分隔符注入（试图提前结束 prompt 模板）
    re.compile(r"\"{3,}|'{3,}|`{3,}"),  # 三个及以上引号
    # 试图绕过内容限制
    re.compile(r"DAN\s+mode|developer\s+mode|jailbreak", re.IGNORECASE),
    re.compile(r"bypass\s+(content\s+)?(filter|restriction|policy|rule)", re.IGNORECASE),
    re.compile(r"(绕过|突破|解除|取消)(内容)?(过滤|限制|审核|安全|管制)"),
    re.compile(r"开发者模式|越狱模式"),
]

# 敏感词列表（可根据需要扩展）
_SENSITIVE_WORDS = [
    "自杀", "自残", "毒品", "赌博", "色情",
    "暴力恐怖", "违法犯罪", "枪支弹药", "邪教",
]

# 最大用户输入长度（防止超长输入消耗 token）
MAX_USER_INPUT_LENGTH = 4000


def sanitize_user_input(text: str) -> Tuple[str, Optional[str]]:
    """
    清洗用户输入，返回 (清洗后文本, 拦截原因或None)。

    拦截原因非 None 表示输入被拒绝，应返回错误给用户。
    """
    if not text or not text.strip():
        return "", "输入不能为空"

    text = text.strip()

    # 长度检查：超长直接截断继续，不阻断对话
    if len(text) > MAX_USER_INPUT_LENGTH:
        text = text[:MAX_USER_INPUT_LENGTH]

    # 检查 prompt injection 模式
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return "", "输入包含不支持的指令，请用自然语言描述你的经历"

    # 敏感词检查
    text_lower = text.lower()
    for word in _SENSITIVE_WORDS:
        if word in text_lower:
            return "", "输入包含不当内容，请修改后重试"

    return text, None


def sanitize_target_job(text: str) -> str:
    """清洗目标岗位输入（比普通消息更宽松，但限制长度和特殊字符）"""
    if not text:
        return ""
    # 限制长度
    text = text.strip()[:100]
    # 移除可能用于注入的特殊字符序列
    text = re.sub(r"\"{3,}|'{3,}|`{3,}", "", text)
    # 移除换行符
    text = text.replace("\n", " ").replace("\r", " ")
    return text
