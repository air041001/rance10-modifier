# 培养与餐券功能的适配边界

以下依据是当前已验证指纹的本机 AIN/EX；不表示其他版本具有相同结构。

| 数据 | 游戏实现依据 | 编辑方式 |
| --- | --- | --- |
| 人物培养★ | `Character@ForceSetStar`、`Character::CalcNextExp`、`PlayerCard@GetStar` | 写人物★，清本级经验，重设门槛；共享人物ID的卡都受影响 |
| 重复强化 | `PlayerCard@Count::set`、`PlayerCard::GetMaxCount` | 写单张卡的重复数量，EX强化上限+1为总份数 |
| 卡牌属性缓存 | `PlayerCard@ForceRecalcStatus`、`OrganizationCardCollection@ForceRecalcStatus` | 清对应卡的`m_lastStar`并标记所属集合已变化 |
| 餐券故事进度 | `FoodTicketEvent@Stage::get`、`MaxStage::get`、`GetEventFlagName` | 只读已看阶段，结合EX中的A/B/C条件展示 |
| 普通餐券候选 | `FoodTicketTargetFinder::Find`、`SceneFoodTicket@PickCards` | 随机至多6位，未完成故事的合格人物优先 |

`Find` 返回字符串数组；`SceneFoodTicket` 保存这份数组，而
`FoodTicketTargetGroup` 还建立卡牌、人物及点击目标的独立引用。
确认点击后，`SceneFoodTicket@OnClickCard` 通过名单获取人物，扣餐券、推进阶段，
再由 `RunCharacterEvent` 播放故事。仅替换某个名字无法证明显示与剧情目标一致。

现有内存组件只执行已经验证的独立整数写入，未支持字符串生命周期、候选控件重建、
游戏事件调用。因此本版不提供强制候选按钮；需要在实际餐券界面核对这些引用，
再验证正常扣券、触发目标故事、经验、保存和重读。

游戏原有的已观看故事回放和通关后的餐券功能属于另外的流程，不能当作普通进度的强制候选。
未来可继续核对HP恢复、AP恢复、勋章换点数等功能；尚未实现，不属于本次发布内容。
