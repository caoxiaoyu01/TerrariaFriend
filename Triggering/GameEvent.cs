#nullable enable

namespace TerrariaFriend.Triggering
{
	// Subject 用于携带 Boss、区域、世界事件或 NPC 的轻量标识。
	public sealed record GameEvent(
		GameEventType EventType,
		string? SubjectId = null,
		string? SubjectName = null);
}
