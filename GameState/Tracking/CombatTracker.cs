using Terraria;
using Terraria.DataStructures;
using Terraria.ModLoader;

namespace TerrariaFriend.GameState.Tracking
{
	// 玩家受伤时把记录放进短期缓存
	public class CombatTracker : ModPlayer
	{
		private const float TicksPerSecond = 60f;
		private readonly EventBuffer _events = new EventBuffer();
		private bool _inCombat;
		private uint _combatStartTick;

		public override void OnEnterWorld()
		{
			_events.Clear();
			_inCombat = false;
			_combatStartTick = 0;
		}

		public override void OnHurt(Player.HurtInfo info)
		{
			(string source, bool isHostile) = GetDamageSource(info.DamageSource);
			_events.AddDamage(Main.GameUpdateCount, info.Damage, source, isHostile);
		}

		internal DamageWindow GetRecentDamage(uint currentTick)
		{
			return _events.GetRecentDamage(currentTick);
		}

		// 只在刚进入战斗时记录开始时刻
		internal float UpdateCombatState(bool combatCondition, uint currentTick)
		{
			if (!combatCondition)
			{
				_inCombat = false;
				_combatStartTick = 0;
				return 0f;
			}

			if (!_inCombat)
			{
				_inCombat = true;
				_combatStartTick = currentTick;
			}

			return (currentTick - _combatStartTick) / TicksPerSecond;
		}

		private static (string Source, bool IsHostile) GetDamageSource(PlayerDeathReason reason)
		{
			if (reason.TryGetCausingEntity(out Entity entity))
			{
				if (entity is NPC npc) return (npc.FullName, !npc.friendly);
				if (entity is Projectile projectile)
				{
					return (Lang.GetProjectileName(projectile.type).Value, projectile.hostile);
				}
				if (entity is Player player) return (player.name, true);
			}

			return ("Environment", false);
		}
	}
}
