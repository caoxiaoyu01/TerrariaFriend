namespace TerrariaFriend.GameState.Tracking
{
	// 仅用于最近五秒滑动窗口，不进入 Snapshot。
	internal sealed record DamageEvent(
		uint Tick,
		int Damage,
		string Source,
		bool IsHostile);
}
