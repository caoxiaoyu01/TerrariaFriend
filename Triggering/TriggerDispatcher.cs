#nullable enable

using System;
using System.Collections.Concurrent;

namespace TerrariaFriend.Triggering
{
	// 统一生成 TriggerEvent 并写入通信入口队列
	public sealed class TriggerDispatcher
	{
		// 创建 trigger 事件队列
		private readonly ConcurrentQueue<TriggerEvent> _pending = new ConcurrentQueue<TriggerEvent>();

		public event Action<TriggerEvent>? TriggerDispatched;

		public int PendingCount => _pending.Count;

		// 三种 triggerEvent -> event 实例
		public TriggerEvent DispatchUserQuery(string query, VitalsContext vitals)
		{
			if (string.IsNullOrWhiteSpace(query))
			{
				throw new ArgumentException("User query cannot be empty.", nameof(query));
			}

			return Dispatch(new TriggerEvent(
				TriggerType.USER_QUERY,
				DateTimeOffset.UtcNow,
				TriggerPriority.HIGH,
				vitals,
				UserQuery: query));
		}

		public TriggerEvent DispatchGameEvent(
			GameEvent gameEvent,
			GameEventContext eventContext,
			VitalsContext vitals)
		{
			return Dispatch(new TriggerEvent(
				TriggerType.GAME_EVENT,
				DateTimeOffset.UtcNow,
				TriggerPriority.NORMAL,
				vitals,
				GameEvent: gameEvent,
				EventContext: eventContext));
		}

		public TriggerEvent DispatchPeriodic(PeriodicSummary summary, VitalsContext vitals)
		{
			return Dispatch(new TriggerEvent(
				TriggerType.PERIODIC,
				DateTimeOffset.UtcNow,
				TriggerPriority.LOW,
				vitals,
				PeriodicSummary: summary));
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
			// 放入队列
			_pending.Enqueue(trigger);
			TriggerDispatched?.Invoke(trigger);
			return trigger;
		}

	}
}
