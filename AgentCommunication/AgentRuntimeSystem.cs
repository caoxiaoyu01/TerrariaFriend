#nullable enable

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading.Tasks;
using Terraria;
using Terraria.ModLoader;
using TerrariaFriend.Common.Systems;
using TerrariaFriend.Triggering;

namespace TerrariaFriend.AgentCommunication
{
	[Autoload(Side = ModSide.Client)]
	public sealed class AgentRuntimeSystem : ModSystem
	{
		private readonly AgentClient _client = new AgentClient();

		// 用户问题和游戏事件分开排队 方便保证处理顺序
		private readonly Queue<TriggerEvent> _pendingUserQueries = new Queue<TriggerEvent>();
		private readonly Queue<TriggerEvent> _pendingGameEvents = new Queue<TriggerEvent>();

		// 后台线程只存放结果 界面由游戏主线程更新
		private readonly ConcurrentQueue<(TriggerType TriggerType, string SessionId, AgentResponse Response)> _completedResponses = new();
		private Task? _activeRequest;
		private System.Threading.CancellationTokenSource? _activeRequestCancellation;
		private string? _currentSessionId;

		public override void OnWorldLoad()
		{
			CancelActiveRequest();
			ClearPending();
			TriggerSystem triggerSystem = ModContent.GetInstance<TriggerSystem>();
			_currentSessionId = triggerSystem.CurrentSessionId;
			triggerSystem.BoundarySignalDispatched -= HandleBoundarySignal;
			triggerSystem.BoundarySignalDispatched += HandleBoundarySignal;
		}

		private void HandleBoundarySignal(GameEvent gameEvent)
		{
			if (gameEvent.EventType != GameEventType.WorldSessionEnded) return;

			// 离开世界时清空还未处理的普通请求
			// 此时等待服务端保存并关闭当前记忆轨迹
			try
			{
				TriggerSystem triggerSystem = ModContent.GetInstance<TriggerSystem>();
				if (triggerSystem.CurrentWorldId == null || triggerSystem.CurrentSessionId == null) return;
				using var timeout = new System.Threading.CancellationTokenSource(
					AgentConfiguration.BoundarySignalTimeout);
				_client.SendWorldSessionEndedAsync(
						DateTimeOffset.UtcNow,
						triggerSystem.CurrentWorldId,
						triggerSystem.CurrentSessionId,
						timeout.Token)
					.GetAwaiter()
					.GetResult();
				Mod.Logger.Info("[AgentRuntime] WorldSessionEnded delivered to L1.");
			}
			catch (Exception exception)
			{
				Mod.Logger.Error($"Failed to deliver WorldSessionEnded: {exception}");
			}
		}

		public override void OnWorldUnload()
		{
			CancelActiveRequest();
			_currentSessionId = null;
			ClearPending();
		}

		public override void PostUpdatePlayers()
		{
			_currentSessionId ??= ModContent.GetInstance<TriggerSystem>().CurrentSessionId;

			// 先处理上一个请求的结果
			if (_activeRequest?.IsCompleted == true)
			{
				_activeRequest = null;
				_activeRequestCancellation?.Dispose();
				_activeRequestCancellation = null;
			}
			ProcessCompletedResponses();

			if (Main.gameMenu) return;

			// 按优先级取出下一个事件
			TriggerEvent? periodic = DrainIncomingTriggers();
			if (_activeRequest != null) return;

			TriggerEvent? next = TakeNextPending() ?? periodic;
			if (next == null) return;

			// 请求放到后台执行 同一时间只发送一个
			Mod.Logger.Info($"[AgentRuntime] sending {next.TriggerType}");
			_activeRequestCancellation = new System.Threading.CancellationTokenSource();
			_activeRequest = SendAndCaptureAsync(next, _activeRequestCancellation.Token);
		}

		// 玩家问题优先于游戏事件 周期检查不进入等待队列
		private TriggerEvent? DrainIncomingTriggers()
		{
			TriggerEvent? periodic = null;
			while (TriggerSystem.TryDequeue(out TriggerEvent? trigger) && trigger != null)
			{
				// 从优先级最高的队列取出事件
				switch (trigger.TriggerType)
				{
					case TriggerType.USER_QUERY:
						_pendingUserQueries.Enqueue(trigger);
						LogQueue("enqueued", trigger, DateTimeOffset.UtcNow);
						break;
					case TriggerType.GAME_EVENT:
						EnqueueGameEvent(trigger);
						break;
					case TriggerType.PERIODIC:
						if (periodic != null)
						{
							LogQueue("dropped_periodic_busy", trigger, DateTimeOffset.UtcNow);
						}
						else
						{
							periodic = trigger;
						}
						break;
				}
			}

			if (periodic != null && TriggerQueuePolicy.ShouldDropPeriodic(
				_activeRequest != null || _pendingUserQueries.Count > 0 || _pendingGameEvents.Count > 0))
			{
				LogQueue("dropped_periodic_busy", periodic, DateTimeOffset.UtcNow);
				return null;
			}
			if (periodic != null) LogQueue("enqueued", periodic, DateTimeOffset.UtcNow);

			return periodic;
		}

