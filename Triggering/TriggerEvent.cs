#nullable enable

using System;

namespace TerrariaFriend.Triggering
{
	// 三种触发入口统一交给未来的 Python Decision Node。
	public sealed record TriggerEvent(
		TriggerType TriggerType,
		DateTimeOffset Timestamp,
		TriggerPriority Priority,
		GameEvent? GameEvent = null,
		string? UserQuery = null);
}
