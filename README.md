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
- `Steam状态`：查看配置玩家当前 Steam 在线/游戏状态
- `Steam排行`：发送 Steam 新增游玩时长排行榜
- `吃什么`、`喝什么`：随机推荐一种食物或饮品，并发送真实实物图片；优先用 Wikimedia，失败后会用 Tavily 图片结果
- `@机器人 狼狼`：随机发送一张可爱的真实狼图
- `温德尔 北京天气`、`天气 北京`、`今天武汉洪山区天气怎么样`：查询实时天气和今日/明日预报
- `@机器人 联网查 今天有什么 AI 新闻`：用 Tavily 搜索后再让 DeepSeek 总结；如果搜索结果带图片，会在同一条消息里附带 1-2 张相关图片。普通聊天不会自动联网。

QQ `2353888741` 的私聊是完整测试入口，不需要艾特或添加 `温德尔` 前缀。可以直接测试 `商店`、`游戏优惠`、`Steam状态`、`Steam排行`、`开始视奸`、`停止视奸`、`吃什么`、`喝什么`、错图反馈、`狼狼`、X 搜索/时间线、天气、联网搜索、明日方舟、无畏契约、画像/记忆和普通聊天。图片与文字只会回到该私聊，不会误发到群里；其他 QQ 的私聊仍只保留原有聊天、明日方舟和无畏契约入口。

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

### Steam 状态监控

机器人可以监控配置的 Steam 玩家：有人开始玩游戏或切换游戏时，会在群里发一张状态卡片，包含 Steam 昵称、头像和游戏图片；每天还会按累计游戏时长快照差值生成一次新增游玩时长排行榜。

先到 Steam 开发者页面申请 Web API Key：

```text
https://steamcommunity.com/dev/apikey
```

然后准备要监控玩家的 SteamID64。最稳的方式是在配置里手动列出玩家：

```json
"steam_status_enabled": true,
"steam_api_key": "你的 Steam Web API Key",
"steam_players": [
  {
    "steam_id": "76561198000000000",
    "name": "群友昵称"
  }
],
"steam_status_check_seconds": 120,
"steam_rank_hour": 22,
"steam_rank_minute": 0
```

如果 `steam_group_ids` 留空，会默认发到 `allowed_group_ids`。一键配置脚本会询问是否自动读取好友，直接按回车就会把你填写的 SteamID64 放进 `steam_friend_source_steam_ids`。Steam 的“好友列表”和“游戏详情”必须设为公开，否则 Steam API 只能读到本人，或者看不到好友正在玩的游戏。

服务器上一键配置：

```bash
bash set_steam_monitor.sh
```

群里可用：

```text
Steam状态
Steam排行
```

`Steam状态` 会发送一张正在游戏的好友总览图，只显示 Steam 昵称、头像、游戏名和游戏封面。在线但没有开游戏、离线的好友不会出现在图片里。图片默认展示前 24 人，后台状态监控仍会读取配置范围内的全部好友。

好友刚打开游戏或切换游戏时，机器人会自动发送一条“个人游戏动态”。每条消息只包含这一位好友的文字说明、头像和大幅游戏封面，不会同时发送其他好友。
如果 `steam_group_ids` 是空列表，自动动态会发送到 `allowed_group_ids`。首次启用监控时，已经在游戏中的好友也会发送一次，方便确认自动通知工作正常；之后只在打开或切换游戏时发送。

QQ `2353888741` 可以在群里艾特温德尔，或直接私聊发送 `开始视奸`、`停止视奸`，全局开启或关闭 Steam 好友自动动态。关闭后仍会维护状态基线，重新开启不会补发已经在玩的好友；`Steam状态`、`Steam排行` 和每日排行榜不受影响。其他 QQ 号无权修改这个开关，开关状态会保存在 `bot_memory/steam_activity_settings.json`，重启后继续生效。

第一次启用排行榜时只会建立基准；下一次运行后才会显示新增游玩时长。
排行榜会把每位好友当天游玩时间最长的游戏作为“主游戏名牌”，使用该游戏封面作为个人卡片背景，并单独标出主游戏时长；总时长仍用于决定排名。
Steam 封面会优先从商店接口读取带哈希目录和本地化文件名的真实 `header_image`；如果试玩版没有独立商店数据，会按游戏名查找正式版素材。只有商店接口、搜索结果和旧版 CDN 地址都失败时才使用占位图。

服务器上也可以手动发一次每日一狼：

```bash
bash run_everyday_one_wolf.sh
```

如果想每天北京时间 21:30 自动发一张狼图：

```bash
bash install_everyday_one_wolf_cron.sh
```

### EveryDayOneWendell 每日推文

`EveryDayOneWendell` 默认读取 X 作者 `@wendellindashop` 的最近帖子，每天选一条发送到
`allowed_group_ids` 中配置的全部 QQ 群。作者转发的内容会还原为原作者的原帖；图片会直接发送，
动态 GIF 会把 X 提供的循环 MP4 转回真正的 GIF 后发送，普通视频仍以视频发送。
该账号的数字 User ID `1837315425178136576` 已作为默认配置保存，因此不会依赖容易波动的
“按用户名查询用户”接口。
如果 X 官方用户帖子时间线返回 `503`，程序会自动改读该账号的公开 RSS。RSS 同样包含作者原帖、
转推原帖、图片以及 GIF/视频地址，并且不会消耗 X API Token。当前默认优先使用 RSS，避免每次
等待已经确认不可用的官方用户帖子接口；RSS 暂时失效时才回退到 X OAuth/API。
普通图片会与正文放在同一条 QQ 消息中。由于 QQ/NapCat 会吞掉混合消息里的视频前文字，视频帖
会自动发送为相邻的两条消息：先发帖子正文和原帖链接，再发视频。
GIF 转换默认使用 12 FPS、最大宽度 640 像素和 15MB 上限；过大时会自动降低帧率和尺寸，转换
失败时才回退为 MP4，保证每日任务不会因为单个媒体失败而中断。

