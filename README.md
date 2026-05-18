# Fortnite Daily Shop

这是一个 Fortnite 每日商城项目。它会每天请求 Fortnite API，生成 `shop.json`，再把商城内容渲染成一张适合手机查看和转发的 `shop.png`。

网页地址：

```text
https://wolping13-png.github.io/fortnite-daily-shop/
```

图片地址：

```text
https://wolping13-png.github.io/fortnite-daily-shop/shop.png
```

## 一键发布

Windows 上双击：

```text
one-click-publish.bat
```

它会创建或更新 GitHub 仓库，开启 GitHub Pages，并触发一次 GitHub Actions 更新。

如果只是把后续修改上传到 GitHub，双击：

```text
push-updates.bat
```

## 本地生成图片

```bash
pip install -r requirements.txt
python update_shop.py
python generate_shop_image.py
python generate_shop_sections.py
```

生成结果是：

```text
shop.png
shop_qq.jpg
```

## QQ 机器人发图

本项目支持 NapCatQQ + OneBot HTTP。

第一次测试：

```text
send-qq-shop.bat
```

如果想先更新商城再发送：

```text
send-qq-update-and-send.bat
```

第一次运行会让你填写：

- NapCat OneBot HTTP 地址，例如 `http://127.0.0.1:3000`
- QQ 群号
- Access token，如果 NapCat 没设置就直接回车
- 图片上方文字

配置会保存到本地 `qq_bot_config.json`。这个文件已经加入 `.gitignore`，不会上传到 GitHub。

## 每天自动发到 QQ 群

先确保 `send-qq-shop.bat` 能成功发图，再双击：

```text
install-qq-daily-task.bat
```

它会创建 Windows 计划任务：每天 08:15 运行一次，先更新商城图片，再通过 NapCatQQ 发到群里。

注意：到点时电脑需要开机，NapCatQQ 也需要正在运行并登录机器人 QQ。

## 云服务器自动发图

如果你不想每天开着自己的电脑，可以把项目放到 Ubuntu VPS 上跑。

看这份说明：

```text
cloud_setup.md
```

核心命令是：

```bash
bash run_daily_qq.sh
bash install_cloud_cron.sh
```

服务器版默认每天 UTC 00:15 运行，也就是北京时间 08:15。前提是服务器上的 NapCatQQ 一直在线。

## AI 群聊机器人

支持把 NapCatQQ 的群消息接入 DeepSeek 或 Gemini API。默认推荐 DeepSeek，对香港服务器更友好。

默认指令：

- `温德尔 你的问题`：调用 AI 回复
- `商店`：发送一张按官方商店分区排列的每日商店总图
- `商店全部`：发送按分区拆开的分页图，适合总图发送失败时备用
- `温德尔 北京天气`、`天气 北京`、`今天武汉洪山区天气怎么样`：查询实时天气和今日/明日预报
- `宠物热点`、`猫猫热点`、`狗狗热点`、`狼狼`：抓取 Reddit 宠物热门图文并发送到群里

服务器上也可以手动发送一次 Reddit 宠物热点：

```bash
bash run_reddit_pets.sh
```

如果想每天北京时间 20:30 自动发一次：

```bash
bash install_reddit_pet_cron.sh
```

服务器上配置：

```bash
cp gemini_bot_config.example.json gemini_bot_config.json
nano gemini_bot_config.json
```

把 `provider` 设为 `deepseek`，并填写 `deepseek_api_key` 和 `allowed_group_ids`。API Key 不要提交到 GitHub。

在 NapCatQQ 的 HTTP Server 配置里，把上报地址设置成：

```text
http://127.0.0.1:8080/onebot
```

测试运行：

```bash
bash run_qq_gemini_bot.sh
```

后台常驻：

```bash
bash install_gemini_bot_service.sh
```

## GitHub Actions 自动更新

`.github/workflows/update-shop.yml` 已经配置：

- 每天北京时间 08:05 自动更新
- 支持在 GitHub Actions 页面手动点击 `Run workflow`

## 文件说明

- `update_shop.py`：请求 Fortnite API，生成 `shop.json`
- `generate_shop_image.py`：读取 `shop.json`，生成按官方分区排列的 `shop.png` 和 QQ 用 `shop_qq.jpg`
- `generate_shop_sections.py`：生成分区分页图，作为 QQ 备用发送方案
- `send_qq_shop.py`：通过 OneBot HTTP 发送 QQ 群图片
- `reddit_pets.py`：抓取 Reddit 宠物热门帖并生成图文图片
- `send_reddit_pets.py`：通过 OneBot HTTP 发送 Reddit 宠物热点
- `run_reddit_pets.sh`：Linux/VPS 手动发送 Reddit 宠物热点
- `install_reddit_pet_cron.sh`：Linux/VPS 安装 Reddit 宠物热点定时任务
- `send-qq-shop.bat`：测试发送当前 `shop.png`
- `send-qq-update-and-send.bat`：更新后发送
- `install-qq-daily-task.bat`：安装每天自动发图任务
- `run_daily_qq.sh`：Linux/VPS 每日更新并发图脚本
- `install_cloud_cron.sh`：Linux/VPS 安装 cron 定时任务
- `index.html`：网页入口，展示 `shop.png`
