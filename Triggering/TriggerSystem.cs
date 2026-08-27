#nullable enable

using System;
using System.Collections.Generic;
using System.Linq;
using Terraria;
using Terraria.ModLoader;
using TerrariaFriend.GameState;
using TerrariaFriend.GameState.Snapshots;
using TerrariaFriend.GameState.Tracking;

namespace TerrariaFriend.Triggering
{
	[Autoload(Side = ModSide.Client)]
	public sealed class TriggerSystem : ModSystem
	{
		private const uint SnapshotPollIntervalTicks = 10;

		private readonly EventDetector _eventDetector = new EventDetector();
		private readonly EquipmentChangeDetector _equipmentChangeDetector = new EquipmentChangeDetector();
		private readonly SceneFeatureExitDetector _sceneFeatureExitDetector = new SceneFeatureExitDetector();
		private readonly ExplorationGridTracker _explorationGridTracker = new ExplorationGridTracker();
		private readonly PeriodicTriggerSource _periodicSource = new PeriodicTriggerSource();
		private readonly TriggerDispatcher _dispatcher = new TriggerDispatcher();
		private float? _previousVitalsHpRatio;

		// 世界卸载时同步触发且不经过随后会被清空的等待队列
		public event Action<GameEvent>? BoundarySignalDispatched;

		public override void OnWorldLoad()
		{
			Reset();
		}

		public override void OnWorldUnload()
		{
			DispatchBoundarySignal(new GameEvent(GameEventType.WorldSessionEnded));
			Reset();
		}

		public override void PostUpdatePlayers()
		{
			if (Main.gameMenu || !Main.LocalPlayer.active) return;

			bool periodicDue = _periodicSource.TryConsumeDueTrigger();
			bool snapshotDue = Main.GameUpdateCount % SnapshotPollIntervalTicks == 0;
			if (!periodicDue && !snapshotDue) return;

			// 同一 tick 只采集一次完整 Snapshot
			GameSnapshot snapshot = GameStateCollector.Capture();
			_previousVitalsHpRatio ??= snapshot.Combat.HpRatio;
			if (snapshotDue)
			{
				IReadOnlyList<GameEvent> detectedEvents = _eventDetector.Detect(snapshot);
				foreach (GameEvent gameEvent in detectedEvents)
				{
					_sceneFeatureExitDetector.Arm(gameEvent, snapshot.Tick);
					GameEventContext context = GameEventContextCollector.Capture(gameEvent, snapshot);
					_dispatcher.DispatchGameEvent(
						gameEvent,
						context,
						CaptureVitals(snapshot),
						snapshot);
				}

				foreach (GameEvent sceneExitEvent in _sceneFeatureExitDetector.Detect(snapshot))
				{
					GameEventContext context = GameEventContextCollector.Capture(sceneExitEvent, snapshot);
					_dispatcher.DispatchGameEvent(
						sceneExitEvent,
						context,
						CaptureVitals(snapshot),
						snapshot);
				}

				if (_equipmentChangeDetector.TryDetect(
					snapshot,
					out GameEvent? equipmentEvent,
					out GameEventContext? equipmentContext))
				{
					_dispatcher.DispatchGameEvent(
						equipmentEvent!,
						equipmentContext!,
						CaptureVitals(snapshot),
						snapshot);
				}

				if (_explorationGridTracker.TryDiscover(snapshot, out GameEvent? explorationEvent, out GameEventContext? explorationContext))
				{
					_dispatcher.DispatchGameEvent(
						explorationEvent!,
						explorationContext!,
						CaptureVitals(snapshot),
						snapshot);
				}

			}

			if (periodicDue)
			{
				_dispatcher.DispatchPeriodic(
					CreatePeriodicSummary(snapshot),
					CaptureVitals(snapshot),
					snapshot);
			}
		}

		// 未来游戏输入框调用此入口
		public static TriggerEvent SubmitUserQuery(string query)
		{
			TriggerSystem system = ModContent.GetInstance<TriggerSystem>();
			system.Mod.Logger.Info($"[UserQuery] submitted: \"{query}\"");
			GameSnapshot snapshot = GameStateCollector.Capture();
			return system._dispatcher.DispatchUserQuery(
				query,
				system.CaptureVitals(snapshot),
				snapshot);
		}

		// 钩子产生的游戏事件也统一进入调度器
		internal static TriggerEvent SubmitGameEvent(GameEvent gameEvent)
		{
			// 钩子事件发生频率低 在这里采集一次当前上下文
			GameSnapshot snapshot = GameStateCollector.Capture();
			GameEventContext context = GameEventContextCollector.Capture(gameEvent, snapshot);
			TriggerSystem system = ModContent.GetInstance<TriggerSystem>();
			return system._dispatcher.DispatchGameEvent(
				gameEvent,
				context,
				system.CaptureVitals(snapshot),
				snapshot);
		}

		// 未来 HTTP/WebSocket transport 从此处消费待发送事件
		public static bool TryDequeue(out TriggerEvent? trigger)
		{
			return ModContent.GetInstance<TriggerSystem>()._dispatcher.TryDequeue(out trigger);
		}

		public static int PendingCount => ModContent.GetInstance<TriggerSystem>()._dispatcher.PendingCount;

		private PeriodicSummary CreatePeriodicSummary(GameSnapshot snapshot)
		{
			string progressionStage = snapshot.Progress.CurrentStage.Id;

			// 只复制 Decision Node 当前需要的轻量字段
			return new PeriodicSummary(
				snapshot.Scene.Biomes.ToArray(),
				snapshot.Scene.Layer,
				snapshot.Combat.ActiveBosses.Select(boss => boss.Name).ToArray(),
				progressionStage,
				snapshot.Player.HeldItem.Name);
		}

		private VitalsContext CaptureVitals(GameSnapshot snapshot)
		{
			float hpRatio = snapshot.Combat.HpRatio;
			float hpDelta = _previousVitalsHpRatio.HasValue
				? hpRatio - _previousVitalsHpRatio.Value
				: 0f;
			_previousVitalsHpRatio = hpRatio;

			return new VitalsContext(hpRatio, hpDelta, snapshot.Combat.InCombat);
		}

		private void Reset()
		{
			_eventDetector.Reset();
			_equipmentChangeDetector.Reset();
			_sceneFeatureExitDetector.Reset();
			_explorationGridTracker.Reset();
			_periodicSource.Reset();
			_dispatcher.Clear();
			_previousVitalsHpRatio = null;
		}

		private void DispatchBoundarySignal(GameEvent gameEvent)
		{
			if (BoundarySignalDispatched == null) return;
			foreach (Action<GameEvent> handler in BoundarySignalDispatched.GetInvocationList())
			{
				try
				{
					handler(gameEvent);
				}
				catch (Exception exception)
				{
					Mod.Logger.Error($"Boundary signal handler failed: {exception}");
				}
			}
		}
	}
}
