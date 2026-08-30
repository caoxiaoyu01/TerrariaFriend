#nullable enable

using System;

namespace TerrariaFriend.Triggering
{
	// 集中定义触发队列的保留和替换规则
	public static class TriggerQueuePolicy
	{
		public static bool IsProtected(GameEventType eventType)
		{
			return eventType is
				GameEventType.BossDefeated or
				GameEventType.PlayerDied or
				GameEventType.WorldSessionEnded or
				GameEventType.ProgressMilestoneChanged;
		}

		public static bool IsLatestWins(GameEventType eventType)
		{
			return eventType == GameEventType.EquipmentChanged;
		}

		public static bool ShouldReplace(GameEventType queued, GameEventType newer)
		{
			return queued == newer && IsLatestWins(newer);
		}

		public static bool ShouldDropPeriodic(bool isBusyOrPending)
		{
			return isBusyOrPending;
		}

		public static bool IsExpired(
			TriggerEvent trigger,
			DateTimeOffset now,
			TimeSpan ttl)
		{
			if (trigger.TriggerType != TriggerType.GAME_EVENT || trigger.GameEvent == null)
			{
				return false;
			}

			return !IsProtected(trigger.GameEvent.EventType) && now - trigger.Timestamp > ttl;
		}

		public static double AgeSeconds(TriggerEvent trigger, DateTimeOffset now)
		{
			return Math.Max(0, (now - trigger.Timestamp).TotalSeconds);
		}
	}
}
