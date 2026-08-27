#nullable enable

using System.Collections.Generic;
using System.Linq;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;
using TerrariaFriend.GameState.Snapshots;
using TerrariaFriend.Triggering;

namespace TerrariaFriend.GameState.Tracking
{
	// 根据玩家跨越的固定格网识别未探索空间
	public sealed class ExplorationGridTracker
	{
		public const int ExplorationCellSize = 100;

		private ExplorationCell? _lastCell;
		private SceneEnvironment? _lastEnvironment;
		private readonly HashSet<ExplorationCell> _sessionVisitedCells = new HashSet<ExplorationCell>();

		public bool TryDiscover(
			GameSnapshot snapshot,
			out GameEvent? gameEvent,
			out GameEventContext? eventContext)
		{
			ExplorationCell currentCell = FromPosition(snapshot.Player);
			SceneEnvironment currentEnvironment = CaptureEnvironment(snapshot.Scene);

			// 第一次采集只建立出生位置 baseline
			if (_lastCell == null)
			{
				MarkCellVisited(currentCell);
				_lastCell = currentCell;
				_lastEnvironment = currentEnvironment;
				gameEvent = null;
				eventContext = null;
				return false;
			}

			if (_lastCell.Value == currentCell)
			{
				_lastEnvironment = currentEnvironment;
				gameEvent = null;
				eventContext = null;
				return false;
			}

			SceneEnvironment previousEnvironment = _lastEnvironment!;
			_lastCell = currentCell;
			_lastEnvironment = currentEnvironment;

			if (!MarkCellVisited(currentCell))
			{
				gameEvent = null;
				eventContext = null;
				return false;
			}

			gameEvent = new GameEvent(
				GameEventType.NewAreaDiscovered,
				CellX: currentCell.X,
				CellY: currentCell.Y);
			eventContext = new GameEventContext(
				ProgressionStage: snapshot.Progress.CurrentStage.Id,
				Biomes: currentEnvironment.Biomes,
				Layer: currentEnvironment.Layer,
				MiniBiomes: currentEnvironment.MiniBiomes,
				SpecialAreas: currentEnvironment.SpecialAreas,
				PreviousBiomes: previousEnvironment.Biomes,
				PreviousLayer: previousEnvironment.Layer,
				PreviousMiniBiomes: previousEnvironment.MiniBiomes,
				PreviousSpecialAreas: previousEnvironment.SpecialAreas);
			return true;
		}

		public void Reset()
		{
			_lastCell = null;
			_lastEnvironment = null;
			_sessionVisitedCells.Clear();
		}

		public static ExplorationCell FromPosition(PlayerSnapshot player)
		{
			return new ExplorationCell(
				(int)(player.PositionTileX / ExplorationCellSize),
				(int)(player.PositionTileY / ExplorationCellSize));
		}

		private static SceneEnvironment CaptureEnvironment(SceneSnapshot scene)
		{
			return new SceneEnvironment(
				scene.Biomes.ToArray(),
				scene.Layer,
				scene.MiniBiomes.ToArray(),
				scene.SpecialAreas.ToArray());
		}

		private bool MarkCellVisited(ExplorationCell cell)
		{
			// 会话集合避免多人同步覆盖客户端临时状态后重复触发
			if (!_sessionVisitedCells.Add(cell)) return false;
			return ModContent.GetInstance<CompanionWorldState>().MarkCellVisited(cell);
		}

		private sealed record SceneEnvironment(
			IReadOnlyList<string> Biomes,
			string Layer,
			IReadOnlyList<string> MiniBiomes,
			IReadOnlyList<string> SpecialAreas);
	}
}
