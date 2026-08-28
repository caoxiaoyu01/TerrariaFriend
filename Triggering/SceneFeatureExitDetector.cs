#nullable enable

using System;
using System.Collections.Generic;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 只检测重要场景的稳定离开 进入事件由别处负责
	public sealed class SceneFeatureExitDetector
	{
		private static readonly FeatureDefinition[] Features =
		{
			new FeatureDefinition("SPECIAL_AREA", SceneFeatureNames.SpecialArea.Dungeon, false),
			new FeatureDefinition("SPECIAL_AREA", SceneFeatureNames.SpecialArea.JungleTemple, false),
			new FeatureDefinition("MINI_BIOME", SceneFeatureNames.MiniBiome.BeeHive, true)
		};

		private readonly Dictionary<string, FeatureState> _states = new Dictionary<string, FeatureState>();

		// 只有已经发出过进入事件的场景 才能再发出一次对应的离开事件
		public void Arm(GameEvent enteredEvent, uint tick)
		{
			if (enteredEvent.EventType != GameEventType.SceneFeatureEntered) return;
			string key = DiscoverableSceneFeatures.CreateKey(
				enteredEvent.SubjectId ?? string.Empty,
				enteredEvent.SubjectName ?? string.Empty);
			foreach (FeatureDefinition feature in Features)
			{
				if (DiscoverableSceneFeatures.CreateKey(feature.Category, feature.Name) != key) continue;
				_states[key] = new FeatureState(FeaturePhase.Inside, tick);
				return;
			}
		}

		public IReadOnlyList<GameEvent> Detect(GameSnapshot snapshot)
		{
			List<GameEvent> events = new List<GameEvent>();
			foreach (FeatureDefinition feature in Features)
			{
				bool inside = feature.IsMiniBiome
					? Contains(snapshot.Scene.MiniBiomes, feature.Name)
					: Contains(snapshot.Scene.SpecialAreas, feature.Name);
				Observe(feature, inside, snapshot.Tick, events);
			}
			return events.ToArray();
		}

		public void Reset()
		{
			_states.Clear();
		}

		private void Observe(
			FeatureDefinition feature,
			bool inside,
			uint tick,
			List<GameEvent> events)
		{
			string key = DiscoverableSceneFeatures.CreateKey(feature.Category, feature.Name);
			if (!_states.TryGetValue(key, out FeatureState? state)) return;

			switch (state.Phase)
			{
				case FeaturePhase.Inside:
					if (!inside)
					{
						state.Phase = FeaturePhase.ExitPending;
						state.PendingSinceTick = tick;
					}
					break;

				case FeaturePhase.ExitPending:
					if (inside)
					{
						state.Phase = FeaturePhase.Inside;
						state.PendingSinceTick = 0;
					}
					else if (unchecked(tick - state.PendingSinceTick)
						>= BoundaryEventConfig.SceneFeatureExitDebounceTicks)
					{
						events.Add(new GameEvent(
							GameEventType.SceneFeatureExited,
							feature.Category,
							feature.Name));
						_states.Remove(key);
					}
					break;
			}
		}

		private static bool Contains(IReadOnlyList<string> values, string target)
		{
			foreach (string value in values)
			{
				if (string.Equals(value, target, StringComparison.Ordinal)) return true;
			}
			return false;
		}

		private sealed record FeatureDefinition(
			string Category,
			string Name,
			bool IsMiniBiome);

		private sealed class FeatureState
		{
			public FeatureState(FeaturePhase phase, uint pendingSinceTick)
			{
				Phase = phase;
				PendingSinceTick = pendingSinceTick;
			}

			public FeaturePhase Phase;
			public uint PendingSinceTick;
		}

		private enum FeaturePhase
		{
			Inside,
			ExitPending
		}
	}
}