程序会缓存作者 ID、最近帖子和各群发送状态。每天只查询上次之后的新帖子；当天没有新帖时，
会从缓存的最近帖子中继续选择。某个群发送失败时，下次只补发失败的群。

手动测试一次（只抓取和下载，不发群）：

```bash
bash run_everyday_one_wendell.sh --dry-run
```

强制立即发送一次：

```bash
bash run_everyday_one_wendell.sh --force
```

只私发一条最新推文用于预览，不改变每日群发送记录：

```bash
bash run_everyday_one_wendell.sh --private-user-id 2353888741
```

只私发作者最近转发的一条原帖：

```bash
bash run_everyday_one_wendell.sh --private-user-id 2353888741 --retweet-only
```

安装北京时间每天 14:00 的自动任务：

```bash
bash install_everyday_one_wendell_cron.sh
```

如果 `everyday_one_wendell_group_ids` 留空，会自动使用 `allowed_group_ids`。旧版
`everyone_wendell_*` 配置字段仍然兼容。默认视频共享目录与当前
NapCat Docker 挂载一致：宿主机 `/opt/napcat/data/wendell_media` 对应容器内
`/app/.config/QQ/wendell_media`。

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

把 `provider` 设为 `openrouter`，填写 `openrouter_api_key`，并把 `model` 设为 `thedrummer/cydonia-24b-v4.1`。如果要继续使用 DeepSeek，也可以把 `provider` 改回 `deepseek` 并填写 `deepseek_api_key`。如果要让机器人联网搜索，再填写 `tavily_api_key`。API Key 不要提交到 GitHub。

OpenRouter 默认开启 `openrouter_plain_chat`，普通聊天会按 OpenRouter 原生 messages 形式发送：人设卡作为 system prompt，个人记忆作为单独背景消息，短期上下文作为历史 user/assistant 消息，最后是当前用户消息。不额外注入时间或短回复规则，尽量不改变人设卡里的说话方式。
OpenRouter 请求遇到临时限流、上游不可用、连接超时或正文内的 provider error 时会自动重试；返回空文字时会保留人设和当前问题、去掉旧上下文再请求一次。可用 `openrouter_request_timeout_seconds` 和 `openrouter_retry_count` 调整超时与重试次数。
当前温德尔人设卡保存在 `wendell_persona.txt`。配置里使用 `system_prompt_file: "wendell_persona.txt"` 时，机器人会把这个文件内容作为 OpenRouter 的 system prompt。

为避免聊久后旧上下文过长导致模型请求失败，机器人会在发送给模型前自动压缩历史消息：`model_history_message_char_limit` 控制单条历史字数，`model_history_total_char_limit` 控制历史总字数。若 OpenRouter/DeepSeek 因上下文失败，`model_history_fallback_enabled` 会让机器人保留人设和当前问题、丢掉旧历史自动重试一次，不需要手动清空上下文。

联网搜索默认使用 Tavily `basic` 搜索，每次大约消耗 1 个 credit。开启 `semi_agent_enabled` 后，机器人可以自行判断问题是否需要联网；你明确说 `联网查` 时会强制联网。
联网搜索默认会请求 Tavily 图片结果，最多在同一条消息里附带 2 张相关图片。可以在 `gemini_bot_config.json` 里用 `web_search_include_images` 和 `web_search_image_limit` 调整。

如果不想手动编辑配置，可以在服务器上运行：

```bash
bash set_openrouter_key.sh
```

粘贴 OpenRouter API Key 后，脚本会自动切到 `thedrummer/cydonia-24b-v4.1` 并重启机器人。

如果已经配置过 OpenRouter Key，只想切回最普通的 OpenRouter 聊天模式，可以运行：

```bash
bash set_openrouter_plain_chat.sh
```

如果要启用当前温德尔人设卡，可以运行：

```bash
bash set_wendell_persona.sh
```

如果只是配置 Tavily 联网搜索，可以运行：

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
- `steam_status.py`：读取 Steam 玩家状态、头像、游戏图片和累计游戏时长，生成状态卡片与每日时长排行榜
- `set_steam_monitor.sh`：Linux/VPS 一键写入 Steam Web API Key、SteamID64 并重启机器人
- `random_food.py`：随机推荐食物/饮品并发送真实实物图片，供 QQ 群触发 `吃什么`、`喝什么`
- `test_random_food.sh`：Linux/VPS 单独测试 `吃什么`、`喝什么` 的真实图片抓取
- `random_wolf.py`：随机抓取真实狼图
- `send_wolf.py`：通过 OneBot HTTP 发送每日一狼
- `run_everyday_one_wolf.sh`：Linux/VPS 手动发送每日一狼
- `install_everyday_one_wolf_cron.sh`：Linux/VPS 安装每日一狼定时任务
- `install_everyday_one_wendell_cron.sh`：Linux/VPS 安装每天 14:00 的 EveryDayOneWendell 推文任务
- `run_everyday_one_wendell.sh`：抓取并发送一条 `@wendellindashop` 的最近推文
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
