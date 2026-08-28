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
		private readonly HashSet<GameEvent> _pendingGameEventKeys = new HashSet<GameEvent>();

		// 后台线程只存放结果 界面由游戏主线程更新
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

			// 离开世界时清空还未处理的普通请求
			// 此时等待服务端保存并关闭当前记忆轨迹
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

			// 先处理上一个请求的结果
			if (_activeRequest?.IsCompleted == true) _activeRequest = null;
			ProcessCompletedResponses();

			if (Main.gameMenu) return;

			// 按优先级取出下一个事件
			TriggerEvent? periodic = DrainIncomingTriggers();
			if (_activeRequest != null) return;

			TriggerEvent? next = TakeNextPending() ?? periodic;
			if (next == null) return;

			// 请求放到后台执行 同一时间只发送一个
			Mod.Logger.Info($"[AgentRuntime] sending {next.TriggerType}");
			_activeRequest = SendAndCaptureAsync(next);
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
			// 只合并仍在排队且内容完全相同的事件
			if (trigger.GameEvent == null || _pendingGameEventKeys.Add(trigger.GameEvent))
			{
				_pendingGameEvents.Enqueue(trigger);
			}
		}

		private TriggerEvent? TakeNextPending()
		{
			// 始终先处理玩家问题
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
				// 记录真正发送请求的时间
				AgentResponse response = await _client.SendTriggerAsync(trigger).ConfigureAwait(false);
				// 把回复交回游戏主线程
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

		// 这里运行在游戏主线程 可以安全更新界面
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
			// 切换世界后丢弃旧世界尚未处理的事件
			_pendingUserQueries.Clear();
			_pendingGameEvents.Clear();
			_pendingGameEventKeys.Clear();
		}
	}
}
