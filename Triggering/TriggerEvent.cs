#nullable enable

using System;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 三种触发都通过同一结构发送给决策服务
	public sealed record TriggerEvent(
		TriggerType TriggerType,
		DateTimeOffset Timestamp,  // 触发时间
		string WorldId,
		string SessionId,
		TriggerPriority Priority,
		VitalsContext Vitals,
		GameEvent? GameEvent = null,
		GameEventContext? EventContext = null,
		string? UserQuery = null,  // 玩家问题
		PeriodicSummary? PeriodicSummary = null,
		GameSnapshot? GameSnapshot = null  // 推理工具读取的游戏状态
		);
}
