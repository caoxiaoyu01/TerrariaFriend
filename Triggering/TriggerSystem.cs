#nullable enable

using Terraria;
using Terraria.ModLoader;
using TerrariaFriend.GameState;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	[Autoload(Side = ModSide.Client)]
	public sealed class TriggerSystem : ModSystem
	{
		private const uint SnapshotPollIntervalTicks = 10;

		private readonly EventDetector _eventDetector = new EventDetector();
		private readonly PeriodicTriggerSource _periodicSource = new PeriodicTriggerSource();
		private readonly TriggerDispatcher _dispatcher = new TriggerDispatcher();

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

			if (_periodicSource.TryConsumeDueTrigger())
			{
				_dispatcher.DispatchPeriodic();
			}

			if (Main.GameUpdateCount % SnapshotPollIntervalTicks != 0) return;

			GameSnapshot snapshot = GameStateCollector.Capture();
			foreach (GameEvent gameEvent in _eventDetector.Detect(snapshot))
			{
				_dispatcher.DispatchGameEvent(gameEvent);
			}
		}

		// 未来游戏输入框调用此入口，不在这里实现聊天 UI。
		public static TriggerEvent SubmitUserQuery(string query)
		{
			return ModContent.GetInstance<TriggerSystem>()._dispatcher.DispatchUserQuery(query);
		}

		// Hook 产生的游戏事件也统一进入 Dispatcher。
		internal static TriggerEvent SubmitGameEvent(GameEvent gameEvent)
		{
			return ModContent.GetInstance<TriggerSystem>()._dispatcher.DispatchGameEvent(gameEvent);
		}

		// 未来 HTTP/WebSocket transport 从此处消费待发送事件。
		public static bool TryDequeue(out TriggerEvent? trigger)
		{
			return ModContent.GetInstance<TriggerSystem>()._dispatcher.TryDequeue(out trigger);
		}

		public static int PendingCount => ModContent.GetInstance<TriggerSystem>()._dispatcher.PendingCount;

		private void Reset()
		{
			_eventDetector.Reset();
			_periodicSource.Reset();
			_dispatcher.Clear();
		}
	}
}
