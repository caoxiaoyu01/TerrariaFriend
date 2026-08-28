using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	public sealed record ProgressMilestoneSnapshot(
		string Id,
		string Name);

	public sealed record ProgressStageSnapshot(
		string Id,
		string Name);

	// 进度与历史探索状态
	public sealed record ProgressSnapshot(
		IReadOnlyList<string> DefeatedBosses,  // 已经击败的首领
		IReadOnlyList<ProgressMilestoneSnapshot> WorldMilestones,  // 使用固定标识的世界进度
		ProgressStageSnapshot CurrentStage,  // 根据游戏进度整理出的当前阶段
		IReadOnlyList<string> VisitedRegions);  // 曾经访问的关键区域
}
