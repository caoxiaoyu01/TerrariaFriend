using System.Collections.Generic;

namespace TerrariaFriend.Triggering
{
	// PERIODIC 判断使用的轻量当前状态
	public sealed record PeriodicSummary(
		IReadOnlyList<string> Biomes,
		string Layer,
		IReadOnlyList<string> ActiveBosses,
		string ProgressionStage,
		string HeldItem);
}
