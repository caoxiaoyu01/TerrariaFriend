#nullable enable

namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record RecentDamageSnapshot(
		int DamageTakenLast5s,
		int LastDamageAmount,
		string? LastDamageSource,
		float TimeSinceLastDamageSeconds);
}
