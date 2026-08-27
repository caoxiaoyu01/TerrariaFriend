using System;
using System.Collections.Generic;
using Terraria;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class ProgressCollector
	{
		private static readonly (Func<bool> IsDefeated, Func<string> Name)[] Bosses =
		{
			(() => NPC.downedSlimeKing, () => "King Slime"),
			(() => NPC.downedBoss1, () => "Eye of Cthulhu"),
			(() => NPC.downedBoss2, () => WorldGen.crimson ? "Brain of Cthulhu" : "Eater of Worlds"),
			(() => NPC.downedQueenBee, () => "Queen Bee"),
			(() => NPC.downedBoss3, () => "Skeletron"),
			(() => NPC.downedDeerclops, () => "Deerclops"),
			(() => Main.hardMode, () => "Wall of Flesh"),
			(() => NPC.downedQueenSlime, () => "Queen Slime"),
			(() => NPC.downedMechBoss1, () => "The Destroyer"),
			(() => NPC.downedMechBoss2, () => "The Twins"),
			(() => NPC.downedMechBoss3, () => "Skeletron Prime"),
			(() => NPC.downedPlantBoss, () => "Plantera"),
			(() => NPC.downedGolemBoss, () => "Golem"),
			(() => NPC.downedFishron, () => "Duke Fishron"),
			(() => NPC.downedEmpressOfLight, () => "Empress of Light"),
			(() => NPC.downedAncientCultist, () => "Lunatic Cultist"),
			(() => NPC.downedMoonlord, () => "Moon Lord")
		};

		private static readonly (Func<bool> IsReached, string Id, string Name)[] WorldMilestones =
		{
			(() => Main.hardMode, "hardmode_started", "Hardmode Started"),
			(() => NPC.downedMechBoss1 && NPC.downedMechBoss2 && NPC.downedMechBoss3,
				"mechanical_bosses_cleared", "Mechanical Bosses Cleared"),
			(() => NPC.downedPlantBoss, "plantera_defeated", "Plantera Defeated"),
			(() => NPC.downedAncientCultist,
				"lunatic_cultist_defeated", "Lunatic Cultist Defeated")
		};

		// 将 Terraria 原生进度标志和持久化探索记录转换成语义列表
		public static ProgressSnapshot Capture()
		{
			List<string> bosses = new List<string>();
			foreach ((Func<bool> isDefeated, Func<string> name) in Bosses)
			{
				if (isDefeated()) bosses.Add(name());
			}

			List<ProgressMilestoneSnapshot> milestones = new List<ProgressMilestoneSnapshot>();
			foreach ((Func<bool> isReached, string id, string name) in WorldMilestones)
			{
				if (isReached()) milestones.Add(new ProgressMilestoneSnapshot(id, name));
			}

			List<string> visitedRegions = new List<string>(ModContent.GetInstance<CompanionWorldState>().VisitedRegions);
			visitedRegions.Sort();

			return new ProgressSnapshot(
				bosses.ToArray(),
				milestones.ToArray(),
				CaptureCurrentStage(),
				visitedRegions.ToArray());
		}

		private static ProgressStageSnapshot CaptureCurrentStage()
		{
			if (NPC.downedAncientCultist)
				return new ProgressStageSnapshot("post_lunatic_cultist", "Post-Lunatic Cultist");
			if (NPC.downedPlantBoss)
				return new ProgressStageSnapshot("post_plantera", "Post-Plantera");
			if (NPC.downedMechBoss1 && NPC.downedMechBoss2 && NPC.downedMechBoss3)
				return new ProgressStageSnapshot("post_mechanical_bosses", "Post-Mechanical Bosses");
			if (Main.hardMode)
				return new ProgressStageSnapshot("hardmode", "Hardmode");
			return new ProgressStageSnapshot("pre_hardmode", "Pre-Hardmode");
		}
	}
}
