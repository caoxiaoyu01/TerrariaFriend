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
		IReadOnlyList<string> DefeatedBosses,  // 已经击败 Boss
		IReadOnlyList<ProgressMilestoneSnapshot> WorldMilestones,  // 稳定 ID 的世界进度事实
		ProgressStageSnapshot CurrentStage,  // Collector 根据原生 flag 归一化的当前阶段
		IReadOnlyList<string> VisitedRegions);  // 曾经访问的关键区域
}
