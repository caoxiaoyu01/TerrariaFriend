#nullable enable

using System;
using System.Collections.Concurrent;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 统一创建触发事件并放入发送队列
	public sealed class TriggerDispatcher
	{
		// 保存等待发送的事件
		private readonly ConcurrentQueue<TriggerEvent> _pending = new ConcurrentQueue<TriggerEvent>();

		public event Action<TriggerEvent>? TriggerDispatched;

		public int PendingCount => _pending.Count;
		private string? _worldId;
		private string? _sessionId;

		public void SetSession(string worldId, string sessionId)
		{
			_worldId = worldId;
			_sessionId = sessionId;
		}

		// 为三种触发创建对应事件
		public TriggerEvent DispatchUserQuery(
			string query,
			VitalsContext vitals,
			GameSnapshot snapshot)
		{
			if (string.IsNullOrWhiteSpace(query))
			{
				throw new ArgumentException("User query cannot be empty.", nameof(query));
			}

			return Dispatch(new TriggerEvent(
				TriggerType.USER_QUERY,
				DateTimeOffset.UtcNow,
				RequireIdentity(_worldId, nameof(_worldId)),
				RequireIdentity(_sessionId, nameof(_sessionId)),
				TriggerPriority.HIGH,
				vitals,
				UserQuery: query,
				GameSnapshot: snapshot));
		}

		public TriggerEvent DispatchGameEvent(
			GameEvent gameEvent,
			GameEventContext eventContext,
			VitalsContext vitals,
			GameSnapshot snapshot)
		{
			return Dispatch(new TriggerEvent(
				TriggerType.GAME_EVENT,
				DateTimeOffset.UtcNow,
				RequireIdentity(_worldId, nameof(_worldId)),
				RequireIdentity(_sessionId, nameof(_sessionId)),
				TriggerPriority.NORMAL,
				vitals,
				GameEvent: gameEvent,
				EventContext: eventContext,
				GameSnapshot: snapshot));
		}

		public TriggerEvent DispatchPeriodic(
			PeriodicSummary summary,
			VitalsContext vitals,
			GameSnapshot snapshot)
		{
			return Dispatch(new TriggerEvent(
				TriggerType.PERIODIC,
				DateTimeOffset.UtcNow,
				RequireIdentity(_worldId, nameof(_worldId)),
				RequireIdentity(_sessionId, nameof(_sessionId)),
				TriggerPriority.LOW,
				vitals,
				PeriodicSummary: summary,
				GameSnapshot: snapshot));
		}

		public bool TryDequeue(out TriggerEvent? trigger)
		{
			return _pending.TryDequeue(out trigger);
		}

		public void Clear()
		{
			while (_pending.TryDequeue(out _)) { }
		}

		private static string RequireIdentity(string? value, string name)
		{
			return !string.IsNullOrWhiteSpace(value)
				? value
				: throw new InvalidOperationException($"{name} is not initialized");
		}

		private TriggerEvent Dispatch(TriggerEvent trigger)
		{
			// 等待通信模块发送
			_pending.Enqueue(trigger);
			TriggerDispatched?.Invoke(trigger);
			return trigger;
		}

	}
}
