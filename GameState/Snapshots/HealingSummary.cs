#nullable enable

namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record HealingSummary(
		int TotalHealingItemCount,
		ItemSummary? BestHealingItem,
		int BestHealingAmount);
}
