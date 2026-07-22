from pathlib import Path

import pandas as pd

import engine


def test_money_parses_common_formats():
    assert engine.money("1,234.50") == 1234.5
    assert engine.money("￥ 88.00") == 88.0
    assert engine.money("(20.5)") == -20.5
    assert engine.money(12) == 12.0


def test_read_file_detects_header_after_bank_metadata(tmp_path: Path):
    path = tmp_path / "statement.csv"
    path.write_text("账户名称,测试公司\n查询期间,2026-01\n交易日期,摘要,收入,支出\n2026-01-02,销售回款,1000,\n", encoding="utf-8-sig")
    df = engine.read_file(path)
    assert list(df.columns)[:4] == ["交易日期", "摘要", "收入", "支出"]
    assert len(df) == 1


def test_rule_classification_uses_direction():
    income = engine.rule_classify({"summary": "客户货款回款", "counterparty": "甲客户", "remark": "", "direction": "收入", "signed_amount": 1000})
    expense = engine.rule_classify({"summary": "供应商材料货款", "counterparty": "乙供应商", "remark": "", "direction": "支出", "signed_amount": -500})
    assert income["category"] == "销售商品、提供劳务收到的现金"
    assert expense["category"] == "购买商品、接受劳务支付的现金"


def test_cashflow_statement_totals():
    job = {"results": [
        {"category": "销售商品、提供劳务收到的现金", "ctx": {"signed_amount": 1000}, "review": False},
        {"category": "购买商品、接受劳务支付的现金", "ctx": {"signed_amount": -300}, "review": False},
        {"category": "取得借款收到的现金", "ctx": {"signed_amount": 500}, "review": False},
    ]}
    cf = engine.cashflow_statement(job)
    assert cf["net_increase"] == 1200
