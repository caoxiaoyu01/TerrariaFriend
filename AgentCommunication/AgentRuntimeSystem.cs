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

		// 用户查询与游戏事件分队列保存以保证固定优先级
		private readonly Queue<TriggerEvent> _pendingUserQueries = new Queue<TriggerEvent>();
		private readonly Queue<TriggerEvent> _pendingGameEvents = new Queue<TriggerEvent>();
		private readonly HashSet<GameEvent> _pendingGameEventKeys = new HashSet<GameEvent>();

		// 后台请求只写入此队列 主线程负责读取并更新 UI
		private readonly ConcurrentQueue<(TriggerType TriggerType, AgentResponse Response)> _completedResponses = new();
		private Task? _activeRequest;

		public override void OnWorldLoad()
		{
			ClearPending();
			TriggerSystem triggerSystem = ModContent.GetInstance<TriggerSystem>();
			triggerSystem.BoundarySignalDispatched -= HandleBoundarySignal;
			triggerSystem.BoundarySignalDispatched += HandleBoundarySignal;
		}

		private void HandleBoundarySignal(GameEvent gameEvent)
		{
			if (gameEvent.EventType != GameEventType.WorldSessionEnded) return;

			// 世界卸载会立即清空普通队列
			// 仅在这个少见边界等待 Python 持久关闭当前一级轨迹
			try
			{
				using var timeout = new System.Threading.CancellationTokenSource(
					AgentConfiguration.BoundarySignalTimeout);
				_client.SendWorldSessionEndedAsync(DateTimeOffset.UtcNow, timeout.Token)
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
			ClearPending();
		}

		public override void PostUpdatePlayers()
		{

			// 检查上一个请求是否结束
			if (_activeRequest?.IsCompleted == true) _activeRequest = null;
			ProcessCompletedResponses();

			if (Main.gameMenu) return;

			// 按照优先级获取 trigger
			TriggerEvent? periodic = DrainIncomingTriggers();
			if (_activeRequest != null) return;

			TriggerEvent? next = TakeNextPending() ?? periodic;
			if (next == null) return;

			// 不等待网络结果；每次只允许一个在途请求
			Mod.Logger.Info($"[AgentRuntime] sending {next.TriggerType}");
			_activeRequest = SendAndCaptureAsync(next);
		}

		// 将入口队列整理成 USER_QUERY > GAME_EVENT 且 PERIODIC 永不进入 pending
		private TriggerEvent? DrainIncomingTriggers()
		{
			TriggerEvent? periodic = null;
			while (TriggerSystem.TryDequeue(out TriggerEvent? trigger) && trigger != null)
			{
				// 按照优先级选取事件 priority queue
				switch (trigger.TriggerType)
				{
					case TriggerType.USER_QUERY:
						_pendingUserQueries.Enqueue(trigger);
						Mod.Logger.Info("[AgentRuntime] queued USER_QUERY");
						break;
					case TriggerType.GAME_EVENT:
						EnqueueGameEvent(trigger);
						break;
					case TriggerType.PERIODIC:
						periodic ??= trigger;
						break;
				}
			}

			if (periodic != null &&
				(_activeRequest != null || _pendingUserQueries.Count > 0 || _pendingGameEvents.Count > 0))
			{
				Mod.Logger.Debug("Dropped PERIODIC trigger because Agent runtime is busy.");
				return null;
			}

			return periodic;
		}

		private void EnqueueGameEvent(TriggerEvent trigger)
		{
			// 只对仍在等待的完全相同事件去重
			if (trigger.GameEvent == null || _pendingGameEventKeys.Add(trigger.GameEvent))
			{
				_pendingGameEvents.Enqueue(trigger);
			}
		}

		private TriggerEvent? TakeNextPending()
		{
			// 用户问题始终先于游戏事件
			if (_pendingUserQueries.Count > 0)
			{
				return _pendingUserQueries.Dequeue();
			}

			if (_pendingGameEvents.Count == 0) return null;

			TriggerEvent trigger = _pendingGameEvents.Dequeue();
			if (trigger.GameEvent != null) _pendingGameEventKeys.Remove(trigger.GameEvent);
			return trigger;
		}

		private async Task SendAndCaptureAsync(TriggerEvent trigger)
		{
			try
			{
				// 发送时事件
				AgentResponse response = await _client.SendTriggerAsync(trigger).ConfigureAwait(false);
				// 放入结果队列
				_completedResponses.Enqueue((trigger.TriggerType, response));
			}
			catch (Exception exception)
			{
				_completedResponses.Enqueue((
					trigger.TriggerType,
					new AgentResponse(
						"ERROR",
						null,
						null,
						false,
						$"Unexpected Agent request failure: {exception.Message}")));
			}
		}

		// 此方法只在游戏更新线程执行 因此可以安全更新 UI
		private void ProcessCompletedResponses()
		{
			while (_completedResponses.TryDequeue(out var completed))
			{
				(TriggerType triggerType, AgentResponse response) = completed;
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
			// 切换世界时不保留旧世界的待处理 Trigger
			_pendingUserQueries.Clear();
			_pendingGameEvents.Clear();
			_pendingGameEventKeys.Clear();
		}
	}
}
