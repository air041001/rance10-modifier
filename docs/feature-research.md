# 培养与餐券功能的适配边界

以下依据是当前已验证指纹的本机 AIN/EX；不表示其他版本具有相同结构。

| 数据 | 游戏实现依据 | 编辑方式 |
| --- | --- | --- |
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
本地1.4.0测试功能临时替换Find的未完成故事筛选及已完成故事填充筛选，
保留GetAvailableCharacterIds里的持有卡、不可用卡及IsAvailable检查。
引用来自当前VM对象表，字符串通过每块4个指针的表解析；不会用存档引用写入运行中的游戏。
让游戏原流程建立控件并播放故事。取消后恢复原代码；磁盘AIN/EXE和故事存档标记不写入。
2026-10-03再次核对：SceneFoodTicket@Run首次生成名单；OnFinishShowApplyEffect在仍有餐券时再次调用PickCards，重新生成名单和控件。
因此播放后换指定人物，再配合手动补券继续观看，符合游戏原有的刷新流程；修改器没有重置故事阶段。
同日用户反馈：测试档中指定后仅出现该人物，刷完后改指定另一人物可继续。首次指定没有出现，经再次指定生效；
首次操作相对读档及名单生成的时机未记录，不能据此断定原因。精确扣券、阶段数值及保存重读仍待确认。

游戏原有的已观看故事回放和通关后的餐券功能属于另外的流程，不能当作普通进度的强制候选。
未来可继续核对HP恢复、AP恢复、勋章换点数等功能；尚未实现，不属于本次发布内容。
