"""真实模型生成：需求解析、方案规划与代码编写。

阶段三把「关键词匹配出的方案与日志」替换为真实模型调用：

- 需求解析：`deepseek-v4-flash`，由需求文本产出结构化方案（应用名、页面、实体、技术栈）。
- 方案规划与代码编写：`claude-opus-5`，先产出文件清单，再产出可运行的单文件应用。

所有结构化输出统一走「提示词约束 → 完整输出 → JSON 块提取 → 必填字段校验 → 一次修复重试」，
解析或校验失败时抛 `GenerationAIError`，由编排层记录成可见的阶段失败，而不是伪造成功。
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from schemas.aihub import ChatMessage, GenTxtRequest
from services.aihub import AIHubService

logger = logging.getLogger(__name__)

PARSE_MODEL = "deepseek-v4-flash"
CODE_MODEL = "claude-opus-5"
TEST_MODEL = "claude-opus-5"
FIX_MODEL = "claude-opus-5"
ENTRY_FILE = "index.html"

# Hard ceiling for a single model call. A stalled upstream must fail the stage
# with a visible error the user can retry, never hold the request open until the
# gateway times out.
MODEL_CALL_TIMEOUT_SECONDS = 180.0

_JSON_SYSTEM = "你只输出 JSON，不要输出任何解释、Markdown 代码块之外说明或多余文字。"


class GenerationAIError(Exception):
    """模型调用或结构化输出校验失败。"""


def _extract_json_block(text: str) -> str:
    """从模型输出中提取 JSON 主体，兼容 ```json 包裹与前后缀说明。"""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        match = re.search(r"```(?:json)?\s*\n(.*?)```", candidate, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
    start, end = candidate.find("{"), candidate.rfind("}")
    if start >= 0 and end > start:
        return candidate[start : end + 1]
    return candidate


def _describe_model_error(model: str, exc: Exception) -> str:
    """把上游模型异常翻译成用户可读的阶段失败原因。

    模型网关以 SDK 异常形式返回额度不足、限流、鉴权失败等错误。这些异常必须收敛为
    `GenerationAIError`，否则会穿透阶段执行、让接口返回 500（外部则表现为网关错误），
    并且跳过失败落库与额度退款。
    """
    text = str(exc)
    lowered = text.lower()
    if "insufficient_ai_balance" in lowered or "balance is insufficient" in lowered:
        return f"{model} 调用失败：平台 AI 额度不足，请充值后重试"
    if "rate limit" in lowered or "429" in text:
        return f"{model} 调用失败：请求过于频繁，请稍后重试"
    if "401" in text or "403" in text or "permission" in lowered or "unauthorized" in lowered:
        return f"{model} 调用失败：AI 服务授权异常（{type(exc).__name__}）"
    if "timeout" in lowered or "timed out" in lowered or "connection" in lowered:
        return f"{model} 调用失败：AI 服务连接异常，请稍后重试"
    return f"{model} 调用失败：{type(exc).__name__}: {text[:200]}"


async def _complete(system: str, user: str, model: str, max_tokens: int = 4096) -> str:
    service = AIHubService()
    request = GenTxtRequest(
        messages=[
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content=user),
        ],
        model=model,
        stream=False,
        temperature=0.2,
        max_tokens=max_tokens,
    )
    try:
        response = await asyncio.wait_for(service.gentxt(request), timeout=MODEL_CALL_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        logger.warning("%s 调用超过 %s 秒未返回，判定为超时", model, MODEL_CALL_TIMEOUT_SECONDS)
        raise GenerationAIError(
            f"{model} 调用超时（超过 {int(MODEL_CALL_TIMEOUT_SECONDS)} 秒），请稍后重试"
        ) from exc
    except GenerationAIError:
        raise
    except Exception as exc:  # noqa: BLE001 - 上游 SDK 异常必须收敛为阶段失败，不能穿透成 500
        logger.warning("%s 调用失败：%s: %s", model, type(exc).__name__, exc)
        raise GenerationAIError(_describe_model_error(model, exc)) from exc
    content = (response.content or "").strip()
    if not content:
        raise GenerationAIError(f"{model} 返回了空结果")
    return content


def _strip_trailing_commas(text: str) -> str:
    """去掉对象/数组结尾多余的逗号，这是模型输出最常见的小瑕疵。"""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _balance(text: str) -> str:
    """补全被截断的输出：闭合未结束的字符串与未闭合的括号。"""
    in_string = False
    escaped = False
    stack: List[str] = []
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]" and stack:
            if (char == "}" and stack[-1] == "{") or (char == "]" and stack[-1] == "["):
                stack.pop()
    tail = '"' if in_string else ""
    for opener in reversed(stack):
        tail += "}" if opener == "{" else "]"
    return text + tail


def _local_fix(text: str) -> str:
    """本地容错修复：先清理尾随逗号，再补全截断结构，避免为小瑕疵再发一次模型调用。"""
    return _strip_trailing_commas(_balance(_strip_trailing_commas(text)))


def _load(raw: str) -> Dict[str, Any]:
    candidate = _extract_json_block(raw)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        payload = json.loads(_local_fix(candidate))
    if not isinstance(payload, dict):
        raise GenerationAIError("模型输出的 JSON 顶层不是对象")
    return payload


async def _complete_json(system: str, user: str, model: str, max_tokens: int = 4096) -> Dict[str, Any]:
    """获取结构化输出：本地容错 → 失败后用同模型修复一次 → 仍失败则抛错。"""
    raw = await _complete(system, user, model, max_tokens=max_tokens)
    try:
        return _load(raw)
    except json.JSONDecodeError:
        logger.warning("%s 首次输出不是合法 JSON，触发一次修复", model)

    repaired = await _complete(
        "你是 JSON 修复器。把用户给出的内容整理为完整合法的 JSON 对象，只输出 JSON 本身："
        "不要 Markdown 代码块、不要注释、不要省略号、不要省略任何字段，"
        "字符串中的引号必须转义，对象与数组结尾不要多余逗号。",
        raw[:12000],
        model,
        max_tokens=max(max_tokens, 2400),
    )
    try:
        return _load(repaired)
    except json.JSONDecodeError as exc:
        raise GenerationAIError(f"{model} 输出无法解析为 JSON") from exc


def _string_list(payload: Dict[str, Any], key: str, minimum: int = 1) -> List[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GenerationAIError(f"结构化输出缺少数组字段 `{key}`")
    items = [str(item).strip() for item in value if str(item).strip()]
    if len(items) < minimum:
        raise GenerationAIError(f"结构化输出的 `{key}` 至少需要 {minimum} 项")
    return items


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return slug or "atoms-app"


def build_repair_hint(previous_error: Optional[str]) -> str:
    """把上一轮的失败原因整理成修复提示，供重试时注入模型上下文。"""
    error = (previous_error or "").strip()
    if not error:
        return ""
    return f"\n\n上一次构建失败的报错如下，请务必避免同样的问题：\n{error[:1200]}"


async def parse_requirements(prompt: str, template_key: str = "", repair_hint: str = "") -> Dict[str, Any]:
    """解析需求：产出应用标识、展示名、页面清单、数据实体与技术栈。"""
    system = (
        f"{_JSON_SYSTEM} 你是需求分析工程师，负责把自然语言需求拆成可执行的应用方案。"
        "输出字段：app_name（小写英文短横线标识，最多 4 个词）、display_name（中文应用名，不超过 12 字）、"
        "pages（3-6 个页面名）、entities（2-6 个数据实体名）、stack（技术栈名称数组，须包含 React）。"
    )
    user = f"需求：{prompt.strip()}"
    if template_key:
        user += f"\n起点模板：{template_key}"
    user += repair_hint

    payload = await _complete_json(system, user, PARSE_MODEL, max_tokens=1200)
    display_name = str(payload.get("display_name") or "").strip() or prompt.strip()[:12] or "未命名应用"
    app_name = _slug(str(payload.get("app_name") or display_name))
    pages = _string_list(payload, "pages", minimum=2)
    entities = _string_list(payload, "entities", minimum=1)
    stack = _string_list(payload, "stack", minimum=1)
    if not any("react" in item.lower() for item in stack):
        stack.insert(0, "React")
    return {
        "app_name": app_name,
        "display_name": display_name[:40],
        "pages": pages[:8],
        "entities": entities[:8],
        "stack": stack[:6],
    }


async def plan_architecture(prompt: str, spec: Dict[str, Any], repair_hint: str = "") -> Dict[str, Any]:
    """规划方案：产出组件树与文件清单，作为代码生成阶段的输入。"""
    system = (
        f"{_JSON_SYSTEM} 你是技术架构师。针对给定方案输出字段："
        "files（数组，每项含 path 与 purpose，必须包含 index.html 作为入口）、"
        "component_tree（数组，3-6 条组件层级描述）、notes（一句话技术说明）。"
    )
    user = (
        f"需求：{prompt.strip()}\n"
        f"应用：{spec.get('display_name')}（{spec.get('app_name')}）\n"
        f"页面：{'、'.join(spec.get('pages', []))}\n"
        f"数据实体：{'、'.join(spec.get('entities', []))}\n"
        f"技术栈：{'、'.join(spec.get('stack', []))}"
        f"{repair_hint}"
    )
    payload = await _complete_json(system, user, CODE_MODEL, max_tokens=2600)
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise GenerationAIError("方案输出缺少文件清单")
    normalized: List[Dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        normalized.append({"path": path, "purpose": str(item.get("purpose") or "").strip()})
    if not any(item["path"] == ENTRY_FILE for item in normalized):
        normalized.insert(0, {"path": ENTRY_FILE, "purpose": "应用入口"})
    tree = payload.get("component_tree")
    return {
        "files": normalized[:12],
        "component_tree": [str(node).strip() for node in tree if str(node).strip()][:8]
        if isinstance(tree, list)
        else [],
        "notes": str(payload.get("notes") or "").strip(),
    }


async def write_application(
    prompt: str,
    spec: Dict[str, Any],
    plan: Dict[str, Any],
    repair_hint: str = "",
) -> Dict[str, Any]:
    """代码编写：产出可独立运行的单文件应用，返回入口内容与实现摘要。"""
    system = (
        f"{_JSON_SYSTEM} 你是前端工程师。产出一个自包含、可直接打开运行的单文件应用。"
        "输出字段：files（数组，首项必须是 path=index.html，content 为完整 HTML，"
        "内联全部 CSS 与 JavaScript，不引用任何外部资源或构建产物）、summary（一句话实现说明）。"
        "HTML 必须包含 <!DOCTYPE html>、<html lang>、<head>、<body>，界面使用深色背景 #0b0c0e、"
        "主色 #c8f751、中文文案，并实现真实可交互的界面（无需真实后端，用内置数据）。"
    )
    user = (
        f"需求：{prompt.strip()}\n"
        f"应用名：{spec.get('display_name')}\n"
        f"需要覆盖的页面/视图：{'、'.join(spec.get('pages', []))}\n"
        f"需要展示的数据实体：{'、'.join(spec.get('entities', []))}\n"
        f"技术栈：{'、'.join(spec.get('stack', []))}\n"
        f"文件清单：{'、'.join(item['path'] for item in plan.get('files', []))}\n"
        f"组件树：{'；'.join(plan.get('component_tree', []))}"
        f"{repair_hint}"
    )
    payload = await _complete_json(system, user, CODE_MODEL, max_tokens=8192)
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise GenerationAIError("代码输出缺少文件内容")
    entry_content = ""
    written: List[str] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        content = item.get("content")
        if not path or not isinstance(content, str) or not content.strip():
            continue
        written.append(path)
        if path == ENTRY_FILE:
            entry_content = content
    if not entry_content:
        first = next((item for item in files if isinstance(item, dict) and isinstance(item.get("content"), str)), None)
        if first is None:
            raise GenerationAIError("代码输出中没有可用的文件内容")
        entry_content = str(first["content"])
        written.append(ENTRY_FILE)
    entry_content = entry_content.strip()
    missing = [tag for tag in ("<html", "</html>", "<body") if tag not in entry_content.lower()]
    if missing:
        raise GenerationAIError(f"生成的入口文件结构不完整，缺少 {'、'.join(missing)}")
    return {
        "entry": ENTRY_FILE,
        "files": written,
        "content": entry_content,
        "summary": str(payload.get("summary") or "").strip(),
    }


# 测试用例类型：结构（标签/区块存在性）、交互（脚本与事件绑定）、内容（文案与业务标签）。
CASE_TYPES = ("structure", "behavior", "content")
_HTML_EXCERPT_LIMIT = 6000


def _html_excerpt(html: str) -> str:
    """产物可能很大，只截取前段内容，控制单次调用的输入成本。"""
    return (html or "")[:_HTML_EXCERPT_LIMIT]


async def write_test_cases(
    spec: Dict[str, Any],
    plan: Dict[str, Any],
    html: str,
    minimum: int = 6,
    repair_hint: str = "",
) -> List[Dict[str, str]]:
    """根据方案与真实产物内容产出可自动执行的测试用例。

    `assertion` 是能在产物源码中直接匹配的字面量，执行阶段据此做确定性断言；
    模型只负责「找出值得验证的点」，是否通过由真实产物决定，不由模型判定。
    """
    system = (
        f"{_JSON_SYSTEM} 你是测试工程师，为给定的单文件 Web 应用产出可自动执行的测试用例。"
        "输出字段：cases（数组，6-10 项，每项含 title、case_type、preconditions、steps、expected、assertion）。"
        "case_type 只能取 structure（结构：按钮、表单、标题、区块等标签是否存在）、"
        "behavior（交互：脚本与事件绑定是否实现）、content（内容：中文文案与业务标签是否出现）。"
        "assertion 必须是能在产物 HTML 源码中直接匹配的小写字面量片段，例如 \"<button\"、\"addeventlistener\"、"
        "\"<h1\"、\"新增\”；不要写正则表达式、不要带引号包裹、不要写解释或空格占位。"
        "title 用简短中文描述这条用例在验证什么；steps 说明人工复核时的操作；expected 说明预期结果。"
        "用例要覆盖该应用真实存在的界面与文案，不要臆造产物中没有的元素。"
    )
    user = (
        f"应用：{spec.get('display_name')}（{spec.get('app_name')}）\n"
        f"页面：{'、'.join(spec.get('pages', []))}\n"
        f"数据实体：{'、'.join(spec.get('entities', []))}\n"
        f"技术栈：{'、'.join(spec.get('stack', []))}\n"
        f"文件清单：{'、'.join(item.get('path', '') for item in plan.get('files', []) if isinstance(item, dict))}\n"
        f"组件树：{'；'.join(plan.get('component_tree', []))}\n"
        f"产物源码节选：\n{_html_excerpt(html)}"
        f"{repair_hint}"
    )
    payload = await _complete_json(system, user, TEST_MODEL, max_tokens=2600)
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise GenerationAIError("测试用例输出缺少 `cases` 数组")

    cases: List[Dict[str, str]] = []
    seen: set = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        assertion = str(item.get("assertion") or "").strip().strip('"').strip("'").strip().lower()
        if not title or not assertion or assertion in seen:
            continue
        case_type = str(item.get("case_type") or "").strip().lower()
        if case_type not in CASE_TYPES:
            case_type = "content"
        seen.add(assertion)
        cases.append(
            {
                "title": title[:120],
                "case_type": case_type,
                "preconditions": str(item.get("preconditions") or "已发布可访问的产物").strip()[:300],
                "steps": str(item.get("steps") or "").strip()[:600],
                "expected": str(item.get("expected") or "").strip()[:300],
                "assertion": assertion[:200],
            }
        )
    if len(cases) < minimum:
        raise GenerationAIError(f"测试用例输出不足 {minimum} 条（实际 {len(cases)} 条）")
    return cases[:12]


# 缺陷修复允许送入模型的源码上限：单文件应用远超此值时无法在一次调用内可靠改写，
# 直接给出可见错误，而不是把被截断的源码交给模型去「猜」剩余部分。
FIX_SOURCE_LIMIT = 48000


async def fix_application(
    prompt: str,
    spec: Dict[str, Any],
    html: str,
    bug_title: str,
    bug_description: str = "",
    reproduction: str = "",
    related_case: str = "",
    repair_hint: str = "",
) -> Dict[str, Any]:
    """按缺陷报告修复单文件应用，返回修复后的完整源码、修复说明与变更清单。

    模型必须输出完整可运行源码而不是差异片段：产物是自包含单文件，差异片段既无法独立校验，
    也无法用于后续的确定性复测。
    """
    source = (html or "").strip()
    if len(source) > FIX_SOURCE_LIMIT:
        raise GenerationAIError(
            f"产物源码超过 {FIX_SOURCE_LIMIT} 字符，超出自动修复范围，请缩小应用规模后重试"
        )
    system = (
        f"{_JSON_SYSTEM} 你是前端工程师，负责修复一个自包含单文件 Web 应用的缺陷。"
        "输出字段：files（数组，首项必须是 path=index.html，content 为修复后的完整 HTML）、"
        "summary（一句话说明这次修复做了什么）、changes（数组，3-6 条，逐条说明改动点）。"
        "content 必须是完整可运行的 HTML：包含 <!DOCTYPE html>、<html lang>、<head>、<body>，"
        "内联全部 CSS 与 JavaScript，不引用任何外部资源。"
        "只做修复该缺陷所需的最小改动，必须保留原有页面、文案、交互与全部既有元素，"
        "不得通过删除或隐藏元素来绕过缺陷。"
    )
    user = (
        f"应用：{spec.get('display_name')}（{spec.get('app_name')}）\n"
        f"原始需求：{prompt.strip()}\n"
        f"缺陷标题：{bug_title}\n"
        f"缺陷描述：{bug_description or '（未提供）'}\n"
        f"复现步骤：{reproduction or '（未提供）'}\n"
        f"关联用例断言（修复后必须仍然匹配）：{related_case or '（无）'}\n"
        f"当前源码：\n{source}"
        f"{repair_hint}"
    )
    payload = await _complete_json(system, user, FIX_MODEL, max_tokens=8192)
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise GenerationAIError("修复输出缺少文件内容")
    content = ""
    for item in files:
        if (
            isinstance(item, dict)
            and str(item.get("path") or "").strip() == ENTRY_FILE
            and isinstance(item.get("content"), str)
        ):
            content = item["content"].strip()
            break
    if not content:
        first = next(
            (
                item
                for item in files
                if isinstance(item, dict) and isinstance(item.get("content"), str) and item["content"].strip()
            ),
            None,
        )
        content = str(first["content"]).strip() if first else ""
    if not content:
        raise GenerationAIError("修复输出中没有可用的入口文件内容")
    missing = [tag for tag in ("<html", "</html>", "<body") if tag not in content.lower()]
    if missing:
        raise GenerationAIError(f"修复后的入口文件结构不完整，缺少 {'、'.join(missing)}")
    changes = payload.get("changes")
    return {
        "content": content,
        "summary": str(payload.get("summary") or "").strip(),
        "changes": [str(item).strip() for item in changes if str(item).strip()][:8]
        if isinstance(changes, list)
        else [],
    }
