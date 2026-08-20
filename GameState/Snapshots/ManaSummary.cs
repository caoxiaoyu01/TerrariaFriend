#nullable enable

namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record ManaSummary(
		int TotalManaItemCount,
		ItemSummary? BestManaItem,
		int BestManaAmount);
}
