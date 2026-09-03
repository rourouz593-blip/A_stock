"""LLM 调用层：provider 无关，按 OpenAI 兼容协议说话。

## 为什么是这一层

在此之前，五个分析步骤是靠**你正坐在里面的那个 coding agent**跑的。
那种模式有两个问题：

1. **跑不了无人值守。** 章节九写着"每个交易日收盘后自动运行"，
   但没人坐在终端前的时候，根本没有东西去做那些判断。
2. **贵。** 每天一次复盘要跑五个推理步骤，
   全压在按会话计费的编码 agent 上，运行成本不可控。

所以这里做一层薄的 provider 抽象：**只要是 OpenAI 兼容的接口就能接**——
DeepSeek、通义、Kimi、智谱、OpenRouter，以及本地的 Ollama / vLLM。
Anthropic 的原生协议单独做了一条分支。

## 三条设计原则

- **不引入 SDK 依赖**：只用 `requests`。每多一个 SDK 就多一次版本冲突，
  而这些服务的协议本身是稳定的。
- **不硬编码价格**：模型价格随时在变，写死的价格半年后就是错的。
  token 用量**永远统计**，价格由你在 `config/models.yaml` 里填，没填就只报用量。
- **超预算就停**：跑飞的循环比跑错的结论更可怕。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.paths import REPO_ROOT


class LLMError(RuntimeError):
    """调用失败。上层应把对应步骤标 failed，而不是拿半截结果往下走。"""


class BudgetExceeded(LLMError):
    """本次 run 的花费/用量已超上限，主动停下。"""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.calls += other.calls


@dataclass
class Provider:
    name: str
    protocol: str          # openai | anthropic
    base_url: str
    api_key_env: str
    model: str
    price_in: float | None = None    # 每百万 输入 token 的价格，自己填
    price_out: float | None = None
    max_tokens: int = 8000
    temperature: float = 0.2
    timeout: int = 180
    extra: dict = field(default_factory=dict)

    @property
    def api_key(self) -> str | None:
        return os.getenv(self.api_key_env) if self.api_key_env else None

    def cost(self, u: Usage) -> float | None:
        if self.price_in is None or self.price_out is None:
            return None
        return round(u.prompt_tokens / 1e6 * self.price_in
                     + u.completion_tokens / 1e6 * self.price_out, 4)


def load_models_config(path: str | Path | None = None) -> dict:
    """读 config/models.yaml，没有就退到 example。"""
    import yaml

    p = Path(path) if path else REPO_ROOT / "config" / "models.yaml"
    if not p.is_file():
        p = REPO_ROOT / "config" / "models.yaml.example"
    if not p.is_file():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def resolve_provider(tier: str = "default", cfg: dict | None = None) -> Provider:
    """按档位（default / fast / reasoning）解析出具体用哪个 provider。

    档位来自 agent package `AGENT.md` frontmatter 的 `model` 字段——
    这样"哪一步值得用更强的模型"是写在角色定义里的，不是散在代码里。
    """
    cfg = cfg if cfg is not None else load_models_config()
    providers = cfg.get("providers") or {}
    tiers = cfg.get("tiers") or {}
    key = tiers.get(tier) or tiers.get("default")
    if not key:
        raise LLMError(
            "config/models.yaml 里没有配置任何模型档位。\n"
            "    cp config/models.yaml.example config/models.yaml 后按注释填一个 provider")
    if key not in providers:
        raise LLMError(f"档位 {tier} 指向的 provider `{key}` 不存在于 providers 里")

    raw = dict(providers[key])
    prov = Provider(
        name=key,
        protocol=raw.get("protocol", "openai"),
        base_url=raw["base_url"].rstrip("/"),
        api_key_env=raw.get("api_key_env", ""),
        model=raw["model"],
        price_in=raw.get("price_per_1m_input"),
        price_out=raw.get("price_per_1m_output"),
        max_tokens=int(raw.get("max_tokens", 8000)),
        temperature=float(raw.get("temperature", 0.2)),
        timeout=int(raw.get("timeout", 180)),
        extra=raw.get("extra") or {},
    )
    if prov.api_key_env and not prov.api_key:
        raise LLMError(
            f"provider `{key}` 需要环境变量 {prov.api_key_env}，但它是空的。\n"
            f"    在 .env 里填上（本项目会自动加载 .env，不用 source）")
    return prov


class Budget:
    """本次 run 的花费闸门。**跑飞的循环比跑错的结论更可怕。**"""

    def __init__(self, max_cost: float | None = None, max_tokens: int | None = None):
        self.max_cost = max_cost
        self.max_tokens = max_tokens
        self.usage = Usage()
        self.cost = 0.0
        self.priced = False          # 有没有配过价格

    def charge(self, prov: Provider, u: Usage) -> None:
        self.usage.add(u)
        c = prov.cost(u)
        if c is not None:
            self.cost += c
            self.priced = True
        if self.max_tokens and self.usage.total > self.max_tokens:
            raise BudgetExceeded(
                f"已用 {self.usage.total:,} token，超过上限 {self.max_tokens:,}。"
                f"调 config/models.yaml 的 budget.max_tokens_per_run，或换个便宜的档位")
        if self.max_cost and self.cost > self.max_cost:
            raise BudgetExceeded(
                f"已花费 {self.cost:.4f}，超过上限 {self.max_cost}。"
                f"调 config/models.yaml 的 budget.max_cost_per_run")

    def report(self) -> dict:
        return {
            "calls": self.usage.calls,
            "prompt_tokens": self.usage.prompt_tokens,
            "completion_tokens": self.usage.completion_tokens,
            "total_tokens": self.usage.total,
            "cost": round(self.cost, 4) if self.priced else None,
            "cost_note": None if self.priced else
            "未在 config/models.yaml 里填价格，只统计 token 用量（价格常变，不写死）",
        }


def _post(url: str, headers: dict, payload: dict, timeout: int, retries: int = 3) -> dict:
    import requests

    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(2 * attempt)      # 限流/服务端错误，退避重试
                continue
            if r.status_code >= 400:
                raise LLMError(f"HTTP {r.status_code}: {r.text[:400]}")
            return r.json()
        except LLMError:
            raise
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(2 * attempt)
    raise LLMError(f"调用失败（重试 {retries} 次）：{last}")


def complete(prov: Provider, system: str, user: str, *,
             json_mode: bool = True, budget: Budget | None = None) -> tuple[str, Usage]:
    """发一次补全请求，返回 (文本, 用量)。

    json_mode：要求模型只输出 JSON。不是所有服务都支持 response_format，
    所以**同时**在提示词里明确要求——双保险，且解析时还会再兜一层。
    """
    if prov.protocol == "anthropic":
        url = f"{prov.base_url}/v1/messages"
        headers = {"x-api-key": prov.api_key or "", "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
        payload = {"model": prov.model, "max_tokens": prov.max_tokens,
                   "temperature": prov.temperature, "system": system,
                   "messages": [{"role": "user", "content": user}], **prov.extra}
        data = _post(url, headers, payload, prov.timeout)
        text = "".join(b.get("text", "") for b in data.get("content", []))
        m = data.get("usage") or {}
        u = Usage(m.get("input_tokens", 0), m.get("output_tokens", 0), 1)
    else:   # OpenAI 兼容：DeepSeek / 通义 / Kimi / 智谱 / OpenRouter / Ollama / vLLM …
        url = f"{prov.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if prov.api_key:
            headers["Authorization"] = f"Bearer {prov.api_key}"
        payload = {"model": prov.model, "max_tokens": prov.max_tokens,
                   "temperature": prov.temperature,
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}], **prov.extra}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            data = _post(url, headers, payload, prov.timeout)
        except LLMError as e:
            # 有些服务不认 response_format，去掉再试一次
            if json_mode and "response_format" in str(e):
                payload.pop("response_format", None)
                data = _post(url, headers, payload, prov.timeout)
            else:
                raise
        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"返回里没有 choices：{str(data)[:300]}")
        text = (choices[0].get("message") or {}).get("content") or ""
        m = data.get("usage") or {}
        u = Usage(m.get("prompt_tokens", 0), m.get("completion_tokens", 0), 1)

    if budget is not None:
        budget.charge(prov, u)
    return text, u


def parse_json(text: str) -> Any:
    """从模型输出里抠出 JSON。

    模型很爱在 JSON 外面裹一层 ```json ``` 或者写几句解释。
    与其在提示词里反复叮嘱，不如在这里稳稳地剥掉——**提示词管不住的事，代码管得住**。
    """
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.lstrip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
        t = t.strip().rstrip("`").strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    end = max(t.rfind("}"), t.rfind("]"))
    if start >= 0 and end > start:
        try:
            return json.loads(t[start:end + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"模型输出不是合法 JSON：{e}；前 200 字：{t[:200]}") from e
    raise LLMError(f"模型输出里找不到 JSON；前 200 字：{t[:200]}")
