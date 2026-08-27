#nullable enable

using System.Collections.Generic;

namespace TerrariaFriend.GameState.Tracking
{
	internal sealed record DamageWindow(
		int TotalDamage,
		int LastDamageAmount,
		string? LastDamageSource,
		float TimeSinceLastDamageSeconds,
		bool HasHostileDamage);

	// 保存最近五秒内发生的短期战斗事件
	internal sealed class EventBuffer
	{
		private const uint WindowTicks = 5 * 60;
		private const float TicksPerSecond = 60f;
		private readonly Queue<DamageEvent> _damageEvents = new Queue<DamageEvent>();

		public void AddDamage(uint tick, int damage, string source, bool isHostile)
		{
			_damageEvents.Enqueue(new DamageEvent(tick, damage, source, isHostile));
			RemoveExpired(tick);
		}

		public DamageWindow GetRecentDamage(uint currentTick)
		{
			RemoveExpired(currentTick);

			int totalDamage = 0;
			DamageEvent? lastDamage = null;
			bool hasHostileDamage = false;
			foreach (DamageEvent damageEvent in _damageEvents)
			{
				totalDamage += damageEvent.Damage;
				lastDamage = damageEvent;
				hasHostileDamage |= damageEvent.IsHostile;
			}

			return new DamageWindow(
				totalDamage,
				lastDamage?.Damage ?? 0,
				lastDamage?.Source,
				lastDamage == null ? 0f : (currentTick - lastDamage.Tick) / TicksPerSecond,
				hasHostileDamage);
		}

		public void Clear()
		{
			_damageEvents.Clear();
		}

		private void RemoveExpired(uint currentTick)
		{
			while (_damageEvents.Count > 0 && currentTick - _damageEvents.Peek().Tick > WindowTicks)
			{
				_damageEvents.Dequeue();
			}
		}
	}
}
