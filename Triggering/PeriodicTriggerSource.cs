using System.Diagnostics;

namespace TerrariaFriend.Triggering
{
	public sealed class PeriodicTriggerSource
	{
		public const int PeriodicIntervalSeconds = 60;

		private readonly Stopwatch _stopwatch = Stopwatch.StartNew();

		// 计时器使用现实时间且不受泰拉瑞亚昼夜时间影响
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
