using System.Collections.Generic;
using System.IO;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace TerrariaFriend.GameState.Persistence
{
	// 保存“这个世界曾经探索过哪些关键区域”。
	public class CompanionWorldState : ModSystem
	{
		private const string VisitedRegionsKey = "visitedRegions";
		private readonly HashSet<string> _visitedRegions = new HashSet<string>();

		public IReadOnlyCollection<string> VisitedRegions => _visitedRegions;

		public void MarkVisited(string region)
		{
			if (_visitedRegions.Add(region) && Main.netMode == NetmodeID.Server)
			{
				NetMessage.SendData(MessageID.WorldData);
			}
		}

		public override void ClearWorld()
		{
			_visitedRegions.Clear();
		}

		public override void SaveWorldData(TagCompound tag)
		{
			tag[VisitedRegionsKey] = new List<string>(_visitedRegions);
		}

		public override void LoadWorldData(TagCompound tag)
		{
			_visitedRegions.UnionWith(tag.GetList<string>(VisitedRegionsKey));
		}

		public override void NetSend(BinaryWriter writer)
		{
			writer.Write((byte)_visitedRegions.Count);
			foreach (string region in _visitedRegions) writer.Write(region);
		}

		public override void NetReceive(BinaryReader reader)
		{
			_visitedRegions.Clear();
			int count = reader.ReadByte();
			for (int i = 0; i < count; i++) _visitedRegions.Add(reader.ReadString());
		}
	}
}
