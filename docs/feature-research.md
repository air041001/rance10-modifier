# 培养与餐券功能的适配边界

## 持有卡牌删除与据点菜单（2026-10-14）

- `Ｔ据点环节Ａ` 中“抱亚基蕾塔”检查任务未完成、人物持有非零、餐券事件阶段至少1。
- 同函数中“哈尼军团参战”（显示名“增加的哈尼”）检查任务未完成、持有红哈尼、`tt[41] == 0`，没有排除亚基蕾塔的条件。
- `＞据点环节登录` 按生成顺序计数，只登录前9个任务；亚基蕾塔任务在哈尼任务前面。这是菜单名额挤占，并非两项任务直接互斥；删一项也不保证其他条件已满足或一定进入前9项。
- `Ｐ友方卡牌識別名有无` 经 `Ｐ友方卡牌卡组状态取得`，先检查出战人物，再检查十阵营的 `IsExistCharacter`。人物任意版本仍持有时，单删一个版本不够。
- `OrganizationCardCollection@Erase` 只减少一份 `m_count`，归零才移除实例。工具的“删除”采用整版本移除语义，重建 `m_characterId`，按旧 `Index` 次序重新编号，并标记阵营已变化。
- 删除的出战版本按 `LeaderCard@Reset` 的空卡、状态和技能计数语义清理；编队历史数组保留格子位置。阵营总属性和部队总属性在读档后进入编队时由游戏重新计算。
- 删除人物最后一个版本时，从 `g_character.m_character` 移除对象，并清零该对象培养、经验、餐券阶段及行动状态。保留其他版本仍在使用的人物数据。
- 清除 `g_eventInfo.m_eventName` 中以该人物名加全角/半角斜杠为前缀的个人事件，清除该人物的 `m_bestFriendId` 引用，删除选中版本的 `m_shownCardIds` 本地显示记录。
- 存档记录编号保持稳定；人物读取改为遍历原生持有集合，不把未引用的旧记录当作当前人物，重新加卡不会复用旧培养和餐券阶段。
- 跨存档共享图鉴、共享已读记录、已完成任务和战况不修改。个人事件可能已经造成世界状态变化，清掉个人记录不等于回滚这些结果。
- 修改仅针对选中的手动存档，仍使用修改前SHA校验、自动备份和回读校验。38号位不用于写入测试。

以下记录游戏方法和编辑字段。现行程序读取使用者本机AIN/EX并按功能核对结构与规则，
安装环境适配说明见[COMPATIBILITY.md](COMPATIBILITY.md)。

| 数据 | 游戏实现依据 | 编辑方式 |
| --- | --- | --- |
| 第二部友情 | `PlayerCommonParam@FriendPoint::set`、`FriendCountView@Update`、`SceneFriend@OnClick` | 实时补满独立的`m_friendPoint`，人物与故事由游戏友情画面处理 |
| 人物培养★ | `Character@ForceSetStar`、`Character::CalcNextExp`、`PlayerCard@GetStar` | 写人物★，清本级经验，重设门槛；共享人物ID的卡都受影响 |
| 重复强化 | `PlayerCard@Count::set`、`PlayerCard::GetMaxCount` | 写单张卡的重复数量，EX强化上限+1为总份数 |
| 卡牌属性缓存 | `PlayerCard@ForceRecalcStatus`、`OrganizationCardCollection@ForceRecalcStatus` | 清对应卡的`m_lastStar`并标记所属集合已变化 |
| 餐券故事进度 | `FoodTicketEvent@Stage::get`、`MaxStage::get`、`GetEventFlagName` | 只读已看阶段，结合EX中的A/B/C条件展示 |
| 战后餐券候选 | `FoodTicketTargetFinder::Find`、`SceneFoodTicket@PickCards` | 随机至多6位，未完成故事的合格人物优先 |
| 地图餐券候选 | `FoodTicketTargetFinder::FindAfter`、`SceneFoodTicketInMap@PickCards` | 持有且有资料的卡、人物50★、故事未完成、剧情条件满足 |

`Find` 返回字符串数组；`SceneFoodTicket` 保存这份数组，而
`FoodTicketTargetGroup` 还建立卡牌、人物及点击目标的独立引用。
确认点击后，`SceneFoodTicket@OnClickCard` 通过名单获取人物，扣餐券、推进阶段，
再由 `RunCharacterEvent` 播放故事。仅替换某个名字无法证明显示与剧情目标一致。

2026-10-03核对调用者后，修正了此前把FindAfter当作战后入口的判断。
它由SceneFoodTicketInMap调用；普通战后画面调用Find，不能只根据函数名字判断。
1.4.0功能临时替换Find的未完成故事筛选及已完成故事填充筛选，
保留GetAvailableCharacterIds里的持有卡、不可用卡及IsAvailable检查。
引用来自当前VM对象表，字符串通过每块4个指针的表解析；不会用存档引用写入运行中的游戏。
让游戏原流程建立控件并播放故事。取消后恢复原代码；磁盘AIN/EXE和故事存档标记不写入。
2026-10-03再次核对：SceneFoodTicket@Run首次生成名单；OnFinishShowApplyEffect在仍有餐券时再次调用PickCards，重新生成名单和控件。
因此播放后换指定人物，再配合手动补券继续观看，符合游戏原有的刷新流程；修改器没有重置故事阶段。
同日用户反馈：测试档中指定后仅出现该人物，刷完后改指定另一人物可继续。首次指定没有出现，经再次指定生效；
首次操作相对读档及名单生成的时机未记录，不能据此断定原因。
后续用户验收确认：读旧档后指定，战后直接只出现该人物；刷满后另存，再由修改器读取新档，进度1/3→3/3。
这证明该样本的故事推进和保存数据有效。没有逐一统计餐券扣减数值，也未覆盖所有人物与路线。

游戏原有的已观看故事回放和通关后的餐券功能属于另外的流程，不能当作普通进度的强制候选。

## 第二部友情（2026-10-04）

本机脚本的FriendPoint setter将数值限制在0到3；FriendCountView从该字段更新三个图标。
`m_friendPoint`与餐券／金块字段`m_foodTicket`独立。新按钮只写友情字段，保留其他资源与部队点数。
字段位置继续由使用者本机AIN结构取得，不另建中文／日文固定地址。

第二部使用SceneFriend与FriendPhaseList。名单来自游戏的友情环节，点击已选人物由原生流程处理；
它不调用第一部的FoodTicketTargetFinder，因此没有复用餐券候选筛选钩子。
只补消耗资源，不直接修改故事阶段、人物培养或剧情标记。
