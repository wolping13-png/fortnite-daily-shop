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

服务器版默认每天北京时间 08:15 运行。前提是服务器上的 NapCatQQ 一直在线。
如果服务器时区不是北京时间，先运行：

```bash
timedatectl set-timezone Asia/Shanghai
bash install_cloud_cron.sh
```

## AI 群聊机器人

支持把 NapCatQQ 的群消息接入 DeepSeek 或 Gemini API。默认推荐 DeepSeek，对香港服务器更友好。
默认人设是游戏专家，尤其熟悉 Fortnite / 堡垒之夜，但也可以聊其他游戏、攻略、更新、电竞、硬件配置、主机、PC 和手游。

默认指令：

- `温德尔 你的问题`：调用 AI 回复
- `@机器人 你的问题`：调用 AI 回复，推荐用这个方式
- `@机器人 指令`、`@机器人 帮助`、`@机器人 菜单`：查看完整指令表
- `商店`：发送一张按官方商店分区排列的每日商店总图
- `游戏优惠`、`Steam折扣榜`、`Epic喜加一`：发送 Steam 高销量折扣榜和 Epic 免费游戏日报
- `吃什么`、`喝什么`：随机推荐一种食物或饮品，并发送真实实物图片；优先用 Wikimedia，失败后会用 Tavily 图片结果
- `@机器人 狼狼`：随机发送一张可爱的真实狼图
- `温德尔 北京天气`、`天气 北京`、`今天武汉洪山区天气怎么样`：查询实时天气和今日/明日预报
- `@机器人 联网查 今天有什么 AI 新闻`：用 Tavily 搜索后再让 DeepSeek 总结；如果搜索结果带图片，会在同一条消息里附带 1-2 张相关图片。普通聊天不会自动联网。

### 主动发起话题

机器人可以根据北京时间、当前天气、日期、节日和最近聊天内容，偶尔在群里主动抛一个轻松话题。如果连续没人回复，它会自动降低主动说话频率。

默认关闭。要开启，在服务器的 `gemini_bot_config.json` 里加入或修改：

```json
"proactive_topic_enabled": true,
"proactive_topic_min_interval_minutes": 120,
"proactive_topic_max_interval_minutes": 480,
"proactive_topic_idle_minutes": 45,
"proactive_topic_daily_limit": 4,
"proactive_topic_recent_limit": 10,
"proactive_topic_active_start_hour": 9,
"proactive_topic_active_end_hour": 23
```

含义：群里安静 45 分钟后才可能开口；基础间隔 120 分钟；如果没人理，会逐步降到最多 480 分钟一次；每天最多主动说 4 次；只在 9:00-23:00 之间主动说话。机器人会记住最近 10 条主动话题，尽量避开重复主题和重复问法。

也可以直接在服务器运行：

```bash
bash enable_proactive_topics.sh
```

### 语境表情包

机器人支持在普通聊天和主动话题里，根据语境附带一张表情包。比如开心、疑惑、思考、安慰、睡觉、吃喝、游戏、狼狼相关语境会优先从对应文件夹里挑图。

表情包放在：

```text
memes/
```

分类目录：

```text
memes/default
memes/happy
memes/confused
memes/thinking
memes/comfort
memes/sleep
memes/food
memes/game
memes/wolf
```

支持 `.jpg`、`.jpeg`、`.png`、`.webp`。把图片放进去后，推送到服务器并重启机器人即可。默认有冷却和每小时上限，不会每句话都发表情包。

服务器上一键开启：

```bash
bash enable_memes.sh
```

可调配置在 `gemini_bot_config.json`：

```json
"meme_enabled": true,
"meme_chance": 0.28,
"meme_cooldown_seconds": 240,
"meme_max_per_hour": 8,
"meme_max_text_length": 180
```

### 用户级称呼和关系记忆

机器人会把个人称呼和关系设定按“群号 + 用户 QQ 号”隔离保存，避免一个人的设定污染其他人。群聊普通历史仍然共享，但“以后叫我老婆”“我是你的主人”这类个人设定不会长期进入普通 DeepSeek 上下文。

记忆文件在服务器：

```text
bot_memory/user_memory.json
```

支持示例：

```text
以后叫我小沃
以后叫我老婆
我是你的主人
把我当成你的搭档
不要叫我老婆了
忘掉我的称呼
清除我的关系设定
```

关系词，比如“老婆、主人、宝宝、对象、搭档”等，会同时作为称呼和关系设定保存。普通昵称，比如“小沃、Lee”，只作为称呼保存。

测试方式：

```text
用户 A：以后叫我老婆
用户 B：你叫我什么
```

机器人不应该把用户 B 叫成“老婆”。

```text
用户 A：你老婆是谁
```

如果用户 A 自己设置过“老婆”，机器人可以回答“是你呀，老婆”。其他用户问同样问题时，机器人不能透露用户 A 的私有设定。

服务器上也可以手动发一次 Steam / Epic 游戏优惠日报：

