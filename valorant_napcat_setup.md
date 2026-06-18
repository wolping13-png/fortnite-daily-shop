# 无畏契约商店接入说明

这个项目已经把 `astrbot_plugin_val_shop` 的核心能力移植到 NapCat 机器人里，不需要运行 AstrBot。

## 群里怎么用

- `瓦` 或 `瓦 qq`：绑定你的无畏契约账号，会发 QQ 扫码登录二维码。
- `瓦 清除`：清除你绑定的无畏契约账号。
- `无畏商店`、`瓦店`、`每日商店`：发送你的无畏契约每日商店图片。
- `瓦监控 添加 皮肤名`：把皮肤加入你的监控列表。
- `瓦监控 删除 皮肤名`：从监控列表删除。
- `瓦监控 列表`：查看你的监控列表。
- `瓦监控 查询`：手动检查今天是否命中监控项。

## 部署到服务器

更新代码后，在服务器运行：

```bash
cd ~/fortnite-daily-shop
git pull --rebase --autostash origin main
pkill -f qq_gemini_bot.py 2>/dev/null || true
nohup bash run_qq_gemini_bot.sh > gemini_bot.log 2>&1 &
sleep 3
tail -n 40 gemini_bot.log
```

`run_qq_gemini_bot.sh` 会根据 `requirements.txt` 自动安装 `aiohttp`。

## 数据保存位置

绑定信息保存在：

```text
bot_memory/valorant_users.json
```

它按 QQ 号隔离，不会写进聊天记录。

## 注意

- `商店` 仍然是 Fortnite 每日商店。
- `无畏商店` / `瓦店` / `每日商店` 才是无畏契约每日商店。
- 如果提示登录过期，重新发送 `瓦` 扫码即可。
