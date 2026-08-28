#nullable enable

using System;
using System.Collections.Generic;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader;

namespace TerrariaFriend.Triggering
{
	/// <summary>
	/// 首领死亡时发出确认击败事件
	/// 首领从场上消失时仍由状态检测发出战斗结束事件
	/// </summary>
	[Autoload(Side = ModSide.Client)]
	public sealed class BossDefeatGlobalNpc : GlobalNPC
	{
		private static readonly HashSet<string> EmittedEncounterKeys = new HashSet<string>();

		public override void OnSpawn(NPC npc, IEntitySource source)
		{
			if (!npc.boss) return;
			BossIdentity identity = Normalize(npc);
			// 新生成的规范身份会开始一次新遭遇
			// 即使本世界此前已有击败记录也可以再次被击败
			EmittedEncounterKeys.Remove(identity.Id);
		}

		public override void OnKill(NPC npc)
		{
			if (!npc.boss) return;

			BossIdentity identity = Normalize(npc);
			if (HasOtherActiveMember(identity.Id, npc.whoAmI)) return;
			if (!EmittedEncounterKeys.Add(identity.Id)) return;

			TriggerSystem.SubmitGameEvent(new GameEvent(
				GameEventType.BossDefeated,
				identity.Id,
				identity.Name));
		}

		internal static void ResetWorldState()
		{
			EmittedEncounterKeys.Clear();
		}

		private static bool HasOtherActiveMember(string identityId, int killedWhoAmI)
		{
			for (int index = 0; index < Main.maxNPCs; index++)
			{
				NPC candidate = Main.npc[index];
				if (candidate.whoAmI == killedWhoAmI || !candidate.active || !candidate.boss)
					continue;
				if (string.Equals(Normalize(candidate).Id, identityId, StringComparison.Ordinal))
					return true;
			}
			return false;
		}

		private static BossIdentity Normalize(NPC npc)
		{
			if (IsAny(npc.type, NPCID.EaterofWorldsHead, NPCID.EaterofWorldsBody, NPCID.EaterofWorldsTail))
				return new BossIdentity("vanilla:eater_of_worlds", "Eater of Worlds");
			if (IsAny(npc.type, NPCID.TheDestroyer, NPCID.TheDestroyerBody, NPCID.TheDestroyerTail))
				return new BossIdentity("vanilla:the_destroyer", "The Destroyer");
			if (IsAny(npc.type, NPCID.Retinazer, NPCID.Spazmatism))
				return new BossIdentity("vanilla:the_twins", "The Twins");
			if (IsAny(npc.type, NPCID.WallofFlesh, NPCID.WallofFleshEye))
				return new BossIdentity("vanilla:wall_of_flesh", "Wall of Flesh");
			if (IsAny(npc.type, NPCID.Golem, NPCID.GolemHead, NPCID.GolemHeadFree))
				return new BossIdentity("vanilla:golem", "Golem");
			if (IsAny(npc.type, NPCID.MoonLordCore, NPCID.MoonLordHead, NPCID.MoonLordHand))
				return new BossIdentity("vanilla:moon_lord", "Moon Lord");

			if (npc.ModNPC != null)
			{
				return new BossIdentity(
					$"mod:{npc.ModNPC.Mod.Name}:{npc.ModNPC.Name}",
					npc.FullName);
			}
			return new BossIdentity($"vanilla:{npc.type}", npc.FullName);
		}

		private static bool IsAny(int type, params int[] candidates)
		{
			foreach (int candidate in candidates)
				if (type == candidate) return true;
			return false;
		}

		private sealed record BossIdentity(string Id, string Name);
	}

	[Autoload(Side = ModSide.Client)]
	public sealed class BossDefeatLifecycleSystem : ModSystem
	{
		public override void OnWorldLoad() => BossDefeatGlobalNpc.ResetWorldState();
		public override void OnWorldUnload() => BossDefeatGlobalNpc.ResetWorldState();
	}
}