```bash
bash run_game_deals_qq.sh
```

如果想每天北京时间 10:05 自动发一次：

```bash
bash install_game_deals_cron.sh
```

服务器上也可以手动发一次每日一狼：

```bash
bash run_everyday_one_wolf.sh
```

如果想每天北京时间 21:30 自动发一张狼图：

```bash
bash install_everyday_one_wolf_cron.sh
```

服务器上也可以手动发一次睡觉提醒：

```bash
bash run_bedtime_reminder.sh
```

如果想每天北京时间 23:30 自动提醒群友睡觉：

```bash
bash install_bedtime_reminder_cron.sh
```

睡觉提醒会附带第二天日期、星期、农历/节日信息、默认城市天气；如果明天是节日，会让 AI 按温德尔的人设发挥几句。它也会检查 Epic 免费游戏是否快结束，并附带 Steam 热销折扣榜摘要。

如果之前安装过 Reddit 宠物热点定时任务，但现在不想再发，可以在服务器上运行：

```bash
bash disable_reddit_pets.sh
```

如果 `吃什么`、`喝什么` 没有发出图片，可以在服务器上单独测试图片抓取：

```bash
bash test_random_food.sh
```

服务器上配置：

```bash
cp gemini_bot_config.example.json gemini_bot_config.json
nano gemini_bot_config.json
```

把 `provider` 设为 `deepseek`，并填写 `deepseek_api_key` 和 `allowed_group_ids`。如果要让机器人联网搜索，再填写 `tavily_api_key`。API Key 不要提交到 GitHub。

联网搜索默认使用 Tavily `basic` 搜索，每次大约消耗 1 个 credit。机器人只有在你明确说 `联网查`、`搜索`、`搜一下`，或者问题里有 `最新`、`热点`、`新闻`、`实时` 这类词时才会联网。
联网搜索默认会请求 Tavily 图片结果，最多在同一条消息里附带 2 张相关图片。可以在 `gemini_bot_config.json` 里用 `web_search_include_images` 和 `web_search_image_limit` 调整。
机器人每次回答都会注入当前中国内地北京时间，以及今天/昨天/明天的具体日期，减少日期和“最新/最近”判断错误。

如果不想手动编辑配置，可以在服务器上运行：

```bash
bash set_tavily_key.sh
```

粘贴 Tavily API Key 后，脚本会自动写入配置并重启机器人。

如果想把旧配置里比较死板的堡垒之夜专属人设更新成“游戏专家，主修堡垒之夜”，可以在服务器上运行：

```bash
bash set_bot_persona.sh
```

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
- `send_qq_shop.py`：通过 OneBot HTTP 发送 QQ 群图片
- `game_deals.py`：抓取 Steam 高销量折扣榜和 Epic 喜加一，并生成 `game_deals.jpg`
- `send_game_deals.py`：通过 OneBot HTTP 发送游戏优惠日报
- `run_game_deals_qq.sh`：Linux/VPS 手动发送游戏优惠日报
- `install_game_deals_cron.sh`：Linux/VPS 安装游戏优惠日报定时任务
- `random_food.py`：随机推荐食物/饮品并发送真实实物图片，供 QQ 群触发 `吃什么`、`喝什么`
- `test_random_food.sh`：Linux/VPS 单独测试 `吃什么`、`喝什么` 的真实图片抓取
- `random_wolf.py`：随机抓取真实狼图
- `send_wolf.py`：通过 OneBot HTTP 发送每日一狼
- `run_everyday_one_wolf.sh`：Linux/VPS 手动发送每日一狼
- `install_everyday_one_wolf_cron.sh`：Linux/VPS 安装每日一狼定时任务
- `bedtime_reminder.py`：生成睡觉提醒、第二天信息、节日文案和游戏优惠临期提醒
- `run_bedtime_reminder.sh`：Linux/VPS 手动发送睡觉提醒
- `install_bedtime_reminder_cron.sh`：Linux/VPS 安装每天 23:30 的睡觉提醒定时任务
- `disable_reddit_pets.sh`：Linux/VPS 关闭旧的 Reddit 宠物触发、移除定时任务并重启机器人
- `uninstall_reddit_pet_cron.sh`：Linux/VPS 移除旧的 Reddit 宠物热点定时任务
- `set_tavily_key.sh`：Linux/VPS 一键写入 Tavily API Key 并重启 AI 群聊机器人
- `set_bot_persona.sh`：Linux/VPS 一键更新 AI 群聊机器人的游戏专家人设并重启
- `send-qq-shop.bat`：测试发送当前 `shop.png`
- `send-qq-update-and-send.bat`：更新后发送
- `install-qq-daily-task.bat`：安装每天自动发图任务
- `run_daily_qq.sh`：Linux/VPS 每日更新并发图脚本
- `install_cloud_cron.sh`：Linux/VPS 安装 cron 定时任务
- `index.html`：网页入口，展示 `shop.png`
