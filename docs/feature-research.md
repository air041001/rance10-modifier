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
目前只读运行数据和模拟写入恢复通过；实际卡面、点击、扣券、故事推进、保存重读仍待测试。

游戏原有的已观看故事回放和通关后的餐券功能属于另外的流程，不能当作普通进度的强制候选。
未来可继续核对HP恢复、AP恢复、勋章换点数等功能；尚未实现，不属于本次发布内容。
