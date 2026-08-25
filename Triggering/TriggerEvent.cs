#nullable enable

using System;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 三种触发入口统一交给未来的 Python Decision Node
	public sealed record TriggerEvent(
		TriggerType TriggerType,
		DateTimeOffset Timestamp,  // 触发时间
		TriggerPriority Priority,
		VitalsContext Vitals,
		GameEvent? GameEvent = null,
		GameEventContext? EventContext = null,
		string? UserQuery = null,  // 玩家问题
		PeriodicSummary? PeriodicSummary = null,
		GameSnapshot? GameSnapshot = null  // REASON Tool 的只读数据源
		);
}
