"""把一个 agent 定义 + 技能 + 输入，组装成一次 LLM 调用，并强制校验产物。

## 这个文件是"无人值守模式"的核心

Agent packages 中的 `AGENT.md`、`SKILL.md` 与 `schemas/*.json` 是 harness-neutral 纯文本。
之前是你所在的 coding agent 去读它们；现在这里做同样的事，
只不过读完之后是发给一个 API。

**同一套内容，两种执行方式。** 角色定义、技能、契约一个字都不用改——
这正是前面几轮把内容与 harness 解耦的回报。

## 三件必须由代码做、不能靠提示词的事

1. **只喂该看的数据**：`dataset_blocks` 在 frontmatter 里声明，这里按它裁剪。
   既省 token，也让"只读这些"从一句纪律变成一个机制。
2. **强制 schema 校验**：模型说完不算数，过不了 schema 就打回重来（带着错误一起）。
3. **禁止空转**：重试有上限，超预算立刻停。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.agent_registry import agent_file, read_meta, skill_files
from core.paths import REPO_ROOT
from .llm import Budget, LLMError, complete, load_models_config, parse_json, resolve_provider

# 每个 agent 该看 dataset 里的哪几块。写在这里而不是让模型自己挑，
# 是因为"少看一点"既省钱又防串味——板块分析师不需要知道你的持仓。
DEFAULT_BLOCKS = {
    "market-analyst": ["calendar", "index_spot", "index_intraday", "index_hist", "breadth"],
    "sector-analyst": ["calendar", "sectors", "sector_flow", "limit_pool", "breadth"],
    "news-analyst": ["calendar", "news", "announcements"],
    "position-advisor": ["calendar", "holdings"],
    "report-writer": [],
}

HARD_RULES = """
【硬性纪律，违反即视为无效产物】
1. 数据缺失就把 status 写成 blocked 并说明原因，**绝不编造任何数字**。
2. 每条结论都要能追溯到输入数据里的具体字段与数值；写不出依据的判断不要写。
3. 不给目标价、不推荐个股、不输出买卖指令。本系统产出的是分析与纪律检查。
4. 只输出一个 JSON 对象，不要 Markdown 代码块，不要任何解释性文字。
5. 严格符合给定的 JSON Schema：必填字段一个都不能少，枚举值只能用给定的那些。
"""


def _body(md: Path) -> str:
    """去掉 frontmatter，留下给模型读的正文。"""
    text = md.read_text(encoding="utf-8")
    parts = text.split("---")
    return "---".join(parts[2:]).strip() if text.startswith("---") and len(parts) >= 3 else text


def agent_meta(name: str) -> dict:
    try:
        return read_meta(agent_file(name))
    except (FileNotFoundError, ValueError) as e:
        raise LLMError(str(e)) from e


def build_system(name: str) -> str:
    """system 提示词 = 角色定义 + 它声明的技能 + 硬性纪律。"""
    meta = agent_meta(name)
    definition = agent_file(name)
    chunks = [f"你是本系统的 `{name}`（{meta.get('display_name')}）。",
              "以下是你的角色定义，请严格按它工作。", "", "===== 角色定义 =====",
              _body(definition)]
    for skill in skill_files(definition, meta):
        chunks += ["", f"===== 技能：{skill.parent.name} =====", _body(skill)]
    chunks += ["", HARD_RULES]
    return "\n".join(chunks)


def slim_dataset(dataset: dict, blocks: list[str]) -> dict:
    """只保留该 agent 需要的数据块。

    不只是省 token——`sector-analyst` 拿不到 `holdings`，
    它就**不可能**替你的持仓找理由。纪律靠机制保证，比靠叮嘱可靠。
    """
    if not blocks:
        return {}
    return {
        "run_id": dataset.get("run_id"), "as_of": dataset.get("as_of"),
        "mode": dataset.get("mode"), "adjust_mode": dataset.get("adjust_mode"),
        "data_source": dataset.get("data_source"),
        "blocks": {k: v for k, v in (dataset.get("blocks") or {}).items() if k in blocks},
        "derived": dataset.get("derived"),
        "quality_flags": dataset.get("quality_flags"),
    }


def build_user(name: str, run_dir: Path, *, include_example: bool = True) -> str:
    meta = agent_meta(name)
    blocks = meta.get("dataset_blocks", DEFAULT_BLOCKS.get(name, []))
    parts: list[str] = []

    for rel in meta.get("reads") or []:
        rel = rel.replace("{run_id}", run_dir.name)
        p = REPO_ROOT / rel
        if not p.is_file():
            parts.append(f"===== {rel} =====\n（文件缺失——若它是你必需的输入，"
                         f"请把 status 写成 blocked）")
            continue
        if p.suffix == ".json":
            doc = json.loads(p.read_text(encoding="utf-8"))
            if p.name == "dataset.json":
                doc = slim_dataset(doc, blocks)
            parts.append(f"===== {rel} =====\n"
                         + json.dumps(doc, ensure_ascii=False, indent=1))
        else:
            parts.append(f"===== {rel} =====\n{p.read_text(encoding='utf-8')}")

    schema_rel = meta.get("schema")
    if schema_rel:
        parts.append(f"===== 你的产物必须符合这份 JSON Schema：{schema_rel} =====\n"
                     + (REPO_ROOT / schema_rel).read_text(encoding="utf-8"))
    if include_example:
        artifact = Path(meta["writes"][0]).name
        ex = REPO_ROOT / "workspace" / "runs" / "2026-08-28_example" / artifact
        if ex.is_file():
            parts.append(f"===== 结构参考（全部为虚构假数据，只看字段形状，"
                         f"不要照抄内容）=====\n{ex.read_text(encoding='utf-8')}")

    parts.append(f"现在基于以上输入产出 `{Path(meta['writes'][0]).name}` 的内容。"
                 f"只输出一个 JSON 对象。")
    return "\n\n".join(parts)


def validate(artifact: str, doc: Any) -> list[str]:
    import jsonschema
    from referencing import Registry

    schemas_dir = REPO_ROOT / "schemas"
    resources = [(f.name, json.loads(f.read_text(encoding="utf-8")))
                 for f in sorted(schemas_dir.glob("*.json"))]
    registry = Registry().with_contents(resources)
    schema = json.loads((schemas_dir / f"{artifact}.schema.json").read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema, registry=registry)
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
            for e in sorted(v.iter_errors(doc), key=lambda e: list(e.path))]


def run_agent(name: str, run_dir: Path, *, budget: Budget | None = None,
              max_attempts: int = 2, cfg: dict | None = None,
              log=print) -> tuple[dict, dict]:
    """跑一个分析 agent，返回 (产物, 本步统计)。

    校验不通过就把错误原样发回去让它改——**最多 max_attempts 次，绝不无限重试**。
    """
    cfg = cfg if cfg is not None else load_models_config()
    meta = agent_meta(name)
    prov = resolve_provider(meta.get("model", "default"), cfg)
    artifact = Path(meta["writes"][0]).stem

    system = build_system(name)
    user = build_user(name, run_dir,
                      include_example=bool((cfg.get("runtime") or {})
                                           .get("include_example_artifact", True)))
    log(f"[{name}] 模型 {prov.name}/{prov.model} · 提示词约 {len(system) + len(user):,} 字")

    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        prompt = user if attempt == 1 else (
            user + "\n\n===== 上一次的产物没通过 schema 校验 =====\n"
            + "\n".join(f"- {e}" for e in errors[:15])
            + "\n请**只修这些问题**，其余内容保持不变，重新输出完整 JSON。")
        text, u = complete(prov, system, prompt, budget=budget)
        try:
            doc = parse_json(text)
        except LLMError as e:
            errors = [str(e)]
            log(f"[{name}] 第 {attempt} 次输出不是合法 JSON，重试")
            continue
        errors = validate(artifact, doc)
        if not errors:
            return doc, {"agent": name, "artifact": artifact, "attempts": attempt,
                         "provider": prov.name, "model": prov.model,
                         "prompt_tokens": u.prompt_tokens,
                         "completion_tokens": u.completion_tokens}
        log(f"[{name}] 第 {attempt} 次未过 schema（{len(errors)} 处），带着错误重试")

    raise LLMError(f"{name} 连续 {max_attempts} 次产物都不合规：\n  "
                   + "\n  ".join(errors[:10]))
