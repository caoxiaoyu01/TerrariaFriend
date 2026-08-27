using System.Collections.Generic;
using System.IO;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;
using TerrariaFriend.GameState.Tracking;

namespace TerrariaFriend.GameState.Persistence
{
	// 保存需要由模组维护的世界级历史状态
	public class CompanionWorldState : ModSystem
	{
		private const string VisitedRegionsKey = "visitedRegions";
		private const string VisitedCellsKey = "visitedCells";
		private const string DiscoveredSceneFeaturesKey = "discoveredSceneFeatures";
		private const string WorldEventOccurrencesKey = "worldEventOccurrences";
		private readonly HashSet<string> _visitedRegions = new HashSet<string>();
		private readonly HashSet<ExplorationCell> _visitedCells = new HashSet<ExplorationCell>();
		private readonly HashSet<string> _discoveredSceneFeatures = new HashSet<string>();
		private readonly Dictionary<string, int> _worldEventOccurrences = new Dictionary<string, int>();

		public IReadOnlyCollection<string> VisitedRegions => _visitedRegions;
		public IReadOnlyCollection<ExplorationCell> VisitedCells => _visitedCells;
		public IReadOnlyCollection<string> DiscoveredSceneFeatures => _discoveredSceneFeatures;

		public void MarkVisited(string region)
		{
			if (_visitedRegions.Add(region) && Main.netMode == NetmodeID.Server)
			{
				NetMessage.SendData(MessageID.WorldData);
			}
		}

		// 返回 true 表示这是首次记录的格网
		public bool MarkCellVisited(ExplorationCell cell)
		{
			bool added = _visitedCells.Add(cell);
			if (added && Main.netMode == NetmodeID.Server)
			{
				NetMessage.SendData(MessageID.WorldData);
			}

			return added;
		}

		// 返回真表示该场景特征在这个世界中第一次被记录
		public bool MarkSceneFeatureDiscovered(string featureKey)
		{
			bool added = _discoveredSceneFeatures.Add(featureKey);
			if (!added) return false;

			if (Main.netMode == NetmodeID.MultiplayerClient)
			{
				ModPacket packet = Mod.GetPacket();
				packet.Write((byte)TerrariaFriendMessageType.SceneFeatureDiscovered);
				packet.Write(featureKey);
				packet.Send();
			}
			else if (Main.netMode == NetmodeID.Server)
			{
				NetMessage.SendData(MessageID.WorldData);
			}

			return true;
		}

		public int GetWorldEventOccurrenceCount(string eventId)
		{
			_worldEventOccurrences.TryGetValue(eventId, out int previousCount);
			return previousCount;
		}

		// 事件结束后将本次经历写入历史
		public int CompleteWorldEventOccurrence(string eventId)
		{
			int previousCount = GetWorldEventOccurrenceCount(eventId);
			_worldEventOccurrences[eventId] = previousCount + 1;
			return previousCount;
		}

		public override void ClearWorld()
		{
			_visitedRegions.Clear();
			_visitedCells.Clear();
			_discoveredSceneFeatures.Clear();
			_worldEventOccurrences.Clear();
		}

		public override void SaveWorldData(TagCompound tag)
		{
			tag[VisitedRegionsKey] = new List<string>(_visitedRegions);
			tag[VisitedCellsKey] = SaveCells(_visitedCells);
			tag[DiscoveredSceneFeaturesKey] = new List<string>(_discoveredSceneFeatures);
			tag[WorldEventOccurrencesKey] = SaveOccurrences(_worldEventOccurrences);
		}

		public override void LoadWorldData(TagCompound tag)
		{
			_visitedRegions.UnionWith(tag.GetList<string>(VisitedRegionsKey));
			LoadCells(tag.GetList<TagCompound>(VisitedCellsKey), _visitedCells);
			_discoveredSceneFeatures.UnionWith(tag.GetList<string>(DiscoveredSceneFeaturesKey));
			LoadOccurrences(tag.GetList<TagCompound>(WorldEventOccurrencesKey), _worldEventOccurrences);
		}

		public override void NetSend(BinaryWriter writer)
		{
			writer.Write((byte)_visitedRegions.Count);
			foreach (string region in _visitedRegions) writer.Write(region);
			writer.Write(_visitedCells.Count);
			foreach (ExplorationCell cell in _visitedCells)
			{
				writer.Write(cell.X);
				writer.Write(cell.Y);
			}
			writer.Write(_discoveredSceneFeatures.Count);
			foreach (string featureKey in _discoveredSceneFeatures) writer.Write(featureKey);
			WriteOccurrences(writer, _worldEventOccurrences);
		}

		public override void NetReceive(BinaryReader reader)
		{
			_visitedRegions.Clear();
			int count = reader.ReadByte();
			for (int i = 0; i < count; i++) _visitedRegions.Add(reader.ReadString());

			_visitedCells.Clear();
			int cellCount = reader.ReadInt32();
			for (int i = 0; i < cellCount; i++)
			{
				_visitedCells.Add(new ExplorationCell(reader.ReadInt32(), reader.ReadInt32()));
			}

			_discoveredSceneFeatures.Clear();
			int featureCount = reader.ReadInt32();
			for (int i = 0; i < featureCount; i++)
			{
				_discoveredSceneFeatures.Add(reader.ReadString());
			}

			ReadOccurrences(reader, _worldEventOccurrences);
		}

		private static List<TagCompound> SaveCells(HashSet<ExplorationCell> cells)
		{
			List<TagCompound> values = new List<TagCompound>();
			foreach (ExplorationCell cell in cells)
			{
				values.Add(new TagCompound { ["x"] = cell.X, ["y"] = cell.Y });
			}
			return values;
		}

		private static void LoadCells(
			IList<TagCompound> values,
			HashSet<ExplorationCell> cells)
		{
			cells.Clear();
			foreach (TagCompound value in values)
			{
				cells.Add(new ExplorationCell(value.GetInt("x"), value.GetInt("y")));
			}
		}

		private static List<TagCompound> SaveOccurrences(Dictionary<string, int> occurrences)
		{
			List<TagCompound> values = new List<TagCompound>();
			foreach ((string id, int count) in occurrences)
			{
				values.Add(new TagCompound { ["id"] = id, ["count"] = count });
			}
			return values;
		}

		private static void LoadOccurrences(
			IList<TagCompound> values,
			Dictionary<string, int> occurrences)
		{
			occurrences.Clear();
			foreach (TagCompound value in values)
			{
				occurrences[value.GetString("id")] = value.GetInt("count");
			}
		}

		private static void WriteOccurrences(BinaryWriter writer, Dictionary<string, int> occurrences)
		{
			writer.Write(occurrences.Count);
			foreach ((string id, int count) in occurrences)
			{
				writer.Write(id);
				writer.Write(count);
			}
		}

		private static void ReadOccurrences(BinaryReader reader, Dictionary<string, int> occurrences)
		{
			occurrences.Clear();
			int count = reader.ReadInt32();
			for (int i = 0; i < count; i++)
			{
				occurrences[reader.ReadString()] = reader.ReadInt32();
			}
		}
	}
}
