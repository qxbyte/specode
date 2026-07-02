import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

DOC_MASK = """---
标题: 银行账号脱敏规则（前六后四）
类型: case
来源: 114371-收付个人数据脱敏需求
tags: [银行账号脱敏, 前六后四, DesensitizeUtils]
描述: 银行账号展示脱敏：保留前六后四，工具类 DesensitizeUtils.mask()。
---

## 定位

- 工具方法 `DesensitizeUtils.mask(String bankAccount)`，长度 <=10 透传。

## 可复用经验 / 坑

- 编辑场景不脱敏，前端保留隐藏真实账号字段。
"""

DOC_AUTH = """---
标题: authorityQueryByPaymentNo 三步查询链路
类型: case
来源: 121659-非见费出单收付登记号授权功能
tags: [SfPlanAuthorityBizImpl, paymentNo, SfPaymentMain]
描述: authorityQuery 按 paymentNo 查询的三步链路。
---

## 定位

- SfPlanAuthorityBizImpl.authorityQueryByPaymentNo → SfPaymentMain 校验 → SfPolicyPayment。
"""

DOC_NAV = """---
标题: 见费出单收款页面前后端定位
类型: navigation
来源: 125577-生成流水号时修改收付机构功能关闭
tags: [SfCodDeal, 见费出单, 见费收款]
描述: 见费出单收款页面与提交接口定位
---

# 见费出单收款页面前后端定位

## 答案路径

- 页面：`SfCodDeal.vue`；新收款：`SfBusinessCredit.credit`。
"""


@pytest.fixture
def kb(tmp_path, monkeypatch):
    """Hermetic 3-doc knowledge base + isolated HOME / HF cache."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    monkeypatch.delenv("HF_ENDPOINT", raising=False)
    root = tmp_path / "knowledge-base"
    (root / "cases").mkdir(parents=True)
    (root / "navigation").mkdir()
    (root / "cases" / "114371-mask-rule.md").write_text(DOC_MASK, encoding="utf-8")
    (root / "cases" / "121659-authority-chain.md").write_text(DOC_AUTH, encoding="utf-8")
    (root / "navigation" / "cod-receipt-page.md").write_text(DOC_NAV, encoding="utf-8")
    return root


@pytest.fixture
def run_cli():
    """Invoke ragkit.py as a CLI subprocess with the (monkeypatched) env."""

    def _run(*args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "ragkit.py"), *args],
            capture_output=True, text=True, env=os.environ.copy(),
        )

    return _run
