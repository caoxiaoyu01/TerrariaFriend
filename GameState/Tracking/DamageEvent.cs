namespace TerrariaFriend.GameState.Tracking
{
	// 仅用于最近五秒滑动窗口且不进入快照
	internal sealed record DamageEvent(
		uint Tick,
		int Damage,
		string Source,
		bool IsHostile);
}
