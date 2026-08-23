#nullable enable

using System;
using System.Collections.Generic;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 比较相邻 Snapshot，只报告刚刚发生的状态变化。
	public sealed class EventDetector
	{
		private GameSnapshot? _previous;

		public IReadOnlyList<GameEvent> Detect(GameSnapshot current)
		{
			if (_previous == null)
			{
				_previous = current;
				return Array.Empty<GameEvent>();
			}

			GameSnapshot previous = _previous;
			List<GameEvent> events = new List<GameEvent>();

			DetectBossChanges(previous, current, events);
			DetectWorldEventChanges(previous, current, events);
			DetectSpecialNpcAppearances(previous, current, events);
			DetectProgressChanges(previous, current, events);

			_previous = current;
			return events.ToArray();
		}

		public void Reset()
		{
			_previous = null;
		}

		private static void DetectBossChanges(
			GameSnapshot previous,
			GameSnapshot current,
			List<GameEvent> events)
		{
			Dictionary<int, BossCombatSummary> previousBosses = IndexBosses(previous.Combat.ActiveBosses);
			Dictionary<int, BossCombatSummary> currentBosses = IndexBosses(current.Combat.ActiveBosses);

			foreach ((int typeId, BossCombatSummary boss) in currentBosses)
			{
				if (!previousBosses.ContainsKey(typeId))
				{
					events.Add(new GameEvent(GameEventType.BossSpawned, typeId.ToString(), boss.Name));
				}
			}

			foreach ((int typeId, BossCombatSummary boss) in previousBosses)
			{
				if (!currentBosses.ContainsKey(typeId))
				{
					events.Add(new GameEvent(GameEventType.BossEnded, typeId.ToString(), boss.Name));
				}
			}
		}

		private static void DetectWorldEventChanges(
			GameSnapshot previous,
			GameSnapshot current,
			List<GameEvent> events)
		{
			Dictionary<string, WorldEventSnapshot> previousEvents = IndexWorldEvents(previous.World.ActiveEvents);
			Dictionary<string, WorldEventSnapshot> currentEvents = IndexWorldEvents(current.World.ActiveEvents);

			foreach ((string id, WorldEventSnapshot worldEvent) in currentEvents)
			{
				if (!previousEvents.ContainsKey(id))
				{
					events.Add(new GameEvent(GameEventType.WorldEventStarted, id, worldEvent.Name));
				}
			}

			foreach ((string id, WorldEventSnapshot worldEvent) in previousEvents)
			{
				if (!currentEvents.ContainsKey(id))
				{
					events.Add(new GameEvent(GameEventType.WorldEventEnded, id, worldEvent.Name));
				}
			}
		}

		private static void DetectSpecialNpcAppearances(
			GameSnapshot previous,
			GameSnapshot current,
			List<GameEvent> events)
		{
			HashSet<int> previousTypes = new HashSet<int>();
			foreach (SpecialNpcSummary npc in previous.Npc.SpecialNpcs) previousTypes.Add(npc.TypeId);

			foreach (SpecialNpcSummary npc in current.Npc.SpecialNpcs)
			{
				if (!previousTypes.Contains(npc.TypeId))
				{
					events.Add(new GameEvent(
						GameEventType.SpecialNpcAppeared,
						npc.TypeId.ToString(),
						npc.Name));
				}
			}
		}

		private static void DetectProgressChanges(
			GameSnapshot previous,
			GameSnapshot current,
			List<GameEvent> events)
		{
			DetectNewProgressItems(
				previous.Progress.DefeatedBosses,
				current.Progress.DefeatedBosses,
				"Boss",
				events);
			DetectNewProgressItems(
				previous.Progress.WorldMilestones,
				current.Progress.WorldMilestones,
				"WorldMilestone",
				events);
		}

		private static void DetectNewProgressItems(
			IReadOnlyList<string> previous,
			IReadOnlyList<string> current,
			string category,
			List<GameEvent> events)
		{
			HashSet<string> previousItems = new HashSet<string>(previous);
			foreach (string item in current)
			{
				if (!previousItems.Contains(item))
				{
					events.Add(new GameEvent(
						GameEventType.ProgressMilestoneChanged,
						$"{category}:{item}",
						item));
				}
			}
		}

		private static Dictionary<int, BossCombatSummary> IndexBosses(
			IReadOnlyList<BossCombatSummary> bosses)
		{
			Dictionary<int, BossCombatSummary> index = new Dictionary<int, BossCombatSummary>();
			foreach (BossCombatSummary boss in bosses) index[boss.TypeId] = boss;
			return index;
		}

		private static Dictionary<string, WorldEventSnapshot> IndexWorldEvents(
			IReadOnlyList<WorldEventSnapshot> worldEvents)
		{
			Dictionary<string, WorldEventSnapshot> index = new Dictionary<string, WorldEventSnapshot>();
			foreach (WorldEventSnapshot worldEvent in worldEvents) index[worldEvent.Id] = worldEvent;
			return index;
		}
	}
}
