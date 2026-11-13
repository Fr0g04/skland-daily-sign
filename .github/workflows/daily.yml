name: 森空岛每日签到

# 三个触发源互为备份，lost 概率从 33% 降到约 4%：
#   1. GitHub 原生 cron（本文件）—— 主触发，不依赖任何外部调度器
#   2. 云端定时任务 03:07 —— 第二触发，走 workflow_dispatch
#   3. 手动触发 —— 调试用
# 三者都经过 retry_gate.py 幂等门禁：今天已成功就跳过，所以重复触发是安全的。
on:
  workflow_dispatch:
    inputs:
      force:
        description: '强制签到（忽略今天是否已成功）'
        type: boolean
        default: false
  schedule:
    # 北京时间 00:05 —— 主触发。GitHub 的 cron 有 5~20 分钟延迟，属正常。
    # 注意：如果游戏的每日重置晚于这个时间，把这里往后挪，并同步修改下方说明。
    - cron: '5 16 * * *'
    # 北京时间 01:07 —— 兜底触发。此时若 00:05 那次已成功，门禁会直接跳过。
    - cron: '7 17 * * *'

permissions:
  # 原为 read。改为 write 以支持心跳提交，
  # 同时避免"仓库 60 天无活动导致 scheduled workflow 被 GitHub 自动禁用"。
  contents: write
  actions: read

concurrency:
  group: skland-daily
  cancel-in-progress: false

jobs:
  attendance:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: 检查今天是否已签到
        id: gate
        env:
          GITHUB_TOKEN: ${{ github.token }}
          SCHEDULE: ${{ github.event.schedule }}
          FORCE_RUN: ${{ github.event.inputs.force }}
        run: python retry_gate.py

      - name: 离线测试
        if: steps.gate.outputs.run == 'true'
        run: python -m unittest discover -s tests -v

      - name: 两个游戏签到
        id: sign
        if: steps.gate.outputs.run == 'true'
        env:
          SKLAND_TOKENS: ${{ secrets.SKLAND_TOKENS }}
          SKLAND_DID: ${{ secrets.SKLAND_DID }}
        # pipefail 确保脚本失败不会被 tee 掩盖。
        shell: bash
        run: |
          set -o pipefail
          python -u skland.py 2>&1 | tee sign-result.txt

      - name: 发送邮件回执
        id: mail
        if: ${{ always() && !cancelled() && steps.gate.outputs.run == 'true' }}
        env:
          SIGN_OUTCOME: ${{ steps.sign.outcome }}
          # 门禁的裁决直接传进来，notify.py 不再自己查 API——
          # 一处事实只查一次，避免两份实现悄悄不一致。
          ALREADY_TODAY: ${{ steps.gate.outputs.already }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          MAIL_TO: ${{ secrets.MAIL_TO }}
          SKLAND_TOKENS: ${{ secrets.SKLAND_TOKENS }}
          SKLAND_DID: ${{ secrets.SKLAND_DID }}
        run: python notify.py

      # 每天落一次提交，让仓库保持"有活动"状态，防止 cron 被自动禁用。
      # 同时把本次的判定结果写进 .state/，这是唯一不依赖日志的可观测通道。
      # continue-on-error 保证它失败也不会把签到任务带红。
      - name: 心跳提交
        if: ${{ always() }}
        continue-on-error: true
        env:
          GATE_RUN: ${{ steps.gate.outputs.run }}
          GATE_ALREADY: ${{ steps.gate.outputs.already }}
          SIGN_OUTCOME: ${{ steps.sign.outcome }}
          MAIL_OUTCOME: ${{ steps.mail.outputs.mail }}
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p .state
          printf '%s event=%s gate=%s already=%s sign=%s mail=%s\n' \
            "$(date -u +%FT%TZ)" \
            "${GITHUB_EVENT_NAME}" \
            "${GATE_RUN:-none}" \
            "${GATE_ALREADY:-none}" \
            "${SIGN_OUTCOME:-none}" \
            "${MAIL_OUTCOME:-none}" > .state/last-run.txt

          {
            echo "### 本次执行流水"
            echo ""
            echo "| 环节 | 结果 |"
            echo "| --- | --- |"
            echo "| 今天是否已有成功运行 | \`${GATE_ALREADY:-none}\` |"
            echo "| 是否执行签到 | \`${GATE_RUN:-none}\` |"
            echo "| 签到结果 | \`${SIGN_OUTCOME:-none}\` |"
            echo "| 邮件 | \`${MAIL_OUTCOME:-none}\` |"
          } >> "${GITHUB_STEP_SUMMARY}"

          git config user.name  "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add .state
          git diff --staged --quiet && exit 0
          git commit -m "chore: heartbeat $(date -u +%F)"
          git push "https://x-access-token:${{ github.token }}@github.com/${{ github.repository }}.git" "HEAD:${GITHUB_REF_NAME}"
