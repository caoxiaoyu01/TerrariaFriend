#nullable enable

using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class NpcCollector
	{
		private const float PixelsPerTile = 16f;

		// 单次扫描生成常驻、附近常驻、特殊 NPC 与活动 Boss 快照。
		public static NpcSnapshot Capture(Player player, float radiusTiles)
		{
			Dictionary<int, TownNpcSummary> townNpcs = new Dictionary<int, TownNpcSummary>();
			Dictionary<int, SpecialNpcSummary> specialNpcs = new Dictionary<int, SpecialNpcSummary>();
			Dictionary<int, BossSummary> activeBosses = new Dictionary<int, BossSummary>();
			List<NearbyTownNpcSummary> nearbyTownNpcs = new List<NearbyTownNpcSummary>();

			for (int i = 0; i < Main.maxNPCs; i++)
			{
				NPC npc = Main.npc[i];
				if (!npc.active) continue;

				float distance = Vector2.Distance(player.Center, npc.Center) / PixelsPerTile;
				bool isNearby = distance <= radiusTiles;
				bool isSpecial = IsSpecialNpc(npc.type);
				if (isSpecial)
				{
					specialNpcs[npc.type] = new SpecialNpcSummary(
						npc.type,
						npc.FullName,
						isNearby,
						isNearby ? distance : null,
						npc.life,
						npc.lifeMax);
				}
				else if (npc.townNPC && !NPCID.Sets.IsTownPet[npc.type])
				{
					townNpcs[npc.type] = new TownNpcSummary(
						npc.type,
						npc.FullName,
						npc.homeless,
						npc.life,
						npc.lifeMax);

					if (isNearby)
					{
						nearbyTownNpcs.Add(new NearbyTownNpcSummary(
							npc.type,
							npc.FullName,
							distance,
							npc.life,
							npc.lifeMax,
							npc.homeless));
					}
				}

				if (npc.boss)
				{
					activeBosses[npc.type] = new BossSummary(
						npc.type,
						npc.FullName,
						npc.life,
						npc.lifeMax,
						(float)npc.life / npc.lifeMax,
						distance,
						isNearby);
				}

			}

			List<TownNpcSummary> townNpcList = new List<TownNpcSummary>(townNpcs.Values);
			List<SpecialNpcSummary> specialNpcList = new List<SpecialNpcSummary>(specialNpcs.Values);
			List<BossSummary> activeBossList = new List<BossSummary>(activeBosses.Values);

			townNpcList.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
			specialNpcList.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
			activeBossList.Sort((a, b) => a.Distance.CompareTo(b.Distance));
			nearbyTownNpcs.Sort((a, b) => a.Distance.CompareTo(b.Distance));

			return new NpcSnapshot(
				townNpcList.Count,
				townNpcList,
				nearbyTownNpcs.Count,
				nearbyTownNpcs,
				specialNpcList.Count,
				specialNpcList,
				activeBossList.Count > 0,
				activeBossList.Count,
				activeBossList);
		}

		// 特殊npc
		private static bool IsSpecialNpc(int type)
		{
			return type == NPCID.TravellingMerchant
				|| type == NPCID.SkeletonMerchant
				|| type == NPCID.OldMan
				|| type == NPCID.BoundGoblin
				|| type == NPCID.BoundWizard
				|| type == NPCID.BoundMechanic
				|| type == NPCID.WebbedStylist
				|| type == NPCID.SleepingAngler
				|| type == NPCID.BartenderUnconscious
				|| type == NPCID.GolferRescue;
		}
	}
}
