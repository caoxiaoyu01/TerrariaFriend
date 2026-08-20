#nullable enable

namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record ArmorSnapshot(
		ItemSummary? Head,
		ItemSummary? Body,
		ItemSummary? Legs);
}
