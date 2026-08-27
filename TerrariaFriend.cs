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

	// 模组各类文件的说明请参考 tModLoader 基础模组开发指南
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
