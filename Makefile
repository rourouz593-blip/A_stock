# 给人用的快捷方式。coding agent 直接用 python tools/astock.py 即可。
PY ?= python3

.DEFAULT_GOAL := help

help:  ## 显示本帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "};{printf "  \033[1m%-12s\033[0m %s\n",$$1,$$2}'

setup:  ## 安装依赖并从 example 生成个人配置
	$(PY) -m pip install -r requirements.txt
	@[ -f config/positions.yaml ]  || cp config/positions.example.yaml  config/positions.yaml
	@[ -f config/thresholds.yaml ] || cp config/thresholds.example.yaml config/thresholds.yaml
	@[ -f .env ] || cp .env.example .env
	@echo "→ 记得填 .env 的 ASTOCK_ACCOUNT_EQUITY 与 config/positions.yaml"

doctor:  ## 环境自检：依赖、配置、网络
	$(PY) tools/astock.py doctor

check:  ## 逐块体检：哪些数据能取到、哪些不能（不跑完整流水线）
	$(PY) tools/astock.py check

budget:  ## 今日请求用量
	$(PY) tools/astock.py budget

store:  ## 本地行情仓库存了什么
	$(PY) tools/astock.py store

review:  ## 跑今日复盘（建 run + 取数 + 进入循环）
	$(PY) tools/astock.py review

next:  ## 我现在该做什么
	$(PY) tools/astock.py next

status:  ## 当前进度
	$(PY) tools/astock.py status

demo:  ## 生成离线示例（不联网）
	$(PY) tools/astock.py demo

sync:  ## 重新生成各 harness 的适配文件
	$(PY) tools/sync_harness.py

test:  ## 跑测试（全 mock，不联网）
	$(PY) -m pytest tests/ -q

clean:  ## 清掉缓存与非示例的 run
	rm -rf workspace/cache .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	find workspace/runs -maxdepth 1 -mindepth 1 -type d ! -name '*_example' -exec rm -rf {} +

.PHONY: help setup doctor check budget store review next status demo sync test clean