		private void EnqueueGameEvent(TriggerEvent trigger)
		{
			GameEvent? gameEvent = trigger.GameEvent;
			if (gameEvent != null && TriggerQueuePolicy.IsLatestWins(gameEvent.EventType))
			{
				int pendingCount = _pendingGameEvents.Count;
				for (int index = 0; index < pendingCount; index++)
				{
					TriggerEvent queued = _pendingGameEvents.Dequeue();
					if (queued.GameEvent != null && TriggerQueuePolicy.ShouldReplace(
						queued.GameEvent.EventType,
						gameEvent.EventType))
					{
						LogQueue("replaced_by_newer", queued, DateTimeOffset.UtcNow);
						continue;
					}
					_pendingGameEvents.Enqueue(queued);
				}
			}

			_pendingGameEvents.Enqueue(trigger);
			LogQueue("enqueued", trigger, DateTimeOffset.UtcNow);
		}

		private TriggerEvent? TakeNextPending()
		{
			// 始终先处理玩家问题
			if (_pendingUserQueries.Count > 0)
			{
				return _pendingUserQueries.Dequeue();
			}

			while (_pendingGameEvents.Count > 0)
			{
				TriggerEvent trigger = _pendingGameEvents.Dequeue();
				DateTimeOffset now = DateTimeOffset.UtcNow;
				if (trigger.GameEvent != null &&
					TriggerQueuePolicy.IsProtected(trigger.GameEvent.EventType) &&
					now - trigger.Timestamp > AgentConfiguration.GameEventTtl)
				{
					LogQueue("protected_event_kept", trigger, now);
				}
				if (TriggerQueuePolicy.IsExpired(trigger, now, AgentConfiguration.GameEventTtl))
				{
					LogQueue("dropped_expired", trigger, now);
					continue;
				}
				return trigger;
			}

			return null;
		}

		private void LogQueue(string action, TriggerEvent trigger, DateTimeOffset now)
		{
			string eventType = trigger.GameEvent?.EventType.ToString() ?? "none";
			double age = TriggerQueuePolicy.AgeSeconds(trigger, now);
			int queueSize = _pendingUserQueries.Count + _pendingGameEvents.Count;
			Mod.Logger.Info(
				$"[TriggerQueue] action={action} trigger={trigger.TriggerType} " +
				$"event={eventType} age={age:F1}s size={queueSize}");
		}

		private async Task SendAndCaptureAsync(
			TriggerEvent trigger,
			System.Threading.CancellationToken cancellationToken)
		{
			try
			{
				// 记录真正发送请求的时间
				AgentResponse response = await _client.SendTriggerAsync(trigger, cancellationToken)
					.ConfigureAwait(false);
				// 把回复交回游戏主线程
				_completedResponses.Enqueue((trigger.TriggerType, trigger.SessionId, response));
			}
			catch (Exception exception)
			{
				_completedResponses.Enqueue((
					trigger.TriggerType,
					trigger.SessionId,
					new AgentResponse(
						"ERROR",
						null,
						null,
						false,
						$"Unexpected Agent request failure: {exception.Message}")));
			}
		}

		// 这里运行在游戏主线程 可以安全更新界面
		private void ProcessCompletedResponses()
		{
			while (_completedResponses.TryDequeue(out var completed))
			{
				(TriggerType triggerType, string sessionId, AgentResponse response) = completed;
				if (!string.Equals(sessionId, _currentSessionId, StringComparison.Ordinal))
				{
					Mod.Logger.Info($"Dropped stale Agent response from session {sessionId}.");
					continue;
				}
				if (!response.Success)
				{
					Mod.Logger.Warn($"Agent request failed [{triggerType}]: {response.Error}");
					continue;
				}

				Mod.Logger.Info($"Agent response [{triggerType}][{response.Action}]: {response.Message}");
				Mod.Logger.Info($"Decision reason: {response.DecisionReason}");
				if (!string.IsNullOrWhiteSpace(response.Message))
				{
					AgentMessageUISystem.ShowMessage(response.Message);
				}
			}
		}

		private void ClearPending()
		{
			// 切换世界后丢弃旧世界尚未处理的事件
			_pendingUserQueries.Clear();
			_pendingGameEvents.Clear();
		}

		private void CancelActiveRequest()
		{
			_activeRequestCancellation?.Cancel();
			_activeRequestCancellation?.Dispose();
			_activeRequestCancellation = null;
			_activeRequest = null;
		}
	}
}
