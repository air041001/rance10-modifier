# 培养与餐券功能的适配边界

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
