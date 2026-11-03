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
5. 工作流每天北京时间 00:00 和 12:47 运行（第二次用于补签）。GitHub 排队可能导致延迟，并不保证准点。

两个游戏需要事先在森空岛账号中绑定。未绑定的游戏不会执行；两个都未绑定会报错。
单个角色失败不会阻止其他角色；有任何失败，工作流最终会显示失败。
使用 GitHub 自带的 Actions 通知查看失败记录；本项目不向第三方推送账号信息。

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
