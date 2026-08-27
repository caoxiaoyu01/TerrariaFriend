#nullable enable

namespace TerrariaFriend.Triggering
{
	// 事件主体用于携带首领 区域 世界事件或非玩家角色的轻量标识
	public sealed record GameEvent(
		GameEventType EventType,
		string? SubjectId = null,
		string? SubjectName = null,
		int? CellX = null,
		int? CellY = null);
}
