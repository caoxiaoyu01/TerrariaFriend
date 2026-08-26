using System.IO;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;
using TerrariaFriend.Triggering;

namespace TerrariaFriend
{
	internal enum TerrariaFriendMessageType : byte
	{
		SceneFeatureDiscovered
	}

	// Please read https://github.com/tModLoader/tModLoader/wiki/Basic-tModLoader-Modding-Guide#mod-skeleton-contents for more information about the various files in a mod.
	public class TerrariaFriend : Mod
	{
		public override void HandlePacket(BinaryReader reader, int whoAmI)
		{
			TerrariaFriendMessageType messageType = (TerrariaFriendMessageType)reader.ReadByte();
			if (messageType != TerrariaFriendMessageType.SceneFeatureDiscovered
				|| Main.netMode != NetmodeID.Server)
			{
				return;
			}

			string featureKey = reader.ReadString();
			if (!DiscoverableSceneFeatures.ContainsKey(featureKey)) return;

			ModContent.GetInstance<CompanionWorldState>()
				.MarkSceneFeatureDiscovered(featureKey);
		}
	}
}
