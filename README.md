# 现金流 AI SaaS

面向中国企业财务和代账会计的银行流水智能分类工具：

- 管理员可切换 OpenAI 兼容平台、模型和 API Key + 会计准则 Skill 逐行分类
- 自动识别常见银行流水表头和列布局
- 现金流量表（经营/投资/筹资）汇总
- SVG 数据可视化看板
- 7 类可组合财务处理 Skill：现金流、收入费用、往来单位、对账、异常、资金健康、税费
- 8+ 张财务分析报表：现金流量表、资金收支、收入/费用、往来单位、待复核、多账户汇总
- Excel 分类台账与完整财务报表包导出
- 多用户、套餐额度、任务隔离
- SMTP 邮箱验证码注册与防刷限流

## 本地运行

```bash
cd saas
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填写 AI_API_KEY 和 ACCOUNT_SECRET
python3 main.py
```

生产环境使用 Gunicorn。运行数据放在 `saas/data/`，不会提交到 GitHub。

## 安全说明

不要把真实 API Key、数据库、上传流水或导出文件提交到仓库。生产环境建议通过 systemd `EnvironmentFile` 注入密钥。

## 本轮优化

- 使用 `backend-pro-max`：CSRF 防护、安全 Cookie、环境变量密钥、上传文件签名校验、登录限速、用户数据隔离、幂等计费与安全删除。
- 使用 `ui-ux-pro-max`：移动端横向导航、结果表格卡片化、44px 触控目标、响应式图表、焦点可见性、减少动态效果支持和上传反馈。
- 自动化测试覆盖注册登录、CSRF、用户隔离、额度幂等、银行表头识别、金额解析和现金流汇总。

## 测试

```bash
pip install -r requirements-dev.txt
pytest -q
```
