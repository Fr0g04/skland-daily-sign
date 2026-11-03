# 森空岛每日签到（国服）

Python 标准库实现，支持明日方舟、明日方舟：终末地的全部已绑定角色。
不包含游戏内每日任务或森空岛社区登岛积分检票。

## GitHub 部署

1. 新建私有仓库 `skland-daily-sign`，把本目录的全部文件上传到默认分支，保留 `.github/workflows/daily.yml`。
2. 在仓库 `Settings → Secrets and variables → Actions → New repository secret` 新增 `SKLAND_TOKENS`。
   值为鹰角通行证 Token（不是短期 cred，也不是 GitHub Token）。多个账号每行一个。
3. 获取 Token：先在官方 https://www.skland.com/ 登录，再访问官方
   https://web-api.skland.com/account/info/hg ，取响应中的 `data.content` 字段值。
   不要把整段 JSON、Cookie 或密码填进 Secret。不要把 Token 发给他人或提交到代码里。
4. 在 `Actions → 森空岛每日签到 → Run workflow` 手动运行，确认两个游戏均成功或明确显示今日已签到。
5. 工作流每天北京时间 00:07 签到，01:07 检查是否需要补签。当天首次定时运行成功则跳过补签；失败、未完成或没有运行记录则补签。GitHub 排队可能导致延迟，并不保证准点。

补签判断以 Actions 工作流的实际成功状态为准，不查询 GitHub 通知是否送达。
判断使用北京时间的自然日；查询 GitHub 运行记录失败时仍执行补签，避免漏签。
GitHub 仍会在 01:07 启动一次检查，满足条件时跳过测试、签到及自定义邮件步骤。
手动运行始终执行，不受补签判断限制。

两个游戏需要事先在森空岛账号中绑定。未绑定的游戏不会执行；两个都未绑定会报错。
单个角色失败不会阻止其他角色；有任何失败，工作流最终会显示失败。
使用 GitHub 自带的 Actions 通知查看失败记录；可按下文配置邮件回执。

## 邮件回执

在仓库 `Settings → Secrets and variables → Actions` 中添加：

| Secret 名称 | 内容 |
| --- | --- |
| `SMTP_HOST` | 发信邮箱服务商提供的 SMTP 服务器地址 |
| `SMTP_USER` | 完整发信邮箱地址，同时作为登录用户名和发件人 |
| `SMTP_PASSWORD` | 邮箱的 SMTP 授权码或应用专用密码，依邮箱服务商要求获取 |
| `MAIL_TO` | 收件邮箱地址；多个地址用英文逗号分隔 |
| `SMTP_PORT` | 可选，默认 `465`（隐式 TLS）；也支持 `587`（STARTTLS） |

先在邮箱设置中启用 SMTP，并按照服务商说明获取授权码，不要提交到代码里。
全部四项必填值都未配置时跳过发信；只配置一部分会报错。
配置完成后到 Actions 手动运行一次，检查邮件步骤和实际收件情况。

每天 00:07 签到、实际执行的01:07 补签及手动运行结束后均会发一封邮件，包括成功/失败状态、
两个游戏各角色的结果和本次运行链接。首次定时运行成功时，01:07 跳过签到及自定义邮件。
如果签到步骤失败，仍会尝试发信；如果工作流被取消、运行环境不可用或网络无法连接，
则不能保证发送。SMTP 接受邮件不等于保证送达，请检查垃圾邮件箱。
邮件发送失败会让工作流显示失败，不会撤销已经成功的签到。
回执不包含 Token、UID 或昵称。工作流会通过所配置的邮箱服务商发送结果至指定收件地址。

## 设备校验与故障

接口不是公开稳定 API。默认通过原生 `/api/v1/user/auth/generate_cred_by_code` 换取短期凭据。
如果提示接口错误 `10001`，不代表签到成功，可能是设备验证或接口发生变化。
可以在官方森空岛网页的浏览器开发者工具 Network 中，查看已登录请求里的 `dId` 请求头，
将真实值保存为可选 Secret `SKLAND_DID`；配置后登录改走网页 `/web/v1` 接口。
脚本不会伪造设备指纹或自动绕过验证；若仍失败，应在官方客户端完成验证后再检查。
Token 或设备信息失效时，需要更新相应 Secret。

公开仓库连续 60 天无活动可能被 GitHub 停用定时任务；建议私有仓库，并留意 Actions 用量。
定时任务必须保存在默认分支。不要在 fork 的不可信代码中配置账号 Secret。

## 本地运行与检查

Python 3.11+，不需要 pip 安装依赖。通过环境变量 `SKLAND_TOKENS` 提供 Token，再运行：

```sh
python -m unittest discover -s tests -v
python skland.py
```

离线测试覆盖签名输入、终末地空请求体与角色头、多角色去重、错误判定和部分失败继续执行。
离线测试不能证明真实账号签到成功；必须配置凭据后以 Actions 运行结果为准。
日志仅显示账号/角色序号和结果，不显示 UID、昵称、Token 或原始接口响应。

## 参考资料

独立实现协议和工作流，没有复制参考项目源文件或发布包。

- 用户提供的历史版本：https://gitee.com/FancyCabbage/skyland-auto-sign/releases/tag/1.2 （2023 年版，仅作历史参考）
- 终末地请求与角色结构：https://github.com/sjtt2/endfield_auto_sign
- 两游戏接口与签名交叉核对：https://github.com/xjwwjx/skland-auto-sign
- GitHub 定时任务说明：https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
