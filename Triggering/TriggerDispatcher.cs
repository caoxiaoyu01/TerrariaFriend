#nullable enable

using System;
using System.Collections.Concurrent;

namespace TerrariaFriend.Triggering
{
	// 统一生成 TriggerEvent；未来通信层从队列读取并发送给 Python。
	public sealed class TriggerDispatcher
	{
		private readonly ConcurrentQueue<TriggerEvent> _pending = new ConcurrentQueue<TriggerEvent>();

		public event Action<TriggerEvent>? TriggerDispatched;

		public int PendingCount => _pending.Count;

		public TriggerEvent DispatchUserQuery(string query)
		{
			if (string.IsNullOrWhiteSpace(query))
			{
				throw new ArgumentException("User query cannot be empty.", nameof(query));
			}

			return Dispatch(new TriggerEvent(
				TriggerType.USER_QUERY,
				DateTimeOffset.UtcNow,
				TriggerPriority.HIGH,
				UserQuery: query));
		}

		public TriggerEvent DispatchGameEvent(GameEvent gameEvent)
		{
			return Dispatch(new TriggerEvent(
				TriggerType.GAME_EVENT,
				DateTimeOffset.UtcNow,
				GetPriority(gameEvent.EventType),
				GameEvent: gameEvent));
		}

		public TriggerEvent DispatchPeriodic()
		{
			return Dispatch(new TriggerEvent(
				TriggerType.PERIODIC,
				DateTimeOffset.UtcNow,
				TriggerPriority.LOW));
		}

		public bool TryDequeue(out TriggerEvent? trigger)
		{
			return _pending.TryDequeue(out trigger);
		}

		public void Clear()
		{
			while (_pending.TryDequeue(out _)) { }
		}

		private TriggerEvent Dispatch(TriggerEvent trigger)
		{
			_pending.Enqueue(trigger);
			TriggerDispatched?.Invoke(trigger);
			return trigger;
		}

		private static TriggerPriority GetPriority(GameEventType eventType)
		{
			return eventType switch
			{
				GameEventType.PlayerDied => TriggerPriority.HIGH,
				GameEventType.BossSpawned => TriggerPriority.HIGH,
				GameEventType.BossEnded => TriggerPriority.HIGH,
				GameEventType.ProgressMilestoneChanged => TriggerPriority.HIGH,
				_ => TriggerPriority.NORMAL
			};
		}
	}
}
