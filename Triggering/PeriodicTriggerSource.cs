using System.Diagnostics;

namespace TerrariaFriend.Triggering
{
	public sealed class PeriodicTriggerSource
	{
		public const int PeriodicIntervalSeconds = 60;

		private readonly Stopwatch _stopwatch = Stopwatch.StartNew();

		// Stopwatch 使用 wall-clock，不受 Terraria 昼夜时间影响。
		public bool TryConsumeDueTrigger()
		{
			if (_stopwatch.Elapsed.TotalSeconds < PeriodicIntervalSeconds) return false;

			_stopwatch.Restart();
			return true;
		}

		public void Reset()
		{
			_stopwatch.Restart();
		}
	}
}
