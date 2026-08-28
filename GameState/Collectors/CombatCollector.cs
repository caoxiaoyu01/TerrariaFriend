using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using TerrariaFriend.GameState.Snapshots;
using TerrariaFriend.GameState.Tracking;

namespace TerrariaFriend.GameState.Collectors
{
	public static class CombatCollector
	{
		private const float PixelsPerTile = 16f;
		public const float NearbyEnemyRadius = GameStateCollector.DefaultSceneRadiusTiles;

		// 汇总当前首领 附近敌人数和最近五秒的受伤记录
		public static CombatSnapshot Capture(Player player)
		{
			List<BossCombatSummary> bosses = new List<BossCombatSummary>();
			int nearbyEnemyCount = CaptureNpcContext(player, bosses);
			bosses.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
			BossCombatSummary[] activeBosses = bosses.ToArray();

			uint currentTick = Main.GameUpdateCount;
			CombatTracker tracker = player.GetModPlayer<CombatTracker>();
			DamageWindow damage = tracker.GetRecentDamage(currentTick);
			bool bossActive = activeBosses.Length > 0;
			bool inCombat = bossActive || damage.HasHostileDamage;
			float combatDuration = tracker.UpdateCombatState(inCombat, currentTick);
			
			float hpRatio = player.statLifeMax2 > 0
				? Math.Clamp((float)player.statLife / player.statLifeMax2, 0f, 1f)
				: 0f;

			return new CombatSnapshot(
				InCombat: inCombat,
				CombatDurationSeconds: combatDuration,
				BossActive: bossActive,
				ActiveBosses: activeBosses,
				NearbyEnemyCount: nearbyEnemyCount,
				HpRatio: hpRatio,
				RecentDamage: new RecentDamageSnapshot(
					DamageTakenLast5s: damage.TotalDamage,
					LastDamageAmount: damage.LastDamageAmount,
					LastDamageSource: damage.LastDamageSource,
					TimeSinceLastDamageSeconds: damage.TimeSinceLastDamageSeconds));
		}

		private static int CaptureNpcContext(Player player, List<BossCombatSummary> bosses)
		{
			float radiusPixels = NearbyEnemyRadius * PixelsPerTile;
			float radiusSquared = radiusPixels * radiusPixels;
			int nearbyEnemyCount = 0;

			for (int i = 0; i < Main.maxNPCs; i++)
			{
				NPC npc = Main.npc[i];
				if (!npc.active) continue;

				if (npc.boss)
				{
					float lifeRatio = npc.lifeMax > 0
						? Math.Clamp((float)npc.life / npc.lifeMax, 0f, 1f)
						: 0f;
					bosses.Add(new BossCombatSummary(npc.type, npc.FullName, lifeRatio));
					continue;
				}

				if (npc.townNPC
					|| NPCID.Sets.CountsAsCritter[npc.type] || !npc.CanBeChasedBy())
				{
					continue;
				}

				if (Vector2.DistanceSquared(player.Center, npc.Center) <= radiusSquared)
				{
					nearbyEnemyCount++;
				}
			}

			return nearbyEnemyCount;
		}
	}
}
