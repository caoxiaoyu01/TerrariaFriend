#nullable enable

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
		private readonly ExplorationGridTracker _explorationGridTracker = new ExplorationGridTracker();
		private readonly PeriodicTriggerSource _periodicSource = new PeriodicTriggerSource();
		private readonly TriggerDispatcher _dispatcher = new TriggerDispatcher();
		private float? _previousVitalsHpRatio;

		public override void OnWorldLoad()
		{
			Reset();
		}

		public override void OnWorldUnload()
		{
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
				if (_explorationGridTracker.TryDiscover(snapshot, out GameEvent? explorationEvent, out GameEventContext? explorationContext))
				{
					_dispatcher.DispatchGameEvent(
						explorationEvent!,
						explorationContext!,
						CaptureVitals(snapshot));
				}

				foreach (GameEvent gameEvent in _eventDetector.Detect(snapshot))
				{
					GameEventContext context = GameEventContextCollector.Capture(gameEvent, snapshot);
					_dispatcher.DispatchGameEvent(gameEvent, context, CaptureVitals(snapshot));
				}
			}

			if (periodicDue)
			{
				_dispatcher.DispatchPeriodic(CreatePeriodicSummary(snapshot), CaptureVitals(snapshot));
			}
		}

		// 未来游戏输入框调用此入口
		public static TriggerEvent SubmitUserQuery(string query)
		{
			TriggerSystem system = ModContent.GetInstance<TriggerSystem>();
			system.Mod.Logger.Info($"[UserQuery] submitted: \"{query}\"");
			GameSnapshot snapshot = GameStateCollector.Capture();
			return system._dispatcher.DispatchUserQuery(query, system.CaptureVitals(snapshot));
		}

		// Hook 产生的游戏事件也统一进入 Dispatcher
		internal static TriggerEvent SubmitGameEvent(GameEvent gameEvent)
		{
			// Hook 事件发生频率低 在这里采集一次当前上下文
			GameSnapshot snapshot = GameStateCollector.Capture();
			GameEventContext context = GameEventContextCollector.Capture(gameEvent, snapshot);
			TriggerSystem system = ModContent.GetInstance<TriggerSystem>();
			return system._dispatcher.DispatchGameEvent(gameEvent, context, system.CaptureVitals(snapshot));
		}

		// 未来 HTTP/WebSocket transport 从此处消费待发送事件
		public static bool TryDequeue(out TriggerEvent? trigger)
		{
			return ModContent.GetInstance<TriggerSystem>()._dispatcher.TryDequeue(out trigger);
		}

		public static int PendingCount => ModContent.GetInstance<TriggerSystem>()._dispatcher.PendingCount;

		private PeriodicSummary CreatePeriodicSummary(GameSnapshot snapshot)
		{
			// 使用最后一个已解锁里程碑描述当前进度阶段
			string progressionStage = snapshot.Progress.WorldMilestones.LastOrDefault() ?? "Pre-Hardmode";

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
			_explorationGridTracker.Reset();
			_periodicSource.Reset();
			_dispatcher.Clear();
			_previousVitalsHpRatio = null;
		}
	}
}
