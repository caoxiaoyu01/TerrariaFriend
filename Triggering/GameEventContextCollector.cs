#nullable enable

using System;
using System.Linq;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 从当前 Snapshot 提取事件判断需要的少量字段
	public static class GameEventContextCollector
	{
		public static GameEventContext Capture(GameEvent gameEvent, GameSnapshot snapshot)
		{
			return gameEvent.EventType switch
			{
				GameEventType.BossSpawned => new GameEventContext(
					NearbyEnemyCount: snapshot.Combat.NearbyEnemyCount),
				GameEventType.BossEnded => new GameEventContext(),
				GameEventType.SceneFeatureEntered => CaptureSceneContext(snapshot),
				GameEventType.WorldEventStarted => new GameEventContext(
					OccurrenceCount: GetWorldEventOccurrenceCount(gameEvent),
					ActiveEvents: GetActiveEvents(snapshot)),
				GameEventType.WorldEventEnded => new GameEventContext(
					OccurrenceCount: CompleteWorldEventOccurrence(gameEvent),
					ActiveEvents: GetActiveEvents(snapshot)),
				GameEventType.SpecialNpcAppeared => new GameEventContext(
					Biomes: snapshot.Scene.Biomes,
					IsNearby: GetSpecialNpcNearby(gameEvent, snapshot)),
				GameEventType.ProgressMilestoneChanged => new GameEventContext(
					Biomes: snapshot.Scene.Biomes),
				GameEventType.PlayerDied => new GameEventContext(
					Biomes: snapshot.Scene.Biomes,
					NearbyEnemyCount: snapshot.Combat.NearbyEnemyCount,
					BossActive: snapshot.Combat.BossActive,
					BossName: GetBossName(snapshot),
					DamageTakenLast5s: snapshot.Combat.RecentDamage.DamageTakenLast5s,
					LastDamageSource: snapshot.Combat.RecentDamage.LastDamageSource),
				_ => throw new ArgumentOutOfRangeException(nameof(gameEvent.EventType))
			};
		}

		private static GameEventContext CaptureSceneContext(GameSnapshot snapshot)
		{
			return new GameEventContext(
				ProgressionStage: snapshot.Progress.WorldMilestones.LastOrDefault() ?? "Pre-Hardmode",
				Biomes: snapshot.Scene.Biomes,
				Layer: snapshot.Scene.Layer,
				MiniBiomes: snapshot.Scene.MiniBiomes,
				SpecialAreas: snapshot.Scene.SpecialAreas);
		}

		private static int GetWorldEventOccurrenceCount(GameEvent gameEvent)
		{
			return ModContent.GetInstance<CompanionWorldState>()
				.GetWorldEventOccurrenceCount(gameEvent.SubjectId ?? gameEvent.SubjectName ?? "Unknown");
		}

		private static int CompleteWorldEventOccurrence(GameEvent gameEvent)
		{
			return ModContent.GetInstance<CompanionWorldState>()
				.CompleteWorldEventOccurrence(gameEvent.SubjectId ?? gameEvent.SubjectName ?? "Unknown");
		}

		private static string[] GetActiveEvents(GameSnapshot snapshot)
		{
			return snapshot.World.ActiveEvents.Select(worldEvent => worldEvent.Id).ToArray();
		}

		private static bool? GetSpecialNpcNearby(GameEvent gameEvent, GameSnapshot snapshot)
		{
			if (!int.TryParse(gameEvent.SubjectId, out int typeId)) return null;

			return snapshot.Npc.SpecialNpcs
				.FirstOrDefault(npc => npc.TypeId == typeId)
				?.IsNearby;
		}

		private static string? GetBossName(GameSnapshot snapshot)
		{
			if (snapshot.Combat.ActiveBosses.Count == 0) return null;
			return string.Join(", ", snapshot.Combat.ActiveBosses.Select(boss => boss.Name));
		}
	}
}
