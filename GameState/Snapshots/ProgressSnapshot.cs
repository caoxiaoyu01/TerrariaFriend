using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 进度与历史探索状态
	public sealed record ProgressSnapshot(
		IReadOnlyList<string> DefeatedBosses,  // 已经击败boss
		IReadOnlyList<string> WorldMilestones,  // 世界进度
		IReadOnlyList<string> VisitedRegions);	// 曾经访问的关键区域
}
